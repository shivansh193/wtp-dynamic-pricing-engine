"""
Orchestration for POST /personalize and POST /simulate.

    customer signals
        -> IP enrichment (cached, ~1-5ms)
        -> market context (festival / demand)
        -> WTP estimator + SHAP
        -> conversion probability (list vs adjusted)
        -> deterministic pricing engine
        -> response + DB log record

Each stage is timed; the sum is compared to LATENCY_BUDGET_MS by the caller.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from . import _bootstrap  # noqa: F401  (registers ip_enrichment + repo root)
from .context import market_context
from .logging_util import log
from .pricing_engine import decide
from .schemas import (
    CustomerSignals,
    FrictionBrief,
    IpEnrichmentBrief,
    PricingResponse,
    ShapFeature,
)

from ip_enrichment import get_service as get_ip_service  # type: ignore
from model.inference import get_model  # type: ignore


async def _enrich_ip(ip: str | None) -> tuple[IpEnrichmentBrief, float]:
    t0 = time.perf_counter()
    if not ip:
        return IpEnrichmentBrief(), round((time.perf_counter() - t0) * 1000, 3)
    try:
        svc = get_ip_service()
        if not svc.ready:
            await svc.startup()
        res = await svc.enrich(ip)
        brief = IpEnrichmentBrief(
            ip_type=res.ip_type,
            ip_trust_multiplier=res.ip_trust_multiplier,
            location_confidence=res.location_confidence,
            is_whitelisted=res.is_whitelisted,
            blocklist_hits=res.blocklist_hits,
            geo_source=res.geo_source,
            cache_hit=res.cache_hit,
            lookup_ms=res.lookup_ms,
        )
    except Exception as exc:  # noqa: BLE001
        log(f"ip enrichment failed for {ip!r}: {exc!r} -> unknown/0.8", level="WARN")
        brief = IpEnrichmentBrief()
    return brief, round((time.perf_counter() - t0) * 1000, 3)


def _apply_context(signals: dict[str, Any]) -> None:
    """Fill festival + demand features in place, unless the caller pre-set them."""
    from datetime import date

    d = signals.get("txn_date") or date.today().isoformat()
    is_fest, intensity = market_context.festival_lookup(d)
    signals.setdefault("is_festival_period", is_fest)
    signals.setdefault("festival_intensity", intensity)
    ym = f"{d[:7]}"
    signals.setdefault("digital_demand_index", market_context.demand_lookup(ym))


async def personalize(payload: CustomerSignals) -> tuple[PricingResponse, dict]:
    """Returns (response, db_log_record)."""
    t_start = time.perf_counter()
    session_id = payload.session_id or f"sess_{uuid.uuid4().hex[:16]}"
    signals = payload.model_signals()

    # a payment-method mix, if supplied, drives the checkout ordering + the
    # derived preference (argmax). Trust/COD signals are derived upstream by
    # /config/derive; here we just make the preference consistent with the mix.
    split = signals.get("payment_split")
    if isinstance(split, dict) and sum(v or 0 for v in split.values()) > 0:
        signals["payment_method_preference"] = max(split, key=lambda k: split.get(k, 0) or 0)

    # ---- 1. IP enrichment ----
    ip_brief, ip_ms = await _enrich_ip(payload.ip)
    # let enrichment override trust signals unless the caller pinned them
    if payload.ip_type is None:
        signals["ip_type"] = ip_brief.ip_type
    if payload.ip_trust_multiplier is None:
        signals["ip_trust_multiplier"] = ip_brief.ip_trust_multiplier
    # brief rule: VPN/DC/Tor traffic discounts the cross-merchant trust score
    if ip_brief.ip_type in {"vpn", "datacenter", "tor"} and not ip_brief.is_whitelisted:
        signals["cross_merchant_trust_score"] = round(
            signals["cross_merchant_trust_score"] * ip_brief.ip_trust_multiplier, 2
        )

    # ---- 2. market context ----
    t0 = time.perf_counter()
    _apply_context(signals)
    ctx_ms = round((time.perf_counter() - t0) * 1000, 3)

    # ---- 3. WTP estimator + SHAP ----
    model = get_model()
    t0 = time.perf_counter()
    pred = model.predict(signals)
    model_ms = round((time.perf_counter() - t0) * 1000, 3)

    # ---- 4. conversion probability at list vs adjusted ----
    t0 = time.perf_counter()
    wtp = pred["wtp_multiplier"]
    eff_guess = max(0.90, min(1.15, wtp))
    conv_adj = model.conversion_proba(signals, eff_guess)
    conv_list = model.conversion_proba(signals, 1.0)
    conv_ms = round((time.perf_counter() - t0) * 1000, 3)

    # ---- 5. friction classifier (after WTP, before the pricing decision) ----
    from .friction_engine import FrictionContext, classify_friction
    from .interventions import build_checkout_config
    from .merchant_config import get_config

    mc = get_config()
    t0 = time.perf_counter()
    fctx = await _friction_context(session_id, signals, trust=signals.get(
        "cross_merchant_trust_score", 55), cod_completion=signals.get(
        "cod_completion_rate", 0.85))
    friction = classify_friction(signals, wtp_multiplier=wtp, context=fctx)
    friction_ms = round((time.perf_counter() - t0) * 1000, 3)

    # ---- 6. deterministic pricing engine (respects merchant config) ----
    decision = decide(
        list_price=payload.list_price,
        wtp_multiplier=wtp,
        conversion_probability=conv_adj,
        customer_signals=signals,
        shap_top=pred["shap_top"],
        model_confidence=pred["confidence"],
        merchant_config=mc,
        force_list_price=bool(getattr(payload, "force_list_price", False)),
    )

    # ---- 7. dynamic checkout config from the detected friction ----
    seg_key = "|".join(str(signals.get(k, "?")) for k in
                       ("city_tier", "device_type", "payment_method_preference"))
    fatigued = await _fatigued_interventions(session_id, seg_key)
    checkout_config = build_checkout_config(
        friction, signals, decision,
        session_id=session_id,
        session_minutes=float(getattr(payload, "session_minutes", 0.0) or 0.0),
        base_session_count=await _session_count(),
        fatigued_intervention_ids=fatigued,
        allowed_ids=mc.allowed_intervention_ids(),
    )

    total_ms = round((time.perf_counter() - t_start) * 1000, 3)
    timing = {
        "ip_enrichment_ms": ip_ms,
        "market_context_ms": ctx_ms,
        "wtp_model_ms": model_ms,
        "conversion_model_ms": conv_ms,
        "friction_ms": friction_ms,
        "pricing_engine_ms": decision.latency_ms,
        "total_ms": total_ms,
    }

    response = PricingResponse(
        session_id=session_id,
        list_price=decision.list_price,
        final_price=decision.final_price,
        price_delta_pct=decision.price_delta_pct,
        effective_multiplier=decision.effective_multiplier,
        wtp_multiplier=decision.wtp_multiplier,
        conversion_probability=decision.conversion_probability,
        offer_type=decision.offer_type,
        offer_rationale=decision.offer_rationale,
        payment_methods_shown=decision.payment_methods_shown,
        cod_eligible=decision.cod_eligible,
        instant_refund_eligible=decision.instant_refund_eligible,
        reasoning=decision.reasoning,
        confidence=decision.confidence,
        shap_top=[ShapFeature(**s) for s in pred["shap_top"]],
        ip_enrichment=ip_brief,
        latency_ms=total_ms,
        budget_ms=0,          # filled by the endpoint (knows the setting)
        budget_exceeded=False,  # filled by the endpoint
        timing_breakdown=timing,
        offer_label=decision.offer_label,
        offer_value_inr=decision.offer_value_inr,
        is_markup=decision.is_markup,
        standard_price=decision.standard_price,
        net_vs_standard_inr=decision.net_vs_standard_inr,
        friction=FrictionBrief(
            primary=friction.primary,
            secondary=friction.secondary,
            confidence=friction.confidence,
            scores=friction.scores,
            drivers=friction.drivers,
            engine=friction.engine,
        ),
        checkout_config=checkout_config,
    )

    db_record = {
        "session_id": session_id,
        "input_signals": _jsonable(signals),
        "ip_address": payload.ip,
        "list_price": decision.list_price,
        "ip_type": ip_brief.ip_type,
        "ip_trust_multiplier": ip_brief.ip_trust_multiplier,
        "ip_is_whitelisted": ip_brief.is_whitelisted,
        "wtp_score": decision.wtp_multiplier,
        "conversion_probability": decision.conversion_probability,
        "model_confidence": decision.confidence,
        "shap_values": {
            "base_value": pred["shap_base_value"],
            "top": pred["shap_top"],
            "all": pred["shap_all"],
            "conversion_at_list": conv_list,
            "conversion_at_adjusted": conv_adj,
        },
        "final_price": decision.final_price,
        "price_delta_pct": decision.price_delta_pct,
        "offer_type": decision.offer_type,
        "payment_methods_shown": decision.payment_methods_shown,
        "cod_eligible": decision.cod_eligible,
        "instant_refund_eligible": decision.instant_refund_eligible,
        "reasoning": decision.reasoning,
        "latency_ms": total_ms,
        "budget_exceeded": False,
        "friction_type": friction.primary,
        "friction_secondary": friction.secondary,
        "friction_confidence": round(friction.confidence, 4),
        "primary_intervention": checkout_config.get("primary_intervention"),
        "secondary_intervention": checkout_config.get("secondary_intervention"),
        "checkout_config": _jsonable(checkout_config),
    }
    return response, db_record


# --------------------------------------------------------------------------- #
# Friction context helpers (session-history proxies)
# --------------------------------------------------------------------------- #
async def _all_sessions_safe() -> list[dict]:
    try:
        from .sessions import session_store

        return await session_store.all(limit=500)
    except Exception:  # noqa: BLE001
        return []


async def _session_count() -> int:
    return len(await _all_sessions_safe())


async def _friction_context(session_id: str, signals: dict, *, trust, cod_completion):
    from .friction_engine import FrictionContext

    rows = await _all_sessions_safe()
    seg = "|".join(str(signals.get(k, "?")) for k in
                   ("city_tier", "device_type", "payment_method_preference"))
    like = [r for r in rows if (r.get("segment_key") == seg)]
    abandoned = sum(1 for r in like if r.get("status") == "abandoned")
    repeats = max(0, len(like) - 1)
    abandonment_rate = (abandoned / len(like)) if like else 0.0
    n_merch = int(signals.get("num_merchants_transacted", 5) or 5)
    cat = signals.get("product_category", "fashion")
    return FrictionContext(
        cart_abandonment_rate=round(min(1.0, abandonment_rate + 0.15 * (
            1 - float(signals.get("payment_success_rate", 0.9) or 0.9))), 4),
        repeat_sessions_on_product=repeats,
        first_purchase_in_category=bool(n_merch <= 2 and cat in {"electronics", "home"}),
        session_minutes=0.0,
        cod_eligible=bool(float(trust or 55) > 55 and float(cod_completion or 0.85) > 0.8),
    )


async def _fatigued_interventions(session_id: str,
                                  segment_key: str | None = None) -> set[str]:
    """Intervention ids this 'customer' has already seen 3+ times without converting."""
    try:
        from .db import db

        return await db.fatigued_interventions(session_id, segment_key)
    except Exception:  # noqa: BLE001
        return set()


async def simulate(profile: CustomerSignals,
                   counterfactuals: dict[str, list[Any]] | None) -> tuple[PricingResponse, list]:
    """Base decision + one-feature-at-a-time counterfactual sweep."""
    base_resp, _ = await personalize(profile)

    cf = counterfactuals or {
        "device_type": ["Android_budget", "Android_premium", "iPhone", "Desktop"],
        "city_tier": [1, 2, 3],
        "payment_method_preference": ["UPI", "Credit_Card", "Debit_Card", "COD", "Wallet"],
    }

    out = []
    base_price = base_resp.final_price
    for feature, values in cf.items():
        for v in values:
            variant = profile.model_copy(update={feature: v})
            # keep the same session so logs group together in the demo
            variant.session_id = profile.session_id
            try:
                r, _ = await personalize(variant)
            except Exception as exc:  # noqa: BLE001
                log(f"counterfactual {feature}={v!r} failed: {exc!r}", level="WARN")
                continue
            out.append({
                "feature": feature,
                "value": v,
                "wtp_multiplier": r.wtp_multiplier,
                "final_price": r.final_price,
                "price_delta_pct": r.price_delta_pct,
                "offer_type": r.offer_type,
                "delta_vs_base_price": round(r.final_price - base_price, 2),
            })
    return base_resp, out


def _jsonable(d: dict) -> dict:
    """Drop values that aren't JSON-serialisable (defensive)."""
    import math

    clean = {}
    for k, v in d.items():
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            clean[k] = None
        else:
            clean[k] = v
    return clean
