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
    .replace("NUMERIC(10,6)", "REAL")
    .replace("NUMERIC(6,3)", "REAL")
    .replace("NUMERIC", "REAL")
    .replace("JSONB", "TEXT")
    .replace("REFERENCES merchants(merchant_id)", "")
)

# best-effort column adds for a DB created by an earlier scaffold version
_MIGRATIONS = [
    "ALTER TABLE merchants ADD COLUMN city_tier INTEGER",
    "ALTER TABLE merchants ADD COLUMN avg_daily_settlement REAL",
    "ALTER TABLE merchants ADD COLUMN settlement_volatility REAL",
    "ALTER TABLE merchants ADD COLUMN operating_threshold REAL",
    "ALTER TABLE merchants ADD COLUMN capital_disbursement_days INTEGER",
    "ALTER TABLE merchants ADD COLUMN late_payment_penalty_rate REAL",
]


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
                    for stmt in _MIGRATIONS:
                        try:
                            await con.execute(stmt.replace(
                                "ADD COLUMN", "ADD COLUMN IF NOT EXISTS"))
                        except Exception:  # noqa: BLE001
                            pass
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
            for stmt in _MIGRATIONS:
                try:
                    con.execute(stmt)
                except sqlite3.OperationalError:
                    pass  # column already exists
            con.commit()
        finally:
            con.close()

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()

    # ------------------------------------------------------------------ #
    # writes (used by seed.py)
    # ------------------------------------------------------------------ #
    _MERCHANT_COLS = (
        "merchant_id", "archetype", "display_name", "onboarded_on", "city_tier",
        "avg_daily_settlement", "settlement_volatility", "operating_threshold",
        "capital_disbursement_days", "late_payment_penalty_rate",
    )

    async def upsert_merchant(self, m: dict) -> None:
        onb = m["onboarded_on"]
        vals = (
            m["merchant_id"], m["archetype"], m["display_name"],
            onb if hasattr(onb, "isoformat") else onb,
            m.get("city_tier"), m.get("avg_daily_settlement"),
            m.get("settlement_volatility"), m.get("operating_threshold"),
            m.get("capital_disbursement_days"), m.get("late_payment_penalty_rate"),
        )
        if self.backend == "postgres":
            async with self._pool.acquire() as con:  # type: ignore[union-attr]
                await con.execute(
                    """INSERT INTO merchants (merchant_id, archetype, display_name,
                         onboarded_on, city_tier, avg_daily_settlement,
                         settlement_volatility, operating_threshold,
                         capital_disbursement_days, late_payment_penalty_rate)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                       ON CONFLICT (merchant_id) DO UPDATE SET
                         archetype=EXCLUDED.archetype, display_name=EXCLUDED.display_name,
                         onboarded_on=EXCLUDED.onboarded_on, city_tier=EXCLUDED.city_tier,
                         avg_daily_settlement=EXCLUDED.avg_daily_settlement,
                         settlement_volatility=EXCLUDED.settlement_volatility,
                         operating_threshold=EXCLUDED.operating_threshold,
                         capital_disbursement_days=EXCLUDED.capital_disbursement_days,
                         late_payment_penalty_rate=EXCLUDED.late_payment_penalty_rate""",
                    *vals,
                )
            return
        vals = tuple(v.isoformat() if hasattr(v, "isoformat") else v for v in vals)
        await asyncio.to_thread(
            self._sqlite_exec,
            "INSERT OR REPLACE INTO merchants "
            "(merchant_id, archetype, display_name, onboarded_on, city_tier, "
            "avg_daily_settlement, settlement_volatility, operating_threshold, "
            "capital_disbursement_days, late_payment_penalty_rate) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            vals,
        )

    async def update_merchant_stats(self, merchant_id: str, *, avg_daily: float,
                                    volatility: float, threshold: float) -> None:
        if self.backend == "postgres":
            async with self._pool.acquire() as con:  # type: ignore[union-attr]
                await con.execute(
                    "UPDATE merchants SET avg_daily_settlement=$2, "
                    "settlement_volatility=$3, operating_threshold=$4 "
                    "WHERE merchant_id=$1",
                    merchant_id, avg_daily, volatility, threshold,
                )
            return
        await asyncio.to_thread(
            self._sqlite_exec,
            "UPDATE merchants SET avg_daily_settlement=?, settlement_volatility=?, "
            "operating_threshold=? WHERE merchant_id=?",
            (avg_daily, volatility, threshold, merchant_id),
        )

    # ---- scenario runs ---- #
    async def save_scenario(self, scenario_id: str, merchant_id: str, shock_type: str,
                            shock_magnitude: float, shock_start_date: date,
                            shock_duration_days: int, result: dict) -> None:
        import json as _json

        blob = _json.dumps(result, default=str)
        sd = shock_start_date.isoformat() if hasattr(shock_start_date, "isoformat") \
            else str(shock_start_date)
        if self.backend == "postgres":
            async with self._pool.acquire() as con:  # type: ignore[union-attr]
                await con.execute(
                    """INSERT INTO scenario_runs (scenario_id, merchant_id, shock_type,
                         shock_magnitude, shock_start_date, shock_duration_days, result)
                       VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb)
                       ON CONFLICT (scenario_id) DO UPDATE SET result=EXCLUDED.result""",
                    scenario_id, merchant_id, shock_type, shock_magnitude, sd,
                    shock_duration_days, blob,
                )
            return
        await asyncio.to_thread(
            self._sqlite_exec,
            "INSERT OR REPLACE INTO scenario_runs (scenario_id, merchant_id, "
            "shock_type, shock_magnitude, shock_start_date, shock_duration_days, "
            "result) VALUES (?,?,?,?,?,?,?)",
            (scenario_id, merchant_id, shock_type, shock_magnitude, sd,
             shock_duration_days, blob),
        )

    async def list_scenarios(self, merchant_id: str) -> list[dict]:
        if self.backend == "postgres":
            async with self._pool.acquire() as con:  # type: ignore[union-attr]
                rows = await con.fetch(
                    "SELECT * FROM scenario_runs WHERE merchant_id=$1 "
                    "ORDER BY created_at DESC LIMIT 50", merchant_id)
            return [dict(r) for r in rows]
        return await asyncio.to_thread(
            self._sqlite_query,
            "SELECT * FROM scenario_runs WHERE merchant_id=? "
            "ORDER BY created_at DESC LIMIT 50", (merchant_id,),
        )

    # ---- LLM recommendation cache ---- #
    async def get_llm_cache(self, merchant_id: str, context_hash: str,
                            ttl_hours: int) -> dict | None:
        if self.backend == "postgres":
            async with self._pool.acquire() as con:  # type: ignore[union-attr]
                row = await con.fetchrow(
                    "SELECT recommendation, model, source, created_at "
                    "FROM llm_recommendations WHERE merchant_id=$1 AND context_hash=$2 "
                    "AND created_at > now() - ($3 || ' hours')::interval",
                    merchant_id, context_hash, str(ttl_hours),
                )
            return dict(row) if row else None
        rows = await asyncio.to_thread(
            self._sqlite_query,
            "SELECT recommendation, model, source, created_at "
            "FROM llm_recommendations WHERE merchant_id=? AND context_hash=? "
            "AND created_at > datetime('now', ?)",
            (merchant_id, context_hash, f"-{int(ttl_hours)} hours"),
        )
        return rows[0] if rows else None

    async def save_llm_cache(self, merchant_id: str, context_hash: str,
                             recommendation: str, model: str, source: str) -> None:
        if self.backend == "postgres":
            async with self._pool.acquire() as con:  # type: ignore[union-attr]
                await con.execute(
                    """INSERT INTO llm_recommendations
                         (merchant_id, context_hash, recommendation, model, source, created_at)
                       VALUES ($1,$2,$3,$4,$5, now())
                       ON CONFLICT (merchant_id, context_hash) DO UPDATE SET
                         recommendation=EXCLUDED.recommendation, model=EXCLUDED.model,
                         source=EXCLUDED.source, created_at=now()""",
                    merchant_id, context_hash, recommendation, model, source,
                )
            return
        await asyncio.to_thread(
            self._sqlite_exec,
            "INSERT OR REPLACE INTO llm_recommendations "
            "(merchant_id, context_hash, recommendation, model, source, created_at) "
            "VALUES (?,?,?,?,?, datetime('now'))",
            (merchant_id, context_hash, recommendation, model, source),
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
