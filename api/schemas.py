"""Request / response models for the pricing API."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

DeviceType = Literal["Android_budget", "Android_premium", "iPhone", "Desktop"]
PaymentPref = Literal["UPI", "Credit_Card", "Debit_Card", "COD", "Wallet"]
Category = Literal["fashion", "electronics", "grocery", "home", "beauty"]


class CustomerSignals(BaseModel):
    """Everything the caller knows about the shopper + the cart.

    Only `list_price` is truly required; every other field has a model-side
    default so a thin payload still returns a sensible decision.
    """

    # ---- identity / routing ----
    session_id: Optional[str] = Field(None, description="merchant checkout session id")
    ip: Optional[str] = Field(None, description="shopper IP for enrichment", examples=["49.36.128.5"])

    # ---- cart ----
    list_price: float = Field(..., gt=0, examples=[4999])
    product_category: Category = "fashion"
    cart_value: Optional[float] = Field(None, gt=0)

    # ---- device / geo / session ----
    device_type: DeviceType = "Android_budget"
    city_tier: Literal[1, 2, 3] = 2
    pin_code: Optional[str] = None
    income_tier: Optional[Literal["low", "lower_mid", "mid", "upper_mid", "high"]] = None
    payment_method_preference: PaymentPref = "UPI"
    time_of_day: Optional[Literal["morning", "afternoon", "evening", "night"]] = None
    hour: Optional[int] = Field(None, ge=0, le=23)
    day_of_week: Optional[Literal["weekday", "weekend"]] = None
    referral_source: Literal["organic", "paid_ad", "social", "email", "influencer"] = "organic"
    txn_date: Optional[str] = Field(None, description="ISO date; defaults to today")

    # ---- behavioural history (from the merchant / Razorpay network) ----
    historical_aov: Optional[float] = Field(None, ge=0)
    return_rate: float = Field(0.15, ge=0, le=1)
    payment_success_rate: float = Field(0.90, ge=0, le=1)
    cod_completion_rate: float = Field(0.85, ge=0, le=1)
    cross_merchant_trust_score: float = Field(55, ge=0, le=100)
    num_merchants_transacted: int = Field(5, ge=1, le=50)
    account_age_days: int = Field(200, ge=1, le=3000)

    # ---- optional overrides (else derived from IP enrichment) ----
    ip_type: Optional[str] = None
    ip_trust_multiplier: Optional[float] = Field(None, ge=0, le=1)

    def model_signals(self) -> dict[str, Any]:
        """Flat dict passed to the model feature builder + pricing engine."""
        d = self.model_dump(exclude_none=False)
        if d.get("cart_value") is None:
            d["cart_value"] = d["list_price"]
        if d.get("historical_aov") is None:
            d["historical_aov"] = d["cart_value"]
        return d


class ShapFeature(BaseModel):
    feature: str
    value: Any
    shap: float


class IpEnrichmentBrief(BaseModel):
    ip_type: str = "unknown"
    ip_trust_multiplier: float = 0.8
    location_confidence: float = 0.0
    is_whitelisted: bool = False
    blocklist_hits: list[str] = Field(default_factory=list)
    geo_source: str = "none"
    cache_hit: bool = False
    lookup_ms: float = 0.0


class PricingResponse(BaseModel):
    session_id: str
    list_price: float
    final_price: float
    price_delta_pct: float
    effective_multiplier: float
    wtp_multiplier: float
    conversion_probability: Optional[float]
    offer_type: str
    offer_rationale: str
    payment_methods_shown: list[str]
    cod_eligible: bool
    instant_refund_eligible: bool
    reasoning: str
    confidence: str
    shap_top: list[ShapFeature]
    ip_enrichment: IpEnrichmentBrief
    latency_ms: float
    budget_ms: int
    budget_exceeded: bool
    timing_breakdown: dict[str, float]


class SimulateRequest(BaseModel):
    profile: CustomerSignals
    counterfactuals: Optional[dict[str, list[Any]]] = Field(
        None,
        description="feature -> list of alternative values to sweep. Defaults to "
        "device_type / city_tier / payment_method_preference.",
    )


class Counterfactual(BaseModel):
    feature: str
    value: Any
    wtp_multiplier: float
    final_price: float
    price_delta_pct: float
    offer_type: str
    delta_vs_base_price: float


class SimulateResponse(BaseModel):
    base: PricingResponse
    sensitivity: list[Counterfactual]
