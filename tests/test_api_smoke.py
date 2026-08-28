"""End-to-end API smoke tests - no Postgres/Redis needed (both degrade)."""

import sys

sys.path.insert(0, ".")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


CUST_A = dict(list_price=4999, device_type="iPhone", city_tier=1,
              payment_method_preference="Credit_Card", cross_merchant_trust_score=92,
              account_age_days=1100, return_rate=0.05, cod_completion_rate=0.9,
              ip="49.36.128.5", session_id="pytestA")
CUST_B = dict(list_price=4999, device_type="Android_budget", city_tier=3,
              payment_method_preference="COD", cross_merchant_trust_score=31,
              account_age_days=180, return_rate=0.35, cod_completion_rate=0.55,
              ip="185.220.101.1", session_id="pytestB")


def test_health(client):
    j = client.get("/health").json()
    assert j["status"] == "ok"
    assert j["components"]["model_loaded"] is True


def test_personalize_high_vs_low_wtp(client):
    a = client.post("/personalize", json=CUST_A).json()
    b = client.post("/personalize", json=CUST_B).json()
    # high-trust premium profile priced above low-trust budget profile
    assert a["final_price"] > b["final_price"]
    assert a["wtp_multiplier"] > b["wtp_multiplier"]
    # price caps respected
    assert -10.01 <= a["price_delta_pct"] <= 15.01
    assert -10.01 <= b["price_delta_pct"] <= 15.01
    # offers differentiate
    assert a["offer_type"] in {"extended_warranty", "priority_support"}
    assert b["offer_type"] in {"free_delivery", "cashback_5pct"}
    # latency budget
    assert a["latency_ms"] < a["budget_ms"]
    # SHAP present
    assert len(a["shap_top"]) >= 2


def test_personalize_detects_tor_ip(client):
    b = client.post("/personalize", json=CUST_B).json()
    assert b["ip_enrichment"]["ip_type"] == "tor"
    assert b["ip_enrichment"]["ip_trust_multiplier"] == 0.30


def test_decision_log_roundtrip(client):
    client.post("/personalize", json=CUST_A)
    d = client.get("/decision/pytestA").json()
    assert d["decision_count"] >= 1
    assert "shap_values" in d["decisions"][0]


def test_metrics_shape(client):
    client.post("/personalize", json=CUST_A)
    client.post("/personalize", json=CUST_B)
    m = client.get("/metrics").json()
    assert m["decisions_logged"] >= 2
    assert "revenue_lift_simulation" in m
    assert "top_features_driving_wtp" in m


def test_simulate_counterfactuals(client):
    r = client.post("/simulate", json={"profile": CUST_B}).json()
    assert "base" in r and "sensitivity" in r
    feats = {c["feature"] for c in r["sensitivity"]}
    assert {"device_type", "city_tier", "payment_method_preference"} <= feats


def test_enrich_subrouter(client):
    j = client.get("/enrich/185.220.101.1").json()
    assert j["ip_type"] == "tor"
