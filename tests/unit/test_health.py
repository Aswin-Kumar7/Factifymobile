"""M01 — the service boots and reports liveness without any dependency."""

import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.main import create_app

pytestmark = pytest.mark.unit


def test_healthz_reports_ok() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "factify",
        "version": __version__,
    }


def test_app_boots_with_no_database_and_no_network() -> None:
    """The factory must not open a connection or call out at import or build time.

    If this ever needs a fixture, a dependency has leaked into construction.
    """
    app = create_app()
    assert app.title == "Factify"


def test_the_trusted_source_counts_come_from_the_list_web_search_uses() -> None:
    """The website quotes these; they must be counted, never typed in."""
    from app.sources.credibility import SourceCredibility

    body = TestClient(create_app()).get("/v1/sources/summary").json()

    trusted = SourceCredibility.load().trusted_hosts
    assert 0 < body["fact_checkers"] < body["sites"] <= len(trusted)
