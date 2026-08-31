"""
Friction-Aware Conversion Engine - unit tests (Step 8).

Covers: the friction classifier per archetype, intervention-library validity,
the COD split-payment math, the A/B simulator's statistics, and
build_checkout_config edge cases (markup never anchored, fatigue rotation,
merchant allow-list, urgency gating).
"""

import sys

sys.path.insert(0, ".")

import math  # noqa: E402

import pytest  # noqa: E402

from api.ab_test import _two_proportion_z, simulate_ab_test  # noqa: E402
from api.friction_engine import (  # noqa: E402
    FRICTION_TYPES,
    FrictionContext,
    classify_friction,
)
from api.interventions import (  # noqa: E402
    ALL_INTERVENTION_IDS,
    INTERVENTIONS,
    build_checkout_config,
    cod_split,
    _lift_midpoint,
)
from api.pricing_engine import decide  # noqa: E402


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _base_signals(**over):
    s = dict(
        list_price=4999, cart_value=4999, historical_aov=4999,
        product_category="fashion", city_tier=2, device_type="Android_premium",
        payment_method_preference="UPI",
        payment_split={"UPI": 0.6, "Credit_Card": 0.2, "Debit_Card": 0.1,
                       "COD": 0.05, "Wallet": 0.05},
        return_rate=0.12, payment_success_rate=0.93, cod_completion_rate=0.88,
        cross_merchant_trust_score=58, num_merchants_transacted=6,
        account_age_days=400, ip_type="residential", ip_trust_multiplier=0.9,
        time_of_day="evening",
    )
    s.update(over)
    return s


def _decision(signals, wtp):
    return decide(list_price=signals["list_price"], wtp_multiplier=wtp,
                  conversion_probability=0.5, customer_signals=signals,
                  shap_top=[], model_confidence="medium")


# --------------------------------------------------------------------------- #
# 1. friction classifier per archetype
# --------------------------------------------------------------------------- #
ARCHETYPES = {
    "price_sensitivity": (
        _base_signals(city_tier=3, device_type="Android_budget", return_rate=0.34,
                      historical_aov=900, cross_merchant_trust_score=40,
                      payment_method_preference="COD",
                      payment_split={"UPI": 0.3, "COD": 0.6, "Debit_Card": 0.1,
                                     "Credit_Card": 0.0, "Wallet": 0.0}),
        0.90,
    ),
    "trust_deficit": (
        _base_signals(account_age_days=20, cross_merchant_trust_score=12,
                      ip_type="vpn", ip_trust_multiplier=0.35,
                      num_merchants_transacted=1),
        1.0,
    ),
    "payment_friction": (
        _base_signals(city_tier=3, payment_method_preference="COD",
                      cod_completion_rate=0.5, cross_merchant_trust_score=35,
                      payment_split={"UPI": 0.2, "COD": 0.7, "Debit_Card": 0.1,
                                     "Credit_Card": 0.0, "Wallet": 0.0}),
        1.02,
    ),
    "delivery_anxiety": (
        _base_signals(product_category="electronics", list_price=18999,
                      cart_value=18999, return_rate=0.33, city_tier=3,
                      num_merchants_transacted=1),
        1.0,
    ),
    "urgency_insensitive": (
        _base_signals(city_tier=1, device_type="iPhone",
                      cross_merchant_trust_score=88, num_merchants_transacted=18,
                      time_of_day="morning", account_age_days=1200,
                      payment_method_preference="Credit_Card",
                      payment_split={"Credit_Card": 0.6, "UPI": 0.3,
                                     "Debit_Card": 0.05, "COD": 0.0,
                                     "Wallet": 0.05}),
        1.18,
    ),
}


@pytest.mark.parametrize("expected,payload", [(k, v) for k, v in ARCHETYPES.items()])
def test_classifier_names_the_archetype(expected, payload):
    signals, wtp = payload
    res = classify_friction(signals, wtp_multiplier=wtp)
    # the intended friction must be the top call or a close second
    assert expected in (res.primary, res.secondary), (
        f"{expected}: got primary={res.primary} secondary={res.secondary} "
        f"scores={ {k: round(x, 2) for k, x in res.scores.items()} }"
    )
    assert 0.0 <= res.confidence <= 1.0
    assert set(res.scores) == set(FRICTION_TYPES)
    assert math.isclose(sum(res.scores.values()), 1.0, abs_tol=1e-6)


def test_decision_paralysis_needs_context():
    """On-the-fence WTP + cart abandonment + repeat visits -> decision_paralysis."""
    signals = _base_signals()
    ctx = FrictionContext(cart_abandonment_rate=0.8, repeat_sessions_on_product=3,
                          session_minutes=6.0)
    res = classify_friction(signals, wtp_multiplier=1.0, context=ctx)
    assert "decision_paralysis" in (res.primary, res.secondary)


def test_classifier_is_deterministic():
    s = _base_signals(city_tier=3, return_rate=0.3)
    a = classify_friction(s, wtp_multiplier=0.92)
    b = classify_friction(s, wtp_multiplier=0.92)
    assert a.primary == b.primary and a.scores == b.scores


# --------------------------------------------------------------------------- #
# 2. intervention library validity
# --------------------------------------------------------------------------- #
def test_intervention_library_shape():
    seen_ids = []
    for ftype in FRICTION_TYPES:
        assert ftype in INTERVENTIONS, f"no interventions for {ftype}"
        slots = INTERVENTIONS[ftype]
        assert set(slots) == {"primary", "secondary", "tertiary"}
        for slot, iv in slots.items():
            for key in ("id", "display_component", "copy",
                        "psychological_mechanism", "expected_conversion_lift"):
                assert iv.get(key) is not None, f"{ftype}.{slot} missing {key}"
            assert iv["psychological_mechanism"].strip()
            lo, hi = iv["expected_conversion_lift"].replace("%", "").split("-")
            assert 0 < float(lo) <= float(hi) < 100
            assert 0 < _lift_midpoint(iv["expected_conversion_lift"]) < 100
            seen_ids.append(iv["id"])
    assert len(seen_ids) == len(set(seen_ids)), "duplicate intervention id"
    assert sorted(seen_ids) == sorted(ALL_INTERVENTION_IDS)


# --------------------------------------------------------------------------- #
# 3. COD split-payment math
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("trust", [0, 10, 40, 55, 70, 100])
def test_cod_split_bounds_and_monotonicity(trust):
    sp = cod_split(4999, trust)
    assert 10 <= sp["upfront_pct"] <= 30
    assert sp["upfront_pct"] + sp["on_delivery_pct"] == 100


def test_cod_split_lower_trust_prepays_more():
    assert cod_split(4999, 20)["upfront_pct"] >= cod_split(4999, 80)["upfront_pct"]
    # a mid-trust shopper sits strictly between the extremes or at a bound
    assert cod_split(4999, 45)["upfront_pct"] >= cod_split(4999, 65)["upfront_pct"]


# --------------------------------------------------------------------------- #
# 4. A/B simulator statistics
# --------------------------------------------------------------------------- #
def test_two_proportion_z_no_effect():
    st = _two_proportion_z(100, 500, 100, 500)
    assert abs(st["z_stat"]) < 1e-6
    assert st["p_value"] > 0.99
    assert not st["significant"]
    assert st["ci95_low"] <= 0 <= st["ci95_high"]


def test_two_proportion_z_strong_effect():
    st = _two_proportion_z(100, 500, 250, 500)   # 20% vs 50%
    assert st["z_stat"] > 5
    assert st["p_value"] < 1e-6
    assert st["significant"]
    assert st["ci95_low"] > 0


def test_ab_sim_structure_and_determinism():
    seg = {"city_tier": 3, "device_type": "Android_budget", "return_rate": 0.3}
    a = simulate_ab_test(seg, 600, seed=123)
    b = simulate_ab_test(seg, 600, seed=123)

    assert a["arms"]["control"]["n"] + a["arms"]["treatment"]["n"] == a["sample_size"] == 600
    # ~50/50 split
    assert abs(a["arms"]["control"]["n"] - 300) < 60
    for arm in ("control", "treatment"):
        cr = a["arms"][arm]["conversion_rate"]
        assert 0.0 <= cr <= 1.0
        assert a["arms"][arm]["rpv"] >= 0.0
    sig = a["significance"]
    assert 0.0 <= sig["p_value"] <= 1.0
    assert sig["ci95_conversion_lift"][0] <= sig["ci95_conversion_lift"][1]
    # deterministic given the seed
    assert a["arms"] == b["arms"] and a["significance"] == b["significance"]
    # the friction/intervention mix shares sum to ~1 over the treatment arm
    assert abs(sum(f["share"] for f in a["friction_mix"]) - 1.0) < 0.02
    if a["top_intervention"]:
        assert a["top_intervention"]["id"] in ALL_INTERVENTION_IDS


def test_ab_sim_seed_changes_draw():
    seg = {"city_tier": 2}
    a = simulate_ab_test(seg, 600, seed=1)
    b = simulate_ab_test(seg, 600, seed=2)
    assert a["arms"]["treatment"]["conversions"] != b["arms"]["treatment"]["conversions"]


# --------------------------------------------------------------------------- #
# 5. build_checkout_config edge cases
# --------------------------------------------------------------------------- #
_CFG_KEYS = {
    "friction_type", "friction_secondary", "friction_confidence", "friction_drivers",
    "primary_intervention", "secondary_intervention", "psychological_mechanism",
    "price_display", "final_price", "list_price", "is_markup", "emi_amount",
    "emi_months", "anchor_price", "trust_badges", "payment_method_order",
    "cod_split_offer", "urgency_message", "urgency_min_seconds", "delivery_promise",
    "social_proof_count", "social_proof_live", "review_snippet", "price_lock_expiry",
    "quality_signal", "premium_note", "exclusivity_note", "expected_conversion_lift",
    "offer_headline",
}


@pytest.mark.parametrize("expected,payload", [(k, v) for k, v in ARCHETYPES.items()])
def test_checkout_config_has_all_keys(expected, payload):
    signals, wtp = payload
    fr = classify_friction(signals, wtp_multiplier=wtp)
    cfg = build_checkout_config(fr, signals, _decision(signals, wtp),
                                session_id="t_cfg")
    assert _CFG_KEYS.issubset(cfg.keys())
    assert cfg["price_display"] in {"full", "emi", "anchored"}
    assert cfg["primary_intervention"] in ALL_INTERVENTION_IDS
    assert isinstance(cfg["trust_badges"], list)


def test_markup_never_anchored():
    signals = ARCHETYPES["urgency_insensitive"][0]
    d = _decision(signals, 1.20)               # well above list -> capped markup
    assert d.is_markup
    fr = classify_friction(signals, wtp_multiplier=1.20)
    cfg = build_checkout_config(fr, signals, d, session_id="t_markup")
    assert cfg["is_markup"] and cfg["price_display"] != "anchored"


def test_price_sensitivity_shows_emi_and_anchor():
    signals, wtp = ARCHETYPES["price_sensitivity"]
    fr = classify_friction(signals, wtp_multiplier=wtp)
    assert fr.primary == "price_sensitivity"
    d = _decision(signals, wtp)
    cfg = build_checkout_config(fr, signals, d, session_id="t_emi")
    assert cfg["price_display"] == "emi"
    assert cfg["emi_amount"] and cfg["emi_amount"] > 0
    assert cfg["emi_months"] == 12
    assert cfg["anchor_price"] and cfg["anchor_price"] > cfg["final_price"]


def test_fatigue_rotates_primary_intervention():
    signals, wtp = ARCHETYPES["price_sensitivity"]
    fr = classify_friction(signals, wtp_multiplier=wtp)
    d = _decision(signals, wtp)
    fresh = build_checkout_config(fr, signals, d, session_id="t_fat")
    fatigued = {fresh["primary_intervention"]}
    rotated = build_checkout_config(fr, signals, d, session_id="t_fat",
                                    fatigued_intervention_ids=fatigued)
    assert rotated["primary_intervention"] not in fatigued


def test_allow_list_excludes_disabled_intervention():
    signals, wtp = ARCHETYPES["price_sensitivity"]
    fr = classify_friction(signals, wtp_multiplier=wtp)
    d = _decision(signals, wtp)
    full = build_checkout_config(fr, signals, d, session_id="t_allow")
    banned = full["primary_intervention"]
    allowed = set(ALL_INTERVENTION_IDS) - {banned}
    limited = build_checkout_config(fr, signals, d, session_id="t_allow",
                                    allowed_ids=allowed)
    assert limited["primary_intervention"] != banned


def test_urgency_never_on_first_load():
    signals = _base_signals()
    ctx = FrictionContext(cart_abandonment_rate=0.7, repeat_sessions_on_product=3)
    fr = classify_friction(signals, wtp_multiplier=1.0, context=ctx)
    d = _decision(signals, 1.0)
    cfg0 = build_checkout_config(fr, signals, d, session_id="t_urg",
                                 session_minutes=0.0)
    assert cfg0["urgency_message"] is None
    assert cfg0["urgency_min_seconds"] == 180
