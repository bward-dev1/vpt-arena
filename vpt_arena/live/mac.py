"""macOS backends: find and capture the Minecraft window, read the player's input, post the agent's input.

Uses Quartz (pyobjc-framework-Quartz). macOS asks once for each permission,
for whichever app runs Python (Terminal, iTerm, VS Code):
  - Screen Recording: capturing the window
  - Input Monitoring: the recorder reading keys and mouse
  - Accessibility: the live agent posting keys and mouse

Key codes are macOS virtual key codes (US layout).
"""
import threading
import time

import numpy as np

try:
    import Quartz as Q
except ImportError:  # lets the pure-logic modules import on machines without pyobjc
    Q = None

KEYCODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "q": 12, "w": 13, "e": 14, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23,
    "9": 25, "7": 26, "8": 28, "space": 49, "escape": 53, "left.shift": 56, "left.control": 59, "left.alt": 58,
    "tab": 48, "r": 15, "t": 17, "f8": 100, "f12": 111,
}
CODE_TO_KEY = {v: k for k, v in KEYCODES.items()}
MODIFIER_CODES = {56: 0x20000, 59: 0x40000, 58: 0x80000}  # keycode -> CGEventFlags mask
AGENT_TAG = 0x56505441  # stamped on every event the agent posts, so the listener can tell them from the player's


def _need_quartz():
    if Q is None:
        raise RuntimeError("pyobjc-framework-Quartz is not installed")


# --------------------------------------------------------------------------- windows

def list_windows():
    _need_quartz()
    infos = Q.CGWindowListCopyWindowInfo(Q.kCGWindowListOptionOnScreenOnly | Q.kCGWindowListExcludeDesktopElements,
                                         Q.kCGNullWindowID) or []
    out = []
    for w in infos:
        b = w.get("kCGWindowBounds", {})
        out.append(dict(id=int(w.get("kCGWindowNumber", 0)), owner=str(w.get("kCGWindowOwnerName", "")),
                        title=str(w.get("kCGWindowName", "") or ""), layer=int(w.get("kCGWindowLayer", 0)),
                        pid=int(w.get("kCGWindowOwnerPID", 0)),
                        bounds=(float(b.get("X", 0)), float(b.get("Y", 0)), float(b.get("Width", 0)), float(b.get("Height", 0)))))
    return out  # front to back


def find_minecraft_window(title_hint="Minecraft"):
    """The largest normal window whose title or owner mentions Minecraft (the game runs as `java`)."""
    cands = [w for w in list_windows() if w["layer"] == 0 and (title_hint.lower() in w["title"].lower()
             or title_hint.lower() in w["owner"].lower()) and w["bounds"][2] > 200]
    if not cands:
        return None
    return max(cands, key=lambda w: w["bounds"][2] * w["bounds"][3])


def frontmost_window_id():
    for w in list_windows():
        if w["layer"] == 0 and w["bounds"][2] > 50:
            return w["id"]
    return None


def capture_window(window_id, crop_title_bar=True):
    """RGB uint8 image of one window's content (works while other windows overlap it)."""
    _need_quartz()
    img = Q.CGWindowListCreateImage(Q.CGRectNull, Q.kCGWindowListOptionIncludingWindow, window_id,
                                    Q.kCGWindowImageBoundsIgnoreFraming | Q.kCGWindowImageNominalResolution)
    if img is None:
        return None
    w, h = Q.CGImageGetWidth(img), Q.CGImageGetHeight(img)
    bpr = Q.CGImageGetBytesPerRow(img)
    buf = Q.CGDataProviderCopyData(Q.CGImageGetDataProvider(img))
    arr = np.frombuffer(buf, np.uint8).reshape(h, bpr // 4, 4)[:, :w]
    rgb = arr[..., [2, 1, 0]].copy()  # BGRA -> RGB
    if crop_title_bar:
        rgb = rgb[title_bar_px(h):]
    return rgb


def title_bar_px(height):
    # 28 pt title bar at nominal resolution; full-screen windows have none.
    try:
        screen_h = Q.CGDisplayBounds(Q.CGMainDisplayID()).size.height
    except Exception:
        screen_h = 0
    return 0 if abs(height - screen_h) < 2 else 28


def cursor_visible():
    """False while Minecraft has grabbed the mouse (in game), True in menus and inventories."""
    try:
        return bool(Q.CGCursorIsVisible())
    except Exception:
        return False


# --------------------------------------------------------------------------- reading input (recorder)

class InputListener:
    """Listen-only event tap. Tracks held keys, mouse buttons, mouse deltas and scroll since the last snapshot()."""

    def __init__(self):
        _need_quartz()
        self.lock = threading.Lock()
        self.keys = set()
        self.new_keys = []
        self.buttons = set()
        self.new_buttons = []
        self.dx = self.dy = self.dwheel = 0.0
        self.mouse_xy = (0.0, 0.0)
        self.human_presses = 0  # key/button presses not posted by the agent (used as a stop signal)
        self.last_human_key = None
        self._loop = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        time.sleep(0.2)
        return self

    def _cb(self, proxy, etype, event, refcon):
        if Q.CGEventGetIntegerValueField(event, Q.kCGEventSourceUserData) == AGENT_TAG:
            return event
        with self.lock:
            if etype in (Q.kCGEventKeyDown, Q.kCGEventLeftMouseDown, Q.kCGEventRightMouseDown, Q.kCGEventOtherMouseDown):
                self.human_presses += 1
                if etype == Q.kCGEventKeyDown:
                    self.last_human_key = CODE_TO_KEY.get(Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode))
            if etype in (Q.kCGEventKeyDown, Q.kCGEventKeyUp):
                code = Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode)
                k = CODE_TO_KEY.get(code)
                if k:
                    if etype == Q.kCGEventKeyDown:
                        if k not in self.keys:
                            self.new_keys.append(k)
                        self.keys.add(k)
                    else:
                        self.keys.discard(k)
            elif etype == Q.kCGEventFlagsChanged:
                code = Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode)
                k, mask = CODE_TO_KEY.get(code), MODIFIER_CODES.get(code)
                if k and mask:
                    if Q.CGEventGetFlags(event) & mask:
                        if k not in self.keys:
                            self.new_keys.append(k)
                        self.keys.add(k)
                    else:
                        self.keys.discard(k)
            elif etype in (Q.kCGEventMouseMoved, Q.kCGEventLeftMouseDragged, Q.kCGEventRightMouseDragged,
                           Q.kCGEventOtherMouseDragged):
                self.dx += Q.CGEventGetIntegerValueField(event, Q.kCGMouseEventDeltaX)
                self.dy += Q.CGEventGetIntegerValueField(event, Q.kCGMouseEventDeltaY)
                loc = Q.CGEventGetLocation(event)
                self.mouse_xy = (loc.x, loc.y)
            elif etype in (Q.kCGEventLeftMouseDown, Q.kCGEventRightMouseDown, Q.kCGEventOtherMouseDown):
                b = {Q.kCGEventLeftMouseDown: 0, Q.kCGEventRightMouseDown: 1}.get(etype, 2)
                self.buttons.add(b)
                self.new_buttons.append(b)
            elif etype in (Q.kCGEventLeftMouseUp, Q.kCGEventRightMouseUp, Q.kCGEventOtherMouseUp):
                b = {Q.kCGEventLeftMouseUp: 0, Q.kCGEventRightMouseUp: 1}.get(etype, 2)
                self.buttons.discard(b)
            elif etype == Q.kCGEventScrollWheel:
                self.dwheel += Q.CGEventGetIntegerValueField(event, Q.kCGScrollWheelEventDeltaAxis1)
        return event

    def _run(self):
        types = [Q.kCGEventKeyDown, Q.kCGEventKeyUp, Q.kCGEventFlagsChanged, Q.kCGEventMouseMoved,
                 Q.kCGEventLeftMouseDragged, Q.kCGEventRightMouseDragged, Q.kCGEventOtherMouseDragged,
                 Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp, Q.kCGEventRightMouseDown, Q.kCGEventRightMouseUp,
                 Q.kCGEventOtherMouseDown, Q.kCGEventOtherMouseUp, Q.kCGEventScrollWheel]
        mask = 0
        for t in types:
            mask |= Q.CGEventMaskBit(t)
        tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap, Q.kCGEventTapOptionListenOnly,
                                 mask, self._cb, None)
        if tap is None:
            raise RuntimeError("could not create the event tap: allow Input Monitoring for this app in System Settings")
        src = Q.CFMachPortCreateRunLoopSource(None, tap, 0)
        self._loop = Q.CFRunLoopGetCurrent()
        Q.CFRunLoopAddSource(self._loop, src, Q.kCFRunLoopCommonModes)
        Q.CGEventTapEnable(tap, True)
        Q.CFRunLoopRun()

    def snapshot(self):
        """Input state for one tick; deltas, new keys and scroll reset after reading."""
        with self.lock:
            s = dict(keys=sorted(self.keys), new_keys=list(self.new_keys), buttons=sorted(self.buttons),
                     new_buttons=list(self.new_buttons), dx=self.dx, dy=self.dy, dwheel=self.dwheel, xy=self.mouse_xy)
            self.new_keys.clear()
            self.new_buttons.clear()
            self.dx = self.dy = self.dwheel = 0.0
        return s

    def stop(self):
        if self._loop is not None:
            Q.CFRunLoopStop(self._loop)


# --------------------------------------------------------------------------- posting input (live agent)

class InputPoster:
    """Posts key, mouse-button and mouse-delta events. Tracks what it holds so release_all() can let go."""

    def __init__(self):
        _need_quartz()
        self.held_keys = set()
        self.held_buttons = set()
        self.flags = 0

    def key(self, name, down):
        code = KEYCODES[name]
        if code in MODIFIER_CODES:
            self.flags = (self.flags | MODIFIER_CODES[code]) if down else (self.flags & ~MODIFIER_CODES[code])
        ev = Q.CGEventCreateKeyboardEvent(None, code, bool(down))
        if code in MODIFIER_CODES:
            Q.CGEventSetType(ev, Q.kCGEventFlagsChanged)
        Q.CGEventSetFlags(ev, self.flags)
        self._post(ev)
        (self.held_keys.add if down else self.held_keys.discard)(name)

    @staticmethod
    def _post(ev):
        Q.CGEventSetIntegerValueField(ev, Q.kCGEventSourceUserData, AGENT_TAG)
        Q.CGEventPost(Q.kCGHIDEventTap, ev)

    def move_to(self, x, y):
        """Absolute cursor move (menus and inventories, where Minecraft follows the cursor position)."""
        ev = Q.CGEventCreateMouseEvent(None, Q.kCGEventMouseMoved, Q.CGPointMake(x, y), Q.kCGMouseButtonLeft)
        self._post(ev)

    def _pos(self):
        return Q.CGEventGetLocation(Q.CGEventCreate(None))

    def button(self, b, down):
        types = {0: (Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp, Q.kCGMouseButtonLeft),
                 1: (Q.kCGEventRightMouseDown, Q.kCGEventRightMouseUp, Q.kCGMouseButtonRight),
                 2: (Q.kCGEventOtherMouseDown, Q.kCGEventOtherMouseUp, Q.kCGMouseButtonCenter)}[b]
        ev = Q.CGEventCreateMouseEvent(None, types[0] if down else types[1], self._pos(), types[2])
        Q.CGEventSetFlags(ev, self.flags)
        self._post(ev)
        (self.held_buttons.add if down else self.held_buttons.discard)(b)

    def move(self, dx, dy):
        """Relative mouse motion, as Minecraft reads it while the cursor is grabbed."""
        dx, dy = int(round(dx)), int(round(dy))
        if dx == 0 and dy == 0:
            return
        if 0 in self.held_buttons:
            etype, btn = Q.kCGEventLeftMouseDragged, Q.kCGMouseButtonLeft
        elif 1 in self.held_buttons:
            etype, btn = Q.kCGEventRightMouseDragged, Q.kCGMouseButtonRight
        else:
            etype, btn = Q.kCGEventMouseMoved, Q.kCGMouseButtonLeft
        ev = Q.CGEventCreateMouseEvent(None, etype, self._pos(), btn)
        Q.CGEventSetIntegerValueField(ev, Q.kCGMouseEventDeltaX, dx)
        Q.CGEventSetIntegerValueField(ev, Q.kCGMouseEventDeltaY, dy)
        self._post(ev)

    def scroll(self, lines):
        ev = Q.CGEventCreateScrollWheelEvent(None, Q.kCGScrollEventUnitLine, 1, int(lines))
        self._post(ev)

    def release_all(self):
        for k in list(self.held_keys):
            self.key(k, False)
        for b in list(self.held_buttons):
            self.button(b, False)
