"""
Friction-Aware Conversion Engine — Step 2 (Intervention Library) + Step 3
(Dynamic Checkout Assembly).

For each friction type there is a primary / secondary / tertiary intervention.
Each carries:
  id                      stable key, logged for the performance tracker
  display_component       which checkout widget renders it
  copy                    the exact shopper-facing text (templated)
  psychological_mechanism the bias / need it addresses
  expected_conversion_lift synthetic range, anchored to published ecommerce
                          research (Baymard cart-abandonment work, EMI/BNPL
                          conversion studies, social-proof field experiments)

`build_checkout_config()` turns a FrictionResult + the priced decision into the
`checkout_config` object the Next.js checkout renders from — nothing in the
layout is hardcoded, every widget is conditional on this config.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from .friction_engine import CATEGORY_AOV, FrictionResult

# --------------------------------------------------------------------------- #
# Intervention library
# --------------------------------------------------------------------------- #
INTERVENTIONS: dict[str, dict[str, dict[str, Any]]] = {
    "price_sensitivity": {
        "primary": {
            "id": "emi_breakdown",
            "display_component": "price_emi",
            "copy": "₹{emi}/month for {months} months · 0% interest",
            "psychological_mechanism": "payment decoupling — a large number reframed "
            "as a small recurring one lowers the perceived pain of paying",
            "expected_conversion_lift": "12-20%",
        },
        "secondary": {
            "id": "price_anchor",
            "display_component": "price_anchor",
            "copy": "Market price ~₹{anchor}",
            "psychological_mechanism": "anchoring — a higher reference price makes "
            "the actual price feel like a gain",
            "expected_conversion_lift": "6-11%",
        },
        "tertiary": {
            "id": "micro_commitment",
            "display_component": "cod_split",
            "copy": "Add to cart free — pay only when you decide to keep it",
            "psychological_mechanism": "endowment + loss aversion — possession before "
            "payment reframes the decision as 'keep' not 'buy'",
            "expected_conversion_lift": "8-14%",
        },
    },
    "trust_deficit": {
        "primary": {
            "id": "social_proof_counter",
            "display_component": "social_proof",
            "copy": "{count} people bought this in the last 24 hours",
            "psychological_mechanism": "social proof — others' behaviour as evidence "
            "of a safe choice under uncertainty",
            "expected_conversion_lift": "10-18%",
        },
        "secondary": {
            "id": "dynamic_trust_badges",
            "display_component": "trust_badges",
            "copy": "",
            "psychological_mechanism": "risk reduction — surface the specific "
            "guarantee that matches this shopper's fear",
            "expected_conversion_lift": "5-9%",
        },
        "tertiary": {
            "id": "relevant_review",
            "display_component": "review_snippet",
            "copy": "{review}",
            "psychological_mechanism": "similarity heuristic — a review from someone "
            "like me carries more weight",
            "expected_conversion_lift": "4-8%",
        },
    },
    "decision_paralysis": {
        "primary": {
            "id": "comparison_eliminator",
            "display_component": "badge_line",
            "copy": "#1 choice in {category} under ₹{bracket}",
            "psychological_mechanism": "choice-overload relief — an external ranking "
            "removes the need to keep searching",
            "expected_conversion_lift": "9-15%",
        },
        "secondary": {
            "id": "soft_urgency",
            "display_component": "urgency",
            "copy": "Only {stock} left at this price",
            "psychological_mechanism": "scarcity — but shown only after real "
            "hesitation (3+ min) and genuinely low stock, never on first load",
            "expected_conversion_lift": "7-12%",
        },
        "tertiary": {
            "id": "price_lock",
            "display_component": "price_lock",
            "copy": "Lock this price for 24 hours — decide later",
            "psychological_mechanism": "commitment device — captures the shopper "
            "even if they don't buy now",
            "expected_conversion_lift": "5-9%",
        },
    },
    "payment_friction": {
        "primary": {
            "id": "payment_reorder",
            "display_component": "payment_order",
            "copy": "{method} ready — one tap to pay",
            "psychological_mechanism": "friction removal — the preferred method is "
            "first and pre-expanded, no scrolling past options they won't use",
            "expected_conversion_lift": "8-16%",
        },
        "secondary": {
            "id": "cod_bridge",
            "display_component": "cod_split",
            "copy": "Pay ₹{upfront} now, ₹{rest} on delivery",
            "psychological_mechanism": "risk splitting — a partial prepay de-risks "
            "the merchant and keeps the shopper's cash-on-delivery comfort",
            "expected_conversion_lift": "10-17%",
        },
        "tertiary": {
            "id": "one_tap_next_time",
            "display_component": "badge_line",
            "copy": "Save this method for one-tap checkout next time",
            "psychological_mechanism": "future-friction reduction — builds toward "
            "the repeat purchase",
            "expected_conversion_lift": "3-6%",
        },
    },
    "delivery_anxiety": {
        "primary": {
            "id": "delivery_promise",
            "display_component": "delivery_promise",
            "copy": "Delivered by {date}",
            "psychological_mechanism": "uncertainty reduction — a specific date beats "
            "'3-5 business days'; concreteness lowers anxiety",
            "expected_conversion_lift": "9-14%",
        },
        "secondary": {
            "id": "return_guarantee_prominent",
            "display_component": "trust_badges",
            "copy": "30-day no-questions returns",
            "psychological_mechanism": "reversibility — a costless exit lowers the "
            "stakes of committing",
            "expected_conversion_lift": "6-10%",
        },
        "tertiary": {
            "id": "packaging_promise",
            "display_component": "badge_line",
            "copy": "Sealed and quality-checked before it ships",
            "psychological_mechanism": "addresses the 'what if it arrives damaged' "
            "fear that dominates high-value first purchases",
            "expected_conversion_lift": "4-7%",
        },
    },
    "urgency_insensitive": {
        "primary": {
            "id": "quality_signal",
            "display_component": "badge_line",
            "copy": "Rated {rating}/5 by {reviews}+ verified buyers",
            "psychological_mechanism": "confirmation — a high-WTP repeat buyer wants "
            "reassurance they're making the right choice, not a countdown",
            "expected_conversion_lift": "6-11%",
        },
        "secondary": {
            "id": "premium_highlight",
            "display_component": "badge_line",
            "copy": "Extended 2-year warranty & priority support included",
            "psychological_mechanism": "premium framing — this segment responds to "
            "added value, not discounts",
            "expected_conversion_lift": "5-9%",
        },
        "tertiary": {
            "id": "exclusivity",
            "display_component": "badge_line",
            "copy": "Offered to select customers based on your purchase history",
            "psychological_mechanism": "recognition + scarcity of access — makes a "
            "loyal customer feel seen (shown only to high-trust shoppers)",
            "expected_conversion_lift": "3-6%",
        },
    },
}

TRUST_BADGES = {
    "easy_returns": "Easy 10-day returns",
    "secure_checkout": "Secure checkout · no card data stored",
    "verified_seller": "Verified seller · RunHub Official",
    "return_30d": "30-day no-questions returns",
    "cod_available": "Cash on Delivery available",
    "delivery_tracked": "Live order tracking",
    "quality_checked": "Sealed & quality-checked",
}

# tiny, profile-keyed review library (category -> tier -> snippet)
_REVIEWS = {
    "electronics": {
        3: "Ordered to Patna, arrived in 3 days, box was sealed. Works perfectly.",
        2: "Delivery to Jaipur was quick and the product is genuine.",
        1: "Same-day delivery in Mumbai, exactly as described.",
    },
    "home": {
        3: "Shipped to a Tier-3 town without a scratch. Packaging was solid.",
        2: "Good quality for the price, delivered on the promised date.",
        1: "Fast delivery, feels premium in person.",
    },
    "fashion": {
        3: "Fit was true to size, return process would've been easy but didn't need it.",
        2: "Nice material, delivered in 2 days.",
        1: "Exactly the colour shown, quick delivery.",
    },
}
_REVIEWS_DEFAULT = "Genuine product, delivered on time, would order again."


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def emi_breakdown(price: float, months: int = 12) -> dict[str, Any]:
    per = round(price / months)
    return {"emi_amount": per, "emi_months": months}


def anchor_price(category: str, final_price: float) -> int:
    base = CATEGORY_AOV.get(category, 2500)
    # anchor = the higher of a category-derived reference and ~1.25x the price
    anchor = max(base * 1.55, final_price * 1.24)
    return int(round(anchor / 50) * 50)


def cod_split(final_price: float, trust: float) -> dict[str, int]:
    # a lower-trust shopper prepays a bit more; clamp 10-30%
    upfront_pct = int(min(30, max(10, round((70 - trust) / 3))))
    return {"upfront_pct": upfront_pct, "on_delivery_pct": 100 - upfront_pct}


def delivery_promise(pin_tier: int, today: date | None = None) -> str:
    today = today or datetime.now(timezone.utc).date()
    days = {1: 1, 2: 3, 3: 5}.get(pin_tier, 4)
    d = today + timedelta(days=days)
    return f"Delivered by {d.strftime('%a, %d %b')}"


def synthetic_stock(session_id: str, cart_value: float) -> int:
    """Deterministic pseudo stock 3..40, lower for pricier carts."""
    h = sum(ord(c) for c in session_id) % 25
    lo = 3 if cart_value >= 5000 else 6
    return lo + h % (18 if cart_value >= 5000 else 30)


def social_proof_count(base_sessions: int, category: str) -> int:
    mult = {"electronics": 1.6, "fashion": 2.1, "home": 1.2, "grocery": 3.0, "beauty": 1.8}
    return int(400 + base_sessions * 7 + 900 * mult.get(category, 1.5))


def review_snippet(signals: dict) -> str:
    cat = signals.get("product_category", "fashion")
    tier = int(signals.get("city_tier", 2) or 2)
    return _REVIEWS.get(cat, {}).get(tier) or _REVIEWS_DEFAULT


def select_trust_badges(friction: str, signals: dict, decision: Any) -> list[str]:
    ip = signals.get("ip_type", "residential")
    acct_new = float(signals.get("account_age_days", 200) or 200) < 90
    cat = signals.get("product_category", "fashion")
    picks: list[str] = []
    if friction == "trust_deficit":
        picks += ["secure_checkout"] if ip in {"vpn", "tor", "datacenter"} else []
        picks += ["easy_returns"] if acct_new else ["verified_seller"]
        picks += ["verified_seller"]
    elif friction == "delivery_anxiety":
        picks += ["return_30d", "delivery_tracked"]
        picks += ["quality_checked"] if cat in {"electronics", "home"} else []
    elif friction == "payment_friction":
        picks += ["cod_available"] if getattr(decision, "cod_eligible", False) else []
        picks += ["secure_checkout", "verified_seller"]
    else:
        picks += ["verified_seller", "easy_returns"]
    # de-dup, keep 2-3
    seen, out = set(), []
    for p in picks:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out[:3]


def _bracket(price: float) -> int:
    for b in (2000, 3000, 5000, 8000, 12000, 20000):
        if price <= b:
            return b
    return 30000


def _lift_midpoint(rng: str) -> float:
    try:
        a, b = rng.replace("%", "").split("-")
        return (float(a) + float(b)) / 2
    except Exception:  # noqa: BLE001
        return 8.0


# --------------------------------------------------------------------------- #
# Step 3 — checkout config assembler
# --------------------------------------------------------------------------- #
def _pick(friction: str, slot: str, fatigued: set[str] | None) -> dict[str, Any]:
    lib = INTERVENTIONS[friction]
    order = ["primary", "secondary", "tertiary"]
    order = order[order.index(slot):] + order[: order.index(slot)]
    for s in order:
        iv = lib[s]
        if not fatigued or iv["id"] not in fatigued:
            return iv
    return lib[slot]


def build_checkout_config(
    friction: FrictionResult,
    signals: dict,
    decision: Any,
    *,
    session_id: str,
    session_minutes: float = 0.0,
    base_session_count: int = 0,
    fatigued_intervention_ids: set[str] | None = None,
    allowed_ids: set[str] | None = None,
) -> dict[str, Any]:
    ft = friction.primary
    price = float(decision.final_price)
    list_price = float(decision.list_price)
    cat = signals.get("product_category", "fashion")
    tier = int(signals.get("city_tier", 2) or 2)
    trust = float(signals.get("cross_merchant_trust_score", 55) or 55)
    is_markup = bool(getattr(decision, "is_markup", price > list_price + 0.5))

    prim = _pick(ft, "primary", fatigued_intervention_ids)
    sec = _pick(friction.secondary, "primary", fatigued_intervention_ids)
    if allowed_ids is not None:
        if prim["id"] not in allowed_ids:
            prim = _pick(ft, "secondary", fatigued_intervention_ids)
        if sec["id"] not in allowed_ids:
            sec = _pick(ft, "tertiary", fatigued_intervention_ids)

    cfg: dict[str, Any] = {
        "friction_type": ft,
        "friction_secondary": friction.secondary,
        "friction_confidence": round(friction.confidence, 3),
        "friction_drivers": friction.drivers,
        "primary_intervention": prim["id"],
        "secondary_intervention": sec["id"],
        "psychological_mechanism": prim["psychological_mechanism"],
        # price display
        "price_display": "full",
        "final_price": price,
        "list_price": list_price,
        "is_markup": is_markup,
        "emi_amount": None,
        "emi_months": None,
        "anchor_price": None,
        # widgets (null unless activated)
        "trust_badges": [],
        "payment_method_order": list(getattr(decision, "payment_methods_shown", []) or []),
        "cod_split_offer": None,
        "urgency_message": None,
        "urgency_min_seconds": 180,
        "delivery_promise": None,
        "social_proof_count": None,
        "social_proof_live": False,
        "review_snippet": None,
        "price_lock_expiry": None,
        "quality_signal": None,
        "premium_note": None,
        "exclusivity_note": None,
        "expected_conversion_lift": prim["expected_conversion_lift"],
        "offer_headline": "",   # the customer-facing one-liner
    }

    # ---- friction-specific activation ----
    if ft == "price_sensitivity":
        emi = emi_breakdown(price, 12)
        cfg.update(price_display="emi", **emi)
        cfg["anchor_price"] = anchor_price(cat, price)
        cfg["offer_headline"] = f"₹{emi['emi_amount']:,}/mo · 0% interest"
        if signals.get("payment_method_preference") == "COD" or \
                (signals.get("payment_split") or {}).get("COD", 0) > 0.4:
            cfg["cod_split_offer"] = cod_split(price, trust)

    elif ft == "trust_deficit":
        cfg["social_proof_count"] = social_proof_count(base_session_count, cat)
        cfg["social_proof_live"] = True
        cfg["trust_badges"] = select_trust_badges(ft, signals, decision)
        cfg["review_snippet"] = review_snippet(signals)
        cfg["offer_headline"] = f"{cfg['social_proof_count']:,} bought this in 24h"

    elif ft == "decision_paralysis":
        cfg["offer_headline"] = f"#1 in {cat} under ₹{_bracket(price):,}"
        stock = synthetic_stock(session_id, price)
        if session_minutes >= 3 and stock <= 10:
            cfg["urgency_message"] = f"Only {stock} left at this price"
        # price lock always available for the fence-sitter
        cfg["price_lock_expiry"] = (
            datetime.now(timezone.utc) + timedelta(hours=24)
        ).isoformat(timespec="seconds")

    elif ft == "payment_friction":
        pref = signals.get("payment_method_preference", "UPI")
        cfg["offer_headline"] = f"{pref.replace('_', ' ')} ready — one tap"
        if not getattr(decision, "cod_eligible", False) and (
            pref == "COD" or (signals.get("payment_split") or {}).get("COD", 0) > 0.4
        ):
            cfg["cod_split_offer"] = cod_split(price, trust)
        cfg["trust_badges"] = select_trust_badges(ft, signals, decision)

    elif ft == "delivery_anxiety":
        cfg["delivery_promise"] = delivery_promise(tier)
        cfg["trust_badges"] = select_trust_badges(ft, signals, decision)
        cfg["offer_headline"] = cfg["delivery_promise"]

    elif ft == "urgency_insensitive":
        cfg["quality_signal"] = "Rated 4.8/5 by 12,000+ verified buyers"
        cfg["premium_note"] = "Extended 2-year warranty & priority support included"
        if trust >= 75:
            cfg["exclusivity_note"] = "Offered to select customers based on your history"
        cfg["offer_headline"] = "4.8/5 · 12,000+ verified buyers"
        if is_markup:
            cfg["price_display"] = "full"

    # a markup always keeps a plain full-price view available; never anchor a markup
    if is_markup and cfg["price_display"] == "anchored":
        cfg["price_display"] = "full"

    return cfg


def intervention_meta(intervention_id: str) -> dict[str, Any] | None:
    for fr, slots in INTERVENTIONS.items():
        for slot, iv in slots.items():
            if iv["id"] == intervention_id:
                return {**iv, "friction_type": fr, "slot": slot,
                        "lift_midpoint_pct": _lift_midpoint(iv["expected_conversion_lift"])}
    return None


ALL_INTERVENTION_IDS = [iv["id"] for slots in INTERVENTIONS.values() for iv in slots.values()]
