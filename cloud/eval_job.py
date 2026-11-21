"""Evaluate one policy on a set of modes: N episodes each, sampling actions, no training.

    xvfb-run -a python cloud/eval_job.py --weights global.weights --name round-3 --modes duels_sword,bedwars_solo --episodes 3 --out eval/
Writes eval/<name>__<first mode>.json = {"name", "modes": {mode: {"episodes", "return", "win_rate", "len"}}}.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import torch as th  # noqa: E402

from vpt_arena.agent import ArenaAgent  # noqa: E402
from vpt_arena.rl.arena_tasks import TASKS  # noqa: E402
from vpt_arena.rl.sim_env import ArenaSimEnv  # noqa: E402


class ClipWriter:
    """Every 2nd frame at 10 fps, 320x180, up to 40 s; re-encoded to H.264 yuv420p so browsers can play it."""

    def __init__(self, path, size=(320, 180), max_frames=400):
        import cv2
        self.cv2, self.path, self.size, self.max = cv2, Path(path), size, max_frames
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.raw = self.path.with_suffix(".raw.mp4")
        self.w = cv2.VideoWriter(str(self.raw), cv2.VideoWriter_fourcc(*"mp4v"), 10, size)
        self.n = 0

    def add(self, rgb):
        if self.n < self.max:
            img = self.cv2.resize(rgb, self.size, interpolation=self.cv2.INTER_AREA)
            self.w.write(self.cv2.cvtColor(img, self.cv2.COLOR_RGB2BGR))
            self.n += 1

    def close(self):
        import shutil
        self.w.release()
        if self.n and shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(self.raw), "-c:v", "libx264", "-pix_fmt",
                            "yuv420p", "-crf", "28", "-movflags", "+faststart", str(self.path)], check=False)
        elif self.n:
            print("ffmpeg missing: clip skipped", flush=True)
        self.raw.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--modes", required=True)
    ap.add_argument("--episodes", type=int, default=3)
    ap.add_argument("--arch", default="1x")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-minutes", type=float, default=80)
    ap.add_argument("--clips", default=None, help="directory for one H.264 clip per mode (first episode)")
    ap.add_argument("--difficulty", type=float, default=0.5, help="fixed opponent strength so rounds compare fairly")
    args = ap.parse_args()
    th.set_num_threads(3)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    modes = args.modes.split(",")
    agent = ArenaAgent(args.arch, args.weights, modes[0], device="cpu")
    env = None
    res = {}
    t0 = time.time()
    for m in modes:
        if env is None:
            env = ArenaSimEnv(m, seed=123, difficulty=args.difficulty)
        else:
            env.task, env.mode = TASKS[m], m
        agent.set_mode(m)
        rets, wins, lens = [], [], []
        for _ in range(args.episodes):
            if time.time() - t0 > args.max_minutes * 60:
                break
            frame = env.reset()
            agent.reset()
            done, ret, n, info = False, 0.0, 0, {}
            clip = ClipWriter(Path(args.clips) / f"{m}.mp4") if args.clips and not rets else None
            while not done:
                a, _ = agent.act(frame)
                frame, r, done, info = env.step(a)
                ret += r
                n += 1
                if clip is not None and n % 2 == 0 and getattr(env, "last_pov", None) is not None:
                    clip.add(env.last_pov)
            if clip is not None:
                clip.close()
            rets.append(ret)
            wins.append(bool(info.get("won")))
            lens.append(n)
        if rets:
            res[m] = {"episodes": len(rets), "return": sum(rets) / len(rets), "win_rate": sum(wins) / len(wins),
                      "len": sum(lens) / len(lens)}
        print(m, res.get(m), flush=True)
    (out / f"{args.name}__{modes[0]}.json").write_text(json.dumps({"name": args.name, "modes": res}))
    if env:
        env.close()


if __name__ == "__main__":
    main()
