"""The sign-in tables (0004_local_auth) against a real database, rolled back per test."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from app.db.repositories import AccountRepository, LoginRepository
from tests.conftest import requires_database

pytestmark = [pytest.mark.anyio, requires_database]


async def _make(conn: Any, email: str) -> str:
    user_id = str(uuid4())
    created = await LoginRepository(conn).create(
        user_id=user_id,
        email=email,
        name="Asha",
        avatar_url=None,
        password_hash="scrypt$16384$8$1$c2FsdA==$aGFzaA==",
        google_sub=None,
    )
    assert created
    return user_id


class TestLogins:
    async def test_a_login_is_found_by_email_in_any_case(self, conn: Any) -> None:
        user_id = await _make(conn, "asha@example.org")

        found = await LoginRepository(conn).by_email("ASHA@Example.org")

        assert found is not None
        assert str(found["user_id"]) == user_id
        assert found["display_name"] == "Asha"

    async def test_one_account_per_email(self, conn: Any) -> None:
        await _make(conn, "asha@example.org")

        again = await LoginRepository(conn).create(
            user_id=str(uuid4()),
            email="Asha@Example.org",
            name=None,
            avatar_url=None,
            password_hash=None,
            google_sub=None,
        )

        assert again is False

    async def test_google_is_linked_and_found(self, conn: Any) -> None:
        user_id = await _make(conn, "ravi@gmail.com")
        repo = LoginRepository(conn)

        await repo.link_google(user_id=user_id, sub="g-1")

        found = await repo.by_google("g-1")
        assert found is not None and str(found["user_id"]) == user_id


class TestSessions:
    async def test_a_session_names_its_person_until_it_ends(self, conn: Any) -> None:
        user_id = await _make(conn, "asha@example.org")
        repo = LoginRepository(conn)
        now = datetime.now(UTC)
        await repo.open_session(
            token_hash="h1", user_id=user_id, method="password", expires_at=now + timedelta(days=1)
        )

        person = await repo.session_person("h1", now)
        assert person is not None and person["email"] == "asha@example.org"

        assert await repo.session_person("h1", now + timedelta(days=2)) is None  # expired
        await repo.close_session("h1")
        assert await repo.session_person("h1", now) is None  # signed out


class TestDeletingAnAccount:
    async def _org(self, conn: Any, *owners: str) -> None:
        cur = await conn.execute("INSERT INTO organisation (name) VALUES ('Newsroom') RETURNING id")
        org_id = (await cur.fetchone())["id"]
        for owner in owners:
            await conn.execute(
                "INSERT INTO org_member (org_id, user_id, role) VALUES (%s, %s, 'owner')",
                (org_id, owner),
            )

    async def test_the_account_and_its_sessions_go(self, conn: Any) -> None:
        user_id = await _make(conn, "asha@example.org")
        repo = LoginRepository(conn)
        now = datetime.now(UTC)
        await repo.open_session(
            token_hash="h1", user_id=user_id, method="password", expires_at=now + timedelta(days=1)
        )

        assert await AccountRepository(conn).delete(user_id=user_id) == []

        assert await repo.session_person("h1", now) is None
        assert await repo.by_email("asha@example.org") is None

    async def test_the_last_owner_of_an_open_organisation_is_refused(self, conn: Any) -> None:
        user_id = await _make(conn, "asha@example.org")
        await self._org(conn, user_id)

        assert await AccountRepository(conn).delete(user_id=user_id) == ["Newsroom"]
        assert await LoginRepository(conn).by_email("asha@example.org") is not None

    async def test_another_owner_lets_the_account_go(self, conn: Any) -> None:
        user_id = await _make(conn, "asha@example.org")
        other = await _make(conn, "ravi@example.org")
        await self._org(conn, user_id, other)

        assert await AccountRepository(conn).delete(user_id=user_id) == []
