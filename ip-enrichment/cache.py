"""
Lookup cache with a 24h TTL.

Primary: Redis (async). Fallback: a bounded in-process dict with per-entry
expiry, used when Redis is unreachable so the module still works standalone
and in tests. Cache key = sha1(ip) under a versioned prefix.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Optional

from . import config as C
from ._util import log

try:
    import redis.asyncio as aioredis  # redis>=4.2 ships asyncio client
except Exception:  # noqa: BLE001
    aioredis = None  # type: ignore


def _key(ip: str) -> str:
    return C.CACHE_KEY_PREFIX + hashlib.sha1(ip.encode()).hexdigest()


class _LocalTTLCache:
    """Minimal LRU-ish dict with expiry. Not thread-safe; fine for asyncio."""

    def __init__(self, maxsize: int = 50_000):
        self.maxsize = maxsize
        self._d: dict[str, tuple[float, str]] = {}

    def get(self, k: str) -> Optional[str]:
        v = self._d.get(k)
        if not v:
            return None
        exp, payload = v
        if exp < time.time():
            self._d.pop(k, None)
            return None
        return payload

    def set(self, k: str, payload: str, ttl: int) -> None:
        if len(self._d) >= self.maxsize:
            # drop ~10% oldest by expiry
            for dead in sorted(self._d, key=lambda x: self._d[x][0])[: self.maxsize // 10]:
                self._d.pop(dead, None)
        self._d[k] = (time.time() + ttl, payload)


class EnrichmentCache:
    def __init__(self) -> None:
        self._redis = None
        self._local = _LocalTTLCache()
        self._redis_ok = False

    async def connect(self) -> None:
        if aioredis is None:
            log("redis client not installed - using in-process cache")
            return
        try:
            self._redis = aioredis.from_url(
                C.REDIS_URL, encoding="utf-8", decode_responses=True,
                socket_connect_timeout=0.5, socket_timeout=0.5,
            )
            await self._redis.ping()
            self._redis_ok = True
            log(f"redis cache connected: {C.REDIS_URL}")
        except Exception as exc:  # noqa: BLE001
            log(f"redis unavailable ({exc!r}) - using in-process cache")
            self._redis = None
            self._redis_ok = False

    async def get(self, ip: str) -> Optional[dict]:
        k = _key(ip)
        if self._redis_ok and self._redis is not None:
            try:
                raw = await self._redis.get(k)
                if raw:
                    return json.loads(raw)
            except Exception:  # noqa: BLE001
                self._redis_ok = False  # degrade for the rest of the process
        raw = self._local.get(k)
        return json.loads(raw) if raw else None

    async def set(self, ip: str, value: dict) -> None:
        k = _key(ip)
        payload = json.dumps(value, separators=(",", ":"))
        if self._redis_ok and self._redis is not None:
            try:
                await self._redis.set(k, payload, ex=C.CACHE_TTL_SECONDS)
            except Exception:  # noqa: BLE001
                self._redis_ok = False
        self._local.set(k, payload, C.CACHE_TTL_SECONDS)

    async def close(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:  # noqa: BLE001
                pass

    @property
    def backend(self) -> str:
        return "redis" if self._redis_ok else "in-process"
