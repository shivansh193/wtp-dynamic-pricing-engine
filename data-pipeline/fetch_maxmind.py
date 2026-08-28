"""
Step 2 - MaxMind GeoLite2 City + ASN databases.

REQUIRES A FREE MAXMIND ACCOUNT.
  1. Sign up: https://www.maxmind.com/en/geolite2/signup
  2. Account -> "Manage License Keys" -> create a key
  3. Put it in .env as MAXMIND_LICENSE_KEY=...

This script downloads:
  - GeoLite2-City.mmdb  -> data/raw/geoip/
  - GeoLite2-ASN.mmdb   -> data/raw/geoip/

If MAXMIND_LICENSE_KEY is not set (or the download fails), NOTHING is written
here - the IP-enrichment module has its own built-in synthetic ASN table and
will run in "mock geo" mode. That is logged loudly at API startup.
"""

from __future__ import annotations

import io
import os
import tarfile

import config as C
from _util import http_get, log, write_source_sidecar

EDITIONS = {
    "GeoLite2-City": C.GEOIP_DIR / "GeoLite2-City.mmdb",
    "GeoLite2-ASN": C.GEOIP_DIR / "GeoLite2-ASN.mmdb",
}


def main() -> None:
    key = os.getenv("MAXMIND_LICENSE_KEY", "").strip()
    log("Fetching MaxMind GeoLite2 databases...")
    if not key:
        log("  MAXMIND_LICENSE_KEY not set -> SKIPPING.")
        log("  The IP-enrichment module will use its built-in synthetic ASN table.")
        log("  To enable real geo lookup: https://www.maxmind.com/en/geolite2/signup")
        (C.GEOIP_DIR / "MAXMIND_NOT_CONFIGURED.txt").write_text(
            "MAXMIND_LICENSE_KEY was not set when the pipeline ran.\n"
            "Set it in .env and re-run `python data-pipeline/fetch_maxmind.py`.\n"
        )
        return

    ok = []
    for edition, target in EDITIONS.items():
        url = C.MAXMIND_PERMALINK.format(edition=edition, key=key)
        resp = http_get(url, timeout=60)
        if resp is None:
            log(f"  {edition}: download failed")
            continue
        try:
            with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tf:
                member = next(m for m in tf.getmembers() if m.name.endswith(".mmdb"))
                extracted = tf.extractfile(member)
                assert extracted is not None
                target.write_bytes(extracted.read())
            log(f"  {edition}: wrote {target} ({target.stat().st_size/1e6:.1f} MB)")
            ok.append(edition)
        except Exception as exc:  # noqa: BLE001
            log(f"  {edition}: extract failed: {exc!r}")

    if ok:
        marker = C.GEOIP_DIR / "maxmind.csv"
        marker.write_text("edition,status\n" + "\n".join(f"{e},ok" for e in ok) + "\n")
        write_source_sidecar(
            marker,
            source="MaxMind GeoLite2 (download.maxmind.com, licensed free tier)",
            live=True,
            note=f"editions: {', '.join(ok)}",
        )


if __name__ == "__main__":
    main()
