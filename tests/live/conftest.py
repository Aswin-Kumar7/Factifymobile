"""Live tests read the real internet, so they need the operating system's certificates.

On a network that inspects TLS (this development machine's does), httpx's bundled
certificates reject every feed and the ingestion test fails with "no items ingested",
which reads like the feeds are down when they are not. `truststore` uses the system
store instead, as `scripts/serve_local.py` does for the running service. Scoped to
the live tests and undone after each, so nothing else in the run is affected.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _system_certificates() -> Iterator[None]:
    try:
        import truststore
    except ImportError:  # pragma: no cover - a plain CI runner without it
        yield
        return
    truststore.inject_into_ssl()
    try:
        yield
    finally:
        truststore.extract_from_ssl()
