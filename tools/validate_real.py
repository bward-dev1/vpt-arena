"""Real-weights check: OpenAI's pretrained policy should predict real human actions far better than a random one.

Runs the policy over a contractor clip through our loader, codec and
sequence forward (the same path train_bc uses) and reports per-step NLL and
button-token accuracy for the pretrained weights and for a random init.

    .venv/bin/python tools/validate_real.py --weights weights/foundation-model-1x.weights --clip data/x/<stem> --arch 1x
"""
import argparse
import json
import os
import sys

import numpy as np
import torch as th

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vpt_arena import data as D, games  # noqa: E402
from vpt_arena.train_bc import bc_terms, seq_forward  # noqa: E402
from vpt_arena.vpt import ActionCodec, build_policy, load_weights  # noqa: E402


@th.no_grad()
def score(policy, steps, T=64, cond_mode="survival"):
    codec = ActionCodec()
    cam_off = th.from_numpy(codec.mapper.BUTTON_IDX_TO_CAMERA_META_OFF)
    state = policy.initial_state(1)
    nll, acc, n = 0.0, 0.0, 0
    for s in range(0, len(steps) - T + 1, T):
        chunk = steps[s:s + T]
        tb = dict(img=th.from_numpy(np.stack([c[0] for c in chunk]))[None],
                  buttons=th.tensor([[[c[1]] for c in chunk]]), camera=th.tensor([[[c[2]] for c in chunk]]),
                  first=th.tensor([[s == 0 and i == 0 for i in range(T)]]),
                  cond=th.tensor(games.cond_ids(cond_mode)).expand(1, T, 3))
        pd, state = seq_forward(policy, tb, state)
        lp, a = bc_terms(policy, pd, tb, cam_off)
        nll += float(-lp.sum())
        acc += float(a.sum())
        n += T
    return nll / n, acc / n, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--clip", required=True, help="trajectory stem (path without .mp4)")
    ap.add_argument("--arch", default="1x")
    ap.add_argument("--max-steps", type=int, default=640)
    args = ap.parse_args()
    th.set_num_threads(max(1, os.cpu_count() - 1))
    steps = []
    for st in D.iter_trajectory(args.clip, ActionCodec(), D._load_cursor()):
        steps.append(st)
        if len(steps) >= args.max_steps:
            break
    print(f"{len(steps)} non-null steps from {args.clip}")
    out = {}
    pre = build_policy(args.arch).eval()
    load_weights(pre, args.weights)
    out["pretrained"] = score(pre, steps)
    del pre
    th.manual_seed(0)
    out["random"] = score(build_policy(args.arch).eval(), steps)
    for k, (nll, acc, n) in out.items():
        print(json.dumps(dict(model=k, nll_per_step=round(nll, 3), button_token_acc=round(acc, 3), steps=n)))


if __name__ == "__main__":
    main()
