"""
Friction-Aware Conversion Engine - Step 6: intervention performance tracker.

`GET /interventions/performance` aggregates the intervention_events log:

  - per intervention: times shown, conversion rate, revenue-per-shown, and how
    that conversion rate compares to the settled baseline
  - the most common frictions per product category
  - fatigue: (segment, intervention) pairs shown 3+ times without a conversion -
    the assembler rotates away from these

Works off Postgres or the in-memory event buffer - same row shape.
"""

from __future__ import annotations

import json
from typing import Any

from .interventions import intervention_meta

FATIGUE_THRESHOLD = 3


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _as_bool(x: Any) -> bool | None:
    if x is None:
        return None
    if isinstance(x, bool):
        return x
    if isinstance(x, str):
        return x.lower() in {"t", "true", "1", "yes"}
    return bool(x)


def compute_performance(events: list[dict]) -> dict:
    evs = [e for e in events if e and e.get("intervention_id")]
    n = len(evs)
    if not n:
        return {"n_events": 0, "n_settled": 0, "baseline_conversion": None,
                "by_intervention": [], "frictions_by_category": {},
                "fatigued_pairs": [], "note": "No interventions logged yet - "
                "run a few checkouts through the link-generator flow."}

    settled = [e for e in evs if _as_bool(e.get("converted")) is not None]
    won = [e for e in settled if _as_bool(e.get("converted"))]
    baseline = (len(won) / len(settled)) if settled else None

    # ---- per intervention ----
    buckets: dict[str, dict[str, Any]] = {}
    for e in evs:
        iid = e["intervention_id"]
        b = buckets.setdefault(iid, {"shown": 0, "settled": 0, "converted": 0,
                                     "revenue": 0.0, "slots": {}})
        b["shown"] += 1
        b["slots"][e.get("slot") or "?"] = b["slots"].get(e.get("slot") or "?", 0) + 1
        cv = _as_bool(e.get("converted"))
        if cv is not None:
            b["settled"] += 1
            if cv:
                b["converted"] += 1
                b["revenue"] += _f(e.get("final_price"))

    by_intervention = []
    for iid, b in sorted(buckets.items(), key=lambda kv: -kv[1]["shown"]):
        meta = intervention_meta(iid) or {}
        conv_rate = (b["converted"] / b["settled"]) if b["settled"] else None
        by_intervention.append({
            "intervention_id": iid,
            "friction_type": meta.get("friction_type"),
            "slot": max(b["slots"], key=b["slots"].get) if b["slots"] else None,
            "display_component": meta.get("display_component"),
            "times_shown": b["shown"],
            "times_settled": b["settled"],
            "conversions": b["converted"],
            "conversion_rate": None if conv_rate is None else round(conv_rate, 4),
            "revenue_per_shown": round(b["revenue"] / b["shown"], 2) if b["shown"] else 0.0,
            "lift_vs_baseline": (None if conv_rate is None or baseline is None
                                 else round(conv_rate - baseline, 4)),
            "library_expected_lift": meta.get("expected_conversion_lift"),
            "psychological_mechanism": meta.get("psychological_mechanism"),
        })

    # ---- frictions by merchant category ----
    cat_fric: dict[str, dict[str, int]] = {}
    for e in evs:
        if (e.get("slot") or "primary") != "primary":
            continue  # count each checkout once, at its primary
        cat = e.get("product_category") or "unknown"
        ft = e.get("friction_type") or "unknown"
        cat_fric.setdefault(cat, {})
        cat_fric[cat][ft] = cat_fric[cat].get(ft, 0) + 1
    frictions_by_category = {}
    for cat, fmap in cat_fric.items():
        tot = sum(fmap.values()) or 1
        frictions_by_category[cat] = [
            {"friction_type": ft, "count": c, "share": round(c / tot, 4)}
            for ft, c in sorted(fmap.items(), key=lambda kv: -kv[1])
        ]

    # ---- fatigue: (segment, intervention) shown >=3x, never converted ----
    pair: dict[tuple, dict[str, Any]] = {}
    for e in evs:
        key = (e.get("segment_key") or e.get("session_id") or "?",
               e["intervention_id"])
        p = pair.setdefault(key, {"shown": 0, "conversions": 0,
                                  "friction_type": e.get("friction_type")})
        p["shown"] += 1
        if _as_bool(e.get("converted")):
            p["conversions"] += 1
    fatigued_pairs = [
        {"segment_key": k[0], "intervention_id": k[1],
         "times_shown": v["shown"], "conversions": v["conversions"],
         "friction_type": v["friction_type"]}
        for k, v in sorted(pair.items(), key=lambda kv: -kv[1]["shown"])
        if v["shown"] >= FATIGUE_THRESHOLD and v["conversions"] == 0
    ]

    return {
        "n_events": n,
        "n_settled": len(settled),
        "baseline_conversion": None if baseline is None else round(baseline, 4),
        "by_intervention": by_intervention,
        "frictions_by_category": frictions_by_category,
        "fatigued_pairs": fatigued_pairs,
        "fatigue_threshold": FATIGUE_THRESHOLD,
        "note": "conversion_rate is over settled events only (session reached "
        "complete/abandon). revenue_per_shown divides won revenue by every "
        "impression. lift_vs_baseline compares to the settled-population "
        "conversion rate. A (segment, intervention) pair shown "
        f"{FATIGUE_THRESHOLD}+ times with zero conversions is flagged fatigued "
        "and rotated out by the checkout assembler.",
    }
