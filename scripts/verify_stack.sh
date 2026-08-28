#!/usr/bin/env bash
# Verify the running docker-compose stack end to end.
# Usage: bash scripts/verify_stack.sh [API_PORT] [DASH_PORT] [PG_PORT]
set -uo pipefail

API="http://localhost:${1:-8000}"
DASH="http://localhost:${2:-3300}"
PGPORT="${3:-5442}"
PASS=0; FAIL=0
ok(){ echo "  PASS: $1"; PASS=$((PASS+1)); }
no(){ echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "== docker compose ps =="
docker compose ps

echo "== /health =="
H=$(curl -s "$API/health")
echo "$H" | grep -q '"status":"ok"' && ok "health ok" || no "health: $H"
echo "$H" | grep -q '"db_backend":"postgres"' && ok "db backend = postgres" || no "db backend not postgres: $H"
echo "$H" | grep -q '"model_loaded":true' && ok "model loaded" || no "model not loaded"
echo "$H" | grep -qE '"cache_backend":"redis"' && ok "cache backend = redis" || no "cache backend not redis: $H"

echo "== POST /personalize  (Customer A: iPhone/Tier1/CC/trust92) =="
A=$(curl -s -XPOST "$API/personalize" -H 'content-type: application/json' -d '{
 "list_price":4999,"device_type":"iPhone","city_tier":1,"payment_method_preference":"Credit_Card",
 "cross_merchant_trust_score":92,"account_age_days":1100,"return_rate":0.05,"cod_completion_rate":0.9,
 "payment_success_rate":0.98,"num_merchants_transacted":22,"ip":"49.36.128.5","session_id":"verifyA"}')
echo "$A" | python -c "import sys,json;d=json.load(sys.stdin);print('   ',d['final_price'],d['price_delta_pct'],d['offer_type'],d['latency_ms'],'ms')"
echo "$A" | grep -q '"budget_exceeded":false' && ok "A within latency budget" || no "A over budget: $A"
AF=$(echo "$A" | python -c "import sys,json;print(json.load(sys.stdin)['final_price'])")

echo "== POST /personalize  (Customer B: budgetAndroid/Tier3/COD/trust31/VPN) =="
B=$(curl -s -XPOST "$API/personalize" -H 'content-type: application/json' -d '{
 "list_price":4999,"device_type":"Android_budget","city_tier":3,"payment_method_preference":"COD",
 "cross_merchant_trust_score":31,"account_age_days":180,"return_rate":0.35,"cod_completion_rate":0.55,
 "payment_success_rate":0.82,"num_merchants_transacted":2,"ip":"146.70.0.5","session_id":"verifyB"}')
echo "$B" | python -c "import sys,json;d=json.load(sys.stdin);print('   ',d['final_price'],d['price_delta_pct'],d['offer_type'],'ip=',d['ip_enrichment']['ip_type'])"
BF=$(echo "$B" | python -c "import sys,json;print(json.load(sys.stdin)['final_price'])")
python -c "import sys; sys.exit(0 if $AF > $BF else 1)" && ok "A ($AF) priced above B ($BF)" || no "A not > B"

echo "== GET /decision/verifyA =="
D=$(curl -s "$API/decision/verifyA")
echo "$D" | grep -q '"decision_count"' && ok "decision log persisted" || no "no decision log: $D"
echo "$D" | grep -q 'shap_values' && ok "SHAP values in log" || no "no shap in log"

echo "== GET /metrics =="
M=$(curl -s "$API/metrics")
echo "$M" | grep -q 'revenue_lift_simulation' && ok "metrics revenue lift present" || no "metrics missing lift"
echo "$M" | python -c "import sys,json;d=json.load(sys.stdin);print('    decisions_logged=',d['decisions_logged'],' db=',d.get('db_backend'))"

echo "== POST /simulate =="
S=$(curl -s -XPOST "$API/simulate" -H 'content-type: application/json' -d '{"profile":{
 "list_price":4999,"device_type":"Android_budget","city_tier":3,"payment_method_preference":"COD",
 "cross_merchant_trust_score":31,"account_age_days":180,"ip":"146.70.0.5"}}')
echo "$S" | grep -q '"sensitivity"' && ok "simulate returns sensitivity sweep" || no "simulate broken: $S"

echo "== GET /enrich/185.220.101.1  (known Tor exit) =="
E=$(curl -s "$API/enrich/185.220.101.1")
echo "$E" | grep -q '"ip_type":"tor"' && ok "enrich detects Tor" || no "enrich tor failed: $E"

echo "== dashboard $DASH =="
DH=$(curl -s -o /dev/null -w '%{http_code}' "$DASH")
[ "$DH" = "200" ] && ok "dashboard HTTP 200" || no "dashboard HTTP $DH"
curl -s "$DASH" | grep -qi "WTP Dynamic Pricing Engine" && ok "dashboard serves our app" || no "dashboard content mismatch"

echo "== postgres row check (host port $PGPORT) =="
CNT=$(docker compose exec -T postgres psql -U wtp -d wtp -tAc "select count(*) from pricing_decisions" 2>/dev/null | tr -d '[:space:]')
[ -n "$CNT" ] && [ "$CNT" -ge 2 ] && ok "pricing_decisions has $CNT rows" || no "pricing_decisions rows=$CNT"

echo
echo "==================  $PASS passed, $FAIL failed  =================="
exit $FAIL
