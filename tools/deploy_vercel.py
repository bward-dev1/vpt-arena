"""Deploy the site's static front end to Vercel; dynamic paths are proxied to the Cloudflare worker.

    python3 tools/deploy_vercel.py            # deploys only if the front end changed
    python3 tools/deploy_vercel.py --force

Builds with tools/publish_site.py --build-only (same scrubbed dist/), adds vercel.json rewrites for
/data.json, /clips/*, /sims/*, /api/*, /live/* to https://vpt-arena.pages.dev, and runs
`vercel deploy --prod` from a temp copy. The Vercel project link is kept in runs/.vercel/.
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = "https://vpt-arena.pages.dev"
PROJECT = "vpt-arena"
LINK = ROOT / "runs" / ".vercel"
STATE = ROOT / "runs" / ".vercel_state.json"

VERCEL_JSON = {
    "cleanUrls": False,
    "rewrites": [
        {"source": "/data.json", "destination": f"{BACKEND}/data.json"},
        {"source": "/clips/:path*", "destination": f"{BACKEND}/clips/:path*"},
        {"source": "/sims/:path*", "destination": f"{BACKEND}/sims/:path*"},
        {"source": "/api/:path*", "destination": f"{BACKEND}/api/:path*"},
        {"source": "/live/:path*", "destination": f"{BACKEND}/live/:path*"},
        {"source": "/trailer.mp4", "destination": f"{BACKEND}/trailer.mp4"},
        {"source": "/trailer-vertical.mp4", "destination": f"{BACKEND}/trailer-vertical.mp4"},
        {"source": "/trailer-60.mp4", "destination": f"{BACKEND}/trailer-60.mp4"},
        {"source": "/clips60/:path*", "destination": f"{BACKEND}/clips60/:path*"},
    ],
    "headers": [
        {"source": "/(.*)\\.(js|css)", "headers": [{"key": "cache-control", "value": "public, max-age=300"}]},
        {"source": "/index.html", "headers": [{"key": "cache-control", "value": "public, max-age=0, must-revalidate"}]},
    ],
}


def dist_hash(d):
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        if p.is_file() and p.name not in ("_worker.js", "_routes.json"):
            h.update(str(p.relative_to(d)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def main():
    force = "--force" in sys.argv
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "publish_site.py"), "--build-only"], cwd=ROOT,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"build failed: {r.stdout[-400:]}{r.stderr[-400:]}")
    dist = ROOT / "dist"
    h = dist_hash(dist)
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    if not force and st.get("hash") == h:
        print("vercel: front end unchanged")
        return
    tmp = Path(tempfile.mkdtemp(prefix="vpt-vercel-"))
    try:
        out = tmp / "site"
        shutil.copytree(dist, out, ignore=shutil.ignore_patterns("_worker.js", "_routes.json", "data.json"))
        (out / "vercel.json").write_text(json.dumps(VERCEL_JSON, indent=1))
        if LINK.exists():
            shutil.copytree(LINK, out / ".vercel")
        else:
            subprocess.run(["vercel", "link", "--yes", "--project", PROJECT], cwd=out, check=True,
                           capture_output=True, text=True)
            shutil.copytree(out / ".vercel", LINK)
        d = subprocess.run(["vercel", "deploy", "--prod", "--yes"], cwd=out, capture_output=True, text=True, timeout=600)
        if d.returncode != 0:
            raise SystemExit(f"vercel deploy failed: {d.stderr[-600:]}")
        st.update(hash=h)
        STATE.write_text(json.dumps(st))
        print("vercel: deployed https://vpt-arena.vercel.app")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
