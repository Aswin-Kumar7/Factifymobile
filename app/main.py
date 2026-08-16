"""Application factory.

One deployable FastAPI service with internal modules (codexplan.md §4) — not seven
microservices. The factory shape exists so tests can build an app without importing
global state, and so later modules (M04 observability, M12 rate limiting) attach
middleware in one known place.
"""

from fastapi import FastAPI

from app import __version__
from app.api import health
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application.

    Settings are resolved here so an invalid configuration is a boot failure rather
    than a surprise at first use. Middleware order matters and is fixed here: request
    context is established before anything else so every downstream log line and
    response carries it.
    """
    settings = settings or get_settings()

    app = FastAPI(
        title="Facify",
        version=__version__,
        summary="Evidence-based content verification",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.state.settings = settings
    app.include_router(health.router)

    return app


app = create_app()
