"""Minimal structured-ish logger used across the API package."""

from __future__ import annotations

import sys
from datetime import datetime


def log(msg: str, *, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} [{level}] {msg}", file=sys.stdout, flush=True)
