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
| `api/` | FastAPI: `POST /personalize`, `GET /metrics`, `GET /decision/{sid}`, `POST /simulate`, `POST /session/create`, `GET /sessions/all`, `GET /segment/stats/{key}`, `WS /ws/sessions`, `GET /health`. CORS, request logging, 200 ms latency ceiling (503 over budget). |
| `dashboard/` | Next.js 14 + Tailwind + Recharts. **Seller dashboard** (`/dashboard`) with a link generator + live session table (WebSocket) + aggregate analytics + Bayesian segment CIs; **customer checkout** (`/checkout/{id}`); **merchant session view** (`/merchant/{id}`) with SHAP waterfall + conversion curve. |
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

**Verified:** `bash scripts/verify_stack.sh` exercises the running stack end to
end (health, both personalise profiles, `/decision`, `/metrics`, `/simulate`,
`/enrich`, the dashboard, and a direct Postgres row count) — 14/14.

**Host-port clashes / thread tuning** — every host port and the seeder thread
cap are env-overridable (defaults in parentheses):
`POSTGRES_HOST_PORT` (5432), `REDIS_HOST_PORT` (6379), `API_HOST_PORT` (8000),
`DASHBOARD_HOST_PORT` (3000), `SEEDER_THREADS` (4), `TRAIN_FAST` (1),
`API_THREADS` (2). Put them in `.env`. (LightGBM oversubscribes threads inside
the Docker Desktop VM — the cap keeps training at ~5 s instead of ~20 min.)

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

## Demo flow (link-generator)

The dashboard (`/dashboard`) drives a link-based demo:

1. Presenter picks a preset — **High Income** (Tier 1 · iPhone · Credit Card ·
   40+ prepaid orders · <5% returns), **Mid**, **Low Income** (Tier 3 · budget
   Android · COD · >25% returns), **Random**, or **Custom** (full form:
   pincode → auto tier, device, payment, prepaid-orders slider, return-rate
   slider, VPN toggle) — and clicks **Generate Link**.
2. A **customer link**, a **merchant link**, and a **QR code** appear. Every
   generated session lands in the **live sessions table** (WebSocket, no
   polling).
3. A panel member scans the QR → `/checkout/{session_id}` opens **pre-filled**
   with the preset (all fields editable). They adjust anything, hit
   **See my price**.
4. 1-second personalisation animation, then the reveal: personalised price,
   "You saved ₹X" / "Premium experience pricing" badge, offer, payment methods
   in personalised order, COD / instant-refund badges, an expandable
   **"Why this price?"** (top-2 SHAP features in plain English), and a dummy
   **Complete Purchase**.
5. The seller dashboard table updates that row to **priced** in real time
   (then **converted** on purchase).
6. Click any row → `/merchant/{session_id}`: anonymised segment summary, WTP
   score + confidence, **SHAP waterfall**, **conversion-probability curve**
   across price points, and the **Bayesian segment posterior** (N seen,
   posterior WTP mean + 95% CI, revenue vs flat pricing).
7. Generate a **Low Income** link in a second tab → same product, ~−10%, free
   delivery / cashback, COD eligible. Toggle **VPN** in the custom form to show
   the trust multiplier drop the price and drop COD eligibility.

Expected prices are ranges, not fixed numbers — a maxed-out High profile hits
the **+15% cap**, a maxed-out Low profile hits the **−10% floor**; adjust the
sliders on the checkout page to see the in-between.

---

## Deployment

Frontend → **Vercel**, backend → **Railway** or **Render**. Same demo domain
for the frontend (`razorpay-wtp.vercel.app`), backend on its own host.

### Backend (Railway)

```bash
# from the repo root
railway init
railway add --plugin postgresql
railway add --plugin redis
railway up            # builds ./Dockerfile, runs scripts/start.sh
```

`scripts/start.sh` self-seeds on first boot (offline data + fast train, ~90 s)
when no model artifacts are baked in, then starts uvicorn on `$PORT`.
`DATABASE_URL` / `REDIS_URL` are injected by the plugins. Set:

| var | value |
|---|---|
| `PUBLIC_BASE_URL` | your Vercel URL, e.g. `https://razorpay-wtp.vercel.app` |
| `CORS_ALLOW_ALL` | `true` (or leave unset — `*.vercel.app` is already allowed) |
| `SYNTHETIC_ROWS` | `20000` (keep first-boot training fast) |

`railway.json` pins the Dockerfile build + `/health` check. **Render**: point a
Blueprint at `render.yaml` (API web service + managed Postgres + Redis).

### Frontend (Vercel)

```bash
cd dashboard
vercel                        # first deploy (links the project)
vercel env add NEXT_PUBLIC_API_URL   # -> https://api.razorpay-wtp.up.railway.app
vercel --prod
```

`NEXT_PUBLIC_API_URL` is the only required env var — the browser calls the API
directly (REST + `wss://` for the live session feed), so it must be publicly
reachable and CORS-open to the Vercel origin. `dashboard/vercel.json` sets the
framework + `bom1` (Mumbai) region.

### One-box (any Docker host)

```bash
docker build -t wtp-api .
docker run -p 8000:8000 -e PUBLIC_BASE_URL=http://localhost:3000 wtp-api
# self-seeds, then serves. Add DATABASE_URL / REDIS_URL to use real datastores.
```

---

## Test

```bash
pytest                       # 31 tests: pricing engine, IP enrichment, API e2e, session flow
python scripts/smoke_api.py  # end-to-end, writes scripts/smoke_output.json
bash scripts/verify_stack.sh 8000 3000 5432   # against a running compose stack (26 checks)
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
