"""Scaffold tests for the Cash Flow Oracle (Track 04)."""

import asyncio
import sys

sys.path.insert(0, ".")

import conftest  # noqa: F401,E402  registers cash_flow_oracle

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from cash_flow_oracle.data_pipeline.generate_settlements import generate_all  # noqa: E402
from cash_flow_oracle.models.garch import fit_garch  # noqa: E402
from cash_flow_oracle.models.regime_hmm import detect_regimes  # noqa: E402
from cash_flow_oracle.models.forecast_prophet import forecast  # noqa: E402


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
