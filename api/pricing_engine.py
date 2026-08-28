"""
Step 5 - Pricing Decision Engine.

A *deterministic* rules layer that turns the ML outputs (WTP multiplier +
conversion probability + SHAP) into a concrete checkout treatment. No
randomness, no model calls here - given the same inputs it always returns the
same decision, which makes it auditable and testable.

    decision = decide(
        list_price=4999,
        wtp_multiplier=1.12,
        conversion_probability=0.63,
        customer_signals={...},          # trust score, cod rate, ip signal, ...
        shap_top=[{"feature": "...", "shap": 0.03, "value": "iPhone"}, ...],
        model_confidence="high",
    )

Output keys (see brief):
    final_price, price_delta_pct, offer_type, payment_methods_shown,
    cod_eligible, instant_refund_eligible, reasoning, confidence, latency_ms
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

# --------------------------------------------------------------------------- #
# Tunable constants (all in one place for the review panel)
# --------------------------------------------------------------------------- #
PRICE_CAP_UP = 0.15      # never charge more than +15% of list
PRICE_CAP_DOWN = -0.10   # never discount more than -10% of list

OFFER_PREMIUM_HIGH = "extended_warranty"   # eff multiplier >= 1.08
OFFER_PREMIUM_MID = "priority_support"     # 1.03 .. 1.08
OFFER_NEUTRAL = "none"                     # ~ list price, healthy conversion
OFFER_NUDGE_SOFT = "free_delivery"        # small discount OR soft conversion
OFFER_NUDGE_HARD = "cashback_5pct"        # deep discount / weak conversion

ALL_OFFERS = [
    OFFER_PREMIUM_HIGH, OFFER_PREMIUM_MID, OFFER_NEUTRAL,
    OFFER_NUDGE_SOFT, OFFER_NUDGE_HARD, "priority_support",
]

# indicative rupee value of each perk, shown to the shopper so a higher price
# never looks unexplained ("₹5,749 — includes a ₹899 warranty").
OFFER_VALUE_INR = {
    OFFER_PREMIUM_HIGH: 899.0,        # 1-yr extended warranty
    OFFER_PREMIUM_MID: 499.0,         # priority support
    "priority_support": 499.0,
    OFFER_NUDGE_SOFT: 99.0,           # free delivery
    OFFER_NUDGE_HARD: None,           # cashback = 5% of final price, computed live
    OFFER_NEUTRAL: 0.0,
}

# defaults - overridable per merchant via api/merchant_config.py
COD_TRUST_MIN = 60.0
COD_COMPLETION_MIN = 0.80
# a COD-native shopper with a solid delivery-acceptance record earns COD even at
# a lower cross-merchant trust score (they just don't transact on cards much)
COD_PREF_TRUST_MIN = 25.0
COD_PREF_COMPLETION_MIN = 0.75
INSTANT_REFUND_TRUST_MIN = 80.0
WEAK_CONVERSION = 0.40

# human-readable names for SHAP features used in `reasoning`
FEATURE_LABELS = {
    "device_type": "device type",
    "city_tier": "city tier",
    "income_tier": "neighbourhood income tier",
    "payment_method_preference": "preferred payment method",
    "time_of_day": "time of day",
    "day_of_week": "day of week",
    "referral_source": "referral source",
    "ip_type": "network type",
    "product_category": "product category",
    "month": "month",
    "digital_demand_index": "overall digital-payments demand",
    "ip_trust_multiplier": "IP trust score",
    "historical_aov": "historical average order value",
    "return_rate": "return rate",
    "payment_success_rate": "payment success rate",
    "cod_completion_rate": "COD completion rate",
    "cross_merchant_trust_score": "cross-merchant trust score",
    "num_merchants_transacted": "number of merchants shopped",
    "account_age_days": "account age",
    "cart_value": "cart value",
    "is_festival_period": "festival period",
    "festival_intensity": "festival intensity",
}


@dataclass
class PricingDecision:
    list_price: float
    final_price: float
    price_delta_pct: float
    effective_multiplier: float
    wtp_multiplier: float
    conversion_probability: float | None
    offer_type: str
    offer_rationale: str
    payment_methods_shown: list[str]
    cod_eligible: bool
    instant_refund_eligible: bool
    reasoning: str
    confidence: str
    latency_ms: float = 0.0
    caps_applied: list[str] = field(default_factory=list)
    # customer-facing incentive framing
    offer_label: str = ""
    offer_value_inr: float = 0.0            # indicative rupee value of the perk
    is_markup: bool = False
    standard_price: float = 0.0             # list price - the "no thanks" option
    net_vs_standard_inr: float = 0.0        # (offer value) - (price delta); >0 = shopper ahead

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
def _humanize_feature(name: str) -> str:
    return FEATURE_LABELS.get(name, name.replace("_", " "))


def _direction_phrase(shap_value: float) -> str:
    return "pushing the price up" if shap_value > 0 else "pulling the price down"


def _price_with_caps(list_price: float, wtp_multiplier: float,
                     cap_up: float = PRICE_CAP_UP,
                     cap_down: float = PRICE_CAP_DOWN) -> tuple[float, float, list[str]]:
    raw_mult = wtp_multiplier
    caps: list[str] = []
    eff = raw_mult
    if eff > 1 + cap_up:
        eff = 1 + cap_up
        caps.append(f"capped at +{cap_up:.0%} (model wanted {raw_mult:.3f})")
    if eff < 1 + cap_down:
        eff = 1 + cap_down
        caps.append(f"floored at {cap_down:.0%} (model wanted {raw_mult:.3f})")
    final = round(list_price * eff, 2)
    return final, eff, caps


_DISCOUNT_FALLBACK = [OFFER_NUDGE_SOFT, OFFER_NUDGE_HARD, OFFER_NEUTRAL]
_PREMIUM_FALLBACK = [OFFER_PREMIUM_HIGH, OFFER_PREMIUM_MID, "priority_support", OFFER_NEUTRAL]


def _first_allowed(candidates: list[str], allowed) -> str:
    for c in candidates:
        if c == OFFER_NEUTRAL or allowed is None or allowed(c):
            return c
    return OFFER_NEUTRAL


def _choose_offer(eff_mult: float, conversion_probability: float | None,
                  allowed=None) -> tuple[str, str]:
    """High WTP -> premium experience. Low WTP / weak conversion -> discount nudge.
    `allowed(offer)->bool` filters to the merchant-enabled perks."""
    weak_conv = conversion_probability is not None and conversion_probability < WEAK_CONVERSION

    if eff_mult >= 1.08:
        offer = _first_allowed(_PREMIUM_FALLBACK, allowed)
        why = "high willingness to pay - reinforce value with a premium-experience perk"
    elif eff_mult >= 1.03:
        offer = _first_allowed(_PREMIUM_FALLBACK[1:], allowed)
        why = "above-list willingness to pay - add a service perk rather than a discount"
    elif eff_mult > 0.97:
        if weak_conv:
            offer = _first_allowed(_DISCOUNT_FALLBACK, allowed)
            why = "list-price shopper but soft conversion odds - a small sweetener nudges checkout"
        else:
            offer = OFFER_NEUTRAL
            why = "priced at list with healthy conversion odds - no offer needed"
    elif eff_mult > 0.93:
        offer = _first_allowed(_DISCOUNT_FALLBACK, allowed)
        why = "modest price sensitivity - a light nudge closes the gap without margin loss"
    else:
        offer = _first_allowed([OFFER_NUDGE_HARD, OFFER_NUDGE_SOFT, OFFER_NEUTRAL], allowed)
        why = "high price sensitivity - a cashback nudge is the most effective here"

    if weak_conv and offer in (OFFER_NEUTRAL, OFFER_PREMIUM_MID):
        offer = _first_allowed(_DISCOUNT_FALLBACK, allowed)
        why += "; downgraded to a nudge because conversion probability is weak"
    return offer, why


def _payment_order(signals: dict, eff_mult: float, cod_eligible: bool) -> list[str]:
    """Personalised, ordered payment method list.

    Starts from the shopper's *own* payment mix (their most-used method first),
    then fills the rest with a WTP-tilted ordering: a high-WTP shopper sees
    card/EMI options promoted, a price-sensitive one sees UPI/COD promoted.
    """
    split = signals.get("payment_split") or {}
    pref = signals.get("payment_method_preference")

    # the shopper's methods, most-used first (only those they actually use)
    used = [m for m, s in sorted(split.items(), key=lambda kv: kv[1], reverse=True)
            if s and s > 0.02]
    if pref and pref not in used:
        used.insert(0, pref)

    if eff_mult >= 1.03:
        tilt = ["Credit_Card", "UPI", "Wallet", "Debit_Card", "COD"]
    elif eff_mult <= 0.97:
        tilt = ["UPI", "COD", "Wallet", "Debit_Card", "Credit_Card"]
    else:
        tilt = ["UPI", "Credit_Card", "Wallet", "Debit_Card", "COD"]

    order = list(used) + [m for m in tilt if m not in used]

    if not cod_eligible:
        order = [m for m in order if m != "COD"]
    elif "COD" not in order:
        order.append("COD")

    seen, out = set(), []
    for m in order:
        if m and m not in seen:
            out.append(m)
            seen.add(m)
    return out[:5]


def _build_reasoning(
    final_price: float, list_price: float, delta_pct: float,
    offer_type: str, shap_top: list[dict], caps: list[str],
) -> str:
    top2 = [s for s in (shap_top or []) if s.get("feature")][:2]
    if top2:
        f1 = top2[0]
        parts = [
            f"{_humanize_feature(f1['feature'])} (={_fmt_val(f1.get('value'))}) is the strongest "
            f"driver, {_direction_phrase(f1['shap'])}"
        ]
        if len(top2) > 1:
            f2 = top2[1]
            parts.append(
                f"followed by {_humanize_feature(f2['feature'])} "
                f"(={_fmt_val(f2.get('value'))}), {_direction_phrase(f2['shap'])}"
            )
        driver_sentence = ", ".join(parts) + "."
    else:
        driver_sentence = "Pricing is based on the blended customer profile."

    direction = (
        f"We are showing {_inr(final_price)} "
        f"({'+' if delta_pct >= 0 else ''}{delta_pct:.1f}% vs the {_inr(list_price)} list price)."
    )
    if offer_type == OFFER_NEUTRAL:
        offer_sentence = "No offer is attached because the list price already converts well here."
    else:
        offer_sentence = f"The '{offer_type}' offer is attached to match this customer's profile."
    cap_sentence = f" Price bounds were enforced: {caps[0]}." if caps else ""
    return f"{direction} {driver_sentence} {offer_sentence}{cap_sentence}"


def _fmt_val(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def _inr(x: float) -> str:
    return f"₹{x:,.0f}"


# --------------------------------------------------------------------------- #
OFFER_LABELS = {
    OFFER_PREMIUM_HIGH: "Free 1-year extended warranty",
    OFFER_PREMIUM_MID: "Priority customer support",
    "priority_support": "Priority customer support",
    OFFER_NUDGE_SOFT: "Free delivery",
    OFFER_NUDGE_HARD: "5% cashback",
    OFFER_NEUTRAL: "",
}


def decide(
    *,
    list_price: float,
    wtp_multiplier: float,
    conversion_probability: float | None,
    customer_signals: dict,
    shap_top: list[dict] | None = None,
    model_confidence: str = "medium",
    merchant_config: Any = None,
    force_list_price: bool = False,
) -> PricingDecision:
    t0 = time.perf_counter()
    mc = merchant_config
    if mc is None:
        from .merchant_config import get_config

        mc = get_config()

    trust = float(customer_signals.get("cross_merchant_trust_score", 50) or 50)
    cod_rate = float(customer_signals.get("cod_completion_rate", 0.0) or 0.0)

    # "prefer standard price" -> never price above list for this request
    raw_mult = float(wtp_multiplier)
    if force_list_price:
        raw_mult = min(raw_mult, 1.0)

    cap_up, cap_down = mc.effective_caps()
    final_price, eff_mult, caps = _price_with_caps(list_price, raw_mult, cap_up, cap_down)
    delta_pct = (final_price / list_price - 1.0) * 100.0 if list_price else 0.0
    is_markup = delta_pct > 0.05

    prefers_cod = customer_signals.get("payment_method_preference") == "COD"
    cod_eligible = (trust > mc.cod_trust_min and cod_rate > mc.cod_completion_min) or (
        prefers_cod and trust > mc.cod_pref_trust_min and cod_rate > mc.cod_pref_completion_min
    )
    instant_refund_eligible = bool(
        mc.offers.instant_refund and trust > mc.instant_refund_trust_min
    )

    offer_type, offer_rationale = _choose_offer(
        eff_mult, conversion_probability, allowed=mc.offers.allowed
    )

    # customer-facing incentive value
    if offer_type == OFFER_NUDGE_HARD:
        offer_value = round(final_price * 0.05, 2)
    else:
        offer_value = float(OFFER_VALUE_INR.get(offer_type) or 0.0)
    price_delta_inr = round(final_price - list_price, 2)
    net_vs_standard = round(offer_value - max(0.0, price_delta_inr), 2)

    payment_methods = _payment_order(customer_signals, eff_mult, cod_eligible)

    confidence = model_confidence
    if caps and confidence == "high":
        confidence = "medium"
    if customer_signals.get("ip_type") in {"vpn", "tor", "datacenter"} and confidence == "high":
        confidence = "medium"

    reasoning = _build_reasoning(final_price, list_price, delta_pct, offer_type,
                                 shap_top or [], caps)

    decision = PricingDecision(
        list_price=round(float(list_price), 2),
        final_price=final_price,
        price_delta_pct=round(delta_pct, 2),
        effective_multiplier=round(eff_mult, 4),
        wtp_multiplier=round(float(wtp_multiplier), 4),
        conversion_probability=(None if conversion_probability is None
                                else round(float(conversion_probability), 4)),
        offer_type=offer_type,
        offer_rationale=offer_rationale,
        payment_methods_shown=payment_methods,
        cod_eligible=cod_eligible,
        instant_refund_eligible=instant_refund_eligible,
        reasoning=reasoning,
        confidence=confidence,
        caps_applied=caps,
        offer_label=OFFER_LABELS.get(offer_type, ""),
        offer_value_inr=offer_value,
        is_markup=is_markup,
        standard_price=round(float(list_price), 2),
        net_vs_standard_inr=net_vs_standard,
        latency_ms=round((time.perf_counter() - t0) * 1000, 4),
    )
    return decision
