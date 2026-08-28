#!/usr/bin/env bash
# Fully-offline one-shot seed for single-container deploys and image bake.
# Generates data with NO network calls, then trains the models (fast).
set -euo pipefail

ROWS="${SYNTHETIC_ROWS:-20000}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
export LGBM_NUM_THREADS="${LGBM_NUM_THREADS:-$OMP_NUM_THREADS}"

echo "[seed_offline] data pipeline (--no-net, rows=$ROWS)"
python data-pipeline/run_all.py --no-net --rows "$ROWS"

# FireHOL / IPinfo: only when explicitly asked (FETCH_BLOCKLISTS=1). Both have
# offline sample fallbacks, and pulling the multi-million-line FireHOL aggregate
# at build time bloats the image - the ip-enrichment module runs fine on the
# committed samples + mock-geo mode.
if [[ "${FETCH_BLOCKLISTS:-0}" == "1" ]]; then
  python data-pipeline/fetch_firehol.py || true
  python data-pipeline/fetch_ipinfo_asn.py || true
else
  python data-pipeline/fetch_ipinfo_asn.py || true   # tiny, offline fallback
fi

echo "[seed_offline] training (fast)"
if [[ "${TRAIN_FAST:-1}" == "1" ]]; then
  python -m model.train --fast
else
  python -m model.train
fi
echo "[seed_offline] done"
