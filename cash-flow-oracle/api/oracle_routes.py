"""
`/oracle/*` HTTP surface for the Cash Flow Oracle dashboard (Track 04).

Mounted on both the standalone CFO app and the Track 01 API. All heavy lifting
lives in `oracle_service.py` (pure, tested); this module fetches rows, calls it,
and shapes responses. The store self-seeds on the first request if empty.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta

import numpy as np
from fastapi import APIRouter, HTTPException

from .. import config as C
from ..db import store
from ..models.regime_hmm import detect_regimes
from ..models.forecast_prophet import forecast as run_forecast
from ..schemas import (
    AlertPreviewRequest,
    LLMRecommendationRequest,
    OracleForecastResponse,
    ScenarioRequest,
)
from ..service import MerchantNotFound, build_forecast
from . import oracle_service as OS
from .festivals import upcoming_festivals
from .llm import generate_recommendation

router = APIRouter(prefix="/oracle", tags=["oracle"])

_seed_lock = asyncio.Lock()
_ready = False


async def _ensure_ready() -> None:
    global _ready
    if _ready:
        return
    async with _seed_lock:
        if _ready:
            return
        try:
            merchants = await store.list_merchants()
        except Exception:  # noqa: BLE001  (store not connected yet)
            await store.connect()
            merchants = await store.list_merchants()
        if not merchants:
            from ..seed import seed_into

            print("[cfo.oracle] store empty -> seeding synthetic merchants")
            await seed_into(store)
        _ready = True


def _as_date(v) -> date:
    return OS._as_date(v)


async def _merchant_or_404(merchant_id: str) -> dict:
    await _ensure_ready()
    rows = {m["merchant_id"]: m for m in await store.list_merchants()}
    if merchant_id not in rows:
        raise HTTPException(404, f"merchant {merchant_id!r} not found")
    return rows[merchant_id]


async def _series(merchant_id: str):
    rows = await store.get_settlements(merchant_id)
    if len(rows) < 90:
        raise HTTPException(422, f"{merchant_id} has too little history")
    dates = [_as_date(r["settlement_date"]) for r in rows]
    net = np.array([float(r["net_settled_inr"]) for r in rows], dtype=float)
    return dates, net


def _fc_arrays(base) -> tuple[list[date], np.ndarray, np.ndarray, np.ndarray]:
    fd = [p.date for p in base.forecast_curve]
    return (fd,
            np.array([p.yhat for p in base.forecast_curve], dtype=float),
            np.array([p.lower for p in base.forecast_curve], dtype=float),
            np.array([p.upper for p in base.forecast_curve], dtype=float))


def _cash_params(me: dict, base, net: np.ndarray) -> tuple[float, float, float]:
    """(opening_balance, daily_burn, operating_threshold) for the cash curve.

    Burn tracks the *recent* settlement run-rate (opex scales with revenue) with
    a small structural bleed on top - so the balance drifts gently in a normal
    stretch, falls in a dip, and recovers when settlements do."""
    recent_level = float(np.mean(net[-90:]))
    avg_daily = float(me.get("avg_daily_settlement") or recent_level)
    opening = float(base.current_cash_position) * C.CASH_ON_HAND_RATIO
    daily_burn = recent_level * C.BURN_RATIO
    threshold = float(me.get("operating_threshold")
                      or C.OPERATING_THRESHOLD_FRACTION * avg_daily * 30.0)
    return opening, daily_burn, threshold


def _stress_freq_per_year(m: dict) -> float:
    """Heuristic stress-period frequency from stored volatility (avoids a
    settlement fetch per peer). Documented in ARCHITECTURE.md Track 04."""
    v = float(m.get("settlement_volatility") or 0.3)
    return round(2.0 + 8.0 * min(1.0, max(0.0, (v - 0.2) / 0.5)), 1)


# --------------------------------------------------------------------------- #
# GET /oracle/merchants
# --------------------------------------------------------------------------- #
@router.get("/merchants")
async def oracle_merchants() -> dict:
    await _ensure_ready()
    rows = await store.list_merchants()
    out = []
    for m in rows:
        avg = float(m.get("avg_daily_settlement") or 0.0)
        out.append({
            "merchant_id": m["merchant_id"],
            "name": m.get("display_name"),
            "category": m.get("archetype"),
            "city_tier": m.get("city_tier"),
            "current_cash_position": round(avg * 30.0, 2),
            "operating_threshold": float(m.get("operating_threshold") or 0.0),
        })
    return {"count": len(out), "merchants": out}


# --------------------------------------------------------------------------- #
# POST /oracle/forecast
# --------------------------------------------------------------------------- #
async def _oracle_forecast(merchant_id: str, horizon_days: int = 60) -> dict:
    me = await _merchant_or_404(merchant_id)
    dates, net = await _series(merchant_id)
    try:
        base = await build_forecast(merchant_id, horizon_days)
    except MerchantNotFound as exc:
        raise HTTPException(404, str(exc))

    fc_dates, yhat, lower, upper = _fc_arrays(base)
    regimes = detect_regimes(dates, net)
    conf = OS.regime_confidence(regimes.labels, regimes.current)

    peers = await store.list_merchants()
    peer_cmp = OS.peer_comparison(me, peers, stress_freq_fn=_stress_freq_per_year)

    anom_flag, anom_expl = OS.current_week_anomaly(
        dates, net, category=me.get("archetype", ""))

    opening, daily_burn, threshold = _cash_params(me, base, net)
    curve = OS.cash_position_curve(
        dates, net, fc_dates, yhat, lower, upper,
        opening_balance=opening, daily_burn=daily_burn,
        regime_current=regimes.current)
    cash_stress = OS.cash_stress_periods(curve, threshold)

    trough_date = _as_date(cash_stress[0]["trough_date"]) if cash_stress else None
    disb = int(me.get("capital_disbursement_days") or 3)
    apply_by = OS.credit_apply_by_date(trough_date, disb)

    if cash_stress:
        s0 = cash_stress[0]
        stress_start = _as_date(s0["start"])
        days_early = disb + max(0, (trough_date - stress_start).days)
        carry = OS.carry_cost_analysis(
            shortfall_inr=s0["shortfall_at_trough"],
            days_early=days_early,
            borrow_cost_pct_month=C.CAPITAL_BORROW_COST_PCT_PER_MONTH,
            penalty_pct_month=float(me.get("late_payment_penalty_rate") or 2.0),
            penalty_base_inr=s0["shortfall_at_trough"],
            penalty_months=max(0.5, s0["days"] / 30.0),
        )
    else:
        carry = OS.carry_cost_analysis(
            shortfall_inr=0.0, days_early=0,
            borrow_cost_pct_month=C.CAPITAL_BORROW_COST_PCT_PER_MONTH,
            penalty_pct_month=float(me.get("late_payment_penalty_rate") or 2.0))

    trend = 0.0
    if net.size >= 14 and net[-14:-7].mean() > 0:
        trend = round((net[-7:].mean() / net[-14:-7].mean() - 1) * 100, 1)

    today = date.today()
    payload = base.model_dump()
    payload.update(
        regime=regimes.current,
        regime_confidence=conf,
        regime_description=OS.regime_description(me.get("archetype", ""), regimes.current),
        regime_history=OS.regime_history(dates, regimes.labels, days=90),
        peer_comparison=peer_cmp,
        anomaly_flag=anom_flag,
        anomaly_explanation=anom_expl,
        operating_threshold=round(threshold, 2),
        cash_on_hand=round(opening, 2),
        cash_position_curve=curve,
        cash_stress_periods=cash_stress,
        credit_apply_by_date=apply_by,
        carry_cost_analysis=carry,
        forecast_accuracy_mape=OS.backtest_mape(dates, net),
        next_stress_days=OS.days_until_stress(curve, cash_stress),
        current_cash_trend_pct=trend,
        festival_markers=upcoming_festivals(
            today, today + timedelta(days=horizon_days + 30)),
    )
    return payload


@router.post("/forecast", response_model=OracleForecastResponse)
async def oracle_forecast_endpoint(body: dict) -> dict:
    merchant_id = body.get("merchant_id")
    if not merchant_id:
        raise HTTPException(422, "merchant_id required")
    horizon = int(body.get("horizon_days", 60) or 60)
    horizon = max(14, min(horizon, C.FORECAST_MAX_DAYS))
    return await _oracle_forecast(merchant_id, horizon)


# --------------------------------------------------------------------------- #
# POST /oracle/scenario
# --------------------------------------------------------------------------- #
@router.post("/scenario")
async def oracle_scenario(req: ScenarioRequest) -> dict:
    me = await _merchant_or_404(req.merchant_id)
    dates, net = await _series(req.merchant_id)
    try:
        base = await build_forecast(req.merchant_id, req.horizon_days)
    except MerchantNotFound as exc:
        raise HTTPException(404, str(exc))

    fc_dates, yhat, lower, upper = _fc_arrays(base)
    regimes = detect_regimes(dates, net)
    opening, daily_burn, threshold = _cash_params(me, base, net)

    orig_curve = OS.cash_position_curve(
        dates, net, fc_dates, yhat, lower, upper,
        opening_balance=opening, daily_burn=daily_burn,
        regime_current=regimes.current)
    orig_stress = OS.cash_stress_periods(orig_curve, threshold)

    s_yhat, s_lower, s_upper = OS.apply_scenario_shock(
        fc_dates, yhat, lower, upper,
        shock_type=req.shock_type, magnitude_pct=req.shock_magnitude,
        shock_start=req.shock_start_date, duration_days=req.shock_duration_days)
    shock_curve = OS.cash_position_curve(
        dates, net, fc_dates, s_yhat, s_lower, s_upper,
        opening_balance=opening, daily_burn=daily_burn,
        regime_current=regimes.current)
    shock_stress = OS.cash_stress_periods(shock_curve, threshold)

    orig_fc = [p for p in orig_curve if p["is_forecast"]]
    shock_fc = [p for p in shock_curve if p["is_forecast"]]
    delta_final = round(shock_fc[-1]["balance"] - orig_fc[-1]["balance"], 2)
    delta_min = round(min(p["balance"] for p in shock_fc)
                      - min(p["balance"] for p in orig_fc), 2)

    orig_windows = {(s["start"], s["end"]) for s in orig_stress}
    new_stress = [s for s in shock_stress if (s["start"], s["end"]) not in orig_windows]

    if new_stress:
        s0 = new_stress[0]
        disb = int(me.get("capital_disbursement_days") or 3)
        trough_date = _as_date(s0["trough_date"])
        apply_by = OS.credit_apply_by_date(trough_date, disb)
        days_early = disb + max(0, (trough_date - _as_date(s0["start"])).days)
        carry = OS.carry_cost_analysis(
            shortfall_inr=s0["shortfall_at_trough"], days_early=days_early,
            borrow_cost_pct_month=C.CAPITAL_BORROW_COST_PCT_PER_MONTH,
            penalty_pct_month=float(me.get("late_payment_penalty_rate") or 2.0),
            penalty_base_inr=s0["shortfall_at_trough"],
            penalty_months=max(0.5, s0["days"] / 30.0))
        credit_rec = {
            "changed": True,
            "apply_by_date": apply_by.isoformat() if apply_by else None,
            "carry_cost_analysis": carry,
            "summary": (f"This scenario introduces a {s0['days']}-day squeeze from "
                        f"{s0['start']}. {carry['explanation']}"),
        }
    else:
        credit_rec = {
            "changed": False,
            "summary": ("This scenario has no impact on stress periods - the "
                        "existing credit guidance still holds."),
        }

    result = {
        "scenario_id": OS.new_scenario_id(),
        "merchant_id": req.merchant_id,
        "shock": {
            "type": req.shock_type, "magnitude_pct": req.shock_magnitude,
            "start_date": req.shock_start_date.isoformat(),
            "duration_days": req.shock_duration_days,
        },
        "original_forecast_curve": orig_fc,
        "shocked_forecast_curve": shock_fc,
        "original_settlement_yhat": [round(float(v), 2) for v in yhat],
        "shocked_settlement_yhat": [round(float(v), 2) for v in s_yhat],
        "forecast_dates": [_as_date(d).isoformat() for d in fc_dates],
        "operating_threshold": round(threshold, 2),
        "delta_cash_position_final_inr": delta_final,
        "delta_min_balance_inr": delta_min,
        "original_stress_periods": orig_stress,
        "shocked_stress_periods": shock_stress,
        "new_stress_periods": new_stress,
        "new_stress_count": len(new_stress),
        "stress_message": (
            f"This scenario introduces {len(new_stress)} new stress "
            f"period{'s' if len(new_stress) != 1 else ''}."
            if new_stress else
            "This scenario has no impact on stress periods."),
        "updated_credit_recommendation": credit_rec,
    }
    try:
        await store.save_scenario(
            result["scenario_id"], req.merchant_id, req.shock_type,
            req.shock_magnitude, req.shock_start_date, req.shock_duration_days, result)
    except Exception as exc:  # noqa: BLE001
        print(f"[cfo.oracle] scenario persist failed ({exc!r})")
    return result


# --------------------------------------------------------------------------- #
# GET /oracle/peers/{merchant_id}
# --------------------------------------------------------------------------- #
@router.get("/peers/{merchant_id}")
async def oracle_peers(merchant_id: str) -> dict:
    me = await _merchant_or_404(merchant_id)
    peers = await store.list_merchants()
    cmp = OS.peer_comparison(me, peers, stress_freq_fn=_stress_freq_per_year)
    cmp["merchant_id"] = merchant_id
    cmp["merchant_name"] = me.get("display_name")
    return cmp


# --------------------------------------------------------------------------- #
# GET /oracle/anomalies/{merchant_id}
# --------------------------------------------------------------------------- #
@router.get("/anomalies/{merchant_id}")
async def oracle_anomalies(merchant_id: str, lookback_days: int = 30) -> dict:
    me = await _merchant_or_404(merchant_id)
    dates, net = await _series(merchant_id)
    lookback_days = max(7, min(lookback_days, 90))
    anomalies = OS.anomaly_scan(
        dates, net, lookback_days=lookback_days,
        sigma_threshold=C.ANOMALY_SIGMA_FEED, category=me.get("archetype", ""))
    return {
        "merchant_id": merchant_id,
        "merchant_name": me.get("display_name"),
        "lookback_days": lookback_days,
        "sigma_threshold": C.ANOMALY_SIGMA_FEED,
        "count": len(anomalies),
        "anomalies": anomalies,
    }


# --------------------------------------------------------------------------- #
# GET /oracle/fingerprint/{merchant_id}
# --------------------------------------------------------------------------- #
@router.get("/fingerprint/{merchant_id}")
async def oracle_fingerprint(merchant_id: str) -> dict:
    me = await _merchant_or_404(merchant_id)
    dates, net = await _series(merchant_id)
    fp = OS.settlement_fingerprint(dates, net)
    curves = OS.festival_response_curves(dates, net)
    return {
        "merchant_id": merchant_id,
        "merchant_name": me.get("display_name"),
        "category": me.get("archetype"),
        "fingerprint": fp,
        "festival_response_curves": curves,
    }


# --------------------------------------------------------------------------- #
# POST /oracle/llm_recommendation
# --------------------------------------------------------------------------- #
@router.post("/llm_recommendation")
async def oracle_llm_recommendation(req: LLMRecommendationRequest) -> dict:
    me = await _merchant_or_404(req.merchant_id)
    payload = {
        "merchant_id": req.merchant_id,
        "merchant": me,
        "forecast": req.forecast,
        "regime": req.regime,
        "regime_confidence": req.regime_confidence,
        "peer_comparison": req.peer_comparison,
        "anomaly_flag": req.anomaly_flag,
        "anomaly_explanation": req.anomaly_explanation,
        "carry_cost_analysis": req.carry_cost_analysis,
        "credit_apply_by_date": req.credit_apply_by_date,
    }
    return await generate_recommendation(payload)


# --------------------------------------------------------------------------- #
# POST /oracle/alert_preview
# --------------------------------------------------------------------------- #
@router.post("/alert_preview")
async def oracle_alert_preview(req: AlertPreviewRequest) -> dict:
    me = await _merchant_or_404(req.merchant_id)
    fc = await _oracle_forecast(req.merchant_id, 60)
    stress = fc["cash_stress_periods"]
    disb = int(me.get("capital_disbursement_days") or 3)
    name = me.get("display_name", "your business")
    today = date.today()

    if stress:
        s0 = stress[0]
        start = _as_date(s0["start"])
        days_to = (start - today).days
        apply_by = fc.get("credit_apply_by_date")
        apply_by = str(apply_by) if apply_by else None
        shortfall = OS.inr(s0.get("shortfall_at_trough") or 0)
        urgency = OS.alert_urgency(
            has_stress=True, days_to_stress=days_to,
            disbursement_days=disb, regime=fc["regime"])
        title = ("Cash flow alert: action needed"
                 if urgency == "high" else "Cash flow heads-up")
        body = (
            f"Hi {name} 👋\n\n"
            f"Our forecast shows your settlement cash position dipping below your "
            f"safe operating level for ~{s0['days']} days starting {start:%d %b}, "
            f"with a shortfall around {shortfall} at the low point.\n\n"
            f"To have Razorpay Capital funds land before then, apply by "
            f"*{apply_by}*. The carry cost is far smaller than the late-payment "
            f"penalties you'd otherwise take on.\n\n"
            f"Tap below to review and apply — takes 2 minutes."
        )
        action = f"Apply for Razorpay Capital by {apply_by}"
    else:
        urgency = "low"
        title = "Cash flow: all clear"
        body = (
            f"Hi {name} 👋\n\n"
            f"Good news — your settlement forecast for the next 60 days stays "
            f"comfortably above your safe operating level. No borrowing needed.\n\n"
            f"We'll ping you if that changes."
        )
        action = "No action needed"
        apply_by = None

    return {
        "merchant_id": req.merchant_id,
        "title": title,
        "body": body,
        "urgency": urgency,
        "recommended_action": action,
        "apply_by_date": apply_by,
        "sender": "Razorpay Cash Flow Oracle",
    }
