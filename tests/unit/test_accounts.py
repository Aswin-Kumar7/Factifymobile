"""Accounts: who is checking, and the credit book that decides what they may spend.

Everything is decided on the server. Until plans exist, usage is recorded and nothing
is refused; the tests hold both halves — recorded now, refusable later by a setting.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.accounts import AuthUser, CreditBook, IdentityUnavailable, SupabaseIdentity
from app.security.fetcher import FetchFailure, FetchResult
from tests.unit.test_orchestration import _result

PERSON = AuthUser(id=str(uuid4()), email="asha@example.org", name="Asha")


def _answer(status: int, payload: object) -> FetchResult:
    body = json.dumps(payload).encode()
    return FetchResult(
        url="https://project.supabase.co/auth/v1/user",
        final_url="https://project.supabase.co/auth/v1/user",
        status_code=status,
        content_type="application/json",
        body=body,
        byte_count=len(body),
        fetched_at=datetime.now(UTC),
    )


class _Supabase:
    """Answers `/auth/v1/user` from a script, and counts the calls."""

    def __init__(self, answer: FetchResult | FetchFailure) -> None:
        self.answer = answer
        self.calls: list[dict[str, str]] = []

    async def get_json(self, url: str, *, provider: str, headers: dict[str, str]) -> Any:
        self.calls.append(headers)
        return self.answer


class _Store:
    """The account tables, in memory."""

    def __init__(self) -> None:
        self.users: dict[str, dict[str, object]] = {}
        self.ledger: list[tuple[str, int, str, str]] = []

    async def upsert(self, user: AuthUser) -> bool:
        created = user.id not in self.users
        self.users.setdefault(
            user.id,
            {"email": user.email, "display_name": user.name, "plan": "free",
             "created_at": datetime.now(UTC), "survey_state": "due"},
        )  # fmt: skip
        return created

    async def record(self, user_id: str, delta: int, reason: str, request_key: str) -> bool:
        if any(e[0] == user_id and e[3] == request_key for e in self.ledger):
            return False
        self.ledger.append((user_id, delta, reason, request_key))
        return True

    async def totals(self, user_id: str) -> tuple[int, int, int]:
        mine = [e[1] for e in self.ledger if e[0] == user_id]
        return sum(mine), -sum(d for d in mine if d < 0), sum(1 for d in mine if d < 0)

    async def profile(self, user_id: str) -> dict[str, object] | None:
        return self.users.get(user_id)

    async def set_name(self, user_id: str, name: str) -> None:
        self.users[user_id]["display_name"] = name

    async def set_survey(self, user_id: str, state: str, answers: dict[str, object] | None) -> None:
        self.users[user_id].update(survey_state=state, survey=answers)


class TestSignInIsCheckedWithSupabase:
    def _identity(self, answer: FetchResult | FetchFailure) -> tuple[SupabaseIdentity, _Supabase]:
        supabase = _Supabase(answer)
        now = [0.0]
        identity = SupabaseIdentity(
            url="https://project.supabase.co", anon_key="public", fetcher=supabase,
            clock=lambda: now[0],
        )  # fmt: skip
        identity._now = now  # type: ignore[attr-defined]
        return identity, supabase

    @pytest.mark.anyio
    async def test_a_valid_session_is_the_person_it_belongs_to(self) -> None:
        identity, supabase = self._identity(
            _answer(200, {"id": PERSON.id, "email": PERSON.email,
                          "user_metadata": {"full_name": "Asha", "avatar_url": "https://a/p.png"}})
        )  # fmt: skip

        user = await identity.verify("token")

        assert user == AuthUser(PERSON.id, PERSON.email, "Asha", "https://a/p.png")
        assert supabase.calls[0] == {"apikey": "public", "Authorization": "Bearer token"}

    @pytest.mark.anyio
    async def test_a_session_supabase_rejects_is_nobody(self) -> None:
        identity, _ = self._identity(_answer(401, {"message": "invalid JWT"}))

        assert await identity.verify("expired") is None

    @pytest.mark.anyio
    async def test_supabase_being_down_is_an_outage_not_a_sign_out(self) -> None:
        identity, _ = self._identity(
            FetchFailure(
                url="https://project.supabase.co", reason="request timed out", kind="timeout"
            )
        )

        with pytest.raises(IdentityUnavailable):
            await identity.verify("token")

    @pytest.mark.anyio
    async def test_the_answer_is_remembered_for_a_minute(self) -> None:
        identity, supabase = self._identity(_answer(200, {"id": PERSON.id, "email": PERSON.email}))

        await identity.verify("token")
        await identity.verify("token")
        identity._now[0] = 61.0  # type: ignore[attr-defined]
        await identity.verify("token")

        assert len(supabase.calls) == 2


class TestTheCreditBook:
    @pytest.mark.anyio
    async def test_a_new_account_is_granted_its_starting_credits_once(self) -> None:
        book = CreditBook(_Store(), signup_credits=100)

        first = await book.account(PERSON)
        again = await book.account(PERSON)

        assert first.balance == again.balance == 100
        assert first.used == 0

    @pytest.mark.anyio
    async def test_someone_their_login_made_is_granted_on_arrival_once(self) -> None:
        store = _Store()
        await store.upsert(PERSON)  # as a Factify login does, at registration
        book = CreditBook(store, signup_credits=100)

        first = await book.account(PERSON, arriving=True)
        again = await book.account(PERSON, arriving=True)

        assert first.balance == again.balance == 100

    @pytest.mark.anyio
    async def test_a_check_is_recorded_and_nothing_is_refused_while_unlimited(self) -> None:
        book = CreditBook(_Store(), signup_credits=1)

        for _ in range(3):
            assert (await book.authorize(PERSON, 1)).allowed
            await book.charge(PERSON, 1, "check")

        account = await book.account(PERSON)
        assert account.balance == -2  # recorded honestly, not capped
        assert account.used == 3 and account.checks == 3

    @pytest.mark.anyio
    async def test_when_enforced_an_empty_balance_is_refused(self) -> None:
        book = CreditBook(_Store(), signup_credits=1, enforce=True)

        assert (await book.authorize(PERSON, 1)).allowed
        await book.charge(PERSON, 1, "check")

        decision = await book.authorize(PERSON, 1)
        assert not decision.allowed and decision.balance == 0

    @pytest.mark.anyio
    async def test_the_ledger_records_that_a_check_happened_not_what_it_was(self) -> None:
        store = _Store()
        book = CreditBook(store, signup_credits=0)

        await book.charge(PERSON, 1, "check")

        ((_, delta, reason, key),) = store.ledger
        assert (delta, reason) == (-1, "check")
        assert key.startswith("check:")  # a random key, linked to no case


class TestTheAccountEndpoints:
    def _app(self, *, enforce: bool = False, balance: int = 100) -> tuple[Any, _Store, list[int]]:
        from app.main import create_app

        store = _Store()
        ran: list[int] = []

        class _Identity:
            async def verify(self, token: str) -> AuthUser | None:
                return PERSON if token == "good" else None

        class _Orchestrator:
            async def cached(self, intake: Any, *, case_id: UUID) -> Any:
                ran.append(1)
                return _result(case_id=case_id, from_cache=True)

            async def verify(self, *args: Any, **kwargs: Any) -> Any:
                raise AssertionError("served from the cache in this test")

        app = create_app()
        app.state.identity = _Identity()
        app.state.credits = CreditBook(store, signup_credits=balance, enforce=enforce)
        app.state.orchestrator = _Orchestrator()
        return app, store, ran

    def test_your_account_needs_you_to_be_signed_in(self) -> None:
        app, _, _ = self._app()

        assert TestClient(app).get("/v1/me").status_code == 401
        assert (
            TestClient(app).get("/v1/me", headers={"Authorization": "Bearer bad"}).status_code
            == 401
        )

    def test_your_account_shows_your_name_email_and_credits(self) -> None:
        app, _, _ = self._app()

        body = TestClient(app).get("/v1/me", headers={"Authorization": "Bearer good"}).json()

        assert body["email"] == PERSON.email and body["name"] == "Asha"
        assert body["credits"]["balance"] == 100
        assert body["credits"]["check_cost"] == 1
        assert body["credits"]["limited"] is False

    def test_a_signed_in_check_costs_one_credit_and_an_anonymous_one_nothing(self) -> None:
        app, store, _ = self._app()
        client = TestClient(app)

        client.post("/v1/verify", json={"text": "A forward."})
        signed = client.post(
            "/v1/verify", json={"text": "A forward."}, headers={"Authorization": "Bearer good"}
        )

        assert signed.status_code == 200
        assert [(e[1], e[2]) for e in store.ledger] == [(100, "signup_grant"), (-1, "check")]

    def test_an_empty_balance_is_refused_only_when_credits_are_enforced(self) -> None:
        app, _, ran = self._app(enforce=True, balance=0)

        response = TestClient(app).post(
            "/v1/verify", json={"text": "A forward."}, headers={"Authorization": "Bearer good"}
        )

        assert response.status_code == 402
        assert "out of credits" in response.json()["detail"]
        assert ran == []  # decided before any work was done

    def test_you_can_change_your_display_name(self) -> None:
        app, _, _ = self._app()

        body = (
            TestClient(app)
            .patch("/v1/me", json={"name": "Asha K"}, headers={"Authorization": "Bearer good"})
            .json()
        )

        assert body["name"] == "Asha K"

    def test_a_new_account_is_asked_the_survey_until_it_answers(self) -> None:
        app, store, _ = self._app()
        client = TestClient(app)
        me = {"Authorization": "Bearer good"}

        assert client.get("/v1/me", headers=me).json()["survey_due"] is True
        answered = client.put(
            "/v1/me/survey",
            json={"role": "journalist", "places": ["youtube", "whatsapp", "whatsapp"],
                  "wants": ["videos"], "heard": None},
            headers=me,
        )  # fmt: skip

        assert answered.status_code == 200 and answered.json()["survey_due"] is False
        assert store.users[PERSON.id]["survey"] == {
            "role": "journalist", "places": ["whatsapp", "youtube"], "wants": ["videos"],
            "heard": None,
        }  # fmt: skip
        assert client.get("/v1/me", headers=me).json()["survey_due"] is False

    def test_the_survey_can_be_skipped_and_is_not_asked_again(self) -> None:
        app, store, _ = self._app()
        client = TestClient(app)
        me = {"Authorization": "Bearer good"}

        body = client.put("/v1/me/survey", json={"skipped": True}, headers=me).json()

        assert body["survey_due"] is False
        assert store.users[PERSON.id]["survey_state"] == "skipped"
        assert store.users[PERSON.id]["survey"] is None

    def test_only_the_surveys_own_answers_are_stored(self) -> None:
        app, store, _ = self._app()
        client = TestClient(app)
        me = {"Authorization": "Bearer good"}
        client.get("/v1/me", headers=me)

        response = client.put("/v1/me/survey", json={"role": "anything I like"}, headers=me)

        assert response.status_code == 422
        assert store.users[PERSON.id]["survey_state"] == "due"
        assert TestClient(app).put("/v1/me/survey", json={"skipped": True}).status_code == 401

    def test_sign_in_config_is_off_until_the_servers_sign_in_is_composed(self) -> None:
        """Sign-in is this server's own now: nothing about a third-party auth
        project, and no key of any kind, is handed to the app."""
        from app.main import create_app

        body = TestClient(create_app()).get("/v1/auth/config").json()

        assert body["enabled"] is False
        assert body["providers"] == []
        assert "anon_key" not in body
