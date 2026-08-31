"""
Friction-Aware Conversion Engine - Step 5: conversion funnel analysis.

`GET /funnel` turns the decision log into a four-stage checkout funnel

    page_load -> profile_submitted -> payment_selected -> order_confirmed

and attributes the drop-off at each step to the friction type the classifier
named for that shopper, plus the interventions that were (or would be) fighting
it there.

Only `order_confirmed` has a directly modelled number - the conversion
classifier's probability. The two intermediate stages use a transparent
retention model: a base pass-through rate per stage, adjusted by the shopper's
primary friction (scaled by the classifier's confidence). The intermediate
rates are then rescaled so the funnel's product still lands on the modelled
conversion probability - the shape is synthesised, the endpoint is real.

If the log is empty (fresh demo) the same math runs over a synthetic cohort
spanning the standard segments.
"""

from __future__ import annotations

import json
from typing import Any

STAGES = [
    ("page_load", "Page load"),
    ("profile_submitted", "Profile submitted"),
    ("payment_selected", "Payment method selected"),
    ("order_confirmed", "Order confirmed"),
]

# per-stage base pass-through + friction-specific deltas (applied * confidence)
_RETENTION = {
    "profile_submitted": {
        "base": 0.90,
        "trust_deficit": -0.24,
        "decision_paralysis": -0.22,
        "delivery_anxiety": -0.06,
        "urgency_insensitive": 0.04,
    },
    "payment_selected": {
        "base": 0.90,
        "payment_friction": -0.30,
        "price_sensitivity": -0.15,
        "delivery_anxiety": -0.08,
        "trust_deficit": -0.06,
    },
}

_STAGE_EXPLAINER = {
    "profile_submitted": "Shoppers who bounce before filling in their details - "
    "usually low trust or too many options to weigh.",
    "payment_selected": "Shoppers who reach payment but stall at the method step - "
    "preferred method missing/blocked, or the price gave them pause.",
    "order_confirmed": "Shoppers who had a payment method selected but didn't "
    "confirm - the last-mile conversion gap.",
}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _as_dict(v: Any) -> dict:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (ValueError, TypeError):
            return {}
    return v or {}


def _row_view(r: dict) -> dict:
    """Pull the handful of fields the funnel needs, tolerating both the
    in-memory record shape and asyncpg's json-as-text columns."""
    shap = _as_dict(r.get("shap_values"))
    conv = r.get("conversion_probability")
    if conv is None:
        conv = shap.get("conversion_at_adjusted") or shap.get("conversion_at_list")
    cfg = _as_dict(r.get("checkout_config"))
    return {
        "friction": r.get("friction_type") or cfg.get("friction_type") or "unknown",
        "confidence": float(r.get("friction_confidence")
                            or cfg.get("friction_confidence") or 0.5),
        "conv": _clamp(float(conv if conv is not None else 0.5), 0.02, 0.985),
        "primary_intervention": r.get("primary_intervention")
        or cfg.get("primary_intervention"),
    }


def _stage_rates(view: dict) -> tuple[float, float, float]:
    """(p2, p3, p4) - probability of advancing INTO profile_submitted,
    payment_selected, order_confirmed for this shopper."""
    ft, conf, conv = view["friction"], _clamp(view["confidence"], 0.0, 1.0), view["conv"]

    r2 = _RETENTION["profile_submitted"]
    p2 = _clamp(r2["base"] + r2.get(ft, 0.0) * conf, 0.40, 0.99)
    r3 = _RETENTION["payment_selected"]
    p3 = _clamp(r3["base"] + r3.get(ft, 0.0) * conf, 0.40, 0.99)
    # rescale the last leg so p2*p3*p4 == modelled conversion probability
    p4 = _clamp(conv / max(p2 * p3, 1e-3), 0.02, 0.99)
    return p2, p3, p4


def compute_funnel(rows: list[dict], *, synth_n: int = 1500) -> dict:
    views = [_row_view(r) for r in rows if r]
    source = "decision_log"
    if len(views) < 20:
        views += _synthetic_views(synth_n - len(views))
        source = "synthetic" if not rows else "decision_log+synthetic"

    n = len(views)
    if not n:
        return {"stages": [], "n": 0, "data_source": "none"}

    # cumulative reach + per-transition drop, bucketed by friction
    cum = [0.0, 0.0, 0.0, 0.0]          # expected count reaching each stage
    drop_by_friction: list[dict[str, float]] = [{}, {}, {}]   # 3 transitions
    drop_by_interv: list[dict[str, float]] = [{}, {}, {}]

    for v in views:
        p2, p3, p4 = _stage_rates(v)
        c = [1.0, p2, p2 * p3, p2 * p3 * p4]
        for k in range(4):
            cum[k] += c[k]
        ps = [p2, p3, p4]
        for t in range(3):
            d = c[t] - c[t + 1]
            if d <= 0:
                continue
            drop_by_friction[t][v["friction"]] = drop_by_friction[t].get(v["friction"], 0.0) + d
            iv = v["primary_intervention"] or "none"
            drop_by_interv[t][iv] = drop_by_interv[t].get(iv, 0.0) + d

    stages_out = []
    for k, (key, label) in enumerate(STAGES):
        entry = {
            "stage": key,
            "label": label,
            "reached": round(cum[k], 1),
            "reached_pct": round(cum[k] / n * 100.0, 2),
        }
        if k > 0:
            t = k - 1
            lost = cum[t] - cum[k]
            entry["dropoff"] = round(lost, 1)
            entry["dropoff_pct_of_prev"] = round(
                (lost / cum[t] * 100.0) if cum[t] else 0.0, 2)
            entry["dropoff_by_friction"] = _top_share(drop_by_friction[t], lost)
            entry["top_interventions"] = _top_share(drop_by_interv[t], lost, drop_none=True)
            entry["explainer"] = _STAGE_EXPLAINER.get(key, "")
        stages_out.append(entry)

    overall = cum[3] / n
    return {
        "stages": stages_out,
        "n": n,
        "data_source": source,
        "overall_conversion": round(overall, 4),
        "biggest_leak": _biggest_leak(stages_out),
        "note": "page_load = 100%. profile_submitted and payment_selected use a "
        "base per-stage retention adjusted by the shopper's primary friction "
        "(x classifier confidence); the final leg is rescaled so the funnel "
        "product equals the conversion model's probability. Drop-off is "
        "attributed to the friction type named for each shopper."
        + ("" if source == "decision_log"
           else "  Includes a synthetic cohort - the live log is still small."),
    }


def _top_share(d: dict[str, float], total: float, *, drop_none: bool = False,
               k: int = 5) -> list[dict]:
    items = [(name, v) for name, v in d.items() if not (drop_none and name == "none")]
    items.sort(key=lambda kv: -kv[1])
    out = []
    for name, v in items[:k]:
        out.append({
            "key": name,
            "count": round(v, 1),
            "share": round(v / total, 4) if total else 0.0,
        })
    return out


def _biggest_leak(stages: list[dict]) -> dict | None:
    worst = None
    for s in stages[1:]:
        if worst is None or s["dropoff"] > worst["dropoff"]:
            worst = s
    if not worst:
        return None
    top = (worst.get("dropoff_by_friction") or [{}])[0]
    return {
        "stage": worst["stage"],
        "label": worst["label"],
        "dropoff_pct_of_prev": worst["dropoff_pct_of_prev"],
        "leading_friction": top.get("key"),
        "leading_friction_share": top.get("share"),
    }


# --------------------------------------------------------------------------- #
# Synthetic fallback
# --------------------------------------------------------------------------- #
def _synthetic_views(n: int) -> list[dict]:
    if n <= 0:
        return []
    import random

    from .ab_test import _make_shopper, _resolve_segment
    from .friction_engine import classify_friction
    from .interventions import build_checkout_config
    from .merchant_config import get_config
    from .pricing_engine import decide
    from model.inference import get_model  # type: ignore

    rng = random.Random(4242)
    segs = [
        {"city_tier": 3, "device_type": "Android_budget", "return_rate": 0.30},
        {"city_tier": 2, "device_type": "Android_premium"},
        {"city_tier": 1, "device_type": "iPhone", "prepaid_orders": 40,
         "payment_method_preference": "Credit_Card"},
        {"city_tier": 2, "product_category": "electronics", "list_price": 16999},
    ]
    resolved = [_resolve_segment(s) for s in segs]
    model = get_model()
    mc = get_config()
    allowed = mc.allowed_intervention_ids()

    cohort, prices = [], []
    for i in range(n):
        res = resolved[i % len(resolved)]
        cohort.append(_make_shopper(res, rng))
        prices.append(res["list_price"])

    bulk = model.simulate_cohort(cohort)            # one vectorised pass
    wtp_arr, eff_arr = bulk["wtp"], bulk["eff"]
    have_conv = bulk["conv_eff"] is not None

    out: list[dict] = []
    for i, sig in enumerate(cohort):
        wtp = float(wtp_arr[i])
        conv = (float(bulk["conv_eff"][i]) if have_conv
                else _clamp(0.62 - 0.9 * (float(eff_arr[i]) - 1.0), 0.05, 0.95))
        fr = classify_friction(sig, wtp_multiplier=wtp)
        d = decide(list_price=prices[i], wtp_multiplier=wtp,
                   conversion_probability=conv, customer_signals=sig,
                   shap_top=[], model_confidence="medium", merchant_config=mc)
        cfg = build_checkout_config(fr, sig, d, session_id=f"synthfunnel_{i}",
                                    allowed_ids=allowed)
        out.append({
            "friction": fr.primary,
            "confidence": float(fr.confidence),
            "conv": _clamp(conv, 0.02, 0.985),
            "primary_intervention": cfg["primary_intervention"],
        })
    return out
