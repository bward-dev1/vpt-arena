"""Label unlabelled gameplay video with VPT's inverse dynamics model (IDM).

This is the core VPT trick: the IDM looks at frames before *and after* each
step, so it can tell which keys and mouse moves produced the footage. Its
labels turn any PvP / minigame video into behaviour-cloning data.

Input: any video. It is resampled to 20 fps and scaled to 640x360 (the
recorder's format), optionally after cropping to the game area
(--crop x,y,w,h in source pixels) to cut facecams and overlays.
Output: `<out>/<stem>.mp4` (20 fps, 640x360), `<stem>.jsonl` (recorder
format with IDM labels), `<stem>.meta.json` (mode, source=idm, loss_weight).

Needs the 4x IDM (1.9 GB weights) and a GPU for any real volume; it runs on
CPU/MPS but slowly.

    python -m vpt_arena.idm_label --weights weights/4x_idm.weights \
        --mode bedwars_solo --ruleset legacy --out data/idm/bedwars  videos/*.mp4
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import torch as th

from . import games
from .vpt import AGENT_RESOLUTION, build_idm, default_device, env_action_to_json, idm_tokens_to_env, load_weights
from .train_bc import to_device_state

REC_SIZE = (640, 360)
FPS = 20
WINDOW = 128  # the IDM's context; it was trained on 128-frame windows


def read_resampled(path, crop=None):
    """Yield (640x360 BGR frame) at 20 fps from any video, by nearest-timestamp resampling."""
    cap = cv2.VideoCapture(str(path))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or FPS
    t_next, i = 0.0, 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t = i / src_fps
            i += 1
            while t + 0.5 / src_fps >= t_next:
                f = frame
                if crop:
                    x, y, w, h = crop
                    f = f[y:y + h, x:x + w]
                yield cv2.resize(f, REC_SIZE, interpolation=cv2.INTER_AREA)
                t_next += 1.0 / FPS
    finally:
        cap.release()


@th.no_grad()
def label_video(idm, path, out_dir, mode, ruleset=None, team_size=None, crop=None, device="cpu",
                min_conf=None, loss_weight=0.5):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / Path(path).stem
    writer = cv2.VideoWriter(str(stem) + ".mp4", cv2.VideoWriter_fourcc(*"mp4v"), FPS, REC_SIZE)
    jl = open(str(stem) + ".jsonl", "w")
    state = to_device_state(idm.initial_state(1), device)
    hotbar, n, kept = 0, 0, 0
    buf = []

    def flush(frames):
        nonlocal state, hotbar, n, kept
        small = np.stack([cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2RGB), AGENT_RESOLUTION,
                                     interpolation=cv2.INTER_LINEAR) for f in frames])[None]
        obs = {"img": th.from_numpy(small).to(device)}
        first = th.zeros((1, len(frames)), dtype=th.bool, device=device)
        ac, state, res = idm.predict(obs, first=first, state_in=state, deterministic=True)
        conf = res["log_prob"].exp().reshape(-1).cpu().numpy()
        acts = idm_tokens_to_env({k: v[0] for k, v in ac.items()})
        for f, a, c in zip(frames, acts, conf):
            for k in range(1, 10):
                if a.get(f"hotbar.{k}"):
                    hotbar = k - 1
            low = min_conf is not None and c < min_conf
            if low:  # write a null step: the loader skips it, the frame stays in sync
                a = {"camera": np.zeros(2)}
            else:
                kept += 1
            jl.write(json.dumps(env_action_to_json(a, hotbar, extra={"idm_conf": round(float(c), 4)})) + "\n")
            writer.write(f)
            n += 1

    try:
        for frame in read_resampled(path, crop):
            buf.append(frame)
            if len(buf) == WINDOW:
                flush(buf)
                buf = []
        if buf:
            flush(buf)
    finally:
        writer.release()
        jl.close()
    meta = dict(mode=games.get(mode).key, ruleset=ruleset, team_size=team_size, source="idm",
                origin=str(path), frames=n, labelled=kept, weight=1.0, loss_weight=loss_weight)
    Path(str(stem) + ".meta.json").write_text(json.dumps({k: v for k, v in meta.items() if v is not None}, indent=1))
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--weights", required=True)
    ap.add_argument("--mode", required=True, help=f"one of: {', '.join(games.BY_KEY)}")
    ap.add_argument("--ruleset", choices=games.RULESETS)
    ap.add_argument("--team-size", type=int, choices=games.TEAM_SIZES)
    ap.add_argument("--crop", help="x,y,w,h of the game area in source pixels")
    ap.add_argument("--min-conf", type=float, default=None, help="drop steps the IDM is less sure of")
    ap.add_argument("--loss-weight", type=float, default=0.5)
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default=None)
    ap.add_argument("--net-overrides", default=None, help="JSON, tests only")
    args = ap.parse_args(argv)
    device = args.device or default_device()
    idm = build_idm(net_overrides=json.loads(args.net_overrides) if args.net_overrides else None)
    if args.weights != "random":
        load_weights(idm, args.weights)
    idm.to(device).eval()
    crop = tuple(int(v) for v in args.crop.split(",")) if args.crop else None
    for v in args.videos:
        m = label_video(idm, v, args.out, args.mode, args.ruleset, args.team_size, crop, device,
                        args.min_conf, args.loss_weight)
        print(json.dumps(m))


if __name__ == "__main__":
    main()
