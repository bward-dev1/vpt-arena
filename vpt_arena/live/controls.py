"""Mapping between game actions and physical keys/mouse, independent of the OS backend.

Bindings live in configs/controls.json so the recorder and the agent agree
with whatever the player set in Minecraft's Controls screen. Recordings always
store VPT's key names (sprint as key.keyboard.left.control, and so on), so a
player who binds sprint to R still produces standard training data.

Mouse sensitivity: Minecraft turns (s*0.6+0.2)^3 * 1.2 degrees per mouse pixel
for slider value s (0..1; "100%" is 0.5). At 0.5 that is exactly VPT's
360/2400 degrees per pixel, so recordings are rescaled to that.
"""
import json
from pathlib import Path

import numpy as np

from ..vpt import CAMERA_SCALER, KEYBOARD_BUTTON_MAPPING, noop_env_action

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BINDINGS = {
    "forward": "w", "back": "s", "left": "a", "right": "d", "jump": "space", "sneak": "left.shift",
    "sprint": "left.control", "inventory": "e", "drop": "q", "swapHands": "f", "ESC": "escape",
    **{f"hotbar.{i}": str(i) for i in range(1, 10)},
    "attack": "mouse0", "use": "mouse1", "pickItem": "mouse2",
}
VPT_KEY_FOR_ACTION = {v: k for k, v in KEYBOARD_BUTTON_MAPPING.items()}  # action -> "key.keyboard.w"


def load_controls(path=None):
    p = Path(path) if path else ROOT / "configs" / "controls.json"
    cfg = json.loads(p.read_text()) if p.exists() else {}
    b = dict(DEFAULT_BINDINGS)
    b.update(cfg.get("bindings", {}))
    return dict(bindings=b, sensitivity=float(cfg.get("sensitivity", 0.5)), gui_scale=int(cfg.get("gui_scale", 2)))


def degrees_per_pixel(sensitivity):
    return (sensitivity * 0.6 + 0.2) ** 3 * 1.2


def tick_to_json(snap, controls, hotbar, gui_open, window_h=None, tick=0):
    """One input snapshot (from mac.InputListener.snapshot) -> one VPT recorder JSON line.

    Returns (json_step, new_hotbar).
    """
    by_key = {}
    for action, key in controls["bindings"].items():
        by_key.setdefault(key, []).append(action)
    keys, new_keys = [], []
    for k in snap["keys"]:
        for action in by_key.get(k, []):
            if action in VPT_KEY_FOR_ACTION:
                keys.append(VPT_KEY_FOR_ACTION[action])
                if k in snap["new_keys"]:
                    new_keys.append(VPT_KEY_FOR_ACTION[action])
    vpt_button = {"attack": 0, "use": 1, "pickItem": 2}
    buttons, new_buttons = [], []
    for b in snap["buttons"]:
        for action in by_key.get(f"mouse{b}", []):
            if action in vpt_button:
                buttons.append(vpt_button[action])
                if b in snap["new_buttons"]:
                    new_buttons.append(vpt_button[action])
    # hotbar: number keys or the scroll wheel (scrolling down moves right)
    for k in snap["new_keys"]:
        for action in by_key.get(k, []):
            if action.startswith("hotbar."):
                hotbar = int(action.split(".")[1]) - 1
    if snap["dwheel"] and not gui_open:
        hotbar = int((hotbar - np.sign(snap["dwheel"])) % 9)
    scale = degrees_per_pixel(controls["sensitivity"]) / CAMERA_SCALER
    dx, dy = (snap["dx"] * scale, snap["dy"] * scale) if not gui_open else (snap["dx"], snap["dy"])
    x, y = snap.get("xy", (0, 0))
    if window_h:  # recorder mouse x/y are in 720p pixels
        x, y = x * 720.0 / window_h, y * 720.0 / window_h
    step = {
        "keyboard": {"keys": sorted(set(keys)), "newKeys": sorted(set(new_keys)), "chars": ""},
        "mouse": {"dx": float(dx), "dy": float(dy), "buttons": sorted(set(buttons)), "newButtons": sorted(set(new_buttons)),
                  "x": float(x), "y": float(y), "dwheel": float(snap["dwheel"])},
        "hotbar": int(hotbar), "isGuiOpen": bool(gui_open), "tick": int(tick),
    }
    return step, hotbar


class ActionApplier:
    """Turns a stream of env actions into press/release/move calls on a poster (mac.InputPoster or a fake)."""

    def __init__(self, poster, controls, max_turn_deg=30.0):
        self.poster = poster
        self.controls = controls
        self.px_per_deg = 1.0 / degrees_per_pixel(controls["sensitivity"])
        self.max_turn = max_turn_deg
        self.held = set()  # physical keys / "mouseN" currently held by us

    def wanted(self, action):
        want = set()
        for act, key in self.controls["bindings"].items():
            if act.startswith("hotbar.") or act in ("ESC", "inventory", "drop", "swapHands"):
                continue  # taps, handled below
            if action.get(act, 0):
                want.add(key)
        return want

    def apply(self, action, gui_open=False):
        want = self.wanted(action)
        for key in sorted(self.held - want):
            self._set(key, False)
        for key in sorted(want - self.held):
            self._set(key, True)
        # taps: press and release within the tick
        for act in ["ESC", "inventory", "drop", "swapHands"] + [f"hotbar.{i}" for i in range(1, 10)]:
            if action.get(act, 0):
                key = self.controls["bindings"][act]
                self._set(key, True)
                self._set(key, False)
        cam = np.clip(np.asarray(action.get("camera", (0, 0)), dtype=float), -self.max_turn, self.max_turn)
        if gui_open:
            # In menus VPT's camera action moves the cursor; MineRL used 1 px per (degree / CAMERA_SCALER).
            dx, dy = cam[1] / CAMERA_SCALER * 0.5, cam[0] / CAMERA_SCALER * 0.5
        else:
            dx, dy = cam[1] * self.px_per_deg, cam[0] * self.px_per_deg
        self.poster.move(dx, dy)

    def _set(self, key, down):
        if key.startswith("mouse"):
            self.poster.button(int(key[5:]), down)
        else:
            self.poster.key(key, down)
        (self.held.add if down else self.held.discard)(key)

    def release_all(self):
        for key in sorted(self.held):
            self._set(key, False)
        self.poster.release_all()


def env_action_summary(action):
    """Compact dict for status.json / the site's Live page."""
    out = {k: int(v) for k, v in action.items() if k != "camera" and int(v)}
    cam = np.asarray(action.get("camera", (0, 0)), dtype=float)
    out["camera"] = [round(float(cam[0]), 2), round(float(cam[1]), 2)]
    return out


__all__ = ["load_controls", "tick_to_json", "ActionApplier", "degrees_per_pixel", "env_action_summary", "noop_env_action"]
