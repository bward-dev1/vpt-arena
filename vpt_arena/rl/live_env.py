"""A real-Minecraft environment for RL and evaluation on your own server.

One LiveEnv = one Minecraft client window logged in as the agent's player.
reset() starts a round over RCON (configs/arenas.json) and waits for the
round_start line; step() applies one 20 Hz action, captures the next frame and
turns new log events into reward with the mode's weights (games.py). The
round ends on a win/loss/draw line or the mode's time limit.

The OS side (capture, input posting, focus check) and the server side (RCON,
log) are passed in, so tests drive it with fakes.
"""
import json
import os
import time
from pathlib import Path

from .. import games
from ..live.controls import ActionApplier, load_controls
from ..live.status import Ticker
from .server import LogFollower, Rcon, parse_line, reward_for

ROOT = Path(__file__).resolve().parents[2]


def load_arenas(path=None):
    return json.loads(Path(path or ROOT / "configs" / "arenas.json").read_text())


class LiveEnv:
    def __init__(self, mode, capture, poster, is_front, gui_open, rcon_cmd, log_lines, agent_name, opponent_name,
                 arena_cfg, controls=None, hz=20, clock=time.time, sleep=True):
        self.mode = games.get(mode)
        self.cfg = arena_cfg["modes"][self.mode.key]
        self.capture, self.is_front, self.gui_open = capture, is_front, gui_open
        self.rcon_cmd, self.log_lines = rcon_cmd, log_lines
        self.me, self.opp = agent_name, opponent_name
        self.applier = ActionApplier(poster, controls or load_controls())
        self.patterns = self.cfg.get("patterns", [])
        self.ticker = Ticker(hz) if sleep else None
        self.clock = clock
        self.t0 = None
        self.last_frame = None

    def _events(self):
        evs = []
        for ln in self.log_lines():
            evs += parse_line(ln, self.patterns)
        return evs

    def reset(self, timeout=60.0):
        self.applier.release_all()
        self.log_lines()  # drop anything older than this round
        for c in self.cfg.get("start", []):
            self.rcon_cmd(c.format(agent=self.me, opponent=self.opp))
        want = self.cfg.get("start_event")
        t0 = self.clock()
        while want and self.clock() - t0 < timeout:
            if any(e["event"] == want for e in self._events()):
                break
            if self.ticker:
                time.sleep(0.1)
        self.t0 = self.clock()
        self.last_frame = self._frame()
        return self.last_frame

    def _frame(self):
        f = self.capture()
        return f if f is not None else self.last_frame

    def step(self, action):
        if not self.is_front():
            self.applier.release_all()
            raise RuntimeError("Minecraft is not the front window; stopping the episode")
        self.applier.apply(action, gui_open=self.gui_open())
        if self.ticker:
            self.ticker.wait()
        frame = self._frame()
        self.last_frame = frame
        evs = self._events()
        r, flags = reward_for(evs, self.me, self.mode.events)
        ends = set(self.cfg.get("end_events", ["win", "loss"]))
        ended_by_event = any(e["event"] in ends for e in evs)
        timed_out = self.clock() - self.t0 > self.cfg.get("max_seconds", 300)
        done = ended_by_event or timed_out
        won = any(e["event"] == "win" and e.get("player") == self.me for e in evs)
        if done:
            self.applier.release_all()
        return frame, r, done, {"won": won, "events": evs, "timed_out": timed_out and not ended_by_event}


def make_live_env(mode, window_title="Minecraft", arenas_path=None, controls_path=None):
    """The real thing: Quartz capture/input, RCON from configs/arenas.json, the server log."""
    from ..live import mac
    cfg = load_arenas(arenas_path)
    win = mac.find_minecraft_window(window_title)
    if not win:
        raise SystemExit("no Minecraft window found")
    pw = os.environ.get("VPT_RCON_PASSWORD")
    if not pw:
        raise SystemExit("set VPT_RCON_PASSWORD (the server's rcon.password)")
    if not cfg.get("server_log") or not cfg.get("opponent_name"):
        raise SystemExit("set server_log and opponent_name in configs/arenas.json")
    rc = Rcon(cfg["rcon"]["host"], cfg["rcon"]["port"], pw)
    follower = LogFollower(os.path.expanduser(cfg["server_log"]))
    return LiveEnv(mode, capture=lambda: mac.capture_window(win["id"]), poster=mac.InputPoster(),
                   is_front=lambda: mac.frontmost_window_id() == win["id"], gui_open=mac.cursor_visible,
                   rcon_cmd=rc.cmd, log_lines=follower.lines, agent_name=cfg["agent_name"],
                   opponent_name=cfg["opponent_name"], arena_cfg=cfg, controls=load_controls(controls_path))
