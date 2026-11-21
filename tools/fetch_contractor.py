"""Download OpenAI's VPT contractor recordings (mp4 + jsonl) for survival rehearsal data.

    python tools/fetch_contractor.py --index 7 --n 50 --out data/contractor
    python tools/fetch_contractor.py --index 7 --n 1 --max-mb 15 --out /tmp/x   # one small clip

Index versions: 6 (general play), 7 (early game), 8 (house building), 9 and 10
(see VPT's README). Each clip is a few to ~120 MB. Skips files already present.
"""
import argparse
import json
import random
import urllib.request
from pathlib import Path

INDEX = {
    6: "all_6xx_Jun_29.json", 7: "all_7xx_Apr_6.json", 8: "all_8xx_Jun_29.json",
    9: "all_9xx_Jun_29.json", 10: "all_10xx_Jun_29.json",
}
BASE = "https://openaipublic.blob.core.windows.net/minecraft-rl/snapshots/"


def size_of(url):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=30) as r:
        return int(r.headers.get("Content-Length", 0))


def fetch(url, dest):
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    tmp.replace(dest)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=int, default=7, choices=sorted(INDEX))
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--max-mb", type=float, default=None, help="skip clips bigger than this")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    with urllib.request.urlopen(BASE + INDEX[args.index], timeout=60) as r:
        idx = json.loads(r.read())
    rel = list(idx["relpaths"])
    random.Random(args.seed).shuffle(rel)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    got = 0
    for rp in rel:
        if got >= args.n:
            break
        mp4 = idx["basedir"] + rp
        stem = out / Path(rp).stem
        if (stem.with_suffix(".mp4")).exists() and (stem.with_suffix(".jsonl")).exists():
            got += 1
            continue
        if args.max_mb and size_of(mp4) > args.max_mb * 2**20:
            continue
        try:
            fetch(mp4[:-4] + ".jsonl", stem.with_suffix(".jsonl"))
            fetch(mp4, stem.with_suffix(".mp4"))
        except Exception as e:  # some index entries have no jsonl
            print(f"skip {rp}: {e}")
            for ext in (".jsonl", ".mp4"):
                stem.with_suffix(ext).unlink(missing_ok=True)
            continue
        got += 1
        print(f"{got}/{args.n} {stem.name}")


if __name__ == "__main__":
    main()
