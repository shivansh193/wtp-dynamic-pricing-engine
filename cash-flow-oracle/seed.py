"""
One-shot seeder for the Cash Flow Oracle scaffold.

    python -m cash_flow_oracle.seed

  1. connects to Postgres (CFO_DATABASE_URL / DATABASE_URL) or a local SQLite file
  2. loads the RBI monthly macro series
  3. generates 10 merchants x 3y daily settlements and persists them

Idempotent: re-running upserts merchants + RBI and skips settlement rows that
already exist (INSERT ... ON CONFLICT DO NOTHING / INSERT OR IGNORE).
"""

from __future__ import annotations

import asyncio
import time

import numpy as np

from . import config as C
from .data_pipeline.fetch_rbi import load_rows as load_rbi_rows
from .data_pipeline.generate_settlements import generate_all
from .db import store
from .models.garch import fit_garch


async def seed_into(the_store) -> dict:
    """Populate an *already-connected* store. Returns a small summary.
    Used by seed.main() and by the API's lazy first-run guard."""
    rbi = load_rbi_rows()
    n_rbi = await the_store.upsert_rbi(rbi)

    merchants, settlements = generate_all()
    for m in merchants:
        await the_store.upsert_merchant(m)
    n = await the_store.bulk_insert_settlements(settlements)

    # ---- per-merchant derived stats from the generated series ----
    #   avg_daily_settlement  = trailing-365-day mean net settlement
    #   settlement_volatility = mean GARCH(1,1) conditional daily-return vol
    #   operating_threshold   = 30% of the monthly average settlement
    by_m: dict[str, list[float]] = {}
    for (mid, _d, _g, _r, _f, net, _c) in settlements:
        by_m.setdefault(mid, []).append(float(net))
    for mid, nets in by_m.items():
        arr = np.asarray(nets, dtype=float)
        avg_daily = float(arr[-365:].mean())
        cv = fit_garch(arr).conditional_vol
        vol = float(np.mean(cv[-120:])) if cv.size else 0.0
        threshold = C.OPERATING_THRESHOLD_FRACTION * avg_daily * 30.0
        await the_store.update_merchant_stats(
            mid, avg_daily=round(avg_daily, 2),
            volatility=round(vol, 6), threshold=round(threshold, 2),
        )
    return {"rbi_months": n_rbi, "merchants": len(merchants), "settlement_rows": n}


async def main() -> None:
    t0 = time.time()
    await store.connect()
    print(f"[cfo.seed] storage backend: {store.backend}")
    summary = await seed_into(store)
    print(f"[cfo.seed] {summary}")
    await store.close()
    print(f"[cfo.seed] done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
