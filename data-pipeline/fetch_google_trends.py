"""
Step 2 - Google Trends monthly search interest for Indian ecommerce categories.

Target: monthly search-interest index (0-100 style) for
fashion / electronics / grocery / home / beauty, 2022-2026 (geo=IN),
written to  data/raw/google_trends_categories.csv

Uses `pytrends`. Google Trends has no API key but aggressively rate-limits
unauthenticated callers (HTTP 429). On any failure we emit a synthetic series
built from CATEGORY_SEASONALITY in config.py plus a mild secular growth trend,
so downstream calibration is deterministic.
"""

from __future__ import annotations

import time

import numpy as np

import config as C
from _util import log, months_between, require_pandas, write_source_sidecar

OUT = C.RAW_DIR / "google_trends_categories.csv"

# Google Trends "search term" per category (India ecommerce intent phrasing)
TREND_TERMS = {
    "fashion": "online shopping clothes",
    "electronics": "buy mobile online",
    "grocery": "grocery online",
    "home": "home furniture online",
    "beauty": "beauty products online",
}


def _try_live():
    pd = require_pandas()
    try:
        from pytrends.request import TrendReq
    except ImportError:
        log("  pytrends not installed; using synthetic Trends series")
        return None

    try:
        py = TrendReq(hl="en-IN", tz=330, timeout=(10, 25), retries=2, backoff_factor=0.5)
        frames = []
        for cat, term in TREND_TERMS.items():
            py.build_payload([term], timeframe="2022-01-01 2026-08-31", geo="IN")
            raw = py.interest_over_time()
            if raw is None or raw.empty:
                raise RuntimeError(f"empty Trends response for {term!r}")
            s = raw[term].resample("MS").mean().rename(cat)
            frames.append(s)
            time.sleep(2)  # be polite to the endpoint
        df = pd.concat(frames, axis=1)
        df.index = df.index.strftime("%Y-%m")
        df = df.reset_index(names="month")
        return df
    except Exception as exc:  # noqa: BLE001
        log(f"  live Google Trends fetch failed: {exc!r}; using synthetic series")
        return None


def _synthetic():
    pd = require_pandas()
    rng = np.random.default_rng(C.RANDOM_SEED + 1)
    months = months_between("2022-01", C.DATA_MAX_MONTH)

    data = {"month": months}
    for cat in C.ECOMMERCE_CATEGORIES:
        shape = np.array(C.CATEGORY_SEASONALITY[cat])
        # secular growth: electronics + beauty grow faster than grocery
        growth_per_year = {
            "fashion": 0.06, "electronics": 0.10, "grocery": 0.04,
            "home": 0.05, "beauty": 0.11,
        }[cat]
        vals = []
        for i, m in enumerate(months):
            mm = int(m.split("-")[1]) - 1
            yr_frac = i / 12.0
            level = shape[mm] * (1 + growth_per_year) ** yr_frac
            vals.append(level * rng.normal(1.0, 0.03))
        vals = np.array(vals)
        # scale to a 0-100 style index like Google Trends
        vals = 100 * vals / vals.max()
        data[cat] = np.round(vals, 1)
    return pd.DataFrame(data)


def main() -> None:
    log("Fetching Google Trends category interest (pytrends)...")
    df = _try_live()
    live = df is not None
    if not live:
        df = _synthetic()

    df.to_csv(OUT, index=False)
    log(f"  wrote {OUT}  ({len(df)} months x {len(C.ECOMMERCE_CATEGORIES)} categories)")
    write_source_sidecar(
        OUT,
        source="Google Trends via pytrends (geo=IN)" if live
        else "Synthetic, built from CATEGORY_SEASONALITY + secular growth",
        live=live,
        note="terms: " + "; ".join(f"{k}={v!r}" for k, v in TREND_TERMS.items()),
    )


if __name__ == "__main__":
    main()
