"""Configuration for the IP enrichment module."""

from __future__ import annotations

import os
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parent
DATA_RAW = REPO_ROOT / "data" / "raw"
FIREHOL_DIR = DATA_RAW / "firehol"
GEOIP_DIR = DATA_RAW / "geoip"
ASN_CSV = DATA_RAW / "ipinfo_asn.csv"

GEOIP_CITY_DB = Path(os.getenv("GEOIP_CITY_DB", GEOIP_DIR / "GeoLite2-City.mmdb"))
GEOIP_ASN_DB = Path(os.getenv("GEOIP_ASN_DB", GEOIP_DIR / "GeoLite2-ASN.mmdb"))

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL_SECONDS = int(os.getenv("IP_CACHE_TTL_SECONDS", "86400"))  # 24h
CACHE_KEY_PREFIX = "ipenrich:v1:"

# ------------------------------------------------------------------ #
# ip_type -> ip_trust_multiplier  (verbatim from the brief, Step 2.5)
# ------------------------------------------------------------------ #
TRUST_MULTIPLIER = {
    "residential": 1.00,
    "mobile_carrier": 0.95,
    "unknown": 0.80,
    "public_wifi": 0.70,
    "vpn": 0.60,
    "datacenter": 0.50,
    "tor": 0.30,
}
DEFAULT_IP_TYPE = "unknown"
DEFAULT_MULTIPLIER = TRUST_MULTIPLIER[DEFAULT_IP_TYPE]

# FireHOL list file -> the ip_type it implies
FIREHOL_TYPE_MAP = {
    "tor_exits.ipset": "tor",
    "vpn.netset": "vpn",
    "datacenters.netset": "datacenter",
    "firehol_level1.netset": "datacenter",  # bogon/hijacked - treat as low trust
}

# ASN `ip_class` (from ipinfo_asn.csv) -> ip_type
ASN_CLASS_TO_TYPE = {
    "mobile": "mobile_carrier",
    "isp": "residential",
    "business": "residential",
    "education": "public_wifi",   # university networks = shared, medium trust
    "hosting": "datacenter",
    "vpn": "vpn",
}
