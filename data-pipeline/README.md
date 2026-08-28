# data-pipeline

Fetches real Indian market data and generates the calibrated synthetic
customer-transaction dataset that trains the WTP estimator.

## Design principle: never block on the network

Every external source has a **calibrated synthetic fallback**. If a fetch
fails (offline, rate-limited, no API key), the pipeline still produces a
complete, internally-consistent dataset. Each output carries a
`*.source.json` sidecar recording `live_fetch: true|false` so you always know
what's real and what's modelled.

## Run

```bash
pip install -r ../requirements.txt

# everything (attempts live fetches, falls back per-source)
python run_all.py

# fully offline, synthetic only
python run_all.py --no-net

# smaller dataset for a quick loop
python run_all.py --rows 5000
```

## Stages

| Script | Output | Live source | Fallback |
|---|---|---|---|
| `fetch_rbi.py` | `data/raw/rbi_digital_payments.csv` | RBI DBIE (dbie.rbi.org.in) | Series interpolated between published RBI/NPCI UPI anchors + festive seasonality |
| `fetch_google_trends.py` | `data/raw/google_trends_categories.csv` | Google Trends via `pytrends` (geo=IN) | `CATEGORY_SEASONALITY` in `config.py` + secular growth |
| `build_pincode_income.py` | `data/raw/pincode_income_tier.csv` | — (constructed) | Tier-anchored mapping over real PIN prefixes for 36 cities |
| `build_festival_calendar.py` | `data/raw/festival_calendar.csv`, `data/processed/festival_features.csv` | — (authored) | Public festival dates 2022–2026, intensity 1–3 |
| `fetch_firehol.py` | `data/raw/firehol/*.netset` | github.com/firehol/blocklist-ipsets | Small real sample of well-known VPN/DC/Tor/bogon ranges |
| `fetch_maxmind.py` | `data/raw/geoip/GeoLite2-*.mmdb` | MaxMind GeoLite2 (**needs free key**) | None — enrichment module runs in "mock geo" mode |
| `fetch_ipinfo_asn.py` | `data/raw/ipinfo_asn.csv` | ipinfo.io/data (**needs free token**) | Curated table: Jio/Airtel/BSNL/VIL + hosting + VPN ASNs |
| `generate_synthetic.py` | `data/processed/transactions.csv`, `feature_schema.json` | — | 50,000 rows calibrated to the above |

## API keys

Two sources need a free account. Add to `.env` (see `.env.example`):

- **`MAXMIND_LICENSE_KEY`** — https://www.maxmind.com/en/geolite2/signup
- **`IPINFO_TOKEN`** — https://ipinfo.io/signup

Without them the system is fully functional; IP geo/ASN resolution uses the
built-in synthetic table and this is logged loudly at API startup.

## Synthetic dataset calibration

`generate_synthetic.py` prints calibration checks on every run:

- festival periods → **+15–25 % AOV** and higher conversion
- `Tier1 + iPhone + Credit_Card` → `actual_wtp` clusters **1.10–1.25**
- `Tier3 + Android_budget + COD` → `actual_wtp` clusters **0.85–0.95**
- VPN / datacenter / Tor users → `ip_trust_multiplier` applied to
  `cross_merchant_trust_score`

The feature schema in `data/processed/feature_schema.json` is the single
source of truth consumed by `/model` and `/api`.
