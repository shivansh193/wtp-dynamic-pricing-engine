"""
Analytics for the Cash Flow Oracle `/oracle/*` endpoints.

Everything here is a pure function over numpy arrays / plain dicts so it can be
unit-tested without a DB or a running server (see tests/test_cash_flow_oracle.py).
The route layer in `oracle_routes.py` fetches rows, calls these, and shapes the
HTTP response.
"""

from __future__ import annotations

import math
import uuid
from datetime import date, datetime, timedelta

import numpy as np

from .. import config as C
from ..models.garch import fit_garch
from ..models.forecast_prophet import forecast as run_forecast
from .festivals import (
    FINGERPRINT_FESTIVALS,
    festival_window_dates,
    major_festivals,
    nearest_festival,
)

# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _as_date(v) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    return datetime.fromisoformat(str(v)[:10]).date()


def inr(x: float) -> str:
    x = float(x)
    if abs(x) >= 1e7:
        return f"₹{x / 1e7:.2f}Cr"
    if abs(x) >= 1e5:
        return f"₹{x / 1e5:.2f}L"
    return f"₹{x:,.0f}"


def _pct_rank(value: float, population: list[float]) -> float:
    """Fraction of the population strictly below `value` (0..1)."""
    pop = [p for p in population if p is not None]
    if not pop:
        return 0.5
    return float(np.mean([1.0 if p < value else 0.0 for p in pop]))


# --------------------------------------------------------------------------- #
# regime confidence + context
# --------------------------------------------------------------------------- #
REGIME_BLURB = {
    "fashion": {
        "high_season": "Fashion merchants in peak season (Diwali / wedding months) "
        "run 40-90% above their annual daily average.",
        "low_season": "Fashion merchants in low season typically see 18-24% lower "
        "settlement volumes, deepest in Jan-Feb.",
        "stress": "Elevated refund activity and volatile daily settlements - treat "
        "the lower forecast band as the planning number.",
    },
    "electronics": {
        "high_season": "Electronics settlements spike hardest in Oct-Nov, often "
        "2x the annual daily average, then fall off sharply.",
        "low_season": "Post-festival lull - electronics merchants commonly see "
        "25-35% below-average settlements into Dec-Jan.",
        "stress": "Chargeback / RMA waves and gateway variance are inflating "
        "volatility; hold a wider buffer.",
    },
    "grocery": {
        "high_season": "Grocery is near-flat; a 'high' regime here is a modest "
        "10-15% festive bump.",
        "low_season": "Mild dip, usually monsoon-driven (Jul-Aug), around 8% "
        "below average.",
        "stress": "Unusual for grocery - likely a supply or gateway disruption.",
    },
    "home": {
        "high_season": "Home & furniture peaks at FY-end (March) and Diwali - "
        "expect 30-70% above the daily average.",
        "low_season": "Monsoon months soften demand 15-20%; delivery timelines "
        "also stretch.",
        "stress": "Large-ticket refunds hit hard - a single cancelled order can "
        "swing a day's settlement.",
    },
    "services": {
        "high_season": "Subscription / services revenue is steady; a 'high' "
        "regime is a 10-15% lift, often June or Q4.",
        "low_season": "Low churn but flat growth - a few percent below average.",
        "stress": "Involuntary churn spike or a billing-gateway issue.",
    },
}


def regime_confidence(labels: list[str], current: str) -> float:
    """Confidence in the current regime call.

    hmmlearn gives real posteriors; the fallback doesn't, so we use a
    persistence proxy: the share of the last 21 days that agree with the
    current label, lightly weighted toward the most recent week."""
    if not labels:
        return 0.34
    tail = labels[-21:]
    agree = np.mean([1.0 if l == current else 0.0 for l in tail])
    recent = np.mean([1.0 if l == current else 0.0 for l in labels[-7:]])
    conf = 0.35 + 0.45 * float(agree) + 0.20 * float(recent)
    return round(min(0.99, max(0.34, conf)), 3)


def regime_history(dates: list[date], labels: list[str], days: int = 90) -> list[dict]:
    out = []
    for d, l in list(zip(dates, labels))[-days:]:
        out.append({"date": _as_date(d).isoformat(), "regime": l})
    return out


def regime_description(category: str, regime: str) -> str:
    return REGIME_BLURB.get(category, {}).get(
        regime, f"{regime.replace('_', ' ').title()} regime for this merchant.")


# --------------------------------------------------------------------------- #
# anomaly detection  (deviation from a GARCH-implied settlement band)
# --------------------------------------------------------------------------- #
def _expected_and_sigma(dates: list[date], net: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-day expected settlement (deseasonalised trailing median x day-of-week
    factor) and a 1-sigma band in rupees from the GARCH conditional return vol."""
    n = net.size
    dow = np.array([_as_date(d).weekday() for d in dates])
    base = float(np.median(net[net > 0])) if np.any(net > 0) else float(np.median(net))
    dow_factor = np.array([
        (np.median(net[dow == k]) / base) if np.any(dow == k) else 1.0 for k in range(7)
    ])
    # 28-day trailing median as the level (robust to spikes), shifted by 1 so
    # "expected" doesn't peek at the day itself
    level = np.empty(n)
    for i in range(n):
        lo = max(0, i - 28)
        level[i] = np.median(net[lo:i]) if i > lo else net[i]
    expected = level * dow_factor[dow]

    g = fit_garch(net)
    cv = g.conditional_vol
    if cv.size < n:
        cv = np.concatenate([np.full(n - cv.size, cv[0] if cv.size else 0.02), cv])
    sigma = expected * np.clip(cv[-n:], 0.02, 1.5)
    return expected, np.maximum(sigma, expected * 0.02)


def anomaly_scan(dates: list[date], net: np.ndarray, *, lookback_days: int = 30,
                 sigma_threshold: float = C.ANOMALY_SIGMA_FEED,
                 category: str = "") -> list[dict]:
    dates = [_as_date(d) for d in dates]
    net = np.asarray(net, dtype=float)
    expected, sigma = _expected_and_sigma(dates, net)
    out: list[dict] = []
    start = max(0, net.size - lookback_days)
    for i in range(start, net.size):
        dev = (net[i] - expected[i]) / sigma[i] if sigma[i] > 0 else 0.0
        if abs(dev) < sigma_threshold:
            continue
        direction = "above" if dev > 0 else "below"
        out.append({
            "date": dates[i].isoformat(),
            "direction": direction,
            "kind": "SPIKE" if dev > 0 else "DIP",
            "magnitude_sigma": round(float(dev), 2),
            "actual_inr": round(float(net[i]), 2),
            "expected_inr": round(float(expected[i]), 2),
            "explanation": _explain_anomaly(dates[i], direction, category),
        })
    out.sort(key=lambda r: r["date"], reverse=True)
    return out


def _explain_anomaly(d: date, direction: str, category: str) -> str:
    fest = nearest_festival(d, window_days=12)
    if fest and direction == "above":
        return f"Settlement spike likely related to the {fest} festival period."
    if fest and direction == "below":
        return (f"Settlement dip just after {fest} - the usual post-festival "
                "pull-forward correction.")
    if d.month == 3 and d.day >= 18 and direction == "above":
        return "Settlement surge consistent with the March financial-year-end push."
    if d.month in (6, 7, 8, 9) and direction == "below":
        return "Settlement dip in line with the monsoon-season demand softening."
    if d.weekday() >= 5 and direction == "above" and category in ("fashion", "home"):
        return "Weekend settlement spike - typical for discretionary retail."
    if direction == "below":
        return ("Settlement dip: possible payment-gateway latency window or a "
                "batch settlement that slipped to the next day.")
    return ("Settlement spike: a large single order or a delayed batch clearing "
            "on this date.")


def current_week_anomaly(dates: list[date], net: np.ndarray, *,
                         sigma_threshold: float = C.ANOMALY_SIGMA_FORECAST_FLAG,
                         category: str = "") -> tuple[bool, str | None]:
    """Does the last 7 days' mean settlement deviate > threshold sigma from the
    GARCH-implied expectation for that week?"""
    dates = [_as_date(d) for d in dates]
    net = np.asarray(net, dtype=float)
    if net.size < 35:
        return False, None
    expected, sigma = _expected_and_sigma(dates, net)
    wk_actual = float(np.mean(net[-7:]))
    wk_expected = float(np.mean(expected[-7:]))
    wk_sigma = float(np.mean(sigma[-7:])) / math.sqrt(7)  # SE of the weekly mean
    if wk_sigma <= 0:
        return False, None
    dev = (wk_actual - wk_expected) / wk_sigma
    if abs(dev) < sigma_threshold:
        return False, None
    direction = "above" if dev > 0 else "below"
    base = _explain_anomaly(dates[-1], direction, category)
    return True, (f"This week's settlements are running {abs(dev):.1f}σ {direction} "
                  f"the expected level ({inr(wk_actual)}/day vs {inr(wk_expected)} "
                  f"expected). {base}")


# --------------------------------------------------------------------------- #
# cash-position curve + stress periods
# --------------------------------------------------------------------------- #
def cash_position_curve(hist_dates: list[date], hist_net: np.ndarray,
                        fc_dates: list[date], fc_yhat: np.ndarray,
                        fc_lower: np.ndarray, fc_upper: np.ndarray,
                        *, opening_balance: float, daily_burn: float,
                        regime_current: str, hist_window: int = 30) -> list[dict]:
    """Reconstruct the trailing balance and project it forward.

    balance[t] = balance[t-1] + settlement[t] - daily_burn
    'today' is anchored at `opening_balance`; history is walked backwards,
    forecast forwards (with cumulative lower/upper bands)."""
    hist_dates = [_as_date(d) for d in hist_dates][-hist_window:]
    hist_net = np.asarray(hist_net, dtype=float)[-hist_window:]

    hist_points: list[dict] = []
    bal = float(opening_balance)
    # walk backwards from today
    rev = []
    b = bal
    for i in range(len(hist_net) - 1, -1, -1):
        rev.append((hist_dates[i], b))
        b = b - float(hist_net[i]) + daily_burn
    for d, v in reversed(rev):
        hist_points.append({"date": d.isoformat(), "balance": round(v, 2),
                            "lower": round(v, 2), "upper": round(v, 2),
                            "is_forecast": False, "regime": regime_current})

    # cumulative point forecast for the balance; the band grows as the
    # root-sum-square of the daily half-widths (errors partly cancel) rather
    # than their linear sum, so a 60-day horizon doesn't produce an absurd band
    fc_points: list[dict] = []
    run = bal
    var_acc = 0.0
    for i, d in enumerate(fc_dates):
        run = run + float(fc_yhat[i]) - daily_burn
        half = max(0.0, (float(fc_upper[i]) - float(fc_lower[i])) / 2.0)
        var_acc += half * half
        band = math.sqrt(var_acc)
        fc_points.append({"date": _as_date(d).isoformat(), "balance": round(run, 2),
                          "lower": round(run - band, 2), "upper": round(run + band, 2),
                          "is_forecast": True, "regime": regime_current})
    return hist_points + fc_points


def cash_stress_periods(curve: list[dict], threshold: float,
                        min_days: int = 3) -> list[dict]:
    """Contiguous forecast runs (>= min_days) where expected balance < threshold."""
    fc = [p for p in curve if p["is_forecast"]]
    out: list[dict] = []
    run: list[dict] = []

    def flush():
        if len(run) < min_days:
            return
        trough = min(run, key=lambda p: p["balance"])
        out.append({
            "start": run[0]["date"], "end": run[-1]["date"], "days": len(run),
            "trough_date": trough["date"],
            "trough_balance": trough["balance"],
            "min_balance_lower": round(min(p["lower"] for p in run), 2),
            "shortfall_at_trough": round(max(0.0, threshold - trough["balance"]), 2),
        })

    for p in fc:
        if p["balance"] < threshold:
            run.append(p)
        else:
            flush()
            run = []
    flush()
    return out


def days_until_stress(curve: list[dict], stress: list[dict]) -> int | None:
    if not stress:
        return None
    today = date.today()
    first = _as_date(stress[0]["start"])
    return max(0, (first - today).days)


# --------------------------------------------------------------------------- #
# forecast accuracy (walk-forward MAPE on the last 30 days)
# --------------------------------------------------------------------------- #
def backtest_mape(dates: list[date], net: np.ndarray, holdout: int = 30) -> float | None:
    net = np.asarray(net, dtype=float)
    if net.size < holdout + 120:
        return None
    train_d = [_as_date(x) for x in dates[:-holdout]]
    train_y = net[:-holdout]
    actual = net[-holdout:]
    fc = run_forecast(train_d, train_y, holdout)
    pred = np.asarray(fc.yhat, dtype=float)
    denom = np.where(actual == 0, np.nan, actual)
    mape = np.nanmean(np.abs((actual - pred) / denom)) * 100.0
    return round(float(mape), 2)


# --------------------------------------------------------------------------- #
# peer benchmarking
# --------------------------------------------------------------------------- #
def peer_comparison(me: dict, all_merchants: list[dict], *, stress_freq_fn=None) -> dict:
    """Position `me` against same-category (+ same-tier when the group is big
    enough) peers on volatility and average daily settlement.

    `stress_freq_fn(merchant_dict) -> float | None` estimates stress periods per
    year; called with the full merchant row, not just the id."""
    cat = me.get("archetype")
    tier = me.get("city_tier")
    same_cat = [m for m in all_merchants
                if m.get("archetype") == cat and m["merchant_id"] != me["merchant_id"]]
    same_tier = [m for m in same_cat if m.get("city_tier") == tier]
    peers = same_tier if len(same_tier) >= 3 else same_cat
    grouping = ("same category, Tier %s" % tier) if peers is same_tier \
        else "same category (all tiers)"

    vol_pop = [float(m["settlement_volatility"]) for m in peers
               if m.get("settlement_volatility") is not None]
    avg_pop = [float(m["avg_daily_settlement"]) for m in peers
               if m.get("avg_daily_settlement") is not None]
    my_vol = float(me.get("settlement_volatility") or 0.0)
    my_avg = float(me.get("avg_daily_settlement") or 0.0)

    vol_pct = _pct_rank(my_vol, vol_pop)
    avg_pct = _pct_rank(my_avg, avg_pop)

    out = {
        "peer_group": grouping,
        "n_peers": len(peers),
        "category": cat,
        "city_tier": tier,
        "volatility": {
            "you": round(my_vol, 4),
            "peer_avg": round(float(np.mean(vol_pop)), 4) if vol_pop else None,
            "peer_min": round(float(np.min(vol_pop)), 4) if vol_pop else None,
            "peer_max": round(float(np.max(vol_pop)), 4) if vol_pop else None,
            "percentile": round(vol_pct * 100, 1),
            "distribution": [round(v, 4) for v in sorted(vol_pop)],
            "plain": _peer_plain("settlement volatility", vol_pct, cat, tier,
                                 higher_is_worse=True),
        },
        "avg_daily_settlement": {
            "you": round(my_avg, 2),
            "peer_avg": round(float(np.mean(avg_pop)), 2) if avg_pop else None,
            "peer_min": round(float(np.min(avg_pop)), 2) if avg_pop else None,
            "peer_max": round(float(np.max(avg_pop)), 2) if avg_pop else None,
            "percentile": round(avg_pct * 100, 1),
            "distribution": [round(v, 2) for v in sorted(avg_pop)],
            "plain": _peer_plain("average daily settlement", avg_pct, cat, tier,
                                 higher_is_worse=False),
        },
    }
    if stress_freq_fn is not None:
        mine = stress_freq_fn(me)
        peer_vals = [stress_freq_fn(m) for m in peers]
        peer_vals = [v for v in peer_vals if v is not None]
        out["stress_frequency"] = {
            "you_per_year": round(mine, 1) if mine is not None else None,
            "peer_avg_per_year": round(float(np.mean(peer_vals)), 1) if peer_vals else None,
            "plain": (
                f"You hit a stress period about {mine:.0f}x/year; similar "
                f"merchants average {np.mean(peer_vals):.0f}x."
                if mine is not None and peer_vals else
                "Not enough history to compare stress frequency."
            ),
        }
    return out


def _peer_plain(metric: str, pct: float, cat: str, tier, *, higher_is_worse: bool) -> str:
    where = f"similar {cat} merchants in Tier {tier} cities" if tier else \
        f"similar {cat} merchants"
    if higher_is_worse:
        return (f"Your {metric} is higher than {pct * 100:.0f}% of {where} - "
                f"{'watch the downside band' if pct > 0.6 else 'in a comfortable range'}.")
    return (f"Your {metric} is higher than {pct * 100:.0f}% of {where}.")


# --------------------------------------------------------------------------- #
# settlement fingerprint + festival response curves
# --------------------------------------------------------------------------- #
def settlement_fingerprint(dates: list[date], net: np.ndarray) -> dict:
    """7x52 matrix: mean settlement intensity by (weekday, ISO week), 0-1 norm."""
    dates = [_as_date(d) for d in dates]
    net = np.asarray(net, dtype=float)
    acc = np.zeros((7, 53))
    cnt = np.zeros((7, 53))
    for d, y in zip(dates, net):
        wk = min(d.isocalendar()[1], 53)
        acc[d.weekday(), wk - 1] += y
        cnt[d.weekday(), wk - 1] += 1
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(cnt > 0, acc / cnt, np.nan)
    lo = np.nanmin(mean)
    hi = np.nanmax(mean)
    norm = (mean - lo) / (hi - lo) if hi > lo else np.zeros_like(mean)
    matrix = [[None if np.isnan(mean[r, c]) else round(float(norm[r, c]), 3)
               for c in range(52)] for r in range(7)]
    raw = [[None if np.isnan(mean[r, c]) else round(float(mean[r, c]), 2)
            for c in range(52)] for r in range(7)]
    return {
        "weekday_labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "week_count": 52,
        "matrix": matrix,      # normalised 0-1
        "raw_inr": raw,        # for the tooltip
    }


def festival_response_curves(dates: list[date], net: np.ndarray) -> dict:
    """For each headline festival: settlement multiplier vs the annual weekly
    mean, for the 4 weeks around the festival, averaged across all years in the
    data."""
    dates = [_as_date(d) for d in dates]
    net = np.asarray(net, dtype=float)
    if net.size < 200:
        return {"weeks_offset": list(range(-2, 3)), "curves": {}}

    # weekly totals keyed by (iso_year, iso_week)
    wk_total: dict[tuple[int, int], float] = {}
    for d, y in zip(dates, net):
        iy, iw, _ = d.isocalendar()
        wk_total[(iy, iw)] = wk_total.get((iy, iw), 0.0) + float(y)
    base = float(np.mean(list(wk_total.values()))) if wk_total else 1.0

    years = sorted({d.year for d in dates})
    offsets = list(range(-2, 3))
    curves: dict[str, list[float]] = {}
    for name in FINGERPRINT_FESTIVALS:
        acc = {o: [] for o in offsets}
        for yr in years:
            anchor, _, _ = festival_window_dates(name, yr, weeks_each_side=2)
            for o in offsets:
                wd = anchor + timedelta(weeks=o)
                iy, iw, _ = wd.isocalendar()
                tot = wk_total.get((iy, iw))
                if tot is not None and base > 0:
                    acc[o].append(tot / base)
        curves[name] = [round(float(np.mean(acc[o])), 3) if acc[o] else None
                        for o in offsets]
    return {"weeks_offset": offsets, "curves": curves}


# --------------------------------------------------------------------------- #
# credit timing + carry-cost
# --------------------------------------------------------------------------- #
def credit_apply_by_date(trough_date: date | None, disbursement_days: int) -> date | None:
    if trough_date is None:
        return None
    return _as_date(trough_date) - timedelta(days=int(disbursement_days))


def carry_cost_analysis(*, shortfall_inr: float, days_early: int,
                        borrow_cost_pct_month: float, penalty_pct_month: float,
                        penalty_base_inr: float | None = None,
                        penalty_months: float = 1.0) -> dict:
    """Cost of drawing Razorpay Capital early vs the cost of paying suppliers /
    obligations late.

      carry_cost      = shortfall x borrow_rate x (days_early / 30)
      penalty_avoided = penalty_base x penalty_rate x penalty_months
      net_benefit     = penalty_avoided - carry_cost      (>0 => borrow early)
    """
    shortfall_inr = max(0.0, float(shortfall_inr))
    days_early = max(0, int(days_early))
    penalty_base = float(penalty_base_inr if penalty_base_inr is not None else shortfall_inr)

    carry_cost = shortfall_inr * (borrow_cost_pct_month / 100.0) * (days_early / 30.0)
    penalty_avoided = penalty_base * (penalty_pct_month / 100.0) * penalty_months
    net_benefit = penalty_avoided - carry_cost
    borrow = net_benefit > 0

    if shortfall_inr <= 0:
        rec = ("No shortfall is projected - no borrowing needed. Keep the line "
               "available but undrawn.")
    elif borrow:
        rec = (f"Draw {inr(shortfall_inr)} of Razorpay Capital ~{days_early} days "
               f"early. The ~{inr(carry_cost)} of carry cost is well below the "
               f"~{inr(penalty_avoided)} in late-payment penalties you'd otherwise "
               f"incur - a net gain of about {inr(net_benefit)}.")
    else:
        rec = (f"Borrowing {inr(shortfall_inr)} this early costs ~{inr(carry_cost)} "
               f"in carry, more than the ~{inr(penalty_avoided)} penalty exposure. "
               f"Delay the draw or size it smaller; net cost of borrowing now is "
               f"~{inr(-net_benefit)}.")
    return {
        "shortfall_inr": round(shortfall_inr, 2),
        "days_early": days_early,
        "borrow_cost_pct_month": borrow_cost_pct_month,
        "penalty_pct_month": penalty_pct_month,
        "carry_cost_inr": round(carry_cost, 2),
        "late_payment_penalty_avoided_inr": round(penalty_avoided, 2),
        "net_benefit_inr": round(net_benefit, 2),
        "recommendation": "borrow_early" if borrow else "delay_or_downsize",
        "explanation": rec,
    }


# --------------------------------------------------------------------------- #
# scenario simulator
# --------------------------------------------------------------------------- #
# (sign, in-window gain fraction of magnitude, post-window tail fraction, tail days)
SHOCK_SHAPES = {
    "discount_sale":          (+1, 0.60, -0.20, 10),   # volume up, then pull-forward dip
    "marketing_spend":        (+1, 0.50, +0.20, 14),   # lift during + halo after
    "inventory_purchase":     (-1, 0.55, +0.10, 7),    # cash diverted, mild rebound
    "payment_gateway_outage": (-1, 0.90, +0.30, 5),    # hard drop, delayed catch-up
}


def apply_scenario_shock(fc_dates: list[date], fc_yhat: np.ndarray,
                         fc_lower: np.ndarray, fc_upper: np.ndarray, *,
                         shock_type: str, magnitude_pct: float,
                         shock_start: date, duration_days: int
                         ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return shocked (yhat, lower, upper) - a multiplicative factor over the
    shock window, plus a decaying tail."""
    sign, in_frac, tail_frac, tail_days = SHOCK_SHAPES.get(
        shock_type, (+1, 0.5, 0.0, 0))
    mag = abs(float(magnitude_pct)) / 100.0
    shock_start = _as_date(shock_start)
    win_end = shock_start + timedelta(days=int(duration_days) - 1)
    tail_end = win_end + timedelta(days=tail_days)

    factor = np.ones(len(fc_dates))
    for i, d in enumerate(fc_dates):
        d = _as_date(d)
        if shock_start <= d <= win_end:
            factor[i] = 1.0 + sign * in_frac * mag
        elif win_end < d <= tail_end and tail_days > 0:
            decay = 1.0 - (d - win_end).days / (tail_days + 1)
            factor[i] = 1.0 + sign * tail_frac * mag * max(0.0, decay)
    return (np.asarray(fc_yhat) * factor,
            np.asarray(fc_lower) * factor,
            np.asarray(fc_upper) * factor)


def new_scenario_id() -> str:
    return "scn_" + uuid.uuid4().hex[:12]


# --------------------------------------------------------------------------- #
# alert urgency
# --------------------------------------------------------------------------- #
def alert_urgency(*, has_stress: bool, days_to_stress: int | None,
                  disbursement_days: int, regime: str) -> str:
    """low | medium | high.

    high   - stress is imminent (you can't get funds in time) or the merchant
             is already in a stress regime
    medium - a stress period is coming inside the 60-day window
    low    - no stress period projected
    """
    if not has_stress:
        return "low"
    if regime == "stress":
        return "high"
    if days_to_stress is not None and days_to_stress <= disbursement_days + 7:
        return "high"
    if days_to_stress is not None and days_to_stress <= 45:
        return "medium"
    return "medium"
