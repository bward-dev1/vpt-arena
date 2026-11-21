"""Pull cloud RL progress into runs/ for the dashboard (status-* branches + workflow runs + releases).

    python3 tools/pull_cloud.py            # once
Writes runs/<job>/{status.json,run.json,rl_log.jsonl} and runs/cloud_status.json.
Uses the gh CLI (already logged in). No large downloads.
"""
import base64
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "bward-dev1/vpt-arena"
RUNS = ROOT / "runs"


def gh(*args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:200])
    return r.stdout


def api(path):
    return json.loads(gh("api", path))


def main():
    RUNS.mkdir(exist_ok=True)
    branches = [b["name"] for b in api(f"repos/{REPO}/branches?per_page=100") if b["name"].startswith("status-")]
    jobs = []
    for br in branches:
        job = br[len("status-"):]
        d = RUNS / job
        d.mkdir(exist_ok=True)
        for name in ("status.json", "run.json", "rl_log.jsonl"):
            try:
                meta = api(f"repos/{REPO}/contents/status/{job}/{name}?ref={br}")
            except RuntimeError:
                continue
            content = meta.get("content")
            if content is None and meta.get("download_url"):
                content = None
                raw = subprocess.run(["curl", "-sfL", meta["download_url"]], capture_output=True, timeout=60).stdout
            else:
                raw = base64.b64decode(content)
            (d / name).write_bytes(raw)
        st = {}
        if (d / "status.json").exists():
            try:
                st = json.loads((d / "status.json").read_text())
            except json.JSONDecodeError:
                pass
        stale = st.get("state") == "running" and time.time() - float(st.get("updated", 0)) > 1800
        modes = ", ".join(st.get("modes", []))
        pm = st.get("per_mode", {})
        prog = f"iter {st.get('iter', 0)}, {st.get('env_steps', 0):,} steps"
        if pm:
            prog += "; " + ", ".join(f"{m}: return {v['return']:.1f}, win {100 * v['win_rate']:.0f}%" for m, v in pm.items())
        jobs.append({"name": f"{job} ({modes})", "platform": "github-actions", "hardware": "4 vCPU, 16 GB, CPU render",
                     "state": "stopped" if stale else st.get("state", "queued"), "started": st.get("started"),
                     "updated": st.get("updated"), "progress": prog, "run": f"runs/{job}"})
    # rounds in flight / done
    try:
        runs = json.loads(gh("run", "list", "-R", REPO, "-w", "rl-round", "-L", "10", "--json",
                             "databaseId,status,conclusion,createdAt,displayTitle"))
    except RuntimeError:
        runs = []
    try:
        rels = [r["tagName"] for r in json.loads(gh("release", "list", "-R", REPO, "--json", "tagName", "-L", "50"))]
    except RuntimeError:
        rels = []
    rounds = [{"name": f"RL round workflow #{r['databaseId']}", "platform": "github-actions", "hardware": "12 workers + merge",
               "state": {"in_progress": "running", "queued": "queued"}.get(r["status"],
                                                                         "finished" if r.get("conclusion") == "success" else "failed"),
               "started": r["createdAt"], "updated": None, "progress": r.get("conclusion") or r["status"], "run": None}
              for r in runs[:3]]
    clips = {}
    for tag in rels:
        try:
            assets = api(f"repos/{REPO}/releases/tags/{tag}").get("assets", [])
        except RuntimeError:
            continue
        for a in assets:
            if a["name"].startswith("clip-") and a["name"].endswith(".mp4"):
                clips.setdefault(tag, {})[a["name"][5:-4]] = a["browser_download_url"]
    out = {"updated": time.time(), "jobs": rounds + sorted(jobs, key=lambda j: j["name"]), "releases": rels,
           "clips": clips, "repo": f"https://github.com/{REPO}"}
    build_league(rels)
    tmp = RUNS / "cloud_status.json.tmp"
    tmp.write_text(json.dumps(out, indent=1))
    tmp.replace(RUNS / "cloud_status.json")
    print(f"{len(jobs)} worker statuses, {len(rounds)} rounds, releases: {rels}")


def build_league(rels):
    """Eval results on releases (eval.json) -> runs/league.json, rated against the fixed arena bots (Elo 1000)."""
    import math
    cache = RUNS / ".eval-cache"
    cache.mkdir(exist_ok=True)
    players, matches = {}, []
    for tag in rels:
        try:
            assets = {a["name"]: a for a in api(f"repos/{REPO}/releases/tags/{tag}").get("assets", [])}
        except RuntimeError:
            continue
        if "eval.json" not in assets:
            continue
        stamp = assets["eval.json"]["updated_at"].replace(":", "")
        f = cache / f"{tag}-{stamp}.json"
        if not f.exists():
            r = subprocess.run(["gh", "release", "download", tag, "-R", REPO, "-p", "eval.json", "-O", str(f), "--clobber"],
                               capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                continue
        try:
            ev = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        by_mode, games_n, wins_n = {}, 0, 0
        for mode, m in ev.get("modes", {}).items():
            n = int(m.get("episodes", 0))
            w = round(float(m.get("win_rate", 0)) * n)
            p = (w + 0.5) / (n + 1)
            by_mode[mode] = round(1000 + 400 * math.log10(p / (1 - p)), 1)
            games_n += n
            wins_n += w
            matches.append({"t": f.stat().st_mtime, "mode": mode, "a": tag, "b": "arena-bots",
                            "winner": tag if w * 2 > n else ("arena-bots" if w * 2 < n else None),
                            "score": f"{w}/{n} wins, return {m.get('return', 0):.1f}"})
        if by_mode:
            players[tag] = {"elo": round(sum(by_mode.values()) / len(by_mode), 1), "games": games_n, "wins": wins_n,
                            "kind": "checkpoint", "by_mode": by_mode}
    if players:
        players["arena-bots"] = {"elo": 1000.0, "games": sum(p["games"] for p in players.values()),
                                 "wins": sum(p["games"] - p["wins"] for p in players.values()), "kind": "scripted",
                                 "by_mode": {}}
        (RUNS / "league.json").write_text(json.dumps({"players": players, "matches": matches[-500:]}, indent=1))


if __name__ == "__main__":
    main()
