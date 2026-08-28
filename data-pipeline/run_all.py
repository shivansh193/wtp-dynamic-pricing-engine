"""
Step 2 + 3 orchestrator - run the whole data pipeline in order.

    python data-pipeline/run_all.py            # everything
    python data-pipeline/run_all.py --no-net   # skip network fetches, synth only
    python data-pipeline/run_all.py --rows 5000

Each stage is independent and idempotent; a failure in one network fetch does
not stop the pipeline because every fetch has a calibrated synthetic fallback.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import time

STAGES = [
    ("fetch_rbi", "RBI DBIE digital payments"),
    ("fetch_google_trends", "Google Trends categories"),
    ("build_pincode_income", "PIN code -> income tier"),
    ("build_festival_calendar", "Festival calendar"),
    ("fetch_firehol", "Firehol blocklists"),
    ("fetch_maxmind", "MaxMind GeoLite2 (needs key)"),
    ("fetch_ipinfo_asn", "IPinfo ASN database"),
    ("generate_synthetic", "Synthetic transactions (Step 3)"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-net", action="store_true", help="skip network fetches")
    ap.add_argument("--rows", type=int, default=None, help="override SYNTHETIC_ROWS")
    args = ap.parse_args()

    if args.rows:
        os.environ["SYNTHETIC_ROWS"] = str(args.rows)

    sys.path.insert(0, os.path.dirname(__file__))
    net_stages = {"fetch_rbi", "fetch_google_trends", "fetch_firehol",
                  "fetch_maxmind", "fetch_ipinfo_asn"}

    t0 = time.time()
    failed = []
    for mod_name, label in STAGES:
        if args.no_net and mod_name in net_stages:
            print(f"\n=== SKIP (--no-net): {label} ===")
            continue
        print(f"\n=== {label}  [{mod_name}] ===")
        try:
            mod = importlib.import_module(mod_name)
            importlib.reload(mod)
            mod.main()
        except Exception as exc:  # noqa: BLE001
            print(f"!!! stage {mod_name} failed: {exc!r}")
            failed.append(mod_name)

    dt = time.time() - t0
    print(f"\n=== pipeline done in {dt:.1f}s ===")
    if failed:
        print(f"stages with errors (fallbacks may have covered): {failed}")
    else:
        print("all stages OK")


if __name__ == "__main__":
    main()
