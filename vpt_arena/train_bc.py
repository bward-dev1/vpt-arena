"""Sequence behaviour cloning for the conditioned VPT policy.

Unlike OpenAI's demo script (one frame at a time, no gradient through time),
this trains on T-step chunks with the transformer memory carried between
chunks of the same recording, which is how VPT itself was trained.

Mix sources with --data DIR[:WEIGHT]; e.g. PvP recordings at weight 4 and
OpenAI contractor data at weight 1 keeps general Minecraft skill from being
forgotten while the arena modes are learned. --kl-coef additionally holds the
policy near the frozen starting model (a second copy in memory).

Example (Colab L4/A100):
    python -m vpt_arena.train_bc --arch 2x --weights weights/foundation-model-2x.weights \
        --data data/human:4 --data data/idm:2 --data data/contractor:1 \
        --run runs/arena-2x --batch 4 --T 64 --accum 4 --steps 20000
"""
import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import torch as th
from torch.utils.checkpoint import checkpoint

from . import data as D
from .vpt import ActionCodec, build_policy, default_device, load_weights

import lib.tree_util as tree_util  # noqa: E402  (on sys.path via vpt)


def to_device_state(state, device):
    return tree_util.tree_map(lambda x: x.to(device) if isinstance(x, th.Tensor) else x, state)


def detach_state(state):
    return tree_util.tree_map(lambda x: x.detach() if isinstance(x, th.Tensor) else x, state)


def batch_to_torch(batch, device):
    return dict(
        img=th.from_numpy(batch["img"]).to(device),
        buttons=th.from_numpy(batch["buttons"]).to(device),
        camera=th.from_numpy(batch["camera"]).to(device),
        first=th.from_numpy(batch["first"]).to(device),
        cond=th.from_numpy(batch["cond"]).to(device),
        weight=th.from_numpy(batch["weight"]).to(device),
    )


def checkpoint_cnn(policy):
    """Recompute the image CNN in backward instead of storing its activations (big memory saving)."""
    proc = policy.net.img_process
    inner = proc.forward

    def fwd(x):
        if th.is_grad_enabled():
            return checkpoint(inner, x, use_reentrant=False)
        return inner(x)

    proc.forward = fwd


def seq_forward(policy, tb, state, conditioned=True):
    from .seqfwd import segmented_forward
    obs = {"img": tb["img"]}
    if conditioned:
        obs["diff_goal"] = tb["cond"]
    (pd, _), state_out = segmented_forward(policy, obs, tb["first"], state)
    return pd, state_out


def bc_terms(policy, pd, tb, cam_off_table):
    """Per-step log-likelihood of the recorded action; camera only counts when the camera meta-action is on."""
    lp_b = policy.pi_head["buttons"].logprob(tb["buttons"], pd["buttons"])          # (B, T)
    lp_c = policy.pi_head["camera"].logprob(tb["camera"], pd["camera"])             # (B, T)
    cam_on = ~cam_off_table[tb["buttons"][..., 0]]
    lp = lp_b + lp_c * cam_on.float()
    with th.no_grad():
        acc_b = (pd["buttons"][..., 0, :].argmax(-1) == tb["buttons"][..., 0]).float()
    return lp, acc_b


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", default="2x", choices=["1x", "2x", "3x"])
    ap.add_argument("--weights", help="VPT .weights or our checkpoint to start from")
    ap.add_argument("--data", action="append", required=True, help="DIR or DIR:WEIGHT (weight multiplies meta weight)")
    ap.add_argument("--run", required=True)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--T", type=int, default=64)
    ap.add_argument("--accum", type=int, default=4, help="chunks per optimizer step")
    ap.add_argument("--steps", type=int, default=20000, help="optimizer steps")
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--wd", type=float, default=0.039)
    ap.add_argument("--warmup", type=int, default=500)
    ap.add_argument("--clip", type=float, default=5.0)
    ap.add_argument("--kl-coef", type=float, default=0.0)
    ap.add_argument("--ckpt-cnn", action="store_true", help="activation checkpointing for the CNN")
    ap.add_argument("--save-every", type=int, default=500)
    ap.add_argument("--eval-every", type=int, default=500)
    ap.add_argument("--eval-chunks", type=int, default=16)
    ap.add_argument("--device", default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--net-overrides", default=None, help="JSON, tests only (tiny networks)")
    args = ap.parse_args(argv)

    th.manual_seed(args.seed)
    device = args.device or default_device()
    run = Path(args.run)
    run.mkdir(parents=True, exist_ok=True)
    overrides = json.loads(args.net_overrides) if args.net_overrides else None
    if not (run / "run.json").exists():
        (run / "run.json").write_text(json.dumps({"kind": "bc", "arch": args.arch, "started": time.time(),
                                                  "args": vars(args)}, indent=1))

    # ---- data: per-directory weight multiplies each trajectory's meta weight via a sidecar map
    trajs, dir_w = [], {}
    for spec in args.data:
        d, _, w = spec.partition(":")
        found = D.find_trajectories(d)
        trajs += found
        for s in found:
            dir_w[str(s)] = float(w or 1.0)
    train_t, held_t = D.split_holdout(trajs, seed=args.seed)
    print(f"{len(train_t)} train / {len(held_t)} held-out trajectories")
    # ---- model
    policy = build_policy(args.arch, conditioned=True, net_overrides=overrides)
    start_step = 0
    latest = run / "latest.pt"
    opt_state = None
    if latest.exists():
        ck = th.load(latest, map_location="cpu", weights_only=True)
        policy.load_state_dict(ck["policy"])
        opt_state, start_step = ck["optim"], int(ck["step"])
        print(f"resumed {latest} at step {start_step}")
    elif args.weights:
        load_weights(policy, args.weights)
        print(f"loaded {args.weights}")
    policy.to(device).train()
    if args.ckpt_cnn:
        checkpoint_cnn(policy)

    prior = None
    if args.kl_coef > 0:
        prior = build_policy(args.arch, conditioned=False, net_overrides=overrides)
        if args.weights:
            load_weights(prior, args.weights)
        prior.to(device).eval().requires_grad_(False)

    opt = th.optim.AdamW(policy.parameters(), lr=args.lr, weight_decay=args.wd)
    if opt_state:
        opt.load_state_dict(opt_state)

    def lr_at(step):
        if step < args.warmup:
            return args.lr * (step + 1) / args.warmup
        p = (step - args.warmup) / max(1, args.steps - args.warmup)
        return args.lr * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * min(1.0, p))))

    codec = ActionCodec()
    cam_off = th.from_numpy(codec.mapper.BUTTON_IDX_TO_CAMERA_META_OFF).to(device)
    use_amp = device == "cuda"
    amp = th.autocast("cuda", dtype=th.bfloat16) if use_amp else th.autocast("cpu", enabled=False)

    loader = WeightedStreamLoader(train_t, dir_w, batch_size=args.batch, T=args.T, seed=args.seed + start_step)
    state = to_device_state(policy.initial_state(args.batch), device)
    prior_state = to_device_state(prior.initial_state(args.batch), device) if prior else None
    log = open(run / "log.jsonl", "a")
    t0 = time.time()
    try:
        for step in range(start_step, args.steps):
            for g in opt.param_groups:
                g["lr"] = lr_at(step)
            tot = dict(nll=0.0, acc=0.0, kl=0.0, n=0.0)
            for _ in range(args.accum):
                tb = batch_to_torch(next(loader), device)
                with amp:
                    pd, state = seq_forward(policy, tb, state)
                    lp, acc = bc_terms(policy, pd, tb, cam_off)
                    w = tb["weight"]
                    loss = -(lp * w).sum() / w.sum().clamp_min(1e-6)
                    if prior is not None:
                        with th.no_grad():
                            pd_p, prior_state = seq_forward(prior, tb, prior_state, conditioned=False)
                        kl = policy.pi_head.kl_divergence(pd_p, pd).mean()
                        loss = loss + args.kl_coef * kl
                        tot["kl"] += float(kl)
                (loss / args.accum).backward()
                state = detach_state(state)
                tot["nll"] += float(-(lp * w).sum() / w.sum().clamp_min(1e-6))
                tot["acc"] += float(acc.mean())
                tot["n"] += 1
            gn = th.nn.utils.clip_grad_norm_(policy.parameters(), args.clip)
            opt.step()
            opt.zero_grad(set_to_none=True)

            rec = dict(step=step + 1, nll=tot["nll"] / tot["n"], btn_acc=tot["acc"] / tot["n"], kl=tot["kl"] / tot["n"],
                       grad_norm=float(gn), lr=lr_at(step), sec=round(time.time() - t0, 1))
            if (step + 1) % args.eval_every == 0 and held_t:
                rec.update(evaluate(policy, held_t, dir_w, args, device, cam_off, amp))
            if (step + 1) % 10 == 0 or "eval_nll" in rec:
                print(json.dumps(rec), flush=True)
            log.write(json.dumps(rec) + "\n")
            log.flush()
            if (step + 1) % args.save_every == 0 or step + 1 == args.steps:
                save(policy, opt, step + 1, run, args)
    finally:
        loader.close()
        log.close()
    return policy


def save(policy, opt, step, run, args):
    tmp = run / "latest.pt.tmp"
    th.save({"policy": policy.state_dict(), "optim": opt.state_dict(), "step": step, "arch": args.arch}, tmp)
    tmp.replace(run / "latest.pt")
    th.save(policy.state_dict(), run / "policy.weights")  # loadable by load_weights / play


@th.no_grad()
def evaluate(policy, held, dir_w, args, device, cam_off, amp):
    policy.eval()
    ld = WeightedStreamLoader(held, dir_w, batch_size=min(args.batch, len(held)), T=args.T, seed=12345)
    st = to_device_state(policy.initial_state(ld.B), device)
    nll, acc = [], []
    try:
        for _ in range(args.eval_chunks):
            tb = batch_to_torch(next(ld), device)
            with amp:
                pd, st = seq_forward(policy, tb, st)
                lp, a = bc_terms(policy, pd, tb, cam_off)
            nll.append(float(-lp.mean()))
            acc.append(float(a.mean()))
    finally:
        ld.close()
        policy.train()
    return dict(eval_nll=float(np.mean(nll)), eval_btn_acc=float(np.mean(acc)))


class WeightedStreamLoader(D.StreamLoader):
    """StreamLoader where each trajectory's sampling weight = meta weight x its --data directory weight."""

    def __init__(self, trajectories, dir_w, **kw):
        import multiprocessing as mp
        self.B, self.T = kw["batch_size"], kw["T"]
        weights = [float(D.read_meta(s)["weight"]) * dir_w.get(str(s), 1.0) for s in trajectories]
        ctx = mp.get_context("spawn")
        self.stop = ctx.Event()
        self.queues = [ctx.Queue(maxsize=4) for _ in range(self.B)]
        self.procs = [ctx.Process(target=D._stream_worker,
                                  args=(b, trajectories, weights, self.T, kw.get("seed", 0), self.queues[b], self.stop),
                                  daemon=True) for b in range(self.B)]
        for p in self.procs:
            p.start()


if __name__ == "__main__":
    main()
