"""Run one Simulation Lab request: build the custom arena, let the chosen model play, record clips and stats.

    xvfb-run -a python cloud/sim_custom.py --spec spec.json --weights w.weights --model-tag round-1 --out out/
Writes out/result.json and out/ep<N>.mp4 (H.264, 320x180, 10 fps).
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import torch as th  # noqa: E402

from cloud.eval_job import ClipWriter  # noqa: E402
from vpt_arena.agent import ArenaAgent  # noqa: E402
from vpt_arena.rl import custom_sim as C  # noqa: E402
from vpt_arena.rl.sim_env import ArenaSimEnv, _num, stat  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--model-tag", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    th.set_num_threads(3)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    raw = json.loads(Path(args.spec).read_text())
    spec = C.validate(raw, releases=[args.model_tag] if args.model_tag.startswith("round-") else ())
    task = C.to_task(spec)
    print(C.describe(spec), flush=True)
    t0 = time.time()
    env = ArenaSimEnv(spec["base_mode"], seed=spec["seed"], difficulty=spec["difficulty"], task=task)
    agent = ArenaAgent("1x", args.weights, spec["base_mode"], device="cpu")
    episodes = []
    for ep in range(spec["episodes"]):
        frame = env.reset()
        agent.reset()
        clip = ClipWriter(out / f"ep{ep}.mp4", max_frames=spec["seconds"] * 10 + 20)
        dmg0 = _num(env.prev.get("damage_dealt"))
        kills0 = stat(env.prev, "kill_entity", task.opponent_types)
        done, ret, n, info = False, 0.0, 0, {}
        while not done:
            a, _ = agent.act(frame)
            frame, r, done, info = env.step(a)
            ret += r
            n += 1
            if n % 2 == 0 and getattr(env, "last_pov", None) is not None:
                clip.add(env.last_pov)
        clip.close()
        episodes.append({"return": round(ret, 3), "won": bool(info.get("won")), "died": bool(info.get("died")),
                         "steps": n, "damage_dealt": round(_num(env.prev.get("damage_dealt")) - dmg0, 1),
                         "kills": int(stat(env.prev, "kill_entity", task.opponent_types) - kills0),
                         "clip": (out / f"ep{ep}.mp4").exists(), "sim_error": bool(info.get("sim_error"))})
        print(json.dumps(episodes[-1]), flush=True)
    result = {"episodes": episodes, "model_tag": args.model_tag, "base_mode": spec["base_mode"],
              "seconds_simulated": round(sum(e["steps"] for e in episodes) / 20, 1),
              "wall_seconds": round(time.time() - t0, 1), "spec": spec, "description": C.describe(spec)}
    (out / "result.json").write_text(json.dumps(result, indent=1))
    env.close()


if __name__ == "__main__":
    main()
