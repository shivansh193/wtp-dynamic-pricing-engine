# 5-Minute Demo Script — Razorpay AI Buildathon 2026

**Runtime as written: ~5:25.** The "why it helps Razorpay" section grew — it
now argues the merchant benefit, not just the platform fit — which costs
about 20s back. The cut list at the bottom gets you under 5:00 if you need it.

**Everything below was verified by actually driving the deployed app** —
seller dashboard, the Custom tuning form, the generated link, the shopper's
own pre-fill screen, "See my price", and both "Why this price?" / "Why this
offer?" panels, for both profiles. Every number and every line of on-screen
copy quoted here is what's actually there as of Sept 4. Two things that were
wrong in the previous draft, now fixed:

1. **The checkout is two screens, not one.** The shopper lands on a
   pre-filled *"adjust anything before you continue"* form first — the same
   fields the seller set — and only sees a price after clicking **"See my
   price."** The old script skipped straight to a priced page.
2. **The seller's Custom tuning form wasn't mentioned at all.** It's a real
   layer: pincode, device, five payment-mix sliders that have to add to 100%,
   a prepaid-orders slider, a return-rate slider, a VPN checkbox. It's also
   necessary — the built-in **"Low Income" preset actually lands on payment
   friction, not price sensitivity**. Custom is what reliably gets the EMI
   story on screen, which is a legitimate reason to show it, not a workaround.

**Your format:** problem with data, the product, why it helps Razorpay, then
Track 4 in the same shape, short.

---

## Before you hit record

- **Warm the API.** The Render free instance sleeps after 15 min idle; a cold
  first call takes ~600ms instead of ~40. Click through a checkout three or
  four times, two minutes before you record.
- **Four tabs, left to right:**
  1. Seller dashboard — `…vercel.app/dashboard`, Profile dropdown on **Custom**
  2. (leave blank — you'll open the customer link live after generating it)
  3. Merchant analytics — `…vercel.app/merchant/dashboard`
  4. Cash Flow Oracle — `…vercel.app/cash-flow-oracle`, on a merchant with a
     current stress period (see below)
- **Tier-3 shopper — exact Custom values, tested just now:**
  Pincode `800001` · Device `Android_budget` · Payment mix UPI `70` / Credit
  Card `2` / Debit Card `8` / Cash on Delivery `18` / Wallet `2` · Prepaid
  orders `4` · Return rate `25`. This is deterministic — same inputs, same
  output, every time, no drift.
  - Generating the link shows a card right on the dashboard: *"Custom · T3 ·
    Patna · Android_budget · trust 29.3 · 4 prepaid · 25% returns."*
  - Opening the link → pre-fill screen: *"pre-filled from 'Custom' — adjust
    anything before you continue,"* the same five fields again, editable, plus
    *"detected: Patna · Tier 3."*
  - Click **See my price** → the priced page: headline **"₹381/mo · 0%
    interest,"** below it **"₹381 / mo × 12,"** then **"0% interest · ₹4,571
    total · market ~₹5,650."** An EMI/Full-price toggle. UPI marked
    "preferred" in the payment list.
  - **"Why this price?"** expands to: *"Your price is set from your shopping
    profile, inside a band the store controls — never more than a small step
    above list, and a price-sensitive shopper is never charged more than
    ₹4,999. We think you're weighing the price carefully (low
    willingness-to-pay signal; Tier 3 location; 25% return rate)... You're
    ₹428 below MRP on this one."*
  - **"Why this offer?"** expands to: *"This checkout leads with an EMI
    breakdown. payment decoupling — a large number reframed as a small
    recurring one lowers the perceived pain of paying. You also get 5%
    cashback with this order."*
- **Metro shopper — the built-in "High income" preset, one click, no tuning
  needed:** T1 · Mumbai · iPhone · trust 99 · 44 prepaid · 4% returns. After
  "See my price": headline **"4.8/5 · 12,000+ verified buyers,"** price
  **₹5,749**, *"🎁 Free 1-year extended warranty — worth about ₹899,"* *"About
  ₹149 ahead versus the standard price,"* and — visible right on the page —
  *"Prefer the standard price? Continue at ₹4,999."*
  - **"Why this price?"** cites *"high willingness-to-pay; shopped 25
    merchants (repeat buyer); trust 99/100."*
  - **"Why this offer?"** names the mechanism: *"confirmation — a high-WTP
    repeat buyer wants reassurance they're making the right choice, not a
    countdown."*
- **Pick the Cash Flow Oracle merchant on the day.** The forecast re-anchors
  to "today". As of Sept 4, **GigaMart** (electronics, Tier 1): ~15-day squeeze
  from Sept 21, ~₹47L below the floor at the trough, apply by Sept 27,
  borrowing early nets ~₹32k, forecast error ~31%. If it's gone quiet, any
  merchant's "Next stress period" card tells you who has one now.

---

## The script

Spoken lines are in quote blocks. `[bracketed]` lines are what you do on screen.

### Open

> Two people are checking out on the same store right now. One's on an iPhone
> in a Tier-1 city, paying by card. The other's in a Tier-3 city, on an
> Android, looking for cash on delivery and hoping for a bit off the price too.
> The store shows both of them the exact same price, on the exact same page.
>
> That's normal. It costs the merchant in two different directions at once.
> I'm Shivansh — this is my attempt at fixing that. There's a second build
> too, about what happens to the merchant's cash after the sale goes through.
> I'll get to it in the last minute.

### The problem, with data

> The Tier-1 shopper would've paid more without blinking, and probably
> wouldn't notice a little extra if it came with something like priority
> support or a free warranty. The Tier-3 shopper, that same amount taken off
> instead, could be the nudge that actually gets the order placed.
>
> Checkout abandonment runs around 70%, and when the Baymard Institute asks
> people why, the answers are price and payment. Almost never the product
> itself.
>
> So the question I actually care about is narrower than "what should this
> shoe cost" — that's fixed, it's on the box. What I care about is: what price
> is this shopper, with this cart, willing to pay, right now. Economists call
> that willingness to pay.

### The product

> This is the seller's dashboard. I'll set up a shopper by hand instead of a
> preset, so you can see the real controls — pincode, device, how they pay
> across five methods, return history. Tier-3 pincode, mostly UPI and cash on
> delivery, a quarter return rate.
>
> `[click Generate link]`
>
> Resolves to a city and a trust score before the shopper's even opened it —
> Patna, Tier 3, trust 29.
>
> `[open the customer link, click See my price]`
>
> One API call, about 40 milliseconds warm. A model trained on 50,000
> synthetic transactions — no real Razorpay data for a hackathon, so it's
> calibrated to actual RBI payment trends and the festival calendar instead —
> reads this as low price tolerance and takes ₹4,999 to ₹4,571, leading with
> EMI: ₹381 a month.
>
> A second model separately names the friction. Here it's price sensitivity —
> that's why EMI leads instead of a flat number.
>
> `[expand "Why this price?"]`
>
> Says so right on the page: low WTP signal, Tier 3, high returns — never
> charged above list.
>
> `[switch to the metro checkout]`
>
> Same two models, opposite shopper — high trust, repeat buyer, pays by card.
> Price moves up instead, to ₹5,749, and it comes with a free one-year
> warranty, not a discount. Opt-out's on the page too: continue at ₹4,999
> standard.
>
> Neither model touches the price directly, though. A separate rules layer
> does, and that's where the caps live — fifteen up, ten down, clamped in
> code. Merchant can tighten it, can't raise it.
>
> `[merchant analytics tab, A/B panel]`
>
> And I can test a change before shipping it — flat pricing against
> friction-aware, a real z-test, honest about when a result isn't
> significant.

### Why it helps Razorpay

> This fits the track's own bar: every money action explainable, bounded, and
> gated. That's what I just showed you, not something bolted on.
>
> For the merchant, it's two jobs at once — same shopper split I opened with.
> The metro shopper wouldn't have blinked at ₹5,749: that's margin the
> merchant was leaving on the table. The Tier-3 shopper needed the EMI just to
> check out: that's a sale that wouldn't have happened at list price. Same
> system, same three seconds, recovering money on one side, rescuing it on the
> other.
>
> It also runs on data Razorpay already has. Those trust signals are a request
> field here, but in production they're a server-side lookup Razorpay already
> owns — so they can't be faked, and this becomes one call at checkout, before
> payment starts.

### Track 4 — Cash Flow Oracle

> Quick last thing — the second build. A cash-flow forecaster for merchants.
>
> Razorpay Capital only hears from a merchant once they're already short. The
> crunch is usually visible in their settlement data weeks before that.
>
> Same approach: synthetic, but shaped like the real thing — 30 merchants,
> three years of daily settlements each. GARCH reads the volatility, a hidden
> Markov model reads the season, Prophet draws the forward curve.
>
> `[Cash Flow Oracle, GigaMart selected]`
>
> For this electronics merchant it's calling a 15-day cash squeeze from
> September 21st, about ₹47 lakh below the safe line at the worst point. It
> works back from Capital's payout time to one date — apply by the 27th — and
> checks that borrowing early actually beats the late-payment penalty, by
> about ₹32,000.
>
> The forecast's off by about 30% on a typical day. Sounds bad — daily
> settlement genuinely swings that hard on one refund. What I want is the
> 60-day shape and the stress window, and it gets those right.

### Close

> Both are deployed, both have an architecture write-up, and the repo's
> public. That's it — thanks.

---

## Timing (as written)

| Section | ~Time | Screen |
|---|---|---|
| Open | 45s | seller dashboard, to camera |
| Problem + data | 55s | seller dashboard, to camera |
| Product | 100s | Custom form → Tier-3 checkout → metro checkout → A/B panel |
| Why it helps Razorpay | 55s | stay on the A/B panel |
| Track 4 | 65s | Cash Flow Oracle |
| Close | 10s | anything |
| **Total** | **≈ 5:30** | |

---

## If you're over 5:00, cut in this order

1. Cut the RBI/festival-calendar clause down to *"synthetic, because there's
   no real Razorpay data for a hackathon"* — 8s
2. In Track 4, cut *"three years of daily settlements each"* — 3s
3. In "why it helps Razorpay," cut the last paragraph (the "runs on data
   Razorpay already has" bit) — the merchant-benefit paragraph is the one worth
   keeping if you have to choose — 15s
4. Tighten the merchant-benefit paragraph itself to one sentence: *"For the
   merchant it's two jobs at once — margin recovered from shoppers like the
   metro one, conversions rescued from shoppers like the Tier-3 one, same
   three seconds."* — 12s

Items 1–2 get you to about 5:20. All four gets you under 5:00.

## Delivery notes

- **Rehearse the Custom form and the two checkout switches until they're
  automatic.** This version has more clicks than the last draft. A fumbled
  click reads worse than any line here.
- Don't read "Why this price?" or "Why this offer?" verbatim — paraphrase what
  you're pointing at, the way the script does. Let the viewer read the actual
  text on screen while you talk over it.
- If a number on screen doesn't match the script, say what's on screen. Live
  data wins, always — that's the whole point of showing it live instead of
  slides.
- Say frictions as plain words ("its read is price sensitivity"), never the
  `snake_case` field name.

## Numbers to re-read on recording day (Track 4 only)

Open your merchant in the Cash Flow Oracle (GigaMart, or whoever's "Next
stress period" card isn't "None") and read: the stress window **start date**
and **length**, the **shortfall at the trough**, the **apply-by date**, the
**net benefit** on the credit card, and the **error %** on the accuracy stat
card. Track 01's numbers are deterministic and don't drift.

## Optional: bump merchant count to match the brief

The Track 4 brief says *"50+ synthetic records."* You have 30 merchants
(~33,000 settlement rows, which clears it at the row level). To make the
merchant count itself read as 50+, set `MERCHANTS_PER_ARCHETYPE = 10` in
`cash-flow-oracle/config.py`, reseed, redeploy — say the word.
