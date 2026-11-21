"""Evaluate one policy on a set of modes: N episodes each, sampling actions, no training.

    xvfb-run -a python cloud/eval_job.py --weights global.weights --name round-3 --modes duels_sword,bedwars_solo --episodes 3 --out eval/
Writes eval/<name>__<first mode>.json = {"name", "modes": {mode: {"episodes", "return", "win_rate", "len"}}}.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import torch as th  # noqa: E402

from vpt_arena.agent import ArenaAgent  # noqa: E402
from vpt_arena.rl.arena_tasks import TASKS  # noqa: E402
from vpt_arena.rl.sim_env import ArenaSimEnv  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--modes", required=True)
    ap.add_argument("--episodes", type=int, default=3)
    ap.add_argument("--arch", default="1x")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-minutes", type=float, default=80)
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
            env = ArenaSimEnv(m, seed=123)
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
            while not done:
                a, _ = agent.act(frame)
                frame, r, done, info = env.step(a)
                ret += r
                n += 1
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
