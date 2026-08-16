"""Application factory.

One deployable FastAPI service with internal modules (codexplan.md §4) — not seven
microservices. The factory shape exists so tests can build an app without importing
global state, and so later modules (M04 observability, M12 rate limiting) attach
middleware in one known place.
"""

from fastapi import FastAPI

from app import __version__
from app.api import health, verify
from app.config import Settings, get_settings
from app.observability import RequestContextMiddleware, configure

DESCRIPTION = """
Facify verifies content against citable evidence.

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

    app = FastAPI(
        title="Facify",
        version=__version__,
        summary="Evidence-based content verification",
        description=DESCRIPTION,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.state.settings = settings

    # Outermost: every log line and every response — including error responses —
    # carries the request identifier.
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)
    app.include_router(verify.router)

    # Excluded from the published schema and authenticated with a shared secret. It
    # is included last so it cannot shadow a public route by accident.
    app.include_router(verify.internal)

    return app


app = create_app()
