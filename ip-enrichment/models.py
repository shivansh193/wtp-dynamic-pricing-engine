"""Pydantic schemas for the enrichment API."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

IpType = Literal[
    "residential", "mobile_carrier", "datacenter", "vpn",
    "public_wifi", "tor", "unknown",
]


class EnrichRequest(BaseModel):
    ip: str = Field(..., examples=["49.36.128.5"], description="IPv4 or IPv6 address")


class EnrichmentResult(BaseModel):
    ip: str
    ip_type: IpType = "unknown"
    ip_trust_multiplier: float = Field(0.8, ge=0.0, le=1.0)
    location_confidence: float = Field(
        0.0, ge=0.0, le=1.0,
        description="How much we trust the geolocation (1.0 = residential ISP in "
                    "expected country; low for VPN/DC/Tor/unknown)",
    )

    # ---- provenance / signals that produced the classification ----
    asn: Optional[str] = None
    asn_org: Optional[str] = None
    isp: Optional[str] = None
    connection_type: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None

    is_whitelisted: bool = False
    whitelist_reason: Optional[str] = None
    blocklist_hits: list[str] = Field(default_factory=list)

    geo_source: Literal["maxmind", "synthetic", "none"] = "none"
    cache_hit: bool = False
    fallback_used: bool = False
    lookup_ms: float = 0.0

    def as_signal(self) -> dict:
        """Compact form the pricing pipeline consumes."""
        return {
            "ip_type": self.ip_type,
            "ip_trust_multiplier": round(self.ip_trust_multiplier, 4),
            "location_confidence": round(self.location_confidence, 4),
            "is_whitelisted": self.is_whitelisted,
            "blocklist_hits": self.blocklist_hits,
        }
