"""Probe the MineStudio simulator on a cloud runner: speed, info layout, arena commands, death handling.

Writes cloud_out/probe.json and a few frames as PNG.
"""
import json
import os
import time

import cv2
import numpy as np
from minestudio.simulator import MinecraftSim

OUT = os.environ.get("OUT", "cloud_out")
os.makedirs(OUT, exist_ok=True)
report = {}


def short(v, n=400):
    s = repr(v)
    return s if len(s) <= n else s[:n] + "..."


t0 = time.time()
sim = MinecraftSim(action_type="env", obs_size=(128, 128), render_size=(640, 360), seed=7)
obs, info = sim.reset()
report["reset_sec"] = round(time.time() - t0, 1)
report["info_keys"] = sorted(info.keys())
report["info_sample"] = {k: short(v) for k, v in info.items() if k not in ("pov", "voxels")}

cmds = [
    "/gamerule doImmediateRespawn true", "/gamerule doMobSpawning false", "/gamerule doDaylightCycle false",
    "/gamerule naturalRegeneration true", "/time set day", "/weather clear", "/difficulty normal",
    "/tp @p 1000 201 1000", "/fill 990 200 990 1010 200 1010 minecraft:smooth_stone",
    "/fill 990 201 990 1010 205 1010 minecraft:air",
    "/give @p minecraft:iron_sword 1", "/replaceitem entity @p armor.chest minecraft:iron_chestplate",
    '/summon minecraft:zombie 1004 201 1000 {PersistenceRequired:1b,HandItems:[{id:"minecraft:iron_sword",Count:1b},{}],'
    'ArmorItems:[{},{},{id:"minecraft:iron_chestplate",Count:1b},{}]}',
]
cmd_results = []
for c in cmds:
    t = time.time()
    try:
        _o, _r, _d, inf = sim.env.execute_cmd(c)
        cmd_results.append({"cmd": c[:60], "ok": True, "sec": round(time.time() - t, 2),
                            "msg": short(inf.get("message", ""), 120) if isinstance(inf, dict) else ""})
    except Exception as e:
        cmd_results.append({"cmd": c[:60], "ok": False, "err": short(e, 200)})
report["commands"] = cmd_results

noop = sim.env.action_space.no_op()
frames, healths, steps = {}, [], 0
t = time.time()
rng = np.random.default_rng(0)
for i in range(400):
    a = dict(noop)
    a["forward"] = int(rng.random() < 0.5)
    a["attack"] = int(rng.random() < 0.5)
    a["camera"] = np.array([0.0, rng.uniform(-10, 10)])
    obs, r, term, trunc, info = sim.step(a)
    steps += 1
    healths.append(float(info.get("health", -1)) if np.isscalar(info.get("health", -1)) else -1)
    if i in (0, 60, 200, 399):
        frames[i] = info["pov"]
report["fps_random_400"] = round(steps / (time.time() - t), 1)
report["health_trace_min"] = min(healths)
report["after_fight"] = {k: short(info.get(k), 600) for k in
                         ("health", "damage_dealt", "kill_entity", "location_stats", "player_pos", "mobs", "message",
                          "food_level", "equipped_items") if k in info}

# death handling
for c in ("/kill @p",):
    sim.env.execute_cmd(c)
post = []
for i in range(40):
    obs, r, term, trunc, info = sim.step(dict(noop))
    post.append((float(info.get("health", -1)) if np.isscalar(info.get("health", -1)) else -1, bool(term)))
report["after_kill_health_term"] = post[:40:4]
report["after_kill_pos"] = short(info.get("player_pos") or info.get("location_stats"), 300)
frames["after_kill"] = info["pov"]

for k, f in frames.items():
    cv2.imwrite(os.path.join(OUT, f"frame_{k}.png"), cv2.cvtColor(f, cv2.COLOR_RGB2BGR))
json.dump(report, open(os.path.join(OUT, "probe.json"), "w"), indent=1)
print(json.dumps(report, indent=1)[:6000])
sim.close()
