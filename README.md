# WTP Dynamic Pricing Engine

**Razorpay AI Buildathon 2026 — Track 01 (AI Growth & Agentic Commerce)**

A real-time checkout personalisation layer for Indian ecommerce. It estimates a
shopper's **willingness to pay (WTP)** from device / geo / behavioural / network
signals, then dynamically adjusts the **price and offer** shown at checkout — in
**under 200 ms** — behind a clean API that sits between a merchant's checkout
and Razorpay payment initiation.

> **Live demo**
> - Seller dashboard: **https://wtp-dynamic-pricing-engine.vercel.app/dashboard**
> - API: **https://wtp-pricing-api.onrender.com** (`/docs`, `/health`)
>
> The API runs on a free Render instance — it sleeps after ~15 min idle and the
> first request then takes ~50 s to wake. Hit `/health` once to warm it before a
> live walkthrough. The checkout auto-retries once and shows a "waking up"
> message if it's cold.

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
   across price points, the **Bayesian segment posterior** (N seen, posterior
   WTP mean + Student-t 95% CI clipped to the price band), and **expected
   gross-margin lift vs flat pricing** (a markup is a margin play — COGS is
   unchanged — so a premium segment shows a clear margin gain even when
   expected *revenue* is roughly flat at the model's conversion elasticity).
7. Generate a **Low Income** link in a second tab → same product, ~−10%, free
   delivery / cashback, COD eligible. Toggle **VPN** in the custom form to show
   the trust multiplier drop the price and drop COD eligibility.

Expected prices are ranges, not fixed numbers — a maxed-out High profile hits
the **+15% cap**, a maxed-out Low profile hits the **−10% floor**; adjust the
sliders on the checkout page to see the in-between.

---

## Deployment

**Frontend → Vercel, backend → Render** (both entirely from the CLI). The API
cannot run on Vercel — `/ws/sessions` needs a long-lived process and the
LightGBM + SHAP + SciPy bundle far exceeds the serverless size limit.

The API image **bakes the dataset + trained models at build time**
(`ARG BAKE_MODEL=1` in the `Dockerfile` → `scripts/seed_offline.sh`), so the
container cold-starts in ~4 s instead of self-seeding for ~2 min on every
scale-from-zero. `docker-compose` passes `BAKE_MODEL=0` (its `seeder` service
handles that).

### Backend — Render (free web service, no card)

```bash
export RENDER_API_KEY=rnd_...     # dashboard.render.com → Account → API Keys

render services create \
  --name wtp-pricing-api --type web_service --runtime docker \
  --repo https://github.com/<you>/wtp-dynamic-pricing-engine --branch master \
  --region singapore --plan free --health-check-path /health \
  --env-var LATENCY_BUDGET_MS=1200 --env-var SYNTHETIC_ROWS=20000 \
  --env-var TRAIN_FAST=1 --env-var OMP_NUM_THREADS=2 --env-var DB_REQUIRED=false \
  --env-var CORS_ALLOW_ALL=true \
  --env-var PUBLIC_BASE_URL=https://<your-app>.vercel.app \
  --confirm
```

Notes:
- **`LATENCY_BUDGET_MS=1200`** — a free shared-CPU instance does the full
  IP-enrich + WTP + SHAP + 2× conversion + engine pass in ~270–300 ms (vs
  <200 ms on real infra), and `POST /personalize` hard-returns **503** over
  budget. Every response still reports the true `latency_ms` + `budget_exceeded`.
- No `DATABASE_URL` / `REDIS_URL` → in-memory decision log + session store +
  cache. Add Render Postgres + Key Value and set the URLs for persistence.
- `CORS_ALLOW_ALL=true`, or leave it off — `*.vercel.app` is allowed by an
  origin regex already.
- Health check path **must** be passed carefully on Windows Git Bash —
  `--health-check-path /health` gets rewritten to a Windows path unless you
  prefix `MSYS_NO_PATHCONV=1`.
- `render.yaml` is the Blueprint equivalent (Render dashboard → New → Blueprint).

### Frontend — Vercel

```bash
cd dashboard
vercel link --yes --project wtp-dynamic-pricing-engine
printf 'https://wtp-pricing-api.onrender.com' | vercel env add NEXT_PUBLIC_API_URL production
vercel deploy --prod --yes
```

`NEXT_PUBLIC_API_URL` is the only required var — it's inlined into the client
bundle at build time; the browser calls the API directly (REST + `wss://` for
the live session feed), so redeploy after changing it. `next.config.js` also
accepts the legacy `NEXT_PUBLIC_API_BASE_URL`. Production alias:
`https://wtp-dynamic-pricing-engine.vercel.app` (the raw `*-<hash>-*.vercel.app`
deployment URLs sit behind Vercel SSO on Hobby; the alias is public).

### One-box (any Docker host)

```bash
docker build -t wtp-api .          # bakes model; ~3 min
docker run -p 8000:8000 -e PUBLIC_BASE_URL=http://localhost:3000 wtp-api
# cold-starts in ~4 s. Add DATABASE_URL / REDIS_URL to use real datastores.
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
