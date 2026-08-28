#!/usr/bin/env bash
# ==========================================================================
# Seeder entrypoint - runs ONCE on first boot (idempotent via a marker file
# on the shared data volume). Regenerates everything if you delete the marker
# or the volumes.
#
#   1. data pipeline  (real fetches w/ offline fallbacks) -> data/
#   2. model training  (WTP estimator + conversion classifier) -> model/artifacts/
# ==========================================================================
set -euo pipefail

MARKER=/app/data/processed/.seed_complete
TXNS=/app/data/processed/transactions.csv
ROWS="${SYNTHETIC_ROWS:-50000}"

# LightGBM + OpenMP oversubscribe hard inside the Docker Desktop Linux VM
# (16+ spinning threads make a 15s train take 20min). Cap threads unless the
# operator overrides.
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"
export LGBM_NUM_THREADS="${LGBM_NUM_THREADS:-$OMP_NUM_THREADS}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-$OMP_NUM_THREADS}"
# --fast: 300 rounds instead of 2000, skip the SHAP beeswarm docs plot.
# Model quality is materially the same (R2 ~0.90); flip to "0" for the full run.
TRAIN_FAST="${TRAIN_FAST:-1}"

if [[ -f "$MARKER" ]]; then
  echo "[seed] marker $MARKER present - already seeded, nothing to do."
  echo "[seed] delete the marker (or the volumes) to force a re-seed."
  exit 0
fi

if [[ -f "$TXNS" ]]; then
  echo "[seed] $TXNS already present - skipping the data pipeline, training only."
else
  echo "[seed] === 1/2  data pipeline (rows=$ROWS) ==="
  python data-pipeline/run_all.py --rows "$ROWS" || {
    echo "[seed] pipeline reported errors; falling back to fully-synthetic run"
    python data-pipeline/run_all.py --no-net --rows "$ROWS"
  }
fi

echo "[seed] === 2/2  model training  (threads=$OMP_NUM_THREADS, fast=$TRAIN_FAST) ==="
if [[ "$TRAIN_FAST" == "1" ]]; then
  python -m model.train --fast
else
  python -m model.train
fi

date -u +"%Y-%m-%dT%H:%M:%SZ" > "$MARKER"
echo "[seed] done. marker written to $MARKER"
