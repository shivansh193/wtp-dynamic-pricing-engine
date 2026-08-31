"""
Friction-Aware Conversion Engine - Step 4: synthetic A/B test simulator.

`POST /simulate/ab_test` takes a segment definition + a sample size, builds a
synthetic cohort around that segment, randomly splits it 50/50, and runs:

  control    flat list price, no friction intervention
  treatment  WTP-adjusted price + the friction-aware intervention for each shopper

Per shopper we draw a Bernoulli conversion from a probability the models
produce (WTP estimator -> price -> conversion classifier), and for the
treatment arm we apply the primary intervention's expected relative uplift on
top. The endpoint reports conversion rate and revenue-per-visitor for each arm,
the lift, a two-proportion z-test p-value, a 95% CI on the conversion-rate lift,
and which interventions did the work.

Everything is deterministic given `seed`. No network, no DB - it's a
what-if tool the merchant runs before shipping a treatment.
"""

from __future__ import annotations

import math
import random
import time
from collections import Counter
from typing import Any

from . import _bootstrap  # noqa: F401
from .interventions import _lift_midpoint, build_checkout_config, intervention_meta
from .friction_engine import FrictionContext, classify_friction
from .merchant_config import get_config
from .pricing_engine import decide
from .presets import DEFAULT_SPLITS, PAYMENTS, derive_signals

from model.inference import get_model  # type: ignore

SAMPLE_MIN, SAMPLE_MAX, SAMPLE_DEFAULT = 200, 20_000, 2_500

# per-tier centres for the knobs the segment doesn't pin explicitly
_TIER_PREPAID = {1: 32, 2: 16, 3: 5}
_TIER_RETURN = {1: 0.06, 2: 0.13, 3: 0.28}
_TIER_DEVICE = {1: "iPhone", 2: "Android_premium", 3: "Android_budget"}


# --------------------------------------------------------------------------- #
# Normal CDF (no scipy dependency)
# --------------------------------------------------------------------------- #
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _two_proportion_z(x_c: int, n_c: int, x_t: int, n_t: int) -> dict[str, Any]:
    """Pooled two-proportion z-test for p_t - p_c, plus an unpooled Wald 95% CI
    on the absolute difference."""
    if n_c == 0 or n_t == 0:
        return {"z_stat": 0.0, "p_value": 1.0, "significant": False,
                "ci95_low": 0.0, "ci95_high": 0.0}
    p_c, p_t = x_c / n_c, x_t / n_t
    p_pool = (x_c + x_t) / (n_c + n_t)
    se_pool = math.sqrt(max(p_pool * (1 - p_pool) * (1 / n_c + 1 / n_t), 1e-12))
    z = (p_t - p_c) / se_pool
    p_value = 2.0 * (1.0 - _norm_cdf(abs(z)))
    se_un = math.sqrt(max(p_t * (1 - p_t) / n_t + p_c * (1 - p_c) / n_c, 1e-12))
    diff = p_t - p_c
    return {
        "z_stat": round(z, 4),
        "p_value": round(p_value, 6),
        "significant": bool(p_value < 0.05),
        "ci95_low": round(diff - 1.96 * se_un, 5),
        "ci95_high": round(diff + 1.96 * se_un, 5),
    }


# --------------------------------------------------------------------------- #
# Synthetic cohort
# --------------------------------------------------------------------------- #
def _jitter_split(base: dict[str, float], rng: random.Random) -> dict[str, float]:
    raw = {m: max(0.0, rng.gauss(base.get(m, 0.0), 0.06)) for m in PAYMENTS}
    s = sum(raw.values()) or 1.0
    return {m: round(v / s, 4) for m, v in raw.items()}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _resolve_segment(segment: dict[str, Any]) -> dict[str, Any]:
    seg = dict(segment or {})
    tier = int(seg.get("city_tier") or 2)
    if tier not in (1, 2, 3):
        tier = 2
    device = seg.get("device_type") or _TIER_DEVICE[tier]
    if seg.get("payment_split"):
        split_center = {m: float(seg["payment_split"].get(m, 0.0)) for m in PAYMENTS}
        tot = sum(split_center.values()) or 1.0
        split_center = {m: v / tot for m, v in split_center.items()}
    elif seg.get("payment_method_preference"):
        split_center = {m: (0.7 if m == seg["payment_method_preference"] else 0.075)
                        for m in PAYMENTS}
    else:
        split_center = dict(DEFAULT_SPLITS[tier])
    return {
        "city_tier": tier,
        "device_type": device,
        "split_center": split_center,
        "prepaid_orders_mean": float(seg.get("prepaid_orders", _TIER_PREPAID[tier])),
        "prepaid_orders_sd": float(seg.get("prepaid_orders_sd", 6.0)),
        "return_rate_mean": float(seg.get("return_rate", _TIER_RETURN[tier])),
        "return_rate_sd": float(seg.get("return_rate_sd", 0.05)),
        "vpn_rate": float(seg.get("vpn_rate", 0.05)),
        "list_price": float(seg.get("list_price", 4999)),
        "product_category": seg.get("product_category", "fashion"),
        "pin_code": seg.get("pin_code"),
    }


def _make_shopper(res: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    prepaid = int(_clamp(round(rng.gauss(res["prepaid_orders_mean"],
                                         res["prepaid_orders_sd"])), 0, 50))
    ret = round(_clamp(rng.gauss(res["return_rate_mean"], res["return_rate_sd"]),
                       0.0, 0.5), 4)
    vpn = rng.random() < res["vpn_rate"]
    split = _jitter_split(res["split_center"], rng)
    sig = derive_signals(
        city_tier=res["city_tier"],
        device_type=res["device_type"],
        payment_split=split,
        prepaid_orders=prepaid,
        return_rate=ret,
        vpn=vpn,
        pin_code=res["pin_code"],
    )
    sig["list_price"] = res["list_price"]
    sig["cart_value"] = res["list_price"]
    sig["product_category"] = res["product_category"]
    sig["historical_aov"] = sig.get("historical_aov") or res["list_price"]
    # cheap, deterministic context fill (the bulk path skips market_context)
    sig.setdefault("is_festival_period", False)
    sig.setdefault("festival_intensity", 0.0)
    sig.setdefault("digital_demand_index", 100.0)
    sig.setdefault("time_of_day", "evening")
    sig.setdefault("day_of_week", "weekday")
    return sig


def _proxy_conv(mult: float) -> float:
    """Logistic-ish fallback if the conversion classifier artifact is absent."""
    return float(_clamp(0.62 - 0.9 * (mult - 1.0), 0.03, 0.97))


def _friction_ctx(sig: dict) -> FrictionContext:
    psr = float(sig.get("payment_success_rate", 0.9) or 0.9)
    n_merch = int(sig.get("num_merchants_transacted", 5) or 5)
    cat = sig.get("product_category", "fashion")
    trust = float(sig.get("cross_merchant_trust_score", 55) or 55)
    cod = float(sig.get("cod_completion_rate", 0.85) or 0.85)
    return FrictionContext(
        cart_abandonment_rate=round(_clamp(1.0 - psr, 0.0, 1.0), 4),
        repeat_sessions_on_product=0,
        first_purchase_in_category=bool(n_merch <= 2 and cat in {"electronics", "home"}),
        session_minutes=0.0,
        cod_eligible=bool(trust > 55 and cod > 0.8),
    )


# --------------------------------------------------------------------------- #
# Simulator
# --------------------------------------------------------------------------- #
def simulate_ab_test(segment: dict[str, Any] | None,
                     sample_size: int = SAMPLE_DEFAULT,
                     *, seed: int | None = None) -> dict[str, Any]:
    t0 = time.perf_counter()
    n = int(_clamp(int(sample_size or SAMPLE_DEFAULT), SAMPLE_MIN, SAMPLE_MAX))
    seed = int(seed if seed is not None else 20260)
    rng = random.Random(seed)
    res = _resolve_segment(segment or {})
    mc = get_config()
    model = get_model()
    allowed_ids = mc.allowed_intervention_ids()
    cap_up, cap_down = mc.effective_caps()

    list_price = res["list_price"]
    arms = {"control": _Arm(), "treatment": _Arm()}
    interv_counter: Counter[str] = Counter()
    friction_counter: Counter[str] = Counter()
    markup_n = 0
    exp_conv = {"control": 0.0, "treatment": 0.0}

    # ---- 1. synthetic cohort + one vectorised model pass ----
    cohort = [_make_shopper(res, rng) for _ in range(n)]
    bulk = model.simulate_cohort(cohort, cap_up=cap_up, cap_down=cap_down)
    wtp_arr = bulk["wtp"]
    eff_arr = bulk["eff"]
    have_conv = bulk["conv_list"] is not None
    assign = [rng.random() < 0.5 for _ in range(n)]  # False=control, True=treatment
    draw = [rng.random() for _ in range(n)]

    # ---- 2. per-shopper arm assignment + friction-aware treatment ----
    for i, sig in enumerate(cohort):
        wtp = float(wtp_arr[i])
        conv_list = float(bulk["conv_list"][i]) if have_conv else _proxy_conv(1.0)

        if not assign[i]:  # control
            exp_conv["control"] += conv_list
            converted = draw[i] < conv_list
            arms["control"].add(converted, list_price if converted else 0.0)
            continue

        # ---- treatment: friction-aware ----
        base_p = float(bulk["conv_eff"][i]) if have_conv else _proxy_conv(float(eff_arr[i]))
        fr = classify_friction(sig, wtp_multiplier=wtp, context=_friction_ctx(sig))
        d = decide(
            list_price=list_price,
            wtp_multiplier=wtp,
            conversion_probability=base_p,
            customer_signals=sig,
            shap_top=[],
            model_confidence="medium",
            merchant_config=mc,
        )
        cfg = build_checkout_config(
            fr, sig, d, session_id=f"ab_{seed}_{i}",
            session_minutes=0.0, base_session_count=n,
            allowed_ids=allowed_ids,
        )
        prim = _lift_midpoint(cfg.get("expected_conversion_lift", "8-12%")) / 100.0
        sec_meta = cfg.get("secondary_intervention")
        m = intervention_meta(sec_meta) if sec_meta else None
        sec = (m["lift_midpoint_pct"] / 100.0) if m else 0.0
        uplift = min(1.0 + prim + 0.35 * sec, 1.45)
        p = float(_clamp(base_p * uplift, 0.001, 0.985))
        exp_conv["treatment"] += p
        converted = draw[i] < p
        arms["treatment"].add(converted, d.final_price if converted else 0.0)
        interv_counter[cfg["primary_intervention"]] += 1
        friction_counter[fr.primary] += 1
        if d.is_markup:
            markup_n += 1

    c, t = arms["control"], arms["treatment"]
    sig_stats = _two_proportion_z(c.conv, c.n, t.conv, t.n)

    cr_c = c.rate()
    cr_t = t.rate()
    rpv_c = c.rpv()
    rpv_t = t.rpv()
    top_iv = interv_counter.most_common(1)
    top_iv_id = top_iv[0][0] if top_iv else None
    top_iv_meta = intervention_meta(top_iv_id) if top_iv_id else None

    return {
        "segment": {
            "city_tier": res["city_tier"],
            "device_type": res["device_type"],
            "product_category": res["product_category"],
            "list_price": list_price,
            "payment_split_center": {k: round(v, 3) for k, v in
                                     res["split_center"].items()},
            "prepaid_orders_mean": res["prepaid_orders_mean"],
            "return_rate_mean": res["return_rate_mean"],
            "vpn_rate": res["vpn_rate"],
        },
        "sample_size": n,
        "seed": seed,
        "arms": {
            "control": {
                "label": "Flat list price, no intervention",
                "n": c.n, "conversions": c.conv,
                "conversion_rate": round(cr_c, 5),
                "expected_conversion_rate": round(exp_conv["control"] / max(c.n, 1), 5),
                "revenue": round(c.revenue, 2),
                "rpv": round(rpv_c, 2),
                "avg_price": round(list_price, 2),
            },
            "treatment": {
                "label": "WTP price + friction-aware intervention",
                "n": t.n, "conversions": t.conv,
                "conversion_rate": round(cr_t, 5),
                "expected_conversion_rate": round(exp_conv["treatment"] / max(t.n, 1), 5),
                "revenue": round(t.revenue, 2),
                "rpv": round(rpv_t, 2),
                "avg_price": round(t.avg_price(), 2),
                "markup_share": round(markup_n / max(t.n, 1), 4),
            },
        },
        "lift": {
            "conversion_rate_abs": round(cr_t - cr_c, 5),
            "conversion_rate_rel_pct": round(((cr_t - cr_c) / cr_c * 100.0)
                                             if cr_c else 0.0, 3),
            "rpv_abs": round(rpv_t - rpv_c, 2),
            "rpv_rel_pct": round(((rpv_t - rpv_c) / rpv_c * 100.0) if rpv_c else 0.0, 3),
        },
        "significance": {
            **sig_stats,
            "ci95_conversion_lift": [sig_stats["ci95_low"], sig_stats["ci95_high"]],
            "method": "pooled two-proportion z-test; 95% CI is unpooled Wald on "
                      "the absolute conversion-rate difference",
        },
        "top_intervention": (
            {
                "id": top_iv_id,
                "times_served": top_iv[0][1] if top_iv else 0,
                "share_of_treatment": round((top_iv[0][1] / max(t.n, 1))
                                            if top_iv else 0.0, 4),
                "display_component": (top_iv_meta or {}).get("display_component"),
                "expected_conversion_lift": (top_iv_meta or {}).get(
                    "expected_conversion_lift"),
                "psychological_mechanism": (top_iv_meta or {}).get(
                    "psychological_mechanism"),
            }
            if top_iv_id else None
        ),
        "intervention_mix": [
            {"id": k, "times_served": v,
             "share": round(v / max(t.n, 1), 4)}
            for k, v in interv_counter.most_common()
        ],
        "friction_mix": [
            {"type": k, "count": v, "share": round(v / max(t.n, 1), 4)}
            for k, v in friction_counter.most_common()
        ],
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
        "note": "Synthetic cohort. Conversion is a Bernoulli draw from the "
                "conversion classifier's probability at each arm's price; the "
                "treatment arm additionally applies the primary intervention's "
                "published relative uplift (secondary at 35% weight). "
                "'expected_*' rows are the pre-sampling analytic means. Treat "
                "this as a power/sizing tool, not a forecast.",
    }


class _Arm:
    __slots__ = ("n", "conv", "revenue", "_price_sum")

    def __init__(self) -> None:
        self.n = 0
        self.conv = 0
        self.revenue = 0.0
        self._price_sum = 0.0

    def add(self, converted: bool, revenue: float) -> None:
        self.n += 1
        self.conv += int(bool(converted))
        self.revenue += revenue
        self._price_sum += revenue if converted else 0.0

    def rate(self) -> float:
        return self.conv / self.n if self.n else 0.0

    def rpv(self) -> float:
        return self.revenue / self.n if self.n else 0.0

    def avg_price(self) -> float:
        return self._price_sum / self.conv if self.conv else 0.0
