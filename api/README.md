# api - FastAPI pricing backend

The real-time layer that sits between a merchant checkout and Razorpay payment
initiation. Full request budget: **< 200 ms** (returns `503` if exceeded).

## Run

```bash
pip install -r ../requirements.txt
# needs data/processed/transactions.csv + model/artifacts/*.joblib
uvicorn api.main:app --port 8000 --reload
# open http://localhost:8000/docs
```

Postgres and Redis are **optional locally** — both degrade gracefully
(in-memory decision log, in-process cache). In Docker they are wired up.

## Endpoints

| method | path | purpose |
|---|---|---|
| `POST` | `/personalize` | full pricing decision for one checkout (IP enrichment → WTP model → pricing engine), logged to Postgres |
| `GET`  | `/metrics` | avg WTP by segment, conversion by offer type, **revenue-lift simulation**, top-5 WTP drivers, VPN/DC traffic share |
| `GET`  | `/decision/{session_id}` | full decision log incl. SHAP values for a session |
| `POST` | `/simulate` | base decision + counterfactual sweep (device / tier / payment method) |
| `GET`  | `/health` | component status (model, enrichment, geo mode, db/cache backend) |
| `*`    | `/enrich`, `/enrich/{ip}`, `/enrich/health` | IP enrichment sub-router (Step 2.5) |

## Request shape (`POST /personalize`)

```jsonc
{
  "list_price": 4999,               // required
  "ip": "49.36.128.5",
  "product_category": "fashion",
  "device_type": "iPhone",           // Android_budget | Android_premium | iPhone | Desktop
  "city_tier": 1,                    // 1 | 2 | 3
  "payment_method_preference": "Credit_Card",
  "cross_merchant_trust_score": 92,  // 0-100
  "return_rate": 0.05,
  "cod_completion_rate": 0.9,
  "account_age_days": 1100,
  "session_id": "optional-merchant-session"
  // every field except list_price has a safe default
}
```

## Response highlights

`final_price`, `price_delta_pct` (capped +15% / −10%), `offer_type`,
`payment_methods_shown` (personalised order), `cod_eligible`,
`instant_refund_eligible`, `reasoning` (plain-English, cites the top-2 SHAP
features), `confidence`, `shap_top`, `ip_enrichment`, and a
`timing_breakdown` for every stage.

## Cross-cutting

- **CORS** — origins from `CORS_ORIGINS` (default `localhost:3000`)
- **request logging** — `METHOD path -> status (ms)` on every call
- **latency middleware** — `X-Process-Time-Ms` header always; `/personalize`
  over budget → `503 {"detail": "latency budget exceeded", ...}`
- **model warm-up** on startup so the first real request is already in-budget

## Layout

```
api/
  main.py            app + endpoints + middleware + lifespan
  service.py         orchestration (enrich → context → model → engine)
  pricing_engine.py  Step 5 - deterministic rules layer (pure, unit-tested)
  metrics.py         /metrics aggregation
  db.py              asyncpg pool + in-memory fallback
  context.py         festival / RBI-demand lookups from pipeline CSVs
  schemas.py         Pydantic request/response models
  schema.sql         Postgres DDL (also mounted by docker-compose)
  _bootstrap.py      registers the hyphenated `ip-enrichment` dir as a module
```
