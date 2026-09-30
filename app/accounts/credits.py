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
    # A new account that has not answered or skipped the survey yet.
    survey_due: bool = False


# The survey asked once after sign-up (0005): each question and its allowed answers.
# The app shows these words in the reader's language; only these keys are stored.
SURVEY_ROLES = frozenset({"journalist", "student", "teacher", "family", "curious"})
SURVEY_PLACES = frozenset(
    {"whatsapp", "instagram", "youtube", "facebook", "x", "telegram", "news_sites"}
)
SURVEY_WANTS = frozenset({"forwards", "links", "pictures", "videos", "voice"})
SURVEY_HEARD = frozenset({"friend", "social", "college", "other"})


@dataclass(frozen=True, slots=True)
class SurveyAnswers:
    """The answers, each checked against its list; a blank one was skipped."""

    role: str | None = None
    places: tuple[str, ...] = ()
    wants: tuple[str, ...] = ()
    heard: str | None = None

    def __post_init__(self) -> None:
        if self.role is not None and self.role not in SURVEY_ROLES:
            raise ValueError(f"unknown role {self.role!r}")
        if self.heard is not None and self.heard not in SURVEY_HEARD:
            raise ValueError(f"unknown answer {self.heard!r}")
        for chosen, allowed in ((self.places, SURVEY_PLACES), (self.wants, SURVEY_WANTS)):
            unknown = set(chosen) - allowed
            if unknown:
                raise ValueError(f"unknown answers {sorted(unknown)}")

    def as_record(self) -> dict[str, object]:
        return {
            "role": self.role,
            # Sorted and without repeats, so the same answers are stored the same way.
            "places": sorted(set(self.places)),
            "wants": sorted(set(self.wants)),
            "heard": self.heard,
        }


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
    async def set_survey(
        self, user_id: str, state: str, answers: dict[str, object] | None
    ) -> None: ...


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
            survey_due=profile.get("survey_state") == "due",
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

    async def answer_survey(self, user: AuthUser, answers: SurveyAnswers | None) -> Account:
        """Record the survey: the answers, or None when the person skipped it."""
        await self.account(user)
        if answers is None:
            await self._store.set_survey(user.id, "skipped", None)
        else:
            await self._store.set_survey(user.id, "answered", answers.as_record())
        return await self.account(user)


def _text(value: object) -> str | None:
    return str(value) if value else None
