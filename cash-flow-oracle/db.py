"""
Storage layer for the Cash Flow Oracle scaffold.

Two backends, same async interface:
  * PostgreSQL via asyncpg  - when CFO_DATABASE_URL / DATABASE_URL is set and
    asyncpg is importable and the server is reachable.
  * SQLite via stdlib sqlite3 (run in a worker thread) - the always-available
    default, so the scaffold runs with zero infra.

The API only needs read paths; `seed.py` uses the write paths.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from . import config as C

try:
    import asyncpg  # type: ignore
except Exception:  # noqa: BLE001
    asyncpg = None  # type: ignore

_SCHEMA = (C.MODULE_DIR / "schema.sql").read_text()
# SQLite doesn't understand BIGSERIAL / NUMERIC(p,s) / TIMESTAMPTZ / now();
# translate the few incompatible bits for the fallback.
_SQLITE_SCHEMA = (
    _SCHEMA.replace("BIGSERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    .replace("TIMESTAMPTZ NOT NULL DEFAULT now()", "TEXT NOT NULL DEFAULT (datetime('now'))")
    .replace("NUMERIC(16,2)", "REAL")
    .replace("NUMERIC", "REAL")
    .replace("REFERENCES merchants(merchant_id)", "")
)


class Store:
    def __init__(self) -> None:
        self.backend = "sqlite"
        self._pool = None
        self._sqlite_path = str(C.SQLITE_FALLBACK)

    # ------------------------------------------------------------------ #
    async def connect(self) -> None:
        dsn = C.DATABASE_URL
        if dsn and asyncpg is not None:
            try:
                self._pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4,
                                                       timeout=5, command_timeout=10)
                async with self._pool.acquire() as con:
                    await con.execute(_SCHEMA)
                self.backend = "postgres"
                return
            except Exception as exc:  # noqa: BLE001
                print(f"[cfo.db] postgres unavailable ({exc!r}) -> sqlite fallback")
                self._pool = None
        await asyncio.to_thread(self._sqlite_init)
        self.backend = "sqlite"

    def _sqlite_init(self) -> None:
        con = sqlite3.connect(self._sqlite_path)
        try:
            con.executescript(_SQLITE_SCHEMA)
            con.commit()
        finally:
            con.close()

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()

    # ------------------------------------------------------------------ #
    # writes (used by seed.py)
    # ------------------------------------------------------------------ #
    async def upsert_merchant(self, merchant_id: str, archetype: str,
                              display_name: str, onboarded_on: date) -> None:
        if self.backend == "postgres":
            async with self._pool.acquire() as con:  # type: ignore[union-attr]
                await con.execute(
                    """INSERT INTO merchants (merchant_id, archetype, display_name, onboarded_on)
                       VALUES ($1,$2,$3,$4)
                       ON CONFLICT (merchant_id) DO UPDATE SET archetype=EXCLUDED.archetype,
                         display_name=EXCLUDED.display_name, onboarded_on=EXCLUDED.onboarded_on""",
                    merchant_id, archetype, display_name, onboarded_on,
                )
            return
        await asyncio.to_thread(
            self._sqlite_exec,
            "INSERT OR REPLACE INTO merchants VALUES (?,?,?,?)",
            (merchant_id, archetype, display_name, onboarded_on.isoformat()),
        )

    async def bulk_insert_settlements(self, rows: Iterable[tuple]) -> int:
        rows = list(rows)
        if not rows:
            return 0
        if self.backend == "postgres":
            async with self._pool.acquire() as con:  # type: ignore[union-attr]
                await con.executemany(
                    """INSERT INTO merchant_settlements
                       (merchant_id, settlement_date, gross_inr, refunds_inr, fees_inr,
                        net_settled_inr, txn_count)
                       VALUES ($1,$2,$3,$4,$5,$6,$7)
                       ON CONFLICT (merchant_id, settlement_date) DO NOTHING""",
                    rows,
                )
            return len(rows)
        await asyncio.to_thread(
            self._sqlite_many,
            "INSERT OR IGNORE INTO merchant_settlements VALUES (?,?,?,?,?,?,?)",
            [(m, d.isoformat() if hasattr(d, "isoformat") else d, g, r, f, n, c) for
             (m, d, g, r, f, n, c) in rows],
        )
        return len(rows)

    async def upsert_rbi(self, rows: Iterable[tuple]) -> int:
        rows = list(rows)
        if self.backend == "postgres":
            async with self._pool.acquire() as con:  # type: ignore[union-attr]
                await con.executemany(
                    """INSERT INTO rbi_digital_payments
                       (month, upi_txn_millions, card_txn_millions, wallet_txn_millions,
                        digital_demand_index)
                       VALUES ($1,$2,$3,$4,$5)
                       ON CONFLICT (month) DO UPDATE SET digital_demand_index=EXCLUDED.digital_demand_index""",
                    rows,
                )
            return len(rows)
        await asyncio.to_thread(
            self._sqlite_many,
            "INSERT OR REPLACE INTO rbi_digital_payments VALUES (?,?,?,?,?)", rows,
        )
        return len(rows)

    # ------------------------------------------------------------------ #
    # reads (used by the API)
    # ------------------------------------------------------------------ #
    async def list_merchants(self) -> list[dict[str, Any]]:
        if self.backend == "postgres":
            async with self._pool.acquire() as con:  # type: ignore[union-attr]
                rows = await con.fetch("SELECT * FROM merchants ORDER BY merchant_id")
            return [dict(r) for r in rows]
        return await asyncio.to_thread(
            self._sqlite_query, "SELECT * FROM merchants ORDER BY merchant_id", ()
        )

    async def get_settlements(self, merchant_id: str) -> list[dict[str, Any]]:
        if self.backend == "postgres":
            async with self._pool.acquire() as con:  # type: ignore[union-attr]
                rows = await con.fetch(
                    """SELECT settlement_date, net_settled_inr, gross_inr, txn_count
                       FROM merchant_settlements WHERE merchant_id=$1 ORDER BY settlement_date""",
                    merchant_id,
                )
            return [dict(r) for r in rows]
        return await asyncio.to_thread(
            self._sqlite_query,
            """SELECT settlement_date, net_settled_inr, gross_inr, txn_count
               FROM merchant_settlements WHERE merchant_id=? ORDER BY settlement_date""",
            (merchant_id,),
        )

    # ------------------------------------------------------------------ #
    # sqlite worker helpers
    # ------------------------------------------------------------------ #
    def _sqlite_exec(self, sql: str, params: tuple) -> None:
        con = sqlite3.connect(self._sqlite_path)
        try:
            con.execute(sql, params)
            con.commit()
        finally:
            con.close()

    def _sqlite_many(self, sql: str, rows: list[tuple]) -> None:
        con = sqlite3.connect(self._sqlite_path)
        try:
            con.executemany(sql, rows)
            con.commit()
        finally:
            con.close()

    def _sqlite_query(self, sql: str, params: tuple) -> list[dict]:
        con = sqlite3.connect(self._sqlite_path)
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql, params).fetchall()]
        finally:
            con.close()


store = Store()
