"""Score for the theatrical trailer: 90.0 s, 80 BPM, 30 bars of 3.0 s, D minor to D major.
Braams and low brass, taiko and timpani builds, choir, string ostinato, hard stops into silence, and one final massive hit.
Real sampled instruments (MuseScore_General SoundFont, MIT) through the music-lab toolkit; rendered file committed as theatrical.mp3.
usage: python3 theatrical_score.py out.wav     (needs ~/music-lab/tools)

Form (bar = 3 s)            time      what
 1        silence           0-3
 2-3      braam, drone      3-9       one low braam on the downbeat of bar 2, then a rumble
 4        heartbeat         9-12      soft timpani, tremolo strings rising
 5-7      three hits        12,15,18  braam + taiko + cymbal; hard stop at 20.25
 8        silence           21-24
 9        THE hit           24        full orchestra, choir, taiko roll
 10-12    ostinato          27-36     string 16ths, low brass pulse, hit at 33
 13-18    hero              36-54     choir, horn theme, taiko half-time, swell
 19       pull back         54-57     piano and strings
 20-21    fanfare           57-63     trumpets, snare roll, hits at 57 and 60; hard stop at 62.25
 22       one low note      63-66     silence to 64.5, then one low piano note
 23-25    clock build       66-75     woodblock tick (beats, 8ths, 16ths), ostinato, riser; stop at 73.5
 26       THE BIGGEST HIT   75-78     everything; second hit at 76.5
 27       tagline           78-81     piano and strings
 28-30    end card          81-90     resolution in D major, final chord rings"""
import os, sys, subprocess, tempfile
import numpy as np

sys.path.insert(0, os.path.expanduser("~/music-lab/tools"))
from lint import lint
from produce import produce
from smf import Song

rng = np.random.default_rng(23)
BPM = 80
song = Song(bpm=BPM, key="D", mode="minor")
piano = song.track("Piano", 0, program=0, role="harmony")
ost = song.track("Strings", 1, program=48, role="harmony")
trem = song.track("Tremolo", 2, program=44, role="pad")
choir = song.track("Choir", 3, program=52, role="pad")
horn = song.track("Horns", 4, program=60, role="lead")
trump = song.track("Trumpets", 5, program=56, role="lead")
tuba = song.track("Tuba", 6, program=58, role="bass")
bone = song.track("Trombones", 7, program=57, role="pad")
timp = song.track("Timpani", 8, program=47, role="bass")
taiko = song.track("Taiko", 10, program=116, role="bass")
cello = song.track("Cello", 11, program=42, role="bass")
cbass = song.track("Contrabass", 12, program=43, role="bass")
ohit = song.track("OrchHit", 13, program=55, role="fx")
wood = song.track("Woodblock", 14, program=115, role="fx")
drums = song.track("Drums", 9, program=48, role="drums")

B = lambda bar, beat=0.0: (bar - 1) * 4 + beat  # beat position of a bar/beat
CH = {"Dm": (2, "min", [50, 53, 57, 62]), "Bb": (10, "maj", [46, 50, 53, 58]), "F": (5, "maj", [53, 57, 60, 65]),
      "C": (0, "maj", [48, 52, 55, 60]), "A": (9, "maj", [45, 49, 52, 57]), "D": (2, "maj", [50, 54, 57, 62]), "Gm": (7, "min", [55, 58, 62, 67])}
ROOT = {"Dm": 38, "Bb": 34, "F": 41, "C": 36, "A": 33, "D": 38, "Gm": 43}  # low root (tuba/cello register)
PROG = {}
for b in range(1, 31):
    PROG[b] = "Dm"
for b, c in ((13, "Dm"), (14, "Bb"), (15, "F"), (16, "C"), (17, "Bb"), (18, "A"), (19, "Dm"), (20, "Bb"), (21, "F"), (22, "Dm"), (23, "Dm"), (24, "Bb"), (25, "A"),
             (26, "Dm"), (27, "Bb"), (28, "D"), (29, "A"), (30, "D"), (10, "Dm"), (11, "Bb"), (12, "F"), (9, "Dm"), (27, "Bb")):
    PROG[b] = c
for b in range(5, 9):
    PROG[b] = ["Dm", "Bb", "F", "Dm"][b - 5]


def hv(v, s=4):
    return int(np.clip(v + rng.normal(0, s), 1, 127))


def stack(tr, beat, ln, pitches, vel, s=3):
    for p in pitches:
        if tr is choir and p < 48:
            p += 12
        tr.note(beat + rng.normal(0, 0.01), ln, p, hv(vel, s))


def hit(bar, beat, vel=118, name="Dm", big=False, ln=3.0, cymbal=True):
    """A trailer hit: orchestra hit, low brass chord, timpani, taiko, bass drum and a cymbal."""
    root, q, tri = CH[name]
    b0 = B(bar, beat)
    ohit.note(b0, 1.0, tri[1] + 12, hv(vel, 9))
    stack(tuba, b0, ln, [ROOT[name]], vel)
    stack(bone, b0, ln, [tri[0], tri[2]], vel - 6)
    stack(horn, b0, ln, [tri[2] + 12, tri[3] + 0], vel - 10)
    cbass.note(b0, ln, ROOT[name] - 12 if ROOT[name] - 12 >= 28 else ROOT[name], hv(vel))
    timp.note(b0, 1.5, 38 + 12 if root == 2 else 40 + (root - 4) % 12, hv(vel + 5 if big else vel))
    taiko.note(b0, 1.0, ROOT[name] + 12, hv(vel + 5))
    taiko.note(b0, 1.0, ROOT[name] + 19, hv(vel))
    drums.note(b0, 0.5, 36, hv(vel + 6))
    if cymbal:
        drums.note(b0, 3.0, 49 if not big else 57, hv(vel))
    if big:
        stack(choir, b0, ln, tri, vel - 20)
        stack(trump, b0, ln, [tri[2] + 12, tri[3] + 12], vel - 14)


for bar in range(1, 31):
    b0 = B(bar)
    nm = PROG[bar]
    root, q, tri = CH[nm]
    song.chord(b0, 4, root, q)
    r = ROOT[nm]

# --- bar 2-3: one low braam, then a rumble
hit(2, 0, vel=124, name="Dm", big=False, ln=6.5, cymbal=False)
cbass.cc(B(2), 11, 127); cbass.cc(B(2, 3), 11, 90); cbass.cc(B(3, 0), 11, 60); cbass.cc(B(3, 3), 11, 40)
for t_ in (tuba, bone, horn):
    t_.cc(B(2), 11, 127); t_.cc(B(2, 3.5), 11, 80); t_.cc(B(3, 2), 11, 45)
for k in range(0, 8):  # rumble: low timpani roll fading
    timp.note(B(3, 0) + k * 0.5, 0.5, 50, hv(60 - k * 4, 3))
stack(cello, B(3), 4.0, [26 + 12], 40)
# --- bar 4: heartbeat and a rising tremolo
for k, (beat, v) in enumerate(((0, 50), (0.5, 38), (2, 62), (2.5, 46), (3.25, 70))):
    timp.note(B(4, beat), 0.4, 50, hv(v, 2))
stack(trem, B(4), 4.0, [50, 57, 62], 30)
trem.cc(B(4), 11, 40); trem.cc(B(4, 4), 11, 120)
# --- bars 5-7: three hits
hit(5, 0, 118, "Dm", ln=2.9)
hit(6, 0, 120, "Bb", ln=2.9)
taiko.note(B(6, 2), 0.5, 46, hv(100)); taiko.note(B(6, 2.5), 0.5, 46, hv(96))
hit(7, 0, 124, "F", big=True, ln=2.25)  # ends at 20.25 s: hard stop
taiko.note(B(7, 1.5), 0.3, 53, hv(110)); taiko.note(B(7, 2.0), 0.25, 53, hv(112))
for bar in (5, 6):  # tremolo bed between hits
    stack(trem, B(bar, 1), 2.0, CH[PROG[bar]][2][:3], 50)
# --- bar 9: THE hit
hit(9, 0, 127, "Dm", big=True, ln=11.0)
for k in range(8):
    taiko.note(B(9, 1.0) + k * 0.25, 0.25, 50 if k % 2 == 0 else 57, hv(70 + k * 4, 3))
for bar in (9, 10, 11, 12):
    stack(trem, B(bar), 4.0, CH[PROG[bar]][2][:3], 48)
# --- bars 10-12: string ostinato + low brass pulse + taiko; hit at 33 s (bar 12 beat 0)
for bar in (10, 11, 12):
    nm = PROG[bar]; root, q, tri = CH[nm]
    for e in range(16):
        p = tri[[0, 1, 2, 1, 3, 2, 1, 2][e % 8]] + 12
        ost.note(B(bar) + e * 0.25, 0.22, p, hv(66 + (bar - 10) * 6 + (10 if e % 4 == 0 else 0), 4))
    for beat in range(4):
        tuba.note(B(bar, beat), 0.9, ROOT[nm], hv(84, 3))
        taiko.note(B(bar, beat), 0.4, ROOT[nm] + 12, hv(78, 3))
    cello.note(B(bar), 4.0, ROOT[nm] + 12, hv(90))
hit(12, 0, 118, "F", ln=1.2, cymbal=True)
# --- bars 13-18: hero. choir, horn theme, half-time taiko, swell
HERO = {13: [(0, 2, 62), (2, 1, 65), (3, 1, 69)], 14: [(0, 3, 70), (3, 1, 65)], 15: [(0, 2, 65), (2, 1, 69), (3, 1, 72)], 16: [(0, 4, 74)],
        17: [(0, 2, 72), (2, 2, 70)], 18: [(0, 2, 69), (2, 2, 73)]}
for bar in range(13, 19):
    nm = PROG[bar]; root, q, tri = CH[nm]
    v = 80 + (bar - 13) * 5
    stack(choir, B(bar), 3.9, tri, v - 12, 4)
    stack(choir, B(bar), 3.9, [tri[0] + 12, tri[2] + 12], v - 20, 4)
    stack(bone, B(bar), 3.9, [tri[0], tri[2]], v - 14)
    cello.note(B(bar), 4.0, ROOT[nm] + 12, hv(v)); cbass.note(B(bar), 4.0, ROOT[nm] if ROOT[nm] >= 28 else ROOT[nm] + 12, hv(v - 6))
    for beat, ln, p in HERO[bar]:
        horn.note(B(bar, beat), ln * 0.97, p, hv(v + 14 + (6 if beat == 0 else 0), 3))
        trump.note(B(bar, beat), ln * 0.97, p + 12 if p + 12 <= 84 else p, hv(v - 6 if bar >= 15 else 0, 3)) if bar >= 15 else None
    taiko.note(B(bar), 0.5, ROOT[nm] + 12, hv(96)); taiko.note(B(bar, 2), 0.5, ROOT[nm] + 19, hv(88))
    for e in range(8):
        ost.note(B(bar) + e * 0.5, 0.45, tri[[1, 2, 3, 2][e % 4]] + 12, hv(56 + (bar - 13) * 3, 4))
    if bar in (14, 16, 18):
        drums.note(B(bar), 3.0, 57, hv(84))
timp.note(B(18, 3), 0.25, 45, hv(100)); timp.note(B(18, 3.25), 0.25, 45, hv(104)); timp.note(B(18, 3.5), 0.25, 45, hv(108)); timp.note(B(18, 3.75), 0.25, 45, hv(114))
# --- bar 19: pull back for the quotes
piano.cc(B(19), 64, 127)
for e, p in enumerate([50, 57, 62, 65, 69, 65, 62, 57]):
    piano.note(B(19) + e * 0.5, 0.6, p, hv(52, 4))
piano.cc(B(19, 3.9), 64, 0)
stack(trem, B(19), 4.0, [50, 57, 62], 44)
# --- bars 20-21: fanfare, snare roll, hits at 57 and 60; hard stop at 62.25
FANS = {20: [(0, 1, 62), (1, 0.5, 65), (1.5, 0.5, 70), (2, 2, 74)], 21: [(0, 1, 65), (1, 0.5, 69), (1.5, 0.5, 72), (2, 2, 77)]}
for bar in (20, 21):
    nm = PROG[bar]; root, q, tri = CH[nm]
    for beat, ln, p in FANS[bar]:
        trump.note(B(bar, beat), ln * 0.95, p, hv(104, 3))
        horn.note(B(bar, beat), ln * 0.95, p - 12, hv(96, 3))
    stack(bone, B(bar), 3.0 if bar == 20 else 2.25, [tri[0], tri[2]], 90)
    stack(tuba, B(bar), 3.0 if bar == 20 else 2.25, [ROOT[nm]], 100)
    taiko.note(B(bar), 0.5, ROOT[nm] + 12, hv(112)); taiko.note(B(bar, 2), 0.5, ROOT[nm] + 19, hv(100))
    for e in range(8 if bar == 20 else 6):
        drums.note(B(bar) + e * 0.5, 0.25, 38, hv(60 + e * 5 + (bar - 20) * 8, 3))
hit(20, 0, 118, "Bb", big=False, ln=2.9)
hit(21, 0, 122, "F", big=True, ln=2.25)
# --- bar 22: one low piano note after the silence (starts 64.5 s = beat 6 of bar 22 is 64.5? bar 22 starts at 63.0 s -> 2.0 beats in)
piano.cc(B(22, 2.0), 64, 127)
piano.note(B(22, 2.0), 6.0, 38, hv(58, 2)); piano.note(B(22, 2.0), 6.0, 50, hv(46, 2))
trem.cc(B(22, 2.0), 11, 30)
stack(trem, B(22, 2.5), 5.5, [50, 57], 30)
# --- bars 23-25: ticking-clock build
for bar in (23, 24, 25):
    nm = PROG[bar]; root, q, tri = CH[nm]
    step = {23: 1.0, 24: 0.5, 25: 0.25}[bar]
    n = int(4 / step)
    for e in range(n):
        wood.note(B(bar) + e * step, 0.1, 76 if e % 4 else 84, hv(80 + (bar - 23) * 10 + (e / n) * 20, 3))
    for e in range(16):
        p = tri[[0, 1, 2, 1, 3, 2, 1, 2][e % 8]] + 12
        ost.note(B(bar) + e * 0.25, 0.22, p, hv(60 + (bar - 23) * 14 + (e / 16) * 10, 4))
    for beat in range(4 if bar == 23 else 8):
        taiko.note(B(bar) + beat * (1 if bar == 23 else 0.5), 0.3, ROOT[nm] + (12 if beat % 2 == 0 else 19), hv(70 + (bar - 23) * 16, 3))
    stack(trem, B(bar), 4.0, tri[:3], 50 + (bar - 23) * 14)
    cello.note(B(bar), 4.0, ROOT[nm] + 12, hv(80 + (bar - 23) * 8)); stack(tuba, B(bar), 4.0, [ROOT[nm]], 60 + (bar - 23) * 12)
# the stop at 73.5 s (bar 25 beat 2) is made by shortening everything at the end of the bar: cut in post (see gate below)
# --- bar 26: THE BIGGEST HIT at 75.0, second at 76.5
hit(26, 0, 127, "Dm", big=True, ln=1.9)
hit(26, 2.0, 127, "Dm", big=True, ln=8.0)
ohit.note(B(26), 1.0, 74, 127); ohit.note(B(26, 2.0), 1.0, 74, 120)
for k in range(12):
    taiko.note(B(26, 0.5) + k * 0.125, 0.125, 50 if k % 2 == 0 else 57, hv(80 + k * 3, 3))
stack(choir, B(26, 2.0), 8.0, [50, 57, 62, 65, 74], 100)
# --- bar 27: tagline, piano and strings
piano.cc(B(27), 64, 127)
for e, p in enumerate([46, 53, 58, 62, 65, 62, 58, 53, 46, 53, 58, 62, 65, 62, 58, 53]):
    piano.note(B(27) + e * 0.25, 0.5, p, hv(54, 4))
piano.cc(B(27, 3.9), 64, 0)
stack(trem, B(27), 4.0, [50, 57, 62], 56)
cello.note(B(27), 4.0, 38 + 12, hv(70))
# --- bars 28-30: end card, resolution to D major
THEME = [(28, 0, 2, 66), (28, 2, 1, 69), (28, 3, 1, 74), (29, 0, 3, 73), (29, 3, 1, 69), (30, 0, 8, 74)]
for bar, beat, ln, p in THEME:
    horn.note(B(bar, beat), ln * 0.97, p, hv(92, 3)); trump.note(B(bar, beat), ln * 0.97, p + 0, hv(74, 3))
for bar in (28, 29, 30):
    nm = PROG[bar]; root, q, tri = CH[nm]
    ln = 4.0 if bar < 30 else 9.0
    stack(choir, B(bar), ln, tri, 80, 4)
    stack(ost, B(bar), ln, [t_ + 12 for t_ in tri[:3]], 70, 3)
    cello.note(B(bar), ln, ROOT[nm] + 12, hv(86)); cbass.note(B(bar), ln, ROOT[nm], hv(80)); stack(bone, B(bar), ln, [tri[0], tri[2]], 78)
    taiko.note(B(bar), 0.5, ROOT[nm] + 12, hv(96))
timp.note(B(30), 2.0, 38 + 12, hv(110)); drums.note(B(30), 4.0, 57, hv(100))
piano.cc(B(30), 64, 127)
piano.note(B(30), 8.0, 38, hv(84)); piano.note(B(30), 8.0, 50, hv(78)); piano.note(B(30, 0.5), 7.0, 66, hv(64))

PLAN = {"_": {"reverb_s": 3.6, "predelay_ms": 40, "duck_key": "Drums", "master_shelf_high": (8000, 5.0), "master_eq": [(55, 5.0, 0.9), (110, 4.5, 0.9), (250, 5.0, 0.8), (400, 0.5, 0.9), (3200, -2.5, 0.8), (4500, 0.0, 0.8)]},
        "Contrabass": {"gain_db": 1, "duck_db": 0, "send": 0.15, "lpf": 2500},
        "Timpani": {"hpf": 35, "lpf": 6000, "comp": (-20, 2, 15, 200), "send": 0.3, "duck_db": 0},
        "Taiko": {"gain_db": -2, "send": 0.3, "duck_db": 0, "hpf": 40},
        "Cello": {"gain_db": -1, "duck_db": 0, "send": 0.2, "shelf_low": (90, 3.0), "eq": [(300, -3, 1.0)]},
        "Tuba": {"gain_db": -1, "duck_db": 0, "send": 0.25, "lpf": 3500},
        "Trombones": {"gain_db": -2, "duck_db": 0, "send": 0.3},
        "Choir": {"gain_db": -4, "send": 0.4},
        "Tremolo": {"duck_db": 0, "eq": [(380, -4, 0.9)], "gain_db": -2},
        "Strings": {"shelf_high": (6000, 4.5), "eq": [(350, -3, 1.0)]},
        "Piano": {"eq": [(300, -2.5, 1.0)], "shelf_high": (5000, 2.0), "send": 0.3},
        "Horns": {"send": 0.35, "eq": [(2500, 2.0, 1.0)]},
        "Trumpets": {"send": 0.35, "gain_db": -1},
        "OrchHit": {"gain_db": -3, "send": 0.3},
        "Woodblock": {"gain_db": 2, "send": 0.1, "duck_db": 0}}

HARD_SILENCE = [(0.0, 2.95), (20.28, 23.97), (62.28, 64.45), (73.5, 74.97)]  # seconds: true silence, 30 ms fades
HITS = [3.0, 12.0, 15.0, 18.0, 24.0, 33.0, 57.0, 60.0, 75.0, 76.5]

if __name__ == "__main__":
    for level, msg in lint(song):
        print(level, msg)
    out = sys.argv[1]
    tmp = tempfile.mkdtemp(prefix="theat-")
    raw = os.path.join(tmp, "raw.wav")
    produce(song, raw, PLAN, target_lufs=-14, length_s=90.0, fade_out_s=1.8)
    from scipy.io import wavfile
    sr, x = wavfile.read(raw)
    x = x.astype(np.float64)
    f = int(0.03 * sr)
    for a, b in HARD_SILENCE:
        i, j = int(a * sr), int(b * sr)
        g = np.ones(len(x))
        g[i:j] = 0
        if i - f >= 0:
            g[i - f:i] = np.linspace(1, 0, f)
        g[j:j + f] = np.maximum(g[j:j + f], np.linspace(0, 1, min(f, len(x) - j)))  # keep the hit's attack intact
        x *= g[:, None] if x.ndim == 2 else g
    wavfile.write(out, sr, np.clip(x, -32768, 32767).astype(np.int16))
    print("hits (s):", HITS)
