# dashboard - live checkout personalisation demo

Next.js 14 (App Router) · Tailwind CSS · Recharts. Talks to the FastAPI
backend at `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`).

## Run

```bash
npm install
cp .env.local.example .env.local     # point at your API if not localhost:8000
npm run dev                          # http://localhost:3000
# or: npm run build && npm start
```

The API must be running with `model/artifacts/*.joblib` present.

## What's on the page

1. **Split-screen checkout** — the same product (Nike Pegasus 41, ₹4,999) for
   two shoppers:
   - **Customer A** — iPhone · Mumbai (Tier 1) · Credit Card · trust 92 ·
     3-year account → prices **up**, premium-experience offer, credit card
     surfaced, instant-refund badge.
   - **Customer B** — Budget Android · Patna (Tier 3) · COD · trust 31 ·
     6-month account → prices **down**, discount nudge, UPI/COD first.
   - On load each panel plays a "personalising checkout…" shimmer, then pops
     in the personalised price. Below each: the **top-3 SHAP drivers** as a
     small bar chart.

2. **Profile editors** — sliders / dropdowns for device, city tier, payment
   preference, trust score, return rate, account age, IP type. Every change
   re-calls `POST /personalize` (350 ms debounce) and shows the measured
   `latency_ms`.

3. **IP enrichment visualiser** — detected `ip_type`, applied
   `ip_trust_multiplier`, whitelist / blocklist status, geo source, and a
   **VPN mode toggle** that swaps the IP to a commercial-VPN egress address and
   re-runs the decision so you can watch the price and COD eligibility move.

4. **Live metrics** (bottom) — auto-refreshes every 30 s from `GET /metrics`:
   avg WTP by city tier, conversion rate by offer type, revenue **WTP vs flat**,
   top features driving WTP, traffic mix by network type, and the headline
   revenue-lift number.

## Notes

- `output: "standalone"` in `next.config.js` for a small Docker runtime image.
- All API calls are client-side (`cache: "no-store"`); no secrets in the
  bundle — only `NEXT_PUBLIC_API_BASE_URL`.
