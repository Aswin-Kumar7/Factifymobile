"""Background checks: every claim checked, while the app polls for progress.

The same pipeline as a check answered in one request, run with the background budget
and patience; the tests hold that the budget really is in force inside the check,
that it answers at once with a case id, that polling shows progress and then the
verdict, and that it is charged - one credit, like any check - only when it finishes.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import HTTPException

from app.accounts import CreditBook
from app.extraction.claims import ExtractedClaims
from app.orchestration.background import BackgroundChecks
from app.orchestration.pipeline import BACKGROUND_SECONDS
from app.security.patience import BRIEF, PATIENT, current_patience
from app.sources.base import check_seconds
from tests.unit.factories import claim
from tests.unit.test_accounts import PERSON, _Store
from tests.unit.test_orchestration import _result


class TestTheBackgroundRunner:
    @pytest.mark.anyio
    async def test_progress_is_visible_and_the_result_is_kept(self) -> None:
        runs = BackgroundChecks()
        release = asyncio.Event()

        async def work(progress: Any) -> str:
            progress(1, 4)
            await release.wait()
            progress(4, 4)
            return "verdict"

        run = runs.start("case-1", work)
        await asyncio.sleep(0)
        assert (run.status, run.claims_done, run.claims_total) == ("running", 1, 4)

        release.set()
        await run.task  # type: ignore[misc]
        assert runs.get("case-1").response == "verdict"  # type: ignore[union-attr]
        assert run.status == "done"

    @pytest.mark.anyio
    async def test_a_refusal_is_delivered_when_collected(self) -> None:
        runs = BackgroundChecks()

        async def work(progress: Any) -> None:
            raise HTTPException(422, "no checkable claims were found on the page")

        run = runs.start("case-2", work)
        await run.task  # type: ignore[misc]

        assert run.status == "failed"
        assert (run.error_status, run.error_detail) == (
            422,
            "no checkable claims were found on the page",
        )


class TestABackgroundCheckThroughTheApi:
    @pytest.mark.anyio
    @pytest.mark.parametrize("mode", ["background", "deep"])
    async def test_it_answers_at_once_takes_its_time_and_is_charged_when_done(
        self, mode: str
    ) -> None:
        from app.main import create_app

        seen: list[tuple[float | None, Any]] = []
        store = _Store()

        class _Identity:
            async def verify(self, token: str) -> Any:
                return PERSON

        class _Pipeline:
            async def extract(self, *args: Any, **kwargs: Any) -> ExtractedClaims:
                return ExtractedClaims(claims=(claim(),))

        class _Orchestrator:
            async def cached(self, intake: Any, *, case_id: UUID) -> Any:
                return None

            async def verify(self, intake: Any, *, case_id: UUID, **kwargs: Any) -> Any:
                seen.append((check_seconds.get(), current_patience.get()))
                await asyncio.sleep(0.05)
                return _result(case_id=case_id)

        app = create_app()
        app.state.identity = _Identity()
        app.state.credits = CreditBook(store, signup_credits=100)
        app.state.claim_pipeline = _Pipeline()
        app.state.orchestrator = _Orchestrator()

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://factify.test") as api:
            started = await api.post(
                "/v1/verify",
                # "deep", the name an older app sends, runs the same one check.
                json={"text": "A forward to check.", "mode": mode},
                headers={"Authorization": "Bearer good"},
            )
            assert started.status_code == 202
            case_id = started.json()["case_id"]

            while True:
                polled = await api.get(f"/v1/cases/{case_id}")
                if polled.status_code != 202:
                    break
                assert polled.json()["status"] == "processing"
                await asyncio.sleep(0.02)

        assert polled.status_code == 200
        assert polled.json()["case_id"] == case_id
        # The background budget and patience were in force inside the check...
        assert seen == [(BACKGROUND_SECONDS, PATIENT)]
        # ...and did not leak out of it.
        assert (check_seconds.get(), current_patience.get()) == (None, BRIEF)
        assert [(e[1], e[2]) for e in store.ledger] == [(100, "signup_grant"), (-1, "check")]
