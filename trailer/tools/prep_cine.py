"""Cloud prep for the cinematic cut. Reads every number from the releases' eval.json at render time.
Run from the repo root: python3 trailer/tools/prep_cine.py  -> trailer/public-cine/ + trailer/props-cine.json"""
import json, os, re, subprocess
import requests

REPO = "bward-dev1/vpt-arena"
SITE = "https://vpt-arena.vercel.app"
PUB = "trailer/public-cine"


def run(*a, check=True, timeout=600):
    return subprocess.run(a, check=check, capture_output=True, text=True, timeout=timeout)


def gh_json(tag, name):
    out = run("gh", "release", "download", tag, "-R", REPO, "-p", name, "-O", "-", check=False).stdout
    try:
        return json.loads(out)
    except Exception:
        return None


def probe_dur(path):
    try:
        return float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path).stdout.strip())
    except Exception:
        return 0.0


os.makedirs(f"{PUB}/clips", exist_ok=True)
os.makedirs(f"{PUB}/grain", exist_ok=True)
os.makedirs(f"{PUB}/shots", exist_ok=True)

tags = [t["tagName"] for t in json.loads(run("gh", "release", "list", "-R", REPO, "--json", "tagName", "-L", "100").stdout)]
rounds = sorted([t for t in tags if re.fullmatch(r"round-\d+", t)], key=lambda t: int(t.split("-")[1]))
scratch = sorted([t for t in tags if re.fullmatch(r"scratch-\d+", t)], key=lambda t: int(t.split("-")[1]))
use = ["baseline"] + rounds + (["openai-rl-2x"] if "openai-rl-2x" in tags else []) + scratch[-1:]

T = {}
for t in use:
    ev = gh_json(t, "eval.json")
    if not ev:
        continue
    per = ev["modes"]
    rets = [v["return"] for v in per.values()]
    T[t] = {
        "mean": sum(rets) / len(rets),
        "wins": round(sum(v.get("win_rate", 0) * v["episodes"] for v in per.values())),
        "games": sum(v["episodes"] for v in per.values()),
        "per": {k: {"return": v["return"], "episodes": v["episodes"], "win_rate": v.get("win_rate", 0)} for k, v in per.items()},
    }
rounds = [t for t in rounds if t in T]
first, last = rounds[0], rounds[-1]
rival = "openai-rl-2x" if "openai-rl-2x" in T else None
scr = scratch[-1] if scratch and scratch[-1] in T else None

# the two modes that improved most from the first round to the latest
delta = sorted(((T[last]["per"][m]["return"] - T[first]["per"][m]["return"], m) for m in T[last]["per"] if m in T[first]["per"]), reverse=True)
improved = [m for _, m in delta[:2]]
duels = [m for m in T[last]["per"] if m.startswith("duels_")]
beat = sum(1 for m in duels if rival and T[last]["per"][m]["return"] > T[rival]["per"][m]["return"])

# clip pairs (tag, mode) we use; each fetched as clip-*.mp4 and, where the release has it, clip60-*.mp4 (60 fps)
want = {("baseline", m) for m in ("duels_sword", "the_bridge", "bedwars_squads", "skywars_solo", "kitpvp")}
for m in improved:
    want |= {(first, m), (last, m)}
want |= {(last, "duels_sword"), (last, "duels_classic")}
if rival:
    want.add((rival, "duels_sword"))
if scr:
    want.add((scr, "duels_classic"))
clips = {}
for t, m in sorted(want):
    d = f"{PUB}/clips/{t}"
    os.makedirs(d, exist_ok=True)
    for pre in ("clip", "clip60"):
        run("gh", "release", "download", t, "-R", REPO, "-p", f"{pre}-{m}.mp4", "-D", d, "--clobber", check=False)
    c, c60 = f"{d}/clip-{m}.mp4", f"{d}/clip60-{m}.mp4"
    if os.path.exists(c):
        clips[f"{t}/{m}"] = {"clip": c.replace(PUB + "/", ""), "clip60": c60.replace(PUB + "/", "") if os.path.exists(c60) else None, "dur": probe_dur(c)}
print("clips:", len(clips), "of", len(want))

data = requests.get(f"{SITE}/data.json", timeout=60).json()
names = {c["mode"]: c["name"] for c in data.get("overview", {}).get("clips", []) if isinstance(c, dict)}

# live card: last frame of the stream, plus the Live tab as a fallback
live = None
try:
    r = requests.get(f"{SITE}/live/frame.jpg", timeout=20)
    if r.status_code == 200 and r.headers.get("content-type", "").startswith("image") and len(r.content) > 2000:
        open(f"{PUB}/shots/liveframe.jpg", "wb").write(r.content)
        live = "shots/liveframe.jpg"
except Exception as e:
    print("no live frame", e)
out = f"{PUB}/shots/live.png"
subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--window-size=1600,1000",
                "--force-device-scale-factor=1", "--virtual-time-budget=25000", f"--screenshot={out}", f"{SITE}/#/live"], capture_output=True, timeout=120)
shot = "shots/live.png" if os.path.exists(out) and os.path.getsize(out) > 5000 else None

# film grain: 8 frames of temporal noise, cycled by the render (ffmpeg only)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=960x540:r=1", "-vf", "noise=alls=45:allf=t+u,format=gray", "-frames:v", "8", f"{PUB}/grain/g%d.png"], check=True)

props = {"tags": T, "rounds": rounds, "first": first, "last": last, "rival": rival, "scratch": scr, "improved": improved, "duelsBeaten": beat,
         "duelsTotal": len(duels), "clips": clips, "names": names, "liveFrame": live, "liveShot": shot}
json.dump(props, open("trailer/props-cine.json", "w"), indent=1)
print(json.dumps({k: (v if k != "tags" else {t: {"mean": round(x["mean"], 2), "wins": x["wins"], "games": x["games"]} for t, x in v.items()}) for k, v in props.items() if k not in ("clips", "names")}))
