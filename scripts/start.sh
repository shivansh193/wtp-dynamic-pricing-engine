#!/usr/bin/env bash
# ==========================================================================
# API entrypoint for standalone / cloud deploys (Railway, Render, `docker run`).
#
# docker-compose does NOT use this - there the `seeder` service prepares the
# shared volumes and `api` runs plain uvicorn. But a single-container deploy has
# no seeder, so make the API self-sufficient: if the model artifacts are
# missing, generate data + train once (fast, fully offline), then start.
# ==========================================================================
set -euo pipefail

ART=/app/model/artifacts/wtp_estimator.joblib
PORT="${PORT:-8000}"                # Railway/Render inject $PORT
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
export LGBM_NUM_THREADS="${LGBM_NUM_THREADS:-$OMP_NUM_THREADS}"

if [[ ! -f "$ART" ]]; then
  echo "[start] no model artifacts - seeding (offline data + fast train)…"
  SYNTHETIC_ROWS="${SYNTHETIC_ROWS:-20000}" \
  TRAIN_FAST="${TRAIN_FAST:-1}" \
  OMP_NUM_THREADS="${OMP_NUM_THREADS}" \
    bash scripts/seed_offline.sh
else
  echo "[start] model artifacts present - skipping seed."
fi

echo "[start] launching API on :$PORT"
exec uvicorn api.main:app --host 0.0.0.0 --port "$PORT"
