"""Merge the round's worker policies into one (federated averaging) and summarise the round.

    python cloud/aggregate.py --inputs artifacts/ --out global.weights --summary summary.json

Every worker started from the same weights and trained on its own modes; the
merged policy averages their parameters, so each mode's progress is kept
through the shared conditioner and network. Workers that ran fewer env steps
get proportionally less weight.
"""
import argparse
import json
from pathlib import Path

import torch as th


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--summary", required=True)
    args = ap.parse_args()
    jobs = []
    for w in sorted(Path(args.inputs).rglob("policy.weights")):
        st = w.parent / "status.json"
        s = json.loads(st.read_text()) if st.exists() else {}
        steps = float(s.get("env_steps") or 0)
        if steps <= 0:
            print(f"skip {w.parent.name}: no env steps")
            continue
        jobs.append((w, steps, s))
    if not jobs:
        raise SystemExit("no usable worker weights")
    total = sum(s for _, s, _ in jobs)
    avg = None
    for w, steps, _ in jobs:
        sd = th.load(w, map_location="cpu", weights_only=True)
        f = steps / total
        if avg is None:
            avg = {k: (v.float() * f if v.is_floating_point() else v.clone()) for k, v in sd.items()}
        else:
            for k, v in sd.items():
                if v.is_floating_point():
                    avg[k] += v.float() * f
    th.save(avg, args.out)
    summ = {"jobs": [{"job": s.get("job"), "modes": s.get("modes"), "env_steps": st, "iter": s.get("iter"),
                      "per_mode": s.get("per_mode", {})} for _, st, s in jobs], "total_env_steps": total}
    Path(args.summary).write_text(json.dumps(summ, indent=1))
    print(json.dumps({"merged": len(jobs), "total_env_steps": total}))


if __name__ == "__main__":
    main()
