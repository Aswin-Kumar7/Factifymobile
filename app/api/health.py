"""Liveness endpoint.

Deliberately dependency-free: it reports that the process is up and which build is
running. It does not probe the database or any provider, so an external outage can
never make the container look dead to the platform's health check.
"""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app import __version__

router = APIRouter(tags=["ops"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["factify"]
    version: str


@router.get("/healthz", response_model=HealthResponse, summary="Liveness probe")
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok", service="factify", version=__version__)


class ReadyResponse(BaseModel):
    ready: bool
    missing: tuple[str, ...] = ()


@router.get("/readyz", response_model=ReadyResponse, summary="Readiness probe")
async def readyz(request: Request) -> ReadyResponse:
    """Whether this instance can actually verify anything.

    Liveness and readiness were the same signal, so a deployment whose composition
    failed — no database, no orchestrator — looked exactly like a healthy one until
    someone submitted a claim and read the 503. The lifespan deliberately survives a
    composition failure so the process can be diagnosed; this endpoint is where that
    survival stops looking like health.
    """
    missing = tuple(
        name
        for name in ("database", "orchestrator", "claim_pipeline")
        if getattr(request.app.state, name, None) is None
    )
    return ReadyResponse(ready=not missing, missing=missing)
