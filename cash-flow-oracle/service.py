"""
Forecast orchestration: settlements -> GARCH + HMM + Prophet -> plain-English
working-capital recommendation.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta


def _timedelta_days(n: int) -> timedelta:
    return timedelta(days=n)

import numpy as np

from . import config as C
from .db import store
from .models.garch import fit_garch
from .models.forecast_prophet import forecast as run_forecast
from .models.regime_hmm import detect_regimes
from .schemas import ForecastPoint, ForecastResponse, StressPeriod


class MerchantNotFound(Exception):
    pass


def _inr(x: float) -> str:
    """Indian-style short currency: ₹2.3L / ₹1.4Cr."""
    x = float(x)
    if abs(x) >= 1e7:
        return f"₹{x / 1e7:.1f}Cr"
    if abs(x) >= 1e5:
        return f"₹{x / 1e5:.1f}L"
    return f"₹{x:,.0f}"


async def build_forecast(merchant_id: str, horizon_days: int = C.FORECAST_DEFAULT_DAYS
                         ) -> ForecastResponse:
    merchants = {m["merchant_id"]: m for m in await store.list_merchants()}
    if merchant_id not in merchants:
        raise MerchantNotFound(merchant_id)
    archetype = merchants[merchant_id].get("archetype")

    rows = await store.get_settlements(merchant_id)
    if len(rows) < 90:
        raise MerchantNotFound(f"{merchant_id} has too little history ({len(rows)} days)")

    dates = [_as_date(r["settlement_date"]) for r in rows]
    net = np.array([float(r["net_settled_inr"]) for r in rows], dtype=float)

    trailing_30 = float(net[-30:].sum())
    trailing_7 = float(net[-7:].sum())
    trailing_30_mean = float(net[-30:].mean())

    # ---- GARCH volatility ----
    garch = fit_garch(net)
    hist_vol = float(np.mean(garch.conditional_vol[-60:])) if garch.conditional_vol.size else 0.0
    fc_vol = float(np.mean(garch.forecast_vol(horizon_days)))
    vol_ratio = (fc_vol / hist_vol) if hist_vol > 1e-9 else 1.0

    # ---- HMM regimes ----
    regimes = detect_regimes(dates, net)

    # ---- Prophet forecast ----
    fc = run_forecast(dates, net, horizon_days, vol_scale=max(0.6, min(vol_ratio, 3.0)))

    # regime hint per forecast day: carry the last known regime forward
    curve = [
        ForecastPoint(
            date=d, yhat=round(float(y), 2), lower=round(float(lo), 2),
            upper=round(float(hi), 2), regime_hint=regimes.current,
        )
        for d, y, lo, hi in zip(fc.dates, fc.yhat, fc.lower, fc.upper)
    ]
    forecast_total = float(np.sum(fc.yhat))

    # ---- stress periods: contiguous forecast days whose *point* forecast sits
    #      materially below the trailing-30d average daily settlement (the band
    #      is reported alongside, but the trigger is the expected shortfall) ----
    threshold = trailing_30_mean * (1 - C.STRESS_LOWER_BAND_DROP)
    stress = _contiguous_stress(fc.dates, fc.yhat, fc.lower, threshold, trailing_30_mean)

    # ---- recommendation ----
    rec = _recommendation(
        archetype, dates, net, fc, trailing_30, forecast_total,
        regimes.current, stress,
    )

    engine = (
        f"{fc.engine}+{garch.engine}+{regimes.engine}"
        if not (fc.engine == garch.engine == regimes.engine)
        else fc.engine
    )

    return ForecastResponse(
        merchant_id=merchant_id,
        archetype=archetype,
        engine=engine,
        generated_on=date.today(),
        current_cash_position=round(trailing_30, 2),
        trailing_30d_net_inr=round(trailing_30, 2),
        trailing_7d_net_inr=round(trailing_7, 2),
        current_regime=regimes.current,
        regime_stats=regimes.state_stats,
        volatility={
            "historical_daily_pct": round(hist_vol * 100, 3),
            "forecast_daily_pct": round(fc_vol * 100, 3),
            "ratio": round(vol_ratio, 3),
        },
        forecast_curve=curve,
        forecast_total_inr=round(forecast_total, 2),
        stress_periods=stress,
        credit_recommendation=rec,
    )


# --------------------------------------------------------------------------- #
def _contiguous_stress(fdates, yhat, lower, threshold, trailing_mean) -> list[StressPeriod]:
    """Flag runs of >=3 consecutive days where the *expected* daily settlement
    is below `threshold` (trailing-30d mean minus STRESS_LOWER_BAND_DROP)."""
    out: list[StressPeriod] = []
    run: list[int] = []

    def _flush():
        if len(run) < 3:
            return
        seg_yhat = float(np.mean([yhat[i] for i in run]))
        seg_lo = float(np.min([lower[i] for i in run]))
        drop = (1 - seg_yhat / trailing_mean) * 100 if trailing_mean else 0.0
        out.append(StressPeriod(
            start=fdates[run[0]], end=fdates[run[-1]], days=len(run),
            min_lower_inr=round(seg_lo, 2),
            drop_vs_trailing_pct=round(drop, 1),
            reason=f"expected daily settlement runs >{int(C.STRESS_LOWER_BAND_DROP * 100)}% "
                   "below the trailing 30-day daily average",
        ))

    for i in range(len(fdates)):
        if yhat[i] < threshold:
            run.append(i)
        else:
            _flush()
            run = []
    _flush()
    return out


def _monthly_seasonal_factor(dates: list[date], net: np.ndarray, month: int) -> float:
    """Average settlement in `month` relative to the overall daily average."""
    base = net.mean()
    m = np.array([d.month for d in dates])
    sel = net[m == month]
    return float(sel.mean() / base) if sel.size and base > 0 else 1.0


def _recommendation(archetype, dates, net, fc, trailing_30, forecast_total,
                    current_regime, stress) -> str:
    base_daily = float(net[-90:].mean())
    fc_daily = float(np.mean(fc.yhat))
    change_pct = (fc_daily / base_daily - 1) * 100 if base_daily else 0.0

    # the dominant month in the forecast window
    fc_month = fc.dates[len(fc.dates) // 2].month
    month_name = calendar.month_name[fc_month]
    seas = _monthly_seasonal_factor(dates, net, fc_month)
    seas_pct = (seas - 1) * 100

    parts: list[str] = []

    if stress:
        s = stress[0]
        # expected shortfall vs running at the recent daily average
        shortfall = max(0.0, base_daily * s.days * min(0.6, s.drop_vs_trailing_pct / 100))
        draw_by = s.start - _timedelta_days(5)
        parts.append(
            f"A cash-flow squeeze is likely between {s.start:%d %b} and "
            f"{s.end:%d %b} ({s.days} days), with expected settlements about "
            f"{s.drop_vs_trailing_pct:.0f}% below your recent daily average. "
            f"We recommend arranging roughly {_inr(shortfall)} of working capital "
            f"by {draw_by:%d %b}."
        )
    elif seas_pct <= -8:
        typical_drop = abs(seas_pct)
        buffer_amt = base_daily * 30 * (typical_drop / 100)
        parts.append(
            f"Your settlements typically drop {typical_drop:.0f}% in {month_name}. "
            f"We recommend drawing down {_inr(buffer_amt)} before "
            f"{month_name} {min(15, calendar.monthrange(fc.dates[0].year, fc_month)[1])}."
        )
    elif change_pct >= 10:
        parts.append(
            f"Settlements are trending up (~{change_pct:.0f}% vs the last 90 days) "
            f"into {month_name}. No borrowing needed; consider holding a "
            f"{_inr(base_daily * 7)} buffer for refund spikes and deploying the rest."
        )
    else:
        parts.append(
            f"Cash flow looks stable for the next {len(fc.dates)} days "
            f"(forecast {_inr(forecast_total)} vs {_inr(trailing_30)} in the "
            f"trailing 30 days). A {_inr(base_daily * 5)} operating buffer is sufficient."
        )

    if current_regime == "stress":
        parts.append(
            "Note: the merchant is currently in a *stress* regime (elevated "
            "volatility / depressed settlements) - treat the lower band as the "
            "planning number."
        )
    elif current_regime == "high_season":
        parts.append(
            "The merchant is in a *high-season* regime - expect the tail-off "
            "after the current peak; don't over-extend on the strength of "
            "recent inflows."
        )
    return " ".join(parts)


def _as_date(v) -> date:
    if isinstance(v, date):
        return v
    if isinstance(v, datetime):
        return v.date()
    return datetime.fromisoformat(str(v)[:10]).date()
