"""Pydantic request/response models for POST /forecast."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class ForecastRequest(BaseModel):
    merchant_id: str = Field(..., examples=["m_fashion_01"])
    horizon_days: int = Field(30, ge=7, le=60)


class ForecastPoint(BaseModel):
    date: date
    yhat: float
    lower: float
    upper: float
    regime_hint: str | None = None


class StressPeriod(BaseModel):
    start: date
    end: date
    days: int
    min_lower_inr: float
    drop_vs_trailing_pct: float
    reason: str


class ForecastResponse(BaseModel):
    merchant_id: str
    archetype: str | None
    engine: str  # "prophet+garch+hmm" or which parts fell back
    generated_on: date

    current_cash_position: float
    trailing_30d_net_inr: float
    trailing_7d_net_inr: float

    current_regime: str
    regime_stats: dict

    volatility: dict  # {historical_daily_pct, forecast_daily_pct, ratio}

    forecast_curve: list[ForecastPoint]
    forecast_total_inr: float

    stress_periods: list[StressPeriod]

    credit_recommendation: str
