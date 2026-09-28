"""The credit book: what each person has spent, and whether they may spend more.

One check costs one credit. A new account is granted a starting
balance once. Every decision is made here, on the server, from the ledger; the app
only displays the answer.

Until plans exist, `enforce` is off: checks are recorded and never refused, so the
balance can go below zero and nothing stops. Turning enforcement on is a setting, not
a code change, and needs nothing from the app — it already shows "out of credits"
when the server says so.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import uuid4

from app.accounts.identity import AuthUser
from app.observability.logging import event

logger = logging.getLogger("factify.accounts")


@dataclass(frozen=True, slots=True)
class Account:
    """A person's profile and credit position."""

    id: str
    email: str
    name: str | None
    avatar_url: str | None
    plan: str
    joined_at: datetime | None
    balance: int
    used: int
    checks: int


@dataclass(frozen=True, slots=True)
class CreditDecision:
    allowed: bool
    balance: int
    cost: int


class AccountStore(Protocol):
    async def upsert(self, user: AuthUser) -> bool: ...
    async def record(self, user_id: str, delta: int, reason: str, request_key: str) -> bool: ...
    async def totals(self, user_id: str) -> tuple[int, int, int]: ...
    async def profile(self, user_id: str) -> dict[str, object] | None: ...
    async def set_name(self, user_id: str, name: str) -> None: ...


class CreditBook:
    def __init__(
        self,
        store: AccountStore,
        *,
        signup_credits: int = 100,
        enforce: bool = False,
    ) -> None:
        self._store = store
        self._signup_credits = signup_credits
        self._enforce = enforce

    @property
    def enforced(self) -> bool:
        return self._enforce

    async def account(self, user: AuthUser, *, arriving: bool = False) -> Account:
        """The person's account, created — with its starting grant — on first sight.

        `arriving` is for a sign-in or sign-up: a Factify login makes the person
        itself, at registration, so "created here" cannot be what gives the grant.
        The grant's key means it is only ever given once either way.
        """
        created = await self._store.upsert(user)
        if (created or arriving) and self._signup_credits:
            # Keyed, so a race between two first requests grants once.
            await self._store.record(user.id, self._signup_credits, "signup_grant", "signup")
        profile = await self._store.profile(user.id) or {}
        balance, used, checks = await self._store.totals(user.id)
        joined = profile.get("created_at")
        return Account(
            id=user.id,
            email=str(profile.get("email") or user.email),
            name=_text(profile.get("display_name")) or user.name,
            avatar_url=_text(profile.get("avatar_url")) or user.avatar_url,
            plan=str(profile.get("plan") or "free"),
            joined_at=joined if isinstance(joined, datetime) else None,
            balance=balance,
            used=used,
            checks=checks,
        )

    async def authorize(self, user: AuthUser, cost: int) -> CreditDecision:
        """Whether this person may spend `cost` now. Always yes while not enforced."""
        account = await self.account(user)
        allowed = not self._enforce or account.balance >= cost
        return CreditDecision(allowed=allowed, balance=account.balance, cost=cost)

    async def charge(self, user: AuthUser, cost: int, reason: str) -> None:
        """Record one spend. Never fails the check it pays for: a ledger outage is
        logged and the person keeps their answer."""
        try:
            await self._store.record(user.id, -cost, reason, f"{reason}:{uuid4()}")
        except Exception:
            logger.exception("could not record a credit charge")
            event(
                logger,
                "credit charge not recorded",
                module="accounts",
                outcome="error",
                level=logging.ERROR,
            )

    async def rename(self, user: AuthUser, name: str) -> Account:
        await self.account(user)
        await self._store.set_name(user.id, name)
        return await self.account(user)


def _text(value: object) -> str | None:
    return str(value) if value else None
