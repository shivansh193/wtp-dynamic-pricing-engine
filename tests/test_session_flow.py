"""Link-generator demo flow: /session/create, /personalize link-up, /sessions/all,
/segment/stats, and the /ws/sessions broadcast."""

import sys

sys.path.insert(0, ".")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


SIG_KEYS = [
    "list_price", "device_type", "city_tier", "payment_method_preference",
    "return_rate", "cross_merchant_trust_score", "num_merchants_transacted",
    "account_age_days", "cod_completion_rate", "payment_success_rate",
    "income_tier", "pin_code",
]


def _personalize_payload(cfg, sid):
    return {**{k: cfg[k] for k in SIG_KEYS}, "ip": cfg["ip"], "session_id": sid}


def test_presets_produce_distinct_configs(client):
    hi = client.post("/session/create", json={"preset": "high"}).json()
    lo = client.post("/session/create", json={"preset": "low"}).json()
    assert hi["config"]["city_tier"] == 1 and hi["config"]["device_type"] == "iPhone"
    assert lo["config"]["city_tier"] == 3 and lo["config"]["payment_method_preference"] == "COD"
    assert hi["config"]["cross_merchant_trust_score"] > lo["config"]["cross_merchant_trust_score"]
    assert hi["qr_code_base64"].startswith("data:image/png;base64,")
    assert hi["customer_url"].endswith("/checkout/" + hi["session_id"])
    assert hi["merchant_url"].endswith("/merchant/" + hi["session_id"])
    assert hi["segment_key"] == "1|iPhone|Credit_Card"


def test_custom_pincode_autodetects_tier(client):
    r = client.post("/session/create", json={
        "preset": "custom",
        "custom": {"pin_code": "560001", "device_type": "iPhone",
                   "payment_method_preference": "UPI", "prepaid_orders": 25,
                   "return_rate": 0.09, "vpn": True},
    }).json()
    assert r["config"]["city_tier"] == 1          # 560xxx = Bengaluru
    assert r["config"]["ip_type"] == "vpn"


def test_session_lifecycle_pending_priced_converted(client):
    r = client.post("/session/create", json={"preset": "mid"}).json()
    sid, cfg = r["session_id"], r["config"]
    assert client.get(f"/session/{sid}").json()["status"] == "pending"

    pr = client.post("/personalize", json=_personalize_payload(cfg, sid)).json()
    got = client.get(f"/session/{sid}").json()
    assert got["status"] == "priced"
    assert got["price_shown"] == pr["final_price"]
    assert got["wtp_score"] == pr["wtp_multiplier"]
    assert got["result"]["offer_type"] == pr["offer_type"]

    done = client.post(f"/session/{sid}/complete").json()
    assert done["status"] == "converted"
    assert done["completed_at"]


def test_sessions_all_lists_created_sessions(client):
    before = client.get("/sessions/all").json()["count"]
    client.post("/session/create", json={"preset": "random"})
    after = client.get("/sessions/all").json()
    assert after["count"] == before + 1
    assert after["sessions"][0]["created_at"]  # newest first


def test_segment_stats_bayesian_posterior(client):
    # drive a few decisions into one segment
    r = client.post("/session/create", json={"preset": "high"}).json()
    for _ in range(3):
        client.post("/personalize", json=_personalize_payload(r["config"], None))
    s = client.get("/segment/stats/1|iPhone|Credit_Card").json()
    assert s["segment_key"] == "1|iPhone|Credit_Card"
    assert s["n_observations"] >= 3
    lo, hi = s["posterior"]["ci_95"]
    assert lo < s["posterior"]["mean_wtp"] < hi
    assert 0.85 <= s["posterior"]["mean_wtp"] <= 1.25
    assert len(s["conversion_curve"]) == 6


def test_ws_sessions_broadcasts_on_create(client):
    with client.websocket_connect("/ws/sessions") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        client.post("/session/create", json={"preset": "low"})
        msg = ws.receive_json()
        assert msg["type"] == "session.created"
        assert msg["session"]["preset"] == "low"
