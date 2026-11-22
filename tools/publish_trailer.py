"""Download trailer release mp4s to a temp dir (deleted afterwards) and write them to Workers KV.
  python3 tools/publish_trailer.py              hype cut: release `trailer`   -> trailer:main (30 fps), trailer:main60 (60 fps), trailer:vertical
  python3 tools/publish_trailer.py --cinematic  cinematic cut: release `trailer-cinematic` -> trailer:cinematic (30 fps), trailer:cinematic60 (60 fps)
Needs the Cloudflare creds that tools/sim_relay.py's KV class reads from env."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sim_relay import KV, REPO  # noqa: E402

CUTS = {
    "hype": ("trailer", {"trailer-30.mp4": "trailer:main", "trailer-60.mp4": "trailer:main60", "trailer-vertical.mp4": "trailer:vertical"}),
    "cinematic": ("trailer-cinematic", {"trailer-cinematic-30.mp4": "trailer:cinematic", "trailer-cinematic-60.mp4": "trailer:cinematic60"}),
}
LIMIT = 24 * 1000 * 1000  # keep under the KV value limit used for clips


def main():
    tag, keys = CUTS["cinematic" if "--cinematic" in sys.argv else "hype"]
    tmp = Path(tempfile.mkdtemp(prefix="trailer-"))
    try:
        subprocess.run(["gh", "release", "download", tag, "-R", REPO, "-D", str(tmp), "--clobber"] + sum((["-p", n] for n in keys), []), check=True)
        kv = KV()
        for name, key in keys.items():
            f = tmp / name
            if not f.exists():
                print(f"skip {name}: not in the release")
                continue
            data = f.read_bytes()
            if len(data) > LIMIT:
                print(f"skip {name}: {len(data)} bytes is over {LIMIT}")
                continue
            kv.put_bytes(key, data)
            print(f"{key}: {len(data):,} bytes written")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
