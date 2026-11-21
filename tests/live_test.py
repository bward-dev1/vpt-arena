"""Live-client logic with fake OS backends: recorder output, input mapping, the play loop's safety stops.

    .venv/bin/python -m tests.live_test
"""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vpt_arena import data as D  # noqa: E402
from vpt_arena.live import controls as C  # noqa: E402
from vpt_arena.live.play import HumanStop, PlayLoop, allowed_server  # noqa: E402
from vpt_arena.live.recorder import Segment  # noqa: E402
from vpt_arena.vpt import ActionCodec, json_to_env_action, noop_env_action  # noqa: E402


class FakePoster:
    def __init__(self):
        self.log = []
        self.held_keys, self.held_buttons = set(), set()

    def key(self, k, down):
        self.log.append(("key", k, down))
        (self.held_keys.add if down else self.held_keys.discard)(k)

    def button(self, b, down):
        self.log.append(("btn", b, down))
        (self.held_buttons.add if down else self.held_buttons.discard)(b)

    def move(self, dx, dy):
        self.log.append(("move", round(dx, 2), round(dy, 2)))

    def release_all(self):
        for k in list(self.held_keys):
            self.key(k, False)
        for b in list(self.held_buttons):
            self.button(b, False)


def snap(keys=(), new=(), buttons=(), newb=(), dx=0.0, dy=0.0, wheel=0.0):
    return dict(keys=list(keys), new_keys=list(new), buttons=list(buttons), new_buttons=list(newb), dx=dx, dy=dy,
                dwheel=wheel, xy=(100, 50))


def main():
    ok = 0
    ctl = C.load_controls()
    ctl["sensitivity"] = 0.5

    # recorder line format, with sprint rebound to R
    ctl_r = dict(ctl, bindings=dict(ctl["bindings"], sprint="r"))
    step, hb = C.tick_to_json(snap(keys=["w", "r"], new=["w"], buttons=[0], newb=[0], dx=10, dy=-4), ctl_r, 0, False)
    assert set(step["keyboard"]["keys"]) == {"key.keyboard.w", "key.keyboard.left.control"}, step
    assert step["mouse"]["buttons"] == [0] and abs(step["mouse"]["dx"] - 10) < 1e-6, step
    a, null = json_to_env_action(step)
    assert a["forward"] and a["sprint"] and a["attack"] and not null
    ok += 1
    # sensitivity rescaling: at slider 1.0 one pixel turns (0.8)^3*1.2 = 0.6144 deg -> 4.096 VPT pixels
    step, _ = C.tick_to_json(snap(dx=1), dict(ctl, sensitivity=1.0), 0, False)
    assert abs(step["mouse"]["dx"] - 4.096) < 1e-3, step["mouse"]
    ok += 1
    # hotbar from number keys and the scroll wheel
    _, hb = C.tick_to_json(snap(keys=["3"], new=["3"]), ctl, 0, False)
    assert hb == 2
    _, hb = C.tick_to_json(snap(wheel=-1), ctl, 8, False)
    assert hb == 0, hb
    ok += 1

    # applier: holds, releases, taps, camera -> pixels
    fp = FakePoster()
    ap = C.ActionApplier(fp, ctl)
    act = noop_env_action()
    act.update(forward=1, attack=1, camera=np.array([1.5, -3.0]))
    ap.apply(act)
    assert ("key", "w", True) in fp.log and ("btn", 0, True) in fp.log
    mv = [e for e in fp.log if e[0] == "move"][-1]
    assert abs(mv[1] + 20.0) < 0.01 and abs(mv[2] - 10.0) < 0.01, mv  # 0.15 deg/px at 100%
    fp.log.clear()
    act2 = noop_env_action()
    act2["hotbar.2"] = 1
    ap.apply(act2)
    assert ("key", "w", False) in fp.log and ("btn", 0, False) in fp.log
    assert ("key", "2", True) in fp.log and ("key", "2", False) in fp.log
    act3 = noop_env_action()
    act3.update(jump=1, sneak=1)
    ap.apply(act3)
    ap.release_all()
    assert not fp.held_keys and not fp.held_buttons and not ap.held
    ok += 1

    # play loop: pauses and lets go when Minecraft isn't in front; stops on a human press after the grace period
    class FakeAgent:
        def act(self, frame):
            a = noop_env_action()
            a["forward"] = 1
            return a, {}

    front = {"v": True}
    presses = {"n": 0}
    t = {"now": 0.0}
    stop = HumanStop(lambda: presses["n"], lambda: front["v"], grace=1.0, clock=lambda: t["now"])
    fp = FakePoster()
    loop = PlayLoop(FakeAgent(), C.ActionApplier(fp, ctl), capture=lambda: np.zeros((360, 640, 3), np.uint8),
                    is_front=lambda: front["v"], gui_open=lambda: False, stop_signal=stop)
    presses["n"] = 1  # the click that focused the window
    assert loop.step() == "acted" and "w" in fp.held_keys
    front["v"] = False
    assert loop.step() == "paused" and not fp.held_keys
    front["v"] = True
    t["now"] = 0.5
    presses["n"] = 2  # click to refocus: inside the grace period, ignored
    assert loop.step() == "acted"
    t["now"] = 3.0
    assert loop.step() == "acted"
    presses["n"] = 3
    assert loop.step() == "stop"
    ok += 1

    assert allowed_server("localhost:25565") and allowed_server("127.0.0.1")
    assert not allowed_server("mc.hypixel.net")
    ok += 1

    # recorder segment -> files the training loader reads
    tmp = Path(tempfile.mkdtemp(prefix="vpt-arena-live-"))
    seg = Segment(tmp / "human" / "duels_sword" / "rec1", "duels_sword", ctl, ruleset="legacy")
    rng = np.random.default_rng(0)
    for i in range(60):
        frame = rng.integers(0, 255, (720, 1280, 3), dtype=np.uint8)
        seg.tick(frame, snap(keys=["w"] if i % 2 else [], dx=float(i % 5)), gui_open=False, window_h=720)
    stem = seg.close()
    meta = json.loads(Path(str(stem) + ".meta.json").read_text())
    assert meta["mode"] == "duels_sword" and meta["frames"] == 60 and meta["ruleset"] == "legacy"
    trajs = D.find_trajectories(tmp / "human")
    steps = list(D.iter_trajectory(trajs[0], ActionCodec()))
    assert len(steps) > 30, len(steps)
    short = Segment(tmp / "human" / "x" / "short", "duels_sword", ctl)
    short.tick(np.zeros((360, 640, 3), np.uint8), snap(), False)
    assert short.close() is None and not Path(str(short.stem) + ".mp4").exists()
    ok += 1
    print(f"{ok} live checks passed")


if __name__ == "__main__":
    main()
