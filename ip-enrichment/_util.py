"""Tiny logging helper shared inside the ip-enrichment module."""

from __future__ import annotations

from datetime import datetime


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [ip-enrichment] {msg}", flush=True)
