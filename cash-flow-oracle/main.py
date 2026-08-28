"""
Cash Flow Oracle API (Track 04 scaffold).

    uvicorn cash_flow_oracle.main:app --port 8010

  POST /forecast      {"merchant_id": "m_fashion_01", "horizon_days": 30}
  GET  /merchants     list seeded merchants
  GET  /health        readiness + which model engines are available
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .db import store
from .schemas import ForecastRequest, ForecastResponse
from .service import MerchantNotFound, build_forecast


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.connect()
    print(f"[cfo] storage backend: {store.backend}")
    yield
    await store.close()


app = FastAPI(
    title="Cash Flow Oracle",
    version="0.1.0-scaffold",
    description="Merchant settlement forecasting - GARCH volatility + HMM regimes "
                "+ Prophet forecast. Razorpay AI Buildathon 2026, Track 04.",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict:
    from .models import forecast_prophet, garch, regime_hmm

    return {
        "status": "ok",
        "storage_backend": store.backend,
        "engines": {
            "prophet": forecast_prophet._HAVE_PROPHET,
            "arch_garch": garch._HAVE_ARCH,
            "hmmlearn": regime_hmm._HAVE_HMM,
        },
        "note": "engines=false -> documented statistical fallback is used",
    }


@app.get("/merchants")
async def merchants() -> dict:
    rows = await store.list_merchants()
    return {"count": len(rows), "merchants": rows}


@app.post("/forecast", response_model=ForecastResponse)
async def forecast_endpoint(req: ForecastRequest) -> ForecastResponse:
    try:
        return await build_forecast(req.merchant_id, req.horizon_days)
    except MerchantNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/")
async def root() -> dict:
    return {"service": "cash-flow-oracle", "docs": "/docs",
            "endpoints": ["POST /forecast", "GET /merchants", "GET /health"]}
