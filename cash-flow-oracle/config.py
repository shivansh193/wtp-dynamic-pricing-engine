"""Configuration for the Cash Flow Oracle scaffold."""

from __future__ import annotations

import os
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parent
SQLITE_FALLBACK = MODULE_DIR / "cash_flow_oracle.sqlite3"

DATABASE_URL = os.getenv(
    "CFO_DATABASE_URL",
    os.getenv("DATABASE_URL", ""),  # reuse the Track 01 DSN if present
)

RANDOM_SEED = int(os.getenv("CFO_RANDOM_SEED", "7"))

# ------------------------------------------------------------------ #
# Synthetic settlement generation
# ------------------------------------------------------------------ #
HISTORY_YEARS = 3
MERCHANTS_PER_ARCHETYPE = 2  # -> 10 merchants total in the scaffold

# archetype -> (daily base settlement INR, day-to-day noise sigma (lognormal),
#               festive spike gain, monsoon dip, march FY-end gain,
#               june back-to-school gain)
ARCHETYPES: dict[str, dict] = {
    "fashion": {
        "base_daily_inr": 220_000, "noise_sigma": 0.35,
        "diwali_gain": 0.85, "wedding_gain": 0.35, "monsoon_dip": -0.15,
        "march_fy_gain": 0.10, "june_school_gain": 0.05, "weekend_gain": 0.20,
    },
    "electronics": {
        "base_daily_inr": 640_000, "noise_sigma": 0.45,
        "diwali_gain": 1.10, "wedding_gain": 0.15, "monsoon_dip": -0.10,
        "march_fy_gain": 0.15, "june_school_gain": 0.10, "weekend_gain": 0.12,
    },
    "grocery": {
        "base_daily_inr": 380_000, "noise_sigma": 0.18,
        "diwali_gain": 0.25, "wedding_gain": 0.05, "monsoon_dip": -0.08,
        "march_fy_gain": 0.03, "june_school_gain": 0.04, "weekend_gain": 0.06,
    },
    "home": {
        "base_daily_inr": 300_000, "noise_sigma": 0.40,
        "diwali_gain": 0.70, "wedding_gain": 0.25, "monsoon_dip": -0.18,
        "march_fy_gain": 0.30, "june_school_gain": 0.03, "weekend_gain": 0.15,
    },
    "services": {
        "base_daily_inr": 260_000, "noise_sigma": 0.15,
        "diwali_gain": 0.15, "wedding_gain": 0.05, "monsoon_dip": -0.04,
        "march_fy_gain": 0.08, "june_school_gain": 0.12, "weekend_gain": -0.05,
    },
}

# principal festival shopping dates (settlement lags spend by ~T+2, handled in gen)
FESTIVAL_DATES = [
    # (name, MM-DD, +/- window days, tag)
    ("diwali", "10-25", 25, "diwali"),      # approx; shifts yearly, close enough for a scaffold
    ("diwali", "11-05", 20, "diwali"),
    ("dussehra", "10-10", 10, "diwali"),
    ("wedding_q4", "12-05", 30, "wedding"),
    ("wedding_q1", "02-05", 25, "wedding"),
    ("holi", "03-14", 5, "wedding"),
]
MONSOON_MONTHS = {6, 7, 8, 9}
MARCH_FY_END = (3, 20, 3, 31)   # month, start-day, .. end-day window
JUNE_SCHOOL = (6, 1, 6, 25)

# ------------------------------------------------------------------ #
# Model params
# ------------------------------------------------------------------ #
GARCH_P, GARCH_Q = 1, 1
HMM_STATES = 3
HMM_STATE_LABELS = ["low_season", "high_season", "stress"]  # re-mapped by mean/vol
FORECAST_DEFAULT_DAYS = 30
FORECAST_MAX_DAYS = 60
PROPHET_INTERVAL_WIDTH = 0.80

# stress flag: forecast day is "stressed" if its lower band falls this far
# below the trailing 30-day mean settlement
STRESS_LOWER_BAND_DROP = 0.20

# ------------------------------------------------------------------ #
# RBI macro series (reuse the Track 01 pipeline's calibrated fallback)
# ------------------------------------------------------------------ #
RBI_CSV_HINT = REPO_ROOT / "data" / "raw" / "rbi_digital_payments.csv"
