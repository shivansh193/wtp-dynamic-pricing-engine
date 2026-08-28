# Architecture — WTP Dynamic Pricing Engine

Razorpay AI Buildathon 2026 · Track 01 (AI Growth & Agentic Commerce)

---

## 1. System design narrative

The engine is a thin, fast **decision layer** that a merchant calls once, at
checkout render, before Razorpay payment initiation. It answers a single
question: *given everything we know about this shopper and this cart, what price
and what offer maximise expected revenue without ever charging a price-sensitive
customer more than list?*

It is built as four decoupled stages joined by data contracts, so each can be
tested, swapped, or scaled independently:

1. **IP enrichment** — the raw client IP becomes a trust signal
   (`ip_type`, `ip_trust_multiplier`, `location_confidence`). FireHOL
   blocklists are held in memory as sorted integer intervals (`bisect` lookup,
   no radix-tree dependency); ASN/ISP resolution uses MaxMind GeoLite2 when a
   licence key is present and a deterministic synthetic table otherwise. A
   whitelist of legitimate Indian *shared* ranges (Jio/Airtel/BSNL business,
   IIT/NIT/NKN campus nets, co-working spaces) prevents corporate-NAT and
   campus traffic from being punished as "datacenter". Every result is cached
   in Redis for 24 h. **Fails safe**: any error → `unknown` / `0.8`.

2. **Market context** — festival period + intensity for the date, and the RBI
   digital-payments demand index for the month, are looked up from the data
   pipeline's outputs and merged into the feature vector.

3. **WTP estimator** — a LightGBM regressor predicts a WTP multiplier in
   `[0.85, 1.25]` from ~21 features (device, city tier, income tier, payment
   preference, behavioural history, IP trust, festival context). A
   `shap.TreeExplainer` is **serialised with the model**, so every prediction
   ships with signed per-feature attributions at no extra training cost. A
   secondary LightGBM classifier predicts P(convert) as a function of the
   *offered* price multiplier — the list-price-vs-adjusted-price curve.

4. **Pricing decision engine** — a **deterministic**, rules-only layer (no
   model calls, no randomness) turns those numbers into a concrete checkout
   treatment: `final_price` (hard-capped at **+15 % / −10 %** of list),
   `offer_type` (premium-experience perks for high WTP, discount nudges for
   low WTP / weak conversion), a **personalised payment-method order**, COD
   and instant-refund eligibility, a plain-English `reasoning` string that
   cites the top-2 SHAP features, and a `confidence` grade.

The API wraps these with CORS, request logging, a model warm-up on startup, and
a hard latency ceiling: `POST /personalize` returns **503** if it exceeds
`LATENCY_BUDGET_MS` (default 200). Every decision — inputs, WTP score, SHAP
values, final price, offer, latency, session id — is logged to PostgreSQL
(async, best-effort; in-memory ring buffer if the DB is down).

---

## 2. Data-flow diagram

```mermaid
flowchart TD
    subgraph Merchant
        CO[Checkout page]
    end

    subgraph "Pricing API  (< 200 ms)"
        direction TB
        RX[POST /personalize\ncustomer_signals + IP]
        IPE[IP Enrichment\nFireHOL · MaxMind/synthetic · whitelist\nRedis cache 24h]
        CTX[Market context\nfestival · RBI demand index]
        WTP[WTP Estimator\nLightGBM regressor + SHAP]
        CONV[Conversion classifier\nP(convert | offered price)]
        PE[Pricing Decision Engine\ncaps ±15/−10% · offer · payment order\nCOD / refund eligibility · reasoning]
        RESP[PricingResponse\nprice · offer · SHAP · timing]
    end

    subgraph Datastores
        RD[(Redis\nIP cache)]
        PG[(PostgreSQL\npricing_decisions)]
    end

    subgraph "Offline  (data-pipeline + model)"
        RBI[RBI DBIE\ndigital payments]
        GT[Google Trends\ncategory interest]
        FES[Festival calendar\n2022–2026]
        FH[FireHOL blocklists]
        SYN[50k synthetic\ntransactions]
        TRAIN[LightGBM training\n+ SHAP + plots]
    end

    CO -->|customer signals + IP| RX
    RX --> IPE
    IPE <-->|get/set| RD
    IPE --> CTX --> WTP --> CONV --> PE --> RESP
    RESP -->|personalised price + offer| CO
    RESP -->|async log: inputs, wtp, shap, price, latency| PG

    RBI --> SYN
    GT --> SYN
    FES --> SYN
    SYN --> TRAIN
    TRAIN -->|wtp_estimator.joblib\nconversion_classifier.joblib| WTP
    TRAIN --> CONV
    FES --> CTX
    RBI --> CTX
    FH --> IPE
```

---

## 3. Tech stack — one-line justifications

| Choice | Why |
|---|---|
| **Python 3.11 + FastAPI + uvicorn** | Async I/O for the enrichment/DB calls, Pydantic validation for a clean merchant-facing contract, first-class OpenAPI docs. |
| **LightGBM** | Best-in-class tabular accuracy, native categorical handling (no one-hot blow-up), millisecond single-row inference — fits the 200 ms budget with room to spare. |
| **SHAP `TreeExplainer`** | Exact, fast Shapley values for trees; every price is explainable to the merchant and the shopper, and drives the `reasoning` text. |
| **Deterministic rules engine (plain Python)** | Pricing policy must be auditable and unit-testable; ML sets the *target*, rules enforce the *guardrails* (caps, eligibility, offer logic). |
| **PostgreSQL + asyncpg** | Durable decision log for analytics / audit / revenue-lift measurement; `asyncpg` keeps logging off the critical path. |
| **Redis (`redis.asyncio`)** | 24 h IP-enrichment cache so repeat shoppers cost ~1 ms, not a fresh blocklist+ASN pass. |
| **MaxMind GeoLite2 (`geoip2`)** | Industry-standard offline IP→ASN/geo; free tier; no per-request network call. |
| **FireHOL blocklist-ipsets** | Community-maintained, frequently-updated VPN/DC/Tor/bogon ranges; loaded once into memory. |
| **pytrends / RBI DBIE** | Ground the synthetic data in *real* Indian demand seasonality and payment-mix trends. |
| **Next.js 14 + Tailwind + Recharts** | App-router SSR for a fast first paint, utility CSS for a polished demo quickly, Recharts for the live metric charts. |
| **Prophet + `arch` (GARCH) + `hmmlearn`** (Track 04) | Settlement forecasting needs trend/seasonality (Prophet), volatility clustering (GARCH), and discrete regime detection (HMM) — three complementary views. |
| **Docker Compose** | One command brings up PG + Redis + seeder + API + dashboard with correct boot ordering and health gates. |
| **joblib** | Simple, compressed serialisation of the model **and** its SHAP explainer as one bundle. |

---

## 4. Latency budget

Target: **end-to-end `POST /personalize` < 200 ms**. Measured stage costs
(local, warm, in-process cache):

| Stage | Budget | Measured (typ.) | Notes |
|---|---:|---:|---|
| IP enrichment (cache hit) | 5 ms | **0.1–0.5 ms** | sorted-interval `bisect`; Redis GET on miss |
| Market context lookup | 1 ms | **~0.02 ms** | in-memory dicts from pipeline CSVs |
| WTP model inference + SHAP | 50 ms | **3–18 ms** | single-row LightGBM predict + `TreeExplainer` |
| Conversion model (list + adjusted) | 30 ms | **2–30 ms** | two single-row predicts |
| Pricing decision engine | 10 ms | **< 0.1 ms** | pure Python arithmetic + string build |
| DB log (async, off critical path) | 0 ms | **0 ms** | `await` after the response is assembled; best-effort |
| **Total** | **< 200 ms** | **~35–65 ms warm** | first request after boot is pre-warmed in the lifespan hook |

Headroom is deliberate: it absorbs a cold Redis miss, a real MaxMind lookup, and
network jitter between the merchant and the API while still clearing 200 ms. The
middleware returns **503** (not a stale price) if the ceiling is ever breached.

---

## 5. Ethical framing — segmentation, not exploitation

**What this system does:** it prices to *observable segment characteristics*
(device class, city tier, neighbourhood income tier, payment-method mix,
return behaviour, network trust), the same variables a merchant already uses for
shipping thresholds, COD eligibility, and ad targeting. It is **second-degree /
third-degree price discrimination** — the economics term for "student
discounts" and "off-peak fares" — not surveillance-based individual extraction.

**Guardrails that make it defensible:**

- **Hard, symmetric-ish caps.** No shopper ever pays more than **+15 %** of
  list; no price is cut more than **−10 %**. The band is small and fixed in
  code, not learned.
- **Low-trust / price-sensitive shoppers are never charged *more* than list.**
  The model pushes their multiplier *down*; the engine gives them the discount
  nudges (free delivery, 5 % cashback). The downside risk lands on the
  merchant's margin, not the vulnerable customer.
- **No protected attributes.** No name, gender, caste, religion, or precise
  location. City tier and income tier are coarse, area-level, and public-census
  derived.
- **Every price is explained.** The `reasoning` string and SHAP attributions
  are returned on every call and logged — a merchant (or a regulator) can see
  exactly why a price was shown.
- **Deterministic policy.** Given the same inputs the decision is identical and
  reproducible; there is no per-user random experimentation on price.

**Why it benefits both sides:**

- *Merchant* — recovers margin from low-price-sensitivity segments (premium
  device + metro + credit card) and rescues conversions from high-sensitivity
  segments with targeted nudges instead of a blanket sitewide discount. The
  `/metrics` revenue-lift simulation quantifies this.
- *Consumer* — a price-sensitive shopper in a Tier-3 town gets a *better* price
  and a delivery/cashback sweetener; a high-intent shopper gets premium-service
  perks (extended warranty, priority support, instant refund) rather than being
  nickel-and-dimed. COD and instant-refund eligibility expand as cross-merchant
  trust grows, which is a consumer benefit the shopper earns.

**What we would not ship:** uncapped pricing, individual-level price memory
("this user paid ₹X last time, try ₹X+10 %"), scarcity/urgency dark patterns
tied to the price, or any use of protected attributes. None of those are in the
codebase and the cap constants are the first thing a reviewer should check
(`api/pricing_engine.py`).

---

## 6. Known limitations & what changes with real Razorpay data

| Limitation today | With real Razorpay transaction data |
|---|---|
| **Synthetic ground truth.** `actual_wtp` is generated by a known additive model, so R² ≈ 0.91 is partly "the model finding the generator". | Train on realised outcomes: A/B'd price exposures → actual conversion and realised revenue. WTP becomes a *latent* target estimated from price-response curves, not a label. |
| **Conversion classifier is weak (AUC ≈ 0.72)** because synthetic conversion has a lot of injected noise. | Real click→pay funnels with true negatives give a much sharper price-elasticity model per segment. |
| **IP enrichment runs in mock-geo mode** unless a MaxMind key is supplied; synthetic ASN resolution is deterministic but arbitrary for unknown IPs. | Drop in the GeoLite2 `.mmdb` files (or Razorpay's own IP intelligence) — `geo_source` flips to `maxmind`, `location_confidence` becomes meaningful. |
| **Behavioural signals are merchant-supplied in the request.** | Razorpay already sees cross-merchant payment success, COD completion, and tenure — these become server-side lookups, not client inputs, and can't be spoofed. |
| **Cross-merchant trust score is a hand-tuned formula.** | Replace with Razorpay's existing risk/trust score. |
| **Festival calendar and RBI demand index are static files.** | Live feeds; per-category, per-region demand nowcasting. |
| **No holdout / guardrail monitoring in production.** | Always keep a control slice at list price to measure true lift and detect model drift; alert if realised margin or conversion drops. |
| **Single-region, single-currency.** | Multi-currency, GST-inclusive display rules, state-level COD policies. |
| **Docker images built but not run in this environment** (Docker daemon was offline during the build session). | CI builds + smoke-tests the compose stack on every push. |

---

## 7. What broke during development

<!-- Fill this in with the real war stories after the build. Seed notes: -->

- **numpy 1.x / 2.x ABI break.** The host Python had `numpy 2.2` but `pandas
  2.0.2` (pinned by an unrelated global package), giving
  `ValueError: numpy.dtype size changed`. Fixed by giving the project its own
  venv with the pinned `requirements.txt` (`numpy 1.26.4` + `pandas 2.2.2`).
  Lesson: never share a Python env with a data project.
- **`shap` vs `numpy` version constraint.** `shap 0.51` requires `numpy>=2`;
  had to pin `shap 0.45.1` to stay on the `numpy 1.26` line that `lightgbm` +
  the rest of the stack were happy with.
- **FireHOL list names changed.** `datacenters.netset` and `vpn.netset` were
  retired from the repo root (404). Mapped `vpn.netset` → `firehol_anonymous.netset`
  (2.8 M CIDRs — added a `FIREHOL_MAX_ENTRIES` cap so startup stays fast) and
  kept a curated sample for `datacenters.netset`.
- **`pytrends` + `urllib3 2.x`.** `Retry.__init__() got an unexpected keyword
  argument 'method_whitelist'` — pytrends 4.9.2 uses the old urllib3 API. The
  calibrated synthetic Trends series is used as the fallback.
- **Hyphenated module dir.** The brief mandates `ip-enrichment/`, which isn't a
  legal Python module name. `api/_bootstrap.py` registers it as `ip_enrichment`
  via `importlib` with an explicit `submodule_search_locations`.
- **`build_features` default bug.** `dict.get("income_tier", "mid")` returned
  `None` (the key existed with a `None` value from the Pydantic model), which
  encoded to `-1` "unseen". Switched to `raw.get(k) or default` throughout.
- **SHAP display values.** Early responses showed encoded integers
  (`device_type = 2.0`) in the reasoning. `inference.py` now keeps the
  pre-encoding frame alongside the encoded one and reports the human value.
- **Docker Desktop was not running** in the build environment, so the images
  are defined and `docker compose config` validates, but the containers
  themselves were verified only by running the services natively.
