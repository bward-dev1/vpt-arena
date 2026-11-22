"""One RL worker on a cloud runner: a few MineStudio sims (one per mode), PPO on the conditioned VPT policy.

    xvfb-run -a python cloud/rl_job.py --modes duels_sword,bedwars_solo --weights w.weights \
        --prior prior.weights --minutes 150 --out out/job-03

Writes out/<job>/rl_log.jsonl (ppo), status.json (for the dashboard), policy.weights at the end.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import torch as th  # noqa: E402

from vpt_arena.rl.ppo import PPO  # noqa: E402
from vpt_arena.vpt import build_policy, load_weights  # noqa: E402


def write_frames(out, envs):
    """Latest view of each sim as a small JPEG, for the site's Live page (pushed with the status)."""
    import cv2
    for i, e in enumerate(envs):
        pov = getattr(e, "last_pov", None)
        if pov is not None:
            img = cv2.resize(pov, (320, 180), interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(out / f"frame{i}.jpg"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 70])


def write_status(out, **kw):
    kw["updated"] = time.time()
    tmp = out / "status.json.tmp"
    tmp.write_text(json.dumps(kw))
    os.replace(tmp, out / "status.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", required=True)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--prior", required=True)
    ap.add_argument("--arch", default="1x")
    ap.add_argument("--minutes", type=float, default=150)
    ap.add_argument("--out", required=True)
    ap.add_argument("--job", default=None)
    ap.add_argument("--round", type=int, default=0)
    ap.add_argument("--T", type=int, default=40)
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--no-freeze-cnn", action="store_true", help="also train VPT's image encoder (slower)")
    ap.add_argument("--kl-coef", type=float, default=0.1)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--difficulty", type=float, default=None, help="opponent strength 0..1 (default: ramps with round)")
    args = ap.parse_args()
    th.set_num_threads(args.threads)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    job = args.job or out.name
    modes = args.modes.split(",")
    t_start = time.time()
    (out / "run.json").write_text(json.dumps({"kind": "rl", "arch": args.arch, "started": t_start, "args": {
        "modes": modes, "round": args.round, "T": args.T, "lr": args.lr, "kl_coef": args.kl_coef,
        "minutes": args.minutes, "platform": "github-actions",
        "difficulty": args.difficulty if args.difficulty is not None else min(1.0, 0.3 + 0.15 * args.round)}}))
    write_status(out, job=job, state="starting", round=args.round, modes=modes, started=t_start, iter=0)

    try:
        run_job(args, out, job, modes, t_start)
    except BaseException as e:
        write_status(out, job=job, state="failed", round=args.round, modes=modes, started=t_start,
                     error=f"{type(e).__name__}: {str(e)[:300]}")
        raise


def run_job(args, out, job, modes, t_start):
    from vpt_arena.rl.sim_env import ArenaSimEnv
    envs = []
    for i, m in enumerate(modes):
        t0 = time.time()
        diff = args.difficulty if args.difficulty is not None else min(1.0, 0.3 + 0.15 * args.round)
        envs.append(ArenaSimEnv(m, seed=args.seed * 10 + i, difficulty=diff, adaptive=True))
        print(f"sim for {m} created in {time.time() - t0:.0f} s", flush=True)

    policy = build_policy(args.arch)
    if args.weights == "random":  # from-scratch comparison model: no pretraining, no prior to stay near
        prior = None
    else:
        load_weights(policy, args.weights)
        prior = build_policy(args.arch, conditioned=False)
        load_weights(prior, args.prior)
        prior.eval().requires_grad_(False)
    ppo = PPO(policy, envs, modes, prior=prior, device="cpu", T=args.T, lr=args.lr, kl_coef=args.kl_coef,
              epochs=1, minibatches=1, gamma=0.995, lam=0.95, vf_warmup=3 if args.round == 0 else 0,
              ent_coef=0.0 if prior is not None else 0.002, run=out,
              freeze_cnn=(not args.no_freeze_cnn) and args.arch != "small")
    deadline = t_start + args.minutes * 60
    write_status(out, job=job, state="running", round=args.round, modes=modes, started=t_start, iter=0)
    try:
        while time.time() < deadline:
            rec = ppo.train(1, log_every=1, save_every=10 ** 9)[-1]
            fin = ppo.finished_episodes()[-50:]
            per_mode = {}
            for m, e in zip(modes, envs):
                eps = [f for f in fin if f[0] == m]
                if eps:
                    per_mode[m] = {"episodes": len(eps), "return": sum(f[1] for f in eps) / len(eps),
                                   "win_rate": sum(f[3] for f in eps) / len(eps), "difficulty": round(e.difficulty, 2)}
            write_frames(out, envs)
            write_status(out, job=job, state="running", round=args.round, modes=modes, started=t_start,
                         iter=rec["iter"], env_steps=rec["env_steps"], fps=rec["fps"], per_mode=per_mode,
                         minutes_left=round((deadline - time.time()) / 60, 1))
    finally:
        ppo.save()
        (out / "latest.pt").unlink(missing_ok=True)  # optimizer state is 3x the policy; artifacts keep policy.weights only
        write_status(out, job=job, state="finished", round=args.round, modes=modes, started=t_start,
                     iter=ppo.iter, env_steps=ppo.env_steps)
        for e in envs:
            e.close()


if __name__ == "__main__":
    main()
