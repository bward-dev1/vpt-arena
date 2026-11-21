"""RL on your own server with the real client.

    VPT_RCON_PASSWORD=... .venv/bin/python -m vpt_arena.rl.train_rl --arch 1x \
        --weights runs/arena-1x/policy.weights --mode duels_sword --run runs/rl-sword --iters 200

One Minecraft window = one env, playing in real time at 20 Hz, so this is
slow (about 72k steps an hour). The 1x model steps in ~20 ms on the M2's CPU;
2x needs a GPU to keep up. Use --toy to check the loop on the AttackOnRed env.
"""
import argparse
import json
import time
from pathlib import Path

from ..vpt import build_policy, default_device, load_weights
from .envs import AttackOnRed
from .ppo import PPO


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", default="1x")
    ap.add_argument("--weights", required=True)
    ap.add_argument("--mode", default="duels_sword")
    ap.add_argument("--run", required=True)
    ap.add_argument("--iters", type=int, default=100)
    ap.add_argument("--T", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--kl-coef", type=float, default=0.2)
    ap.add_argument("--vf-warmup", type=int, default=10)
    ap.add_argument("--device", default=None)
    ap.add_argument("--toy", action="store_true")
    ap.add_argument("--net-overrides", default=None)
    args = ap.parse_args(argv)
    run = Path(args.run)
    run.mkdir(parents=True, exist_ok=True)
    (run / "run.json").write_text(json.dumps({"kind": "rl", "arch": args.arch, "started": time.time(),
                                              "args": vars(args)}, indent=1))
    ov = json.loads(args.net_overrides) if args.net_overrides else None
    device = args.device or default_device()
    policy = build_policy(args.arch, net_overrides=ov)
    prior = build_policy(args.arch, conditioned=False, net_overrides=ov)
    if args.weights != "random":
        load_weights(policy, args.weights)
        load_weights(prior, args.weights)
    else:  # same random start for both, so the KL starts at zero
        prior.load_state_dict({k: v for k, v in policy.state_dict().items() if "diff_obs_process" not in k})
    policy.to(device)
    prior.to(device).eval().requires_grad_(False)
    if args.toy:
        envs = [AttackOnRed(seed=i) for i in range(4)]
    else:
        from .live_env import make_live_env
        envs = [make_live_env(args.mode)]
    ppo = PPO(policy, envs, [args.mode] * len(envs), prior=prior, device=device, T=args.T, lr=args.lr,
              kl_coef=args.kl_coef, vf_warmup=args.vf_warmup, run=run)
    latest = run / "latest.pt"
    if latest.exists():
        import torch as th
        ck = th.load(latest, map_location="cpu", weights_only=True)
        policy.load_state_dict(ck["policy"])
        ppo.opt.load_state_dict(ck["optim"])
        ppo.iter, ppo.env_steps, ppo.kl_coef = int(ck["iter"]), int(ck["env_steps"]), float(ck["kl_coef"])
        print(f"resumed at iter {ppo.iter}")
    ppo.train(max(0, args.iters - ppo.iter))


if __name__ == "__main__":
    main()
