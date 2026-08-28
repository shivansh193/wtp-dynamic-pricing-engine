"""
ASN / ISP / geo resolution.

Priority:
  1. MaxMind GeoLite2 (City + ASN .mmdb) if the files exist  -> geo_source="maxmind"
  2. Synthetic ASN table (data/raw/ipinfo_asn.csv) keyed by a deterministic
     hash of the IP's /16, so the same IP always resolves the same way
     -> geo_source="synthetic"
  3. Nothing resolvable -> geo_source="none"

The synthetic path is what runs in the Buildathon demo when no MaxMind key is
configured. It is clearly labelled as synthetic in every response.
"""

from __future__ import annotations

import csv
import ipaddress
import zlib
from dataclasses import dataclass
from pathlib import Path

from . import config as C
from ._util import log

try:
    import geoip2.database  # type: ignore

    _HAVE_GEOIP2 = True
except ImportError:
    _HAVE_GEOIP2 = False


@dataclass
class AsnInfo:
    asn: str | None = None
    org: str | None = None
    isp: str | None = None
    ip_class: str | None = None       # isp / mobile / hosting / vpn / education / business
    country: str | None = None
    city: str | None = None
    connection_type: str | None = None  # from GeoLite2 City "traits" when available
    source: str = "none"              # maxmind / synthetic / none


class AsnResolver:
    def __init__(self) -> None:
        self._city_reader = None
        self._asn_reader = None
        self._synth_rows: list[dict] = []
        self._load()

    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        if _HAVE_GEOIP2 and C.GEOIP_ASN_DB.exists():
            try:
                self._asn_reader = geoip2.database.Reader(str(C.GEOIP_ASN_DB))
                log(f"MaxMind ASN DB loaded: {C.GEOIP_ASN_DB.name}")
            except Exception as exc:  # noqa: BLE001
                log(f"MaxMind ASN DB failed to open: {exc!r}")
        if _HAVE_GEOIP2 and C.GEOIP_CITY_DB.exists():
            try:
                self._city_reader = geoip2.database.Reader(str(C.GEOIP_CITY_DB))
                log(f"MaxMind City DB loaded: {C.GEOIP_CITY_DB.name}")
            except Exception as exc:  # noqa: BLE001
                log(f"MaxMind City DB failed to open: {exc!r}")

        if self._asn_reader is None:
            self._load_synth()

    def _load_synth(self) -> None:
        path: Path = C.ASN_CSV
        if not path.exists():
            log(f"synthetic ASN table missing at {path}; ASN resolution disabled")
            return
        with path.open(newline="", encoding="utf-8") as fh:
            self._synth_rows = list(csv.DictReader(fh))
        log(f"synthetic ASN table loaded: {len(self._synth_rows)} ASNs "
            f"(no MaxMind key -> MOCK GEO MODE)")

    @property
    def mock_geo_mode(self) -> bool:
        return self._asn_reader is None

    # ------------------------------------------------------------------ #
    def resolve(self, ip: str) -> AsnInfo:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return AsnInfo(source="none")

        if self._asn_reader is not None:
            return self._resolve_maxmind(ip, addr)
        if self._synth_rows:
            return self._resolve_synth(ip, addr)
        return AsnInfo(source="none")

    def _resolve_maxmind(self, ip: str, addr) -> AsnInfo:
        info = AsnInfo(source="maxmind")
        try:
            a = self._asn_reader.asn(ip)  # type: ignore[union-attr]
            info.asn = f"AS{a.autonomous_system_number}"
            info.org = a.autonomous_system_organization
            info.isp = a.autonomous_system_organization
        except Exception:  # noqa: BLE001 - address not in DB
            pass
        if self._city_reader is not None:
            try:
                c = self._city_reader.city(ip)
                info.country = c.country.iso_code
                info.city = c.city.name
                info.connection_type = getattr(c.traits, "connection_type", None)
            except Exception:  # noqa: BLE001
                pass
        info.ip_class = _class_from_org(info.org)
        return info

    def _resolve_synth(self, ip: str, addr) -> AsnInfo:
        # 1. well-known ranges get a correct answer even in mock mode (demo-friendly)
        known = _match_known_range(addr)
        if known is not None:
            org, ip_class, country = known
            return AsnInfo(asn=None, org=org, isp=org, ip_class=ip_class,
                           country=country, source="synthetic")

        # 2. otherwise deterministic pick: hash the /16 so an IP always maps to
        #    one ASN row (stable, repeatable classification)
        if addr.version == 4:
            key = ".".join(ip.split(".")[:2])
        else:
            key = ip.split(":")[0]
        idx = zlib.adler32(key.encode()) % len(self._synth_rows)
        row = self._synth_rows[idx]
        return AsnInfo(
            asn=row.get("asn"),
            org=row.get("name"),
            isp=row.get("name"),
            ip_class=row.get("ip_class") or _class_from_org(row.get("name")),
            country=row.get("country") or ("IN" if _looks_indian(addr) else None),
            city=None,
            connection_type=None,
            source="synthetic",
        )

    def close(self) -> None:
        for r in (self._city_reader, self._asn_reader):
            try:
                if r is not None:
                    r.close()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------- #
_HOSTING_HINTS = ("amazon", "aws", "google", "microsoft", "azure", "digitalocean",
                  "ovh", "hetzner", "linode", "cloudflare", "akamai", "vultr",
                  "contabo", "leaseweb", "choopa")
_VPN_HINTS = ("nordvpn", "mullvad", "expressvpn", "surfshark", "m247", "datacamp",
              "cdn77", "private internet access", "protonvpn")
_MOBILE_HINTS = ("jio", "airtel", "vodafone", "idea", "cellular", "mobile", "gprs")
_EDU_HINTS = ("iit", "nit", "university", "institute", "ernet", "nkn", "academ", "ac.in")


def _class_from_org(org: str | None) -> str | None:
    if not org:
        return None
    o = org.lower()
    if any(h in o for h in _VPN_HINTS):
        return "vpn"
    if any(h in o for h in _HOSTING_HINTS):
        return "hosting"
    if any(h in o for h in _EDU_HINTS):
        return "education"
    if any(h in o for h in _MOBILE_HINTS):
        return "mobile"
    return "isp"


# Well-known public ranges - so the mock-geo demo still classifies the
# "famous" IPs correctly (Google DNS, Cloudflare, common clouds/VPNs).
# (label, ip_class, country)
_KNOWN_RANGES: list[tuple[str, str, str, str]] = [
    ("8.8.8.0/24", "Google Public DNS", "hosting", "US"),
    ("8.8.4.0/24", "Google Public DNS", "hosting", "US"),
    ("1.1.1.0/24", "Cloudflare DNS", "hosting", "US"),
    ("1.0.0.0/24", "Cloudflare DNS", "hosting", "US"),
    ("13.32.0.0/15", "Amazon CloudFront", "hosting", "US"),
    ("13.224.0.0/14", "Amazon AWS", "hosting", "US"),
    ("13.232.0.0/14", "Amazon AWS ap-south-1 (Mumbai)", "hosting", "IN"),
    ("15.206.0.0/15", "Amazon AWS ap-south-1 (Mumbai)", "hosting", "IN"),
    ("3.6.0.0/15", "Amazon AWS ap-south-1 (Mumbai)", "hosting", "IN"),
    ("34.64.0.0/10", "Google Cloud", "hosting", "US"),
    ("35.192.0.0/12", "Google Cloud", "hosting", "US"),
    ("20.0.0.0/8", "Microsoft Azure", "hosting", "US"),
    ("40.64.0.0/10", "Microsoft Azure", "hosting", "US"),
    ("104.16.0.0/12", "Cloudflare", "hosting", "US"),
    ("146.70.0.0/15", "M247 / commercial VPN egress", "vpn", "GB"),
    ("143.244.32.0/19", "DataCamp / commercial VPN", "vpn", "GB"),
    ("45.83.88.0/22", "commercial VPN block", "vpn", "NL"),
    ("185.220.100.0/22", "Tor relay range", "vpn", "DE"),
    # a couple of real Indian consumer ISP ranges for the "good customer" demo
    ("49.36.0.0/14", "Reliance Jio", "mobile", "IN"),
    ("49.44.0.0/14", "Reliance Jio", "mobile", "IN"),
    ("117.192.0.0/10", "BSNL", "isp", "IN"),
    ("122.160.0.0/12", "Bharti Airtel", "isp", "IN"),
    ("103.21.124.0/22", "IIT Bombay", "education", "IN"),
]

_KNOWN_PARSED = []
for _cidr, _org, _cls, _cc in _KNOWN_RANGES:
    try:
        _KNOWN_PARSED.append((ipaddress.ip_network(_cidr), _org, _cls, _cc))
    except ValueError:
        pass


def _match_known_range(addr):
    for net, org, cls, cc in _KNOWN_PARSED:
        if addr.version == net.version and addr in net:
            return org, cls, cc
    return None


def _looks_indian(addr) -> bool:
    """Very rough: several APNIC blocks heavily used by Indian ISPs."""
    if addr.version != 4:
        return False
    first = int(str(addr).split(".")[0])
    return first in {1, 14, 27, 43, 49, 59, 103, 106, 110, 111, 112, 113,
                     114, 115, 116, 117, 118, 119, 120, 122, 123, 125, 157,
                     171, 175, 180, 182, 183, 202, 203, 210, 218, 219, 220, 223}
