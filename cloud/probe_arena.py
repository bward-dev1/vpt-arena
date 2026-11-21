"""Diagnose arena episodes: run ArenaSimEnv for a few modes with no-op / forward actions,
log position, health and death cause per step, and save frames."""
import json
import os
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpt_arena.rl import sim_env as S  # noqa: E402
from vpt_arena.rl.sim_env import ArenaSimEnv, health, position  # noqa: E402

OUT = Path(os.environ.get("OUT", "cloud_out"))
OUT.mkdir(exist_ok=True)
report = {}
env = None
for mode in sys.argv[1:] or ["duels_sword", "bedwars_solo", "parkour_duel"]:
    if env is None:
        env = ArenaSimEnv(mode, seed=3)
    else:
        env.task, env.mode = S.TASKS[mode], mode
    rows = []
    for ep in range(2):
        env.reset()
        rows.append({"ep": ep, "origin": env.origin, "start_pos": position(env.prev), "start_hp": health(env.prev)})
        for t in range(120):
            a = {"forward": 0}
            frame, r, done, info = env.step(a)
            p = position(env.prev)
            if t % 5 == 0 or done:
                rows.append({"t": t, "pos": [round(v, 1) for v in p] if p else None, "hp": health(env.prev), "r": r,
                             "done": done, "died": info.get("died"), "won": info.get("won")})
            if t in (0, 15, 40) or done:
                if env.last_pov is not None:
                    cv2.imwrite(str(OUT / f"{mode}_ep{ep}_t{t}.png"), cv2.cvtColor(env.last_pov, cv2.COLOR_RGB2BGR))
            if done:
                break
    report[mode] = rows
    print(mode, json.dumps(rows)[:3000], flush=True)
json.dump(report, open(OUT / "arena_probe.json", "w"), indent=1, default=str)
env.close()
