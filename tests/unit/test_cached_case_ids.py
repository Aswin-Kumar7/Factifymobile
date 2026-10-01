"""A result served from the cache answers under a case that exists.

When the stored case behind a cache hit could not be read back, the thin result was
served under the id minted for this request - a case never written - and Report, the
correction to send back and the source reader all answered 404 on it (2026-10-02).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.extraction.claims import ExtractedClaims
from tests.unit.factories import claim
from tests.unit.test_orchestration import _result


class _Orchestrator:
    def __init__(self, source_case_id: UUID | None) -> None:
        self.source_case_id = source_case_id
        self.fresh: list[bool] = []

    async def cached(self, intake: Any, *, case_id: UUID) -> Any:
        return _result(case_id=case_id, from_cache=True, source_case_id=self.source_case_id)

    async def verify(self, intake: Any, *, case_id: UUID, fresh: bool = False, **kw: Any) -> Any:
        self.fresh.append(fresh)
        return _result(case_id=case_id)


class _Pipeline:
    async def extract(self, *args: Any, **kwargs: Any) -> ExtractedClaims:
        return ExtractedClaims(claims=(claim(),))


def _client(orchestrator: _Orchestrator) -> TestClient:
    from app.main import create_app

    app = create_app()
    app.state.orchestrator = orchestrator
    app.state.claim_pipeline = _Pipeline()
    # No case reader: the stored case cannot be read back, so the result is thin.
    app.state.case_reader = None
    return TestClient(app)


def test_a_thin_result_carries_the_case_it_was_recorded_under() -> None:
    original = uuid4()
    orchestrator = _Orchestrator(original)

    answered = _client(orchestrator).post("/v1/verify", json={"text": "A forward to check."})

    assert answered.status_code == 200, answered.text
    assert answered.json()["case_id"] == str(original)
    assert answered.json()["from_cache"] is True
    # Served from the cache: nothing was checked again.
    assert orchestrator.fresh == []
