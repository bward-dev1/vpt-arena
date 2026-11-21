"""Server side: log parsing, rewards, RCON against a fake server, LiveEnv rounds with fakes, the Elo league, the datapack.

    .venv/bin/python -m tests.server_test
"""
import json
import socket
import struct
import sys
import tempfile
import threading
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vpt_arena import games, league  # noqa: E402
from vpt_arena.rl.live_env import LiveEnv, load_arenas  # noqa: E402
from vpt_arena.rl.server import LogFollower, Rcon, parse_line, reward_for  # noqa: E402
from vpt_arena.vpt import noop_env_action  # noqa: E402
from tests.live_test import FakePoster  # noqa: E402
from tools import make_datapack  # noqa: E402

L = "[10:31:02] [Server thread/INFO]: "


def fake_rcon_server(password, log):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def run():
        c, _ = srv.accept()
        while True:
            hdr = c.recv(4)
            if len(hdr) < 4:
                break
            (n,) = struct.unpack("<i", hdr)
            data = b""
            while len(data) < n:
                data += c.recv(n - len(data))
            rid, ptype = struct.unpack("<ii", data[:8])
            body = data[8:-2].decode()
            if ptype == 3:
                rid = rid if body == password else -1
                text = ""
            else:
                log.append(body)
                text = f"ran {body}"
            out = struct.pack("<ii", rid, 0) + text.encode() + b"\x00\x00"
            c.sendall(struct.pack("<i", len(out)) + out)
        c.close()

    threading.Thread(target=run, daemon=True).start()
    return srv.getsockname()[1]


def main():
    n = 0
    # parsing
    ev = parse_line(L + "Steve was slain by VPTAgent")
    assert {"event": "death", "player": "Steve", "other": "VPTAgent"} in ev
    assert {"event": "kill", "player": "VPTAgent", "other": "Steve"} in ev
    ev = parse_line(L + "VPTAgent was knocked into the void by Steve")
    assert any(e["event"] == "void_kill" and e["player"] == "Steve" for e in ev)
    ev = parse_line(L + "VPTAgent fell out of the world")
    assert ev == [{"event": "death", "player": "VPTAgent", "other": None}]
    assert parse_line(L + "[VPTAgent] [ARENA] win") == [{"event": "win", "player": "VPTAgent", "other": None}]
    assert parse_line(L + "[Server] [ARENA] round_start sword")[0]["other"] == "sword"
    assert parse_line(L + "<Steve> I was slain by lag") == []  # chat isn't a death
    pats = load_arenas()["modes"]["bedwars_solo"]["patterns"]
    assert parse_line(L + "Red's bed was destroyed by VPTAgent", pats)[0] == {"event": "bed_broken",
                                                                              "player": "VPTAgent", "other": "Red"}
    n += 1
    w = games.get("duels_sword").events
    r, flags = reward_for(parse_line(L + "Steve was slain by VPTAgent") + parse_line(L + "[VPTAgent] [ARENA] win"),
                          "VPTAgent", w)
    assert r == w["kill"] + w["win"] and {"kill", "win"} <= flags
    r, _ = reward_for(parse_line(L + "[Steve] [ARENA] win"), "VPTAgent", w)
    assert r == w["loss"]
    n += 1

    # rcon
    got = []
    port = fake_rcon_server("pw", got)
    rc = Rcon("127.0.0.1", port, "pw")
    assert rc.cmd("/say hi") == "ran say hi" and got == ["say hi"]
    rc.close()
    port = fake_rcon_server("pw", [])
    try:
        Rcon("127.0.0.1", port, "nope")
        raise AssertionError("bad password accepted")
    except PermissionError:
        pass
    n += 1

    # log follower with rotation
    tmp = Path(tempfile.mkdtemp(prefix="vpt-arena-srv-"))
    log = tmp / "latest.log"
    log.write_text(L + "old line\n")
    fol = LogFollower(log)
    with open(log, "a") as f:
        f.write(L + "[VPTAgent] [ARENA] win\n")
    assert len(fol.lines()) == 1
    log.unlink()
    log.write_text(L + "after restart\n")
    assert fol.lines() == [L + "after restart\n"]
    n += 1

    # LiveEnv round with fakes: start commands, round_start wait, kill + win -> reward and done
    cmds, pending = [], []
    feed = {"lines": []}

    def rcon_cmd(c):
        cmds.append(c)
        if c.startswith("function vpt:duel/start_"):
            feed["lines"].append(L + "[Server] [ARENA] round_start sword\n")

    def log_lines():
        out, feed["lines"] = feed["lines"], []
        return out

    clock = {"t": 0.0}
    env = LiveEnv("duels_sword", capture=lambda: np.zeros((360, 640, 3), np.uint8), poster=FakePoster(),
                  is_front=lambda: True, gui_open=lambda: False, rcon_cmd=rcon_cmd, log_lines=log_lines,
                  agent_name="VPTAgent", opponent_name="Steve", arena_cfg=load_arenas(), sleep=False,
                  clock=lambda: clock["t"])
    env.reset()
    assert "tag VPTAgent add vpt_a" in cmds and "function vpt:duel/start_sword" in cmds
    a = noop_env_action()
    a["attack"] = 1
    _, r, done, info = env.step(a)
    assert r == 0 and not done
    feed["lines"] += [L + "Steve was slain by VPTAgent\n", L + "[VPTAgent] [ARENA] win\n"]
    _, r, done, info = env.step(a)
    assert done and info["won"] and r == w["kill"] + w["win"]
    env.reset()
    clock["t"] = 10_000.0
    _, _, done, info = env.step(a)
    assert done and info["timed_out"]
    n += 1

    # league
    lg = {"players": {}, "matches": []}
    for _ in range(5):
        league.record(lg, "duels_sword", "ckpt-a", "bot", "ckpt-a")
    league.record(lg, "duels_sword", "ckpt-a", "bot", None)
    pa, pb = lg["players"]["ckpt-a"], lg["players"]["bot"]
    assert pa["elo"] > 1060 and abs(pa["elo"] + pb["elo"] - 2000) < 0.5 and pa["wins"] == 5 and pa["games"] == 6
    assert pa["by_mode"]["duels_sword"] == pa["elo"]
    league.save(lg, tmp / "league.json")
    assert league.load(tmp / "league.json")["players"]["bot"]["games"] == 6
    n += 1

    # datapack files
    make_datapack.main(["--out", str(tmp / "dp"), "--format", "101"])
    mc = json.loads((tmp / "dp" / "pack.mcmeta").read_text())["pack"]
    assert mc["max_format"] == 101 and "pack_format" not in mc
    fns = {p.relative_to(tmp / "dp" / "data" / "vpt" / "function").as_posix()
           for p in (tmp / "dp" / "data" / "vpt" / "function").rglob("*.mcfunction")}
    for mode, cfg in load_arenas()["modes"].items():
        for c in cfg.get("start", []):
            if c.startswith("function vpt:"):
                assert c.split("vpt:")[1] + ".mcfunction" in fns, c
    body = "".join(p.read_text() for p in (tmp / "dp").rglob("*.mcfunction"))
    assert "doImmediateRespawn" not in body and "[ARENA] win" in body
    n += 1
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{n} server checks passed")


if __name__ == "__main__":
    main()
