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
COPY scripts/ ./scripts/
COPY pytest.ini .

RUN mkdir -p /app/data/raw /app/data/processed /app/model/artifacts \
    && chmod +x scripts/*.sh

EXPOSE 8000

# Default entrypoint self-seeds (data + model) when artifacts are missing, then
# starts the API - so a single-container deploy (Railway / Render / `docker run`)
# just works. docker-compose overrides `command:` (its `seeder` handles this).
CMD ["bash", "scripts/start.sh"]
