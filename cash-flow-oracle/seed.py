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

from .data_pipeline.fetch_rbi import load_rows as load_rbi_rows
from .data_pipeline.generate_settlements import generate_all
from .db import store


async def main() -> None:
    t0 = time.time()
    await store.connect()
    print(f"[cfo.seed] storage backend: {store.backend}")

    rbi = load_rbi_rows()
    n_rbi = await store.upsert_rbi(rbi)
    print(f"[cfo.seed] RBI months upserted: {n_rbi}")

    merchants, settlements = generate_all()
    for m in merchants:
        await store.upsert_merchant(
            m["merchant_id"], m["archetype"], m["display_name"], m["onboarded_on"]
        )
    print(f"[cfo.seed] merchants upserted: {len(merchants)}")

    n = await store.bulk_insert_settlements(settlements)
    print(f"[cfo.seed] settlement rows written: {n:,}")

    await store.close()
    print(f"[cfo.seed] done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
