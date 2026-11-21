"""Trajectories and the streaming sequence loader.

One trajectory = `<stem>.mp4` + `<stem>.jsonl` in VPT's contractor recorder
format (one JSON object per 20 Hz frame), plus an optional `<stem>.meta.json`:

    {"mode": "bedwars_solo", "ruleset": "legacy", "team_size": 1,
     "source": "human" | "contractor" | "idm",
     "weight": 1.0,        # how often the loader picks this recording
     "loss_weight": 1.0}   # per-step loss multiplier (e.g. 0.5 for noisy IDM labels)

Without a meta file a trajectory counts as survival play (mode 0), which is
right for OpenAI's contractor data. Our own recorder and the IDM labeller
write the same format, so every source goes through one loader.

The loader keeps B parallel streams. Row b of every batch always comes from
stream b, so the trainer can carry the transformer memory from one chunk to
the next (truncated BPTT across the whole recording, as VPT trained). When a
stream moves on to its next trajectory, that step is marked `first` and the
network's attention mask cuts the memory there.
"""
import json
import multiprocessing as mp
import random
from pathlib import Path

import cv2
import numpy as np

from . import games
from .vpt import AGENT_RESOLUTION, ActionCodec, json_to_env_action

CURSOR_PNG = Path(__file__).resolve().parent.parent / "third_party" / "vpt" / "cursors" / "mouse_cursor_white_16x16.png"
RECORDER_HEIGHT_PX = 720  # contractor mouse x/y are in 720p screen pixels


def find_trajectories(*dirs):
    out = []
    for d in dirs:
        for mp4 in sorted(Path(d).rglob("*.mp4")):
            js = mp4.with_suffix(".jsonl")
            if js.exists():
                out.append(mp4.with_suffix(""))
    return out


def read_meta(stem):
    p = Path(str(stem) + ".meta.json")
    meta = json.loads(p.read_text()) if p.exists() else {}
    meta.setdefault("mode", "survival")
    meta.setdefault("source", "contractor")
    meta.setdefault("weight", 1.0)
    return meta


def resize_frame(frame_rgb):
    # VPT: "For your sanity, do not resize with any function than INTER_LINEAR"
    return cv2.resize(frame_rgb, AGENT_RESOLUTION, interpolation=cv2.INTER_LINEAR)


def _composite_cursor(frame, cursor, alpha, x, y):
    ch = max(0, min(frame.shape[0] - y, cursor.shape[0]))
    cw = max(0, min(frame.shape[1] - x, cursor.shape[1]))
    if ch == 0 or cw == 0 or x < 0 or y < 0:
        return
    a = alpha[:ch, :cw]
    frame[y:y + ch, x:x + cw] = (frame[y:y + ch, x:x + cw] * (1 - a) + cursor[:ch, :cw] * a).astype(np.uint8)


def iter_trajectory(stem, codec, cursor=None):
    """Yield (frame 128x128x3 uint8 RGB, button token, camera token) for each non-null step.

    Applies VPT's loader fixes: attack stuck down at the start of a recording,
    hotbar changes made with the scroll wheel, and the mouse cursor drawn
    into GUI frames (the recorder captured video without it).
    """
    lines = Path(str(stem) + ".jsonl").read_text().splitlines()
    steps = [json.loads(l) for l in lines if l.strip()]
    cap = cv2.VideoCapture(str(stem) + ".mp4")
    attack_stuck = False
    last_hotbar = 0
    try:
        for i, step in enumerate(steps):
            mouse = step["mouse"]
            if i == 0 and mouse.get("newButtons") == [0]:
                attack_stuck = True
            elif attack_stuck and 0 in mouse.get("newButtons", []):
                attack_stuck = False
            if attack_stuck:
                mouse["buttons"] = [b for b in mouse["buttons"] if b != 0]

            action, null = json_to_env_action(step)
            hb = step.get("hotbar", last_hotbar)
            if hb != last_hotbar:
                action[f"hotbar.{hb + 1}"] = 1
                null = False
            last_hotbar = hb

            ok, frame = cap.read()  # read even for null steps to stay in sync
            if not ok:
                break
            if null:
                continue
            if step.get("isGuiOpen") and cursor is not None:
                s = frame.shape[0] / RECORDER_HEIGHT_PX
                _composite_cursor(frame, cursor[0], cursor[1], int(mouse.get("x", 0) * s), int(mouse.get("y", 0) * s))
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            tok, tok_null = codec.env_to_tokens([action])
            if tok_null[0]:
                continue
            yield resize_frame(frame), int(tok["buttons"][0, 0]), int(tok["camera"][0, 0])
    finally:
        cap.release()


def _load_cursor():
    img = cv2.imread(str(CURSOR_PNG), cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    img = img[:16, :16]
    return img[:, :, :3], img[:, :, 3:] / 255.0


def _stream_worker(stream_id, trajs, weights, T, seed, queue, stop):
    """Produce chunks of T steps forever (or until stop), cycling through a weighted shuffle of trajectories."""
    rng = random.Random(seed + 7919 * stream_id)
    codec = ActionCodec()
    cursor = _load_cursor()
    buf = None

    def new_buf():
        return dict(img=np.zeros((T, *AGENT_RESOLUTION, 3), np.uint8), buttons=np.zeros((T, 1), np.int64),
                    camera=np.zeros((T, 1), np.int64), first=np.zeros((T,), bool), cond=np.zeros((T, 3), np.int64),
                    weight=np.zeros((T,), np.float32))

    buf, n = new_buf(), 0
    while not stop.is_set():
        stem = rng.choices(trajs, weights=weights, k=1)[0]
        meta = read_meta(stem)
        cond = games.cond_ids(meta["mode"], meta.get("ruleset"), meta.get("team_size"))
        first = True
        for frame, b, c in iter_trajectory(stem, codec, cursor):
            buf["img"][n] = frame
            buf["buttons"][n, 0] = b
            buf["camera"][n, 0] = c
            buf["first"][n] = first
            buf["cond"][n] = cond
            buf["weight"][n] = float(meta.get("loss_weight", 1.0))
            first = False
            n += 1
            if n == T:
                buf["src"] = str(stem)
                while not stop.is_set():
                    try:
                        queue.put(buf, timeout=1.0)
                        break
                    except Exception:
                        continue
                buf, n = new_buf(), 0
            if stop.is_set():
                return


class StreamLoader:
    """B parallel streams -> batches of dict(img (B,T,128,128,3) uint8, buttons, camera, first, cond, weight)."""

    def __init__(self, trajectories, batch_size=8, T=128, seed=0, queue_depth=4):
        if not trajectories:
            raise ValueError("no trajectories found")
        self.B, self.T = batch_size, T
        weights = [float(read_meta(s)["weight"]) for s in trajectories]
        ctx = mp.get_context("spawn")
        self.stop = ctx.Event()
        self.queues = [ctx.Queue(maxsize=queue_depth) for _ in range(batch_size)]
        self.procs = [ctx.Process(target=_stream_worker, args=(b, trajectories, weights, T, seed, self.queues[b], self.stop),
                                  daemon=True) for b in range(batch_size)]
        for p in self.procs:
            p.start()

    def __iter__(self):
        return self

    def _get(self, b, timeout=600.0):
        """Next chunk from stream b; raises if its worker died instead of waiting forever."""
        import queue as _q
        waited = 0.0
        while True:
            try:
                return self.queues[b].get(timeout=5.0)
            except _q.Empty:
                waited += 5.0
                if not self.procs[b].is_alive():
                    raise RuntimeError(f"data stream {b} died (exit code {self.procs[b].exitcode})")
                if waited >= timeout:
                    raise TimeoutError(f"data stream {b} produced nothing for {timeout:.0f} s")

    def __next__(self):
        rows = [self._get(b) for b in range(len(self.queues))]
        batch = {k: np.stack([r[k] for r in rows]) for k in ("img", "buttons", "camera", "first", "cond", "weight")}
        batch["src"] = [r["src"] for r in rows]
        return batch

    def close(self):
        self.stop.set()
        for q in self.queues:
            try:
                while not q.empty():
                    q.get_nowait()
            except Exception:
                pass
        for p in self.procs:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()


def split_holdout(trajs, frac=0.05, seed=0):
    """Deterministic train/held-out split by file name, so resumes see the same split."""
    rng = random.Random(seed)
    trajs = sorted(trajs)
    held = set(rng.sample(trajs, max(1, int(len(trajs) * frac)))) if len(trajs) > 1 else set()
    return [t for t in trajs if t not in held], sorted(held)

