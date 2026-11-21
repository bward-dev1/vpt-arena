"""live/status.json and live/frame.jpg, read by the site's Live page."""
import json
import os
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "live"


def write_status(**fields):
    LIVE.mkdir(exist_ok=True)
    fields["updated"] = time.time()
    tmp = LIVE / "status.json.tmp"
    tmp.write_text(json.dumps(fields))
    os.replace(tmp, LIVE / "status.json")


def write_frame(rgb, size=(384, 216)):
    LIVE.mkdir(exist_ok=True)
    img = cv2.resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), size, interpolation=cv2.INTER_NEAREST)
    tmp = LIVE / "frame.tmp.jpg"
    cv2.imwrite(str(tmp), img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    os.replace(tmp, LIVE / "frame.jpg")


class Ticker:
    """Fixed-rate loop timing without drift."""

    def __init__(self, hz=20):
        self.dt = 1.0 / hz
        self.next = time.perf_counter()
        self.late = 0

    def wait(self):
        self.next += self.dt
        delay = self.next - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        else:
            self.late += 1
            if delay < -0.5:  # fell far behind; don't try to catch up with a burst
                self.next = time.perf_counter()
