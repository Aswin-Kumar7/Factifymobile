"""Liveness endpoints, and the size of the trusted-source list.

Deliberately dependency-free: it reports that the process is up and which build is
running. It does not probe the database or any provider, so an external outage can
never make the container look dead to the platform's health check.
"""

import json
from functools import cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app import __version__
from app.sources.credibility import SourceCredibility

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


class SourcesResponse(BaseModel):
    """How many sites web search may cite, as the website states it."""

    # Publishers, fact-checkers and official sites named one by one in
    # data/source_credibility.json; government and university domains trusted by
    # their registry (gov.in, ac.uk ...) are not counted.
    sites: int
    # Of those, fact-checkers: IFCN or EFCSN verified now, or verified in the past.
    fact_checkers: int


_SUFFIX_CATEGORY = "government_and_academic_domains"


@cache
def _source_counts() -> SourcesResponse:
    """Counted from the same list, loaded the same way, as web search uses."""
    credibility = SourceCredibility.load()
    path = Path(__file__).resolve().parents[2] / "data" / "source_credibility.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        suffixes = {
            str(d).strip().lower().removeprefix("www.").rstrip(".")
            for d in raw.get(_SUFFIX_CATEGORY, [])
        }
    except (OSError, json.JSONDecodeError, AttributeError):
        suffixes = set()
    sites = [h for h in credibility.trusted_hosts if h not in suffixes]
    return SourcesResponse(
        sites=len(sites), fact_checkers=sum(credibility.is_fact_checker(h) for h in sites)
    )


@router.get("/v1/sources/summary", response_model=SourcesResponse, summary="Trusted-source counts")
async def sources_summary() -> SourcesResponse:
    """The numbers the website quotes, so they are never typed in by hand."""
    return _source_counts()
