"""API settings - environment driven, with working local defaults."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _env(key: str, default: str) -> str:
    return os.getenv(key, default)


class Settings:
    REPO_ROOT: Path = REPO_ROOT

    # ---- latency ----
    LATENCY_BUDGET_MS: int = int(_env("LATENCY_BUDGET_MS", "200"))

    # ---- datastores ----
    DATABASE_URL: str = _env(
        "DATABASE_URL",
        "postgresql://wtp:wtp_dev_password@localhost:5432/wtp",
    )
    REDIS_URL: str = _env("REDIS_URL", "redis://localhost:6379/0")

    # when Postgres is not reachable the API keeps working and logs decisions
    # to an in-memory ring buffer instead (demo-friendly, non-persistent)
    DB_REQUIRED: bool = _env("DB_REQUIRED", "false").lower() == "true"

    # ---- model artifacts ----
    MODEL_DIR: Path = Path(_env("MODEL_DIR", str(REPO_ROOT / "model" / "artifacts")))

    # ---- data context ----
    DATA_RAW: Path = REPO_ROOT / "data" / "raw"
    DATA_PROCESSED: Path = REPO_ROOT / "data" / "processed"

    # ---- CORS ----
    CORS_ORIGINS: list[str] = _env(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001,"
        "http://localhost:3300,http://127.0.0.1:3300",
    ).split(",")
    # "*" allows any origin (handy for a Vercel preview URL you don't know yet)
    CORS_ALLOW_ALL: bool = _env("CORS_ALLOW_ALL", "false").lower() == "true"

    # ---- public URLs (link generator builds customer/merchant links) ----
    PUBLIC_BASE_URL: str = _env("PUBLIC_BASE_URL", "https://razorpay-wtp.vercel.app").rstrip("/")

    # ---- misc ----
    SERVICE_NAME: str = "wtp-pricing-engine"
    VERSION: str = "1.1.0"


settings = Settings()
