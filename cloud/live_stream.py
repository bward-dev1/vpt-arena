"""Always-on live stream from a cloud runner: the newest model plays the arena modes in turn, and its view
and key presses are served once a second through a Cloudflare quick tunnel for the site's Live page.

Writes the tunnel URL to OUT/tunnel.json (pushed to branch status-live by the workflow); the local relay
copies it into KV `livetunnel_cloud`, and the site's worker proxies /live/* to it when no local session runs.
"""
import argparse
import json
import random
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import torch as th  # noqa: E402

from vpt_arena import games  # noqa: E402
from vpt_arena.agent import ArenaAgent  # noqa: E402
from vpt_arena.live.controls import env_action_summary  # noqa: E402
from vpt_arena.rl.arena_tasks import TASKS  # noqa: E402
from vpt_arena.rl.sim_env import ArenaSimEnv  # noqa: E402

LATEST = {"status": b'{"state":"offline"}', "frame": None}
LOCK = threading.Lock()


HLS_DIR = Path("live_hls")
HLS_RE = re.compile(r"^/hls/(30|60)/([a-z0-9_]{1,40}\.(?:m3u8|ts))$")


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        p = self.path.split("?", 1)[0]
        m = HLS_RE.match(p)
        if m:
            f = HLS_DIR / m.group(1) / m.group(2)
            if not f.exists():
                self.send_error(404)
                return
            body = f.read_bytes()
            self.send_response(200)
            self.send_header("content-type", "application/vnd.apple.mpegurl" if f.suffix == ".m3u8" else "video/mp2t")
            self.send_header("cache-control", "no-store" if f.suffix == ".m3u8" else "max-age=60")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        with LOCK:
            body = LATEST["status"] if p == "/status.json" else LATEST["frame"] if p == "/frame.jpg" else None
        if body is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("content-type", "application/json" if p.endswith(".json") else "image/jpeg")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


FRAME_RGB = {"img": None}


def encoder():
    """Feed the newest 480x270 view at a steady 20 fps into ffmpeg, which writes 30 fps and 60 fps HLS
    (2 s segments, frames blended in between) for the site's live video player."""
    import numpy as np
    for r in ("30", "60"):
        (HLS_DIR / r).mkdir(parents=True, exist_ok=True)
    common = ["-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-pix_fmt", "yuv420p", "-g", "60",
              "-sc_threshold", "0", "-f", "hls", "-hls_time", "2", "-hls_list_size", "6",
              "-hls_flags", "delete_segments+independent_segments+omit_endlist"]
    cmd = ["ffmpeg", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "480x270", "-r", "20", "-i", "-",
           "-filter_complex", "[0:v]split=2[a][b];[a]minterpolate=fps=30:mi_mode=blend[v30];[b]minterpolate=fps=60:mi_mode=blend[v60]",
           "-map", "[v30]", *common, "-hls_segment_filename", str(HLS_DIR / "30" / "s_%05d.ts"), str(HLS_DIR / "30" / "index.m3u8"),
           "-map", "[v60]", *common, "-hls_segment_filename", str(HLS_DIR / "60" / "s_%05d.ts"), str(HLS_DIR / "60" / "index.m3u8")]
    blank = np.zeros((270, 480, 3), np.uint8)
    while True:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        nxt = time.time()
        try:
            while proc.poll() is None:
                img = FRAME_RGB["img"]
                proc.stdin.write((img if img is not None else blank).tobytes())
                nxt += 0.05
                time.sleep(max(0.0, nxt - time.time()))
        except (BrokenPipeError, OSError):
            pass
        print("encoder restarted", flush=True)
        time.sleep(2)


def tunnel(port, out):
    proc = subprocess.Popen(["./cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
                            stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
    for line in proc.stderr:
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            (out / "tunnel.json").write_text(json.dumps({"url": m.group(0), "since": int(time.time() * 1000)}))
            print("tunnel", m.group(0), flush=True)
    proc.wait()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--minutes", type=float, default=340)
    ap.add_argument("--out", default="live_out")
    ap.add_argument("--port", type=int, default=7793)
    args = ap.parse_args()
    th.set_num_threads(3)
    out = Path(args.out)
    out.mkdir(exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    threading.Thread(target=tunnel, args=(args.port, out), daemon=True).start()
    threading.Thread(target=encoder, daemon=True).start()
    modes = [m for m in TASKS if TASKS[m].sky] + ["survival"]
    random.seed(int(time.time()))
    env, agent = None, ArenaAgent("1x", args.weights, "duels_sword", device="cpu")
    deadline = time.time() + args.minutes * 60
    while time.time() < deadline:
        mode = random.choice(modes)
        if env is None:
            env = ArenaSimEnv(mode, seed=7, difficulty=0.6)
        else:
            env.task, env.mode = TASKS[mode], mode
        agent.set_mode(mode)
        agent.reset()
        frame = env.reset()
        done, ret, t0, n, last_push, info = False, 0.0, time.time(), 0, 0.0, {}
        while not done and time.time() < deadline:
            a, _ = agent.act(frame)
            frame, r, done, info = env.step(a)
            ret += r
            n += 1
            if getattr(env, "last_pov", None) is not None:
                FRAME_RGB["img"] = cv2.resize(env.last_pov, (480, 270), interpolation=cv2.INTER_AREA)
            now = time.time()
            if now - last_push >= 1.0 or done:
                last_push = now
                st = {"state": "playing", "mode": mode, "mode_name": games.get(mode).name, "checkpoint": args.tag,
                      "server": "cloud arena (MineStudio 1.16.5)", "fps": round(n / max(1e-6, now - t0), 1),
                      "updated": now, "last_action": env_action_summary(a),
                      "episode": {"t": round(n / 20, 1), "return": round(ret, 2)}, "source": "cloud",
                      "hls": {"30": "/live/hls/30/index.m3u8", "60": "/live/hls/60/index.m3u8"}}
                jpg = None
                if getattr(env, "last_pov", None) is not None:
                    img = cv2.resize(env.last_pov, (384, 216), interpolation=cv2.INTER_AREA)
                    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 75])
                    jpg = buf.tobytes() if ok else None
                with LOCK:
                    LATEST["status"] = json.dumps(st).encode()
                    if jpg:
                        LATEST["frame"] = jpg
        print(f"{mode}: return {ret:.2f} won {info.get('won')} in {n} steps", flush=True)
    with LOCK:
        LATEST["status"] = b'{"state":"offline"}'
    time.sleep(5)


if __name__ == "__main__":
    main()
