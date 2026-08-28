"""
Step 3 - Synthetic Indian ecommerce customer-transaction generator.

Produces `data/processed/transactions.csv` (default 50,000 rows) plus a
`data/processed/feature_schema.json` describing every column, its type and its
role (feature / target / context). The model and API treat that schema as the
single source of truth.

Calibration hooks (all optional - falls back to internal constants):
  - data/raw/rbi_digital_payments.csv     -> monthly `digital_demand_index`
  - data/raw/google_trends_categories.csv -> monthly per-category demand shape
  - data/processed/festival_features.csv  -> daily festival period + intensity
  - data/raw/pincode_income_tier.csv      -> pin_code -> income_tier + income

Target-variable design (see brief Step 3):
  actual_wtp        : ground-truth WTP multiplier in [0.85, 1.25]
                      higher for iPhone / Tier 1 / credit card / low return rate
  converted         : Bernoulli, P up when offered price <= actual_wtp
  offer_responded   : Bernoulli, whether the shown offer was used

Deliberate clusters the brief asks us to reproduce:
  Tier1 + iPhone + Credit_Card    -> actual_wtp ~ 1.10-1.25
  COD + Tier3 + Android_budget    -> actual_wtp ~ 0.85-0.95
  VPN users                       -> ip_trust_multiplier applied to
                                     cross_merchant_trust_score
Festival periods                  -> +15-25% AOV and conversion
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

import config as C
from _util import log, require_pandas, write_source_sidecar

OUT = C.PROCESSED_DIR / "transactions.csv"
SCHEMA_OUT = C.PROCESSED_DIR / "feature_schema.json"

rng = np.random.default_rng(C.RANDOM_SEED)


# --------------------------------------------------------------------------- #
# Calibration data loading (graceful fallbacks)
# --------------------------------------------------------------------------- #
def _load_demand_index() -> dict[str, float]:
    path = C.RAW_DIR / "rbi_digital_payments.csv"
    if path.exists():
        df = pd.read_csv(path)
        if "digital_demand_index" in df:
            return dict(zip(df.month, df.digital_demand_index))
    log("  rbi_digital_payments.csv missing -> flat demand index")
    return {}


def _load_trends() -> pd.DataFrame | None:
    path = C.RAW_DIR / "google_trends_categories.csv"
    if path.exists():
        return pd.read_csv(path).set_index("month")
    log("  google_trends_categories.csv missing -> using CATEGORY_SEASONALITY")
    return None


def _load_festivals() -> pd.DataFrame | None:
    path = C.PROCESSED_DIR / "festival_features.csv"
    if path.exists():
        return pd.read_csv(path).set_index("date")
    log("  festival_features.csv missing -> festivals disabled")
    return None


def _load_pincode_income() -> dict[str, tuple[str, int]]:
    path = C.RAW_DIR / "pincode_income_tier.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype={"pin_code": str})
    return {r.pin_code: (r.income_tier, int(r.median_household_income_inr)) for r in df.itertuples()}


DEMAND_INDEX = _load_demand_index()
TRENDS = _load_trends()
FESTIVALS_DF = _load_festivals()
PIN_INCOME = _load_pincode_income()


# --------------------------------------------------------------------------- #
# Helper samplers
# --------------------------------------------------------------------------- #
def _weighted(mapping: dict, n: int) -> np.ndarray:
    keys = list(mapping)
    probs = np.array(list(mapping.values()), dtype=float)
    probs = probs / probs.sum()
    return rng.choice(keys, size=n, p=probs)


def _sample_dates(n: int) -> pd.DatetimeIndex:
    """Sample transaction dates across the window, weighted by monthly digital
    demand so festive / recent months carry proportionally more transactions."""
    months = pd.period_range("2022-01", C.DATA_MAX_MONTH, freq="M")
    if DEMAND_INDEX:
        w = np.array([DEMAND_INDEX.get(str(m), 1.0) for m in months], dtype=float)
    else:
        # gentle secular growth if no RBI file
        w = np.linspace(0.7, 1.6, len(months))
    w = w / w.sum()
    chosen_month = rng.choice(len(months), size=n, p=w)
    days = []
    for mi in chosen_month:
        p = months[mi]
        start = p.to_timestamp()
        dim = p.days_in_month
        days.append(start + pd.Timedelta(days=int(rng.integers(0, dim))))
    return pd.DatetimeIndex(days)


def _category_for_month(month_str: str, n: int) -> np.ndarray:
    """Category choice modulated by Google-Trends monthly interest."""
    base = np.array([C.CATEGORY_WEIGHTS[c] for c in C.ECOMMERCE_CATEGORIES])
    if TRENDS is not None and month_str in TRENDS.index:
        interest = np.array([TRENDS.loc[month_str, c] for c in C.ECOMMERCE_CATEGORIES], dtype=float)
        interest = interest / interest.mean()
    else:
        mm = int(month_str.split("-")[1]) - 1
        interest = np.array([C.CATEGORY_SEASONALITY[c][mm] for c in C.ECOMMERCE_CATEGORIES])
    w = base * interest
    w = w / w.sum()
    return rng.choice(C.ECOMMERCE_CATEGORIES, size=n, p=w)


def _pin_for_tier(tier: int) -> str:
    cities = C.CITY_TIERS[tier]["cities"]
    city = rng.choice(list(cities))
    prefix = rng.choice(cities[city])
    return f"{prefix}{int(rng.integers(1, 999)):03d}"


TIME_OF_DAY = {"morning": 0.22, "afternoon": 0.28, "evening": 0.34, "night": 0.16}
REFERRAL = {"organic": 0.38, "paid_ad": 0.24, "social": 0.18, "email": 0.10, "influencer": 0.10}


# --------------------------------------------------------------------------- #
# Main generation
# --------------------------------------------------------------------------- #
def generate(n: int = C.SYNTHETIC_ROWS) -> pd.DataFrame:
    log(f"Generating {n:,} synthetic transactions...")

    dates = _sample_dates(n)
    month_str = dates.strftime("%Y-%m")
    date_str = dates.strftime("%Y-%m-%d")

    # ---- customer signals ----
    city_tier = _weighted(C.CITY_TIER_WEIGHTS, n).astype(int)
    pin_code = np.array([_pin_for_tier(t) for t in city_tier])
    device_type = _weighted(C.DEVICE_WEIGHTS, n)

    payment_pref = np.empty(n, dtype=object)
    for t in (1, 2, 3):
        mask = city_tier == t
        payment_pref[mask] = _weighted(C.PAYMENT_PREF_BY_TIER[t], int(mask.sum()))

    time_of_day = _weighted(TIME_OF_DAY, n)
    day_of_week = np.where(dates.dayofweek >= 5, "weekend", "weekday")
    referral_source = _weighted(REFERRAL, n)

    ip_type = _weighted(C.IP_TYPE_WEIGHTS, n)
    ip_trust_multiplier = np.array([C.IP_TRUST_MULTIPLIER[t] for t in ip_type])
    ip_trust_multiplier = np.clip(ip_trust_multiplier + rng.normal(0, 0.015, n), 0.25, 1.0)

    # ---- category + transaction context ----
    product_category = np.empty(n, dtype=object)
    for m in np.unique(month_str):
        mask = month_str == m
        product_category[mask] = _category_for_month(m, int(mask.sum()))

    festival_intensity = np.zeros(n, dtype=int)
    is_festival = np.zeros(n, dtype=bool)
    if FESTIVALS_DF is not None:
        fi = FESTIVALS_DF.reindex(date_str)
        festival_intensity = fi["intensity_score"].fillna(0).to_numpy().astype(int)
        is_festival = fi["is_festival_period"].fillna(False).to_numpy().astype(bool)
    month_num = dates.month.to_numpy()

    # ---- income tier from pin ----
    income_tier = np.array([PIN_INCOME.get(p, (None, None))[0] for p in pin_code], dtype=object)
    # fill any misses from a tier-conditioned default
    default_income_tier = {1: "upper_mid", 2: "mid", 3: "lower_mid"}
    for i in range(n):
        if income_tier[i] is None:
            income_tier[i] = default_income_tier[city_tier[i]]
    income_rank = np.array(
        [{"high": 4, "upper_mid": 3, "mid": 2, "lower_mid": 1, "low": 0}[t] for t in income_tier]
    )

    # ---- behavioural history ----
    account_age_days = rng.integers(1, 1801, n)
    # tenure correlates with #merchants and trust
    num_merchants = np.clip(
        (1 + rng.gamma(2.0, 1.0, n) * (account_age_days / 1800) * 12).round(), 1, 50
    ).astype(int)

    cat_aov = np.array([C.CATEGORY_ECONOMICS[c]["aov"] for c in product_category])
    cat_sigma = np.array([C.CATEGORY_ECONOMICS[c]["cart_lognorm_sigma"] for c in product_category])
    # historical AOV: category centre, lifted by device premium + income rank
    device_aov_mult = np.array(
        [{"iPhone": 1.35, "Android_premium": 1.18, "Desktop": 1.10, "Android_budget": 0.85}[d]
         for d in device_type]
    )
    historical_aov = (
        cat_aov
        * device_aov_mult
        * (0.9 + 0.06 * income_rank)
        * rng.lognormal(0, 0.25, n)
    ).round(0)

    cat_ret = np.array([C.CATEGORY_ECONOMICS[c]["return_rate"] for c in product_category])
    cat_ret_sd = np.array([C.CATEGORY_ECONOMICS[c]["return_sd"] for c in product_category])
    # tier 3 slightly higher returns (fit/expectation gaps), premium devices lower
    tier_ret_adj = np.array([{1: -0.02, 2: 0.0, 3: 0.03}[t] for t in city_tier])
    return_rate = np.clip(
        rng.normal(cat_ret + tier_ret_adj, cat_ret_sd), 0.0, 0.85
    )

    payment_success_rate = np.clip(rng.normal(0.93, 0.05, n) + 0.02 * (city_tier == 1), 0.5, 0.999)
    # COD completion: lower for tier 3 / budget android / low trust
    cod_base = np.where(city_tier == 3, 0.80, np.where(city_tier == 2, 0.87, 0.92))
    cod_completion_rate = np.clip(
        rng.normal(cod_base, 0.08) - 0.03 * (device_type == "Android_budget"), 0.4, 0.999
    )

    # ---- cross-merchant trust score (0-100) derived from behaviour ----
    trust_raw = (
        30
        + 25 * payment_success_rate
        + 15 * cod_completion_rate
        + 12 * (num_merchants / 50)
        + 10 * (account_age_days / 1800)
        - 22 * return_rate
        + rng.normal(0, 5, n)
    )
    cross_merchant_trust_score = np.clip(trust_raw, 0, 100)
    # brief: VPN users have ip_trust_multiplier applied to their trust score
    vpn_like = np.isin(ip_type, ["vpn", "datacenter", "tor"])
    cross_merchant_trust_score = np.where(
        vpn_like,
        cross_merchant_trust_score * ip_trust_multiplier,
        cross_merchant_trust_score,
    )
    cross_merchant_trust_score = np.clip(cross_merchant_trust_score, 0, 100).round(1)

    # ---- cart value: lognormal around category AOV, festival lift 15-25% ----
    festival_lift = np.where(
        is_festival, 1.0 + (0.15 + 0.10 * (festival_intensity / 3.0)), 1.0
    )
    cart_value = (
        cat_aov
        * rng.lognormal(0, cat_sigma)
        * (0.75 + 0.10 * income_rank / 4 + 0.15 * device_aov_mult / 1.35)
        * festival_lift
    ).round(0)
    cart_value = np.clip(cart_value, 199, None)

    # ================================================================== #
    # TARGET 1: actual_wtp  (ground-truth willingness-to-pay multiplier)
    # ================================================================== #
    # Coefficients are deliberately moderate so the target clusters sit *inside*
    # their bands rather than piling up against the [0.85, 1.25] clips.
    wtp = np.full(n, 1.0)
    wtp += np.array(
        [{"iPhone": 0.075, "Android_premium": 0.034, "Desktop": 0.018, "Android_budget": -0.042}[d]
         for d in device_type]
    )
    wtp += np.array([{1: 0.048, 2: 0.0, 3: -0.042}[t] for t in city_tier])
    wtp += np.array(
        [{"Credit_Card": 0.048, "Wallet": 0.010, "UPI": 0.0, "Debit_Card": -0.008, "COD": -0.048}[p]
         for p in payment_pref]
    )
    wtp += 0.010 * (income_rank - 2)                       # income tier gradient
    wtp += -0.13 * (return_rate - cat_ret)                 # heavy returners pay less
    wtp += 0.045 * (cross_merchant_trust_score / 100 - 0.5)
    wtp += 0.014 * festival_intensity                      # festive urgency
    wtp += 0.09 * (ip_trust_multiplier - 1.0)              # vpn/datacenter drag
    wtp += 0.025 * np.tanh((historical_aov / cat_aov - 1.0))
    wtp += 0.012 * (np.isin(referral_source, ["influencer", "email"]).astype(float))
    wtp += rng.normal(0, 0.026, n)
    actual_wtp = np.clip(wtp, 0.85, 1.25).round(4)

    # ================================================================== #
    # TARGET 2: converted  (given an offered price multiplier)
    # We randomise the offered multiplier around 1.0 (a flat-pricing world
    # with existing ad-hoc discounts) so the secondary classifier can learn
    # the price-response curve: list price vs adjusted price.
    # ================================================================== #
    offered_price_multiplier = np.clip(rng.normal(1.0, 0.06, n), 0.85, 1.20).round(4)
    price_gap = actual_wtp - offered_price_multiplier      # >0 => underpriced => converts more
    conv_logit = (
        -0.15
        + 8.5 * price_gap
        + 1.1 * (cross_merchant_trust_score / 100 - 0.5)
        + 0.25 * festival_intensity
        + 0.4 * (payment_success_rate - 0.9)
        - 0.3 * (return_rate - 0.15)
        + 0.2 * np.isin(referral_source, ["organic", "email"]).astype(float)
        + rng.normal(0, 0.35, n)
    )
    converted = (1 / (1 + np.exp(-conv_logit)) > rng.uniform(0, 1, n)).astype(int)

    # ================================================================== #
    # TARGET 3: offer_responded
    # Low-WTP customers engage with discount nudges; high-WTP customers
    # engage with premium-experience offers. Influencer/social traffic
    # responds more. Only meaningful when an offer would be shown.
    # ================================================================== #
    offer_logit = (
        -0.6
        + 1.4 * (0.5 - np.abs(actual_wtp - 1.0) / 0.4)          # extremes respond most
        + 0.9 * np.isin(referral_source, ["influencer", "social"]).astype(float)
        + 0.5 * is_festival.astype(float)
        + 0.6 * (converted == 1)
        + rng.normal(0, 0.4, n)
    )
    offer_responded = (1 / (1 + np.exp(-offer_logit)) > rng.uniform(0, 1, n)).astype(int)

    df = pd.DataFrame(
        {
            # ---- identifiers / context ----
            "txn_date": date_str,
            "month": month_num,
            "year_month": month_str,
            "digital_demand_index": [DEMAND_INDEX.get(m, 1.0) for m in month_str],
            # ---- customer signals ----
            "device_type": device_type,
            "city_tier": city_tier,
            "pin_code": pin_code,
            "income_tier": income_tier,
            "payment_method_preference": payment_pref,
            "time_of_day": time_of_day,
            "day_of_week": day_of_week,
            "referral_source": referral_source,
            "ip_type": ip_type,
            "ip_trust_multiplier": ip_trust_multiplier.round(4),
            # ---- behavioural history ----
            "historical_aov": historical_aov,
            "return_rate": return_rate.round(4),
            "payment_success_rate": payment_success_rate.round(4),
            "cod_completion_rate": cod_completion_rate.round(4),
            "cross_merchant_trust_score": cross_merchant_trust_score,
            "num_merchants_transacted": num_merchants,
            "account_age_days": account_age_days,
            # ---- transaction context ----
            "product_category": product_category,
            "cart_value": cart_value,
            "is_festival_period": is_festival.astype(int),
            "festival_intensity": festival_intensity,
            # ---- offered price (for conversion classifier) ----
            "offered_price_multiplier": offered_price_multiplier,
            # ---- targets ----
            "actual_wtp": actual_wtp,
            "converted": converted,
            "offer_responded": offer_responded,
        }
    )
    return df


# --------------------------------------------------------------------------- #
# Feature schema - the contract model/ and api/ both read
# --------------------------------------------------------------------------- #
FEATURE_SCHEMA = {
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


def main() -> None:
    require_pandas()
    df = generate()

    # quick calibration sanity checks printed for the reviewer
    fest = df[df.is_festival_period == 1]
    nonfest = df[df.is_festival_period == 0]
    log("  --- calibration checks ---")
    log(f"  festival AOV lift: {fest.cart_value.mean() / nonfest.cart_value.mean() - 1:+.1%} "
        f"(target +15-25%)")
    log(f"  festival conv lift: {fest.converted.mean() / nonfest.converted.mean() - 1:+.1%}")
    hi = df[(df.city_tier == 1) & (df.device_type == "iPhone")
            & (df.payment_method_preference == "Credit_Card")]
    lo = df[(df.city_tier == 3) & (df.device_type == "Android_budget")
            & (df.payment_method_preference == "COD")]
    log(f"  Tier1+iPhone+CC  actual_wtp mean={hi.actual_wtp.mean():.3f} "
        f"[{hi.actual_wtp.quantile(.1):.2f}-{hi.actual_wtp.quantile(.9):.2f}] (target ~1.10-1.25)")
    log(f"  Tier3+budget+COD actual_wtp mean={lo.actual_wtp.mean():.3f} "
        f"[{lo.actual_wtp.quantile(.1):.2f}-{lo.actual_wtp.quantile(.9):.2f}] (target ~0.85-0.95)")
    log(f"  overall conversion rate: {df.converted.mean():.1%}")
    log(f"  vpn/datacenter/tor share: {df.ip_type.isin(['vpn','datacenter','tor']).mean():.1%}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    SCHEMA_OUT.write_text(json.dumps(FEATURE_SCHEMA, indent=2))
    log(f"  wrote {OUT}  ({len(df):,} rows x {df.shape[1]} cols)")
    log(f"  wrote {SCHEMA_OUT}")
    write_source_sidecar(
        OUT,
        source="Synthetic generator (generate_synthetic.py), calibrated to "
        "RBI digital demand + Google Trends seasonality + festival calendar",
        live=False,
        note=f"seed={C.RANDOM_SEED}, rows={len(df)}",
    )


if __name__ == "__main__":
    main()
