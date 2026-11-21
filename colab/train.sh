#!/usr/bin/env bash
# Full training pipeline on a Colab GPU (L4 or A100). GitHub Actions (cloud/) is the other free option.
#
# In a Colab cell:
#   from google.colab import drive; drive.mount('/content/drive')
#   !bash /content/drive/MyDrive/mc-vpt-arena/colab/train.sh
#
# Expects the repo (without .venv) at $REPO on Drive. Weights, data and runs live on Drive so a
# disconnected runtime resumes where it stopped (train_bc resumes from runs/<run>/latest.pt).
set -euo pipefail
REPO=${REPO:-/content/drive/MyDrive/mc-vpt-arena}
ARCH=${ARCH:-2x}
STEPS=${STEPS:-20000}
CONTRACTOR_CLIPS=${CONTRACTOR_CLIPS:-200}
cd "$REPO"
pip -q install opencv-python-headless attrs

mkdir -p weights data/contractor data/idm videos runs
fetch() { [ -s "weights/$2" ] || curl -sfL -o "weights/$2" "$1"; }
fetch https://openaipublic.blob.core.windows.net/minecraft-rl/models/foundation-model-$ARCH.weights foundation-model-$ARCH.weights
fetch https://openaipublic.blob.core.windows.net/minecraft-rl/idm/4x_idm.weights 4x_idm.weights
python tools/check_weights.py "$ARCH" idm4x

# 1. survival rehearsal data (OpenAI contractors, early game)
python tools/fetch_contractor.py --index 7 --n "$CONTRACTOR_CLIPS" --max-mb 120 --out data/contractor

# 2. label any PvP videos placed in videos/<mode>/ (mode = a games.py key, e.g. videos/bedwars_solo/)
for d in videos/*/; do
  [ -d "$d" ] || continue
  mode=$(basename "$d")
  ls "$d"*.mp4 >/dev/null 2>&1 || continue
  python -m vpt_arena.idm_label --weights weights/4x_idm.weights --mode "$mode" --out "data/idm/$mode" "$d"*.mp4
done

# 3. behaviour cloning over everything: own recordings weigh most, IDM labels next, contractor data keeps survival skill
SRC=(--data data/contractor:1)
[ -d data/human ] && SRC+=(--data data/human:4)
[ -d data/idm ] && SRC+=(--data data/idm:2)
python -m vpt_arena.train_bc --arch "$ARCH" --weights "weights/foundation-model-$ARCH.weights" "${SRC[@]}" \
  --run "runs/arena-$ARCH" --batch 4 --T 64 --accum 4 --ckpt-cnn --steps "$STEPS" --kl-coef 0.05
echo "done: runs/arena-$ARCH/policy.weights"
