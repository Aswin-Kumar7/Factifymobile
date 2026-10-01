"""Factify's own sign-in: an account made with an email and a password, or with Google.

Accounts are compulsory - every check is made by a signed-in person - and this
module is what makes that possible without depending on a third-party auth service.
It creates the person (`app_user`, the same row credits and the profile use), checks
their password or their Google identity, and issues the session the app sends with
every request.

A session is an opaque random token. The app holds it; the server keeps only its
SHA-256, so the session table cannot be replayed if it is ever read. Sessions last
`session_days` and end on sign-out.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from app.accounts.identity import AuthUser
from app.accounts.passwords import hash_password, verify_password

# Every token this module issues starts with this, so a request's token can be sent
# to the right checker without trying each in turn.
TOKEN_PREFIX = "fs_"  # noqa: S105 - a label, not a secret

# Deliberately loose: an address is checked by using it, not by a pattern. This only
# refuses what cannot be an address at all.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthRefused(Exception):
    """Sign-in or registration refused, with a reason the app can say in words.

    `reason` is one of: invalid_email, weak_password, email_taken, wrong_credentials,
    use_google. "wrong_credentials" is the same whether the email is unknown or the
    password is wrong, so the answer does not reveal who has an account.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    expires_at: datetime
    method: str
    user: AuthUser


class LoginStore(Protocol):
    async def login_by_email(self, email: str) -> dict[str, Any] | None: ...

    async def login_by_google(self, sub: str) -> dict[str, Any] | None: ...

    async def create_user(
        self,
        *,
        user_id: str,
        email: str,
        name: str | None,
        avatar_url: str | None,
        password_hash: str | None,
        google_sub: str | None,
    ) -> bool: ...

    async def link_google(self, *, user_id: str, sub: str) -> None: ...

    async def create_session(
        self, *, token_hash: str, user_id: str, method: str, expires_at: datetime
    ) -> None: ...

    async def session_user(self, token_hash: str, now: datetime) -> dict[str, Any] | None: ...

    async def delete_session(self, token_hash: str) -> None: ...


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalise_email(email: str) -> str:
    return email.strip().lower()


def _user(row: dict[str, Any]) -> AuthUser:
    return AuthUser(
        id=str(row["user_id"]),
        email=str(row["email"]),
        name=row.get("display_name"),
        avatar_url=row.get("avatar_url"),
    )


class LocalAuth:
    def __init__(
        self,
        store: LoginStore,
        *,
        session_days: int = 30,
        min_password_length: int = 8,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._session_days = session_days
        self._min_password = min_password_length
        self._clock = clock

    async def register(
        self, *, email: str, password: str, name: str | None = None
    ) -> IssuedSession:
        address = _normalise_email(email)
        if not _EMAIL.match(address):
            raise AuthRefused("invalid_email")
        if len(password) < self._min_password:
            raise AuthRefused("weak_password")
        # Off the event loop: scrypt is deliberately slow.
        hashed = await asyncio.to_thread(hash_password, password)
        user_id = str(uuid4())
        created = await self._store.create_user(
            user_id=user_id,
            email=address,
            name=(name or "").strip() or None,
            avatar_url=None,
            password_hash=hashed,
            google_sub=None,
        )
        if not created:
            raise AuthRefused("email_taken")
        user = AuthUser(id=user_id, email=address, name=(name or "").strip() or None)
        return await self._open(user, "password")

    async def sign_in(self, *, email: str, password: str) -> IssuedSession:
        row = await self._store.login_by_email(_normalise_email(email))
        if row is None:
            # Hash anyway, so an unknown email takes as long as a wrong password and
            # the timing does not reveal which addresses have accounts.
            await asyncio.to_thread(hash_password, password)
            raise AuthRefused("wrong_credentials")
        if row.get("disabled"):
            raise AuthRefused("wrong_credentials")
        if row.get("password_hash") is None:
            raise AuthRefused("use_google")
        if not await asyncio.to_thread(verify_password, password, row["password_hash"]):
            raise AuthRefused("wrong_credentials")
        return await self._open(_user(row), "password")

    async def sign_in_google(
        self, *, sub: str, email: str, name: str | None, avatar_url: str | None
    ) -> IssuedSession:
        """Sign in someone Google has vouched for, making their account if it is new.

        An existing account with the same email is linked rather than duplicated:
        Google has verified the address, which is what owning the account means.
        """
        row = await self._store.login_by_google(sub)
        if row is not None and row.get("disabled"):
            raise AuthRefused("wrong_credentials")
        if row is None:
            address = _normalise_email(email)
            row = await self._store.login_by_email(address)
            if row is not None and row.get("disabled"):
                raise AuthRefused("wrong_credentials")
            if row is not None:
                await self._store.link_google(user_id=str(row["user_id"]), sub=sub)
            else:
                user_id = str(uuid4())
                created = await self._store.create_user(
                    user_id=user_id,
                    email=address,
                    name=name,
                    avatar_url=avatar_url,
                    password_hash=None,
                    google_sub=sub,
                )
                if not created:  # a race with a registration of the same address
                    raise AuthRefused("email_taken")
                row = {
                    "user_id": user_id,
                    "email": address,
                    "display_name": name,
                    "avatar_url": avatar_url,
                }
        return await self._open(_user(row), "google")

    async def verify(self, token: str) -> AuthUser | None:
        """The person this session belongs to, or None when it is unknown or over."""
        if not token.startswith(TOKEN_PREFIX):
            return None
        row = await self._store.session_user(_hash(token), self._clock())
        return None if row is None else _user(row)

    async def sign_out(self, token: str) -> None:
        if token.startswith(TOKEN_PREFIX):
            await self._store.delete_session(_hash(token))

    async def open_handoff_session(self, user: AuthUser) -> IssuedSession:
        """A short web session for paying, opened from the app (payment_handoff)."""
        return await self._open(user, "handoff", hours=2)

    async def _open(
        self, user: AuthUser, method: str, *, hours: int | None = None
    ) -> IssuedSession:
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        life = timedelta(hours=hours) if hours else timedelta(days=self._session_days)
        expires = self._clock() + life
        await self._store.create_session(
            token_hash=_hash(token), user_id=user.id, method=method, expires_at=expires
        )
        return IssuedSession(token=token, expires_at=expires, method=method, user=user)


class Identities:
    """Every way a request's token is checked: this server's own sessions first, then
    any external provider still configured (a Supabase session from before)."""

    def __init__(self, local: LocalAuth, external: Any | None = None) -> None:
        self._local = local
        self._external = external

    async def verify(self, token: str) -> AuthUser | None:
        if token.startswith(TOKEN_PREFIX):
            return await self._local.verify(token)
        if self._external is not None:
            user: AuthUser | None = await self._external.verify(token)
            return user
        return None
