"""
IP Enrichment module (Buildathon Step 2.5).

Turns a raw IP address into a trust signal for the pricing engine:
  ip_type, ip_trust_multiplier, location_confidence, whitelist/blacklist status.

Fully self-contained: FireHOL blocklists load into memory on startup, MaxMind
GeoLite2 is used when present (else a synthetic ASN table), and every lookup is
cached (Redis, with an in-process LRU fallback) for 24h to protect the 200ms
end-to-end latency budget.
"""

from .service import EnrichmentService, get_service  # noqa: F401
from .models import EnrichmentResult  # noqa: F401

__all__ = ["EnrichmentService", "get_service", "EnrichmentResult"]
