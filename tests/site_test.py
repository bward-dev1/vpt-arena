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


class EmptyRootTest(unittest.TestCase):
    def test_empty_root(self):
        tmp = Path(tempfile.mkdtemp(prefix="vpt-site-empty-"))
        srv = make_server(tmp, 0)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            for p in ("overview", "modes", "runs", "data", "league", "live"):
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/{p}") as r:
                    self.assertEqual(r.status, 200)
                    json.loads(r.read())
        finally:
            srv.shutdown()
            srv.server_close()
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
