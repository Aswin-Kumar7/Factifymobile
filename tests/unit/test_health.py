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
        "service": "facify",
        "version": __version__,
    }


def test_app_boots_with_no_database_and_no_network() -> None:
    """The factory must not open a connection or call out at import or build time.

    If this ever needs a fixture, a dependency has leaked into construction.
    """
    app = create_app()
    assert app.title == "Facify"
