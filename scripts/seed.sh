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
ROWS="${SYNTHETIC_ROWS:-50000}"

if [[ -f "$MARKER" ]]; then
  echo "[seed] marker $MARKER present - already seeded, nothing to do."
  echo "[seed] delete the marker (or the volumes) to force a re-seed."
  exit 0
fi

echo "[seed] === 1/2  data pipeline (rows=$ROWS) ==="
python data-pipeline/run_all.py --rows "$ROWS" || {
  echo "[seed] pipeline reported errors; falling back to fully-synthetic run"
  python data-pipeline/run_all.py --no-net --rows "$ROWS"
}

echo "[seed] === 2/2  model training ==="
python -m model.train

date -u +"%Y-%m-%dT%H:%M:%SZ" > "$MARKER"
echo "[seed] done. marker written to $MARKER"
