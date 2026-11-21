"""Record your own Minecraft games as training data: 20 fps 640x360 video + exact keys and mouse.

Output per segment, in VPT's recorder format (what train_bc reads):
    data/human/<mode>/<date>-<n>.mp4 / .jsonl / .meta.json

Recording runs only while the Minecraft window is in front; switching away
closes the segment. F8 pauses and resumes. Ctrl-C stops.

    .venv/bin/python -m vpt_arena.live.recorder --mode bedwars_solo --ruleset legacy

Game settings that match VPT: FOV 70, GUI scale 2 at 1280x720 (or any 16:9
window), brightness Moody, view bobbing on. Mouse sensitivity goes in
configs/controls.json ("sensitivity": the slider value, 0.5 = 100%).
"""
import argparse
import json
import time
from pathlib import Path

import cv2

from .. import games
from . import controls as C
from .status import ROOT, Ticker, write_frame, write_status

REC_SIZE = (640, 360)


class Segment:
    """One recording file set. Backend-free: give it RGB frames and input snapshots."""

    def __init__(self, stem, mode, controls, ruleset=None, team_size=None, source="human", fps=20):
        self.stem = Path(stem)
        self.stem.parent.mkdir(parents=True, exist_ok=True)
        self.controls = controls
        self.writer = cv2.VideoWriter(str(self.stem) + ".mp4", cv2.VideoWriter_fourcc(*"mp4v"), fps, REC_SIZE)
        self.jl = open(str(self.stem) + ".jsonl", "w")
        self.meta = dict(mode=games.get(mode).key, ruleset=ruleset, team_size=team_size, source=source,
                         weight=1.0, loss_weight=1.0, started=time.time(), recorder="vpt_arena.live.recorder",
                         sensitivity=controls["sensitivity"])
        self.hotbar = 0
        self.n = 0

    def tick(self, frame_rgb, snap, gui_open, window_h=None):
        frame = cv2.resize(frame_rgb, REC_SIZE, interpolation=cv2.INTER_AREA)
        step, self.hotbar = C.tick_to_json(snap, self.controls, self.hotbar, gui_open, window_h=window_h, tick=self.n)
        self.writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        self.jl.write(json.dumps(step) + "\n")
        self.n += 1
        return step

    def close(self, min_frames=40):
        self.writer.release()
        self.jl.close()
        if self.n < min_frames:  # under 2 s: not worth keeping
            for ext in (".mp4", ".jsonl"):
                Path(str(self.stem) + ext).unlink(missing_ok=True)
            return None
        self.meta.update(frames=self.n, ended=time.time())
        Path(str(self.stem) + ".meta.json").write_text(json.dumps({k: v for k, v in self.meta.items() if v is not None},
                                                                  indent=1))
        return self.stem


def next_stem(out_dir):
    out_dir = Path(out_dir)
    day = time.strftime("%Y%m%d-%H%M%S")
    return out_dir / f"{day}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, help=f"one of: {', '.join(games.BY_KEY)}")
    ap.add_argument("--ruleset", choices=games.RULESETS)
    ap.add_argument("--team-size", type=int, choices=games.TEAM_SIZES)
    ap.add_argument("--out", default=None, help="default data/human/<mode>")
    ap.add_argument("--controls", default=None)
    ap.add_argument("--window", default="Minecraft", help="text in the window title")
    args = ap.parse_args(argv)
    from . import mac

    controls = C.load_controls(args.controls)
    out = Path(args.out or ROOT / "data" / "human" / games.get(args.mode).key)
    win = mac.find_minecraft_window(args.window)
    if not win:
        raise SystemExit(f"no window titled like {args.window!r}; start Minecraft first")
    print(f"recording window {win['id']} ({win['title']!r}) -> {out}  [F8 pause, Ctrl-C stop]")
    listener = mac.InputListener().start()
    seg, paused, saved = None, False, []
    tick = Ticker(20)
    last_frame = last_status = 0.0
    try:
        while True:
            snap = listener.snapshot()
            if "f8" in snap["new_keys"]:
                paused = not paused
                print("paused" if paused else "resumed")
            front = mac.frontmost_window_id() == win["id"]
            if paused or not front:
                if seg:
                    s = seg.close()
                    if s:
                        saved.append(s)
                        print(f"saved {s} ({seg.n / 20:.0f} s)")
                    seg = None
            else:
                frame = mac.capture_window(win["id"])
                if frame is not None:
                    if seg is None:
                        seg = Segment(next_stem(out), args.mode, controls, args.ruleset, args.team_size)
                    seg.tick(frame, snap, mac.cursor_visible(), window_h=win["bounds"][3])
                    if time.time() - last_frame > 1:
                        write_frame(frame)
                        last_frame = time.time()
            if time.time() - last_status > 1:
                last_status = time.time()
                write_status(state="recording" if seg else "idle", mode=args.mode, server="", fps=20.0,
                             checkpoint="", last_action={}, episode={"t": (seg.n / 20) if seg else 0, "return": 0})
            tick.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if seg:
            s = seg.close()
            if s:
                saved.append(s)
        listener.stop()
        write_status(state="idle", mode=args.mode, server="", fps=0.0, checkpoint="", last_action={}, episode={})
        print(f"{len(saved)} segments saved")


if __name__ == "__main__":
    main()
