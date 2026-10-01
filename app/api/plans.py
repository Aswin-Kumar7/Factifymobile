"""Monthly plans (0008): the price list, subscribing and cancelling, extra usage, and
billing a month's extra usage.

A person subscribes to Plus or Pro; an organisation's owner to Team (per member, from
three) or moves it to API (every check paid at the end of the month). Subscribing
makes a Razorpay subscription the website opens in Checkout; the plan starts when its
first payment is confirmed - by the website's signed result or Razorpay's webhook,
whichever comes first - and follows Razorpay's webhooks after that.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.admin import _staff
from app.api.orgs import _access, _person, _razorpay, _store
from app.orgs import payments, plans
from app.orgs.errors import ApiError, bad_request
from app.orgs.store import org_month

logger = logging.getLogger("factify.api.plans")

router = APIRouter(prefix="/v1", tags=["plans"])

Interval = Literal["month", "year"]


class Subscribe(BaseModel):
    plan: str
    interval: Interval = "month"


class TeamSubscribe(BaseModel):
    interval: Interval = "month"
    seats: int = Field(ge=plans.TEAM.min_seats, le=10_000)


class SubscriptionConfirm(BaseModel):
    payment_id: str
    subscription_id: str
    signature: str


class ExtraUsage(BaseModel):
    enabled: bool
    # Rupees a month; empty is no cap.
    cap_inr: int | None = Field(default=None, ge=0, le=10_000_000)


class OrgApiPlan(BaseModel):
    enabled: bool


class CloseMonth(BaseModel):
    # "YYYY-MM"; empty is last month.
    month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else (str(value) if value else None)


@router.get("/plans", summary="The price list")
async def price_list() -> dict[str, object]:
    return plans.catalogue()


# ---- starting a subscription --------------------------------------------------------


async def _razorpay_plan(request: Request, plan: plans.Plan, interval: str) -> str:
    """Razorpay's plan for one of ours, made the first time it is needed."""
    razorpay = _razorpay(request)
    key = f"{plan.id}:{interval}:{'test' if razorpay.test_mode else 'live'}"
    store = _store(request)
    known = await store.razorpay_plan_id(key)
    if known:
        return known
    plan_id = await razorpay.create_plan(
        interval=interval,
        amount_paise=plan.price_paise(interval),  # type: ignore[arg-type]
        name=f"Factify {plan.name}{' (per member)' if plan.team else ''}"
        f" - {'monthly' if interval == 'month' else 'yearly'}",
    )
    await store.save_razorpay_plan(key, plan_id)
    return await store.razorpay_plan_id(key) or plan_id


async def _start(
    request: Request, *, plan: plans.Plan, interval: str, seats: int, user_id: str | None,
    org_id: str | None, actor: str, email: str,
) -> dict[str, Any]:  # fmt: skip
    razorpay = _razorpay(request)
    try:
        plan_id = await _razorpay_plan(request, plan, interval)
        sub = await razorpay.create_subscription(
            plan_id=plan_id, interval=interval, quantity=seats,
            notes={"plan": plan.id, "user_id": user_id or "", "org_id": org_id or ""},
        )  # fmt: skip
    except payments.PaymentsUnavailable as error:
        logger.warning("razorpay subscription failed: %s", error)
        raise ApiError(502, "payments_unavailable", "the payment could not be started") from error
    amount = plan.price_paise(interval, seats)  # type: ignore[arg-type]
    await _store(request).create_subscription(
        user_id=user_id, org_id=org_id, plan=plan.id, interval=interval, seats=seats,
        amount_paise=amount, razorpay_subscription_id=str(sub["id"]),
        razorpay_plan_id=plan_id, test_mode=razorpay.test_mode, actor=actor,
    )  # fmt: skip
    every = "a month" if interval == "month" else "a year"
    return {
        "subscription_id": sub["id"],
        "key_id": razorpay.key_id,
        "amount": amount,
        "currency": "INR",
        "name": "Factify",
        "description": f"{plan.name}{f' for {seats} members' if plan.team else ''}, "
        f"₹{amount // 100:,} {every}",
        "prefill": {"email": email},
        "test_mode": razorpay.test_mode,
    }


async def _activate(request: Request, subscription_id: str, actor: str) -> dict[str, Any] | None:
    """Put a paid subscription's owner on its plan, and cancel what it replaced."""
    razorpay = _razorpay(request)
    start: datetime | None = None
    end: datetime | None = None
    try:
        entity = await razorpay.fetch_subscription(subscription_id)
        start = payments._moment(entity.get("current_start"))
        end = payments._moment(entity.get("current_end"))
    except payments.PaymentsUnavailable:
        logger.warning("could not read subscription %s; using today's period", subscription_id)
    store = _store(request)
    sub = await store.subscription(subscription_id)
    if sub is None:
        return None
    if end is None:
        start = datetime.now(UTC)
        end = start + (timedelta(days=31) if sub["interval"] == "month" else timedelta(days=366))
    row = await store.activate_subscription(
        subscription_id, current_start=start, current_end=end, actor=actor
    )
    for old in (row or {}).get("replaced", []):
        try:
            await razorpay.cancel_subscription(old, at_cycle_end=False)
        except payments.PaymentsUnavailable:
            logger.warning("could not cancel replaced subscription %s", old)
    return row


async def _cancel(request: Request, sub: dict[str, Any] | None) -> dict[str, str]:
    if sub is None:
        raise bad_request("there is no paid plan to cancel", "no_plan")
    try:
        await _razorpay(request).cancel_subscription(
            str(sub["razorpay_subscription_id"]), at_cycle_end=True
        )
    except payments.PaymentsUnavailable as error:
        raise ApiError(502, "payments_unavailable", "the plan could not be cancelled") from error
    await _store(request).end_subscription(str(sub["razorpay_subscription_id"]), "cancelling")
    return {"status": "cancelling", "ends_at": str(sub.get("current_end") or "")}


# ---- a person's plan ----------------------------------------------------------------


@router.get("/me/plan", summary="Your plan, this month's use, and your bills")
async def my_plan(request: Request) -> dict[str, Any]:
    user = await _person(request)
    book = request.app.state.credits
    p = await book.position(user.id)
    store = _store(request)
    return {
        "plan": p.plan,
        "name": p.name,
        "interval": p.interval,
        "renews_at": _iso(p.renews_at),
        "cancel_at_end": p.cancel_at_end,
        "allowance": p.allowance,
        "used": p.used,
        "resets_at": _iso(p.resets_at),
        "credits": p.credits,
        "checks_left": max(p.allowance - p.used, 0) + max(p.credits, 0),
        "extra": {
            "enabled": p.extra_enabled,
            "cap_paise": p.extra_cap_paise,
            "used_paise": p.extra_used_paise,
            "price_paise": p.extra_price_paise,
            "blocked": p.extra_blocked,
        },
        "subscriptions": await store.subscriptions(user_id=user.id),
        "bills": await store.usage_bills(user_id=user.id),
    }


@router.post("/me/plan/subscribe", summary="Start a Plus or Pro subscription")
async def subscribe(payload: Subscribe, request: Request) -> dict[str, Any]:
    user = await _person(request)
    plan = plans.personal(payload.plan)
    if plan is None or plan is plans.FREE:
        raise bad_request("choose Plus or Pro", "unknown_plan")
    return await _start(
        request, plan=plan, interval=payload.interval, seats=1, user_id=user.id, org_id=None,
        actor=user.id, email=user.email,
    )  # fmt: skip


@router.post("/me/plan/confirm", summary="Confirm a subscription's first payment")
async def confirm(payload: SubscriptionConfirm, request: Request) -> dict[str, Any]:
    user = await _person(request)
    if not _razorpay(request).subscription_is_genuine(
        payload.payment_id, payload.subscription_id, payload.signature
    ):
        raise bad_request("the payment's signature doesn't match", "bad_signature")
    sub = await _store(request).subscription(payload.subscription_id)
    if sub is None or sub.get("user_id") != user.id:
        raise bad_request("unknown subscription")
    await _activate(request, payload.subscription_id, user.id)
    return {"status": "active", "plan": sub["plan"]}


@router.post("/me/plan/cancel", summary="Cancel at the end of the period")
async def cancel(request: Request) -> dict[str, str]:
    user = await _person(request)
    return await _cancel(request, await _store(request).current_subscription(user_id=user.id))


@router.put("/me/plan/extra", summary="Turn extra usage on or off, with a monthly cap")
async def my_extra(payload: ExtraUsage, request: Request) -> dict[str, Any]:
    user = await _person(request)
    p = await request.app.state.credits.position(user.id)
    if payload.enabled and p.plan == plans.FREE.id:
        raise bad_request("extra usage comes with a paid plan", "paid_plan_needed")
    cap = payload.cap_inr * 100 if payload.cap_inr is not None else None
    await _store(request).set_extra_usage(
        user_id=user.id, enabled=payload.enabled, cap_paise=cap, actor=user.id
    )
    return {"enabled": payload.enabled, "cap_paise": cap}


# ---- an organisation's plan ---------------------------------------------------------


@router.get("/orgs/{org_id}/plan", summary="The organisation's plan and this month's use")
async def org_plan(org_id: str, request: Request) -> dict[str, Any]:
    await _access(request, org_id)
    store = _store(request)
    org = await store.org(org_id)
    renews = org.get("plan_renews_at")
    month = org_month(
        {
            **org,
            "plan_renews_at": datetime.fromisoformat(renews) if renews else None,
            "credits": int(org.get("balance") or 0) - int(org.get("held") or 0),
        },
        datetime.now(UTC),
    )
    return {
        "plan": org.get("plan"),
        "seats": org.get("seats"),
        "interval": org.get("plan_interval"),
        "renews_at": renews,
        "cancel_at_end": org.get("plan_cancel_at_end"),
        "allowance": month.allowance,
        "used": month.used,
        "resets_at": org.get("plan_resets_at"),
        "credits": month.balance,
        "checks_left": plans.checks_left(month),
        "extra": {
            "enabled": month.extra_enabled,
            "cap_paise": month.extra_cap_paise,
            "used_paise": month.extra_used_paise,
            "price_paise": month.extra_price_paise,
            "blocked": month.extra_blocked,
        },
        "subscriptions": await store.subscriptions(org_id=org_id),
        "bills": await store.usage_bills(org_id=org_id),
    }


@router.post("/orgs/{org_id}/plan/subscribe", summary="Start a Team subscription")
async def org_subscribe(org_id: str, payload: TeamSubscribe, request: Request) -> dict[str, Any]:
    user, _ = await _access(request, org_id, "owner")
    return await _start(
        request, plan=plans.TEAM, interval=payload.interval, seats=payload.seats,
        user_id=None, org_id=org_id, actor=user.id, email=user.email,
    )  # fmt: skip


@router.post("/orgs/{org_id}/plan/confirm", summary="Confirm a Team subscription's payment")
async def org_confirm(
    org_id: str, payload: SubscriptionConfirm, request: Request
) -> dict[str, Any]:
    user, _ = await _access(request, org_id, "owner")
    if not _razorpay(request).subscription_is_genuine(
        payload.payment_id, payload.subscription_id, payload.signature
    ):
        raise bad_request("the payment's signature doesn't match", "bad_signature")
    sub = await _store(request).subscription(payload.subscription_id)
    if sub is None or sub.get("org_id") != org_id:
        raise bad_request("unknown subscription")
    await _activate(request, payload.subscription_id, user.id)
    return {"status": "active", "plan": "team", "seats": sub["seats"]}


@router.post("/orgs/{org_id}/plan/cancel", summary="Cancel Team at the end of the period")
async def org_cancel(org_id: str, request: Request) -> dict[str, str]:
    await _access(request, org_id, "owner")
    return await _cancel(request, await _store(request).current_subscription(org_id=org_id))


@router.put("/orgs/{org_id}/plan/extra", summary="Extra usage for the organisation")
async def org_extra(org_id: str, payload: ExtraUsage, request: Request) -> dict[str, Any]:
    user, _ = await _access(request, org_id, "owner")
    org = await _store(request).org(org_id)
    if payload.enabled and org.get("plan") == "credits":
        raise bad_request("extra usage comes with the Team or API plan", "paid_plan_needed")
    cap = payload.cap_inr * 100 if payload.cap_inr is not None else None
    await _store(request).set_extra_usage(
        org_id=org_id, enabled=payload.enabled or org.get("plan") == "api", cap_paise=cap,
        actor=user.id,
    )  # fmt: skip
    return {"enabled": payload.enabled, "cap_paise": cap}


@router.put("/orgs/{org_id}/plan/api", summary="Pay per check (API) or go back to packs")
async def org_api_plan(org_id: str, payload: OrgApiPlan, request: Request) -> dict[str, str]:
    user, _ = await _access(request, org_id, "owner")
    org = await _store(request).org(org_id)
    if org.get("plan") == "team":
        raise bad_request("cancel the Team plan first", "on_team_plan")
    plan = "api" if payload.enabled else "credits"
    await _store(request).set_org_plan(org_id, plan, user.id)
    return {"plan": plan}


# ---- webhooks and the month's bills --------------------------------------------------


async def handle_webhook(request: Request, event: dict[str, Any]) -> None:
    """The plan half of Razorpay's webhook (app/api/orgs.py calls it)."""
    store = _store(request)
    sub = payments.subscription_event(event)
    if sub is not None:
        sub_id, status, _start_at, _end_at = sub
        if status == "active":
            await _activate(request, sub_id, "razorpay")
        else:
            await store.end_subscription(sub_id, status)
    link = payments.payment_link_event(event)
    if link is not None:
        await store.mark_bill(link[0], link[1])


def _last_month(today: date) -> date:
    first = today.replace(day=1)
    return (first - timedelta(days=1)).replace(day=1)


@router.post("/admin/billing/close-month", summary="Bill last month's extra usage")
async def close_month(payload: CloseMonth, request: Request) -> dict[str, Any]:
    """Send everyone with extra usage in the month a payment link for it - once."""
    user = await _staff(request)
    india_today = (datetime.now(UTC) + timedelta(hours=5, minutes=30)).date()
    month = date.fromisoformat(f"{payload.month}-01") if payload.month else _last_month(india_today)
    if month >= india_today.replace(day=1):
        raise bad_request("a month can be billed only after it ends", "month_not_over")
    store = _store(request)
    razorpay = _razorpay(request)
    sent, failed = 0, 0
    for row in await store.extra_usage_to_bill(month):
        checks = int(row["checks"])
        amount = checks * int(row["price_paise"])
        if checks <= 0 or amount <= 0:
            continue
        owner = row.get("user_id") or row.get("org_id")
        try:
            link = await razorpay.create_payment_link(
                amount_paise=amount,
                description=f"Factify extra usage, {month:%B %Y}: {checks:,} checks",
                email=row.get("email"),
                reference=f"extra-{month:%Y%m}-{str(owner)[:8]}",
                notes={"month": f"{month:%Y-%m}", "owner": str(owner)},
            )
        except payments.PaymentsUnavailable:
            logger.exception("could not bill extra usage for %s", owner)
            failed += 1
            continue
        await store.create_usage_bill(
            user_id=row.get("user_id"), org_id=row.get("org_id"), month=month, checks=checks,
            amount_paise=amount, payment_link_id=str(link["id"]),
            short_url=link.get("short_url"), test_mode=razorpay.test_mode,
        )  # fmt: skip
        sent += 1
    logger.info("closed %s: %d bills sent, %d failed (by %s)", month, sent, failed, user.email)
    return {"month": f"{month:%Y-%m}", "sent": sent, "failed": failed}
