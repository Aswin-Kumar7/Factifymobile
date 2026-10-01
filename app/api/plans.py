"""Monthly plans (0008): the price list, subscribing and cancelling, extra usage, and
billing a month's extra usage.

A person subscribes to Plus or Pro; an organisation's owner to Team (per member, from
three) or moves it to API (every check paid at the end of the month). Subscribing
makes a Razorpay subscription the website opens in Checkout; the plan starts when its
first payment is confirmed - by the website's signed result or Razorpay's webhook,
whichever comes first - and follows Razorpay's webhooks after that.

Where the Razorpay account has no subscriptions (its Plans API refuses), a plan is
bought as one payment for a month or a year instead, an ordinary Razorpay order
(0010): it does not renew by itself, and buying the same plan again adds the next
period after the one paid for.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.admin import _staff
from app.api.orgs import _access, _person, _razorpay, _store
from app.orgs import month_close, payments, plans
from app.orgs.errors import ApiError, bad_request

logger = logging.getLogger("factify.api.plans")

router = APIRouter(prefix="/v1", tags=["plans"])

Interval = Literal["month", "year"]


class Subscribe(BaseModel):
    plan: str
    interval: Interval = "month"
    # The phone's payment handoff, when the app sent the person here to choose.
    handoff_id: str | None = None


class TeamSubscribe(BaseModel):
    interval: Interval = "month"
    seats: int = Field(ge=plans.TEAM.min_seats, le=10_000)
    handoff_id: str | None = None


class SubscriptionConfirm(BaseModel):
    payment_id: str
    signature: str
    # One of the two: an auto-renewing subscription, or a plan paid by one order.
    subscription_id: str | None = None
    order_id: str | None = None


class ExtraUsage(BaseModel):
    enabled: bool
    # Rupees a month; empty is no cap.
    cap_inr: int | None = Field(default=None, ge=0, le=10_000_000)


class OrgApiPlan(BaseModel):
    enabled: bool


class CloseMonth(BaseModel):
    # "YYYY-MM"; empty is last month.
    month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")


# Razorpay accounts (by key) found to have no subscriptions: their plans are paid a
# period at a time, without asking again.
_NO_SUBSCRIPTIONS: set[str] = set()


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
    org_id: str | None, actor: str, email: str, handoff_id: str | None = None,
) -> dict[str, Any]:  # fmt: skip
    razorpay = _razorpay(request)
    amount = plan.price_paise(interval, seats)  # type: ignore[arg-type]
    every = "a month" if interval == "month" else "a year"
    notes = {
        "plan": plan.id,
        "interval": interval,
        "user_id": user_id or "",
        "org_id": org_id or "",
    }
    sub: dict[str, Any] | None = None
    if razorpay.key_id not in _NO_SUBSCRIPTIONS:
        try:
            plan_id = await _razorpay_plan(request, plan, interval)
            sub = await razorpay.create_subscription(
                plan_id=plan_id, interval=interval, quantity=seats, notes=notes
            )
        except payments.PaymentsUnavailable as error:
            # A refusal (not an outage) means the account has no subscriptions.
            if any(code in str(error) for code in ("400", "401", "403", "404")):
                _NO_SUBSCRIPTIONS.add(razorpay.key_id)
            logger.warning("razorpay subscription unavailable, paying by order: %s", error)
    if sub is not None:
        await _store(request).create_subscription(
            user_id=user_id, org_id=org_id, plan=plan.id, interval=interval, seats=seats,
            amount_paise=amount, razorpay_subscription_id=str(sub["id"]),
            razorpay_plan_id=plan_id, test_mode=razorpay.test_mode, actor=actor,
            handoff_id=handoff_id,
        )  # fmt: skip
        mode, ids = "subscription", {"subscription_id": sub["id"]}
    else:
        try:
            order_id = await razorpay.create_order(
                amount_paise=amount,
                receipt=f"plan-{plan.id}-{(user_id or org_id or '')[:8]}-"
                f"{int(datetime.now(UTC).timestamp())}",
                notes=notes,
            )
        except payments.PaymentsUnavailable as error:
            logger.warning("razorpay order for a plan failed: %s", error)
            raise ApiError(
                502, "payments_unavailable", "the payment could not be started"
            ) from error
        await _store(request).create_subscription(
            user_id=user_id, org_id=org_id, plan=plan.id, interval=interval, seats=seats,
            amount_paise=amount, razorpay_subscription_id=None, razorpay_plan_id=None,
            test_mode=razorpay.test_mode, actor=actor, handoff_id=handoff_id, kind="prepaid",
            order_id=order_id,
        )  # fmt: skip
        mode, ids = "order", {"order_id": order_id}
        every = "for a month" if interval == "month" else "for a year"
    return {
        "mode": mode,
        **ids,
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
        await _cancel_quietly(request, old)
    return row


async def _confirm(
    request: Request, payload: SubscriptionConfirm, actor: str, owner: tuple[str, str]
) -> dict[str, Any]:
    """Check Checkout's signed result and start the plan it paid for, if it is the
    owner's (`owner` is ("user_id" or "org_id", its id))."""
    razorpay = _razorpay(request)
    store = _store(request)
    if payload.order_id:
        if not razorpay.payment_is_genuine(payload.order_id, payload.payment_id, payload.signature):
            raise bad_request("the payment's signature doesn't match", "bad_signature")
        sub = await store.subscription_by_order(payload.order_id)
        if sub is None or sub.get(owner[0]) != owner[1]:
            raise bad_request("unknown order")
        row = await store.activate_prepaid(payload.order_id, payload.payment_id, actor)
        for old in (row or {}).get("replaced", []):
            await _cancel_quietly(request, old)
    elif payload.subscription_id:
        if not razorpay.subscription_is_genuine(
            payload.payment_id, payload.subscription_id, payload.signature
        ):
            raise bad_request("the payment's signature doesn't match", "bad_signature")
        sub = await store.subscription(payload.subscription_id)
        if sub is None or sub.get(owner[0]) != owner[1]:
            raise bad_request("unknown subscription")
        await _activate(request, payload.subscription_id, actor)
    else:
        raise bad_request("say which payment this is")
    return {"status": "active", "plan": sub["plan"], "seats": sub["seats"]}


async def _cancel_quietly(request: Request, subscription_id: str) -> None:
    try:
        await _razorpay(request).cancel_subscription(subscription_id, at_cycle_end=False)
    except payments.PaymentsUnavailable:
        logger.warning("could not cancel replaced subscription %s", subscription_id)


async def _cancel(request: Request, sub: dict[str, Any] | None) -> dict[str, str]:
    if sub is None:
        raise bad_request("there is no paid plan to cancel", "no_plan")
    if sub.get("kind") == "prepaid":
        raise bad_request(
            "this plan was paid for one period and does not renew; it ends on its own",
            "does_not_renew",
        )
    try:
        await _razorpay(request).cancel_subscription(
            str(sub["razorpay_subscription_id"]), at_cycle_end=True
        )
    except payments.PaymentsUnavailable as error:
        raise ApiError(502, "payments_unavailable", "the plan could not be cancelled") from error
    await _store(request).end_subscription(str(sub["razorpay_subscription_id"]), "cancelling")
    return {"status": "cancelling", "ends_at": str(sub.get("current_end") or "")}


def _renewal(sub: dict[str, Any] | None) -> str | None:
    """'auto' when the plan renews by itself, 'manual' when it is paid a period at a
    time, None with no paid plan."""
    if sub is None:
        return None
    return "manual" if sub.get("kind") == "prepaid" else "auto"


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
        # Whether running out refuses checks; off, checks go on past the plan.
        "enforced": bool(getattr(book, "enforced", False)),
        "extra": {
            "enabled": p.extra_enabled,
            "cap_paise": p.extra_cap_paise,
            "used_paise": p.extra_used_paise,
            "price_paise": p.extra_price_paise,
            "blocked": p.extra_blocked,
        },
        "renewal": _renewal(await store.current_subscription(user_id=user.id)),
        "subscriptions": await store.subscriptions(user_id=user.id),
        "bills": await store.usage_bills(user_id=user.id),
    }


@router.post("/me/plan/subscribe", summary="Start a Plus or Pro subscription")
async def subscribe(payload: Subscribe, request: Request) -> dict[str, Any]:
    user = await _person(request)
    plan = plans.personal(payload.plan)
    if plan is None or plan is plans.FREE:
        raise bad_request("choose Plus or Pro", "unknown_plan")
    if payload.handoff_id:
        await _store(request).handoff(user.id, payload.handoff_id)  # theirs, or 404
    return await _start(
        request, plan=plan, interval=payload.interval, seats=1, user_id=user.id, org_id=None,
        actor=user.id, email=user.email, handoff_id=payload.handoff_id,
    )  # fmt: skip


@router.post("/me/plan/confirm", summary="Confirm a subscription's first payment")
async def confirm(payload: SubscriptionConfirm, request: Request) -> dict[str, Any]:
    user = await _person(request)
    return await _confirm(request, payload, user.id, ("user_id", user.id))


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
    # The same figures `OrgStore.hold` decides by (checks still running count as used).
    m = org["month"]
    return {
        "plan": org.get("plan"),
        "seats": org.get("seats"),
        "interval": org.get("plan_interval"),
        "renews_at": org.get("plan_renews_at"),
        "cancel_at_end": org.get("plan_cancel_at_end"),
        "allowance": m["allowance"],
        "used": m["plan_used"],
        "resets_at": org.get("plan_resets_at"),
        "credits": m["credits"],
        "checks_left": m["checks_left"],
        "pay_per_check": m["pay_per_check"],
        "extra": {
            "enabled": m["extra_enabled"],
            "open": m["extra_open"],
            "cap_paise": m["extra_cap_paise"],
            "used_paise": m["extra_used_paise"],
            "price_paise": m["extra_price_paise"],
            "blocked": m["extra_blocked"],
            "checks_left": m["extra_checks_left"],
        },
        "renewal": _renewal(await store.current_subscription(org_id=org_id)),
        "subscriptions": await store.subscriptions(org_id=org_id),
        "bills": await store.usage_bills(org_id=org_id),
    }


@router.post("/orgs/{org_id}/plan/subscribe", summary="Start a Team subscription")
async def org_subscribe(org_id: str, payload: TeamSubscribe, request: Request) -> dict[str, Any]:
    user, _ = await _access(request, org_id, "owner")
    if payload.handoff_id:
        await _store(request).handoff(user.id, payload.handoff_id)  # theirs, or 404
    return await _start(
        request, plan=plans.TEAM, interval=payload.interval, seats=payload.seats,
        user_id=None, org_id=org_id, actor=user.id, email=user.email,
        handoff_id=payload.handoff_id,
    )  # fmt: skip


@router.post("/orgs/{org_id}/plan/confirm", summary="Confirm a Team subscription's payment")
async def org_confirm(
    org_id: str, payload: SubscriptionConfirm, request: Request
) -> dict[str, Any]:
    user, _ = await _access(request, org_id, "owner")
    return await _confirm(request, payload, user.id, ("org_id", org_id))


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
    paid = payments.paid_order(event)
    if paid is not None:
        # A plan paid by one order; nothing for an order that was a credit pack.
        row = await store.activate_prepaid(paid[0], paid[1], "razorpay")
        for old in (row or {}).get("replaced", []):
            await _cancel_quietly(request, old)
    link = payments.payment_link_event(event)
    if link is not None:
        await store.mark_bill(link[0], link[1])


@router.post("/admin/billing/close-month", summary="Bill last month's extra usage")
async def close_month(payload: CloseMonth, request: Request) -> dict[str, Any]:
    """Send everyone with extra usage in the month a payment link for it - once.
    The server also does this on its own every few hours (app/orgs/month_close.py)."""
    user = await _staff(request)
    month = (
        date.fromisoformat(f"{payload.month}-01")
        if payload.month
        else month_close.last_month(month_close.india_today())
    )
    try:
        billed = await month_close.bill_month(_store(request), _razorpay(request), month)
    except ValueError as error:
        raise bad_request(str(error), "month_not_over") from error
    logger.info("%s closed %s by hand", user.email, month)
    return {"month": f"{month:%Y-%m}", "sent": billed.sent, "failed": billed.failed}
