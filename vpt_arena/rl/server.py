"""Talking to your Minecraft server: RCON commands out, game events in (from the server log).

Events come from two kinds of log lines:
  - vanilla death messages ("Steve was slain by VPTAgent", "VPTAgent fell out of the world")
  - arena lines printed by the vpt_arena datapack or a minigame plugin via /say:
        [VPTAgent] [ARENA] win
        [Server] [ARENA] round_start duels_sword
    and, for plugins with their own chat format, regexes in configs/arenas.json
    ("patterns": [{"regex": "...(?P<player>\\w+) broke (?P<other>\\w+)'s bed", "event": "bed_broken"}]).

Event dicts: {"event": name, "player": who it happened to / who did it, "other": opponent or None}.
"""
import os
import re
import socket
import struct
import time
from pathlib import Path

LOG_PREFIX = re.compile(r"^\[[^\]]*\] \[[^\]]*/INFO\]: (?:\[Not Secure\] )?(?P<msg>.*)$")
ARENA = re.compile(r"^\[(?P<who>[^\]]+)\] \[ARENA\] (?P<event>\w+)(?: (?P<arg>\S+))?")
NAME = r"(?P<victim>[A-Za-z0-9_]{3,16})"
DEATH_VERBS = (
    "was slain by", "was shot by", "was killed by", "was knocked into the void by", "was blown up by",
    "was fireballed by", "was pummeled by", "was impaled by", "was squashed by", "was skewered by",
    "was struck by lightning", "was doomed to fall", "was burnt to a crisp", "was poked to death",
    "fell from a high place", "fell off", "fell out of the world", "fell into", "hit the ground too hard",
    "drowned", "burned to death", "went up in flames", "went off with a bang", "tried to swim in lava",
    "blew up", "suffocated", "starved to death", "withered away", "froze to death", "died",
    "experienced kinetic energy", "discovered the floor was lava", "walked into", "didn't want to live",
    "left the confines of this world",
)
DEATH = re.compile(rf"^{NAME} (?P<verb>{'|'.join(re.escape(v) for v in DEATH_VERBS)})(?P<rest>.*)$")
BY = re.compile(r"\bby (?P<killer>[A-Za-z0-9_]{3,16})\b")


def parse_line(line, patterns=()):
    """One server log line -> list of event dicts."""
    m = LOG_PREFIX.match(line.rstrip("\n"))
    msg = m.group("msg") if m else line.rstrip("\n")
    out = []
    a = ARENA.match(msg)
    if a:
        who = a.group("who")
        out.append(dict(event=a.group("event"), player=None if who in ("Server", "Rcon") else who, other=a.group("arg")))
        return out
    d = DEATH.match(msg)
    if d:
        victim = d.group("victim")
        k = BY.search(d.group("verb") + d.group("rest"))
        killer = k.group("killer") if k else None
        out.append(dict(event="death", player=victim, other=killer))
        if killer and killer != victim:
            out.append(dict(event="kill", player=killer, other=victim))
        if "void" in d.group("verb") or "out of the world" in d.group("verb"):
            if killer:
                out.append(dict(event="void_kill", player=killer, other=victim))
        return out
    for p in patterns:
        mm = re.search(p["regex"], msg)
        if mm:
            g = mm.groupdict()
            out.append(dict(event=p["event"], player=g.get("player"), other=g.get("other")))
    return out


def reward_for(events, me, weights):
    """Sum mode reward weights over events that concern `me`.

    An event counts for me when I'm its `player`. A few events are mirrored onto
    the other side: someone else's `kill` of me is already my `death`, and a
    `bed_broken` by someone else against my bed comes in as `bed_lost` from the
    plugin pattern, so no mirroring is needed beyond `win` -> the rest lose.
    """
    r, flags = 0.0, set()
    for e in events:
        if e.get("player") == me:
            r += weights.get(e["event"], 0.0)
            flags.add(e["event"])
        elif e["event"] == "win" and e.get("player") not in (None, me):
            r += weights.get("loss", 0.0)
            flags.add("loss")
    return r, flags


class LogFollower:
    """tail -F for the server's logs/latest.log (handles rotation on restart)."""

    def __init__(self, path, from_end=True):
        self.path = Path(path)
        self.f, self.ino = None, None
        self._open(from_end)

    def _open(self, from_end):
        try:
            self.f = open(self.path, "r", errors="replace")
            self.ino = os.fstat(self.f.fileno()).st_ino
            if from_end:
                self.f.seek(0, 2)
        except FileNotFoundError:
            self.f = None

    def lines(self):
        if self.f is None:
            self._open(False)
            if self.f is None:
                return []
        out = []
        while True:
            ln = self.f.readline()
            if not ln:
                break
            out.append(ln)
        try:
            if os.stat(self.path).st_ino != self.ino:  # rotated
                self.f.close()
                self._open(False)
                out += self.lines()
        except FileNotFoundError:
            pass
        return out


class Rcon:
    """Minimal Source RCON client (what Minecraft speaks with enable-rcon=true)."""

    def __init__(self, host="127.0.0.1", port=25575, password="", timeout=5.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.req = 0
        if self._send(3, password)[0] == -1:
            raise PermissionError("RCON authentication failed")

    def _pkt(self, rid, ptype, body):
        data = struct.pack("<ii", rid, ptype) + body.encode("utf-8") + b"\x00\x00"
        return struct.pack("<i", len(data)) + data

    def _recv(self):
        hdr = self._read(4)
        (n,) = struct.unpack("<i", hdr)
        data = self._read(n)
        rid, ptype = struct.unpack("<ii", data[:8])
        return rid, ptype, data[8:-2].decode("utf-8", "replace")

    def _read(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("RCON connection closed")
            buf += chunk
        return buf

    def _send(self, ptype, body):
        self.req += 1
        self.sock.sendall(self._pkt(self.req, ptype, body))
        rid, _, text = self._recv()
        return rid, text

    def cmd(self, command):
        return self._send(2, command.lstrip("/"))[1]

    def close(self):
        self.sock.close()


def wait_for(follower, pred, timeout=30.0, patterns=(), poll=0.1):
    """Read log events until pred(event) is true; returns (event or None, all events seen)."""
    seen, t0 = [], time.time()
    while time.time() - t0 < timeout:
        for ln in follower.lines():
            for e in parse_line(ln, patterns):
                seen.append(e)
                if pred(e):
                    return e, seen
        time.sleep(poll)
    return None, seen
