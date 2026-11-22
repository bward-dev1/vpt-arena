"""Score for the cinematic trailer cut: 96.0 s, 75 BPM, 30 bars of 3.2 s. A minor lifting to C major.
Made with the music-lab toolkit (real sampled instruments through FluidSynth, MuseScore_General soundfont (MIT)); the rendered
file is committed as cinematic.mp3 so the cloud workflow needs no soundfont.
Form (bar = 3.2 s):  1-4 drone + piano (cold open) | 5-10 strings enter (premise) | 11-19 build, horns at 15, timpani roll 18-19 (learning)
                     20-24 full orchestra (rivals) | 25 hush: one low piano note, nothing else (0 wins) | 26-27 piano, strings rise (Yet.)
                     28-30 resolution in C, final chord rings out (Watch it learn live).
usage: python3 cinematic_score.py out.wav   (needs ~/music-lab/tools)"""
import os, sys
import numpy as np

sys.path.insert(0, os.path.expanduser("~/music-lab/tools"))
from lint import lint
from produce import produce
from smf import Song

rng = np.random.default_rng(11)
BPM = 75
song = Song(bpm=BPM, key="A", mode="minor")
piano = song.track("Piano", 0, program=0, role="harmony")
ost = song.track("StringsFast", 1, program=48, role="harmony")
pad = song.track("StringsSlow", 2, program=49, role="pad")
horn = song.track("Horns", 3, program=60, role="lead")
brass = song.track("LowBrass", 8, program=58, role="pad")  # tuba: the low swells
timp = song.track("Timpani", 4, program=47, role="bass")
choir = song.track("Choir", 5, program=52, role="pad")
cello = song.track("Low", 6, program=42, role="bass")
cbass = song.track("Contrabass", 7, program=43, role="bass")
drums = song.track("Drums", 9, program=48, role="drums")

CH = {"Am": (9, "min", [57, 60, 64]), "F": (5, "maj", [53, 57, 60]), "C": (0, "maj", [55, 60, 64]), "G": (7, "maj", [55, 59, 62])}
CYCLE = ["Am", "F", "C", "G"]
BARS = {1: "Am", 2: "Am", 3: "F", 4: "G", 25: "Am", 26: "Am", 27: "F", 28: "C", 29: "G", 30: "C"}
for b in range(5, 25):
    BARS[b] = CYCLE[(b - 5) % 4]


def hv(v, s=5):
    return int(np.clip(v + rng.normal(0, s), 1, 127))


def ht(b, ms=7):
    return b + rng.normal(0, ms / 1000 * BPM / 60)


def lowroot(root):
    r = 36 + root
    return r if r <= 47 else r - 12


MEL = {"Am": [(0, 2, 64), (2, 1, 67), (3, 1, 69)], "F": [(0, 1.5, 69), (1.5, 0.5, 67), (2, 2, 65)],
       "C": [(0, 2, 64), (2, 1, 67), (3, 1, 72)], "G": [(0, 3, 71), (3, 1, 69)]}

for bar in range(1, 31):
    b0 = (bar - 1) * 4
    name = BARS[bar]
    root, q, tri = CH[name]
    song.chord(b0, 4, root, q)
    lr = lowroot(root)
    # drone under the cold open and the hush
    if bar == 1:
        cbass.note(b0, 4, 33, hv(34, 2))
    if bar == 2:
        cbass.note(b0, 4, 33, hv(40, 2))
        piano.cc(b0, 64, 127)
        piano.note(b0 + 1, 3, 57, hv(44)); piano.note(b0 + 2.5, 1.5, 64, hv(38))
        piano.cc(b0 + 3.9, 64, 0)
    # piano arpeggio (slow eighths), bars 3-14, softer in the opening
    if 3 <= bar <= 14 or 26 <= bar <= 29:
        piano.cc(b0, 64, 127)
        pat = [lr + 12, tri[0], tri[1], tri[2], tri[1] + 12, tri[2], tri[1], tri[0]]
        base = 48 if bar < 5 else 58 if bar < 11 else 66
        if bar >= 26: base = 50 if bar == 26 else 60
        for e, p in enumerate(pat):
            piano.note(ht(b0 + e * 0.5), 0.55, p, hv(base + (10 if e == 0 else 0)))
        piano.cc(b0 + 3.95, 64, 0)
    # slow strings from bar 5; swell on 10 and 18-19; rise at 27
    if 5 <= bar <= 24 or bar >= 27:
        v = 46 if bar < 8 else 58 if bar < 11 else 70 if bar < 15 else 84
        if bar >= 27: v = 62 + 8 * (bar - 27)
        if bar in (9, 10): v = 66 + 6 * (bar - 9)
        for p in tri:
            pad.note(ht(b0, 3), 4.0, p, hv(v, 3))
    if 8 <= bar <= 24 or bar >= 27:
        # fast strings ostinato (eighths), quiet until bar 15
        v0 = 46 if bar < 15 else 72
        if bar >= 27: v0 = 50 + 10 * (bar - 27)
        for e in range(8):
            p = tri[[0, 1, 2, 1][e % 4]] + 12
            ost.note(ht(b0 + e * 0.5, 4), 0.48, p, hv(v0 + (10 if e % 2 == 0 else 0), 4))
    # cellos / basses
    if 6 <= bar <= 24 or bar >= 27:
        v = 70 if bar < 11 else 84 if bar < 20 else 98
        if bar >= 27: v = 70 + 8 * (bar - 27)
        cello.note(b0, 4, lr, hv(v, 3))
        if bar >= 8:
            cbass.note(b0, 4, lr - 12 if lr - 12 >= 28 else lr, hv(v - 6, 4))
    # timpani: single hits on downbeats from bar 13, roll in 18-19, full bars 20-24
    if 13 <= bar <= 17:
        timp.note(b0, 2, lr + 12 if lr + 12 <= 57 else lr, hv(64 + (bar - 13) * 4))
    if bar in (18, 19):
        for k in range(16):
            timp.note(b0 + k * 0.25, 0.25, 45 if bar == 18 else 50, hv(40 + (bar - 18) * 30 + k * 2.5, 3))
    if 20 <= bar <= 23:
        timp.note(b0, 1.5, lr + 12 if lr + 12 <= 57 else lr, hv(112))
        timp.note(b0 + 2, 1.5, lr + 7 if lr + 7 <= 57 else lr, hv(92))
        drums.note(b0, 0.5, 36, hv(104)); drums.note(b0 + 2, 0.5, 36, hv(92))
        if bar in (20, 22):
            drums.note(b0, 3, 57, hv(100))
    if bar == 24:  # hold, brass swell, then everything stops on beat 4 (the hush)
        timp.note(b0, 1.5, lr + 12 if lr + 12 <= 57 else lr, hv(104))
        drums.note(b0 + 2, 0.5, 36, hv(84))
    # choir and low brass in the big sections
    if 15 <= bar <= 24:
        for k, p in enumerate(tri):
            choir.note(ht(b0 + k * 0.08), 3.8 if bar < 24 else 2.9, p, hv(48 + 6 * (bar >= 20) + 5 * k, 6))
    if 18 <= bar <= 24:
        brass.note(b0, 3.8 if bar < 24 else 2.9, lr, hv(62 + 6 * (bar - 18), 3))
    # horn theme: soft at 15-18 (one phrase), full at 20-23
    if 15 <= bar <= 18 or 20 <= bar <= 23:
        for beat, ln, p in MEL[name]:
            loud = 70 if bar <= 18 else 96
            horn.note(b0 + beat, ln * 0.96, p, hv(loud + (8 if beat == 0 else 0), 3))
    if bar == 28 or bar == 29:  # resolution: horns carry the theme again, gently
        for beat, ln, p in MEL[name]:
            horn.note(b0 + beat, ln * 0.96, p, hv(80, 3))

# the hush (bar 25): one low piano note and a thin string breath
piano.cc(96, 64, 127)
piano.note(96, 3.6, 45, hv(52, 2)); piano.note(96 + 1.5, 2.2, 57, hv(34, 2))
piano.cc(99.9, 64, 0)
# final chord (bar 30), rings out
for p, inst in ((48, cello), (36, cbass), (55, pad), (60, pad), (64, pad), (72, horn), (67, horn), (60, choir), (64, choir), (67, choir)):
    inst.note(116, 9, p, hv(88 if inst is not choir else 56, 3))
timp.note(116, 2, 48, hv(100))
piano.cc(116, 64, 127); piano.note(116, 9, 36, hv(80)); piano.note(116, 9, 48, hv(74)); piano.note(116.5, 8, 64, hv(60))

PLAN = {"_": {"reverb_s": 3.2, "predelay_ms": 40, "duck_key": "Drums", "master_shelf_high": (7000, 8.5), "master_eq": [(400, -2.0, 0.9), (3500, 3.0, 0.8), (5500, 3.5, 0.8)]},
        "Contrabass": {"gain_db": 1, "duck_db": 0, "send": 0.15, "lpf": 2500},
        "Timpani": {"hpf": 35, "lpf": 6000, "gain_db": 0, "comp": (-20, 2, 15, 200), "send": 0.3, "duck_db": 0},
        "Low": {"gain_db": -1, "duck_db": 0, "send": 0.2, "shelf_low": (90, 3.0), "eq": [(300, -3, 1.0)]},
        "LowBrass": {"gain_db": -3, "duck_db": 0, "send": 0.3, "lpf": 3000},
        "Choir": {"gain_db": -6},
        "StringsSlow": {"duck_db": 0, "eq": [(380, -4, 0.9)], "gain_db": -2},
        "StringsFast": {"shelf_high": (6000, 4.5), "eq": [(350, -3, 1.0)]},
        "Piano": {"eq": [(300, -2.5, 1.0)], "shelf_high": (5000, 2.0), "send": 0.3},
        "Horns": {"send": 0.35, "eq": [(2500, 2.0, 1.0)]}}

if __name__ == "__main__":
    for level, msg in lint(song):
        print(level, msg)
    produce(song, sys.argv[1], PLAN, target_lufs=-15, length_s=96.0, fade_out_s=2.2)
