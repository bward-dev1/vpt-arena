"""Fine-tune VPT's inverse dynamics model on exactly-labelled recordings (your own games).

VPT's IDM learned from 1.16 footage. Recordings from your server (any newer
version, other resource packs, PvP-speed mouse movement) come with exact
key/mouse labels from the recorder, so they can teach the IDM the new look.
A better IDM gives better labels on PvP videos (idm_label.py), and those feed BC.

The IDM sees whole 128-frame windows (frames before and after each step), so
--T should stay 128. Needs a big GPU for the 4x IDM (hidsize 4096).

    python -m vpt_arena.train_idm --weights weights/4x_idm.weights --data data/human --run runs/idm-ft --steps 2000
"""
import argparse
import json
import time
from pathlib import Path

import torch as th

from . import data as D
from .train_bc import WeightedStreamLoader, detach_state, to_device_state
from .vpt import ActionCodec, build_idm, default_device, load_weights


def factored_targets(codec, buttons_joint, camera_joint):
    """Joint (B,T,1) tokens -> factored (B,T,20) button bits and (B,T,2) camera bins, as the IDM predicts them."""
    b = buttons_joint.reshape(-1, 1)
    c = camera_joint.reshape(-1, 1)
    fac = codec.mapper.to_factored({"buttons": b, "camera": c})
    B, T = buttons_joint.shape[:2]
    return fac["buttons"].reshape(B, T, -1), fac["camera"].reshape(B, T, 2)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True, help="4x_idm.weights, or 'random' for tests")
    ap.add_argument("--data", action="append", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--T", type=int, default=128)
    ap.add_argument("--steps", type=int, default=2000)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--save-every", type=int, default=250)
    ap.add_argument("--device", default=None)
    ap.add_argument("--net-overrides", default=None)
    args = ap.parse_args(argv)
    device = args.device or default_device()
    run = Path(args.run)
    run.mkdir(parents=True, exist_ok=True)
    (run / "run.json").write_text(json.dumps({"kind": "idm", "arch": "idm4x", "started": time.time(), "args": vars(args)}))
    idm = build_idm(net_overrides=json.loads(args.net_overrides) if args.net_overrides else None)
    if args.weights != "random":
        load_weights(idm, args.weights)
    idm.to(device).train()
    opt = th.optim.AdamW(idm.parameters(), lr=args.lr, weight_decay=0.0)
    trajs = []
    for d in args.data:
        trajs += D.find_trajectories(d)
    codec = ActionCodec()
    loader = WeightedStreamLoader(trajs, {}, batch_size=args.batch, T=args.T, seed=0)
    state = to_device_state(idm.initial_state(args.batch), device)
    amp = th.autocast("cuda", dtype=th.bfloat16) if device == "cuda" else th.autocast("cpu", enabled=False)
    log = open(run / "log.jsonl", "a")
    t0 = time.time()
    try:
        for step in range(args.steps):
            b = next(loader)
            tb, tc = factored_targets(codec, b["buttons"], b["camera"])
            obs = {"img": th.from_numpy(b["img"]).to(device)}
            first = th.from_numpy(b["first"]).to(device)
            with amp:
                (pd, _, _), state = idm(obs=obs, first=first, state_in=state)
                lp = idm.pi_head.logprob({"buttons": th.from_numpy(tb).to(device), "camera": th.from_numpy(tc).to(device)}, pd)
                loss = -lp.mean()
            opt.zero_grad(set_to_none=True)
            loss.backward()
            th.nn.utils.clip_grad_norm_(idm.parameters(), 1.0)
            opt.step()
            state = detach_state(state)
            with th.no_grad():
                pred_b = pd["buttons"].argmax(-1).cpu().numpy()
                acc = float((pred_b == tb).mean())
            rec = dict(step=step + 1, nll=float(loss), btn_bit_acc=acc, sec=round(time.time() - t0, 1))
            log.write(json.dumps(rec) + "\n")
            log.flush()
            if (step + 1) % 10 == 0:
                print(json.dumps(rec), flush=True)
            if (step + 1) % args.save_every == 0 or step + 1 == args.steps:
                th.save(idm.state_dict(), run / "idm.weights")
    finally:
        loader.close()
        log.close()


if __name__ == "__main__":
    main()
