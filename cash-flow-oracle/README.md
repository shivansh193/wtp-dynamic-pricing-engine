# Cash Flow Oracle — Track 04 scaffold

> **Status: scaffold.** Clean, runnable code for the settlement-forecasting
> pipeline and API. No frontend. Built after the Track 01 engine.

Predicts a merchant's near-term settlement cash flow and turns it into a plain-
English working-capital recommendation:

> *"Your settlements typically drop 23 % in August. We recommend drawing down
> ₹2L before August 15th."*

## Pipeline

```
RBI DBIE monthly payment stats ──▶ PostgreSQL (rbi_digital_payments)
                                        │  (macro context)
5 merchant archetypes × 3y daily  ──▶ PostgreSQL (merchant_settlements)
settlements, Indian seasonality          │
                                         ▼
        ┌────────────────────────────────────────────────┐
        │  GARCH(1,1)   volatility of daily settlements   │
        │  HMM (3-state) regime: high_season/low/stress   │
        │  Prophet       30–60 day forward forecast + CI  │
        └────────────────────────────────────────────────┘
                                         ▼
                POST /forecast {merchant_id}
                → current_cash_position
                → forecast_curve (30d daily, upper/lower bands)
                → stress_periods (flagged dates)
                → credit_recommendation (plain English)
```

## Run

```bash
pip install -r requirements.txt          # prophet, arch, hmmlearn, statsmodels

# the directory name has a hyphen, so a small runner shims the import.
# (or `pip install -e .` from the repo root, then use the module paths directly)

python scripts/cfo.py seed                       # generate + persist settlements
python scripts/cfo.py forecast m_fashion_01 30   # one-off forecast to stdout
python scripts/cfo.py serve 8010                 # FastAPI on :8010

# with `pip install -e .`:
python -m cash_flow_oracle.seed
uvicorn cash_flow_oracle.main:app --port 8010
```

Endpoints:
- `POST /forecast` `{"merchant_id": "m_fashion_01", "horizon_days": 30}`
- `GET /merchants`
- `GET /health` — shows which model engines (`prophet` / `arch_garch` /
  `hmmlearn`) are installed vs falling back

Storage: uses `CFO_DATABASE_URL` / `DATABASE_URL` (PostgreSQL via asyncpg) when
set and reachable, otherwise a local `cash_flow_oracle.sqlite3` file so the
scaffold runs with zero infra.

If `prophet` / `arch` / `hmmlearn` aren't installed, each model degrades to a
documented statistical fallback (EWMA trend + rolling-vol + quantile regimes)
so the endpoint still returns a sane forecast — clearly flagged
`"engine": "fallback"` in the response.

## Merchant archetypes

| id prefix | archetype | seasonality shape |
|---|---|---|
| `m_fashion_` | Fashion & apparel | strong Diwali + wedding-season spikes, Jan/Feb trough |
| `m_electronics_` | Electronics | sharpest festive spike (Oct–Nov), post-festival dip |
| `m_grocery_` | Grocery & essentials | near-flat, mild festive bump, monsoon dip |
| `m_home_` | Home & furniture | Mar FY-end surge, Diwali spike, monsoon dip |
| `m_services_` | Services / subscriptions | low volatility, mild June back-to-school + Q4 |

All calibrated to: **Diwali spikes**, **monsoon dips (Jun–Sep)**, **March
financial-year-end surge**, **June back-to-school**.

## Layout

```
cash-flow-oracle/
  config.py                merchant archetypes, seasonality, GARCH/HMM params
  db.py                    async PG (asyncpg) with SQLite fallback
  schema.sql               merchant_settlements + rbi_digital_payments DDL
  data_pipeline/
    fetch_rbi.py           RBI DBIE monthly series -> PG (offline fallback)
    generate_settlements.py 5 archetypes x 3y daily, seasonal calibration
  models/
    garch.py               GARCH(1,1) on daily settlement returns
    regime_hmm.py           3-state Gaussian HMM -> high_season/low_season/stress
    forecast_prophet.py     Prophet 30–60d forecast + confidence bands
  service.py               orchestration + credit_recommendation text
  schemas.py               Pydantic request/response
  main.py                  FastAPI: POST /forecast, GET /merchants, GET /health
  seed.py                  one-shot: generate + persist
```
