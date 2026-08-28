#!/usr/bin/env bash
# Fully-offline one-shot seed for single-container deploys (called by start.sh).
# Generates data with NO network calls, then trains the models (fast).
set -euo pipefail

ROWS="${SYNTHETIC_ROWS:-20000}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
export LGBM_NUM_THREADS="${LGBM_NUM_THREADS:-$OMP_NUM_THREADS}"

echo "[seed_offline] data pipeline (--no-net, rows=$ROWS)"
python data-pipeline/run_all.py --no-net --rows "$ROWS"

# firehol/ipinfo have offline sample fallbacks; run them so ip-enrichment loads
python data-pipeline/fetch_firehol.py || true
python data-pipeline/fetch_ipinfo_asn.py || true

echo "[seed_offline] training (fast)"
if [[ "${TRAIN_FAST:-1}" == "1" ]]; then
  python -m model.train --fast
else
  python -m model.train
fi
echo "[seed_offline] done"
