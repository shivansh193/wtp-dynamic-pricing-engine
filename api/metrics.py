"""
Aggregate analytics for GET /metrics.

Reads the decision log (Postgres or the in-memory fallback) and computes:
  - avg WTP multiplier by segment (city_tier | device | payment pref)
  - conversion rate by offer type
  - revenue-lift simulation: expected revenue with WTP pricing vs flat pricing
  - top 5 features driving WTP (mean |SHAP| over recent decisions)
  - VPN / datacenter / Tor traffic share
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any


def _get_shap(row: dict) -> dict:
    v = row.get("shap_values")
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:  # noqa: BLE001
            return {}
    return v or {}


def _get_signals(row: dict) -> dict:
    v = row.get("input_signals")
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:  # noqa: BLE001
            return {}
    return v or {}


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def compute_metrics(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"decisions_logged": 0, "note": "no decisions yet - call POST /personalize"}

    # ---- avg WTP by segment ----
    seg_wtp: dict[str, list[float]] = defaultdict(list)
    by_tier: dict[str, list[float]] = defaultdict(list)
    by_device: dict[str, list[float]] = defaultdict(list)
    by_pay: dict[str, list[float]] = defaultdict(list)

    # ---- conversion rate by offer type + revenue/margin lift ----
    offer_conv: dict[str, list[float]] = defaultdict(list)
    rev_wtp = 0.0
    rev_flat = 0.0
    mgn_wtp = 0.0
    mgn_flat = 0.0
    try:
        from .config import settings as _s

        GROSS_MARGIN = _s.GROSS_MARGIN
    except Exception:  # noqa: BLE001
        GROSS_MARGIN = 0.45

    # ---- shap aggregation ----
    shap_accum: dict[str, list[float]] = defaultdict(list)

    # ---- ip mix ----
    ip_counts: dict[str, int] = defaultdict(int)

    for r in rows:
        sig = _get_signals(r)
        wtp = _f(r.get("wtp_score"))
        tier = str(sig.get("city_tier", "?"))
        device = str(sig.get("device_type", "?"))
        pay = str(sig.get("payment_method_preference", "?"))
        seg = f"tier{tier}|{device}|{pay}"
        seg_wtp[seg].append(wtp)
        by_tier[f"tier_{tier}"].append(wtp)
        by_device[device].append(wtp)
        by_pay[pay].append(wtp)

        offer = r.get("offer_type", "none")
        shap = _get_shap(r)
        c_adj = _f(shap.get("conversion_at_adjusted"), None if shap.get("conversion_at_adjusted") is None else 0.0)
        c_list = shap.get("conversion_at_list")
        c_adj_v = _f(shap.get("conversion_at_adjusted"))
        c_list_v = _f(c_list) if c_list is not None else c_adj_v
        offer_conv[offer].append(c_adj_v)

        final_price = _f(r.get("final_price"))
        list_price = _f(r.get("list_price"))
        # expected revenue per checkout impression = price * P(convert at that price)
        rev_wtp += final_price * c_adj_v
        rev_flat += list_price * c_list_v
        # expected gross margin: COGS is unchanged by the price we charge
        cogs = list_price * (1.0 - GROSS_MARGIN)
        mgn_wtp += (final_price - cogs) * c_adj_v
        mgn_flat += (list_price - cogs) * c_list_v

        for item in shap.get("all", []) or shap.get("top", []) or []:
            if isinstance(item, dict) and "feature" in item:
                shap_accum[item["feature"]].append(abs(_f(item.get("shap"))))

        ip_counts[str(r.get("ip_type", "unknown"))] += 1

    def _avg(d: dict[str, list[float]]) -> dict[str, float]:
        return {k: round(sum(v) / len(v), 4) for k, v in d.items() if v}

    top_segments = sorted(_avg(seg_wtp).items(), key=lambda kv: kv[1], reverse=True)

    shap_rank = sorted(
        ({"feature": k, "mean_abs_shap": round(sum(v) / len(v), 5), "n": len(v)}
         for k, v in shap_accum.items() if v),
        key=lambda d: d["mean_abs_shap"], reverse=True,
    )

    vpn_dc = sum(ip_counts.get(t, 0) for t in ("vpn", "datacenter", "tor"))

    lift_abs = rev_wtp - rev_flat
    lift_pct = (lift_abs / rev_flat * 100.0) if rev_flat else 0.0
    mgn_lift_abs = mgn_wtp - mgn_flat
    mgn_lift_pct = (mgn_lift_abs / mgn_flat * 100.0) if mgn_flat else 0.0

    return {
        "decisions_logged": n,
        "avg_wtp_by_segment": {
            "top_10": [{"segment": s, "avg_wtp": w} for s, w in top_segments[:10]],
            "by_city_tier": _avg(by_tier),
            "by_device": _avg(by_device),
            "by_payment_pref": _avg(by_pay),
        },
        "conversion_rate_by_offer_type": {
            k: round(sum(v) / len(v), 4) for k, v in offer_conv.items() if v
        },
        "revenue_lift_simulation": {
            "expected_revenue_wtp_pricing": round(rev_wtp, 2),
            "expected_revenue_flat_pricing": round(rev_flat, 2),
            "revenue_pct_lift": round(lift_pct, 3),
            "gross_margin_assumption": GROSS_MARGIN,
            "expected_margin_wtp_pricing": round(mgn_wtp, 2),
            "expected_margin_flat_pricing": round(mgn_flat, 2),
            "margin_absolute_lift": round(mgn_lift_abs, 2),
            "pct_lift": round(mgn_lift_pct, 3),
            "absolute_lift": round(mgn_lift_abs, 2),
            "n_decisions": n,
            "basis": "per impression: value x P(convert at that price), over logged decisions",
            "caveat": f"headline pct_lift is on GROSS MARGIN (assumes "
                      f"{GROSS_MARGIN:.0%} margin, COGS unchanged by price). A markup "
                      f"keeps its extra rupees even when a few price-sensitive buyers "
                      f"drop, so a premium segment can show flat/negative revenue lift "
                      f"but clearly positive margin lift. Assumes the conversion model "
                      f"is calibrated; ignores repeat-purchase/LTV. Sensitive to sample "
                      f"size + traffic mix - directional, not a production estimate.",
        },
        "top_features_driving_wtp": shap_rank[:5],
        "traffic_quality": {
            "ip_type_counts": dict(ip_counts),
            "vpn_datacenter_tor_share_pct": round(100.0 * vpn_dc / n, 2),
        },
    }
