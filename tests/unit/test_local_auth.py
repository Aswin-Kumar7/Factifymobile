"""Factify's own sign-in: accounts are compulsory, so this has to be right.

Passwords are stored only as scrypt hashes; a wrong password and an unknown email
are refused alike; a session is a random token the server keeps only a hash of; and
Google is trusted only for what Google itself confirms.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from app.accounts.google import GoogleOAuth, GoogleSignInFailed
from app.accounts.local_auth import TOKEN_PREFIX, AuthRefused, Identities, LocalAuth
from app.accounts.passwords import hash_password, verify_password
from app.security.fetcher import FetchResult

pytestmark = pytest.mark.unit


class _Store:
    """The login tables, in memory."""

    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}

    async def login_by_email(self, email: str) -> dict[str, Any] | None:
        return next((u for u in self.users.values() if u["email"] == email.lower()), None)

    async def login_by_google(self, sub: str) -> dict[str, Any] | None:
        return next((u for u in self.users.values() if u["google_sub"] == sub), None)

    async def create_user(self, **f: Any) -> bool:
        if await self.login_by_email(f["email"]):
            return False
        self.users[f["user_id"]] = {
            "user_id": f["user_id"],
            "email": f["email"],
            "password_hash": f["password_hash"],
            "google_sub": f["google_sub"],
            "display_name": f["name"],
            "avatar_url": f["avatar_url"],
        }
        return True

    async def link_google(self, *, user_id: str, sub: str) -> None:
        self.users[user_id]["google_sub"] = sub

    async def create_session(self, **f: Any) -> None:
        self.sessions[f["token_hash"]] = f

    async def session_user(self, token_hash: str, now: datetime) -> dict[str, Any] | None:
        session = self.sessions.get(token_hash)
        if session is None or session["expires_at"] <= now:
            return None
        return self.users[session["user_id"]]

    async def delete_session(self, token_hash: str) -> None:
        self.sessions.pop(token_hash, None)


class TestPasswords:
    def test_a_password_checks_against_its_own_hash_only(self) -> None:
        stored = hash_password("correct horse battery")

        assert stored.startswith("scrypt$")
        assert "correct horse" not in stored
        assert verify_password("correct horse battery", stored)
        assert not verify_password("correct horse batterY", stored)

    def test_the_same_password_hashes_differently_each_time(self) -> None:
        assert hash_password("same password") != hash_password("same password")

    def test_nothing_malformed_ever_matches(self) -> None:
        assert not verify_password("x", None)
        assert not verify_password("x", "")
        assert not verify_password("x", "bcrypt$whatever")
        assert not verify_password("x", "scrypt$not$a$valid$hash")


class TestAccounts:
    @pytest.mark.anyio
    async def test_register_then_the_session_names_the_person(self) -> None:
        auth = LocalAuth(_Store())

        session = await auth.register(
            email=" Asha@Example.org ", password="long enough", name="Asha"
        )

        assert session.token.startswith(TOKEN_PREFIX)
        assert session.method == "password"
        user = await auth.verify(session.token)
        assert user is not None
        assert (user.email, user.name) == ("asha@example.org", "Asha")

    @pytest.mark.anyio
    async def test_signing_in_needs_the_right_password(self) -> None:
        auth = LocalAuth(_Store())
        await auth.register(email="asha@example.org", password="long enough")

        session = await auth.sign_in(email="ASHA@example.org", password="long enough")
        assert await auth.verify(session.token) is not None

        with pytest.raises(AuthRefused) as wrong:
            await auth.sign_in(email="asha@example.org", password="not the password")
        with pytest.raises(AuthRefused) as unknown:
            await auth.sign_in(email="nobody@example.org", password="long enough")
        # The same answer, so it does not reveal who has an account.
        assert wrong.value.reason == unknown.value.reason == "wrong_credentials"

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        ("email", "password", "reason"),
        [
            ("not-an-address", "long enough", "invalid_email"),
            ("asha@example.org", "short", "weak_password"),
        ],
    )
    async def test_what_cannot_make_an_account_says_why(
        self, email: str, password: str, reason: str
    ) -> None:
        with pytest.raises(AuthRefused) as refused:
            await LocalAuth(_Store()).register(email=email, password=password)
        assert refused.value.reason == reason

    @pytest.mark.anyio
    async def test_one_account_per_email(self) -> None:
        auth = LocalAuth(_Store())
        await auth.register(email="asha@example.org", password="long enough")

        with pytest.raises(AuthRefused) as taken:
            await auth.register(email="ASHA@example.org", password="another one")
        assert taken.value.reason == "email_taken"

    @pytest.mark.anyio
    async def test_signing_out_ends_the_session(self) -> None:
        auth = LocalAuth(_Store())
        session = await auth.register(email="asha@example.org", password="long enough")

        await auth.sign_out(session.token)

        assert await auth.verify(session.token) is None

    @pytest.mark.anyio
    async def test_a_session_ends_when_it_expires(self) -> None:
        now = [datetime(2026, 9, 26, tzinfo=UTC)]
        auth = LocalAuth(_Store(), session_days=30, clock=lambda: now[0])
        session = await auth.register(email="asha@example.org", password="long enough")

        now[0] += timedelta(days=31)

        assert await auth.verify(session.token) is None

    @pytest.mark.anyio
    async def test_a_made_up_token_is_nobody(self) -> None:
        auth = LocalAuth(_Store())
        assert await auth.verify(TOKEN_PREFIX + "guessed") is None
        assert await auth.verify("not-even-ours") is None


class TestGoogleAccounts:
    @pytest.mark.anyio
    async def test_a_new_google_person_gets_an_account(self) -> None:
        store = _Store()
        auth = LocalAuth(store)

        session = await auth.sign_in_google(
            sub="g-1", email="Ravi@Gmail.com", name="Ravi", avatar_url=None
        )

        assert session.method == "google"
        assert (await auth.verify(session.token)).email == "ravi@gmail.com"  # type: ignore[union-attr]
        # Made with Google: no password to sign in with.
        with pytest.raises(AuthRefused) as refused:
            await auth.sign_in(email="ravi@gmail.com", password="anything at all")
        assert refused.value.reason == "use_google"

    @pytest.mark.anyio
    async def test_an_existing_email_is_linked_not_duplicated(self) -> None:
        store = _Store()
        auth = LocalAuth(store)
        made = await auth.register(email="ravi@gmail.com", password="long enough")

        session = await auth.sign_in_google(
            sub="g-1", email="ravi@gmail.com", name=None, avatar_url=None
        )

        assert len(store.users) == 1
        assert session.user.id == made.user.id
        # And the password still works too.
        assert await auth.sign_in(email="ravi@gmail.com", password="long enough")


class TestIdentities:
    @pytest.mark.anyio
    async def test_our_sessions_are_checked_here_and_others_elsewhere(self) -> None:
        auth = LocalAuth(_Store())
        session = await auth.register(email="asha@example.org", password="long enough")
        asked: list[str] = []

        class _External:
            async def verify(self, token: str) -> Any:
                asked.append(token)
                return None

        identities = Identities(auth, _External())

        assert await identities.verify(session.token) is not None
        assert await identities.verify("eyJ.supabase.jwt") is None
        assert asked == ["eyJ.supabase.jwt"]


class _Google:
    """Google's token endpoints, answering from a script."""

    def __init__(self, claims: dict[str, Any]) -> None:
        self.claims = claims
        self.form: dict[str, str] = {}

    @staticmethod
    def _reply(url: str, payload: dict[str, Any]) -> FetchResult:
        body = json.dumps(payload).encode()
        return FetchResult(
            url=url,
            final_url=url,
            status_code=200,
            content_type="application/json",
            body=body,
            byte_count=len(body),
            fetched_at=datetime.now(UTC),
        )

    async def post_form(self, url: str, form: dict[str, str], **_: Any) -> FetchResult:
        self.form = form
        return self._reply(url, {"id_token": "the.id.token"})

    async def get_json(self, url: str, **_: Any) -> FetchResult:
        return self._reply(url, self.claims)


def _oauth(claims: dict[str, Any]) -> tuple[GoogleOAuth, _Google]:
    google = _Google(claims)
    oauth = GoogleOAuth(
        client_id="client-1",
        client_secret="secret-1",
        redirect_uri="https://api.factify.example/v1/auth/google/callback",
        fetcher=google,
    )
    return oauth, google


_GOOD = {
    "aud": "client-1",
    "iss": "https://accounts.google.com",
    "sub": "g-1",
    "email": "ravi@gmail.com",
    "email_verified": "true",
    "name": "Ravi",
}


class TestGoogleOAuth:
    @pytest.mark.anyio
    async def test_a_sign_in_this_server_started_comes_back_as_the_person(self) -> None:
        oauth, google = _oauth(_GOOD)
        state = httpx.URL(oauth.start()).params["state"]

        profile = await oauth.finish(code="code-1", state=state)

        assert (profile.sub, profile.email) == ("g-1", "ravi@gmail.com")
        # The secret went to Google's token endpoint, and nowhere near the app.
        assert google.form["client_secret"] == "secret-1"
        assert google.form["redirect_uri"].endswith("/v1/auth/google/callback")

    @pytest.mark.anyio
    async def test_a_state_this_server_did_not_start_is_refused(self) -> None:
        oauth, _ = _oauth(_GOOD)
        with pytest.raises(GoogleSignInFailed):
            await oauth.finish(code="code-1", state="forged")

    @pytest.mark.anyio
    async def test_a_state_works_once(self) -> None:
        oauth, _ = _oauth(_GOOD)
        state = httpx.URL(oauth.start()).params["state"]
        await oauth.finish(code="code-1", state=state)
        with pytest.raises(GoogleSignInFailed):
            await oauth.finish(code="code-1", state=state)

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "change",
        [{"aud": "someone-elses-app"}, {"email_verified": "false"}, {"iss": "evil.example"}],
    )
    async def test_a_token_google_does_not_vouch_for_is_refused(
        self, change: dict[str, str]
    ) -> None:
        oauth, _ = _oauth({**_GOOD, **change})
        state = httpx.URL(oauth.start()).params["state"]
        with pytest.raises(GoogleSignInFailed):
            await oauth.finish(code="code-1", state=state)


class TestTheSignInApi:
    def _app(self, *, required: bool = True) -> Any:
        from app.config import get_settings
        from app.main import create_app

        app = create_app()
        settings = get_settings()
        app.state.settings = settings.model_copy(
            update={"auth": settings.auth.model_copy(update={"required": required})}
        )
        auth = LocalAuth(_Store())
        app.state.local_auth = auth
        app.state.identity = Identities(auth)
        return app

    async def _client(self, app: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")

    @pytest.mark.anyio
    async def test_register_sign_in_and_a_wrong_password(self) -> None:
        app = self._app()
        async with await self._client(app) as api:
            made = await api.post(
                "/v1/auth/register",
                json={"email": "asha@example.org", "password": "long enough", "name": "Asha"},
            )
            assert made.status_code == 201
            assert made.json()["access_token"].startswith(TOKEN_PREFIX)
            assert made.json()["method"] == "password"

            again = await api.post(
                "/v1/auth/register", json={"email": "asha@example.org", "password": "x" * 9}
            )
            assert (again.status_code, again.json()["detail"]) == (409, "email_taken")

            wrong = await api.post(
                "/v1/auth/login", json={"email": "asha@example.org", "password": "wrong one"}
            )
            assert (wrong.status_code, wrong.json()["detail"]) == (401, "wrong_credentials")

            right = await api.post(
                "/v1/auth/login", json={"email": "asha@example.org", "password": "long enough"}
            )
            assert right.status_code == 200

    @pytest.mark.anyio
    async def test_a_new_account_starts_with_its_signup_credits(self) -> None:
        from app.accounts.credits import CreditBook
        from app.orgs import plans
        from tests.unit.test_accounts import _Store as _Accounts

        class _MadeByTheLogin(_Accounts):
            """The account tables, where registering has already made the person."""

            async def upsert(self, user: Any) -> bool:
                await super().upsert(user)
                return False

        app = self._app()
        app.state.credits = CreditBook(_MadeByTheLogin(), signup_credits=100)
        async with await self._client(app) as api:
            made = await api.post(
                "/v1/auth/register", json={"email": "asha@example.org", "password": "long enough"}
            )
            await api.post(
                "/v1/auth/login", json={"email": "asha@example.org", "password": "long enough"}
            )
            me = await api.get(
                "/v1/me", headers={"authorization": f"Bearer {made.json()['access_token']}"}
            )
        # The grant, once, on top of the Free plan's checks this month.
        assert me.json()["credits"]["balance"] == 100 + plans.FREE.monthly_checks
        assert me.json()["plan_usage"]["credits"] == 100

    @pytest.mark.anyio
    async def test_a_check_without_an_account_is_refused(self) -> None:
        async with await self._client(self._app(required=True)) as api:
            response = await api.post("/v1/verify", json={"text": "A forward to check."})
        assert response.status_code == 401

    @pytest.mark.anyio
    async def test_the_config_says_how_to_sign_in(self) -> None:
        async with await self._client(self._app(required=True)) as api:
            config = (await api.get("/v1/auth/config")).json()
        assert config["enabled"] is True
        assert config["required"] is True
        assert config["providers"] == ["password"]  # Google only once it is configured

    @pytest.mark.anyio
    async def test_google_without_a_client_returns_to_the_app_saying_so(self) -> None:
        async with await self._client(self._app()) as api:
            started = await api.get("/v1/auth/google/start", follow_redirects=False)
        assert started.status_code in (302, 307)
        assert started.headers["location"] == "factify://auth-callback#error=google_unavailable"

    @pytest.mark.anyio
    async def test_signing_out_ends_the_session_for_the_server(self) -> None:
        app = self._app()
        async with await self._client(app) as api:
            token = (
                await api.post(
                    "/v1/auth/register",
                    json={"email": "asha@example.org", "password": "long enough"},
                )
            ).json()["access_token"]
            out = await api.post("/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
            assert out.status_code == 204
        assert await app.state.local_auth.verify(token) is None

    @pytest.mark.anyio
    async def test_guessing_is_slowed_per_caller_not_for_everyone_behind_the_proxy(
        self,
    ) -> None:
        """Caddy and the website forward the caller's address in X-Forwarded-For; the
        socket's address is the proxy's, the same for every person."""
        from app.api import accounts

        accounts._attempts.reset()
        async with await self._client(self._app()) as api:

            async def attempt(n: int, address: str) -> int:
                response = await api.post(
                    "/v1/auth/login",
                    json={"email": f"guess{n}@example.org", "password": "wrong one"},
                    headers={"x-forwarded-for": address},
                )
                return response.status_code

            codes = [await attempt(n, "203.0.113.7") for n in range(11)]
            other = await attempt(99, "198.51.100.4")
        accounts._attempts.reset()

        assert codes[:10] == [401] * 10
        assert codes[10] == 429
        assert other == 401

    @pytest.mark.anyio
    async def test_the_review_queue_is_for_staff_only(self) -> None:
        """It lists cases and why each was held back, and records a reviewer's label."""

        class _Queue:
            async def pending(self) -> list[Any]:
                return []

            async def record(self, **_: Any) -> None:
                raise AssertionError("a label was recorded for someone who is not staff")

        class _Orgs:
            async def is_staff(self, user_id: str, email: str, staff: Any) -> bool:
                return False

            async def member(self, org_id: str, user_id: str) -> None:
                return None

        app = self._app(required=False)
        app.state.review_queue = _Queue()
        app.state.orgs = _Orgs()
        label = {"label": "SUPPORTED", "reviewer": "anyone"}
        item = "00000000-0000-0000-0000-000000000001"
        async with await self._client(app) as api:
            anonymous = await api.get("/v1/review")
            token = (
                await api.post(
                    "/v1/auth/register",
                    json={"email": "asha@example.org", "password": "long enough"},
                )
            ).json()["access_token"]
            signed_in = {"Authorization": f"Bearer {token}"}
            listed = await api.get("/v1/review", headers=signed_in)
            labelled = await api.post(f"/v1/review/{item}", json=label, headers=signed_in)
            unsigned = await api.post(f"/v1/review/{item}", json=label)

        assert anonymous.status_code == 401
        assert listed.status_code == 403
        assert labelled.status_code == 403
        assert unsigned.status_code == 401
