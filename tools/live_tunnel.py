"""Make the local Live view (live/status.json + live/frame.jpg) reachable from any device.

A tiny read-only server on 127.0.0.1:7792 serves exactly those two files. A Cloudflare quick tunnel
(cloudflared, no account) exposes it, and the tunnel URL goes into KV key `livetunnel`, which the
public site's worker reads to proxy /live/status.json and /live/frame.jpg. Nothing else on the Mac
is reachable through it. Restarts the tunnel if it drops.

    python3 tools/live_tunnel.py          # run detached; Ctrl-C / kill clears the KV key
"""
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from sim_relay import KV  # noqa: E402

LIVE = ROOT / "live"
PORT = 7792
FILES = {"/status.json": ("status.json", "application/json"), "/frame.jpg": ("frame.jpg", "image/jpeg")}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path not in FILES:
            self.send_error(404)
            return
        name, ctype = FILES[path]
        f = LIVE / name
        if not f.exists():
            body = b'{"state":"offline"}' if name.endswith(".json") else b""
            code = 200 if body else 404
        else:
            body, code = f.read_bytes(), 200
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("cache-control", "no-store")
        self.send_header("access-control-allow-origin", "*")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def run_tunnel(kv):
    home = tempfile.mkdtemp(prefix="cf-quick-")  # keep cloudflared away from ~/.cloudflared/config.yml
    env = dict(os.environ, HOME=home)
    proc = subprocess.Popen(["cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORT}"],
                            stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, env=env)
    url = None
    for line in proc.stderr:
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m and not url:
            url = m.group(0)
            kv.put_json("livetunnel", {"url": url, "since": int(time.time() * 1000)})
            print(f"tunnel up: {url}", flush=True)
    return proc.wait()


def main():
    LIVE.mkdir(exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    kv = KV()

    def stop(*_):
        try:
            kv.put_json("livetunnel", {"url": None, "since": int(time.time() * 1000)})
        finally:
            os._exit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while True:
        code = run_tunnel(kv)
        print(f"tunnel exited ({code}); restarting in 15 s", flush=True)
        time.sleep(15)


if __name__ == "__main__":
    main()
