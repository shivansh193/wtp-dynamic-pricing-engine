"""
Step 2 - IPinfo.io free ASN database.

IPinfo publishes a free ASN dump (CSV) at https://ipinfo.io/data - it needs a
free account + token. Set IPINFO_TOKEN in .env to enable the live download.

Output: data/raw/ipinfo_asn.csv
Columns: asn, name, domain, type, country  (+ our derived `ip_class`)

Fallback: a curated table of the ASNs that actually matter for an Indian
ecommerce checkout - major consumer ISPs (Jio, Airtel, BSNL, VIL, ACT), the
big hosting providers, and a few commercial VPN ASNs - each tagged with an
`ip_class` the enrichment module maps to a trust multiplier.
"""

from __future__ import annotations

import os

import config as C
from _util import http_get, log, require_pandas, write_source_sidecar

OUT = C.RAW_DIR / "ipinfo_asn.csv"

IPINFO_ASN_URL = "https://ipinfo.io/data/free/asn.csv.gz?token={token}"

# Curated fallback - `ip_class` in {isp, mobile, hosting, vpn, education, business}
FALLBACK_ASNS = [
    # asn,   name,                                 domain,             type,       country, ip_class
    ("AS55836", "Reliance Jio Infocomm Limited",    "jio.com",          "isp",      "IN", "mobile"),
    ("AS45609", "Bharti Airtel Ltd. (Mobile)",      "airtel.in",        "isp",      "IN", "mobile"),
    ("AS24560", "Bharti Airtel Ltd. (Broadband)",   "airtel.in",        "isp",      "IN", "isp"),
    ("AS9829",  "BSNL National Internet Backbone",  "bsnl.co.in",       "isp",      "IN", "isp"),
    ("AS55410", "Vodafone Idea Ltd",                "myvi.in",          "isp",      "IN", "mobile"),
    ("AS17488", "Hathway Cable & Datacom",          "hathway.com",      "isp",      "IN", "isp"),
    ("AS18101", "Reliance Communications",          "rcom.co.in",       "isp",      "IN", "isp"),
    ("AS133982","Atria Convergence Technologies (ACT)","actcorp.in",    "isp",      "IN", "isp"),
    ("AS45820", "Tata Teleservices",                "tatatel.co.in",    "isp",      "IN", "isp"),
    ("AS4755",  "Tata Communications (VSNL)",       "tatacommunications.com","isp",  "IN", "business"),
    # education
    ("AS55824", "National Knowledge Network (NKN)", "nkn.in",           "education","IN", "education"),
    ("AS132215","Indian Institute of Technology Bombay","iitb.ac.in",   "education","IN", "education"),
    ("AS141133","Indian Institute of Technology Madras","iitm.ac.in",   "education","IN", "education"),
    ("AS10029", "ERNET India",                      "ernet.in",         "education","IN", "education"),
    # hosting / datacenter
    ("AS16509", "Amazon AWS",                       "aws.amazon.com",   "hosting",  "US", "hosting"),
    ("AS15169", "Google LLC",                       "google.com",       "hosting",  "US", "hosting"),
    ("AS8075",  "Microsoft Azure",                  "azure.com",        "hosting",  "US", "hosting"),
    ("AS14061", "DigitalOcean LLC",                 "digitalocean.com", "hosting",  "US", "hosting"),
    ("AS16276", "OVH SAS",                          "ovh.com",          "hosting",  "FR", "hosting"),
    ("AS24940", "Hetzner Online GmbH",              "hetzner.com",      "hosting",  "DE", "hosting"),
    ("AS63949", "Akamai (Linode)",                  "linode.com",       "hosting",  "US", "hosting"),
    ("AS16625", "Akamai Technologies",              "akamai.com",       "hosting",  "US", "hosting"),
    ("AS13335", "Cloudflare, Inc.",                 "cloudflare.com",   "hosting",  "US", "hosting"),
    # commercial VPN
    ("AS9009",  "M247 Europe SRL (VPN carrier)",    "m247.com",         "hosting",  "GB", "vpn"),
    ("AS212238","Datacamp Limited (CDN77/VPN)",     "datacamp.co.uk",   "hosting",  "GB", "vpn"),
    ("AS60068", "Datacamp / CDN77",                 "cdn77.com",        "hosting",  "GB", "vpn"),
    ("AS131199","Nord Security (NordVPN)",          "nordvpn.com",      "hosting",  "PA", "vpn"),
    ("AS208046","Mullvad VPN AB",                   "mullvad.net",      "hosting",  "SE", "vpn"),
]


def _try_live():
    pd = require_pandas()
    token = os.getenv("IPINFO_TOKEN", "").strip()
    if not token:
        log("  IPINFO_TOKEN not set -> using curated fallback ASN table")
        return None
    resp = http_get(IPINFO_ASN_URL.format(token=token), timeout=60)
    if resp is None:
        log("  IPinfo download failed -> using curated fallback ASN table")
        return None
    try:
        import gzip
        import io as _io

        raw = gzip.decompress(resp.content)
        df = pd.read_csv(_io.BytesIO(raw))
        df["ip_class"] = df.get("type", "isp").map(
            {"isp": "isp", "hosting": "hosting", "business": "business",
             "education": "education"}
        ).fillna("isp")
        return df
    except Exception as exc:  # noqa: BLE001
        log(f"  IPinfo parse failed: {exc!r} -> using curated fallback")
        return None


def main() -> None:
    pd = require_pandas()
    log("Fetching IPinfo.io ASN database...")
    df = _try_live()
    live = df is not None
    if not live:
        df = pd.DataFrame(
            FALLBACK_ASNS,
            columns=["asn", "name", "domain", "type", "country", "ip_class"],
        )

    df.to_csv(OUT, index=False)
    log(f"  wrote {OUT}  ({len(df)} ASNs)")
    write_source_sidecar(
        OUT,
        source="IPinfo.io free ASN dump (ipinfo.io/data)" if live
        else "Curated fallback: major Indian ISPs + hosting + VPN ASNs",
        live=live,
        note="ip_class in {isp, mobile, hosting, vpn, education, business}",
    )


if __name__ == "__main__":
    main()
