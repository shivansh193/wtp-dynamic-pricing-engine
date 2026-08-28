"""
Session store for the link-generator demo flow.

Shares the Postgres pool owned by `api.db.db`; falls back to an in-process dict
when Postgres isn't available (same graceful-degradation contract as the
decision log).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .db import db
from .logging_util import log


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_session_id() -> str:
    return "sess_" + uuid.uuid4().hex[:20]


def new_merchant_id() -> str:
    return "merch_" + uuid.uuid4().hex[:12]


class _MemSessions:
    def __init__(self) -> None:
        self._d: dict[str, dict] = {}

    def put(self, row: dict) -> None:
        self._d[row["session_id"]] = row

    def get(self, sid: str) -> Optional[dict]:
        return self._d.get(sid)

    def all(self, limit: int = 500) -> list[dict]:
        return sorted(self._d.values(), key=lambda r: r["created_at"], reverse=True)[:limit]


class SessionStore:
    def __init__(self) -> None:
        self._mem = _MemSessions()

    @property
    def _pool(self):
        return getattr(db, "_pool", None)

    @property
    def backend(self) -> str:
        return "postgres" if self._pool is not None else "memory"

    # ------------------------------------------------------------------ #
    async def create(self, *, preset: str, config: dict, segment_key: str,
                     merchant_id: str | None = None) -> dict:
        sid = new_session_id()
        mid = merchant_id or new_merchant_id()
        row = {
            "session_id": sid,
            "merchant_id": mid,
            "preset": preset,
            "config": config,
            "status": "pending",
            "created_at": _now(),
            "priced_at": None,
            "completed_at": None,
            "list_price": float(config.get("list_price", 4999)),
            "price_shown": None,
            "wtp_score": None,
            "offer_type": None,
            "segment_key": segment_key,
            "result": None,
        }
        if self._pool is None:
            self._mem.put(row)
            return row
        async with self._pool.acquire() as con:
            await con.execute(
                """INSERT INTO sessions
                   (session_id, merchant_id, preset, config, status, created_at,
                    list_price, segment_key)
                   VALUES ($1,$2,$3,$4::jsonb,'pending',$5,$6,$7)""",
                sid, mid, preset, json.dumps(config), row["created_at"],
                row["list_price"], segment_key,
            )
        return row

    async def get(self, sid: str) -> Optional[dict]:
        if self._pool is None:
            return self._mem.get(sid)
        async with self._pool.acquire() as con:
            r = await con.fetchrow("SELECT * FROM sessions WHERE session_id=$1", sid)
        return _normalise(r) if r else None

    async def all(self, limit: int = 500) -> list[dict]:
        if self._pool is None:
            return self._mem.all(limit)
        async with self._pool.acquire() as con:
            rows = await con.fetch(
                "SELECT * FROM sessions ORDER BY created_at DESC LIMIT $1", limit
            )
        return [_normalise(r) for r in rows]

    async def mark_priced(self, sid: str, *, wtp_score: float, price_shown: float,
                          offer_type: str, result: dict) -> Optional[dict]:
        ts = _now()
        if self._pool is None:
            row = self._mem.get(sid)
            if not row:
                return None
            row.update(status="priced", priced_at=ts, wtp_score=wtp_score,
                       price_shown=price_shown, offer_type=offer_type, result=result)
            return row
        async with self._pool.acquire() as con:
            r = await con.fetchrow(
                """UPDATE sessions
                   SET status = CASE WHEN status='converted' THEN status ELSE 'priced' END,
                       priced_at = COALESCE(priced_at, $2),
                       wtp_score = $3, price_shown = $4, offer_type = $5,
                       result = $6::jsonb
                   WHERE session_id = $1
                   RETURNING *""",
                sid, ts, wtp_score, price_shown, offer_type, json.dumps(result, default=str),
            )
        return _normalise(r) if r else None

    async def set_status(self, sid: str, status: str) -> Optional[dict]:
        ts = _now()
        if self._pool is None:
            row = self._mem.get(sid)
            if not row:
                return None
            row["status"] = status
            if status == "converted":
                row["completed_at"] = ts
            return row
        async with self._pool.acquire() as con:
            r = await con.fetchrow(
                """UPDATE sessions SET status=$2,
                     completed_at = CASE WHEN $2 IN ('converted','abandoned')
                                         THEN $3 ELSE completed_at END
                   WHERE session_id=$1 RETURNING *""",
                sid, status, ts,
            )
        return _normalise(r) if r else None


def _normalise(r) -> dict:
    d = dict(r)
    for k in ("config", "result"):
        v = d.get(k)
        if isinstance(v, str):
            try:
                d[k] = json.loads(v)
            except (ValueError, TypeError):
                pass
    for k in ("created_at", "priced_at", "completed_at"):
        v = d.get(k)
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    for k in ("list_price", "price_shown", "wtp_score"):
        v = d.get(k)
        if v is not None and not isinstance(v, (int, float)):
            try:
                d[k] = float(v)
            except (ValueError, TypeError):
                d[k] = None
    return d


session_store = SessionStore()
