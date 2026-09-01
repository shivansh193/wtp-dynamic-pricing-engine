"""
Step 6 - FastAPI backend for the WTP Dynamic Pricing Engine.

Endpoints
---------
POST /personalize            full pricing decision for one checkout
GET  /metrics                aggregate analytics + revenue-lift simulation
GET  /decision/{sid}         full decision log (incl. SHAP) for a session
POST /simulate               decision + counterfactual sensitivity sweep
POST /simulate/ab_test       synthetic control (flat) vs treatment (friction-aware)
GET  /funnel                 4-stage conversion funnel, drop-off by friction type
GET  /interventions/performance   conversion + RPV by intervention, fatigue
POST /session/create         generate a demo customer link (+ QR)
GET  /session/{sid}          session config + results if priced
GET  /sessions/all           every generated session (seller dashboard table)
POST /session/{sid}/complete mark the dummy "purchase" as converted
GET  /segment/stats/{key}    Bayesian posterior WTP for a segment
WS   /ws/sessions            live session updates for the seller dashboard
GET  /health                 liveness + component status
GET  /                       service banner

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

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import _bootstrap  # noqa: F401
from . import presets as _presets
from .config import settings
from .context import market_context
from .db import db
from .logging_util import log
from .metrics import compute_metrics
from .qr import make_qr_data_uri
from .schemas import (
    ABTestRequest,
    CustomerSignals,
    PricingResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionInfo,
    SessionListResponse,
    SimulateRequest,
    SimulateResponse,
)
from .merchant_config import get_config as get_merchant_config
from .merchant_config import reset_config as reset_merchant_config
from .merchant_config import update_config as update_merchant_config
from .schemas import MerchantConfigPatch
from .segment_stats import posterior as segment_posterior
from .service import personalize, simulate
from .sessions import session_store
from .ws import manager as ws_manager

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

    # Track 04: Cash Flow Oracle shares this process. Connect + seed its store
    # so the first /oracle/* request is warm. Non-fatal if it can't.
    try:
        from cash_flow_oracle.api.oracle_routes import _ensure_ready as _cfo_ready

        await _cfo_ready()
        log("cash flow oracle ready (/oracle/*)")
    except Exception as exc:  # noqa: BLE001
        log(f"cash flow oracle warm-up skipped: {exc!r}", level="WARN")

    log(f"ready. latency budget = {settings.LATENCY_BUDGET_MS}ms, db backend = {db.backend}")
    yield
    await get_ip_service().shutdown()
    await db.disconnect()
    try:
        from cash_flow_oracle.db import store as _cfo_store

        await _cfo_store.close()
    except Exception:  # noqa: BLE001
        pass
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
    allow_origins=["*"] if settings.CORS_ALLOW_ALL else settings.CORS_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app" if not settings.CORS_ALLOW_ALL else None,
    allow_credentials=not settings.CORS_ALLOW_ALL,
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

# Track 04: Cash Flow Oracle - /oracle/* on the same service (statistical
# fallbacks for GARCH/HMM/Prophet; prophet/arch/hmmlearn are not in the
# Track 01 image). See docs/ARCHITECTURE.md Track 04.
try:
    from cash_flow_oracle.api.oracle_routes import router as _oracle_router

    app.include_router(_oracle_router)
except Exception as _exc:  # noqa: BLE001
    log(f"cash flow oracle routes not mounted: {_exc!r}", level="WARN")


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
                      "/simulate", "/simulate/ab_test", "/funnel",
                      "/interventions/performance", "/session/create",
                      "/session/{id}", "/sessions/all", "/segment/stats/{key}",
                      "/ws/sessions", "/enrich", "/health", "/docs"],
        "public_base_url": settings.PUBLIC_BASE_URL,
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
            "session_backend": session_store.backend,
            "cache_backend": ip_svc.cache_backend if ip_svc.ready else "n/a",
            "festival_context": market_context.loaded,
            "ws_clients": ws_manager.count,
        },
        "public_base_url": settings.PUBLIC_BASE_URL,
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

    # intervention performance tracker: record what was shown (outcome settles
    # later when the demo session completes / abandons)
    try:
        cfg = response.checkout_config or {}
        items = [(cfg.get("primary_intervention"), "primary"),
                 (cfg.get("secondary_intervention"), "secondary")]
        await db.log_interventions(
            session_id=response.session_id,
            segment_key=_seg_key(db_record),
            product_category=(db_record.get("input_signals") or {}).get("product_category"),
            list_price=response.list_price,
            final_price=response.final_price,
            friction_type=response.friction.primary,
            items=[(i, s) for i, s in items if i],
        )
    except Exception as exc:  # noqa: BLE001
        log(f"intervention logging failed: {exc!r}", level="WARN")

    # if this call belongs to a generated demo session, mark it priced and
    # push the update to the seller dashboard over the websocket
    if payload.session_id:
        try:
            updated = await session_store.mark_priced(
                payload.session_id,
                wtp_score=response.wtp_multiplier,
                price_shown=response.final_price,
                offer_type=response.offer_type,
                result=response.model_dump(),
            )
            if updated:
                await ws_manager.broadcast("session.priced", updated)
        except Exception as exc:  # noqa: BLE001
            log(f"session update failed for {payload.session_id}: {exc!r}", level="WARN")

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
    _JSON_COLS = {"input_signals", "shap_values", "payment_methods_shown", "checkout_config"}

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


@app.get("/funnel")
async def funnel_endpoint() -> dict:
    """Four-stage checkout funnel with friction-attributed drop-off, built from
    the decision log (synthetic cohort mixed in while the log is small)."""
    import anyio

    from .funnel import compute_funnel

    rows = await db.fetch_all()
    return await anyio.to_thread.run_sync(lambda: compute_funnel(rows))


@app.post("/simulate/ab_test")
async def ab_test_endpoint(req: ABTestRequest) -> dict:
    """Synthetic control (flat) vs treatment (friction-aware) experiment for a
    segment. Runs off the request thread so a large cohort doesn't block the
    event loop."""
    import anyio

    from .ab_test import simulate_ab_test

    return await anyio.to_thread.run_sync(
        lambda: simulate_ab_test(req.segment, req.sample_size, seed=req.seed)
    )


# --------------------------------------------------------------------------- #
# Link-generator demo flow
# --------------------------------------------------------------------------- #
def _session_urls(session_id: str) -> tuple[str, str]:
    base = settings.PUBLIC_BASE_URL
    return f"{base}/checkout/{session_id}", f"{base}/merchant/{session_id}"


@app.post("/session/create", response_model=SessionCreateResponse)
async def session_create(req: SessionCreateRequest) -> SessionCreateResponse:
    custom = req.custom.model_dump(exclude_none=True) if req.custom else None
    config = _presets.build_config(req.preset, custom, seed=req.seed)
    segment_key = _presets.segment_key_for(config)

    row = await session_store.create(preset=req.preset, config=config, segment_key=segment_key)
    customer_url, merchant_url = _session_urls(row["session_id"])
    qr = make_qr_data_uri(customer_url)

    await ws_manager.broadcast("session.created", _row_public(row))

    return SessionCreateResponse(
        session_id=row["session_id"],
        merchant_id=row["merchant_id"],
        preset=req.preset,
        config=config,
        segment_key=segment_key,
        customer_url=customer_url,
        merchant_url=merchant_url,
        qr_code_base64=qr,
        status=row["status"],
        created_at=str(row["created_at"]),
    )


@app.get("/merchant/config")
async def merchant_config_get() -> dict:
    return get_merchant_config().to_dict()


@app.put("/merchant/config")
async def merchant_config_put(patch: MerchantConfigPatch) -> dict:
    updated = update_merchant_config(patch.model_dump(exclude_none=True))
    return updated.to_dict()


@app.post("/merchant/config/reset")
async def merchant_config_reset() -> dict:
    return reset_merchant_config().to_dict()


@app.post("/config/derive")
async def config_derive(body: dict) -> dict:
    """Re-derive a full customer config from the raw checkout-form knobs
    (pincode, device, payment, prepaid_orders, return_rate, vpn) WITHOUT
    creating a session. The checkout form calls this as the shopper edits."""
    cfg = _presets.build_config(
        "custom",
        {
            "pin_code": body.get("pin_code"),
            "device_type": body.get("device_type"),
            "payment_method_preference": body.get("payment_method_preference"),
            "payment_split": body.get("payment_split"),
            "prepaid_orders": body.get("prepaid_orders"),
            "return_rate": body.get("return_rate"),
            "vpn": body.get("vpn"),
            "city_tier": body.get("city_tier"),
        },
    )
    return {"config": cfg, "segment_key": _presets.segment_key_for(cfg)}


@app.get("/session/{session_id}", response_model=SessionInfo)
async def session_get(session_id: str) -> SessionInfo:
    row = await session_store.get(session_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not found")
    return SessionInfo(**_row_public(row))


@app.get("/sessions/all", response_model=SessionListResponse)
async def sessions_all(limit: int = 500) -> SessionListResponse:
    rows = await session_store.all(limit=limit)
    return SessionListResponse(
        count=len(rows),
        backend=session_store.backend,
        sessions=[SessionInfo(**_row_public(r)) for r in rows],
    )


@app.post("/session/{session_id}/complete", response_model=SessionInfo)
async def session_complete(session_id: str) -> SessionInfo:
    row = await session_store.set_status(session_id, "converted")
    if not row:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not found")
    try:
        await db.settle_interventions(session_id, True)
    except Exception as exc:  # noqa: BLE001
        log(f"intervention settle failed for {session_id}: {exc!r}", level="WARN")
    pub = _row_public(row)
    await ws_manager.broadcast("session.completed", pub)
    return SessionInfo(**pub)


@app.post("/session/{session_id}/abandon", response_model=SessionInfo)
async def session_abandon(session_id: str) -> SessionInfo:
    row = await session_store.set_status(session_id, "abandoned")
    if not row:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not found")
    try:
        await db.settle_interventions(session_id, False)
    except Exception as exc:  # noqa: BLE001
        log(f"intervention settle failed for {session_id}: {exc!r}", level="WARN")
    pub = _row_public(row)
    await ws_manager.broadcast("session.abandoned", pub)
    return SessionInfo(**pub)


@app.get("/interventions/performance")
async def interventions_performance() -> dict:
    """Conversion rate + revenue-per-shown by intervention, frictions by
    category, and fatigued (segment, intervention) pairs."""
    from .intervention_perf import compute_performance

    evs = await db.intervention_events()
    return compute_performance(evs)


@app.get("/segment/stats/{segment_key:path}")
async def segment_stats(segment_key: str) -> dict:
    rows = await db.fetch_all()
    stats = segment_posterior(segment_key, rows)
    # add a flat-vs-WTP revenue comparison for this segment from the log
    seg_rows = [r for r in rows if _seg_key(r) == segment_key]
    rev = _segment_revenue(seg_rows)
    stats["revenue_simulation"] = rev
    stats["n_customers_like_this"] = len(seg_rows)
    return stats


@app.websocket("/ws/sessions")
async def ws_sessions(ws: WebSocket) -> None:
    await ws_manager.connect(ws)
    try:
        await ws.send_json({"type": "hello", "session": None,
                            "backend": session_store.backend})
        while True:
            # we don't expect client messages; this keeps the socket open
            await ws.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(ws)
    except Exception:  # noqa: BLE001
        await ws_manager.disconnect(ws)


# ---- helpers ---- #
def _row_public(row: dict) -> dict:
    """Session row -> JSON-safe dict matching SessionInfo."""
    keys = ("session_id", "merchant_id", "preset", "config", "status", "created_at",
            "priced_at", "completed_at", "list_price", "price_shown", "wtp_score",
            "offer_type", "segment_key", "result")
    out = {}
    for k in keys:
        v = row.get(k)
        if hasattr(v, "isoformat"):
            v = v.isoformat()
        out[k] = v
    return out


def _seg_key(decision_row: dict) -> str:
    import json as _json

    v = decision_row.get("input_signals")
    sig = _json.loads(v) if isinstance(v, str) else (v or {})
    return "|".join(str(sig.get(k, "?")) for k in
                    ("city_tier", "device_type", "payment_method_preference"))


def _segment_revenue(seg_rows: list[dict]) -> dict:
    import json as _json

    gm = get_merchant_config().gross_margin
    rev_wtp = rev_flat = mgn_wtp = mgn_flat = 0.0
    for r in seg_rows:
        sv = r.get("shap_values")
        sv = _json.loads(sv) if isinstance(sv, str) else (sv or {})
        c_adj = float(sv.get("conversion_at_adjusted") or 0.0)
        c_list = float(sv.get("conversion_at_list") or c_adj)
        lp = float(r.get("list_price") or 0.0)
        fp = float(r.get("final_price") or 0.0)
        cogs = lp * (1.0 - gm)  # same unit cost whatever we charge
        rev_wtp += fp * c_adj
        rev_flat += lp * c_list
        mgn_wtp += (fp - cogs) * c_adj
        mgn_flat += (lp - cogs) * c_list
    rev_lift = rev_wtp - rev_flat
    mgn_lift = mgn_wtp - mgn_flat
    return {
        # topline
        "expected_revenue_wtp_pricing": round(rev_wtp, 2),
        "expected_revenue_flat_pricing": round(rev_flat, 2),
        "revenue_pct_lift": round((rev_lift / rev_flat * 100.0) if rev_flat else 0.0, 3),
        # margin (the headline - a markup is a margin play, same COGS)
        "gross_margin_assumption": gm,
        "expected_margin_wtp_pricing": round(mgn_wtp, 2),
        "expected_margin_flat_pricing": round(mgn_flat, 2),
        "margin_absolute_lift": round(mgn_lift, 2),
        "pct_lift": round((mgn_lift / mgn_flat * 100.0) if mgn_flat else 0.0, 3),
        "n_decisions": len(seg_rows),
        "note": f"expected per impression = value x P(convert at that price). "
                f"Headline pct_lift is on GROSS MARGIN (assumes {gm:.0%} margin, "
                f"COGS unchanged by price) - a markup keeps its extra rupees even "
                f"when a few price-sensitive buyers drop, so revenue lift can be "
                f"flat/negative on a premium segment while margin lift is clearly "
                f"positive. Assumes the conversion model is calibrated; ignores "
                f"repeat-purchase/LTV. Sensitive to sample size + traffic mix.",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)
