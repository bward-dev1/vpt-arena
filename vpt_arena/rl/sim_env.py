"""MineStudio-backed environment for one arena task (see arena_tasks.py).

reset() -> 128x128 RGB frame; step(env_action) -> (frame, reward, done, info).
Rewards come from MineStudio's cumulative stats in `info` (damage_dealt,
kill_entity, mine_block, pickup, craft_item, health, position), read
defensively because the exact layout varies between versions.
"""
import math
import random

import numpy as np

from .arena_tasks import TASKS, Y

ENV_KEYS = ("attack", "back", "forward", "jump", "left", "right", "sneak", "sprint", "use",
            *[f"hotbar.{i}" for i in range(1, 10)])

# survival / UHC curriculum (VPT-style): item -> (reward per unit, max units)
CURRICULUM = {
    "log": (1.0, 8), "planks": (0.25, 20), "stick": (0.25, 8), "crafting_table": (2.0, 1), "wooden_pickaxe": (4.0, 1),
    "cobblestone": (0.3, 11), "stone_pickaxe": (6.0, 1), "furnace": (6.0, 1), "coal": (1.0, 5), "iron_ore": (8.0, 3),
    "iron_ingot": (10.0, 3), "iron_pickaxe": (20.0, 1), "torch": (0.5, 8), "diamond": (40.0, 3),
}


def _num(v):
    if v is None:
        return 0.0
    if isinstance(v, dict):
        return float(sum(_num(x) for x in v.values()))
    if isinstance(v, (list, tuple, np.ndarray)):
        return float(np.sum(v)) if len(v) else 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def stat(info, key, names=None):
    """Cumulative count for info[key], optionally only entries whose name ends with one of `names`."""
    v = info.get(key)
    if not isinstance(v, dict) or names is None:
        return _num(v)
    total = 0.0
    for k, x in v.items():
        base = str(k).split(":")[-1]
        if any(base == n or base.endswith("_" + n) or base.startswith(n) for n in names):
            total += _num(x)
    return total


def position(info):
    p = info.get("player_pos")
    if isinstance(p, dict) and "x" in p:
        return float(p["x"]), float(p["y"]), float(p["z"])
    ls = info.get("location_stats")
    if isinstance(ls, dict) and "xpos" in ls:
        return float(_num(ls["xpos"])), float(_num(ls["ypos"])), float(_num(ls["zpos"]))
    return None


def health(info):
    h = info.get("health")
    if h is None and isinstance(info.get("location_stats"), dict):
        h = info["location_stats"].get("life")
    return _num(h) if h is not None else 20.0


class ArenaSimEnv:
    def __init__(self, mode, seed=0, sim=None, obs_size=(128, 128)):
        self.task = TASKS[mode]
        self.mode = mode
        self.rng = random.Random(seed)
        self.seed = seed
        if sim is None:
            from minestudio.simulator import MinecraftSim
            sim = MinecraftSim(action_type="env", obs_size=obs_size, render_size=(640, 360), seed=seed)
        self.sim = sim
        self.started = False
        self.episode = 0
        self.noop = None

    # ------------------------------------------------------------------ helpers
    def _cmd(self, c):
        try:
            self.sim.env.execute_cmd(c)
        except Exception as e:  # a bad command shouldn't kill training; log it once
            if not getattr(self, "_warned", False):
                print(f"[sim_env] command failed: {c[:80]}: {e}")
                self._warned = True

    def _noop(self):
        if self.noop is None:
            self.noop = self.sim.env.action_space.no_op()
        return dict(self.noop)

    def _idle(self, n):
        obs = info = None
        for _ in range(n):
            obs, _, _, _, info = self.sim.step(self._noop())
        return obs, info

    # ------------------------------------------------------------------ gym-ish
    def reset(self):
        if not self.started:
            obs, info = self.sim.reset()
            self.started = True
            for c in ("/gamerule doImmediateRespawn true", "/gamerule doMobSpawning false", "/gamerule doDaylightCycle false",
                      "/gamerule announceAdvancements false", "/gamerule sendCommandFeedback false",
                      "/gamerule naturalRegeneration true", "/difficulty normal", "/time set day", "/weather clear 99999"):
                self._cmd(c)
        self.episode += 1
        t = self.task
        self._cmd("/gamerule naturalRegeneration true")
        if t.sky:
            x0 = 3000 + 160 * (self.episode % 50) + 4000 * (self.seed % 5)
            z0 = 3000 + 160 * (self.episode // 50) + 4000 * (self.seed // 5)
            self._cmd(f"/tp @p {x0} {Y} {z0} -90 0")
            self._idle(12)  # let the chunks load before /fill
        else:
            cx, cz = self.rng.randint(-3000, 3000), self.rng.randint(-3000, 3000)
            self._cmd(f"/spreadplayers {cx} {cz} 0 40 false @p")
            self._idle(10)
        for c in t.setup:
            self._cmd(c)
        if t.sky:
            self._cmd(f"/tp @p {x0} {Y} {z0} -90 0")
        for c in t.opponents:
            self._cmd(c)
        obs, info = self._idle(4)
        self.t = 0
        self.prev = info
        self.origin = position(info) or (0.0, float(Y), 0.0)
        self.kills0 = stat(info, "kill_entity", t.opponent_types)
        self.n_opp = len(t.opponents)
        self.targets0 = stat(info, "mine_block", t.target_blocks) if t.target_blocks else 0.0
        self.best_dist = self._goal_dist(info)
        self.cur_units = {k: 0 for k in CURRICULUM}
        self.ret = 0.0
        return obs["image"]

    def _goal_dist(self, info):
        g = self.task.goal
        p = position(info)
        if not g or p is None:
            return None
        return math.hypot(p[0] - (self.origin[0] + g[0]), p[2] - (self.origin[2] + g[1]))

    def step(self, action):
        a = self._noop()
        for k in ENV_KEYS:
            a[k] = int(action.get(k, 0))
        a["camera"] = np.asarray(action.get("camera", (0.0, 0.0)), dtype=np.float32)
        obs, _, term, trunc, info = self.sim.step(a)
        t, w = self.task, self.task.w
        self.t += 1
        r = 0.0
        ev = {}
        dd = _num(info.get("damage_dealt")) - _num(self.prev.get("damage_dealt"))
        if dd > 0:
            r += w["damage_dealt"] * dd
        hp, hp_prev = health(info), health(self.prev)
        if hp < hp_prev:
            r += w["damage_taken"] * (hp_prev - hp)
        kills = stat(info, "kill_entity", t.opponent_types) - self.kills0
        new_kills = kills - (stat(self.prev, "kill_entity", t.opponent_types) - self.kills0)
        if new_kills > 0:
            r += w["kill"] * new_kills
            ev["kill"] = new_kills
        r += w["alive"]
        # objective blocks (bed, wool)
        hit_target = False
        if t.target_blocks:
            if stat(info, "mine_block", t.target_blocks) - self.targets0 > 0:
                hit_target = True
        # races and bridges: reward new best distance to the goal
        reached = False
        d = self._goal_dist(info)
        if d is not None and self.best_dist is not None:
            if d < self.best_dist:
                r += w["progress"] * (self.best_dist - d)
                self.best_dist = d
            reached = d < 1.5
        # survival-style collection
        if w["collect"]:
            if self.mode == "spleef":
                r += w["collect"] * max(0.0, stat(info, "mine_block", ("snow",)) - stat(self.prev, "mine_block", ("snow",)))
            else:
                for item, (rw, cap) in CURRICULUM.items():
                    have = max(stat(info, "pickup", (item,)), stat(info, "craft_item", (item,)), stat(info, "mine_block", (item,)))
                    gain = min(cap, int(have)) - self.cur_units[item]
                    if gain > 0:
                        r += w["collect"] * rw * gain
                        self.cur_units[item] += gain
        # death: health hits 0, or fell out of a sky arena, or respawned far away
        p = position(info)
        fell = t.sky and p is not None and p[1] < self.origin[1] - 8
        respawned = p is not None and t.sky and math.hypot(p[0] - self.origin[0], p[2] - self.origin[2]) > 60
        died = hp <= 0 or fell or respawned or bool(term)
        won = False
        if died:
            r += w["death"]
            ev["death"] = 1
        else:
            if t.target_blocks and hit_target:
                r += w["target"] + w["win"]
                won = True
            elif t.goal and not t.target_blocks and reached:
                r += w["goal"] + w["win"]
                won = True
            elif self.n_opp and kills >= self.n_opp and not t.goal:
                r += w["win"]
                won = True
        timeout = self.t >= t.max_steps
        if timeout and not (died or won):
            r += w["timeout"]
            if self.mode == "tnt_run":
                won = True
        done = died or won or timeout
        if done and (fell or hp <= 0):
            self._cmd("/kill @p")  # immediate respawn; next reset rebuilds
        self.prev = info
        self.ret += r
        return obs["image"], float(r), bool(done), {"won": won, "died": died, "events": ev, "mode": self.mode}

    def close(self):
        try:
            self.sim.close()
        except Exception:
            pass
