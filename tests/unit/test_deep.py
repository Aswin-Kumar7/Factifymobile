"""Deep checks: a longer, wider check that runs in the background while the app polls.

The same pipeline as a normal check, run with the deep profile; the tests hold that it
is really deep (the profile is in force inside the check), that it answers at once
with a case id, that polling shows progress and then the verdict, and that it is
charged — three credits — only when it finishes.
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
from app.orchestration.deep import DeepChecks
from app.sources.base import DEEP, NORMAL, current_depth
from tests.unit.factories import claim
from tests.unit.test_accounts import PERSON, _Store
from tests.unit.test_orchestration import _result


class TestTheBackgroundRunner:
    @pytest.mark.anyio
    async def test_progress_is_visible_and_the_result_is_kept(self) -> None:
        runs = DeepChecks()
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
        runs = DeepChecks()

        async def work(progress: Any) -> None:
            raise HTTPException(422, "no checkable claims were found on the page")

        run = runs.start("case-2", work)
        await run.task  # type: ignore[misc]

        assert run.status == "failed"
        assert (run.error_status, run.error_detail) == (
            422,
            "no checkable claims were found on the page",
        )


class TestADeepCheckThroughTheApi:
    @pytest.mark.anyio
    async def test_it_answers_at_once_runs_deep_and_is_charged_when_done(self) -> None:
        from app.main import create_app

        seen_depth: list[str] = []
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
                seen_depth.append(current_depth.get().name)
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
                json={"text": "A forward to check deeply.", "mode": "deep"},
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
        assert seen_depth == [DEEP.name]  # the deep profile was in force
        assert current_depth.get() is NORMAL  # and did not leak out of the check
        assert [(e[1], e[2]) for e in store.ledger] == [(100, "signup_grant"), (-3, "deep_check")]
