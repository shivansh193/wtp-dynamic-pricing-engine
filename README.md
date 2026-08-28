# WTP Dynamic Pricing Engine

**Razorpay AI Buildathon 2026 — Track 01 (AI Growth & Agentic Commerce)**

A real-time checkout personalisation layer for Indian ecommerce. It estimates a
shopper's **willingness to pay (WTP)** from device / geo / behavioural / network
signals, then dynamically adjusts the **price and offer** shown at checkout — in
**under 200 ms** — behind a clean API that sits between a merchant's checkout
and Razorpay payment initiation.

```
customer signals ─▶ IP enrichment ─▶ WTP estimator (LightGBM + SHAP)
                                          │
                                          ▼
              deterministic pricing engine (caps, offers, payment order)
                                          │
                          ┌───────────────┴───────────────┐
                          ▼                               ▼
                 personalised checkout            PostgreSQL decision log
```

---

## What's in the box

| Path | What it is |
|---|---|
| `data-pipeline/` | Fetch real data (RBI DBIE, Google Trends, FireHOL, MaxMind, IPinfo) + generate 50 k calibrated synthetic transactions. Every fetch has an offline fallback. |
| `model/` | LightGBM **WTP regressor** (R² ≈ 0.91) + **conversion classifier** (AUC ≈ 0.72), SHAP explainer serialised with the model, 4 docs plots. |
| `ip-enrichment/` | VPN / datacenter / Tor / public-wifi detection. In-memory FireHOL matcher, MaxMind + synthetic-ASN fallback, Indian shared-IP whitelist, Redis cache. `/enrich` router. |
| `api/` | FastAPI: `POST /personalize`, `GET /metrics`, `GET /decision/{sid}`, `POST /simulate`, `GET /health`. CORS, request logging, 200 ms latency ceiling (503 over budget). |
| `dashboard/` | Next.js 14 + Tailwind + Recharts. Split-screen checkout demo, live profile editor, IP-enrichment visualiser, auto-refreshing metrics. |
| `cash-flow-oracle/` | Track 04 scaffold — merchant settlement forecasting (GARCH + HMM + Prophet). Clean code, no frontend. |
| `docs/` | [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) + generated plots. |

---

## Run it

### Docker (everything)

```bash
cp .env.example .env          # optional: add MAXMIND_LICENSE_KEY / IPINFO_TOKEN
docker compose up --build
```

Boot order: `postgres` + `redis` → `seeder` (runs the data pipeline + trains
the models into shared volumes, **once**) → `api` → `dashboard`.

- Dashboard: <http://localhost:3000>
- API docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>

First boot takes a few minutes (pip install + 50 k-row generation + training).
Later boots are fast — the seeder sees its marker file and exits immediately.
Delete the `appdata` / `appmodels` volumes to force a re-seed.

### Local (no Docker)

```bash
python -m venv .venv && . .venv/Scripts/activate      # or .venv/bin/activate
pip install -r requirements.txt

python data-pipeline/run_all.py --no-net              # data/  (fully offline)
python -m model.train                                 # model/artifacts/

uvicorn api.main:app --port 8000                      # API (PG/Redis optional)
cd dashboard && npm install && npm run dev            # http://localhost:3000
```

Without Postgres/Redis the API degrades gracefully: in-memory decision log,
in-process cache. Everything still works.

---

## Demo script

1. Open the dashboard. Two shoppers see the **same** Nike Pegasus 41 (₹4,999):
   - **Customer A** (iPhone, Mumbai/Tier 1, Credit Card, trust 92) → **₹5,749
     (+15 %)**, free extended warranty, credit card surfaced, instant-refund
     badge.
   - **Customer B** (budget Android, Patna/Tier 3, COD, trust 31, on a VPN) →
     **₹4,499 (−10 %)**, 5 % cashback, UPI/COD first.
2. Drag the **trust score** slider on Customer B up past 60 → COD becomes
   eligible; past 80 → instant refund unlocks.
3. Toggle **VPN mode** on Customer A → `ip_trust_multiplier` drops to 0.6, it's
   applied to the trust score, price and offer move.
4. Watch the **metrics panel**: revenue with WTP pricing vs flat, conversion by
   offer type, top SHAP features, VPN/datacenter traffic share.
5. `POST /simulate` (or the API docs) shows the full **counterfactual sweep** —
   what the price would be if device / tier / payment method changed.

---

## Test

```bash
pytest                       # 20 tests: pricing engine, IP enrichment, API e2e
python scripts/smoke_api.py  # end-to-end, writes scripts/smoke_output.json
```

---

## API keys (optional)

| Key | For | Without it |
|---|---|---|
| `MAXMIND_LICENSE_KEY` | real GeoLite2 City/ASN lookup | synthetic ASN table, "MOCK GEO MODE" logged, clearly flagged in every response |
| `IPINFO_TOKEN` | IPinfo free ASN dump | curated fallback table (Jio/Airtel/BSNL + hosting + VPN ASNs) |

Sign-up links are in `.env.example` and each fetch script's docstring.

---

## Design notes & ethics

See **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)** for the system-design
narrative, the data-flow diagram, the latency budget breakdown, and the ethical
framing — why this is **segment-level pricing with hard ± caps**, never
individualised gouging, and why it benefits both merchants (conversion, margin)
and consumers (low-trust / price-sensitive shoppers are never charged *more*
than list, and get the discount nudges).
