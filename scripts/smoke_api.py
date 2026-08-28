"""End-to-end smoke test for the pricing API (no external services needed)."""

import json
import sys

sys.path.insert(0, ".")
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402

A = dict(list_price=4999, product_category="fashion", device_type="iPhone", city_tier=1,
         payment_method_preference="Credit_Card", cross_merchant_trust_score=92,
         account_age_days=1100, return_rate=0.05, cod_completion_rate=0.9,
         payment_success_rate=0.98, num_merchants_transacted=22, ip="49.36.128.5",
         referral_source="organic", session_id="demoA")
B = dict(list_price=4999, product_category="fashion", device_type="Android_budget", city_tier=3,
         payment_method_preference="COD", cross_merchant_trust_score=31, account_age_days=180,
         return_rate=0.35, cod_completion_rate=0.6, payment_success_rate=0.82,
         num_merchants_transacted=2, ip="146.70.0.5", referral_source="social", session_id="demoB")

out = []
with TestClient(app) as c:
    h = c.get("/health").json()
    out.append(("health", h))
    for name, p in (("A", A), ("B", B)):
        r = c.post("/personalize", json=p)
        out.append((f"personalize_{name}_status", r.status_code))
        out.append((f"personalize_{name}", r.json()))
    out.append(("metrics", c.get("/metrics").json()))
    out.append(("decision_demoA", c.get("/decision/demoA").json()))
    s = c.post("/simulate", json={"profile": B})
    out.append(("simulate_status", s.status_code))
    out.append(("simulate", s.json()))
    # enrich sub-router
    out.append(("enrich_vpn", c.get("/enrich/146.70.0.5").json()))
    out.append(("enrich_health", c.get("/enrich/health").json()))

with open("scripts/smoke_output.json", "w", encoding="utf-8") as fh:
    json.dump({k: v for k, v in out}, fh, indent=2, default=str)

# concise console summary (ascii only)
def g(key):
    return dict(out)[key]

for name in ("A", "B"):
    r = g(f"personalize_{name}")
    print(f"Customer {name}: list={r['list_price']} final={r['final_price']} "
          f"delta={r['price_delta_pct']}% wtp={r['wtp_multiplier']} "
          f"conv={r['conversion_probability']} offer={r['offer_type']} "
          f"cod={r['cod_eligible']} refund={r['instant_refund_eligible']} conf={r['confidence']}")
    r_ip = r["ip_enrichment"]
    print(f"   ip={r_ip['ip_type']} mult={r_ip['ip_trust_multiplier']} wl={r_ip['is_whitelisted']} "
          f"blk={r_ip['blocklist_hits']}")
    print(f"   pay={r['payment_methods_shown']}")
    print(f"   shap_top={[(s['feature'], s['value'], round(s['shap'], 3)) for s in r['shap_top'][:3]]}")
    print(f"   latency_ms={r['latency_ms']} breakdown={r['timing_breakdown']}")
    print(f"   reasoning={r['reasoning']}")

m = g("metrics")
print("\nmetrics.decisions_logged =", m["decisions_logged"])
print("metrics.revenue_lift =", json.dumps(m["revenue_lift_simulation"]))
print("metrics.top_features =", [f["feature"] for f in m["top_features_driving_wtp"]])
print("metrics.traffic_quality =", json.dumps(m["traffic_quality"]))
d = g("decision_demoA")
print("\ndecision/demoA count =", d["decision_count"])
s = g("simulate")
print("simulate base final =", s["base"]["final_price"], " sensitivity rows =", len(s["sensitivity"]))
for cf in s["sensitivity"]:
    print(f"   {cf['feature']}={cf['value']} -> {cf['final_price']} (delta {cf['delta_vs_base_price']}) {cf['offer_type']}")
print("\nenrich_health =", json.dumps(g("enrich_health")))
print("OK - full output in scripts/smoke_output.json")
