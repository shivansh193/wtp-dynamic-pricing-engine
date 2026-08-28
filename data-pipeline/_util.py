"""Small shared helpers for the fetch/build scripts."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # requests is optional for the pure-synthetic path
    requests = None  # type: ignore


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def write_source_sidecar(target: Path, *, source: str, live: bool, note: str = "") -> None:
    """Record provenance next to every dataset we write.

    `source`  - human label of where the data came from
    `live`    - True if fetched from the network, False if synthetic fallback
    """
    sidecar = target.with_suffix(target.suffix + ".source.json")
    sidecar.write_text(
        json.dumps(
            {
                "dataset": target.name,
                "source": source,
                "live_fetch": live,
                "note": note,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )
    )
    log(f"  provenance -> {sidecar.name} (live={live})")


def http_get(url: str, *, timeout: int = 20, retries: int = 2, **kwargs: Any):
    """GET with a couple of retries. Returns a Response or None on failure."""
    if requests is None:
        log("  requests not installed; skipping network fetch")
        return None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=timeout, **kwargs)
            if resp.status_code == 200:
                return resp
            log(f"  GET {url} -> HTTP {resp.status_code} (attempt {attempt}/{retries})")
        except Exception as exc:  # noqa: BLE001 - deliberately broad, this is best-effort
            log(f"  GET {url} failed: {exc!r} (attempt {attempt}/{retries})")
        time.sleep(1.5 * attempt)
    return None


def months_between(start: str, end: str) -> list[str]:
    """Inclusive list of 'YYYY-MM' strings between two 'YYYY-MM' bounds."""
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            m = 1
            y += 1
    return out


def require_pandas():
    try:
        import pandas as pd  # noqa: F401

        return pd
    except ImportError:
        log("FATAL: pandas is required. `pip install -r requirements.txt`")
        sys.exit(1)
