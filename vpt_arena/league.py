"""Elo league over checkpoints, scripted bots and people, stored in runs/league.json (the site's League page).

    python -m vpt_arena.league play --weights runs/arena-2x/policy.weights --name arena-2x@20k \
        --opponent Steve --opponent-kind human --mode duels_sword --games 10

Overall Elo and a per-mode Elo are both kept. K=32, start 1000.
"""
import argparse
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "runs" / "league.json"
K, START = 32.0, 1000.0


def load(path=PATH):
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            pass
    return {"players": {}, "matches": []}


def save(league, path=PATH):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(league, indent=1))
    os.replace(tmp, p)


def expected(ra, rb):
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


def _player(league, name, kind):
    return league["players"].setdefault(name, {"elo": START, "games": 0, "wins": 0, "kind": kind, "by_mode": {}})


def record(league, mode, a, b, winner, kind_a="checkpoint", kind_b="scripted", score="", t=None):
    """winner: a, b, or None for a draw. Updates both overall and per-mode Elo."""
    pa, pb = _player(league, a, kind_a), _player(league, b, kind_b)
    sa = 1.0 if winner == a else 0.0 if winner == b else 0.5
    for key in ("elo", mode):
        ra = pa["elo"] if key == "elo" else pa["by_mode"].get(mode, START)
        rb = pb["elo"] if key == "elo" else pb["by_mode"].get(mode, START)
        ea = expected(ra, rb)
        na, nb = ra + K * (sa - ea), rb + K * ((1 - sa) - (1 - ea))
        if key == "elo":
            pa["elo"], pb["elo"] = round(na, 1), round(nb, 1)
        else:
            pa["by_mode"][mode], pb["by_mode"][mode] = round(na, 1), round(nb, 1)
    for p, w in ((pa, winner == a), (pb, winner == b)):
        p["games"] += 1
        p["wins"] += int(w)
    league["matches"].append({"t": t or time.time(), "mode": mode, "a": a, "b": b, "winner": winner, "score": score})
    league["matches"] = league["matches"][-2000:]
    return league


def play(args):
    from .agent import ArenaAgent
    from .rl.live_env import make_live_env
    env = make_live_env(args.mode)
    agent = ArenaAgent(args.arch, args.weights, args.mode, device=args.device)
    league = load()
    for g in range(args.games):
        frame = env.reset()
        agent.reset()
        done, info = False, {}
        while not done:
            action, _ = agent.act(frame)
            frame, _, done, info = env.step(action)
        winner = args.name if info.get("won") else (None if info.get("timed_out") or any(
            e["event"] == "draw" for e in info.get("events", [])) else args.opponent)
        record(league, args.mode, args.name, args.opponent, winner, "checkpoint", args.opponent_kind,
               score="timeout" if info.get("timed_out") else "")
        save(league)
        print(f"game {g + 1}: winner {winner}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("play")
    p.add_argument("--weights", required=True)
    p.add_argument("--arch", default="2x")
    p.add_argument("--name", required=True)
    p.add_argument("--opponent", required=True)
    p.add_argument("--opponent-kind", default="scripted", choices=["checkpoint", "scripted", "human", "random"])
    p.add_argument("--mode", required=True)
    p.add_argument("--games", type=int, default=10)
    p.add_argument("--device", default=None)
    t = sub.add_parser("table")
    t.add_argument("--mode", default=None)
    args = ap.parse_args(argv)
    if args.cmd == "play":
        play(args)
    else:
        lg = load()
        rows = sorted(lg["players"].items(), key=lambda kv: -(kv[1]["by_mode"].get(args.mode, START) if args.mode
                                                               else kv[1]["elo"]))
        for name, p in rows:
            elo = p["by_mode"].get(args.mode, START) if args.mode else p["elo"]
            print(f"{elo:7.1f}  {name:30s} {p['kind']:10s} {p['wins']}/{p['games']}")


if __name__ == "__main__":
    main()
