"""
FastAPI sub-router mounted by the main API at `/enrich`.

    from ip_enrichment.router import router as enrich_router
    app.include_router(enrich_router)

Endpoints:
  POST /enrich          {"ip": "..."}         -> full EnrichmentResult
  GET  /enrich/{ip}                            -> full EnrichmentResult
  GET  /enrich/health                          -> module readiness + geo mode
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .models import EnrichRequest, EnrichmentResult
from .service import get_service

router = APIRouter(prefix="/enrich", tags=["ip-enrichment"])


@router.get("/health")
async def health() -> dict:
    svc = get_service()
    return {
        "ready": svc.ready,
        "geo_mode": "mock" if svc.mock_geo_mode else "maxmind",
        "cache_backend": svc.cache_backend if svc.ready else "n/a",
    }


@router.post("", response_model=EnrichmentResult)
async def enrich_post(req: EnrichRequest) -> EnrichmentResult:
    svc = get_service()
    if not svc.ready:
        await svc.startup()
    if not req.ip or not req.ip.strip():
        raise HTTPException(status_code=422, detail="ip is required")
    return await svc.enrich(req.ip)


@router.get("/{ip}", response_model=EnrichmentResult)
async def enrich_get(ip: str) -> EnrichmentResult:
    svc = get_service()
    if not svc.ready:
        await svc.startup()
    return await svc.enrich(ip)
