"""
Async PostgreSQL access (asyncpg).

Everything degrades gracefully: if Postgres is unreachable and DB_REQUIRED is
false, decisions are logged to an in-process ring buffer so the demo keeps
working. `/metrics` and `/decision/{id}` transparently read from whichever
backend is active.
"""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg

from .config import settings
from .logging_util import log

SCHEMA_SQL = (settings.REPO_ROOT / "api" / "schema.sql").read_text()


class _MemoryStore:
    """Fallback log store when Postgres is down. Not persistent."""

    def __init__(self, maxlen: int = 20_000):
        self._rows: deque[dict] = deque(maxlen=maxlen)
        self._id = 0

    def insert(self, row: dict) -> int:
        self._id += 1
        row = {**row, "id": self._id, "created_at": datetime.now(timezone.utc)}
        self._rows.append(row)
        return self._id

    def by_session(self, session_id: str) -> list[dict]:
        return [r for r in self._rows if r["session_id"] == session_id]

    def all(self) -> list[dict]:
        return list(self._rows)


class Database:
    def __init__(self) -> None:
        self._pool: Optional[asyncpg.Pool] = None
        self._mem = _MemoryStore()
        self.backend = "uninitialised"

    # ------------------------------------------------------------------ #
    async def connect(self) -> None:
        try:
            self._pool = await asyncpg.create_pool(
                dsn=settings.DATABASE_URL, min_size=1, max_size=8,
                command_timeout=5, timeout=5,
            )
            async with self._pool.acquire() as con:
                await con.execute(SCHEMA_SQL)
            self.backend = "postgres"
            log(f"database connected: postgres ({_safe_dsn(settings.DATABASE_URL)})")
        except Exception as exc:  # noqa: BLE001
            if settings.DB_REQUIRED:
                raise
            self._pool = None
            self.backend = "memory"
            log(f"database unavailable ({exc!r}) -> using in-memory decision log")

    async def disconnect(self) -> None:
        if self._pool is not None:
            await self._pool.close()

    # ------------------------------------------------------------------ #
    async def log_decision(self, record: dict[str, Any]) -> int:
        """Persist one /personalize decision. Best-effort; never raises."""
        if self._pool is None:
            return self._mem.insert(record)
        try:
            async with self._pool.acquire() as con:
                row = await con.fetchrow(
                    """
                    INSERT INTO pricing_decisions (
                        session_id, input_signals, ip_address, list_price,
                        ip_type, ip_trust_multiplier, ip_is_whitelisted,
                        wtp_score, conversion_probability, model_confidence, shap_values,
                        final_price, price_delta_pct, offer_type, payment_methods_shown,
                        cod_eligible, instant_refund_eligible, reasoning,
                        latency_ms, budget_exceeded
                    ) VALUES (
                        $1, $2::jsonb, $3::inet, $4,
                        $5, $6, $7,
                        $8, $9, $10, $11::jsonb,
                        $12, $13, $14, $15::jsonb,
                        $16, $17, $18,
                        $19, $20
                    ) RETURNING id
                    """,
                    record["session_id"],
                    json.dumps(record["input_signals"]),
                    _maybe_ip(record.get("ip_address")),
                    record["list_price"],
                    record.get("ip_type"),
                    record.get("ip_trust_multiplier"),
                    record.get("ip_is_whitelisted"),
                    record["wtp_score"],
                    record.get("conversion_probability"),
                    record.get("model_confidence"),
                    json.dumps(record.get("shap_values")),
                    record["final_price"],
                    record["price_delta_pct"],
                    record["offer_type"],
                    json.dumps(record["payment_methods_shown"]),
                    record.get("cod_eligible"),
                    record.get("instant_refund_eligible"),
                    record.get("reasoning"),
                    record["latency_ms"],
                    record.get("budget_exceeded", False),
                )
                return int(row["id"])
        except Exception as exc:  # noqa: BLE001
            log(f"log_decision failed ({exc!r}) -> memory fallback for this row")
            return self._mem.insert(record)

    # ------------------------------------------------------------------ #
    async def get_session(self, session_id: str) -> list[dict]:
        if self._pool is None:
            return self._mem.by_session(session_id)
        async with self._pool.acquire() as con:
            rows = await con.fetch(
                "SELECT * FROM pricing_decisions WHERE session_id=$1 ORDER BY created_at",
                session_id,
            )
        return [dict(r) for r in rows]

    async def fetch_all(self, limit: int = 50_000) -> list[dict]:
        if self._pool is None:
            return self._mem.all()
        async with self._pool.acquire() as con:
            rows = await con.fetch(
                "SELECT * FROM pricing_decisions ORDER BY created_at DESC LIMIT $1", limit
            )
        return [dict(r) for r in rows]


def _safe_dsn(dsn: str) -> str:
    # hide password in logs
    if "@" in dsn and "//" in dsn:
        head, tail = dsn.split("//", 1)
        creds, host = tail.split("@", 1)
        user = creds.split(":", 1)[0]
        return f"{head}//{user}:***@{host}"
    return dsn


def _maybe_ip(ip: Any):
    if not ip:
        return None
    return str(ip)


db = Database()
