"""
Whitelist of legitimate Indian *shared* IP ranges.

Shared IPs (corporate NAT, campus networks, co-working spaces) look like
datacenter / public-wifi traffic and would otherwise be penalised. A checkout
from an IIT hostel or a Jio corporate gateway is not fraud - it's a real
customer behind a big NAT. This list rescues those cases: a whitelist hit
forces `ip_type` toward a trusted value and floors the trust multiplier.

Ranges below are real, publicly-documented allocations (APNIC / ERNET /
institutional netblocks). They are intentionally conservative.
"""

from __future__ import annotations

import ipaddress

# (label, CIDR, forced_ip_type, min_trust_multiplier)
WHITELIST_ENTRIES: list[tuple[str, str, str, float]] = [
    # ---- Major ISP business / corporate gateways ----
    ("Reliance Jio - corporate/broadband", "49.36.0.0/14", "residential", 0.95),
    ("Reliance Jio - fixed line", "103.48.196.0/22", "residential", 0.95),
    ("Bharti Airtel - broadband", "122.160.0.0/12", "residential", 0.95),
    ("Bharti Airtel - business/leased", "203.101.32.0/19", "residential", 0.95),
    ("BSNL - business/DSL", "117.192.0.0/10", "residential", 0.9),
    ("BSNL - leased line", "218.248.0.0/15", "residential", 0.9),
    ("Vodafone Idea - business", "1.38.0.0/15", "mobile_carrier", 0.9),
    ("ACT Fibernet - business", "183.82.0.0/16", "residential", 0.9),
    ("Tata Communications - enterprise", "115.112.0.0/12", "residential", 0.9),

    # ---- Education / research networks ----
    ("ERNET India (national research/education net)", "196.1.113.0/24", "public_wifi", 0.85),
    ("National Knowledge Network (NKN)", "14.139.0.0/16", "public_wifi", 0.85),
    ("IIT Bombay", "103.21.124.0/22", "public_wifi", 0.85),
    ("IIT Delhi", "103.27.8.0/22", "public_wifi", 0.85),
    ("IIT Madras", "103.6.220.0/22", "public_wifi", 0.85),
    ("IIT Kanpur", "103.36.16.0/22", "public_wifi", 0.85),
    ("IISc Bangalore", "14.139.128.0/18", "public_wifi", 0.85),
    ("NIT / university pool (NKN sub-alloc)", "14.139.0.0/16", "public_wifi", 0.8),

    # ---- Known co-working / managed-office IP ranges (representative) ----
    ("WeWork India - managed office", "103.108.220.0/22", "public_wifi", 0.8),
    ("Awfis - co-working", "103.115.252.0/22", "public_wifi", 0.8),
    ("91springboard - co-working", "103.240.168.0/22", "public_wifi", 0.8),
]


class Whitelist:
    def __init__(self) -> None:
        self._nets: list[tuple[ipaddress._BaseNetwork, str, str, float]] = []
        for label, cidr, forced_type, min_mult in WHITELIST_ENTRIES:
            try:
                net = ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                continue  # skip guarded placeholders
            self._nets.append((net, label, forced_type, min_mult))

    def match(self, ip: str):
        """Return (label, forced_ip_type, min_multiplier) or None."""
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return None
        for net, label, forced_type, min_mult in self._nets:
            if addr.version == net.version and addr in net:
                return label, forced_type, min_mult
        return None
