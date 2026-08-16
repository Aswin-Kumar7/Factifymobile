"""Liveness endpoint.

Deliberately dependency-free: it reports that the process is up and which build is
running. It does not probe the database or any provider, so an external outage can
never make the container look dead to the platform's health check.
"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__

router = APIRouter(tags=["ops"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["facify"]
    version: str


@router.get("/healthz", response_model=HealthResponse, summary="Liveness probe")
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok", service="facify", version=__version__)
