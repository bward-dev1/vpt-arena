"""IDM fine-tuning on synthetic recorder data with a tiny random IDM (CPU)."""
import json
import random
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.smoke import TINY_IDM, make_traj  # noqa: E402
from vpt_arena import train_idm  # noqa: E402


def main():
    tmp = Path(tempfile.mkdtemp(prefix="vpt-arena-idm-"))
    try:
        rng = random.Random(0)
        for i in range(2):
            (tmp / "d").mkdir(exist_ok=True)
            make_traj(tmp / "d", f"t{i}", 80, rng, mode="duels_sword")
        train_idm.main(["--weights", "random", "--data", str(tmp / "d"), "--run", str(tmp / "run"), "--batch", "2",
                        "--T", "16", "--steps", "20", "--lr", "1e-3", "--device", "cpu",
                        "--net-overrides", json.dumps(TINY_IDM)])
        L = [json.loads(l) for l in (tmp / "run" / "log.jsonl").read_text().splitlines()]
        print(f"nll {L[0]['nll']:.2f} -> {L[-1]['nll']:.2f}, bit acc {L[0]['btn_bit_acc']:.3f} -> {L[-1]['btn_bit_acc']:.3f}")
        assert L[-1]["nll"] < L[0]["nll"] and (tmp / "run" / "idm.weights").exists()
        print("idm checks passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
