#!/usr/bin/env python3
"""Publish the VPT Arena dashboard as a public static site on Cloudflare Pages.

Run with the stdlib only:   ~/homebrew/bin/python3 tools/publish_site.py [--root .]

What it does
  1. Builds dist/ (gitignored): the front end from vpt_arena/site/static plus a worker
     (_worker.js) that serves /data.json from a Workers KV value.
  2. Builds one scrubbed data snapshot from the repo's runs/, data/ and weights/ using the
     same Arena functions the local server uses. No names, paths, servers or frames go in.
  3. Fails if any scrubbed pattern shows up in the output (see FORBIDDEN).
  4. Writes the snapshot to KV (one key; skipped when unchanged, refreshed at least hourly).
  5. Deploys the Pages project only when the front-end files changed (content hash).

Credentials come from CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_AUTH_EMAIL and
CLOUDFLARE_GLOBAL_API_KEY. They are only sent as request headers, never printed or stored.

Options: --build-only (no network), --force (redeploy and rewrite KV), --project NAME.
"""
import argparse
import base64
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from vpt_arena.site import server as srv  # noqa: E402

STATIC = srv.STATIC
API = "https://api.cloudflare.com/client/v4"
PROJECT = "vpt-arena"
KV_TITLE = "vpt-arena-data"
KV_KEY = "data"
COMPAT_DATE = "2025-01-01"
MAX_RUNS = 12
PUBLIC_POINTS = 200
KV_REFRESH_S = 3600

# Anything matching these in the built files or the snapshot fails the publish.
FORBIDDEN = [
    (re.compile(r"/Users/"), "/Users/ path"),
    (re.compile(r"@gmail", re.I), "gmail address"),
    (re.compile(r"@outlook", re.I), "outlook address"),
    (re.compile(r"192\.168\."), "LAN IP"),
    (re.compile(r"127\.0\.0\.1"), "loopback IP"),
    (re.compile(r"rcon", re.I), "rcon"),
    (re.compile(r"\blocalhost\b", re.I), "localhost"),
]
# Personal words (names, account names) live in a gitignored local file so the public repo doesn't list them:
# configs/scrub.local.json = {"words": ["...", ...]}  (matched as whole words, case-insensitive)
_LOCAL = Path(__file__).resolve().parent.parent / "configs" / "scrub.local.json"
if _LOCAL.exists():
    for _w in json.loads(_LOCAL.read_text()).get("words", []):
        FORBIDDEN.append((re.compile(r"\b" + re.escape(_w) + r"\b", re.I), "a private word from scrub.local.json"))
TEXT_EXT = {".html", ".js", ".css", ".json", ".txt", ".svg", ".md"}

WORKER_JS = """// Serves /data.json from Workers KV; everything else is the static site.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/data.json") {
      const body = await env.DATA.get("%s", { cacheTtl: 60 });
      const h = { "content-type": "application/json; charset=utf-8", "x-content-type-options": "nosniff",
                  "access-control-allow-origin": "*" };
      if (body === null) return new Response('{"error":"no data published yet"}', { status: 404, headers: { ...h, "cache-control": "no-store" } });
      return new Response(body, { headers: { ...h, "cache-control": "public, max-age=60" } });
    }
    return env.ASSETS.fetch(request);
  },
};
""" % KV_KEY

ROUTES_JSON = json.dumps({"version": 1, "include": ["/data.json"], "exclude": []})


# --------------------------------------------------------------------------- snapshot

class PublicArena(srv.Arena):
    """Arena with the live view switched off: its status can name a server and frames show players."""

    def api_live(self):
        return {"online": False, "age": None, "status": None, "frame": False, "now": time.time()}


BAD_ARG_KEY = re.compile(r"server|host|user|player|pass|rcon|token|secret|email|addr|port|log|cookie|key", re.I)


def _safe_arg(v):
    if isinstance(v, str):
        if v.startswith(("/", "~")) or "@" in v or "\\" in v or re.search(r"\d+\.\d+\.\d+\.\d+", v):
            return None
        return v
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    if isinstance(v, list):
        out = [_safe_arg(x) for x in v]
        return None if any(x is None and y is not None for x, y in zip(out, v)) else out
    return None


def scrub_args(args):
    out = {}
    for k, v in (args or {}).items():
        if BAD_ARG_KEY.search(str(k)):
            continue
        sv = _safe_arg(v)
        if sv is not None or v is None:
            out[k] = sv
    return out


def thin(points, n=PUBLIC_POINTS):
    return srv.downsample(points, n)


def public_run(detail):
    detail = dict(detail)
    detail["args"] = scrub_args(detail.get("args"))
    detail["charts"] = [{"field": c["field"], "points": thin(c["points"])} for c in detail.get("charts", [])]
    detail["mode_curves"] = {k: thin(v) for k, v in (detail.get("mode_curves") or {}).items()}
    return detail


def anonymize_league(lg):
    names = {}
    n = 0
    for p in lg["players"]:
        if p["kind"] in ("human", "other"):
            n += 1
            names[p["name"]] = f"Human player {n}"
    known = {p["name"] for p in lg["players"]}

    def nm(x):
        if x is None or x == "":
            return x
        if x in names:
            return names[x]
        if x in known or x in ("a", "b", "draw"):
            return x
        names[x] = f"Player {len(names) + 1}"
        return names[x]

    for p in lg["players"]:
        p["name"] = nm(p["name"])
    for m in lg["matches"]:
        for k in ("a", "b", "winner"):
            m[k] = nm(m[k])
    lg["_map"] = dict(names)
    return lg


def build_snapshot(root):
    a = PublicArena(root)
    runs = a.api_runs()["runs"][:MAX_RUNS]
    data = a.api_data()
    for it in data["recent"]:
        it.pop("path", None)
    overview = a.api_overview()
    overview["live"] = {"online": False, "state": None, "age": None}
    league = anonymize_league(a.api_league())
    names = league.pop("_map")
    modes = a.api_modes()
    for holder in [overview] + modes["modes"]:
        be = holder.get("best_elo")
        if be and be["name"] in names:
            be["name"] = names[be["name"]]
    return {
        "generated": time.time(),
        "overview": overview,
        "modes": modes,
        "runs": {"runs": runs},
        "run": {r["name"]: public_run(a.api_run(r["name"])) for r in runs if a.api_run(r["name"])},
        "data": data,
        "league": league,
        "cloud": a.api_cloud(),
        "live": {"online": False, "age": None, "status": None, "frame": False, "now": time.time()},
    }


def snapshot_hash(snap):
    s = {k: v for k, v in snap.items() if k not in ("generated", "live")}
    # drop the volatile ages that Arena computes against the clock
    s["overview"] = {k: v for k, v in s["overview"].items() if k != "live"}
    return hashlib.sha256(json.dumps(s, sort_keys=True, default=str).encode()).hexdigest()


# --------------------------------------------------------------------------- dist

def check_text(label, text):
    bad = []
    for rx, what in FORBIDDEN:
        m = rx.search(text)
        if m:
            ctx = text[max(0, m.start() - 30): m.end() + 30].replace("\n", " ")
            bad.append(f"{label}: {what}: ...{ctx}...")
    return bad


def check_dist(dist, payload):
    bad = []
    for p in sorted(Path(dist).rglob("*")):
        if p.is_file() and p.suffix.lower() in TEXT_EXT:
            bad += check_text(str(p.relative_to(dist)), p.read_text("utf-8", errors="replace"))
    bad += check_text("data.json", payload)
    return bad


def build_dist(dist):
    dist = Path(dist)
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)
    for p in STATIC.iterdir():
        if p.is_file():
            shutil.copy2(p, dist / p.name)
    idx = (dist / "index.html").read_text("utf-8")
    marker = '<script src="/app.js"></script>'
    if marker not in idx:
        raise SystemExit("index.html has no app.js script tag to mark static mode")
    idx = idx.replace(marker, '<script>window.VPT_STATIC=true</script>\n' + marker)
    (dist / "index.html").write_text(idx, "utf-8")
    (dist / "_worker.js").write_text(WORKER_JS, "utf-8")
    (dist / "_routes.json").write_text(ROUTES_JSON, "utf-8")


def asset_files(dist):
    """Files that go in the Pages manifest (everything except the worker and routes)."""
    return {"/" + p.relative_to(dist).as_posix(): p for p in sorted(Path(dist).rglob("*"))
            if p.is_file() and p.name not in ("_worker.js", "_routes.json", ".DS_Store")}


def frontend_hash(dist):
    h = hashlib.sha256()
    for p in sorted(Path(dist).rglob("*")):
        if p.is_file():
            h.update(p.relative_to(dist).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


# --------------------------------------------------------------------------- Cloudflare

class CF:
    def __init__(self):
        try:
            self.acct = os.environ["CLOUDFLARE_ACCOUNT_ID"]
            self._h = {"X-Auth-Email": os.environ["CLOUDFLARE_AUTH_EMAIL"],
                       "X-Auth-Key": os.environ["CLOUDFLARE_GLOBAL_API_KEY"]}
        except KeyError as e:
            raise SystemExit(f"missing environment variable {e.args[0]}")

    def call(self, method, path, body=None, raw=None, ctype=None, headers=None, url=None):
        h = dict(headers if headers is not None else self._h)
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        elif ctype:
            h["Content-Type"] = ctype
        req = urllib.request.Request(url or (API + path), data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                txt = r.read().decode()
        except urllib.error.HTTPError as e:
            txt = e.read().decode(errors="replace")
            try:
                errs = json.loads(txt).get("errors")
            except ValueError:
                errs = txt[:200]
            raise RuntimeError(f"{method} {path.split('?')[0]} -> HTTP {e.code}: {errs}")
        out = json.loads(txt) if txt else {}
        if isinstance(out, dict) and out.get("success") is False:
            raise RuntimeError(f"{method} {path} failed: {out.get('errors')}")
        return out.get("result") if isinstance(out, dict) and "result" in out else out

    def jwt_call(self, method, path, jwt, body):
        return self.call(method, path, body=body, headers={"Authorization": "Bearer " + jwt})

    # project + KV
    def ensure_project(self, name):
        base = f"/accounts/{self.acct}/pages/projects"
        for cand in [name, name + "-site", name + "-dash"]:
            try:
                return self.call("GET", f"{base}/{cand}")
            except RuntimeError as e:
                if "HTTP 404" not in str(e) and "8000007" not in str(e):
                    raise
            try:
                return self.call("POST", base, {"name": cand, "production_branch": "main"})
            except RuntimeError as e:
                print(f"could not create project {cand}: {e}")
        raise SystemExit("no usable Pages project name")

    def ensure_kv(self):
        base = f"/accounts/{self.acct}/storage/kv/namespaces"
        for ns in self.call("GET", base + "?per_page=100") or []:
            if ns.get("title") == KV_TITLE:
                return ns["id"]
        return self.call("POST", base, {"title": KV_TITLE})["id"]

    def bind_kv(self, project, ns_id):
        cfg = {"kv_namespaces": {"DATA": {"namespace_id": ns_id}}, "compatibility_date": COMPAT_DATE}
        self.call("PATCH", f"/accounts/{self.acct}/pages/projects/{project}",
                  {"deployment_configs": {"production": cfg, "preview": cfg}})

    def kv_put(self, ns_id, key, text):
        self.call("PUT", f"/accounts/{self.acct}/storage/kv/namespaces/{ns_id}/values/{key}",
                  raw=text.encode(), ctype="application/json")

    # deployment (Pages direct upload)
    def deploy(self, project, dist, label):
        files = asset_files(dist)
        info = {}
        for path, p in files.items():
            b = base64.b64encode(p.read_bytes()).decode()
            ext = p.suffix.lstrip(".")
            key = hashlib.sha256((b + ext).encode()).hexdigest()[:32]
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            info[path] = (key, b, ctype)
        tok = self.call("GET", f"/accounts/{self.acct}/pages/projects/{project}/upload-token")["jwt"]
        hashes = [v[0] for v in info.values()]
        missing = self.jwt_call("POST", "/pages/assets/check-missing", tok, {"hashes": hashes}) or []
        todo = [{"key": k, "value": b, "metadata": {"contentType": c}, "base64": True}
                for k, b, c in info.values() if k in set(missing)]
        if todo:
            self.jwt_call("POST", "/pages/assets/upload", tok, todo)
        self.jwt_call("POST", "/pages/assets/upsert-hashes", tok, {"hashes": hashes})
        manifest = {path: v[0] for path, v in info.items()}
        boundary = "----vpt" + uuid.uuid4().hex
        parts = []

        def field(name, value, filename=None, ctype=None):
            disp = f'form-data; name="{name}"' + (f'; filename="{filename}"' if filename else "")
            head = f"--{boundary}\r\nContent-Disposition: {disp}\r\n" + (f"Content-Type: {ctype}\r\n" if ctype else "") + "\r\n"
            parts.append(head.encode() + value.encode() + b"\r\n")

        field("manifest", json.dumps(manifest))
        field("branch", "main")
        field("commit_message", label)
        field("_worker.js", (Path(dist) / "_worker.js").read_text(), "_worker.js", "application/javascript+module")
        field("_routes.json", ROUTES_JSON, "_routes.json", "application/json")
        raw = b"".join(parts) + f"--{boundary}--\r\n".encode()
        return self.call("POST", f"/accounts/{self.acct}/pages/projects/{project}/deployments", raw=raw,
                         ctype=f"multipart/form-data; boundary={boundary}")


# --------------------------------------------------------------------------- main

def load_state(p):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return {}


def save_state(p, st):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(st, indent=1))


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "vpt-arena-publisher"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode(errors="replace")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Publish the VPT Arena public site")
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--project", default=PROJECT)
    ap.add_argument("--build-only", action="store_true", help="build dist/ and run the scrub check; no network")
    ap.add_argument("--force", action="store_true", help="redeploy and rewrite the data value")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    dist = root / "dist"
    state_path = root / "runs" / ".publish_state.json"

    build_dist(dist)
    snap = build_snapshot(root)
    payload = json.dumps(srv._clean(snap), allow_nan=False, separators=(",", ":"))
    bad = check_dist(dist, payload)
    if bad:
        print("PUBLISH BLOCKED: scrubbed patterns found in the output:", file=sys.stderr)
        for b in bad[:20]:
            print("  " + b, file=sys.stderr)
        return 2
    (dist / "data.preview.json").write_text(payload)   # for local inspection only; removed before deploy
    print(f"built dist/ ({len(payload) // 1024} KiB data, scrub check passed)")
    if args.build_only:
        return 0
    (dist / "data.preview.json").unlink()

    st = load_state(state_path)
    cf = CF()
    proj = cf.ensure_project(args.project)
    pname = proj["name"]
    sub = proj.get("subdomain") or f"{pname}.pages.dev"
    if st.get("project") != pname or not st.get("kv_ns"):
        ns = cf.ensure_kv()
        cf.bind_kv(pname, ns)
        st.update(project=pname, kv_ns=ns, frontend=None)
        save_state(state_path, st)

    fh = frontend_hash(dist)
    if args.force or st.get("frontend") != fh:
        d = cf.deploy(pname, dist, "front end " + fh[:8])
        st["frontend"] = fh
        save_state(state_path, st)
        print("deployed front end", fh[:8], (d or {}).get("url", ""))
    else:
        print("front end unchanged, no deployment")

    sh = snapshot_hash(snap)
    age = time.time() - st.get("kv_time", 0)
    if args.force or st.get("data") != sh or age > KV_REFRESH_S:
        cf.kv_put(st["kv_ns"], KV_KEY, payload)
        st.update(data=sh, kv_time=time.time())
        save_state(state_path, st)
        print("data written to KV")
    else:
        print("data unchanged, KV not written")
    print("site: https://" + sub)
    return 0


if __name__ == "__main__":
    sys.exit(main())
