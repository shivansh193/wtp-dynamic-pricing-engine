"""
Step 2 - RBI DBIE monthly digital payment statistics.

Target: UPI / card / wallet monthly transaction volume & value, 2022-2026,
written to  data/raw/rbi_digital_payments.csv

Reality check: dbie.rbi.org.in is a stateful ASP.NET WebForms portal that
requires a multi-step session (subject -> report -> parameter POST) and returns
XLS blobs. Scraping it headlessly is brittle and out of scope for a 200ms demo
backend. This script:

  1. Tries the DBIE "download as CSV" style endpoints (best effort).
  2. Falls back to a synthetic monthly series *calibrated to RBI / NPCI
     published headline numbers* (see RBI_UPI_ANCHORS_MN in config.py) with
     realistic festive-quarter seasonality and a plausible card/wallet mix.

The synthetic series is good enough to calibrate the synthetic customer
generator (Step 3) - which only needs the *shape* of monthly demand.
"""

from __future__ import annotations

import numpy as np

import config as C
from _util import log, months_between, require_pandas, write_source_sidecar

OUT = C.RAW_DIR / "rbi_digital_payments.csv"


def _try_live() -> "object | None":
    """Best-effort attempt at a real DBIE pull. Returns a DataFrame or None."""
    pd = require_pandas()
    # DBIE occasionally exposes flat CSVs under this path pattern; try a couple.
    candidates = [
        "https://data.rbi.org.in/DBIE/dbie.rbi?site=statistics",  # landing only
    ]
    from _util import http_get

    for url in candidates:
        resp = http_get(url, timeout=15)
        if resp is None:
            continue
        # We got the landing page but not machine-readable data - bail to fallback.
        log("  DBIE reachable but no direct CSV endpoint; using calibrated fallback")
        return None
    log("  DBIE not reachable; using calibrated fallback")
    return None


def _synthetic() -> "object":
    pd = require_pandas()
    rng = np.random.default_rng(C.RANDOM_SEED)

    months = months_between("2022-01", C.DATA_MAX_MONTH)

    # ---- interpolate UPI volume (millions of txns) between published anchors ----
    anchor_idx = {}
    for i, m in enumerate(months):
        if m in C.RBI_UPI_ANCHORS_MN:
            anchor_idx[i] = C.RBI_UPI_ANCHORS_MN[m]
    idxs = sorted(anchor_idx)
    xp = np.array(idxs, dtype=float)
    fp = np.array([anchor_idx[i] for i in idxs], dtype=float)
    upi_trend = np.interp(np.arange(len(months)), xp, fp)

    # festive-quarter seasonality: Sep-Nov lifted, Feb dip
    season = np.array(
        [0.96, 0.94, 0.99, 1.00, 1.01, 1.00, 1.02, 1.05, 1.10, 1.14, 1.08, 1.05]
    )
    upi_vol_mn = []
    for i, m in enumerate(months):
        mm = int(m.split("-")[1]) - 1
        noise = rng.normal(1.0, 0.015)
        upi_vol_mn.append(upi_trend[i] * season[mm] * noise)
    upi_vol_mn = np.array(upi_vol_mn)

    # avg UPI ticket size drifts down over time (more P2M small-value) ~ INR
    upi_avg_ticket = np.linspace(1650, 1240, len(months)) * rng.normal(1.0, 0.01, len(months))
    upi_val_cr = upi_vol_mn * upi_avg_ticket / 1e7  # INR crore

    # ---- cards: credit + debit, slower growth, less seasonal ----
    card_trend = np.linspace(2400, 3800, len(months))  # million txns/month
    card_vol_mn = card_trend * (0.5 + 0.5 * season[[int(m.split("-")[1]) - 1 for m in months]])
    card_vol_mn *= rng.normal(1.0, 0.02, len(months))
    card_avg_ticket = np.linspace(3600, 4200, len(months))
    card_val_cr = card_vol_mn * card_avg_ticket / 1e7

    # ---- prepaid wallets (PPI): roughly flat, mild decline as share ----
    wallet_vol_mn = np.linspace(520, 610, len(months)) * rng.normal(1.0, 0.03, len(months))
    wallet_avg_ticket = np.linspace(640, 720, len(months))
    wallet_val_cr = wallet_vol_mn * wallet_avg_ticket / 1e7

    df = pd.DataFrame(
        {
            "month": months,
            "upi_txn_millions": np.round(upi_vol_mn, 1),
            "upi_value_inr_crore": np.round(upi_val_cr, 0),
            "card_txn_millions": np.round(card_vol_mn, 1),
            "card_value_inr_crore": np.round(card_val_cr, 0),
            "wallet_txn_millions": np.round(wallet_vol_mn, 1),
            "wallet_value_inr_crore": np.round(wallet_val_cr, 0),
        }
    )
    df["total_digital_txn_millions"] = (
        df.upi_txn_millions + df.card_txn_millions + df.wallet_txn_millions
    ).round(1)
    # normalised demand index used by the synthetic generator
    base = df.total_digital_txn_millions.iloc[:12].mean()
    df["digital_demand_index"] = (df.total_digital_txn_millions / base).round(4)
    return df


def main() -> None:
    log("Fetching RBI DBIE digital payment statistics...")
    df = _try_live()
    live = df is not None
    if not live:
        df = _synthetic()

    df.to_csv(OUT, index=False)
    log(f"  wrote {OUT}  ({len(df)} months)")
    write_source_sidecar(
        OUT,
        source="RBI DBIE (dbie.rbi.org.in) digital payments" if live
        else "Synthetic, calibrated to RBI/NPCI published headline figures",
        live=live,
        note="UPI anchors: " + ", ".join(f"{k}={v}mn" for k, v in C.RBI_UPI_ANCHORS_MN.items()),
    )


if __name__ == "__main__":
    main()
