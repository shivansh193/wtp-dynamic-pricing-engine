"""
Quick command-line check:

    python -m ip_enrichment.cli 49.36.128.5 13.234.1.1 185.220.101.1

Prints the full enrichment result for each IP. Handy for demos and for
sanity-checking the blocklist / whitelist / ASN wiring without the API.
"""

from __future__ import annotations

import asyncio
import json
import sys

from .service import get_service

SAMPLES = [
    "49.36.128.5",     # Jio broadband range (whitelisted -> residential)
    "13.234.20.10",    # AWS ap-south-1 (datacenter)
    "185.220.101.1",   # known Tor exit
    "146.70.0.5",      # commercial VPN block
    "14.139.45.9",     # NKN / university (public_wifi)
    "203.0.113.7",     # TEST-NET-3 (non-routable -> unknown)
]


async def _run(ips: list[str]) -> None:
    svc = get_service()
    await svc.startup()
    for ip in ips:
        res = await svc.enrich(ip)
        print(json.dumps(res.model_dump(), indent=2))
        print("-" * 60)
    await svc.shutdown()


def main() -> None:
    ips = sys.argv[1:] or SAMPLES
    asyncio.run(_run(ips))


if __name__ == "__main__":
    main()
