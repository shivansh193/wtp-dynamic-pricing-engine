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
    # richer than a single favourite: {"UPI":0.4,"Credit_Card":0.4,"COD":0.2}.
    # When present, the engine derives the preference (argmax) + trust signals
    # from the whole mix.
    payment_split: Optional[dict[str, float]] = None
    # shopper clicked "prefer the standard price" - never price above list
    force_list_price: bool = False
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


class FrictionBrief(BaseModel):
    primary: str = "urgency_insensitive"
    secondary: str = "price_sensitivity"
    confidence: float = 0.0
    scores: dict[str, float] = Field(default_factory=dict)
    drivers: list[dict[str, Any]] = Field(default_factory=list)
    engine: str = "rules"


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
    # customer-facing incentive framing
    offer_label: str = ""
    offer_value_inr: float = 0.0
    is_markup: bool = False
    standard_price: float = 0.0
    net_vs_standard_inr: float = 0.0
    # friction-aware conversion engine
    friction: FrictionBrief = Field(default_factory=lambda: FrictionBrief())
    checkout_config: dict[str, Any] = Field(default_factory=dict)


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


# ==========================================================================
# Link-generator demo flow
# ==========================================================================
Preset = Literal["random", "high", "mid", "low", "custom"]


class CustomSessionFields(BaseModel):
    pin_code: Optional[str] = None
    device_type: Optional[DeviceType] = None
    payment_method_preference: Optional[PaymentPref] = None
    payment_split: Optional[dict[str, float]] = None
    prepaid_orders: Optional[int] = Field(None, ge=0, le=50)
    return_rate: Optional[float] = Field(None, ge=0, le=0.5)
    vpn: Optional[bool] = None
    city_tier: Optional[Literal[1, 2, 3]] = None


class MerchantConfigPatch(BaseModel):
    """Partial update - only the fields present are changed."""
    markup_enabled: Optional[bool] = None
    max_markup_pct: Optional[float] = Field(None, ge=0, le=0.15)
    max_discount_pct: Optional[float] = Field(None, ge=0, le=0.10)
    cod_trust_min: Optional[float] = Field(None, ge=0, le=100)
    cod_completion_min: Optional[float] = Field(None, ge=0, le=1)
    instant_refund_trust_min: Optional[float] = Field(None, ge=0, le=100)
    gross_margin: Optional[float] = Field(None, ge=0.05, le=0.9)
    offers: Optional[dict[str, bool]] = None
    trust_weights: Optional[dict[str, float]] = None


class SessionCreateRequest(BaseModel):
    preset: Preset = "random"
    custom: Optional[CustomSessionFields] = None
    seed: Optional[int] = None


class SessionCreateResponse(BaseModel):
    session_id: str
    merchant_id: str
    preset: str
    config: dict[str, Any]
    segment_key: str
    customer_url: str
    merchant_url: str
    qr_code_base64: str
    status: str
    created_at: str


class SessionInfo(BaseModel):
    session_id: str
    merchant_id: str
    preset: str
    config: dict[str, Any]
    status: str
    created_at: Optional[str] = None
    priced_at: Optional[str] = None
    completed_at: Optional[str] = None
    list_price: Optional[float] = None
    price_shown: Optional[float] = None
    wtp_score: Optional[float] = None
    offer_type: Optional[str] = None
    segment_key: Optional[str] = None
    result: Optional[dict[str, Any]] = None


class SessionListResponse(BaseModel):
    count: int
    backend: str
    sessions: list[SessionInfo]
