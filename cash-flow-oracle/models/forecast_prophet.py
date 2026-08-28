"""
Prophet 30-60 day forward forecast of daily net settlements.

Real path: `prophet.Prophet` with yearly + weekly seasonality and an 80%
interval.
Fallback: additive decomposition - EWMA trend + day-of-week factors + a
month-of-year factor, with a Gaussian interval whose width is scaled by the
GARCH conditional vol (passed in) so the bands widen in volatile regimes.

Interface:
    fc = forecast(dates, net_settlements, horizon_days, vol_scale=1.0)
    fc.dates   -> list[date] length horizon
    fc.yhat / fc.lower / fc.upper  -> np.ndarray length horizon
    fc.engine  -> "prophet" | "fallback"
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from .. import config as C

try:
    from prophet import Prophet  # type: ignore

    _HAVE_PROPHET = True
except Exception:  # noqa: BLE001
    _HAVE_PROPHET = False


@dataclass
class ForecastResult:
    dates: list[date]
    yhat: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    engine: str


def forecast(dates: list[date], net_settlements, horizon_days: int,
             vol_scale: float = 1.0) -> ForecastResult:
    horizon_days = int(max(1, min(horizon_days, C.FORECAST_MAX_DAYS)))
    y = np.asarray(net_settlements, dtype=float)
    last = dates[-1]
    fut_dates = [last + timedelta(days=i + 1) for i in range(horizon_days)]

    if _HAVE_PROPHET and y.size >= 90:
        try:
            import pandas as pd

            df = pd.DataFrame({"ds": pd.to_datetime(dates), "y": y})
            m = Prophet(interval_width=C.PROPHET_INTERVAL_WIDTH,
                        weekly_seasonality=True, yearly_seasonality=True,
                        daily_seasonality=False)
            m.fit(df)
            fut = m.make_future_dataframe(periods=horizon_days)
            out = m.predict(fut).tail(horizon_days)
            return ForecastResult(
                fut_dates,
                out["yhat"].to_numpy(),
                out["yhat_lower"].to_numpy(),
                out["yhat_upper"].to_numpy(),
                "prophet",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[cfo.prophet] prophet failed ({exc!r}) -> fallback")

    # ---- fallback additive model ----
    return _fallback(dates, y, fut_dates, vol_scale)


def _fallback(dates, y, fut_dates, vol_scale) -> ForecastResult:
    """Additive decomposition: smoothed trend x day-of-week x month factors,
    with a multiplicative uncertainty band scaled by the *relative* residual
    dispersion (clamped) so the interval stays sane on spiky small-merchant
    data."""
    y = np.asarray(y, dtype=float)
    n = y.size

    # smoothed trend: 30-day centred median then EWMA (median tames the spikes)
    med = _rolling_median(y, 30)
    lam = 2 / (30 + 1)
    ewma = np.empty(n)
    ewma[0] = med[0]
    for t in range(1, n):
        ewma[t] = lam * med[t] + (1 - lam) * ewma[t - 1]
    level = float(np.mean(ewma[-14:]))
    w = min(90, n - 1)
    slope = (ewma[-1] - ewma[-1 - w]) / w if w > 0 else 0.0
    slope = float(np.clip(slope, -0.01 * level, 0.02 * level))  # <=2%/day drift

    base = float(np.median(y))
    dow = np.array([d.weekday() for d in dates])
    dow_factor = np.array([
        (np.median(y[dow == k]) / base) if (dow == k).any() else 1.0 for k in range(7)
    ])
    moy = np.array([d.month for d in dates])
    moy_factor = np.array([
        (np.median(y[moy == k]) / base) if (moy == k).any() else 1.0 for k in range(1, 13)
    ])

    # relative residual dispersion of the *deseasonalised* series (robust)
    deseason = y / np.maximum(1e-6, ewma * dow_factor[dow] * moy_factor[moy - 1])
    rel_disp = float(np.clip(np.nanstd(deseason[-120:]), 0.05, 0.6))

    yhat, lower, upper = [], [], []
    for i, d in enumerate(fut_dates):
        trend = level + slope * (i + 1)
        seasonal = dow_factor[d.weekday()] * moy_factor[d.month - 1]
        point = max(0.0, trend * seasonal)
        # ~80% band, grows slowly with horizon, capped at +/-55% of the point
        frac = min(0.55, 1.2818 * rel_disp * vol_scale * (1 + i / 60.0))
        band = point * frac
        yhat.append(point)
        lower.append(max(0.0, point - band))
        upper.append(point + band)

    return ForecastResult(fut_dates, np.array(yhat), np.array(lower),
                          np.array(upper), "fallback")


def _rolling_median(y: np.ndarray, k: int) -> np.ndarray:
    n = y.size
    out = np.empty(n)
    half = k // 2
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        out[i] = np.median(y[lo:hi])
    return out
