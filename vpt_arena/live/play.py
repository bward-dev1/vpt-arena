"""Let the agent play: capture the Minecraft window, run the policy at 20 Hz, post keys and mouse.

    .venv/bin/python -m vpt_arena.live.play --weights runs/arena-2x/policy.weights --mode duels_sword \
        --server localhost:25565

--server has to be listed in configs/own_servers.json (your own servers;
public servers ban bots). The agent only sends input while the Minecraft
window is in front. Any key or click from you stops it (F12 also does), and
it lets go of every key on the way out.
"""
import argparse
import json
import time
from pathlib import Path

from .. import games
from . import controls as C
from .status import ROOT, Ticker, write_frame, write_status


def allowed_server(server, path=None):
    p = Path(path) if path else ROOT / "configs" / "own_servers.json"
    allowed = json.loads(p.read_text()).get("servers", []) if p.exists() else []
    host = server.split(":")[0].lower()
    return any(host == a.split(":")[0].lower() for a in allowed)


class PlayLoop:
    """Backend-free loop body, so it can be driven by fakes in tests and by RL's LiveEnv."""

    def __init__(self, agent, applier, capture, is_front, gui_open, stop_signal):
        self.agent, self.applier = agent, applier
        self.capture, self.is_front, self.gui_open, self.stop_signal = capture, is_front, gui_open, stop_signal
        self.paused = False
        self.steps = 0
        self.last_action = None
        self.last_frame = None

    def step(self):
        """One 20 Hz tick. Returns 'stop', 'paused' or 'acted'."""
        if self.stop_signal():
            return "stop"
        if not self.is_front():
            if not self.paused:
                self.applier.release_all()
                self.paused = True
            return "paused"
        frame = self.capture()
        if frame is None:
            return "paused"
        if self.paused:
            self.paused = False
        action, info = self.agent.act(frame)
        self.applier.apply(action, gui_open=self.gui_open())
        self.steps += 1
        self.last_action, self.last_frame = action, frame
        return "acted"


class HumanStop:
    """True once the player presses anything after the agent has had the window for `grace` seconds.

    The click that brings Minecraft to the front doesn't count, and presses
    while another app is in front don't either.
    """

    def __init__(self, presses, is_front, grace=1.5, clock=time.monotonic):
        self.presses, self.is_front, self.grace, self.clock = presses, is_front, grace, clock
        self.base, self.front_since = presses(), None

    def __call__(self):
        now, n = self.clock(), self.presses()
        if not self.is_front():
            self.base, self.front_since = n, None
            return False
        if self.front_since is None:
            self.front_since = now
        if now - self.front_since < self.grace:
            self.base = n
            return False
        return n > self.base


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--arch", default="2x")
    ap.add_argument("--mode", required=True, help=f"one of: {', '.join(games.BY_KEY)}")
    ap.add_argument("--ruleset", choices=games.RULESETS)
    ap.add_argument("--team-size", type=int, choices=games.TEAM_SIZES)
    ap.add_argument("--server", required=True, help="host[:port] of the server the client is connected to")
    ap.add_argument("--controls", default=None)
    ap.add_argument("--window", default="Minecraft")
    ap.add_argument("--deterministic", action="store_true")
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--device", default=None)
    args = ap.parse_args(argv)
    if not allowed_server(args.server):
        raise SystemExit(f"{args.server} is not in configs/own_servers.json; the agent only plays on your own servers")

    from ..agent import ArenaAgent
    from . import mac

    win = mac.find_minecraft_window(args.window)
    if not win:
        raise SystemExit(f"no window titled like {args.window!r}; start Minecraft and join {args.server} first")
    controls = C.load_controls(args.controls)
    agent = ArenaAgent(args.arch, args.weights, args.mode, args.ruleset, args.team_size, device=args.device,
                       stochastic=not args.deterministic)
    poster = mac.InputPoster()
    applier = C.ActionApplier(poster, controls)
    listener = mac.InputListener().start()
    is_front = lambda: mac.frontmost_window_id() == win["id"]  # noqa: E731
    loop = PlayLoop(agent, applier, capture=lambda: mac.capture_window(win["id"]), is_front=is_front,
                    gui_open=mac.cursor_visible, stop_signal=HumanStop(lambda: listener.human_presses, is_front))
    print(f"playing {args.mode} on {args.server}; click into Minecraft to start, press any key to stop")
    tick, t0, last_ui = Ticker(20), time.time(), 0.0
    reason = "time limit"
    try:
        while time.time() - t0 < args.minutes * 60:
            r = loop.step()
            if r == "stop":
                reason = f"you pressed {listener.last_human_key or 'a mouse button'}"
                break
            if time.time() - last_ui > 1:
                last_ui = time.time()
                if loop.last_frame is not None:
                    write_frame(loop.last_frame)
                write_status(state="paused" if r == "paused" else "playing", mode=args.mode, server=args.server,
                             checkpoint=str(args.weights), fps=round(20.0 * (1 - min(1, tick.late / max(1, loop.steps))), 1),
                             last_action=C.env_action_summary(loop.last_action) if loop.last_action else {},
                             episode={"t": round(time.time() - t0, 1), "return": 0.0})
            tick.wait()
    except KeyboardInterrupt:
        reason = "Ctrl-C"
    finally:
        applier.release_all()
        listener.stop()
        write_status(state="idle", mode=args.mode, server=args.server, checkpoint=str(args.weights), fps=0.0,
                     last_action={}, episode={})
        print(f"stopped ({reason}) after {loop.steps} steps")


if __name__ == "__main__":
    main()
