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

    # ---- 5. deterministic pricing engine (respects merchant config) ----
    from .merchant_config import get_config

    decision = decide(
        list_price=payload.list_price,
        wtp_multiplier=wtp,
        conversion_probability=conv_adj,
        customer_signals=signals,
        shap_top=pred["shap_top"],
        model_confidence=pred["confidence"],
        merchant_config=get_config(),
        force_list_price=bool(getattr(payload, "force_list_price", False)),
    )

    total_ms = round((time.perf_counter() - t_start) * 1000, 3)
    timing = {
        "ip_enrichment_ms": ip_ms,
        "market_context_ms": ctx_ms,
        "wtp_model_ms": model_ms,
        "conversion_model_ms": conv_ms,
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
    }
    return response, db_record


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
