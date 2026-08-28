"""
Signal fusion: blocklists + whitelist + ASN class  ->  final classification.

Precedence (most trustworthy signal wins, most dangerous signal overrides):

  1. Tor exit node            -> tor            (0.30)   [overrides whitelist]
  2. Whitelisted Indian shared range -> forced type, trust floored
  3. VPN (blocklist or ASN)   -> vpn            (0.60)
  4. Datacenter/hosting       -> datacenter     (0.50)
  5. Mobile carrier ASN       -> mobile_carrier (0.95)
  6. Education/campus ASN      -> public_wifi    (0.70)
  7. Consumer ISP ASN         -> residential    (1.00)
  8. anything else / failure  -> unknown        (0.80)
"""

from __future__ import annotations

import ipaddress

from . import config as C
from .asn_lookup import AsnInfo
from .models import EnrichmentResult

_LOCATION_CONF_BASE = {
    "residential": 0.90,
    "mobile_carrier": 0.80,
    "public_wifi": 0.60,
    "datacenter": 0.30,
    "vpn": 0.20,
    "tor": 0.10,
    "unknown": 0.15,
}


def _is_special(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast


def classify(
    ip: str,
    *,
    blocklist_hits: list[str],
    implied_block_type: str | None,
    whitelist_hit,          # tuple(label, forced_type, min_mult) | None
    asn: AsnInfo,
) -> EnrichmentResult:
    res = EnrichmentResult(ip=ip)
    res.asn = asn.asn
    res.asn_org = asn.org
    res.isp = asn.isp
    res.country = asn.country
    res.city = asn.city
    res.connection_type = asn.connection_type
    res.blocklist_hits = blocklist_hits
    res.geo_source = asn.source  # "maxmind" | "synthetic" | "none"

    asn_type = C.ASN_CLASS_TO_TYPE.get(asn.ip_class or "", None)

    # ---- 0. unusable input ----
    if _is_special(ip) or not _valid(ip):
        res.ip_type = C.DEFAULT_IP_TYPE
        res.ip_trust_multiplier = C.DEFAULT_MULTIPLIER
        res.location_confidence = 0.10
        res.fallback_used = True
        res.whitelist_reason = "non-routable / invalid IP -> default unknown"
        return res

    # ---- 1. Tor: hardest signal, cannot be whitelisted away ----
    if implied_block_type == "tor" or "tor_exits.ipset" in blocklist_hits:
        res.ip_type = "tor"

    # ---- 2. whitelist (legit Indian shared range) ----
    elif whitelist_hit is not None:
        label, forced_type, min_mult = whitelist_hit
        res.is_whitelisted = True
        res.whitelist_reason = label
        res.ip_type = forced_type
        base_mult = C.TRUST_MULTIPLIER.get(forced_type, C.DEFAULT_MULTIPLIER)
        res.ip_trust_multiplier = max(base_mult, min_mult)
        res.location_confidence = max(0.85, _LOCATION_CONF_BASE.get(forced_type, 0.5))
        _apply_geo_penalty(res, asn)
        return res

    # ---- 3-7. blocklist / ASN driven ----
    elif implied_block_type == "vpn" or asn_type == "vpn":
        res.ip_type = "vpn"
    elif implied_block_type == "datacenter" or asn_type == "datacenter":
        res.ip_type = "datacenter"
    elif asn_type == "mobile_carrier":
        res.ip_type = "mobile_carrier"
    elif asn_type == "public_wifi":
        res.ip_type = "public_wifi"
    elif asn_type == "residential":
        res.ip_type = "residential"
    else:
        res.ip_type = C.DEFAULT_IP_TYPE
        res.fallback_used = asn.source == "none"

    res.ip_trust_multiplier = C.TRUST_MULTIPLIER.get(res.ip_type, C.DEFAULT_MULTIPLIER)
    res.location_confidence = _LOCATION_CONF_BASE.get(res.ip_type, 0.15)
    if asn.country == "IN":
        res.location_confidence = min(1.0, res.location_confidence + 0.10)
    _apply_geo_penalty(res, asn)
    return res


def _apply_geo_penalty(res: EnrichmentResult, asn: AsnInfo) -> None:
    """Synthetic / missing geo lowers how much we trust the *location*."""
    if asn.source == "synthetic":
        res.location_confidence = round(res.location_confidence * 0.70, 4)
    elif asn.source == "none":
        res.location_confidence = round(min(res.location_confidence, 0.20), 4)
    else:
        res.location_confidence = round(res.location_confidence, 4)


def _valid(ip: str) -> bool:
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False
