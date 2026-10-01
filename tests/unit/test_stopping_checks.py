"""Stopping a background check, and when a check is charged.

Stop on the website stopped only the page following the check: the check ran on to
the end and was charged for an answer nobody was waiting for. And a video was charged
when it was accepted, so one whose check failed, or that was stopped, still cost
three checks. The tests hold that a stopped check is never charged and gives back an
organisation's hold, that only the person who started it can stop it, and that a
video is charged when it has its answer, like any background check (2026-10-02).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.accounts import CreditBook
from app.accounts.identity import AuthUser
from app.extraction.claims import ExtractedClaims
from app.intake.normalizer import InputType
from app.orchestration.background import BackgroundChecks
from tests.unit.factories import claim
from tests.unit.test_accounts import PERSON, _Store
from tests.unit.test_orchestration import _result

OTHER = AuthUser(id=str(uuid4()), email="ravi@example.org", name="Ravi")
ASHA = {"Authorization": "Bearer asha"}
RAVI = {"Authorization": "Bearer ravi"}
FORWARD = {"text": "A forward to check.", "mode": "background"}


class _Blocked:
    """An orchestrator whose check runs until it is let go."""

    def __init__(self) -> None:
        self.go = asyncio.Event()
        self.started = asyncio.Event()

    async def cached(self, intake: Any, *, case_id: UUID) -> Any:
        return None

    async def verify(self, intake: Any, *, case_id: UUID, **kwargs: Any) -> Any:
        self.started.set()
        await self.go.wait()
        return _result(case_id=case_id)


def _app(store: _Store, orchestrator: Any, **state: Any) -> Any:
    from app.main import create_app

    class _Identity:
        async def verify(self, token: str) -> Any:
            return PERSON if token == "asha" else OTHER

    class _Pipeline:
        async def extract(self, *args: Any, **kwargs: Any) -> ExtractedClaims:
            return ExtractedClaims(claims=(claim(),))

    app = create_app()
    app.state.identity = _Identity()
    app.state.credits = CreditBook(store, signup_credits=100)
    app.state.claim_pipeline = _Pipeline()
    app.state.orchestrator = orchestrator
    for name, value in state.items():
        setattr(app.state, name, value)
    return app


def _client(app: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://factify.test")


async def _answered(api: httpx.AsyncClient, case_id: str) -> httpx.Response:
    for _ in range(500):
        polled = await api.get(f"/v1/cases/{case_id}")
        if polled.status_code != 202:
            return polled
        await asyncio.sleep(0.02)
    raise AssertionError("the check never finished")


def _ledger(store: _Store) -> list[tuple[int, str]]:
    return [(entry[1], entry[2]) for entry in store.ledger]


class TestTheRunner:
    @pytest.mark.anyio
    async def test_it_cancels_the_work_and_gives_back_what_was_held(self) -> None:
        runs = BackgroundChecks()
        given_back: list[str] = []
        reached_the_end: list[bool] = []

        async def work(progress: Any) -> str:
            await asyncio.Event().wait()
            reached_the_end.append(True)
            return "verdict"

        async def give_back() -> None:
            given_back.append("hold")

        run = runs.start("case-1", work, owner="asha", on_cancel=give_back)
        await asyncio.sleep(0)

        assert await runs.cancel(run)
        assert run.status == "cancelled"
        assert run.task is not None and run.task.done()
        assert given_back == ["hold"] and reached_the_end == []
        # Stopping it again is not an error.
        assert await runs.cancel(run)

    @pytest.mark.anyio
    async def test_a_check_stopped_before_it_ran_still_gives_back_its_hold(self) -> None:
        runs = BackgroundChecks()
        given_back: list[str] = []

        async def work(progress: Any) -> str:
            return "verdict"

        async def give_back() -> None:
            given_back.append("hold")

        # Cancelled before the task has had a turn: none of `work` ever runs.
        run = runs.start("case-2", work, on_cancel=give_back)
        assert await runs.cancel(run)
        assert given_back == ["hold"] and run.status == "cancelled"

    @pytest.mark.anyio
    async def test_a_finished_or_settling_check_cannot_be_stopped(self) -> None:
        runs = BackgroundChecks()

        async def work(progress: Any) -> str:
            return "verdict"

        done = runs.start("case-3", work)
        await done.task  # type: ignore[misc]
        assert not await runs.cancel(done)
        assert done.status == "done"

        async def slow(progress: Any) -> str:
            await asyncio.Event().wait()
            return "verdict"

        settling = runs.start("case-4", slow)
        settling.settling = True
        assert not await runs.cancel(settling)
        assert settling.status == "running"
        settling.task.cancel()  # type: ignore[union-attr]


class TestStopThroughTheApi:
    @pytest.mark.anyio
    async def test_the_person_who_started_it_stops_it_and_it_costs_nothing(self) -> None:
        store = _Store()
        orchestrator = _Blocked()

        async with _client(_app(store, orchestrator)) as api:
            started = await api.post("/v1/verify", json=FORWARD, headers=ASHA)
            case_id = started.json()["case_id"]
            await orchestrator.started.wait()

            # Someone else cannot stop it, nor learn that it exists.
            assert (await api.delete(f"/v1/cases/{case_id}", headers=RAVI)).status_code == 404
            assert (await api.get(f"/v1/cases/{case_id}")).status_code == 202

            assert (await api.delete(f"/v1/cases/{case_id}", headers=ASHA)).status_code == 204
            # Again: still stopped, still fine.
            assert (await api.delete(f"/v1/cases/{case_id}", headers=ASHA)).status_code == 204
            collected = await api.get(f"/v1/cases/{case_id}")

        assert collected.status_code == 410
        # The signup grant and nothing else: never charged.
        assert _ledger(store) == [(100, "signup_grant")]

    @pytest.mark.anyio
    async def test_a_finished_check_is_too_late_to_stop(self) -> None:
        store = _Store()
        orchestrator = _Blocked()
        orchestrator.go.set()

        async with _client(_app(store, orchestrator)) as api:
            started = await api.post("/v1/verify", json=FORWARD, headers=ASHA)
            case_id = started.json()["case_id"]
            await _answered(api, case_id)

            late = await api.delete(f"/v1/cases/{case_id}", headers=ASHA)
            unknown = await api.delete(f"/v1/cases/{uuid4()}", headers=ASHA)

        assert late.status_code == 409
        assert unknown.status_code == 404
        assert _ledger(store) == [(100, "signup_grant"), (-1, "check")]

    @pytest.mark.anyio
    async def test_an_organisations_hold_is_given_back_and_never_settled(self) -> None:
        class _Orgs:
            def __init__(self) -> None:
                self.held: list[Any] = []
                self.released: list[Any] = []
                self.settled: list[Any] = []

            async def member(self, org_id: str, user_id: str) -> dict[str, str]:
                return {"role": "member"}

            async def hold(self, payer: Any, cost: int) -> Any:
                hold = SimpleNamespace(payer=payer, cost=cost, remaining=99)
                self.held.append(hold)
                return hold

            async def release(self, hold: Any) -> None:
                self.released.append(hold)

            async def settle(self, hold: Any) -> None:
                self.settled.append(hold)

            async def record_check(self, *args: Any, **kwargs: Any) -> None:
                return None

        orgs = _Orgs()
        orchestrator = _Blocked()

        async with _client(_app(_Store(), orchestrator, orgs=orgs)) as api:
            started = await api.post(
                "/v1/verify", json=FORWARD, headers={**ASHA, "X-Factify-Account": "org-1"}
            )
            case_id = started.json()["case_id"]
            await orchestrator.started.wait()
            stopped = await api.delete(f"/v1/cases/{case_id}", headers=ASHA)

        assert stopped.status_code == 204
        assert len(orgs.held) == 1
        assert orgs.released == orgs.held and orgs.settled == []


class TestAVideoIsChargedWhenItHasItsAnswer:
    @staticmethod
    def _video(monkeypatch: pytest.MonkeyPatch, check: Any) -> None:
        import app.api.verify as verify

        async def read(request: Any, file: Any, consent: bool) -> Any:
            return SimpleNamespace(input_type=InputType.VIDEO), b"video"

        monkeypatch.setattr(verify, "_read_upload", read)
        monkeypatch.setattr(verify, "_checked_video", check)

    @staticmethod
    async def _upload(api: httpx.AsyncClient, background: str) -> httpx.Response:
        return await api.post(
            "/v1/verify/file",
            files={"file": ("clip.mp4", b"video", "video/mp4")},
            data={"consent_to_process_media": "true", "background": background},
            headers=ASHA,
        )

    @pytest.mark.anyio
    @pytest.mark.parametrize("background", ["true", "false"])
    async def test_charged_only_once_it_is_answered(
        self, monkeypatch: pytest.MonkeyPatch, background: str
    ) -> None:
        from app.api.verify import to_response

        go = asyncio.Event()

        async def check(
            request: Any, intake: Any, data: bytes, *, case_id: UUID, recheck: bool
        ) -> Any:
            await go.wait()
            return to_response(_result(case_id=case_id))

        self._video(monkeypatch, check)
        store = _Store()
        app = _app(store, _Blocked())
        cost = app.state.settings.auth.video_check_cost

        async with _client(app) as api:
            started = await self._upload(api, background)
            assert started.status_code == 202
            # Accepted, and not yet charged.
            assert _ledger(store) == [(100, "signup_grant")]

            go.set()
            answered = await _answered(api, started.json()["case_id"])

        assert answered.status_code == 200
        assert _ledger(store) == [(100, "signup_grant"), (-cost, "check")]

    @pytest.mark.anyio
    async def test_a_video_whose_check_fails_costs_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def check(
            request: Any, intake: Any, data: bytes, *, case_id: UUID, recheck: bool
        ) -> Any:
            raise HTTPException(422, "no frames could be read")

        self._video(monkeypatch, check)
        store = _Store()

        async with _client(_app(store, _Blocked())) as api:
            started = await self._upload(api, "true")
            answered = await _answered(api, started.json()["case_id"])

        assert answered.status_code == 422
        assert _ledger(store) == [(100, "signup_grant")]
