# 5-Minute Demo Script — Razorpay AI Buildathon 2026

**Runtime target:** 4:45 (hard ceiling 5:00). ~700 spoken words at ~145 wpm.

**Structure (your format):** problem with data → the product → why it helps
Razorpay → then Track 4, same shape, compressed into the last ~60 seconds.

**Tracks:** primary is **Track 01 — AI Growth & Agentic Commerce** (the pricing +
conversion engine). Secondary is **Track 04 — AI Finance Controller** (the Cash
Flow Oracle). The Track 01 success bar on the site is *"every money action
explainable, bounded and gated"* — that line is quoted back in the pitch on
purpose, because it's exactly the design.

---

## Before you hit record

- **Warm the API.** The Render free instance sleeps after 15 min. Open
  `https://wtp-pricing-api.onrender.com/health`, then all three dashboards,
  about two minutes before you record so nothing cold-starts on camera.
- **Four tabs, left to right:**
  1. Seller dashboard — `…vercel.app/dashboard`
  2. A customer checkout link for the **price-sensitive** profile (generate it first, see below)
  3. Merchant analytics — `…vercel.app/merchant/dashboard` (scroll to the A/B panel)
  4. Cash Flow Oracle — `…vercel.app/cash-flow-oracle`, on a merchant that
     **currently shows a stress period** (see next bullet)
- **Price-sensitive profile** (link generator → Custom): Tier 3 / PIN `800001`,
  Android budget, UPI, prepaid orders ~4, return rate ~25%. Confirm the checkout
  shows **₹4,499** and a monthly line near **₹375/month at 0% interest**.
- **Metro profile:** the built-in **High income** preset. Confirm **₹5,749** and
  a *free 1-year extended warranty* offer (no discount, no timer).
- **Pick the Cash Flow Oracle merchant on the day.** The forecast re-anchors to
  "today", so which merchants are in a stress period drifts. As of Sept 4,
  **GigaMart (electronics, Tier 1)** shows a clean one: ~15-day squeeze from
  Sept 21, ~₹47L short at the trough, apply by Sept 27, borrowing early nets
  ~₹32k. If GigaMart has gone quiet by recording day, click down the dropdown —
  the "Next stress period" stat card tells you instantly which merchants have
  one. Electronics and Home merchants tend to. Then read that merchant's real
  numbers into the Track 4 lines.
- The Track 01 figures (₹4,499, ₹375/mo, ₹5,749) are stable.

---

## The script

Spoken lines are in quote blocks. `[bracketed]` lines are what you do on screen.

### [0:00 – 0:12]  Open — on the seller dashboard

> Hi, I'm [name]. I built two things. The main one is a pricing and conversion
> engine for Indian checkouts, and that's most of what I'll show. The second is a
> cash-flow forecaster for merchants, and I'll get to that at the end.

### [0:12 – 1:06]  The problem, with data

> Indian ecommerce shows one price to everyone. A shopper on an iPhone in Mumbai
> paying by card, and a shopper on a six-thousand-rupee Android in a Tier-3 town
> who only pays cash on delivery — same price, same checkout, same offer.
>
> That costs the merchant on both ends. The Mumbai shopper would have paid more
> and nobody asked. The Tier-3 shopper drops at the payment step, because cash on
> delivery isn't offered or the number just feels too high. Baymard's research
> puts checkout abandonment around seventy percent, and most of the reasons are
> price and payment friction, not the product.
>
> So the real question isn't "what should this cost." It's "this shopper, this
> cart, right now — what price converts, and what's actually stopping them from
> paying."

### [1:06 – 2:52]  The product

> Here's the seller dashboard. I generate a checkout link for a shopper profile.
> Let's take the Tier-3, cash-on-delivery one.
>
> `[open the customer checkout tab]`
>
> When the shopper opens this, one API call does five things in about forty
> milliseconds. It estimates willingness to pay with a gradient-boosted model —
> that's the four-thousand-nine-ninety-nine list price coming down to four-four-
> nine-nine here, because the model reads low price tolerance from the city tier,
> the return history, the payment mix. Then a second model names the friction.
> For this shopper it's price sensitivity, so the page changes: the price is
> shown as three-seventy-five a month at zero interest, with a market-price
> reference above it, and UPI and cash on delivery move to the top.
>
> `[switch to the High income preset checkout]`
>
> Same engine, different shopper. Now it's a small markup, five-seven-four-nine,
> and instead of a discount it's a free one-year extended warranty. The friction
> here isn't price. It's that this person wants a quality signal, not a countdown
> timer, so that's what the page gives them.
>
> Three things to point at. First, every price is capped in code — never more
> than plus fifteen percent, never a discount past minus ten, and a
> price-sensitive shopper is never charged above list. Second, every decision
> comes back with its SHAP explanation, so the merchant sees why. Third, the
> merchant owns the controls: this panel turns the markup off completely,
> tightens the caps, switches individual perks on and off.
>
> `[merchant analytics tab, A/B panel]`
>
> And I can test a change before shipping it. This runs a synthetic A/B test,
> flat pricing against the friction-aware version, with a two-proportion z-test
> and a confidence interval on the lift. When a segment's result isn't
> significant, it says so.

### [2:52 – 3:36]  Why it helps Razorpay

> Why does this fit Razorpay specifically. The bar for this track is that every
> money action is explainable, bounded, and gated. That's the design. The caps
> are constants in the pricing file. The SHAP values are on every response. The
> merchant gates each lever.
>
> And it runs on data Razorpay already holds. Right now the trust signals —
> cross-merchant payment success, COD completion, account age — come in on the
> request. In production those are a server-side lookup Razorpay already owns, so
> they can't be spoofed, and the whole thing becomes one call at checkout render,
> before payment starts. The repo's public, front end's on Vercel, API's on
> Render.

### [3:36 – 4:34]  Track 4 — Cash Flow Oracle

> Last thing, quickly. Track 4, the finance controller.
>
> Razorpay Capital is reactive. A merchant applies for credit when they're
> already short. But the signal that they're heading for a crunch is in their
> settlement stream weeks earlier.
>
> So I built a forecaster. Thirty synthetic merchants, three years of daily
> settlements. GARCH for the volatility, a hidden Markov model for the season,
> Prophet for the forward curve.
>
> `[Cash Flow Oracle tab, GigaMart selected]`
>
> For this merchant it flags a fifteen-day cash squeeze starting September
> twenty-first — the balance drops about forty-seven lakh short of the operating
> floor at the low point. It works backwards from Capital's disbursement time to
> one date, apply by the twenty-seventh, and it shows that borrowing early beats
> the late-payment penalty by around thirty-two thousand rupees. The forecast
> error is on the page, twenty-six percent on
> held-out days, and the model flags when it's running on fallbacks. That's the
> honest exception list the track asks for.

### [4:34 – 4:44]  Close

> Both are live, both have an architecture doc, and the repo's public. Thanks for
> watching.

---

## Timing

| Section | Starts | ~Time | Screen |
|---|---|---|---|
| Open | 0:00 | 12s | seller dashboard |
| Problem + data | 0:12 | 54s | seller dashboard (talk to camera) |
| Product | 1:06 | 106s | checkout ×2 → merchant A/B panel |
| Why it helps Razorpay | 2:52 | 44s | stay on A/B panel or cut to code |
| Track 4 | 3:36 | 58s | Cash Flow Oracle |
| Close | 4:34 | 10s | anything |
| **Total** | | **≈ 4:44** | |

---

## Delivery notes

- **Pace:** ~145 wpm is relaxed. If you talk fast you have slack; if slow, use
  the cut list below.
- **Two lines to land.** Pause a full second after *"what's actually stopping
  them from paying"* and after *"explainable, bounded, and gated."* Everything
  else can move at pace.
- **Don't read panels aloud.** Point at the SHAP explanation, say "the merchant
  sees why," move on. Same for the A/B numbers — gesture, don't recite.
- **The tab switches are the fragile part.** All four tabs pre-loaded, know the
  click order, practice the two checkout switches until they're muscle memory.
- **Screen recording > webcam-in-corner.** The dashboards are the story. A small
  face cam is fine; a big one isn't.
- Say the friction names as plain English ("price sensitivity", "wants a quality
  signal"), not as `snake_case` field names.

## If you run past 5:00, cut in this order

1. *"with a market-price reference above it"* in the product section — 3s
2. The last sentence of "why it helps Razorpay" (Vercel / Render) — 5s
3. Collapse the three "point at" items to two: drop the SHAP one, since
   "explainable" is covered in the next section — 8s
4. In Track 4, drop *"three years of daily settlements"* — 3s

## Numbers to re-read on recording day (Track 4 only)

Open your chosen merchant in the Cash Flow Oracle (GigaMart, or whichever
currently has a "Next stress period" that isn't "None") and read, in order: the
stress-period **start date** and **length**, the **shortfall at the trough**,
the **apply-by date**, the **net benefit** on the credit card, and the **MAPE**
on the third stat card. Drop them into the Track 4 lines. Everything in Track 01
is stable.

## Optional: bump merchant count to match the brief exactly

The Track 4 brief says *"50+ synthetic records."* You have 30 merchants (about
33,000 settlement rows, which clears it at the row level). If you'd rather the
merchant count itself read as 50+, set `MERCHANTS_PER_ARCHETYPE = 10` in
`cash-flow-oracle/config.py`, reseed, redeploy — say the word and I'll do it.
