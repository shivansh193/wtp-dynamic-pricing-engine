"""Scaffold tests for the Cash Flow Oracle (Track 04)."""

import asyncio
import sys

sys.path.insert(0, ".")

import conftest  # noqa: F401,E402  registers cash_flow_oracle

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from datetime import date, timedelta  # noqa: E402

from cash_flow_oracle.data_pipeline.generate_settlements import generate_all  # noqa: E402
from cash_flow_oracle.models.garch import fit_garch  # noqa: E402
from cash_flow_oracle.models.regime_hmm import detect_regimes  # noqa: E402
from cash_flow_oracle.models.forecast_prophet import forecast  # noqa: E402
from cash_flow_oracle.api import oracle_service as OS  # noqa: E402
from cash_flow_oracle.api import llm as LLM  # noqa: E402


def test_generator_shape_and_seasonality():
    merchants, settlements = generate_all()
    assert len(merchants) == 30           # 5 archetypes x MERCHANTS_PER_ARCHETYPE
    assert len(settlements) > 25_000
    # every merchant carries the extended metadata fields
    for m in merchants:
        assert m["city_tier"] in (1, 2, 3)
        assert 2 <= m["capital_disbursement_days"] <= 3
        assert 1.5 <= m["late_payment_penalty_rate"] <= 3.0
    # net settled is always non-negative and < gross
    for (_mid, _d, gross, refunds, fees, net, txn) in settlements[:500]:
        assert net >= 0
        assert net <= gross
        assert txn >= 1


def test_garch_forecast_is_positive_and_right_length():
    rng = np.random.default_rng(0)
    series = 100_000 * np.exp(np.cumsum(rng.normal(0, 0.05, 400)))
    res = fit_garch(series)
    fv = res.forecast_vol(30)
    assert fv.shape == (30,)
    assert np.all(fv > 0)
    assert res.engine in {"arch", "fallback"}


def test_regime_labels_are_from_the_expected_set():
    from datetime import date, timedelta

    rng = np.random.default_rng(1)
    n = 500
    dates = [date(2023, 1, 1) + timedelta(days=i) for i in range(n)]
    series = 100_000 * (1 + 0.3 * np.sin(np.arange(n) / 30)) * rng.lognormal(0, 0.1, n)
    series[200:215] *= 0.3  # a stress dip
    res = detect_regimes(dates, series)
    assert set(res.labels) <= {"high_season", "low_season", "stress"}
    assert res.current in {"high_season", "low_season", "stress"}
    assert res.engine in {"hmmlearn", "fallback"}


def test_forecast_bands_bracket_the_point():
    from datetime import date, timedelta

    rng = np.random.default_rng(2)
    n = 400
    dates = [date(2023, 1, 1) + timedelta(days=i) for i in range(n)]
    series = 200_000 * (1 + 0.2 * np.sin(np.arange(n) / 30)) * rng.lognormal(0, 0.15, n)
    fc = forecast(dates, series, 30, vol_scale=1.0)
    assert len(fc.dates) == 30
    assert np.all(fc.lower <= fc.yhat + 1e-6)
    assert np.all(fc.upper >= fc.yhat - 1e-6)
    assert np.all(fc.lower >= 0)


def test_build_forecast_end_to_end(tmp_path, monkeypatch):
    """Seed a fresh sqlite db and run a full forecast."""
    from cash_flow_oracle import config as cfg
    from cash_flow_oracle import db as dbmod

    monkeypatch.setattr(cfg, "SQLITE_FALLBACK", tmp_path / "t.sqlite3")
    monkeypatch.setattr(cfg, "DATABASE_URL", "")
    store = dbmod.Store()
    dbmod.store = store

    from cash_flow_oracle.seed import main as seed_main
    from cash_flow_oracle.service import build_forecast

    async def run():
        await seed_main()
        return await build_forecast("m_grocery_01", 30)

    resp = asyncio.run(run())
    assert resp.merchant_id == "m_grocery_01"
    assert resp.archetype == "grocery"
    assert len(resp.forecast_curve) == 30
    assert resp.forecast_total_inr > 0
    assert resp.current_regime in {"high_season", "low_season", "stress"}
    assert isinstance(resp.credit_recommendation, str) and len(resp.credit_recommendation) > 20


# ==========================================================================
# Track 04 - /oracle/* analytics (Step 4 of the CFO dashboard build)
# ==========================================================================
def _fc_dates(start: date, n: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def test_scenario_shock_respects_magnitude_and_window():
    fdates = _fc_dates(date(2026, 9, 1), 40)
    yhat = np.full(40, 100_000.0)
    lower, upper = yhat * 0.8, yhat * 1.2
    start, dur = date(2026, 9, 10), 8
    s_yhat, _s_lo, _s_hi = OS.apply_scenario_shock(
        fdates, yhat, lower, upper,
        shock_type="payment_gateway_outage", magnitude_pct=30,
        shock_start=start, duration_days=dur)

    win = [i for i, d in enumerate(fdates)
           if start <= d <= start + timedelta(days=dur - 1)]
    pre = [i for i, d in enumerate(fdates) if d < start]
    assert len(win) == dur
    # payment_gateway_outage is a negative shock; in-window factor = 1 - 0.90*0.30
    exp_in = 100_000.0 * (1 - 0.90 * 0.30)
    assert all(abs(s_yhat[i] - exp_in) < 1.0 for i in win)
    assert all(abs(s_yhat[i] - 100_000.0) < 1e-6 for i in pre)   # untouched before

    p_yhat, *_ = OS.apply_scenario_shock(
        fdates, yhat, lower, upper, shock_type="discount_sale",
        magnitude_pct=30, shock_start=start, duration_days=dur)
    assert all(p_yhat[i] > 100_000.0 for i in win)               # positive shock

    big, *_ = OS.apply_scenario_shock(
        fdates, yhat, lower, upper, shock_type="payment_gateway_outage",
        magnitude_pct=50, shock_start=start, duration_days=dur)
    assert big[win[0]] < s_yhat[win[0]]                          # bigger magnitude


def test_credit_apply_by_date_backs_off_disbursement_days():
    trough = date(2026, 9, 30)
    assert OS.credit_apply_by_date(trough, 3) == date(2026, 9, 27)
    assert OS.credit_apply_by_date(trough, 2) == date(2026, 9, 28)
    assert OS.credit_apply_by_date(None, 3) is None


def test_carry_cost_net_benefit_math():
    r = OS.carry_cost_analysis(
        shortfall_inr=1_000_000, days_early=30, borrow_cost_pct_month=1.5,
        penalty_pct_month=2.0, penalty_base_inr=1_000_000, penalty_months=1.0)
    assert abs(r["carry_cost_inr"] - 15_000) < 1e-6      # 1e6 * 1.5% * 30/30
    assert abs(r["late_payment_penalty_avoided_inr"] - 20_000) < 1e-6  # 1e6 * 2% * 1
    assert abs(r["net_benefit_inr"] - 5_000) < 1e-6
    assert r["recommendation"] == "borrow_early"

    r2 = OS.carry_cost_analysis(
        shortfall_inr=1_000_000, days_early=90, borrow_cost_pct_month=1.5,
        penalty_pct_month=2.0, penalty_base_inr=1_000_000, penalty_months=1.0)
    assert r2["net_benefit_inr"] < 0
    assert r2["recommendation"] == "delay_or_downsize"

    r3 = OS.carry_cost_analysis(
        shortfall_inr=0, days_early=0, borrow_cost_pct_month=1.5,
        penalty_pct_month=2.0)
    assert r3["net_benefit_inr"] == 0.0


def test_anomaly_scan_flags_large_deviations_only():
    rng = np.random.default_rng(3)
    n = 400
    dates = _fc_dates(date(2025, 6, 1), n)
    net = 500_000 * rng.lognormal(0, 0.06, n)      # tight series
    net[-3] *= 3.0                                  # a clear spike
    net[-9] *= 0.25                                 # a clear dip
    found = OS.anomaly_scan(dates, net, lookback_days=20,
                            sigma_threshold=1.5, category="grocery")
    by_date = {a["date"]: a for a in found}
    assert by_date[dates[-3].isoformat()]["kind"] == "SPIKE"
    assert by_date[dates[-3].isoformat()]["magnitude_sigma"] > 1.5
    assert by_date[dates[-9].isoformat()]["kind"] == "DIP"
    assert by_date[dates[-9].isoformat()]["magnitude_sigma"] < -1.5
    assert all(abs(a["magnitude_sigma"]) >= 1.5 for a in found)
    assert dates[-2].isoformat() not in by_date            # a normal day is not flagged


def test_peer_comparison_ranks_in_distribution():
    def mk(mid, vol, avg, tier=2):
        return {"merchant_id": mid, "archetype": "fashion", "city_tier": tier,
                "settlement_volatility": vol, "avg_daily_settlement": avg}

    peers = [mk(f"p{i}", 0.20 + 0.05 * i, 1_000_000 + 200_000 * i) for i in range(5)]
    hi = OS.peer_comparison(mk("me", 0.60, 3_000_000), peers + [mk("me", 0.60, 3_000_000)])
    lo = OS.peer_comparison(mk("me", 0.10, 500_000), peers + [mk("me", 0.10, 500_000)])
    assert hi["volatility"]["percentile"] == 100.0
    assert hi["avg_daily_settlement"]["percentile"] == 100.0
    assert lo["volatility"]["percentile"] == 0.0
    assert hi["volatility"]["distribution"] == sorted(hi["volatility"]["distribution"])
    mid = OS.peer_comparison(mk("me", 0.325, 1_500_000), peers)
    assert 0 < mid["volatility"]["percentile"] < 100


def test_llm_recommendation_falls_back_to_template(monkeypatch):
    monkeypatch.setattr(LLM.C, "ANTHROPIC_API_KEY", "")
    payload = {
        "merchant_id": "m_fashion_01",
        "merchant": {"display_name": "Kapda & Co", "archetype": "fashion",
                     "city_tier": 2, "avg_daily_settlement": 200_000,
                     "operating_threshold": 1_800_000},
        "forecast": {
            "current_cash_position": 900_000, "forecast_total_inr": 12_000_000,
            "trailing_7d_net_inr": 1_400_000,
            "cash_stress_periods": [{
                "start": "2026-09-20", "end": "2026-10-02", "days": 12,
                "trough_balance": 400_000, "shortfall_at_trough": 700_000}]},
        "regime": "low_season",
        "carry_cost_analysis": {"recommendation": "borrow_early",
                                "shortfall_inr": 700_000, "carry_cost_inr": 5_000,
                                "late_payment_penalty_avoided_inr": 14_000},
        "credit_apply_by_date": "2026-09-17",
    }
    assert asyncio.new_event_loop().run_until_complete(LLM._call_anthropic("hi")) is None
    tmpl = LLM.template_recommendation(payload)
    assert isinstance(tmpl, str) and len(tmpl) > 40
    assert "Kapda & Co" in tmpl
    assert "2026-09-17" in tmpl                 # references the real apply-by date


@pytest.mark.parametrize("has_stress,days,regime,expected", [
    (False, None, "high_season", "low"),
    (True, 3, "high_season", "high"),           # imminent - can't fund in time
    (True, 40, "stress", "high"),               # already in a stress regime
    (True, 30, "low_season", "medium"),         # coming, but time to act
    (True, 55, "high_season", "medium"),
])
def test_alert_urgency_levels(has_stress, days, regime, expected):
    assert OS.alert_urgency(has_stress=has_stress, days_to_stress=days,
                            disbursement_days=3, regime=regime) == expected


def test_cash_curve_and_stress_periods_are_consistent():
    hist_d = _fc_dates(date(2026, 8, 1), 30)
    hist_net = np.full(30, 100_000.0)
    fc_d = _fc_dates(date(2026, 8, 31), 30)
    fc_y = np.full(30, 100_000.0)
    fc_y[7:21] = 20_000.0                       # a two-week dip, then recovery
    curve = OS.cash_position_curve(
        hist_d, hist_net, fc_d, fc_y, fc_y * 0.9, fc_y * 1.1,
        opening_balance=1_000_000, daily_burn=100_000, regime_current="low_season")
    assert len(curve) == 60
    assert curve[29]["balance"] == 1_000_000    # anchored at 'today'
    stress = OS.cash_stress_periods(curve, threshold=700_000)
    assert len(stress) == 1
    assert stress[0]["days"] >= 3
    assert stress[0]["trough_balance"] < 700_000
