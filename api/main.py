"""
Step 6 - FastAPI backend for the WTP Dynamic Pricing Engine.

Endpoints
---------
POST /personalize        full pricing decision for one checkout
GET  /metrics            aggregate analytics + revenue-lift simulation
GET  /decision/{sid}     full decision log (incl. SHAP) for a session
POST /simulate           decision + counterfactual sensitivity sweep
GET  /health             liveness + component status
GET  /                   service banner

Cross-cutting
-------------
- CORS middleware (origins from CORS_ORIGINS)
- request-logging middleware (method, path, status, ms)
- latency middleware: POST /personalize returns 503 if it blows the
  LATENCY_BUDGET_MS ceiling (default 200ms); every response carries an
  X-Process-Time-Ms header
- IP enrichment `/enrich/*` sub-router is mounted here
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import _bootstrap  # noqa: F401
from .config import settings
from .context import market_context
from .db import db
from .logging_util import log
from .metrics import compute_metrics
from .schemas import CustomerSignals, PricingResponse, SimulateRequest, SimulateResponse
from .service import personalize, simulate

from ip_enrichment.router import router as enrich_router  # type: ignore
from ip_enrichment.service import get_service as get_ip_service  # type: ignore
from model.inference import get_model  # type: ignore


@asynccontextmanager
async def lifespan(app: FastAPI):
    log(f"starting {settings.SERVICE_NAME} v{settings.VERSION}")
    market_context.load()
    # warm the model (load + a throwaway inference) so the first real request
    # is already inside the latency budget
    t0 = time.perf_counter()
    try:
        get_model().predict({"list_price": 1000, "device_type": "iPhone", "city_tier": 1})
        log(f"model warmed in {(time.perf_counter()-t0)*1000:.0f}ms")
    except Exception as exc:  # noqa: BLE001
        log(f"model warm-up failed: {exc!r} (is model/artifacts populated?)", level="WARN")
    await get_ip_service().startup()
    await db.connect()
    log(f"ready. latency budget = {settings.LATENCY_BUDGET_MS}ms, db backend = {db.backend}")
    yield
    await get_ip_service().shutdown()
    await db.disconnect()
    log("shutdown complete")


app = FastAPI(
    title="WTP Dynamic Pricing Engine",
    version=settings.VERSION,
    description="Real-time willingness-to-pay estimation and checkout personalisation "
                "for Indian ecommerce. Razorpay AI Buildathon 2026, Track 01.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Process-Time-Ms"],
)


# --------------------------------------------------------------------------- #
# Middleware: request logging + latency ceiling
# --------------------------------------------------------------------------- #
@app.middleware("http")
async def timing_and_logging(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:  # noqa: BLE001
        elapsed = (time.perf_counter() - start) * 1000
        log(f'{request.method} {request.url.path} -> 500 ({elapsed:.1f}ms) {exc!r}', level="ERROR")
        raise
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
    log(f'{request.method} {request.url.path} -> {response.status_code} ({elapsed_ms:.1f}ms)')

    # hard latency ceiling for the money path
    if request.url.path == "/personalize" and elapsed_ms > settings.LATENCY_BUDGET_MS:
        log(f"LATENCY BUDGET EXCEEDED: /personalize took {elapsed_ms:.1f}ms "
            f"> {settings.LATENCY_BUDGET_MS}ms", level="WARN")
        return JSONResponse(
            status_code=503,
            headers={"X-Process-Time-Ms": f"{elapsed_ms:.2f}"},
            content={
                "detail": "latency budget exceeded",
                "latency_ms": round(elapsed_ms, 2),
                "budget_ms": settings.LATENCY_BUDGET_MS,
            },
        )
    return response


app.include_router(enrich_router)


# --------------------------------------------------------------------------- #
# Core endpoints
# --------------------------------------------------------------------------- #
@app.get("/")
async def root() -> dict:
    return {
        "service": settings.SERVICE_NAME,
        "version": settings.VERSION,
        "track": "Razorpay AI Buildathon 2026 - Track 01",
        "endpoints": ["/personalize", "/metrics", "/decision/{session_id}",
                      "/simulate", "/enrich", "/health", "/docs"],
    }


@app.get("/health")
async def health() -> dict:
    ip_svc = get_ip_service()
    model_ok = True
    try:
        get_model()
    except Exception:  # noqa: BLE001
        model_ok = False
    return {
        "status": "ok",
        "version": settings.VERSION,
        "components": {
            "model_loaded": model_ok,
            "ip_enrichment_ready": ip_svc.ready,
            "ip_geo_mode": "mock" if ip_svc.mock_geo_mode else "maxmind",
            "db_backend": db.backend,
            "cache_backend": ip_svc.cache_backend if ip_svc.ready else "n/a",
            "festival_context": market_context.loaded,
        },
        "latency_budget_ms": settings.LATENCY_BUDGET_MS,
    }


@app.post("/personalize", response_model=PricingResponse)
async def personalize_endpoint(payload: CustomerSignals) -> PricingResponse:
    if payload.list_price <= 0:
        raise HTTPException(status_code=422, detail="list_price must be > 0")

    response, db_record = await personalize(payload)

    budget = settings.LATENCY_BUDGET_MS
    response.budget_ms = budget
    response.budget_exceeded = response.latency_ms > budget
    db_record["budget_exceeded"] = response.budget_exceeded

    # async-ish logging: don't let a slow DB write hurt the response path
    try:
        await db.log_decision(db_record)
    except Exception as exc:  # noqa: BLE001
        log(f"decision logging failed: {exc!r}", level="WARN")

    return response


@app.get("/metrics")
async def metrics_endpoint() -> dict:
    rows = await db.fetch_all()
    out = compute_metrics(rows)
    out["db_backend"] = db.backend
    out["model"] = get_model().metadata
    return out


@app.get("/decision/{session_id}")
async def decision_endpoint(session_id: str) -> dict:
    rows = await db.get_session(session_id)
    if not rows:
        raise HTTPException(status_code=404, detail=f"no decisions for session {session_id!r}")

    import decimal
    import ipaddress
    import json as _json

    def _scalar(v):
        if v is None or isinstance(v, (str, int, float, bool)):
            return v
        if isinstance(v, decimal.Decimal):
            return float(v)
        if isinstance(v, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
            return str(v)
        if hasattr(v, "isoformat"):          # date / datetime
            return v.isoformat()
        if isinstance(v, (dict, list)):
            return v
        return str(v)

    # asyncpg returns jsonb columns as text; decode them back to objects
    _JSON_COLS = {"input_signals", "shap_values", "payment_methods_shown"}

    def _norm(r: dict) -> dict:
        d = dict(r)
        for k, v in list(d.items()):
            if k in _JSON_COLS and isinstance(v, str):
                try:
                    d[k] = _json.loads(v)
                    continue
                except (ValueError, TypeError):
                    pass
            d[k] = _scalar(v)
        return d

    return {
        "session_id": session_id,
        "decision_count": len(rows),
        "decisions": [_norm(r) for r in rows],
    }


@app.post("/simulate", response_model=SimulateResponse)
async def simulate_endpoint(req: SimulateRequest) -> SimulateResponse:
    if req.profile.list_price <= 0:
        raise HTTPException(status_code=422, detail="profile.list_price must be > 0")
    base, sensitivity = await simulate(req.profile, req.counterfactuals)
    base.budget_ms = settings.LATENCY_BUDGET_MS
    base.budget_exceeded = base.latency_ms > settings.LATENCY_BUDGET_MS
    return SimulateResponse(base=base, sensitivity=sensitivity)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)
