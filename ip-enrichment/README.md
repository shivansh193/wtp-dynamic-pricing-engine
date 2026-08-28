# ip-enrichment (Buildathon Step 2.5)

Turns a raw IP into a checkout-trust signal in **well under 1 ms** (cached) or
a few ms (cold), so it fits comfortably inside the 200 ms pricing budget.

## What it does

1. Loads FireHOL blocklists into memory on startup (sorted integer intervals,
   `bisect` lookup — no radix-tree dependency).
2. Resolves ASN / ISP / connection-type via **MaxMind GeoLite2** when the
   `.mmdb` files are present, otherwise a **synthetic ASN table** keyed by a
   deterministic hash of the IP's /16 (clearly flagged `geo_source: synthetic`,
   "MOCK GEO MODE" logged at startup). Well-known ranges (Google DNS,
   Cloudflare, AWS Mumbai, common VPN blocks, Jio/Airtel/BSNL, IIT Bombay) are
   hard-coded so the demo still classifies famous IPs correctly without a key.
3. Maintains a **whitelist of legitimate Indian shared ranges** — Jio/Airtel/
   BSNL business, IIT/NIT/NKN/ERNET campus networks, co-working spaces — so
   corporate-NAT and campus traffic isn't punished as "datacenter".
4. Classifies into `residential / mobile_carrier / datacenter / vpn /
   public_wifi / tor / unknown` and emits:

   | field | meaning |
   |---|---|
   | `ip_type` | the class above |
   | `ip_trust_multiplier` | residential 1.0 · mobile 0.95 · unknown 0.8 · public_wifi 0.7 · vpn 0.6 · datacenter 0.5 · tor 0.3 |
   | `location_confidence` | 0–1, how much to trust the geolocation |
   | `is_whitelisted`, `whitelist_reason`, `blocklist_hits` | provenance |

5. **Fails safe**: any lookup error → `ip_type=unknown`, `multiplier=0.8`,
   `fallback_used=true`.
6. **Caches** every result in Redis with a 24 h TTL (in-process LRU fallback
   when Redis is down).

## Precedence

`Tor` (hard, overrides whitelist) → `whitelist` → `VPN` → `datacenter` →
`mobile_carrier` → `public_wifi` (campus) → `residential` → `unknown`.

## Use it

```python
# standalone
uvicorn ip_enrichment.app:app --port 8100      # POST /enrich  {"ip": "..."}

# mounted by the main API
from ip_enrichment.router import router
app.include_router(router)                      # GET /enrich/{ip}, /enrich/health

# quick CLI
python -c "import api._bootstrap; from ip_enrichment.cli import main; main()" 8.8.8.8
```

## Config (env)

`REDIS_URL`, `IP_CACHE_TTL_SECONDS` (86400), `GEOIP_CITY_DB`, `GEOIP_ASN_DB`,
`FIREHOL_MAX_ENTRIES` (250000 — cap for huge aggregate lists; `0` disables).

## MaxMind key (optional)

Free signup at <https://www.maxmind.com/en/geolite2/signup>, then
`MAXMIND_LICENSE_KEY=...` in `.env` and `python data-pipeline/fetch_maxmind.py`.
Without it the module runs in mock-geo mode — functional, clearly labelled.
