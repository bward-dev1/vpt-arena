"""Read-only local web dashboard for VPT Arena (stdlib only).

Serves static pages from ./static and JSON built from files under --root.
It never starts processes and never writes outside <root>/runs/.site-cache/.
"""
import argparse
import hashlib
import json
import mimetypes
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
DEFAULT_ROOT = HERE.parent.parent
FPS = 20
SOURCES = ("human", "idm", "contractor", "other")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_POINTS = 600
OFFLINE_AFTER = 10.0

BC_FIELDS = ["nll", "btn_acc", "eval_nll", "eval_btn_acc", "lr", "grad_norm", "kl", "sec"]
RL_FIELDS = ["ep_return_mean", "win_rate", "kl", "entropy", "pi_loss", "v_loss", "fps", "ep_len_mean", "env_steps"]


# --------------------------------------------------------------------------- helpers

def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def read_jsonl(path):
    rows = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
    except OSError:
        pass
    return rows


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")


def downsample(rows, n=MAX_POINTS):
    if len(rows) <= n:
        return rows
    step = (len(rows) - 1) / (n - 1)
    return [rows[round(i * step)] for i in range(n)]


def safe_join(base, rel):
    """Resolve rel under base; return None if it escapes or contains odd characters."""
    if not rel or "\x00" in rel or "\\" in rel:
        return None
    try:
        base = base.resolve()
        p = (base / rel).resolve()
        p.relative_to(base)
    except (ValueError, OSError):
        return None
    return p


def _clean(o):
    if isinstance(o, float) and (o != o or abs(o) == float("inf")):
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def load_modes():
    sys.path.insert(0, str(HERE.parent.parent))
    from vpt_arena import games
    return [{"id": m.id, "key": m.key, "name": m.name, "ruleset": m.ruleset, "team_size": m.team_size,
             "summary": m.summary, "events": dict(m.events)} for m in games.MODES]


# --------------------------------------------------------------------------- data model

class Arena:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.modes = load_modes()
        self.mode_keys = {m["key"] for m in self.modes}
        self._lines = {}      # (path, mtime_ns, size) -> line count
        self._scan = None
        self._scan_t = 0.0
        self._lock = threading.Lock()

    # -- data inventory
    def _count_lines(self, p):
        try:
            st = p.stat()
        except OSError:
            return 0
        key = (str(p), st.st_mtime_ns, st.st_size)
        if key in self._lines:
            return self._lines[key]
        n = 0
        try:
            with open(p, "rb") as f:
                for line in f:
                    if line.strip():
                        n += 1
        except OSError:
            pass
        self._lines[key] = n
        return n

    def scan_data(self):
        with self._lock:
            if self._scan is not None and time.time() - self._scan_t < 5:
                return self._scan
            data_dir = self.root / "data"
            items = []
            if data_dir.is_dir():
                try:
                    mp4s = sorted(data_dir.rglob("*.mp4"))
                except OSError:
                    mp4s = []
                for mp4 in mp4s:
                    if mp4.name.startswith(".") or not mp4.is_file():
                        continue
                    jl = mp4.with_suffix(".jsonl")
                    if not jl.is_file():
                        continue
                    meta = read_json(mp4.with_suffix(".meta.json"), {})
                    if not isinstance(meta, dict):
                        meta = {}
                    has_meta = bool(meta)
                    mode = meta.get("mode") if isinstance(meta.get("mode"), str) else "survival"
                    src = meta.get("source") if has_meta else "contractor"
                    if src not in SOURCES[:3]:
                        src = "other"
                    lines = self._count_lines(jl)
                    try:
                        mt = mp4.stat().st_mtime
                    except OSError:
                        mt = 0
                    items.append({
                        "path": mp4.relative_to(data_dir).as_posix(), "mode": mode, "source": src,
                        "ruleset": meta.get("ruleset") if isinstance(meta.get("ruleset"), str) else None,
                        "team_size": meta.get("team_size") if num(meta.get("team_size")) else None,
                        "weight": meta.get("weight") if num(meta.get("weight")) else None,
                        "loss_weight": meta.get("loss_weight") if num(meta.get("loss_weight")) else None,
                        "frames": lines, "hours": lines / FPS / 3600.0, "mtime": mt,
                    })
            self._scan = items
            self._scan_t = time.time()
            return items

    def api_data(self):
        items = self.scan_data()
        by_source = {s: {"trajectories": 0, "hours": 0.0} for s in SOURCES}
        by_mode = {}
        for it in items:
            for tbl, k in ((by_source, it["source"]), (by_mode, it["mode"])):
                e = tbl.setdefault(k, {"trajectories": 0, "hours": 0.0})
                e["trajectories"] += 1
                e["hours"] += it["hours"]
        recent = sorted(items, key=lambda x: x["mtime"], reverse=True)[:48]
        names = {m["key"]: m["name"] for m in self.modes}
        for it in recent:
            it["mode_name"] = names.get(it["mode"], it["mode"])
        return {"total": {"trajectories": len(items), "hours": sum(i["hours"] for i in items)},
                "by_source": by_source, "by_mode": by_mode, "recent": recent}

    # -- thumbnails
    def thumb(self, rel):
        data_dir = self.root / "data"
        p = safe_join(data_dir, rel)
        if p is None or p.suffix.lower() != ".mp4" or not p.is_file():
            return None, 404
        try:
            import cv2
        except ImportError:
            return None, 503
        st = p.stat()
        h = hashlib.sha1(f"{p}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest()
        cache = self.root / "runs" / ".site-cache"
        cp = cache / f"{h}.jpg"
        if cp.is_file():
            try:
                return cp.read_bytes(), 200
            except OSError:
                pass
        cap = cv2.VideoCapture(str(p))
        try:
            ok, frame = cap.read()
        finally:
            cap.release()
        if not ok or frame is None:
            return None, 404
        hh, ww = frame.shape[:2]
        w = 224
        frame = cv2.resize(frame, (w, max(1, round(hh * w / ww))), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            return None, 404
        data = buf.tobytes()
        try:
            cache.mkdir(parents=True, exist_ok=True)
            cp.write_bytes(data)
        except OSError:
            pass
        return data, 200

    # -- runs
    def run_dirs(self):
        d = self.root / "runs"
        out = []
        if d.is_dir():
            for p in d.iterdir():
                if p.is_dir() and not p.name.startswith(".") and NAME_RE.match(p.name):
                    out.append(p)
        return out

    def _run_logs(self, p):
        bc = read_jsonl(p / "log.jsonl")
        rl = read_jsonl(p / "rl_log.jsonl")
        return bc, rl

    def run_summary(self, p):
        info = read_json(p / "run.json", {})
        if not isinstance(info, dict):
            info = {}
        bc, rl = self._run_logs(p)
        kind = info.get("kind") if info.get("kind") in ("bc", "rl") else ("rl" if rl and not bc else "bc")
        rows = rl if kind == "rl" else bc
        last = rows[-1] if rows else {}
        updated = 0.0
        for f in ("log.jsonl", "rl_log.jsonl", "run.json"):
            try:
                updated = max(updated, (p / f).stat().st_mtime)
            except OSError:
                pass
        s = {"name": p.name, "kind": kind, "arch": info.get("arch"), "started": info.get("started"),
             "updated": updated, "points": len(rows), "last": {k: v for k, v in last.items() if num(v)}}
        if kind == "bc":
            ev = [r["eval_nll"] for r in bc if num(r.get("eval_nll"))]
            s["latest_eval_nll"] = ev[-1] if ev else None
            s["best_eval_nll"] = min(ev) if ev else None
        return s

    def api_runs(self):
        runs = [self.run_summary(p) for p in self.run_dirs()]
        runs.sort(key=lambda r: r["updated"], reverse=True)
        return {"runs": runs}

    def api_run(self, name):
        if not NAME_RE.match(name or ""):
            return None
        p = safe_join(self.root / "runs", name)
        if p is None or not p.is_dir():
            return None
        info = read_json(p / "run.json", {})
        if not isinstance(info, dict):
            info = {}
        s = self.run_summary(p)
        bc, rl = self._run_logs(p)
        xkey = "iter" if s["kind"] == "rl" else "step"
        rows = rl if s["kind"] == "rl" else bc
        wanted = RL_FIELDS if s["kind"] == "rl" else BC_FIELDS
        extra = []
        for r in rows:
            for k, v in r.items():
                if num(v) and k != xkey and k not in wanted and k not in extra and k != "by_mode":
                    extra.append(k)
        charts = []
        for f in wanted + extra:
            pts = [[r[xkey] if num(r.get(xkey)) else i, r[f]] for i, r in enumerate(rows) if num(r.get(f))]
            if pts:
                charts.append({"field": f, "points": downsample(pts)})
        by_mode = {}
        if s["kind"] == "rl" and rl:
            for r in reversed(rl):
                if isinstance(r.get("by_mode"), dict):
                    by_mode = {k: v for k, v in r["by_mode"].items() if num(v)}
                    break
        mode_curves = {}
        if s["kind"] == "rl":
            for i, r in enumerate(rl):
                bm = r.get("by_mode")
                if isinstance(bm, dict):
                    x = r[xkey] if num(r.get(xkey)) else i
                    for k, v in bm.items():
                        if num(v):
                            mode_curves.setdefault(str(k), []).append([x, v])
            mode_curves = {k: downsample(v) for k, v in mode_curves.items()}
        return {"summary": s, "x": xkey, "charts": charts, "by_mode": by_mode, "mode_curves": mode_curves,
                "args": info.get("args") if isinstance(info.get("args"), dict) else {},
                "started": info.get("started"), "arch": info.get("arch")}

    # -- league
    def league(self):
        d = read_json(self.root / "runs" / "league.json", {})
        if not isinstance(d, dict):
            d = {}
        players_raw = d.get("players") if isinstance(d.get("players"), dict) else {}
        players = []
        for name, p in players_raw.items():
            if not isinstance(p, dict) or not num(p.get("elo")):
                continue
            games = int(p["games"]) if num(p.get("games")) else 0
            wins = int(p["wins"]) if num(p.get("wins")) else 0
            bm = p.get("by_mode") if isinstance(p.get("by_mode"), dict) else {}
            players.append({"name": str(name), "kind": p.get("kind") if isinstance(p.get("kind"), str) else "other",
                            "elo": p["elo"], "games": games, "wins": wins,
                            "win_pct": (100.0 * wins / games) if games else None,
                            "by_mode": {k: v for k, v in bm.items() if num(v)}})
        matches = []
        for m in (d.get("matches") if isinstance(d.get("matches"), list) else []):
            if isinstance(m, dict):
                matches.append({"t": m.get("t") if num(m.get("t")) else None, "mode": m.get("mode"),
                                "a": m.get("a"), "b": m.get("b"), "winner": m.get("winner"),
                                "score": m.get("score")})
        matches.sort(key=lambda m: m["t"] or 0, reverse=True)
        return players, matches

    def api_league(self):
        players, matches = self.league()
        players.sort(key=lambda p: p["elo"], reverse=True)
        return {"players": players, "matches": matches[:200], "modes": [m["key"] for m in self.modes]}

    # -- live
    def api_live(self):
        st = read_json(self.root / "live" / "status.json", None)
        now = time.time()
        if not isinstance(st, dict):
            return {"online": False, "age": None, "status": None, "frame": (self.root / "live" / "frame.jpg").is_file(), "now": now}
        upd = st.get("updated")
        age = now - upd if num(upd) else None
        return {"online": age is not None and age <= OFFLINE_AFTER, "age": age, "status": st,
                "frame": (self.root / "live" / "frame.jpg").is_file(), "now": now}

    # -- cloud jobs (runs/cloud_status.json, written by whatever launches Colab/Kaggle jobs)
    def api_cloud(self):
        d = read_json(self.root / "runs" / "cloud_status.json", None)
        if not isinstance(d, dict):
            return {"updated": None, "jobs": []}
        jobs = []
        for j in (d.get("jobs") if isinstance(d.get("jobs"), list) else []):
            if not isinstance(j, dict):
                continue
            st = j.get("state") if j.get("state") in ("queued", "running", "finished", "failed", "stopped") else "queued"
            pf = j.get("platform") if j.get("platform") in ("colab", "kaggle", "local") else "local"
            jobs.append({"name": str(j.get("name", "")), "platform": pf, "hardware": str(j.get("hardware") or ""),
                         "state": st, "started": j.get("started") if num(j.get("started")) else None,
                         "updated": j.get("updated") if num(j.get("updated")) else None,
                         "progress": str(j.get("progress") or ""),
                         "run": j.get("run") if isinstance(j.get("run"), str) and NAME_RE.match(j["run"].split("/")[-1]) else None})
        return {"updated": d.get("updated") if num(d.get("updated")) else None, "jobs": jobs}

    # -- modes + overview
    def api_modes(self):
        data = self.api_data()["by_mode"]
        players, _ = self.league()
        out = []
        for m in self.modes:
            best = None
            for p in players:
                e = p["by_mode"].get(m["key"])
                if e is not None and (best is None or e > best["elo"]):
                    best = {"name": p["name"], "elo": e}
            d = data.get(m["key"], {"trajectories": 0, "hours": 0.0})
            out.append({**m, "trajectories": d["trajectories"], "hours": d["hours"], "best_elo": best})
        return {"modes": out}

    def api_overview(self):
        data = self.api_data()
        runs = self.api_runs()["runs"]
        players, _ = self.league()
        live = self.api_live()
        bc = [r for r in runs if r["kind"] == "bc"]
        rl = [r for r in runs if r["kind"] == "rl"]
        latest_eval = next((r["latest_eval_nll"] for r in bc if r.get("latest_eval_nll") is not None), None)
        best_elo = max(players, key=lambda p: p["elo"]) if players else None
        weights = []
        wd = self.root / "weights"
        if wd.is_dir():
            weights = sorted(p.name for p in wd.glob("*.weights"))
        src = data["by_source"]
        phases = [
            {"phase": 0, "tested": "Weights verified; the real 1x model checked on contractor data.", "name": "VPT foundation", "what": "VPT foundation 2x, or the RL early-game 2x for survival",
             "status": f"{len(weights)} weight file(s) in weights/" if weights else "no weight files in weights/",
             "state": "done" if weights else "todo"},
            {"phase": 1, "tested": "Recorder written, tested with fake input and capture backends.", "name": "Record own games", "what": "Record the Minecraft window plus exact keys and mouse to data/human/",
             "status": f"{src['human']['trajectories']} trajectory(ies), {src['human']['hours']:.2f} h" if src["human"]["trajectories"] else "no human data",
             "state": "done" if src["human"]["trajectories"] else "todo"},
            {"phase": 2, "tested": "Labeller tested on synthetic video.", "name": "IDM labelling", "what": "Label PvP videos with VPT's inverse dynamics model, saved to data/idm/",
             "status": f"{src['idm']['trajectories']} trajectory(ies), {src['idm']['hours']:.2f} h" if src["idm"]["trajectories"] else "no IDM data",
             "state": "done" if src["idm"]["trajectories"] else "todo"},
            {"phase": 3, "tested": "Tested on synthetic data and one real clip.", "name": "Behavior cloning", "what": "Sequence BC over all modes, with contractor data mixed in",
             "status": (f"{len(bc)} run(s), latest eval NLL {latest_eval:.3f}" if latest_eval is not None else f"{len(bc)} run(s)") if bc else "no BC runs",
             "state": "done" if bc else "todo"},
            {"phase": 4, "tested": "Live client written, tested with fakes; not run in a real game.", "name": "Live client", "what": "Capture the game window, act through keyboard and mouse events on your own server",
             "status": ("agent " + str(live["status"].get("state", "?")) if live["online"] else "offline") if live["status"] else "no live status file",
             "state": "active" if live["online"] else ("done" if live["status"] else "todo")},
            {"phase": 5, "tested": "Tested on a toy env; LiveEnv and datapack tested with fakes.", "name": "Reinforcement learning", "what": "RL on the server: reward from game events, KL to the BC policy",
             "status": f"{len(rl)} run(s)" if rl else "no RL runs", "state": "done" if rl else "todo"},
        ]
        return {"hours": data["total"]["hours"], "trajectories": data["total"]["trajectories"],
                "by_source": src, "latest_eval_nll": latest_eval, "bc_runs": len(bc), "rl_runs": len(rl),
                "best_elo": {"name": best_elo["name"], "elo": best_elo["elo"]} if best_elo else None,
                "live": {"online": live["online"], "state": live["status"].get("state") if live["status"] else None,
                         "age": live["age"]},
                "modes": len(self.modes), "phases": phases, "cloud": self.api_cloud()}


# --------------------------------------------------------------------------- http

class Handler(BaseHTTPRequestHandler):
    server_version = "VPTArenaSite/1"
    arena = None

    def log_message(self, fmt, *args):
        if getattr(self.server, "verbose", False):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body, ctype, cache="no-store"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200):
        try:
            body = json.dumps(obj, allow_nan=False)
        except ValueError:      # NaN/Infinity from a hand-edited file
            body = json.dumps(_clean(obj), allow_nan=False)
        self._send(code, body.encode(), "application/json; charset=utf-8")

    def _err(self, code, msg):
        self._json({"error": msg}, code)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            self._route()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # keep the server alive on any bad file
            try:
                self._err(500, f"{type(e).__name__}")
            except Exception:
                pass

    def do_POST(self):
        self._err(405, "read-only")

    do_PUT = do_DELETE = do_PATCH = do_POST

    def _route(self):
        u = urlparse("http://x" + self.path) if self.path.startswith("/") else urlparse(self.path)
        path = unquote(u.path)
        q = parse_qs(u.query)
        a = self.arena
        if "\x00" in path or "\\" in path or path.startswith("//") or ".." in path.split("/"):
            return self._err(400, "bad path")
        if path.startswith("/api/"):
            ep = path[5:].strip("/")
            if ep == "overview":
                return self._json(a.api_overview())
            if ep == "modes":
                return self._json(a.api_modes())
            if ep == "runs":
                return self._json(a.api_runs())
            if ep.startswith("run/"):
                r = a.api_run(ep[4:])
                return self._json(r) if r is not None else self._err(404, "no such run")
            if ep == "data":
                return self._json(a.api_data())
            if ep == "league":
                return self._json(a.api_league())
            if ep == "live":
                return self._json(a.api_live())
            if ep == "cloud":
                return self._json(a.api_cloud())
            if ep == "thumb":
                rel = (q.get("path") or [""])[0]
                data, code = a.thumb(rel)
                if data is None:
                    return self._err(code, "no thumbnail")
                return self._send(200, data, "image/jpeg", cache="max-age=3600")
            return self._err(404, "unknown endpoint")
        if path == "/live/frame.jpg":
            p = a.root / "live" / "frame.jpg"
            try:
                data = p.read_bytes()
            except OSError:
                return self._err(404, "no frame")
            return self._send(200, data, "image/jpeg")
        # static files
        if path in ("", "/"):
            path = "/index.html"
        p = safe_join(STATIC, path.lstrip("/"))
        if p is None:
            return self._err(400, "bad path")
        if not p.is_file():
            if "." not in Path(path).name:      # client-side routes fall back to the app shell
                p = STATIC / "index.html"
            else:
                return self._err(404, "not found")
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8" if "charset" not in ctype else ""
        self._send(200, p.read_bytes(), ctype)


def make_server(root, port=7790, host="127.0.0.1"):
    arena = Arena(root)
    handler = type("BoundHandler", (Handler,), {"arena": arena})
    srv = ThreadingHTTPServer((host, port), handler)
    srv.daemon_threads = True
    return srv


def main(argv=None):
    ap = argparse.ArgumentParser(description="VPT Arena local dashboard (read-only)")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="repo root holding data/, runs/, live/")
    ap.add_argument("--port", type=int, default=7790)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    srv = make_server(args.root, args.port)
    srv.verbose = args.verbose
    print(f"VPT Arena site: http://127.0.0.1:{args.port}/  (root {Path(args.root).resolve()})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
