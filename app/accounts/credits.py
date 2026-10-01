"""The credit book: what each person has spent, and whether they may spend more.

A person is on a monthly plan (Free, Plus or Pro, 0008): its checks this month pay
first, then any credits they hold (bought packs, a sign-up grant), then - on a paid
plan, if they turned it on - extra usage up to their cap (`app.orgs.plans`). Every
decision is made here, on the server, from the ledger; the app only displays it.

With `enforce` off, checks are recorded and never refused: past everything the plan
and credits cover, the credit balance goes below zero. Turning enforcement on is a
setting, not a code change; the app already shows "out of credits" when told so.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from app.accounts.identity import AuthUser
from app.observability.logging import event
from app.orgs import plans

logger = logging.getLogger("factify.accounts")


@dataclass(frozen=True, slots=True)
class PlanPosition:
    """Where a person stands on their plan this month."""

    plan: str
    name: str
    interval: str | None
    renews_at: datetime | None
    cancel_at_end: bool
    allowance: int
    used: int
    resets_at: datetime | None
    # Credits held besides the plan (bought packs, grants).
    credits: int
    extra_enabled: bool
    extra_cap_paise: int | None
    extra_used_paise: int
    extra_price_paise: int
    extra_blocked: bool


@dataclass(frozen=True, slots=True)
class Account:
    """A person's profile and credit position."""

    id: str
    email: str
    name: str | None
    avatar_url: str | None
    plan: str
    joined_at: datetime | None
    # Checks they can still make this month: the plan's left plus their credits.
    balance: int
    used: int
    checks: int
    # A new account that has not answered or skipped the survey yet.
    survey_due: bool = False
    position: PlanPosition | None = None


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
    async def month(self, user_id: str) -> dict[str, object] | None: ...
    async def charge_check(self, user_id: str, cost: int, reason: str, request_key: str) -> str: ...
    async def profile(self, user_id: str) -> dict[str, object] | None: ...
    async def set_name(self, user_id: str, name: str) -> None: ...
    async def set_survey(
        self, user_id: str, state: str, answers: dict[str, object] | None
    ) -> None: ...
    async def delete(self, user_id: str) -> list[str]: ...


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
        _, used, checks = await self._store.totals(user.id)
        position = await self.position(user.id)
        joined = profile.get("created_at")
        return Account(
            id=user.id,
            email=str(profile.get("email") or user.email),
            name=_text(profile.get("display_name")) or user.name,
            avatar_url=_text(profile.get("avatar_url")) or user.avatar_url,
            plan=position.plan,
            joined_at=joined if isinstance(joined, datetime) else None,
            balance=max(position.allowance - position.used, 0) + position.credits,
            used=used,
            checks=checks,
            survey_due=profile.get("survey_state") == "due",
            position=position,
        )

    async def position(self, user_id: str) -> PlanPosition:
        """The person's plan and this month's use of it."""
        row = await self._store.month(user_id) or {}
        now = datetime.now(UTC)
        month = plans.personal_month(row, now)
        renews = _when(row.get("plan_renews_at"))
        plan = plans.effective_plan(
            str(row.get("plan") or "free"), renews, now, ending=bool(row.get("plan_cancel_at_end"))
        )
        paid = plan is not plans.FREE
        return PlanPosition(
            plan=plan.id,
            name=plan.name,
            interval=_text(row.get("plan_interval")) if paid else None,
            renews_at=renews if paid else None,
            cancel_at_end=bool(row.get("plan_cancel_at_end")) and paid,
            allowance=month.allowance,
            used=month.used,
            resets_at=_when(row.get("resets_at")),
            credits=month.balance,
            extra_enabled=month.extra_enabled,
            extra_cap_paise=month.extra_cap_paise,
            extra_used_paise=month.extra_used_paise,
            extra_price_paise=month.extra_price_paise,
            extra_blocked=month.extra_blocked,
        )

    async def authorize(self, user: AuthUser, cost: int) -> CreditDecision:
        """Whether this person may spend `cost` now. Always yes while not enforced."""
        await self.account(user)
        month = plans.personal_month(await self._store.month(user.id) or {}, datetime.now(UTC))
        allowed = not self._enforce or plans.source_for(month, cost) is not None
        return CreditDecision(allowed=allowed, balance=plans.checks_left(month), cost=cost)

    async def charge(self, user: AuthUser, cost: int, reason: str) -> None:
        """Record one spend, paid from the plan, credits or extra usage. Never fails
        the check it pays for: a ledger outage is logged and the person keeps their
        answer."""
        try:
            await self._store.charge_check(user.id, cost, reason, f"{reason}:{uuid4()}")
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

    async def delete_account(self, user: AuthUser) -> list[str]:
        """Delete the account; the organisations that stop it, when it is their last
        owner (and then nothing is deleted)."""
        return await self._store.delete(user.id)

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


def _when(value: object) -> datetime | None:
    return value if isinstance(value, datetime) else None
