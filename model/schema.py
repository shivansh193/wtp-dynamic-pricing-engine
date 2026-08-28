"""
Feature contract shared by training and inference.

The synthetic generator writes `data/processed/feature_schema.json`; this
module loads it and provides:

  - FEATURES            ordered list of model input columns
  - CATEGORICALS        subset that LightGBM treats as categorical
  - encode(df)          -> DataFrame with categoricals as integer codes
                           (mapping is frozen at train time, saved in the
                           artifact, and reused verbatim at inference)
  - build_features(raw) -> turn a raw /personalize payload into a 1-row frame

Keeping this in one place means the API can never drift from the trained model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "data" / "processed" / "feature_schema.json"

# ---- fallback schema (keeps model/ importable before the pipeline runs) ----
_FALLBACK = {
    "categorical_features": [
        "device_type", "city_tier", "income_tier", "payment_method_preference",
        "time_of_day", "day_of_week", "referral_source", "ip_type",
        "product_category",
    ],
    "numeric_features": [
        "month", "digital_demand_index", "ip_trust_multiplier", "historical_aov",
        "return_rate", "payment_success_rate", "cod_completion_rate",
        "cross_merchant_trust_score", "num_merchants_transacted",
        "account_age_days", "cart_value", "is_festival_period",
        "festival_intensity",
    ],
    "wtp_target": "actual_wtp",
    "conversion_target": "converted",
    "conversion_extra_feature": "offered_price_multiplier",
    "offer_target": "offer_responded",
    "context_only": ["txn_date", "year_month", "pin_code"],
}


def load_schema() -> dict:
    if SCHEMA_PATH.exists():
        return json.loads(SCHEMA_PATH.read_text())
    return dict(_FALLBACK)


_S = load_schema()

CATEGORICALS: list[str] = list(_S["categorical_features"])
NUMERICS: list[str] = list(_S["numeric_features"])
FEATURES: list[str] = CATEGORICALS + NUMERICS

WTP_TARGET: str = _S["wtp_target"]
CONVERSION_TARGET: str = _S["conversion_target"]
CONVERSION_EXTRA: str = _S["conversion_extra_feature"]
OFFER_TARGET: str = _S["offer_target"]

# Known categories per categorical column. Frozen here so encoding is stable
# even if a training sample happens to miss a rare level. Extended/overridden
# by whatever the training data actually contains (see build_category_maps).
KNOWN_CATEGORIES: dict[str, list[Any]] = {
    "device_type": ["Android_budget", "Android_premium", "iPhone", "Desktop"],
    "city_tier": [1, 2, 3],
    "income_tier": ["low", "lower_mid", "mid", "upper_mid", "high"],
    "payment_method_preference": ["UPI", "Credit_Card", "Debit_Card", "COD", "Wallet"],
    "time_of_day": ["morning", "afternoon", "evening", "night"],
    "day_of_week": ["weekday", "weekend"],
    "referral_source": ["organic", "paid_ad", "social", "email", "influencer"],
    "ip_type": ["residential", "mobile_carrier", "datacenter", "vpn",
                "public_wifi", "tor", "unknown"],
    "product_category": ["fashion", "electronics", "grocery", "home", "beauty"],
}


def build_category_maps(df: pd.DataFrame) -> dict[str, dict[Any, int]]:
    """Freeze {category value -> int code} for every categorical column."""
    maps: dict[str, dict[Any, int]] = {}
    for col in CATEGORICALS:
        seen = list(KNOWN_CATEGORIES.get(col, []))
        for v in df[col].dropna().unique().tolist():
            if v not in seen:
                seen.append(v)
        maps[col] = {v: i for i, v in enumerate(seen)}
    return maps


def encode(df: pd.DataFrame, category_maps: dict[str, dict[Any, int]]) -> pd.DataFrame:
    """Apply frozen integer encoding. Unseen values -> -1 (LightGBM handles it)."""
    out = df.copy()
    for col in CATEGORICALS:
        m = category_maps.get(col, {})
        out[col] = out[col].map(m).fillna(-1).astype("int32")
    for col in NUMERICS:
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("float64")
    return out[FEATURES]


# --------------------------------------------------------------------------- #
# Raw payload -> feature row  (used by the API /personalize path)
# --------------------------------------------------------------------------- #
_TIME_BUCKETS = [
    (5, "morning"), (12, "afternoon"), (17, "evening"), (21, "night"), (24, "night"),
]


def _income_tier_for(city_tier: int) -> str:
    return {1: "upper_mid", 2: "mid", 3: "lower_mid"}.get(city_tier, "mid")


def _derive_time_of_day(hour: int | None) -> str:
    if hour is None:
        return "evening"
    for edge, label in _TIME_BUCKETS:
        if hour < edge:
            return label
    return "night"


def build_features(raw: dict, *, festival_lookup=None, demand_lookup=None) -> pd.DataFrame:
    """
    Build the exact model input frame from a loose customer-signals dict.

    `raw` may under-specify; every field has a sane default so the endpoint
    never 500s on a thin payload. `festival_lookup(date)->(is_fest,intensity)`
    and `demand_lookup(year_month)->float` are injected by the API so this
    module stays dependency-free.
    """
    from datetime import date, datetime

    txn_dt = raw.get("txn_date")
    if isinstance(txn_dt, str):
        try:
            d = datetime.fromisoformat(txn_dt).date()
        except ValueError:
            d = date.today()
    else:
        d = date.today()

    hour = raw.get("hour")
    tod = raw.get("time_of_day") or _derive_time_of_day(hour if isinstance(hour, int) else None)
    dow = raw.get("day_of_week") or ("weekend" if d.weekday() >= 5 else "weekday")

    is_fest, intensity = (0, 0)
    if festival_lookup is not None:
        try:
            is_fest, intensity = festival_lookup(d.isoformat())
        except Exception:  # noqa: BLE001
            pass
    is_fest = int(raw.get("is_festival_period", is_fest) or 0)
    intensity = int(raw.get("festival_intensity", intensity) or 0)

    year_month = f"{d.year:04d}-{d.month:02d}"
    demand = 1.0
    if demand_lookup is not None:
        try:
            demand = float(demand_lookup(year_month))
        except Exception:  # noqa: BLE001
            demand = 1.0
    demand = float(raw.get("digital_demand_index", demand) or 1.0)

    # NB: use `or` not dict.get(default) - callers pass explicit None for
    # "unknown", and we want the sensible default in that case too.
    row = {
        "device_type": raw.get("device_type") or "Android_budget",
        "city_tier": int(raw.get("city_tier") or 2),
        "income_tier": raw.get("income_tier") or _income_tier_for(int(raw.get("city_tier") or 2)),
        "payment_method_preference": raw.get("payment_method_preference") or "UPI",
        "time_of_day": tod,
        "day_of_week": dow,
        "referral_source": raw.get("referral_source") or "organic",
        "ip_type": raw.get("ip_type") or "unknown",
        "product_category": raw.get("product_category") or "fashion",
        "month": d.month,
        "digital_demand_index": demand,
        "ip_trust_multiplier": float(raw.get("ip_trust_multiplier", 0.8)),
        "historical_aov": float(raw.get("historical_aov", raw.get("cart_value", 2000) or 2000)),
        "return_rate": float(raw.get("return_rate", 0.15)),
        "payment_success_rate": float(raw.get("payment_success_rate", 0.9)),
        "cod_completion_rate": float(raw.get("cod_completion_rate", 0.85)),
        "cross_merchant_trust_score": float(raw.get("cross_merchant_trust_score", 55)),
        "num_merchants_transacted": int(raw.get("num_merchants_transacted", 5)),
        "account_age_days": int(raw.get("account_age_days", 200)),
        "cart_value": float(raw.get("cart_value", raw.get("list_price", 2000) or 2000)),
        "is_festival_period": is_fest,
        "festival_intensity": intensity,
    }
    return pd.DataFrame([row])[FEATURES]
