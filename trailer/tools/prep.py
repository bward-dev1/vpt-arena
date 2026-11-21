"""Cloud prep for the trailer: download clips + data, capture site screenshots, build the clip walls, write props.json.
Run from the repo root: python3 trailer/tools/prep.py   (needs gh, ffmpeg, ffprobe, google-chrome, pip: requests brotli)"""
import json, os, re, subprocess, sys, shutil
import requests

REPO = "bward-dev1/vpt-arena"
SITE = "https://vpt-arena.vercel.app"
PUB = "trailer/public"


def run(*a, check=True, timeout=600):
    return subprocess.run(a, check=check, capture_output=True, text=True, timeout=timeout)


def probe_dur(path):
    try:
        return float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path).stdout.strip())
    except Exception:
        return 0.0


os.makedirs(f"{PUB}/shots", exist_ok=True)

# ---- real numbers ----
data = requests.get(f"{SITE}/data.json", timeout=60).json()
json.dump(data, open("trailer/data.json", "w"))
mode_ids = data["rounds"]["modes"]
names = {c["mode"]: c["name"] for c in data["cloud"].get("clips", [])}
rounds = []
for r in data["rounds"]["rounds"]:
    ms = r.get("modes", {})
    rounds.append({
        "tag": r["tag"], "elo": r.get("elo"),
        "wins": sum(v.get("wins", 0) for v in ms.values()), "games": sum(v.get("episodes", 0) for v in ms.values()),
        "per": ms,
    })
rounds_by_tag = {r["tag"]: r for r in rounds}

tags = json.loads(run("gh", "release", "list", "-R", REPO, "--json", "tagName", "-L", "100").stdout)
tags = [t["tagName"] for t in tags]
round_tags = sorted([t for t in tags if re.fullmatch(r"round-\d+", t)], key=lambda t: int(t.split("-")[1]))

steps = 0
workers = []
for t in round_tags:
    out = run("gh", "release", "download", t, "-R", REPO, "-p", "summary.json", "-O", "-", check=False).stdout
    try:
        jobs = json.loads(out)["jobs"]
    except Exception:
        continue
    steps += sum(int(j.get("env_steps", 0)) for j in jobs)
    workers = [{"job": j["job"], "modes": j.get("modes", []), "steps": int(j.get("env_steps", 0))} for j in jobs]  # latest round with a summary

# ---- clips: latest tag that has each mode, baseline as the fallback ----
have = {}
for t in ["baseline"] + round_tags:
    d = f"{PUB}/clips/{t}"
    os.makedirs(d, exist_ok=True)
    run("gh", "release", "download", t, "-R", REPO, "-p", "clip-*.mp4", "-D", d, "--clobber", check=False)
    for f in os.listdir(d):
        m = re.fullmatch(r"clip-(.+)\.mp4", f)
        if m:
            have[(t, m.group(1))] = f"clips/{t}/{f}"
modes = []
for mid in mode_ids:
    pick = None
    for t in reversed(["baseline"] + round_tags):
        if (t, mid) in have:
            pick = (t, have[(t, mid)])
            break
    if not pick:
        continue
    per = rounds_by_tag.get(pick[0], {}).get("per", {}).get(mid, {})
    modes.append({
        "id": mid, "name": names.get(mid, mid.replace("_", " ").title()), "clip": pick[1], "dur": probe_dur(f"{PUB}/{pick[1]}"),
        "tag": pick[0], "wins": per.get("wins", 0), "episodes": per.get("episodes", 0), "ret": per.get("return"),
    })
print("modes with clips:", len(modes), "tags used:", sorted({m["tag"] for m in modes}))

# ---- clip walls (23 tiles + one blank) built once with ffmpeg, so the render only decodes one video ----
def wall(cols, rows, out, secs=16):
    n = cols * rows
    cmd = ["ffmpeg", "-y", "-v", "error"]
    chains = []
    for i in range(n):
        if i < len(modes):
            cmd += ["-stream_loop", "-1", "-ss", str(min(2.0, max(0, modes[i]["dur"] - secs))), "-t", str(secs), "-i", f"{PUB}/{modes[i]['clip']}"]
            chains.append(f"[{i}:v]scale=320:180:flags=neighbor,fps=30,setsar=1[v{i}]")
        else:
            cmd += ["-f", "lavfi", "-t", str(secs), "-i", "color=c=0x0c0f14:s=320x180:r=30"]
            chains.append(f"[{i}:v]setsar=1[v{i}]")
    layout = "|".join(f"{(i % cols) * 320}_{(i // cols) * 180}" for i in range(n))
    fc = ";".join(chains) + ";" + "".join(f"[v{i}]" for i in range(n)) + f"xstack=inputs={n}:layout={layout}[o]"
    cmd += ["-filter_complex", fc, "-map", "[o]", "-t", str(secs), "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30", out]
    subprocess.run(cmd, check=True)

wall(6, 4, f"{PUB}/wall.mp4")
wall(3, 8, f"{PUB}/wallv.mp4")

# ---- site screenshots (headless Chrome) ----
shots = {}
for key in ["overview", "dashboard", "simulate", "live"]:
    out = f"{PUB}/shots/{key}.png"
    subprocess.run([
        "google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--window-size=1600,1000",
        "--force-device-scale-factor=1", "--virtual-time-budget=25000", f"--screenshot={out}", f"{SITE}/#/{key}",
    ], capture_output=True, timeout=120)
    if os.path.exists(out) and os.path.getsize(out) > 5000:
        shots[key] = f"shots/{key}.png"
print("shots:", shots)

live = None
try:
    r = requests.get(f"{SITE}/live/frame.jpg", timeout=20)
    if r.status_code == 200 and r.headers.get("content-type", "").startswith("image") and len(r.content) > 2000:
        open(f"{PUB}/shots/liveframe.jpg", "wb").write(r.content)
        live = "shots/liveframe.jpg"
except Exception as e:
    print("no live frame", e)

base = rounds_by_tag.get("baseline", {"wins": 0, "games": 69})
props = {
    "modes": modes,
    "stats": {"games": base["games"], "wins": base["wins"], "steps": steps, "rounds": [{k: v for k, v in r.items() if k != "per"} for r in rounds], "workers": workers},
    "shots": shots,
    "liveFrame": live,
}
json.dump(props, open("trailer/props.json", "w"), indent=1)
print(json.dumps(props["stats"])[:600])
