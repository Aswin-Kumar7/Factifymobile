"""Monthly plans: what each gives, and what pays for a check (0008).

Pure rules, no I/O. The store gathers an account's month (`Month`) from the
database and asks `source_for` what pays for the next check; the website and the
app show `catalogue()` as the price list.

Prices were set from what a check costs us (2026-10-01): about Rs 5 for a full
open-web check, about Rs 0.6 when our own records settle it and nothing when the
answer is cached - about Rs 2.9 blended at launch, falling as the cache fills.
A plan's price per included check sits a little below that blended cost at full
use; few people use every check, and extra usage at Rs 3 a check covers its own.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

Source = Literal["plan", "credits", "extra"]
Interval = Literal["month", "year"]


@dataclass(frozen=True, slots=True)
class Plan:
    id: str
    name: str
    # Checks a calendar month; for Team, per member.
    monthly_checks: int
    month_inr: int
    year_inr: int
    team: bool = False
    min_seats: int = 1

    def price_paise(self, interval: Interval, seats: int = 1) -> int:
        each = self.month_inr if interval == "month" else self.year_inr
        return each * 100 * max(seats, 1)


FREE = Plan("free", "Free", 30, 0, 0)
PLUS = Plan("plus", "Plus", 120, 299, 2_990)
PRO = Plan("pro", "Pro", 400, 799, 7_990)
TEAM = Plan("team", "Team", 300, 599, 5_988, team=True, min_seats=3)

PERSONAL_PLANS: tuple[Plan, ...] = (FREE, PLUS, PRO)

# What a check past the plan costs, when extra usage is on.
EXTRA_CHECK_PAISE = 300
# An organisation on the API plan pays this for every check, billed monthly.
API_CHECK_PAISE = 400
# A month's extra usage bill unpaid this long stops further extra usage.
UNPAID_GRACE_DAYS = 15
# After a paid period ends without a renewal, the plan still holds this long.
RENEWAL_GRACE_DAYS = 3


def personal(plan_id: str) -> Plan | None:
    return next((p for p in PERSONAL_PLANS if p.id == plan_id), None)


def paid_plan(plan_id: str) -> Plan | None:
    """A plan someone can subscribe to."""
    return next((p for p in (PLUS, PRO, TEAM) if p.id == plan_id), None)


@dataclass(frozen=True, slots=True)
class Month:
    """One account's position this month, as the store read it."""

    allowance: int
    # Checks the plan has paid for this month, including ones still running.
    used: int
    # Credits the account holds besides its plan (bought packs, grants).
    balance: int
    paid: bool = False
    extra_enabled: bool = False
    # None is no cap.
    extra_cap_paise: int | None = None
    extra_used_paise: int = 0
    extra_price_paise: int = EXTRA_CHECK_PAISE
    # An extra usage bill left unpaid past its grace.
    extra_blocked: bool = False

    @property
    def plan_left(self) -> int:
        return max(self.allowance - self.used, 0)

    @property
    def extra_open(self) -> bool:
        return self.paid and self.extra_enabled and not self.extra_blocked

    def extra_checks_left(self) -> int | None:
        """How many more checks extra usage covers; None is no cap."""
        if not self.extra_open:
            return 0
        if self.extra_cap_paise is None:
            return None
        return max(self.extra_cap_paise - self.extra_used_paise, 0) // self.extra_price_paise


def effective_plan(
    plan_id: str, renews_at: datetime | None, now: datetime, *, ending: bool = False
) -> Plan:
    """The person's plan now: a paid plan whose period ended is Free again.

    One that renews by itself keeps a few days' grace, for a renewal Razorpay has not
    confirmed yet. One that is `ending` - paid a period at a time, or cancelled -
    stops on the day its period ends: to go on, the person pays again.
    """
    plan = personal(plan_id) or FREE
    if plan is FREE:
        return FREE
    return FREE if lapsed(renews_at, now, ending=ending) else plan


def lapsed(renews_at: datetime | None, now: datetime, *, ending: bool) -> bool:
    """Whether a paid period that ended `renews_at` is over now."""
    if renews_at is None:
        return False
    return renews_at + timedelta(days=0 if ending else RENEWAL_GRACE_DAYS) < now


def personal_month(row: Mapping[str, Any], now: datetime) -> Month:
    """A person's `Month` from the row `AccountRepository.month` reads."""
    plan = effective_plan(
        str(row.get("plan") or "free"), row.get("plan_renews_at"), now,
        ending=bool(row.get("plan_cancel_at_end")),
    )  # fmt: skip
    paid = plan is not FREE
    cap = row.get("extra_cap_paise")
    return Month(
        allowance=plan.monthly_checks,
        used=int(row.get("used") or 0),
        balance=int(row.get("balance") or 0),
        paid=paid,
        extra_enabled=bool(row.get("extra_usage")) and paid,
        extra_cap_paise=int(cap) if cap is not None else None,
        extra_used_paise=int(row.get("extra_checks") or 0) * EXTRA_CHECK_PAISE,
        extra_price_paise=EXTRA_CHECK_PAISE,
        extra_blocked=bool(row.get("extra_blocked")),
    )


def source_for(month: Month, cost: int) -> Source | None:
    """What pays for a check costing `cost`; None when nothing can.

    A check is paid whole from one place: the plan when it still has `cost` checks
    this month, else the account's credits, else extra usage within its cap.
    """
    if cost <= 0:
        return "plan"
    if month.used + cost <= month.allowance:
        return "plan"
    if month.balance >= cost:
        return "credits"
    if month.extra_open and (
        month.extra_cap_paise is None
        or month.extra_used_paise + cost * month.extra_price_paise <= month.extra_cap_paise
    ):
        return "extra"
    return None


def checks_left(month: Month) -> int:
    """Checks the account can still make this month without extra usage."""
    return month.plan_left + max(month.balance, 0)


def catalogue() -> dict[str, object]:
    """The price list, as the website and the app show it."""

    def row(p: Plan) -> dict[str, object]:
        return {
            "id": p.id,
            "name": p.name,
            "monthly_checks": p.monthly_checks,
            "month_inr": p.month_inr,
            "year_inr": p.year_inr,
            "team": p.team,
            "min_seats": p.min_seats,
        }

    return {
        "personal": [row(p) for p in PERSONAL_PLANS],
        "team": [row(TEAM)],
        "extra_check_inr": EXTRA_CHECK_PAISE / 100,
        "api_check_inr": API_CHECK_PAISE / 100,
        "currency": "INR",
    }
