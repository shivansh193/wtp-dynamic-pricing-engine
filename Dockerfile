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

RUN mkdir -p /app/data/raw /app/data/processed /app/model/artifacts

EXPOSE 8000

# default: run the API. The seeder service overrides `command:`.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
