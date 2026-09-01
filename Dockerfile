# ==========================================================================
# Shared Python image - powers both the `api` service and the `seeder`
# (data pipeline + model training) service. One build, two commands.
# ==========================================================================
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

# build tooling for lightgbm / shap wheels that need compilation on slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# project code (data/ and model/artifacts/ come from volumes at runtime)
COPY data-pipeline/ ./data-pipeline/
COPY model/ ./model/
COPY api/ ./api/
COPY ip-enrichment/ ./ip-enrichment/
COPY cash-flow-oracle/ ./cash-flow-oracle/
COPY scripts/ ./scripts/
COPY pytest.ini .

RUN mkdir -p /app/data/raw /app/data/processed /app/model/artifacts \
    && chmod +x scripts/*.sh

# Bake the dataset + trained models INTO the image so a single-container deploy
# (Render / Fly / `docker run`) cold-starts in seconds instead of self-seeding
# for ~2 min on every scale-from-zero. Fully offline, deterministic.
# (docker-compose mounts a named volume over /app/model/artifacts, so its
# `seeder` service still regenerates these there - this build-time seed is only
# used when nothing is mounted.)
ARG BAKE_MODEL=1
ARG SYNTHETIC_ROWS=20000
RUN if [ "$BAKE_MODEL" = "1" ]; then \
      OMP_NUM_THREADS=4 SYNTHETIC_ROWS=$SYNTHETIC_ROWS TRAIN_FAST=1 \
        bash scripts/seed_offline.sh ; \
    fi

# Track 04: bake the Cash Flow Oracle's synthetic settlement DB into the image
# (SQLite, ~33k rows, deterministic, offline) so /oracle/* is warm on cold start.
RUN if [ "$BAKE_MODEL" = "1" ]; then python scripts/cfo.py seed ; fi

EXPOSE 8000

# start.sh runs the API; it self-seeds only if artifacts are somehow absent
# (e.g. BAKE_MODEL=0 or a volume shadowed them). docker-compose overrides
# `command:` and relies on its own `seeder` service instead.
CMD ["bash", "scripts/start.sh"]
