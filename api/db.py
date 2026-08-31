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
        self._iv: deque[dict] = deque(maxlen=80_000)   # intervention events
        self._id = 0
        self._iv_id = 0

    def insert(self, row: dict) -> int:
        self._id += 1
        row = {**row, "id": self._id, "created_at": datetime.now(timezone.utc)}
        self._rows.append(row)
        return self._id

    def by_session(self, session_id: str) -> list[dict]:
        return [r for r in self._rows if r["session_id"] == session_id]

    def all(self) -> list[dict]:
        return list(self._rows)

    # ---- intervention events ---- #
    def add_interventions(self, evs: list[dict]) -> None:
        for e in evs:
            self._iv_id += 1
            self._iv.append({**e, "id": self._iv_id,
                             "created_at": datetime.now(timezone.utc),
                             "converted": e.get("converted")})

    def settle_interventions(self, session_id: str, converted: bool) -> int:
        n = 0
        for e in self._iv:
            if e["session_id"] == session_id and e.get("converted") is None:
                e["converted"] = bool(converted)
                e["settled_at"] = datetime.now(timezone.utc)
                n += 1
        return n

    def interventions_all(self) -> list[dict]:
        return list(self._iv)


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
                        friction_type, friction_secondary, friction_confidence,
                        primary_intervention, secondary_intervention, checkout_config,
                        latency_ms, budget_exceeded
                    ) VALUES (
                        $1, $2::jsonb, $3::inet, $4,
                        $5, $6, $7,
                        $8, $9, $10, $11::jsonb,
                        $12, $13, $14, $15::jsonb,
                        $16, $17, $18,
                        $19, $20, $21,
                        $22, $23, $24::jsonb,
                        $25, $26
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
                    record.get("friction_type"),
                    record.get("friction_secondary"),
                    record.get("friction_confidence"),
                    record.get("primary_intervention"),
                    record.get("secondary_intervention"),
                    json.dumps(record.get("checkout_config")),
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

    # ------------------------------------------------------------------ #
    # Intervention performance tracker (Step 6)
    # ------------------------------------------------------------------ #
    async def log_interventions(self, *, session_id: str, segment_key: str | None,
                                product_category: str | None, list_price: float | None,
                                final_price: float | None, friction_type: str | None,
                                items: list[tuple[str, str]]) -> None:
        """Record every intervention *shown* on one checkout (outcome unknown
        until the session settles). Best-effort; never raises."""
        if not items:
            return
        evs = [{
            "session_id": session_id, "segment_key": segment_key,
            "product_category": product_category, "list_price": list_price,
            "final_price": final_price, "friction_type": friction_type,
            "intervention_id": iid, "slot": slot, "converted": None,
        } for iid, slot in items]
        if self._pool is None:
            self._mem.add_interventions(evs)
            return
        try:
            async with self._pool.acquire() as con:
                await con.executemany(
                    """
                    INSERT INTO intervention_events (
                        session_id, segment_key, product_category, list_price,
                        final_price, friction_type, intervention_id, slot
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                    """,
                    [(e["session_id"], e["segment_key"], e["product_category"],
                      e["list_price"], e["final_price"], e["friction_type"],
                      e["intervention_id"], e["slot"]) for e in evs],
                )
        except Exception as exc:  # noqa: BLE001
            log(f"log_interventions failed ({exc!r}) -> memory fallback")
            self._mem.add_interventions(evs)

    async def settle_interventions(self, session_id: str, converted: bool) -> int:
        """Stamp the outcome on every still-open intervention event for a
        session (called when the demo session completes / abandons)."""
        if self._pool is None:
            return self._mem.settle_interventions(session_id, converted)
        try:
            async with self._pool.acquire() as con:
                res = await con.execute(
                    "UPDATE intervention_events SET converted=$2, settled_at=now() "
                    "WHERE session_id=$1 AND converted IS NULL",
                    session_id, bool(converted),
                )
            # asyncpg returns e.g. "UPDATE 3"
            return int(str(res).split()[-1]) if res else 0
        except Exception as exc:  # noqa: BLE001
            log(f"settle_interventions failed ({exc!r}) -> memory fallback")
            return self._mem.settle_interventions(session_id, converted)

    async def intervention_events(self, limit: int = 100_000) -> list[dict]:
        if self._pool is None:
            return self._mem.interventions_all()
        try:
            async with self._pool.acquire() as con:
                rows = await con.fetch(
                    "SELECT * FROM intervention_events ORDER BY created_at DESC "
                    "LIMIT $1", limit)
            return [dict(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log(f"intervention_events read failed ({exc!r})")
            return self._mem.interventions_all()

    async def fatigued_interventions(self, session_id: str,
                                     segment_key: str | None = None) -> set[str]:
        """Intervention ids that this 'customer' (best proxy in the demo: the
        session's segment) has been shown 3+ times WITHOUT converting - the
        assembler then rotates to the next intervention in the slot."""
        THRESH = 3
        if self._pool is not None:
            try:
                async with self._pool.acquire() as con:
                    rows = await con.fetch(
                        """
                        SELECT intervention_id, count(*) AS n
                        FROM intervention_events
                        WHERE converted IS DISTINCT FROM true
                          AND ($1::text IS NOT NULL AND segment_key = $1
                               OR session_id = $2)
                        GROUP BY intervention_id
                        HAVING count(*) >= $3
                        """,
                        segment_key, session_id, THRESH,
                    )
                return {r["intervention_id"] for r in rows}
            except Exception as exc:  # noqa: BLE001
                log(f"fatigued_interventions query failed ({exc!r})")
                return set()

        evs = self._mem.interventions_all()
        if not evs:
            return set()
        key = segment_key
        if key is None:
            for e in evs:
                if e.get("session_id") == session_id and e.get("segment_key"):
                    key = e["segment_key"]
                    break
        counts: dict[str, int] = {}
        for e in evs:
            if e.get("converted") is True:
                continue
            if (key and e.get("segment_key") == key) or e.get("session_id") == session_id:
                iid = e.get("intervention_id")
                if iid:
                    counts[iid] = counts.get(iid, 0) + 1
        return {iid for iid, c in counts.items() if c >= THRESH}

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
