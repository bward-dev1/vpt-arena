"""Generate PvP demonstrations with a scripted teacher in the cloud arenas, in VPT recorder format.

The teacher uses one privileged trick: `/tp @p ~ ~ ~ facing entity <nearest opponent> eyes` tells it which way
the opponent is (we read the resulting yaw/pitch, then turn back). It then turns toward the opponent at most
10 degrees per tick (VPT's camera range), sprints at it, jumps over small steps, and swings on the 1.9 attack
cooldown when roughly aimed. Strafes a little when close. Every tick it records the frame it saw BEFORE acting
and the action it took, so behaviour cloning learns "see opponent -> turn, chase, hit".

    xvfb-run -a python cloud/teacher_demos.py --modes duels_sword,kitpvp --minutes 60 --out demos/
Writes demos/<mode>/<stem>.mp4 + .jsonl + .meta.json (source "teacher"), readable by train_bc.
"""
import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from vpt_arena import games  # noqa: E402
from vpt_arena.rl.arena_tasks import TASKS  # noqa: E402
from vpt_arena.rl.sim_env import ArenaSimEnv, position  # noqa: E402
from vpt_arena.vpt import env_action_to_json, noop_env_action  # noqa: E402

MELEE = ["duels_sword", "duels_classic", "duels_uhc", "duels_nodebuff", "duels_combo", "duels_boxing", "duels_sumo",
         "kitpvp", "survival_games", "duels_bow"]


def yaw_pitch(info):
    p = info.get("player_pos") or {}
    return float(p.get("yaw", 0.0)), float(p.get("pitch", 0.0))


def wrap(a):
    return (a + 180.0) % 360.0 - 180.0


class Teacher:
    def __init__(self, env, rng):
        self.env, self.rng = env, rng
        self.t = 0
        self.last_swing = -99
        self.strafe = 0
        self.cached = None  # (yaw, pitch) of the opponent, refreshed every few ticks (each look-up costs 2 game ticks)

    def target_direction(self):
        """Ask the game which way the nearest opponent is; returns (yaw, pitch) or None. Restores facing after."""
        sim = self.env.sim
        yaw0, pitch0 = yaw_pitch(self.env.prev)
        try:
            _, _, _, info = sim.env.execute_cmd(
                "/tp @p ~ ~ ~ facing entity @e[type=!player,type=!item,type=!arrow,distance=..48,limit=1,sort=nearest] eyes")
        except Exception:
            return None
        p = info.get("player_pos") or info.get("location_stats") or {}
        yaw = float(p.get("yaw", yaw0)) if isinstance(p, dict) else yaw0
        pitch = float(p.get("pitch", pitch0)) if isinstance(p, dict) else pitch0
        try:
            sim.env.execute_cmd(f"/tp @p ~ ~ ~ {yaw0:.2f} {pitch0:.2f}")
        except Exception:
            pass
        if abs(wrap(yaw - yaw0)) < 1e-3 and abs(pitch - pitch0) < 1e-3:
            return None  # nothing to face (no opponent in range)
        return yaw, pitch

    def act(self):
        a = noop_env_action()
        yaw0, pitch0 = yaw_pitch(self.env.prev)
        if self.t % 5 == 0 or self.cached is None:
            self.cached = self.target_direction()
        tgt = self.cached
        if tgt is None:  # no opponent: walk forward and look around a little
            a["forward"] = 1
            a["camera"] = np.array([0.0, self.rng.uniform(-4, 4)])
            self.t += 1
            return a
        dyaw, dpitch = wrap(tgt[0] - yaw0), tgt[1] - pitch0
        # human-like turning: proportional, capped at VPT's 10 degrees per tick, a little noise
        cy = float(np.clip(0.6 * dyaw + self.rng.gauss(0, 0.6), -10, 10))
        cp = float(np.clip(0.6 * dpitch + self.rng.gauss(0, 0.4), -10, 10))
        a["camera"] = np.array([cp, cy])  # VPT order: [pitch, yaw]
        aimed = abs(dyaw) < 12 and abs(dpitch) < 15
        a["forward"] = 1
        a["sprint"] = 1 if abs(dyaw) < 45 else 0
        if self.t % 40 == 0:
            self.strafe = self.rng.choice([0, 0, -1, 1])
        if self.strafe and aimed:
            a["left" if self.strafe < 0 else "right"] = 1
        if self.rng.random() < 0.04:
            a["jump"] = 1
        if aimed and self.t - self.last_swing >= 11:  # about the 1.9 sword cooldown at 20 Hz
            a["attack"] = 1
            self.last_swing = self.t
        self.t += 1
        return a


def record_episode(env, mode, out_dir, rng, max_steps):
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / f"{mode}-{int(time.time() * 1000)}-{rng.randint(0, 9999):04d}"
    env.reset()
    teacher = Teacher(env, rng)
    writer = cv2.VideoWriter(str(stem) + ".mp4", cv2.VideoWriter_fourcc(*"mp4v"), 20, (640, 360))
    lines, ret, won, n = [], 0.0, False, 0
    pov = env.last_pov if getattr(env, "last_pov", None) is not None else None
    done = False
    hotbar = 0
    while not done and n < max_steps:
        a = teacher.act()
        # the frame the teacher saw before acting (taken after its look-up commands restored the view)
        frame = getattr(env, "last_pov", None)
        _, r, done, info = env.step(a)
        if frame is None:
            frame = env.last_pov
        if frame is not None:
            writer.write(cv2.cvtColor(cv2.resize(frame, (640, 360)), cv2.COLOR_RGB2BGR))
            lines.append(json.dumps(env_action_to_json(a, hotbar)))
        ret += r
        won = won or bool(info.get("won"))
        n += 1
    writer.release()
    Path(str(stem) + ".jsonl").write_text("\n".join(lines) + "\n")
    meta = dict(mode=mode, source="teacher", weight=1.0, loss_weight=1.0, won=won, ret=round(ret, 2), frames=len(lines))
    Path(str(stem) + ".meta.json").write_text(json.dumps(meta))
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", default=",".join(MELEE))
    ap.add_argument("--minutes", type=float, default=60)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--difficulty", type=float, default=0.6)
    ap.add_argument("--max-steps", type=int, default=1200)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    modes = args.modes.split(",")
    env = ArenaSimEnv(modes[0], seed=args.seed, difficulty=args.difficulty)
    deadline = time.time() + args.minutes * 60
    stats = []
    i = 0
    while time.time() < deadline:
        mode = modes[i % len(modes)]
        i += 1
        env.task, env.mode = TASKS[mode], mode
        m = record_episode(env, mode, Path(args.out) / mode, rng, args.max_steps)
        stats.append(m)
        print(json.dumps(m), flush=True)
    won = sum(s["won"] for s in stats)
    summary = {"episodes": len(stats), "wins": won, "frames": sum(s["frames"] for s in stats),
               "by_mode": {m: {"episodes": sum(1 for s in stats if s["mode"] == m),
                               "wins": sum(1 for s in stats if s["mode"] == m and s["won"])} for m in modes}}
    (Path(args.out) / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary), flush=True)
    env.close()


if __name__ == "__main__":
    main()
