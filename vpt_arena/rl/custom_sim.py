"""Custom simulations from the site's Simulation Lab: validate a spec (configs/sim_spec.json) and build an arena Task.

The same rules run in the Cloudflare worker (on submit), in the local relay (before dispatch) and in the
cloud runner (before anything reaches Minecraft), so a bad spec never turns into a game command.
"""
import json
import math
from pathlib import Path

from .. import games
from . import arena_tasks as A

SPEC = json.loads((Path(__file__).resolve().parents[2] / "configs" / "sim_spec.json").read_text())
L, E, D = SPEC["limits"], SPEC["enums"], SPEC["defaults"]


class SpecError(ValueError):
    pass


def _int(v, lo_hi, name):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v:
        raise SpecError(f"{name} must be a whole number")
    v = int(v)
    if not lo_hi[0] <= v <= lo_hi[1]:
        raise SpecError(f"{name} must be between {lo_hi[0]} and {lo_hi[1]}")
    return v


def _enum(v, options, name):
    if v not in options:
        raise SpecError(f"{name} must be one of: {', '.join(options)}")
    return v


def _keys(d, allowed, name):
    if not isinstance(d, dict):
        raise SpecError(f"{name} must be an object")
    extra = set(d) - set(allowed)
    if extra:
        raise SpecError(f"unknown field(s) in {name}: {', '.join(sorted(extra))}")


def validate(spec, releases=()):
    """Return a normalised copy of spec, or raise SpecError with a readable message."""
    _keys(spec, D.keys(), "spec")
    s = json.loads(json.dumps(D))  # defaults, deep copy
    for k, v in spec.items():
        if isinstance(v, dict) and isinstance(s.get(k), dict):
            s[k].update(v)
        else:
            s[k] = v
    name = s["name"]
    if not isinstance(name, str) or not name.strip() or len(name) > L["name_max"]:
        raise SpecError(f"name must be 1-{L['name_max']} characters")
    s["name"] = "".join(ch for ch in name if ch.isprintable()).strip()
    m = s["model"]
    if m not in ("baseline", "latest") and m not in releases:
        raise SpecError("model must be baseline, latest, or an existing round-N release")
    if s["base_mode"] not in games.BY_KEY:
        raise SpecError("base_mode must be a game mode key")
    a = s["arena"]
    _keys(a, D["arena"].keys(), "arena")
    a["size"] = _int(a["size"], L["arena_size"], "arena.size")
    _enum(a["floor"], E["floor"], "arena.floor")
    _enum(a["hazard"], E["hazard"], "arena.hazard")
    _enum(a["time"], E["time"], "arena.time")
    p = s["player"]
    _keys(p, D["player"].keys(), "player")
    _enum(p["weapon"], E["weapon"], "player.weapon")
    _enum(p["armor"], E["armor"], "player.armor")
    if not isinstance(p["bow"], bool):
        raise SpecError("player.bow must be true or false")
    p["arrows"] = _int(p["arrows"], L["arrows"], "player.arrows")
    p["blocks"] = _int(p["blocks"], L["blocks"], "player.blocks")
    p["gapples"] = _int(p["gapples"], L["gapples"], "player.gapples")
    ops = s["opponents"]
    if not isinstance(ops, list) or not L["opponent_groups"][0] <= len(ops) <= L["opponent_groups"][1]:
        raise SpecError(f"opponents must be a list of {L['opponent_groups'][0]}-{L['opponent_groups'][1]} groups")
    total = 0
    for i, o in enumerate(ops):
        _keys(o, D["opponents"][0].keys(), f"opponents[{i}]")
        o = {**D["opponents"][0], **o}
        ops[i] = o
        _enum(o["type"], E["opponent_type"], f"opponents[{i}].type")
        o["count"] = _int(o["count"], L["opponent_count"], f"opponents[{i}].count")
        _enum(o["weapon"], E["weapon"], f"opponents[{i}].weapon")
        _enum(o["armor"], E["armor"], f"opponents[{i}].armor")
        o["distance"] = _int(o["distance"], L["opponent_distance"], f"opponents[{i}].distance")
        total += o["count"]
    if total > L["opponents_total_max"]:
        raise SpecError(f"at most {L['opponents_total_max']} opponents in total")
    g = s["goal"]
    _keys(g, D["goal"].keys(), "goal")
    _enum(g["type"], E["goal"], "goal.type")
    g["distance"] = _int(g["distance"], L["goal_distance"], "goal.distance")
    if g["type"] != "none" and a["hazard"] == "ground":
        raise SpecError("bridge and bed goals need a void or lava arena")
    s["seconds"] = _int(s["seconds"], L["seconds"], "seconds")
    s["episodes"] = _int(s["episodes"], L["episodes"], "episodes")
    d = s["difficulty"]
    if isinstance(d, bool) or not isinstance(d, (int, float)) or not L["difficulty"][0] <= d <= L["difficulty"][1]:
        raise SpecError("difficulty must be between 0 and 1")
    s["difficulty"] = float(d)
    s["seed"] = _int(s["seed"], L["seed"], "seed")
    return s


def to_task(s):
    """A validated spec -> arena Task (commands built only from whitelisted values)."""
    a, p, g = s["arena"], s["player"], s["goal"]
    sky = a["hazard"] != "ground"
    setup = list(A.BASE)
    setup.append("/time set 18000" if a["time"] == "night" else "/time set 6000")
    if sky:
        setup += A.platform(a["size"], a["floor"], pit=a["hazard"] == "lava")
    if p["weapon"] != "none":
        setup += A.give(p["weapon"])
    if p["armor"] != "none":
        setup += A.armour(p["armor"])
    if p["bow"]:
        setup += A.give("bow", f"arrow {max(1, p['arrows'])}")
    if p["blocks"]:
        setup += A.give(f"white_wool {p['blocks']}")
    if p["gapples"]:
        setup += A.give(f"golden_apple {p['gapples']}")
    goal, targets = None, ()
    if g["type"] in ("bridge", "bed"):
        setup += A.island(g["distance"], 0, 3, "end_stone")
        goal = (g["distance"], 0)
        if g["type"] == "bed":
            setup += [f"/setblock ~{g['distance']} ~ ~0 minecraft:red_bed[facing=east,part=foot]",
                      f"/setblock ~{g['distance'] + 1} ~ ~0 minecraft:red_bed[facing=east,part=head]"]
            targets = ("red_bed",)
    opponents = []
    n_total = sum(o["count"] for o in s["opponents"])
    k = 0
    for o in s["opponents"]:
        for _ in range(o["count"]):
            # spread opponents on an arc in front of the player (who faces +x)
            ang = 0.0 if n_total == 1 else (-0.9 + 1.8 * k / (n_total - 1))
            dx, dz = round(o["distance"] * math.cos(ang)), round(o["distance"] * math.sin(ang))
            if goal:  # opponents defend the goal island instead
                dx, dz = goal[0] + (k % 2), (k - n_total // 2)
            opponents.append(A.mob(o["type"], dx, dz, None if o["weapon"] == "none" else o["weapon"],
                                   None if o["armor"] == "none" else o["armor"]))
            k += 1
    w = dict(progress=0.3 if goal else 0.0, goal=5.0 if g["type"] == "bridge" else 0.0,
             target=10.0 if targets else 0.0, collect=0.0)
    return A.T(s["base_mode"], setup, opponents, sky=sky, goal=goal, target_blocks=targets,
               max_steps=s["seconds"] * 20, w=w)


def describe(s):
    """One plain sentence for logs and the result page."""
    ops = ", ".join(f"{o['count']} {o['type']}" + (f" ({o['armor']}, {o['weapon']})" if o["armor"] != "none" or
                                                    o["weapon"] != "none" else "") for o in s["opponents"]) or "no opponents"
    return (f"{s['name']}: {s['arena']['size'] * 2 + 1}x{s['arena']['size'] * 2 + 1} {s['arena']['floor']} arena over "
            f"{s['arena']['hazard']}, {s['arena']['time']}; player {s['player']['armor']} armour, {s['player']['weapon']}; "
            f"vs {ops}; goal {s['goal']['type']}; {s['seconds']} s x {s['episodes']}; model {s['model']}")
