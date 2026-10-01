"""Application factory.

One deployable FastAPI service with internal modules (codexplan.md §4) — not seven
microservices. The factory shape exists so tests can build an app without importing
global state, and so later modules (M04 observability, M12 rate limiting) attach
middleware in one known place.
"""

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.api import accounts, admin, billing, health, orgs, pages, verify
from app.config import Settings, get_settings
from app.observability import RequestContextMiddleware, configure
from app.orchestration.background import BackgroundChecks
from app.orchestration.progress import progress_bus
from app.orgs.errors import ApiError

logger = logging.getLogger("factify.main")

if sys.platform == "win32":
    # psycopg's async mode refuses to run on Windows' default ProactorEventLoop, and
    # the failure surfaces as "pool initialization incomplete after 10.0 sec" — a
    # timeout that reads like an unreachable database rather than a loop mismatch.
    #
    # Set here because it must happen before any loop is created, and `create_app` is
    # too late when a server has already started one. Deployment is Linux, where this
    # branch never runs; it exists so local development on Windows works at all.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

DESCRIPTION = """
Factify verifies content against citable evidence.

Every decisive verdict carries at least one citation with a fetched excerpt and an
anchor into the source. A claim with no citable evidence returns `UNVERIFIED` — that
is the designed answer, not a failure.

Forensic signals appear in `advisories`, never inside `evidence`. They are shown for
transparency and are not used in any verdict.
""".strip()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application.

    Settings are resolved here so an invalid configuration is a boot failure rather
    than a surprise at first use. Middleware order matters and is fixed here: request
    context is established before anything else so every downstream log line and
    response carries it.
    """
    settings = settings or get_settings()
    configure(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Open the pool and compose the verification stack.

        A composition failure is logged and left to stand rather than raised: the
        health endpoint must still answer so a failing deployment can be diagnosed,
        and `/verify` already returns 503 when no orchestrator is present. Crashing
        the boot instead would leave nothing to ask.
        """
        from app.orchestration import composition

        try:
            for name, value in (await composition.build(settings)).items():
                setattr(app.state, name, value)
        except Exception as error:
            logger.exception("composition failed; /verify will report unavailable: %s", error)

        # The news, collected in the background while the service runs.
        ingestion = getattr(app.state, "ingestion", None)
        if ingestion is not None:
            ingestion.start()

        yield

        if ingestion is not None:
            await ingestion.stop()

        database = getattr(app.state, "database", None)
        if database is not None:
            await database.close()

    app = FastAPI(
        lifespan=lifespan,
        title="Factify",
        version=__version__,
        summary="Evidence-based content verification",
        description=DESCRIPTION,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.state.settings = settings
    # Deep checks run in the background; the app polls them by case id.
    app.state.background_checks = BackgroundChecks()
    # What a watched check is doing, for the Checking screen (contract 1.3).
    redis_url = settings.progress_redis_url
    app.state.progress_bus = progress_bus(redis_url.get_secret_value() if redis_url else None)

    # Outermost: every log line and every response — including error responses —
    # carries the request identifier.
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, error: ApiError) -> JSONResponse:
        # A human message and a machine-readable code, for API callers.
        return JSONResponse(
            {"detail": error.message, "error_code": error.error_code},
            status_code=error.status_code,
            headers=error.headers,
        )

    @app.middleware("http")
    async def _credit_headers(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        used = getattr(request.state, "credits_used", None)
        if used is not None:
            response.headers["Factify-Credits-Used"] = str(used)
            response.headers["Factify-Credits-Remaining"] = str(
                getattr(request.state, "credits_remaining", "")
            )
        return response

    app.include_router(health.router)
    app.include_router(verify.router)
    app.include_router(accounts.router)
    app.include_router(orgs.router)
    app.include_router(admin.router)
    app.include_router(billing.router)
    app.include_router(pages.router)

    # Excluded from the published schema and authenticated with a shared secret. It
    # is included last so it cannot shadow a public route by accident.
    app.include_router(verify.internal)

    return app


app = create_app()
