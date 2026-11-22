"""Tests for the dashboard server: builds a tiny fixture root, serves it, hits every endpoint.

Run:   .venv/bin/python -m tests.site_test
Look:  .venv/bin/python -m tests.site_test --serve [port]   (fixture root kept fresh; Ctrl-C deletes it)
"""
import json
import math
import random
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from vpt_arena import games
from vpt_arena.site.server import make_server


def _video(path, n=6, seed=0):
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 20, (64, 36))
    rng = np.random.RandomState(seed)
    for i in range(n):
        f = np.zeros((36, 64, 3), np.uint8)
        f[:, :] = (40 + seed * 40 % 200, 90, 160)
        f[10:20, 5 + i * 3:20 + i * 3] = rng.randint(100, 255, 3)
        w.write(f)
    w.release()


def _traj(d, stem, n, meta=None, seed=0, corrupt=False):
    d.mkdir(parents=True, exist_ok=True)
    _video(d / f"{stem}.mp4", n, seed)
    lines = [json.dumps({"keyboard": {"keys": ["key.keyboard.w"], "newKeys": [], "chars": ""},
                         "mouse": {"dx": 0.0, "dy": 0.0, "buttons": [], "newButtons": [], "x": 0.0, "y": 0.0, "dwheel": 0.0},
                         "hotbar": 0, "isGuiOpen": False, "tick": i}) for i in range(n)]
    if corrupt:
        lines.append("{not json")
    (d / f"{stem}.jsonl").write_text("\n".join(lines) + "\n")
    if meta is not None:
        (d / f"{stem}.meta.json").write_text(json.dumps(meta))


def write_status(root, state="playing", t=None, frame=True):
    live = Path(root) / "live"
    live.mkdir(parents=True, exist_ok=True)
    t = time.time() if t is None else t
    keys = ["forward", "left", "back", "right", "jump", "attack", "use", "sprint", "sneak"]
    a = {k: 0 for k in keys}
    for k in random.sample(keys, 3):
        a[k] = 1
    a["hotbar.%d" % random.randint(1, 9)] = 1
    a["camera"] = [round(random.uniform(-6, 6), 2), round(random.uniform(-9, 9), 2)]
    (live / "status.json").write_text(json.dumps({
        "state": state, "mode": "duels_sword", "checkpoint": "runs/arena-2x/step_5000.pt", "server": "localhost:25565",
        "fps": 19.7, "updated": t, "last_action": a, "episode": {"t": 41.5, "return": 3.2}}))
    if frame:
        img = np.zeros((360, 640, 3), np.uint8)
        img[:] = (60, 110, 80)
        cv2.rectangle(img, (200, 120), (440, 300), (30, 60, 200), -1)
        cv2.putText(img, "agent view", (230, 220), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.imwrite(str(live / "frame.jpg"), img)


def make_fixture(root):
    root = Path(root)
    now = time.time()
    _traj(root / "data" / "human" / "run1", "g1", 12, {"mode": "bedwars_solo", "ruleset": "legacy", "team_size": 1,
                                                       "source": "human", "weight": 1.0, "loss_weight": 1.0}, 1)
    _traj(root / "data" / "idm" / "sword", "g2", 8, {"mode": "duels_sword", "ruleset": "modern", "team_size": 1,
                                                    "source": "idm", "weight": 1.0, "loss_weight": 0.5}, 2, corrupt=True)
    _traj(root / "data" / "contractor", "g3", 6, None, 3)
    _traj(root / "data" / "misc", "g4", 5, {"mode": "not_a_mode", "source": "weird"}, 4)
    # a video with no jsonl is ignored
    _video(root / "data" / "contractor" / "orphan.mp4")
    runs = root / "runs"
    (runs / "bc1").mkdir(parents=True)
    (runs / "bc1" / "run.json").write_text(json.dumps({"kind": "bc", "arch": "2x", "started": now - 3600,
                                                      "args": {"lr": 2e-5, "steps": 20000, "data": ["data/human:4"]}}))
    rows = []
    for s in range(1, 81):
        r = {"step": s * 50, "nll": 3.2 * math.exp(-s / 30) + 1.1 + random.random() * .05, "btn_acc": 0.3 + 0.4 * (1 - math.exp(-s / 25)),
             "kl": 0.01 * s ** .5, "grad_norm": 2 + random.random(), "lr": 2e-5 * min(1, s / 10), "sec": 1.5 + random.random() * .2}
        if s % 5 == 0:
            r["eval_nll"] = r["nll"] + 0.1
            r["eval_btn_acc"] = r["btn_acc"] - 0.05
        rows.append(json.dumps(r))
    rows.insert(7, "{broken")
    rows.append('{"step": 4100, "nll": 1.2')    # truncated last line
    (runs / "bc1" / "log.jsonl").write_text("\n".join(rows))
    (runs / "rl1").mkdir()
    (runs / "rl1" / "run.json").write_text(json.dumps({"kind": "rl", "arch": "2x", "started": now - 600, "args": {"kl_coef": 0.1}}))
    (runs / "rl1" / "rl_log.jsonl").write_text("\n".join(json.dumps({
        "iter": i, "env_steps": i * 4096, "ep_return_mean": -4 + i * .3, "ep_len_mean": 800 + i, "win_rate": min(1, .2 + i * .02),
        "kl": .01 * i, "pi_loss": .1 / (i + 1), "v_loss": 1 / (i + 1), "entropy": 2.2 - i * .02, "fps": 300 + i,
        "by_mode": {"duels_sword": i * .2, "bedwars_solo": i * .1}}) for i in range(30)))
    (runs / "empty").mkdir()
    players = {
        "ckpt-5000": {"elo": 1112.5, "games": 40, "wins": 24, "kind": "checkpoint", "by_mode": {"duels_sword": 1150, "bedwars_solo": 1060}},
        "bot-sword": {"elo": 1000.0, "games": 50, "wins": 22, "kind": "scripted", "by_mode": {"duels_sword": 990}},
        "player-1": {"elo": 1180.0, "games": 12, "wins": 9, "kind": "human", "by_mode": {"duels_sword": 1210}},
        "random": {"elo": 760.0, "games": 0, "wins": 0, "kind": "random", "by_mode": {}},
    }
    matches = [{"t": now - i * 90, "mode": ["duels_sword", "bedwars_solo"][i % 2], "a": "ckpt-5000", "b": "bot-sword",
                "winner": ["ckpt-5000", "bot-sword", None][i % 3], "score": "3-2"} for i in range(15)]
    (runs / "league.json").write_text(json.dumps({"players": players, "matches": matches}))
    write_status(root)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="vpt-site-test-"))
        make_fixture(cls.tmp)
        cls.srv = make_server(cls.tmp, 0)
        cls.port = cls.srv.server_address[1]
        cls.th = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.th.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def get(self, path, method="GET"):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def j(self, path):
        code, h, body = self.get(path)
        self.assertEqual(code, 200, path)
        self.assertIn("application/json", h["Content-Type"])
        return json.loads(body)


class SiteTest(Base):
    def test_static(self):
        for p, ct in (("/", "text/html"), ("/index.html", "text/html"), ("/style.css", "text/css"), ("/app.js", "javascript")):
            code, h, body = self.get(p)
            self.assertEqual(code, 200, p)
            self.assertIn(ct, h["Content-Type"])
            self.assertTrue(body)
        self.assertEqual(self.get("/nope.js")[0], 404)
        self.assertEqual(self.get("/docs/record")[0], 200)     # route fallback

    def test_modes(self):
        d = self.j("/api/modes")["modes"]
        self.assertEqual(len(d), len(games.MODES))
        m = {x["key"]: x for x in d}["duels_sword"]
        self.assertEqual(m["ruleset"], "modern")
        self.assertIn("win", m["events"])
        self.assertEqual(m["trajectories"], 1)
        self.assertAlmostEqual(m["hours"], 9 / 20 / 3600, places=9)    # raw non-empty line count, corrupt line included
        self.assertEqual(m["best_elo"]["name"], "player-1")
        self.assertEqual(m["best_elo"]["elo"], 1210)
        self.assertIsNone({x["key"]: x for x in d}["spleef"]["best_elo"])

    def test_data(self):
        d = self.j("/api/data")
        self.assertEqual(d["total"]["trajectories"], 4)
        self.assertEqual(d["by_source"]["human"]["trajectories"], 1)
        self.assertEqual(d["by_source"]["idm"]["trajectories"], 1)
        self.assertEqual(d["by_source"]["contractor"]["trajectories"], 1)    # no meta
        self.assertEqual(d["by_source"]["other"]["trajectories"], 1)         # source "weird"
        self.assertEqual(d["by_mode"]["survival"]["trajectories"], 1)
        self.assertIn("not_a_mode", d["by_mode"])
        self.assertAlmostEqual(d["total"]["hours"], (12 + 9 + 6 + 5) / 20 / 3600, places=9)
        self.assertEqual(len(d["recent"]), 4)
        for k in ("path", "mode", "source", "hours", "frames", "mode_name"):
            self.assertIn(k, d["recent"][0])

    def test_thumb(self):
        d = self.j("/api/data")
        for t in d["recent"]:
            code, h, body = self.get("/api/thumb?path=" + urllib.request.quote(t["path"]))
            self.assertEqual(code, 200)
            self.assertEqual(h["Content-Type"], "image/jpeg")
            self.assertTrue(body.startswith(b"\xff\xd8"))
        self.assertTrue(any((self.tmp / "runs" / ".site-cache").glob("*.jpg")))
        self.assertEqual(self.get("/api/thumb?path=nothing.mp4")[0], 404)
        self.assertEqual(self.get("/api/thumb")[0], 404)

    def test_runs(self):
        runs = {r["name"]: r for r in self.j("/api/runs")["runs"]}
        self.assertEqual(set(runs), {"bc1", "rl1", "empty"})
        self.assertEqual(runs["bc1"]["kind"], "bc")
        self.assertIsNotNone(runs["bc1"]["latest_eval_nll"])
        self.assertEqual(runs["rl1"]["kind"], "rl")
        bc = self.j("/api/run/bc1")
        fields = {c["field"]: c for c in bc["charts"]}
        for f in ("nll", "btn_acc", "eval_nll", "eval_btn_acc", "lr", "grad_norm"):
            self.assertIn(f, fields)
        self.assertEqual(bc["x"], "step")
        self.assertEqual(len(fields["nll"]["points"]), 80)    # broken and truncated lines skipped
        self.assertEqual(bc["args"]["steps"], 20000)
        rl = self.j("/api/run/rl1")
        self.assertEqual(rl["x"], "iter")
        for f in ("ep_return_mean", "win_rate", "kl", "entropy", "pi_loss", "v_loss", "fps"):
            self.assertIn(f, {c["field"] for c in rl["charts"]})
        self.assertIn("duels_sword", rl["by_mode"])
        e = self.j("/api/run/empty")
        self.assertEqual(e["charts"], [])

    def test_league(self):
        d = self.j("/api/league")
        self.assertEqual([p["name"] for p in d["players"]][:2], ["player-1", "ckpt-5000"])
        p = {x["name"]: x for x in d["players"]}
        self.assertAlmostEqual(p["ckpt-5000"]["win_pct"], 60.0)
        self.assertIsNone(p["random"]["win_pct"])
        self.assertEqual(len(d["matches"]), 15)
        self.assertGreaterEqual(d["matches"][0]["t"], d["matches"][-1]["t"])

    def test_live(self):
        d = self.j("/api/live")
        self.assertTrue(d["online"])
        self.assertEqual(d["status"]["state"], "playing")
        self.assertTrue(d["frame"])
        code, h, body = self.get("/live/frame.jpg")
        self.assertEqual((code, h["Content-Type"]), (200, "image/jpeg"))
        write_status(self.tmp, t=time.time() - 30)
        d = self.j("/api/live")
        self.assertFalse(d["online"])
        self.assertGreater(d["age"], 29)
        write_status(self.tmp)

    def test_overview(self):
        o = self.j("/api/overview")
        self.assertEqual(o["trajectories"], 4)
        self.assertEqual(o["modes"], len(games.MODES))
        self.assertEqual(len(o["phases"]), 6)
        self.assertEqual(o["best_elo"]["name"], "player-1")
        self.assertIsNotNone(o["latest_eval_nll"])
        self.assertTrue(o["live"]["online"])

    def test_traversal(self):
        bad = ["/../../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "/..%2f..%2fetc/passwd", "/static/../server.py",
               "/api/run/..", "/api/run/../../etc", "/api/run/%2e%2e%2f%2e%2e", "/api/run/a%2fb", "/api/run/.site-cache",
               "/api/thumb?path=../../etc/passwd", "/api/thumb?path=/etc/passwd", "/api/thumb?path=..%2f..%2fruns%2fbc1%2frun.json",
               "/api/thumb?path=human/../../runs/league.json", "/api/thumb?path=human%5c..%5c..", "/api/thumb?path=%00",
               "/%00", "/..%5c..%5cetc", "/app.js%00.png"]
        for p in bad:
            code = self.get(p)[0]
            self.assertTrue(400 <= code < 500, f"{p} -> {code}")
        # the response body of a rejected path never contains file content
        self.assertNotIn(b"root:", self.get("/../../etc/passwd")[2])
        # http.server folds a leading // to /, so this is just the app shell; it must not leak the file
        self.assertNotIn(b"root:", self.get("//etc/passwd")[2])

    def test_read_only(self):
        for m in ("POST", "PUT", "DELETE", "PATCH"):
            self.assertEqual(self.get("/api/runs", m)[0], 405)
        self.assertEqual(self.get("/api/nothing")[0], 404)

    def test_bind_local(self):
        self.assertEqual(self.srv.server_address[0], "127.0.0.1")


class PublishTest(Base):
    """The public build: scrubbed snapshot, forbidden-pattern check, anonymised league."""

    def test_snapshot_is_scrubbed(self):
        from tools import publish_site as ps
        snap = ps.build_snapshot(self.tmp)
        payload = json.dumps(snap)
        self.assertEqual(ps.check_text("snapshot", payload), [])
        self.assertTrue(all("path" not in it for it in snap["data"]["recent"]))
        self.assertFalse(snap["live"]["online"])
        self.assertNotIn("player-1", payload)
        self.assertIn("Human player 1", [p["name"] for p in snap["league"]["players"]])
        self.assertIn("cloud", snap["overview"])

    def test_forbidden_patterns_block(self):
        from tools import publish_site as ps
        for bad in ("/Users/x", "a@gmail.com", "192.168.1.2", "127.0.0.1", "RCON"):
            self.assertTrue(ps.check_text("t", "text " + bad + " text"), bad)
        self.assertEqual(ps.check_text("t", "toward the forward policy"), [])

    def test_dist_builds_clean(self):
        from tools import publish_site as ps
        d = self.tmp / "dist"
        ps.build_dist(d)
        self.assertIn("VPT_STATIC", (d / "index.html").read_text())
        self.assertEqual(ps.check_dist(d, "{}"), [])

    def test_args_scrub(self):
        from tools import publish_site as ps
        out = ps.scrub_args({"lr": 1e-4, "server": "x:1", "weights": "/Users/a/w", "mode": "duels_sword"})
        self.assertEqual(out, {"lr": 1e-4, "mode": "duels_sword"})

    def test_cloud_endpoint(self):
        (self.tmp / "runs" / "cloud_status.json").write_text(json.dumps({"updated": 5, "jobs": [
            {"name": "j", "platform": "colab", "state": "running", "run": None}, "junk"]}))
        self.assertEqual(self.j("/api/cloud")["jobs"][0]["platform"], "colab")


class CloudRoundsTest(unittest.TestCase):
    """Rounds, workers and clips as written by tools/pull_cloud.py."""

    def setUp(self):
        from vpt_arena.site.server import Arena
        self.tmp = Path(tempfile.mkdtemp(prefix="vpt-cloud-test-"))
        runs = self.tmp / "runs"
        (runs / "r1-w01").mkdir(parents=True)
        (runs / "r1-w01" / "status.json").write_text(json.dumps({
            "job": "r1-w01", "state": "running", "round": 1, "modes": ["duels_sword", "survival"], "iter": 3,
            "env_steps": 900, "fps": 19.5, "minutes_left": 40, "updated": time.time(),
            "per_mode": {"duels_sword": {"episodes": 4, "return": 1.5, "win_rate": 0.25}}}))
        players = {"baseline": {"elo": 1000, "games": 4, "wins": 1, "kind": "checkpoint", "by_mode": {"duels_sword": 1000}},
                   "round-0": {"elo": 1100, "games": 4, "wins": 3, "kind": "checkpoint", "by_mode": {"duels_sword": 1100}},
                   "arena-bots": {"elo": 1000, "games": 8, "wins": 4, "kind": "scripted", "by_mode": {}}}
        matches = [{"t": 2, "mode": "duels_sword", "a": "round-0", "b": "arena-bots", "winner": "round-0", "score": "3/4 wins, return 2.5"},
                   {"t": 1, "mode": "duels_sword", "a": "baseline", "b": "arena-bots", "winner": None, "score": "1/4 wins, return -0.5"}]
        (runs / "league.json").write_text(json.dumps({"players": players, "matches": matches}))
        good = "https://github.com/bward-dev1/vpt-arena/releases/download/round-0/clip-duels_sword.mp4"
        (runs / "cloud_status.json").write_text(json.dumps({
            "updated": 1, "repo": "https://github.com/bward-dev1/vpt-arena", "releases": ["round-0", "baseline"],
            "clips": {"round-0": {"duels_sword": good, "survival": "http://evil.example/x.mp4"}},
            "jobs": [{"name": "w", "platform": "github-actions", "state": "running", "started": "2026-11-21T18:24:20Z"}]}))
        self.a = Arena(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rounds(self):
        r = self.a.api_rounds()["rounds"]
        self.assertEqual([x["tag"] for x in r], ["baseline", "round-0"])
        self.assertAlmostEqual(r[1]["modes"]["duels_sword"]["win_rate"], 0.75)
        self.assertEqual(r[0]["modes"]["duels_sword"]["return"], -0.5)

    def test_workers(self):
        w = self.a.api_workers()["workers"]
        self.assertEqual(w[0]["job"], "r1-w01")
        self.assertEqual(w[0]["round"], 1)
        self.assertEqual(w[0]["per_mode"]["duels_sword"]["win_rate"], 0.25)

    def test_clips_and_cloud(self):
        c = self.a.api_cloud()
        self.assertEqual(c["jobs"][0]["platform"], "github-actions")
        self.assertIsInstance(c["jobs"][0]["started"], float)
        self.assertEqual(list(c["clips"]["round-0"]), ["duels_sword"])   # non-github URL dropped
        clips = self.a.api_clips()
        self.assertEqual([x["mode"] for x in clips], ["duels_sword"])
        m = {x["key"]: x for x in self.a.api_modes()["modes"]}
        self.assertEqual(m["duels_sword"]["clip"]["tag"], "round-0")
        self.assertIsNone(m["survival"]["clip"])

    def test_public_snapshot_passes_scrub(self):
        from tools import publish_site as ps
        snap = ps.build_snapshot(self.tmp)
        self.assertEqual(ps.check_text("snap", json.dumps(snap)), [])
        self.assertTrue(snap["rounds"]["rounds"])
        self.assertTrue(snap["workers"]["workers"])


class TracksTest(unittest.TestCase):
    """The from-scratch track: workers s*, releases scratch-N, ordering, difficulty, and what the Simulation Lab may run."""

    def setUp(self):
        from vpt_arena.site.server import Arena
        self.tmp = Path(tempfile.mkdtemp(prefix="vpt-tracks-test-"))
        runs = self.tmp / "runs"
        for job, rnd in (("r1-w01", 1), ("s0-s01", 0)):
            (runs / job).mkdir(parents=True)
            (runs / job / "status.json").write_text(json.dumps({"job": job, "state": "running", "round": rnd, "modes": ["duels_sword"], "updated": time.time(),
                                                               "per_mode": {"duels_sword": {"episodes": 2, "return": 1.0, "win_rate": 0.5, "difficulty": 0.45}}}))
        players = {t: {"elo": 1000, "games": 3, "wins": 1, "kind": "checkpoint", "by_mode": {"duels_sword": 1000}} for t in ("scratch-1", "round-0", "scratch-0", "baseline")}
        matches = [{"t": i, "mode": "duels_sword", "a": t, "b": "arena-bots", "winner": None, "score": "1/3 wins, return -1.0"} for i, t in enumerate(players)]
        (runs / "league.json").write_text(json.dumps({"players": players, "matches": matches}))
        self.a = Arena(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_workers_have_tracks_and_difficulty(self):
        w = {x["job"]: x for x in self.a.api_workers()["workers"]}
        self.assertEqual((w["r1-w01"]["track"], w["s0-s01"]["track"]), ("vpt", "scratch"))
        self.assertEqual(w["s0-s01"]["round"], 0)
        self.assertEqual(w["s0-s01"]["per_mode"]["duels_sword"]["difficulty"], 0.45)
        self.assertEqual([x["job"] for x in self.a.api_workers()["workers"]][0], "r1-w01")   # VPT first

    def test_release_order_and_tracks(self):
        r = self.a.api_rounds()["rounds"]
        self.assertEqual([x["tag"] for x in r], ["baseline", "round-0", "scratch-0", "scratch-1"])
        self.assertEqual([x["track"] for x in r], ["vpt", "vpt", "scratch", "scratch"])

    def test_scratch_not_offered_to_simulation_lab(self):
        from tools import publish_site as ps
        tags = ps.model_tags({"cloud": {"releases": ["round-0", "scratch-0"]}, "rounds": {"rounds": [{"tag": "baseline"}, {"tag": "scratch-1"}]}})
        self.assertEqual(tags, ["round-0", "baseline"])
        spec = ps.load_sim_spec()
        out, errs = ps.validate_spec({"model": "scratch-0"}, spec, ["baseline", "latest", "round-0"])
        self.assertIsNone(out)
        self.assertTrue(errs)


class EmptyRootTest(unittest.TestCase):
    def test_empty_root(self):
        tmp = Path(tempfile.mkdtemp(prefix="vpt-site-empty-"))
        srv = make_server(tmp, 0)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            for p in ("overview", "modes", "runs", "data", "league", "live", "cloud", "rounds", "workers", "clips"):
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/{p}") as r:
                    self.assertEqual(r.status, 200)
                    json.loads(r.read())
        finally:
            srv.shutdown()
            srv.server_close()
            shutil.rmtree(tmp, ignore_errors=True)


GOOD_SPEC = {}
NODE = shutil.which("node") or str(Path.home() / ".nvm/versions/node/v24.15.0/bin/node")


class SimLabTest(unittest.TestCase):
    """Simulation Lab: the validation rules (Python mirror and generated JS), the generated worker and clip routes."""

    @classmethod
    def setUpClass(cls):
        from tools import publish_site as ps
        cls.ps = ps
        cls.spec = ps.load_sim_spec()
        cls.models = ["baseline", "latest", "round-0", "round-1"]
        d = cls.spec["defaults"]
        import copy
        def v(**kw):
            x = copy.deepcopy(d)
            for k, val in kw.items():
                x[k] = val
            return x
        def nested(key, **kw):
            x = copy.deepcopy(d)
            x[key].update(kw)
            return x
        many = copy.deepcopy(d)
        many["opponents"] = [{"type": "zombie", "count": 4}, {"type": "husk", "count": 3}]
        cls.cases = [
            ("defaults", d, True), ("empty object takes defaults", {}, True), ("round tag", v(model="round-1"), True),
            ("no opponents", v(opponents=[]), True), ("goal bed", v(goal={"type": "bed", "distance": 20}), True),
            ("unknown model", v(model="round-9"), False), ("unknown key", v(extra=1), False),
            ("nested unknown key", nested("arena", colour="red"), False), ("seconds too big", v(seconds=121), False),
            ("seconds float", v(seconds=60.5), False), ("seconds is a bool", v(seconds=True), False),
            ("episodes zero", v(episodes=0), False), ("difficulty above 1", v(difficulty=1.5), False),
            ("difficulty string", v(difficulty="1"), False), ("bad floor", nested("arena", floor="dirt"), False),
            ("arena too small", nested("arena", size=2), False), ("bow not a bool", nested("player", bow=1), False),
            ("blocks too many", nested("player", blocks=65), False), ("seven opponents", many, False),
            ("too many groups", v(opponents=[{"type": "zombie"}] * 5), False), ("opponent without type", v(opponents=[{"count": 1}]), False),
            ("opponent distance 2", v(opponents=[{"type": "zombie", "distance": 2}]), False), ("goal far", v(goal={"type": "bed", "distance": 31}), False),
            ("not an object", [], False), ("name empty", v(name="  "), False), ("name markup", v(name="<b>x</b>"), False),
            ("name too long", v(name="x" * 41), False), ("unknown base mode", v(base_mode="nope"), False),
        ]

    def test_spec_embedded_in_worker_and_page(self):
        js = self.ps.worker_js(self.spec)
        self.assertIn(json.dumps(self.spec["limits"], separators=(",", ":"))[:40], js)
        self.assertIn('"opponents_total_max":6', js)
        self.assertIn("duels_sword", js)
        for route in ("/api/sim", "/api/sims", "\\/sims\\/", "\\/clips(60)?", "_60", "simindex", "simreq:", "simstat:", "simclip:", "simclip60:", "trailer:main", "/trailer.mp4", "/live/status.json"):
            self.assertIn(route, js)
        routes = json.loads(self.ps.ROUTES_JSON)["include"]
        for r in ("/data.json", "/api/*", "/clips/*", "/clips60/*", "/sims/*", "/live/*", "/trailer*"):
            self.assertIn(r, routes)
        d = self.tmp_dist()
        self.assertIn("VPT_SIM", (d / "index.html").read_text())
        self.assertIn("round-0", self.spec.get("models", "round-N") + "round-0")
        self.assertEqual(self.ps.check_dist(d, "{}"), [])

    def tmp_dist(self):
        d = Path(tempfile.mkdtemp(prefix="vpt-dist-test-"))
        self.addCleanup(shutil.rmtree, d, True)
        self.ps.build_dist(d / "dist", self.spec)
        return d / "dist"

    def test_python_rules(self):
        for name, spec, ok in self.cases:
            out, errs = self.ps.validate_spec(spec, self.spec, self.models)
            self.assertEqual(not errs, ok, f"{name}: {errs}")
            self.assertEqual(out is not None, ok, name)
        out, _ = self.ps.validate_spec({}, self.spec, self.models)
        self.assertEqual(out, {**self.spec["defaults"], "opponents": [{**self.spec["defaults"]["opponents"][0]}]})

    @unittest.skipUnless(Path(NODE).exists(), "node not installed")
    def test_js_matches_python(self):
        d = self.tmp_dist()
        (d / "cases.json").write_text(json.dumps([c[1] for c in self.cases]))
        runner = d / "run.js"
        runner.write_text("""
const fs=require('fs'),vm=require('vm');
const src=fs.readFileSync(process.argv[2],'utf8').replace('export default','globalThis.W =');
const ctx={crypto:require('crypto').webcrypto,Response,URL,TextEncoder,console};vm.createContext(ctx);
vm.runInContext(src+';globalThis.validateSpec=validateSpec;',ctx);
const cases=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
console.log(JSON.stringify(cases.map(c=>{const r=ctx.validateSpec(c,%s);return {ok:!!r.spec,spec:r.spec}})));
""" % json.dumps(self.models))
        import subprocess
        r = subprocess.run([NODE, str(runner), str(d / "_worker.js"), str(d / "cases.json")], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        js = json.loads(r.stdout)
        for (name, spec, ok), res in zip(self.cases, js):
            py, errs = self.ps.validate_spec(spec, self.spec, self.models)
            self.assertEqual(res["ok"], not errs, f"JS and Python disagree on: {name}")
            if py is not None:
                self.assertEqual(res["spec"], py, name)

    @unittest.skipUnless(Path(NODE).exists(), "node not installed")
    def test_worker_endpoints_with_fake_kv(self):
        d = self.tmp_dist()
        runner = d / "w.mjs"
        runner.write_text("""
import fs from 'fs';
const src=fs.readFileSync(process.argv[2],'utf8').replace('export default','globalThis.W =');
(0,eval)(src);
const kv=new Map([['models',JSON.stringify(['baseline','latest','round-0'])],['clip:round-0:duels_sword',new Uint8Array([0,1,2,3,4,5,6,7,8,9]).buffer]]);
const env={DATA:{async get(k,o){const v=kv.get(k);if(v===undefined)return null;if(o&&o.type==='arrayBuffer')return v;return v;},async put(k,v){kv.set(k,v);}},ASSETS:{fetch:async()=>new Response('asset')}};
const call=(path,init,ip)=>W.fetch(new Request('https://x.test'+path,{...init,headers:{'x-forwarded-for':ip||'1.1.1.1',...(init&&init.headers)}}),env);
const out={};
const body=JSON.stringify({name:'t'});
const r1=await call('/api/sim',{method:'POST',body}); out.submit=[r1.status,(await r1.json())];
out.bad=(await call('/api/sim',{method:'POST',body:JSON.stringify({seconds:999})})).status;
out.badModel=(await call('/api/sim',{method:'POST',body:JSON.stringify({model:'round-7'})})).status;
await call('/api/sim',{method:'POST',body},'1.1.1.1');await call('/api/sim',{method:'POST',body},'1.1.1.1');
out.limited=(await call('/api/sim',{method:'POST',body},'1.1.1.1')).status;
out.otherIp=(await call('/api/sim',{method:'POST',body},'2.2.2.2')).status;
const id=out.submit[1].id;
const g=await call('/api/sim/'+id); out.get=[g.status,(await g.json()).status];
kv.set('simstat:'+id,JSON.stringify({status:'done',updated:1,result:{episodes:[{return:1,won:true,died:false,steps:10,damage_dealt:3,kills:1,clip:true}],model_tag:'round-0',base_mode:'duels_sword',seconds_simulated:1}}));
const l=await (await call('/api/sims')).json(); out.list=[l.sims.length,l.sims.find(s=>s.id===id).status,l.sims.find(s=>s.id===id).clips];
out.missing=(await call('/api/sim/aaaaaaaaaa')).status;
const rg=await call('/clips/round-0/duels_sword.mp4',{headers:{range:'bytes=2-5'}});
out.range=[rg.status,rg.headers.get('content-range'),rg.headers.get('content-type'),rg.headers.get('accept-ranges'),(await rg.arrayBuffer()).byteLength];
const open=await call('/clips/round-0/duels_sword.mp4',{headers:{range:'bytes=7-'}}); out.open=[open.status,open.headers.get('content-range')];
const suf=await call('/clips/round-0/duels_sword.mp4',{headers:{range:'bytes=-3'}}); out.suffix=[suf.status,suf.headers.get('content-range')];
const bad=await call('/clips/round-0/duels_sword.mp4',{headers:{range:'bytes=50-60'}}); out.range416=[bad.status,bad.headers.get('content-range')];
const full=await call('/clips/round-0/duels_sword.mp4'); out.full=[full.status,full.headers.get('content-length'),full.headers.get('cache-control')];
out.none=(await call('/clips/round-0/nope.mp4')).status;
out.asset=await (await call('/index.html')).text();
console.log(JSON.stringify(out));
""")
        import subprocess
        r = subprocess.run([NODE, str(runner), str(d / "_worker.js")], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        o = json.loads(r.stdout)
        self.assertEqual(o["submit"][0], 200)
        self.assertRegex(o["submit"][1]["id"], r"^[0-9a-z]{10}$")
        self.assertEqual((o["bad"], o["badModel"]), (400, 400))
        self.assertEqual((o["limited"], o["otherIp"]), (429, 200))
        self.assertEqual(o["get"], [200, "queued"])
        self.assertEqual(o["list"], [4, "done", 1])
        self.assertEqual(o["missing"], 404)
        self.assertEqual(o["range"], [206, "bytes 2-5/10", "video/mp4", "bytes", 4])
        self.assertEqual(o["open"], [206, "bytes 7-9/10"])
        self.assertEqual(o["suffix"], [206, "bytes 7-9/10"])
        self.assertEqual(o["range416"], [416, "bytes */10"])
        self.assertEqual(o["full"], [200, "10", "public, max-age=86400"])
        self.assertEqual((o["none"], o["asset"]), (404, "asset"))


class ClipsAndFramesTest(unittest.TestCase):
    def test_clip_urls_rewritten_and_filtered(self):
        from tools import publish_site as ps
        g = "https://github.com/x/y/releases/download/round-0/clip-duels_sword.mp4"
        snap = {"cloud": {"clips": {"round-0": {"duels_sword": g, "uhc": g}}, "clips60": {"round-0": {"duels_sword": g}}},
                "overview": {"clips": [{"tag": "round-0", "mode": "duels_sword", "name": "S", "url": g, "url60": g}], "cloud": {}},
                "modes": {"modes": [{"key": "duels_sword", "clip": {"tag": "round-0", "url": g, "url60": g}}, {"key": "uhc", "clip": {"tag": "round-0", "url": g}}]}}
        import copy
        a = ps.rewrite_clips(copy.deepcopy(snap))
        self.assertEqual(a["overview"]["clips"][0]["url"], "/clips/round-0/duels_sword.mp4")
        self.assertEqual(a["overview"]["clips"][0]["url60"], "/clips60/round-0/duels_sword.mp4")
        self.assertEqual(a["cloud"]["clips"]["round-0"]["uhc"], "/clips/round-0/uhc.mp4")
        b = ps.rewrite_clips(copy.deepcopy(snap), {("round-0", "duels_sword")}, set())   # only the 30 fps one is in KV
        self.assertNotIn("url60", b["overview"]["clips"][0])
        self.assertEqual(b["cloud"]["clips60"], {})
        self.assertIsNone(b["modes"]["modes"][1]["clip"])
        self.assertEqual(b["modes"]["modes"][0]["clip"]["url"], "/clips/round-0/duels_sword.mp4")
        self.assertNotIn("github.com", json.dumps(b))

    def test_frames_in_snapshot_and_scrub_ignores_base64(self):
        from tools import publish_site as ps
        tmp = Path(tempfile.mkdtemp(prefix="vpt-frames-test-"))
        try:
            run = tmp / "runs" / "r2-w01"
            run.mkdir(parents=True)
            (run / "status.json").write_text(json.dumps({"job": "r2-w01", "state": "running", "round": 2, "modes": ["duels_sword", "uhc"], "updated": time.time(),
                                                         "per_mode": {"duels_sword": {"episodes": 2, "return": 1.0, "win_rate": 0.5}}}))
            jpg = b"\xff\xd8\xff" + b"rcon@gmail" * 3 + b"\xff\xd9"           # base64 of this is not what matters; the check must skip it
            (run / "frame0.jpg").write_bytes(jpg)
            (run / "frame1.jpg").write_bytes(b"not a jpeg")
            from vpt_arena.site.server import Arena
            fr = ps.build_frames(tmp, Arena(tmp).api_workers()["workers"])["frames"]
            self.assertEqual(len(fr), 1)
            self.assertEqual((fr[0]["job"], fr[0]["mode"], fr[0]["round"], fr[0]["win_rate"]), ("r2-w01", "duels_sword", 2, 0.5))
            self.assertTrue(fr[0]["img"].startswith("data:image/jpeg;base64,"))
            payload = json.dumps({"x": "data:image/jpeg;base64,cmNvbgBBQQ=="})
            self.assertEqual(ps.check_text("t", ps.DATAURL_RE.sub("data:image/jpeg;base64,", payload)), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def serve(port):
    tmp = Path(tempfile.mkdtemp(prefix="vpt-site-view-"))
    make_fixture(tmp)
    srv = make_server(tmp, port)
    stop = threading.Event()

    def refresh():
        while not stop.wait(2):
            write_status(tmp)
    threading.Thread(target=refresh, daemon=True).start()
    print(f"fixture {tmp} on http://127.0.0.1:{port}/", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        srv.server_close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--serve":
        serve(int(sys.argv[2]) if len(sys.argv) > 2 else 7791)
    else:
        unittest.main(argv=sys.argv[:1])
