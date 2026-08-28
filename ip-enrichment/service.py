"""
EnrichmentService - the object the API mounts.

Lifecycle:
  await service.startup()   # load blocklists + ASN DB + connect Redis
  result = await service.enrich("49.36.128.5")
  await service.shutdown()

enrich() path:
  cache hit  -> return (~1ms)
  cache miss -> blocklist match (O(log n)) + whitelist + ASN resolve
             -> classify -> cache write (24h TTL) -> return

Every branch returns a valid EnrichmentResult; failures degrade to
ip_type="unknown", multiplier=0.8, fallback_used=True.
"""

from __future__ import annotations

import time

from .asn_lookup import AsnResolver
from .blocklists import BlocklistMatcher
from .cache import EnrichmentCache
from .classifier import classify
from .models import EnrichmentResult
from .whitelist import Whitelist
from ._util import log


class EnrichmentService:
    def __init__(self) -> None:
        self._blocklists: BlocklistMatcher | None = None
        self._whitelist: Whitelist | None = None
        self._asn: AsnResolver | None = None
        self._cache = EnrichmentCache()
        self._ready = False

    # ------------------------------------------------------------------ #
    async def startup(self) -> None:
        t0 = time.perf_counter()
        self._blocklists = BlocklistMatcher.load()
        self._whitelist = Whitelist()
        self._asn = AsnResolver()
        await self._cache.connect()
        self._ready = True
        log(f"service ready in {(time.perf_counter()-t0)*1000:.0f}ms "
            f"(geo={'MOCK' if self._asn.mock_geo_mode else 'maxmind'}, "
            f"cache={self._cache.backend})")

    async def shutdown(self) -> None:
        if self._asn:
            self._asn.close()
        await self._cache.close()
        self._ready = False

    # ------------------------------------------------------------------ #
    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def mock_geo_mode(self) -> bool:
        return bool(self._asn and self._asn.mock_geo_mode)

    @property
    def cache_backend(self) -> str:
        return self._cache.backend

    # ------------------------------------------------------------------ #
    async def enrich(self, ip: str) -> EnrichmentResult:
        t0 = time.perf_counter()
        ip = (ip or "").strip()

        # ---- cache ----
        try:
            cached = await self._cache.get(ip)
        except Exception:  # noqa: BLE001
            cached = None
        if cached:
            res = EnrichmentResult(**cached)
            res.cache_hit = True
            res.lookup_ms = round((time.perf_counter() - t0) * 1000, 3)
            return res

        # ---- compute ----
        try:
            block_hits = self._blocklists.hits(ip) if self._blocklists else []
            implied = self._blocklists.implied_type(block_hits) if self._blocklists else None
            wl = self._whitelist.match(ip) if self._whitelist else None
            asn = self._asn.resolve(ip) if self._asn else None
            if asn is None:
                from .asn_lookup import AsnInfo

                asn = AsnInfo(source="none")
            res = classify(
                ip,
                blocklist_hits=block_hits,
                implied_block_type=implied,
                whitelist_hit=wl,
                asn=asn,
            )
        except Exception as exc:  # noqa: BLE001 - never fail the caller
            log(f"enrich({ip!r}) hard-failed: {exc!r} -> default unknown")
            res = EnrichmentResult(
                ip=ip, ip_type="unknown", ip_trust_multiplier=0.8,
                location_confidence=0.1, fallback_used=True,
            )

        res.cache_hit = False
        res.lookup_ms = round((time.perf_counter() - t0) * 1000, 3)

        # ---- cache write (best effort) ----
        try:
            payload = res.model_dump()
            payload.pop("cache_hit", None)
            payload.pop("lookup_ms", None)
            await self._cache.set(ip, payload)
        except Exception:  # noqa: BLE001
            pass

        return res


# module-level singleton so the API and the CLI share one warm instance
_service: EnrichmentService | None = None


def get_service() -> EnrichmentService:
    global _service
    if _service is None:
        _service = EnrichmentService()
    return _service
