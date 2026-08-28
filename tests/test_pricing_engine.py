"""Unit tests for the deterministic pricing decision engine (Step 5)."""

import sys

sys.path.insert(0, ".")

from api.pricing_engine import decide, PRICE_CAP_DOWN, PRICE_CAP_UP  # noqa: E402


HIGH_TRUST = dict(cross_merchant_trust_score=90, cod_completion_rate=0.95,
                  payment_method_preference="Credit_Card", ip_type="residential")
LOW_TRUST = dict(cross_merchant_trust_score=30, cod_completion_rate=0.55,
                 payment_method_preference="COD", ip_type="vpn")

SHAP = [
    {"feature": "device_type", "value": "iPhone", "shap": 0.07},
    {"feature": "city_tier", "value": 1, "shap": 0.05},
]


def test_price_capped_up():
    d = decide(list_price=1000, wtp_multiplier=1.40, conversion_probability=0.8,
               customer_signals=HIGH_TRUST, shap_top=SHAP, model_confidence="high")
    assert d.final_price == 1000 * (1 + PRICE_CAP_UP)
    assert d.effective_multiplier == 1 + PRICE_CAP_UP
    assert d.caps_applied and "capped" in d.caps_applied[0]
    assert d.price_delta_pct == 15.0


def test_price_floored_down():
    d = decide(list_price=1000, wtp_multiplier=0.70, conversion_probability=0.5,
               customer_signals=LOW_TRUST, shap_top=SHAP, model_confidence="high")
    assert d.final_price == round(1000 * (1 + PRICE_CAP_DOWN), 2)
    assert d.price_delta_pct == -10.0


def test_offer_premium_for_high_wtp():
    d = decide(list_price=4999, wtp_multiplier=1.12, conversion_probability=0.7,
               customer_signals=HIGH_TRUST, shap_top=SHAP, model_confidence="high")
    assert d.offer_type in {"extended_warranty", "priority_support"}
    # high WTP leads with credit card
    assert d.payment_methods_shown[0] in {"Credit_Card", "UPI"}


def test_offer_discount_for_low_wtp():
    d = decide(list_price=4999, wtp_multiplier=0.90, conversion_probability=0.35,
               customer_signals=LOW_TRUST, shap_top=SHAP, model_confidence="medium")
    assert d.offer_type in {"free_delivery", "cashback_5pct"}
    assert d.payment_methods_shown[0] in {"UPI", "COD"}


def test_cod_and_refund_eligibility_thresholds():
    ok = decide(list_price=1000, wtp_multiplier=1.0, conversion_probability=0.6,
                customer_signals=dict(cross_merchant_trust_score=85, cod_completion_rate=0.9),
                shap_top=SHAP)
    assert ok.cod_eligible is True
    assert ok.instant_refund_eligible is True

    borderline = decide(list_price=1000, wtp_multiplier=1.0, conversion_probability=0.6,
                        customer_signals=dict(cross_merchant_trust_score=61,
                                              cod_completion_rate=0.79),
                        shap_top=SHAP)
    assert borderline.cod_eligible is False       # cod rate 0.79 < 0.80
    assert borderline.instant_refund_eligible is False  # trust 61 < 80


def test_determinism():
    args = dict(list_price=2999, wtp_multiplier=1.05, conversion_probability=0.55,
                customer_signals=HIGH_TRUST, shap_top=SHAP, model_confidence="high")
    a = decide(**args).to_dict()
    b = decide(**args).to_dict()
    a.pop("latency_ms"); b.pop("latency_ms")
    assert a == b


def test_reasoning_references_top_two_shap_features():
    d = decide(list_price=4999, wtp_multiplier=1.10, conversion_probability=0.7,
               customer_signals=HIGH_TRUST, shap_top=SHAP, model_confidence="high")
    assert "device type" in d.reasoning
    assert "city tier" in d.reasoning
