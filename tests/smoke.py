"""End-to-end smoke test on synthetic data with tiny random networks (CPU, ~1 min).

Checks the plumbing, not playing strength: action conversion, the zero-init
conditioner, the stream loader, sequence BC with resume, IDM labelling, and
that the real 1x/2x architectures build from configs/vpt_models.json.

    .venv/bin/python -m tests.smoke
"""
import json
import random
import shutil
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import torch as th

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vpt_arena import data as D, games, idm_label, train_bc  # noqa: E402
from vpt_arena.vpt import (ActionCodec, build_idm, build_policy, env_action_to_json, json_to_env_action,  # noqa: E402
                           noop_env_action)

TINY = dict(hidsize=64, impala_width=1, attention_heads=4, n_recurrence_layers=1, attention_memory_size=32, timesteps=16)
TINY_IDM = dict(hidsize=64, impala_width=1, attention_heads=4, n_recurrence_layers=1, attention_memory_size=16,
                timesteps=16, img_shape=[128, 128, 8], conv3d_params={"inchan": 3, "kernel_size": [5, 1, 1],
                                                                      "outchan": 8, "padding": [2, 0, 0]})
OK = []


def check(name, cond, detail=""):
    if not cond:
        raise AssertionError(f"FAIL {name} {detail}")
    OK.append(name)
    print(f"ok  {name} {detail}")


def random_action(rng):
    a = noop_env_action()
    # one choice per exclusive group, as a human can't usefully press W and S together
    for group in (("forward", "back"), ("left", "right"), ("sneak", "sprint")):
        c = rng.choice((None,) + group)
        if c:
            a[c] = 1
    for b in ("attack", "use", "jump"):
        a[b] = int(rng.random() < 0.3)
    if rng.random() < 0.6:
        a["camera"] = np.array([rng.uniform(-8, 8), rng.uniform(-8, 8)])
    return a


def make_traj(d, name, n, rng, mode=None):
    w = cv2.VideoWriter(str(d / f"{name}.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 20, (640, 360))
    with open(d / f"{name}.jsonl", "w") as f:
        for i in range(n):
            frame = np.full((360, 640, 3), (i * 7) % 255, np.uint8)
            cv2.putText(frame, str(i), (40, 200), cv2.FONT_HERSHEY_SIMPLEX, 4, (255, 255, 255), 6)
            w.write(frame)
            f.write(json.dumps(env_action_to_json(random_action(rng), hotbar=0)) + "\n")
    w.release()
    if mode:
        (d / f"{name}.meta.json").write_text(json.dumps({"mode": mode, "source": "human"}))


def main():
    rng = random.Random(0)
    th.manual_seed(0)
    codec = ActionCodec()

    # 1. action conversion
    acts = [random_action(rng) for _ in range(200)]
    tok, null = codec.env_to_tokens(acts)
    back = codec.tokens_to_env(tok)
    btn_ok = all(all(a[k] == b[k] for k in ("forward", "back", "left", "right", "attack", "use", "jump", "sneak", "sprint"))
                 for a, b in zip(acts, back))
    cam_err = max(float(np.abs(a["camera"] - b["camera"]).max()) for a, b in zip(acts, back))
    check("codec buttons round-trip", btn_ok)
    check("codec camera within one mu-law bin", cam_err < 3.5, f"max err {cam_err:.2f} deg")
    j = [json_to_env_action(env_action_to_json(a, 0))[0] for a in acts]
    check("json round-trip", all(np.allclose(a["camera"], b["camera"]) and a["attack"] == b["attack"] for a, b in zip(acts, j)))

    # 2. conditioner starts as a no-op
    pol = build_policy("1x", net_overrides=TINY).eval()
    img = th.randint(0, 255, (1, 4, 128, 128, 3), dtype=th.uint8)
    first = th.zeros((1, 4), dtype=th.bool)
    outs = []
    for mode in ("survival", "bedwars_solo"):
        cond = th.tensor(games.cond_ids(mode)).expand(1, 4, 3)
        (pd, _, _), _ = pol(obs={"img": img, "diff_goal": cond}, first=first, state_in=pol.initial_state(1))
        outs.append(pd["buttons"])
    check("conditioner zero-init leaves logits unchanged", th.allclose(outs[0], outs[1]))
    th.nn.init.normal_(pol.net.diff_obs_process.out.weight, std=0.1)
    (pd2, _, _), _ = pol(obs={"img": img, "diff_goal": th.tensor(games.cond_ids("bedwars_solo")).expand(1, 4, 3)},
                         first=first, state_in=pol.initial_state(1))
    check("trained conditioner changes logits", not th.allclose(outs[0], pd2["buttons"]))

    # 2b. sequence BC can fit a fixed chunk (the loss actually trains the policy)
    pol = build_policy("1x", net_overrides=TINY).train()
    codec_tbl = th.from_numpy(codec.mapper.BUTTON_IDX_TO_CAMERA_META_OFF)
    tok, _ = codec.env_to_tokens([random_action(rng) for _ in range(16)])
    tb = dict(img=th.randint(0, 255, (1, 16, 128, 128, 3), dtype=th.uint8), first=th.zeros((1, 16), dtype=th.bool),
              cond=th.tensor(games.cond_ids("duels_sword")).expand(1, 16, 3),
              buttons=th.from_numpy(tok["buttons"])[None], camera=th.from_numpy(tok["camera"])[None])
    opt = th.optim.Adam(pol.parameters(), lr=1e-3)
    nlls = []
    for _ in range(40):
        pd, _ = train_bc.seq_forward(pol, tb, pol.initial_state(1))
        lp, _ = train_bc.bc_terms(pol, pd, tb, codec_tbl)
        loss = -lp.mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
        nlls.append(float(loss))
    check("BC overfits a fixed chunk", nlls[-1] < 0.5 * nlls[0], f"nll {nlls[0]:.2f} -> {nlls[-1]:.2f}")

    tmp = Path(tempfile.mkdtemp(prefix="vpt-arena-smoke-"))
    try:
        # 3. stream loader
        dd = tmp / "data"
        dd.mkdir()
        for i in range(3):
            make_traj(dd, f"t{i}", 60, rng, mode="duels_sword" if i else None)
        trajs = D.find_trajectories(dd)
        check("found trajectories", len(trajs) == 3)
        ld = D.StreamLoader(trajs, batch_size=2, T=16)
        b = next(ld)
        b2 = next(ld)
        ld.close()
        check("batch shapes", b["img"].shape == (2, 16, 128, 128, 3) and b["buttons"].shape == (2, 16, 1),
              str(b["img"].shape))
        check("first flag at stream start", bool(b["first"][:, 0].all()) and b2["img"].shape == b["img"].shape)
        check("cond ids present", b["cond"].shape == (2, 16, 3))

        # 4. sequence BC, then resume
        run = tmp / "run"
        args = ["--arch", "1x", "--data", f"{dd}:1", "--run", str(run), "--batch", "2", "--T", "16", "--accum", "2",
                "--steps", "3", "--warmup", "1", "--save-every", "3", "--eval-every", "3", "--eval-chunks", "1",
                "--device", "cpu", "--lr", "1e-3", "--net-overrides", json.dumps(TINY)]
        train_bc.main(args)
        logs = [json.loads(l) for l in (run / "log.jsonl").read_text().splitlines()]
        check("BC ran 3 steps, finite loss", len(logs) == 3 and all(np.isfinite(r["nll"]) for r in logs),
              f"nll {logs[0]['nll']:.2f} -> {logs[-1]['nll']:.2f}")
        check("checkpoint saved", (run / "latest.pt").exists() and (run / "policy.weights").exists())
        from vpt_arena.vpt import load_weights
        load_weights(build_policy("1x", conditioned=False, net_overrides=TINY), run / "policy.weights")
        check("unconditioned prior loads a conditioned checkpoint", True)
        args[args.index("--steps") + 1] = "5"
        train_bc.main(args)
        logs = [json.loads(l) for l in (run / "log.jsonl").read_text().splitlines()]
        check("resume continued from step 3", [r["step"] for r in logs] == [1, 2, 3, 4, 5])

        # 5. IDM labelling of a raw video at a different fps and size
        raw = tmp / "raw.mp4"
        w = cv2.VideoWriter(str(raw), cv2.VideoWriter_fourcc(*"mp4v"), 30, (1280, 720))
        for i in range(90):
            w.write(np.full((720, 1280, 3), i * 2, np.uint8))
        w.release()
        th.manual_seed(0)
        idm_label.main([str(raw), "--weights", "random", "--mode", "bedwars_solo", "--out", str(tmp / "idm"),
                        "--device", "cpu", "--net-overrides", json.dumps(TINY_IDM)])
        lines = (tmp / "idm" / "raw.jsonl").read_text().splitlines()
        check("IDM resampled 3 s of 30 fps to 20 fps", abs(len(lines) - 60) <= 1, f"{len(lines)} steps")
        meta = json.loads((tmp / "idm" / "raw.meta.json").read_text())
        check("IDM meta", meta["source"] == "idm" and meta["mode"] == "bedwars_solo")
        n = sum(1 for _ in D.iter_trajectory(tmp / "idm" / "raw", codec))
        check("IDM output readable by the loader", n >= 0, f"{n} non-null steps")
        build_idm(net_overrides=TINY_IDM)

        # 6. the real architectures build (no weights needed)
        for arch, expect in (("1x", 1024), ("2x", 2048)):
            p = build_policy(arch)
            nparam = sum(x.numel() for x in p.parameters())
            check(f"{arch} architecture builds", p.net.hidsize == expect, f"{nparam / 1e6:.0f}M params")
            del p
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(OK)} checks passed")


if __name__ == "__main__":
    main()
