"""
Standalone runner for the enrichment module (useful for local testing and as
its own container if you want to scale it separately).

    uvicorn ip_enrichment.app:app --port 8100
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .router import router
from .service import get_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_service().startup()
    yield
    await get_service().shutdown()


app = FastAPI(
    title="IP Enrichment Service",
    version="1.0.0",
    description="VPN / datacenter / public-network detection for checkout trust scoring.",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/")
async def root() -> dict:
    return {"service": "ip-enrichment", "docs": "/docs", "enrich": "POST /enrich"}
