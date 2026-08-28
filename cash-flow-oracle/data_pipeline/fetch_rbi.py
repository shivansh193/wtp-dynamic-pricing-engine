"""
RBI DBIE monthly digital-payment statistics -> PostgreSQL (Track 04 macro context).

Reuses the Track 01 pipeline's output if present
(`data/raw/rbi_digital_payments.csv`), otherwise reproduces the same calibrated
fallback series inline so this module is self-contained. Rows are handed to
`db.store.upsert_rbi()`.
"""

from __future__ import annotations

import csv

from .. import config as C


def load_rows() -> list[tuple]:
    """Return list of (month, upi_mn, card_mn, wallet_mn, demand_index)."""
    path = C.RBI_CSV_HINT
    if path.exists():
        rows = []
        with path.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                rows.append((
                    r["month"],
                    _f(r.get("upi_txn_millions")),
                    _f(r.get("card_txn_millions")),
                    _f(r.get("wallet_txn_millions")),
                    _f(r.get("digital_demand_index"), 1.0),
                ))
        print(f"[cfo.rbi] loaded {len(rows)} months from {path}")
        return rows

    print("[cfo.rbi] Track 01 RBI CSV not found -> synthetic fallback series")
    return _synthetic()


def _synthetic() -> list[tuple]:
    import numpy as np

    anchors = {
        "2022-01": 4610, "2022-12": 7820, "2023-06": 9330, "2023-12": 12020,
        "2024-06": 13890, "2024-12": 16730, "2025-06": 18400, "2026-06": 22600,
    }
    months = []
    y, m = 2022, 1
    while (y, m) <= (2026, 8):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            m, y = 1, y + 1
    idx = [i for i, mm in enumerate(months) if mm in anchors]
    xp = np.array(idx, dtype=float)
    fp = np.array([anchors[months[i]] for i in idx], dtype=float)
    upi = np.interp(np.arange(len(months)), xp, fp)
    base = upi[:12].mean()
    out = []
    for i, mm in enumerate(months):
        card = 2400 + (3800 - 2400) * i / len(months)
        wallet = 520 + (610 - 520) * i / len(months)
        out.append((mm, round(float(upi[i]), 1), round(card, 1), round(wallet, 1),
                    round(float((upi[i] + card + wallet) / (base + 2400 + 520)), 4)))
    return out


def _f(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
