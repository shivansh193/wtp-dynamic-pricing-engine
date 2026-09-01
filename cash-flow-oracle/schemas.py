"""Pydantic request/response models for the Cash Flow Oracle."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional

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


# ==========================================================================
# /oracle/* endpoints (Track 04 dashboard)
# ==========================================================================
class OracleForecastResponse(ForecastResponse):
    """POST /oracle/forecast - the scaffold forecast plus everything the
    dashboard's hero + regime + credit panels need in one call."""
    regime: str
    regime_confidence: float
    regime_description: str
    regime_history: list[dict]

    peer_comparison: dict
    anomaly_flag: bool
    anomaly_explanation: Optional[str] = None

    operating_threshold: float
    cash_on_hand: float
    cash_position_curve: list[dict]
    cash_stress_periods: list[dict]

    credit_apply_by_date: Optional[date] = None
    carry_cost_analysis: dict

    forecast_accuracy_mape: Optional[float] = None
    next_stress_days: Optional[int] = None
    current_cash_trend_pct: float = 0.0
    festival_markers: list[dict] = Field(default_factory=list)


ShockType = Literal["discount_sale", "marketing_spend",
                    "inventory_purchase", "payment_gateway_outage"]


class ScenarioRequest(BaseModel):
    merchant_id: str = Field(..., examples=["m_fashion_01"])
    shock_type: ShockType
    shock_magnitude: float = Field(..., ge=1, le=90, description="percentage impact")
    shock_start_date: date
    shock_duration_days: int = Field(..., ge=1, le=45)
    horizon_days: int = Field(60, ge=14, le=60)


class LLMRecommendationRequest(BaseModel):
    merchant_id: str
    forecast: dict
    regime: Optional[str] = None
    regime_confidence: Optional[float] = None
    peer_comparison: Optional[dict] = None
    anomaly_flag: bool = False
    anomaly_explanation: Optional[str] = None
    carry_cost_analysis: Optional[dict] = None
    credit_apply_by_date: Optional[str] = None


class AlertPreviewRequest(BaseModel):
    merchant_id: str = Field(..., examples=["m_fashion_01"])
