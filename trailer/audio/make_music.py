"""Original trailer music, synthesised with numpy only. 128 BPM, A minor. No samples, no copyrighted material.
usage: make_music.py main|vertical out.wav
Bars are 1.875 s. Section names per bar are in LAYOUT; the visual cuts in trailer/src are placed on the same bar lines."""
import sys, wave
import numpy as np

SR = 44100
BEAT = 60 / 128
BAR = 4 * BEAT
LAYOUT = {
    # 40 bars = 75 s
    "main": ["intro"] * 4 + ["groove"] * 8 + ["groove2"] * 4 + ["riser"] * 4 + ["drop"] * 8 + ["brk"] * 7 + ["brkup"] + ["drop", "drop", "hit", "tail"],
    # 16 bars = 30 s
    "vertical": ["intro"] * 2 + ["groove", "groove", "groove2", "groove2"] + ["riser"] * 2 + ["drop"] * 4 + ["brk", "brkup"] + ["drop", "hit"],
}
ROOTS = [55.0, 43.65, 65.41, 49.0]  # A1 F1 C2 G1
CHORDS = [[220.0, 261.63, 329.63], [174.61, 220.0, 261.63], [261.63, 329.63, 392.0], [196.0, 246.94, 293.66]]
rng = np.random.default_rng(7)


def tt(n):
    return np.arange(int(n * SR)) / SR


def lp_noise(n, k):
    x = rng.standard_normal(int(n * SR))
    out = np.cumsum(x)
    return x if k == 0 else np.convolve(x, np.ones(k) / k, mode="same")


def hp(x):
    return np.concatenate([[0], np.diff(x)])


def kick():
    t = tt(0.42)
    ph = 2 * np.pi * np.cumsum(46 + 130 * np.exp(-t * 32)) / SR
    return np.tanh(2.2 * np.sin(ph) * np.exp(-t * 7.5)) * 0.95 + 0.25 * hp(rng.standard_normal(len(t))) * np.exp(-t * 400)


def clap():
    t = tt(0.3)
    n = hp(rng.standard_normal(len(t)))
    env = np.exp(-t * 20) + 0.6 * np.exp(-((t - 0.012) ** 2) * 2e4) + 0.5 * np.exp(-((t - 0.024) ** 2) * 2e4)
    return n * env * 0.55 + np.sin(2 * np.pi * 190 * t) * np.exp(-t * 35) * 0.3


def hat(open_=False):
    t = tt(0.35 if open_ else 0.07)
    n = hp(hp(rng.standard_normal(len(t))))
    return n * np.exp(-t * (16 if open_ else 90)) * 0.28


def saw(f, t, maxf=7000):
    out = np.zeros(len(t))
    k = 1
    while f * k < maxf and k < 40:
        out += np.sin(2 * np.pi * f * k * t) / k
        k += 1
    return out * 0.55


def bass(f, dur):
    t = tt(dur)
    s = np.sin(2 * np.pi * f * t) + 0.5 * np.sin(4 * np.pi * f * t) + 0.25 * np.sin(6 * np.pi * f * t) * np.exp(-t * 6)
    env = np.minimum(1, t / 0.004) * np.minimum(1, (dur - t) / 0.02)
    return np.tanh(1.6 * s) * env * 0.5


def stab(freqs, dur=0.26):
    t = tt(dur)
    L = np.zeros(len(t))
    R = np.zeros(len(t))
    for f in freqs:
        for d, side in ((0.994, 0), (1.0, 1), (1.006, 2)):
            v = saw(f * d, t, 5200)
            if side != 2:
                L += v * (0.7 if side == 0 else 0.5)
            if side != 0:
                R += v * (0.7 if side == 2 else 0.5)
    env = np.minimum(1, t / 0.003) * np.exp(-t * 11) * np.minimum(1, (dur - t) / 0.02)
    return L * env * 0.16, R * env * 0.16


def pluck(f, dur=0.3):
    t = tt(dur)
    s = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t)
    return s * np.exp(-t * 14) * np.minimum(1, t / 0.002) * 0.22


def pad(freqs, dur):
    t = tt(dur)
    L = np.zeros(len(t)); R = np.zeros(len(t))
    for i, f in enumerate(freqs):
        for d in (0.997, 1.003):
            v = np.sin(2 * np.pi * f * d * t + i) + 0.4 * np.sin(4 * np.pi * f * d * t)
            L += v * (0.6 if d < 1 else 0.4)
            R += v * (0.4 if d < 1 else 0.6)
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.5
    return L * env * 0.07, R * env * 0.07


def riser(dur):
    t = tt(dur)
    x = t / dur
    ph = 2 * np.pi * np.cumsum(180 * 2 ** (x * 4.2)) / SR
    tone = (np.sin(ph) + 0.5 * np.sin(2 * ph)) * 0.12
    n = hp(rng.standard_normal(len(t))) * (x ** 2.2) * 0.35
    return (tone + n) * x ** 1.3


def impact(dur=2.2):
    t = tt(dur)
    boom = np.sin(2 * np.pi * 38 * t - 6 * np.exp(-t * 2)) * np.exp(-t * 2.0) * 0.9
    crash = hp(rng.standard_normal(len(t))) * np.exp(-t * 2.6) * 0.45
    return np.tanh(boom * 1.4) + crash


def build(name, out):
    layout = LAYOUT[name]
    total = len(layout) * BAR
    N = int(total * SR) + SR * 2
    L = np.zeros(N, dtype=np.float64); R = np.zeros(N, dtype=np.float64)
    musicL = np.zeros(N); musicR = np.zeros(N)  # sidechained group
    kick_times = []

    def put(buf, sig, t0, g=1.0):
        i = int(t0 * SR)
        if i >= N:
            return
        m = min(len(sig), N - i)
        buf[i:i + m] += sig[:m] * g

    def putst(sig, t0, g=1.0, pan=0.0, group=False):
        a, b = (musicL, musicR) if group else (L, R)
        put(a, sig, t0, g * (1 - max(0, pan)))
        put(b, sig, t0, g * (1 + min(0, pan)))

    K, CL, HC, HO = kick(), clap(), hat(), hat(True)
    for bar, sec in enumerate(layout):
        t0 = bar * BAR
        ch = CHORDS[bar % 4]
        root = ROOTS[bar % 4]
        kicks = sec in ("groove", "groove2", "riser", "drop", "hit", "brk", "brkup")
        if sec == "intro":
            if bar % 2 == 0 or bar == 0:
                putst(K, t0, 0.5); kick_times.append(t0)
            if bar == 3 or name == "vertical" and bar == 1:
                for s in range(8):
                    putst(HC, t0 + s * BEAT / 2, 0.5)
        if sec in ("groove", "groove2", "drop", "hit", "brk", "brkup"):
            g = 0.55 if sec in ("brk", "brkup") else 1.0
            for b in range(4):
                putst(K, t0 + b * BEAT, g); kick_times.append(t0 + b * BEAT)
        if sec == "riser":
            for b in range(4):
                if not (bar == len(layout) - 1 or layout[min(bar + 1, len(layout) - 1)] != "riser") or b < 3:
                    putst(K, t0 + b * BEAT, 0.8 if b % 2 == 0 else 0.55); kick_times.append(t0 + b * BEAT)
        if sec in ("groove", "groove2", "drop", "hit"):
            for b in (1, 3):
                putst(CL, t0 + b * BEAT, 0.8 if sec != "groove" else 0.55)
            for s in range(8):
                putst(HO if s % 2 == 1 else HC, t0 + s * BEAT / 2 + (0 if s % 2 else 0), 0.6 if s % 2 else 0.35)
        if sec == "drop":
            for s in range(16):
                putst(HC, t0 + s * BEAT / 4, 0.3)
        if sec in ("groove", "groove2", "drop", "hit"):
            pat = [0, 2, 3, 5, 6, 7] if sec == "drop" else [0, 1, 2, 3, 4, 5, 6, 7]
            for s in range(8):
                if sec == "drop":
                    f = root * (2 if s % 4 == 3 else 1)
                    for q in (0, 1):
                        putst(bass(f, BEAT / 2 * 0.8), t0 + s * BEAT / 2 + q * BEAT / 4, 0.8, group=True)
                else:
                    putst(bass(root * (2 if s % 4 == 3 else 1), BEAT / 2 * 0.85), t0 + s * BEAT / 2, 0.85, group=True)
        if sec in ("brk", "brkup"):
            putst(bass(root, BAR * 0.95), t0, 0.7, group=True)
        if sec in ("groove2", "drop", "brk", "brkup", "hit"):
            n = 16 if sec in ("drop", "hit") else 8
            seq = [ch[0] * 2, ch[1] * 2, ch[2] * 2, ch[1] * 2, ch[0] * 4, ch[2] * 2, ch[1] * 2, ch[2] * 4]
            for s in range(n):
                f = seq[s % 8] * (2 if s % 8 in (4, 7) and sec == "drop" else 1)
                putst(pluck(f), t0 + s * BAR / n, 0.8 if sec != "brk" else 0.6, pan=0.35 if s % 2 else -0.35, group=True)
        if sec in ("drop", "hit", "groove2"):
            hits = [0, 3, 6, 10, 12] if sec == "drop" else [2, 6]
            for s in hits:
                a, b = stab(ch, 0.26)
                put(musicL, a, t0 + s * BEAT / 4, 1.0); put(musicR, b, t0 + s * BEAT / 4, 1.0)
        if sec in ("intro", "groove", "brk", "brkup", "tail", "hit"):
            a, b = pad(ch, BAR * 1.15)
            put(musicL, a, t0, 1.5 if sec in ("intro", "tail", "brk") else 1.0); put(musicR, b, t0, 1.5 if sec in ("intro", "tail", "brk") else 1.0)
        if sec == "riser" and (bar == 0 or layout[bar - 1] != "riser"):
            cnt = sum(1 for x in layout if x == "riser")
            r = riser(cnt * BAR - BEAT)
            put(L, r, t0, 1.0); put(R, r[::-1] if False else r, t0, 1.0)
            # snare roll: 8ths, then 16ths, then 32nds; last beat left empty (the gap before the drop)
            steps = int(cnt * BAR / BEAT * 2)
            for i in range(steps):
                tt_ = t0 + i * BEAT / 2
                rate = 1 if i < steps * 0.4 else 2 if i < steps * 0.8 else 4
                for q in range(rate):
                    tq = tt_ + q * BEAT / (2 * rate)
                    if tq < t0 + cnt * BAR - BEAT:
                        putst(CL, tq, 0.25 + 0.6 * (i / steps))
        if sec == "brkup":
            for i in range(16):
                putst(CL, t0 + i * BEAT / 4 + (0 if i < 8 else 0), 0.2 + 0.5 * i / 16)
            r = riser(BAR); put(L, r, t0, 0.8); put(R, r, t0, 0.8)
        if sec == "intro" and bar == len(layout) and False:
            pass
        if sec in ("drop", "hit") and (bar == 0 or layout[bar - 1] != sec or sec == "hit"):
            im = impact(2.2 if sec == "hit" else 1.8)
            putst(im, t0, 1.0 if sec == "hit" else 0.9)
            if sec == "hit":
                kick_times.append(t0)
        if sec == "tail":
            pass
    # sidechain: music group ducks on every kick
    sc = np.ones(N)
    n = int(0.28 * SR)
    curve = 1 - 0.7 * np.exp(-np.arange(n) / SR * 14)
    for kt in kick_times:
        i = int(kt * SR)
        m = min(n, N - i)
        if m > 0:
            sc[i:i + m] = np.minimum(sc[i:i + m], curve[:m])
    L += musicL * sc; R += musicR * sc
    # the empty last beat of every riser: hard gap, 4 ms fades
    for bar, sec in enumerate(layout):
        if sec == "riser" and (bar + 1 == len(layout) or layout[bar + 1] != "riser"):
            a = int((bar * BAR + 3 * BEAT) * SR)
            b = int((bar + 1) * BAR * SR)
            g = np.ones(N)
            f = int(0.004 * SR)
            g[a:b] = 0
            g[a - f:a] = np.linspace(1, 0, f)
            L *= g; R *= g
    # tail: fade to silence at the end of the video
    end = int(total * SR)
    fade = int(1.4 * SR)
    env = np.ones(N); env[end - fade:end] = np.linspace(1, 0, fade) ** 1.6; env[end:] = 0
    L *= env; R *= env
    L = L[:end]; R = R[:end]
    # master: soft clip, normalise to about -1.5 dBFS peak
    mix = np.stack([L, R], axis=1)
    mix = np.tanh(mix * 1.15)
    mix = mix / max(1e-9, np.abs(mix).max()) * 0.84
    mix[: int(0.01 * SR)] *= np.linspace(0, 1, int(0.01 * SR))[:, None]
    pcm = (mix * 32767).astype(np.int16)
    with wave.open(out, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"{name}: {total:.2f}s, {len(layout)} bars, {len(kick_times)} kicks -> {out}")


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
