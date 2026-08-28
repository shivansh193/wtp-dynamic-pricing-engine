"""
Market-context lookups the model needs but that aren't in the request:
festival period/intensity for a date, and the RBI digital-demand index for a
month. Loaded once from the pipeline's CSV outputs; safe no-op defaults if the
files are absent.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .config import settings
from .logging_util import log


class MarketContext:
    def __init__(self) -> None:
        self._festival: dict[str, tuple[int, int]] = {}
        self._demand: dict[str, float] = {}
        self.loaded = {"festival": False, "demand": False}

    def load(self) -> None:
        self._load_festival()
        self._load_demand()

    def _load_festival(self) -> None:
        path = settings.DATA_PROCESSED / "festival_features.csv"
        if not path.exists():
            log(f"context: {path.name} missing - festivals default to off")
            return
        with path.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                is_fest = str(r.get("is_festival_period", "")).strip().lower() in {"true", "1"}
                try:
                    intensity = int(float(r.get("intensity_score", 0) or 0))
                except ValueError:
                    intensity = 0
                self._festival[r["date"]] = (int(is_fest), intensity)
        self.loaded["festival"] = True
        log(f"context: festival calendar loaded ({len(self._festival)} days)")

    def _load_demand(self) -> None:
        path = settings.DATA_RAW / "rbi_digital_payments.csv"
        if not path.exists():
            log(f"context: {path.name} missing - demand index defaults to 1.0")
            return
        with path.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try:
                    self._demand[r["month"]] = float(r.get("digital_demand_index", 1.0) or 1.0)
                except ValueError:
                    continue
        self.loaded["demand"] = True
        log(f"context: RBI demand index loaded ({len(self._demand)} months)")

    # ------------------------------------------------------------------ #
    def festival_lookup(self, iso_date: str) -> tuple[int, int]:
        return self._festival.get(iso_date, (0, 0))

    def demand_lookup(self, year_month: str) -> float:
        if year_month in self._demand:
            return self._demand[year_month]
        # fall back to the most recent known month
        if self._demand:
            return self._demand[sorted(self._demand)[-1]]
        return 1.0


market_context = MarketContext()
