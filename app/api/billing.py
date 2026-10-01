"""A person's own credit purchases, paying from the phone in the browser, and
organisation plans by request.

Paying from the phone (like Spotify): the app asks for a handoff, opens the browser
at `{web}/pay?h=<token>`, and polls the handoff until the payment it led to is paid,
failed or cancelled - or it expires: unopened after 10 minutes, or opened and not
finished within 30. The token is random, single-use, lives 10 minutes and is new
for every purchase; only its hash is stored. Exchanged once, it gives the browser
a two-hour session for the same person - nothing more.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.accounts import AuthUser
from app.api.orgs import (
    _access,
    _person,
    _razorpay,
    _store,
    bill_invoice_html,
    invoice_html,
    plan_invoice_html,
)
from app.orgs import payments
from app.orgs.errors import ApiError, bad_request

logger = logging.getLogger("factify.api.billing")

router = APIRouter(prefix="/v1", tags=["billing"])


class PersonalOrder(BaseModel):
    pack: str
    handoff_id: str | None = None


class Confirm(BaseModel):
    order_id: str
    payment_id: str
    signature: str


class HandoffCreate(BaseModel):
    # The organisation to buy for; empty is the person's own credits.
    org_id: str | None = None


class HandoffExchange(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class HandoffFinish(BaseModel):
    status: str


class OrgRequestCreate(BaseModel):
    org_name: str = Field(min_length=1, max_length=80)
    billing_email: str | None = Field(default=None, max_length=254)
    use_case: str | None = Field(default=None, max_length=1000)
    expected_checks: int | None = Field(default=None, ge=0, le=10_000_000)
    website: str | None = Field(default=None, max_length=200)


def _web(request: Request) -> str:
    auth = request.app.state.settings.auth
    return (auth.web_url or auth.public_url or "").rstrip("/")


# ---- a person's own credits ------------------------------------------------------


@router.post("/me/billing/orders", summary="Start buying credits for yourself")
async def personal_order(payload: PersonalOrder, request: Request) -> dict[str, Any]:
    user = await _person(request)
    chosen = payments.personal_pack(payload.pack)
    if chosen is None:
        raise bad_request("unknown pack")
    razorpay = _razorpay(request)
    amount = chosen.price_inr * 100
    try:
        order_id = await razorpay.create_order(
            amount_paise=amount,
            receipt=f"user-{user.id[:8]}-{int(datetime.now(UTC).timestamp())}",
            notes={"user_id": user.id, "pack": chosen.id},
        )
    except payments.PaymentsUnavailable as error:
        logger.warning("razorpay order failed: %s", error)
        raise ApiError(502, "payments_unavailable", "the payment could not be started") from error
    await _store(request).create_payment(
        None, user.id, order_id=order_id, pack=chosen.id, credits=chosen.credits,
        amount_paise=amount, test_mode=razorpay.test_mode, for_user=user.id,
        handoff_id=payload.handoff_id,
    )  # fmt: skip
    return {
        "order_id": order_id,
        "key_id": razorpay.key_id,
        "amount": amount,
        "currency": "INR",
        "name": "Factify",
        "description": f"{chosen.name}: {chosen.credits:,} credits",
        "prefill": {"email": user.email},
        "test_mode": razorpay.test_mode,
    }


@router.post("/me/billing/confirm", summary="Confirm a payment Razorpay completed")
async def personal_confirm(payload: Confirm, request: Request) -> dict[str, Any]:
    user = await _person(request)
    if not _razorpay(request).payment_is_genuine(
        payload.order_id, payload.payment_id, payload.signature
    ):
        raise bad_request("the payment's signature doesn't match", "bad_signature")
    row = await _store(request).mark_paid(payload.order_id, payload.payment_id, user.id)
    if row is None or row.get("user_id") != user.id:
        raise bad_request("unknown order")
    return {"status": "paid", "credits": row["credits"]}


@router.get("/me/billing/payments", summary="Your payments")
async def personal_payments(request: Request) -> list[dict[str, Any]]:
    user = await _person(request)
    return await _store(request).my_payments(user.id)


@router.get(
    "/me/billing/payments/{payment_id}/invoice",
    response_class=HTMLResponse,
    summary="A printable invoice",
)
async def personal_invoice(payment_id: str, request: Request) -> HTMLResponse:
    user = await _person(request)
    p = await _store(request).my_payment(user.id, payment_id)
    if p["status"] != "paid":
        raise bad_request("only a paid order has an invoice")
    return invoice_html(p, request)


@router.get(
    "/me/billing/plans/{subscription_id}/invoice",
    response_class=HTMLResponse,
    summary="A printable invoice for a plan payment",
)
async def personal_plan_invoice(subscription_id: str, request: Request) -> HTMLResponse:
    user = await _person(request)
    s = await _store(request).plan_payment(subscription_id, user_id=user.id)
    return plan_invoice_html(s, request)


@router.get(
    "/me/billing/bills/{bill_id}/invoice",
    response_class=HTMLResponse,
    summary="A printable invoice for a paid extra usage bill",
)
async def personal_bill_invoice(bill_id: str, request: Request) -> HTMLResponse:
    user = await _person(request)
    b = await _store(request).usage_bill(bill_id, user_id=user.id)
    return bill_invoice_html(b, request)


# ---- paying from the phone ---------------------------------------------------------


@router.post("/billing/handoff", summary="A one-time link to pay in the browser")
async def create_handoff(payload: HandoffCreate, request: Request) -> dict[str, Any]:
    user = await _person(request)
    if payload.org_id:
        await _access(request, payload.org_id, "owner")
    row, token = await _store(request).create_handoff(user.id, payload.org_id)
    return {**row, "url": f"{_web(request)}/pay?h={token}"}


@router.get("/billing/handoff/{handoff_id}", summary="Where the browser payment has got to")
async def handoff_status(handoff_id: str, request: Request) -> dict[str, Any]:
    user = await _person(request)
    row = await _store(request).handoff(user.id, handoff_id)
    # Never opened in time, or opened and left (closed, or something else chosen):
    # the app stops waiting.
    if row.get("expired"):
        row["status"] = "expired"
    return row


@router.post("/billing/handoff/{handoff_id}/finish", summary="Cancel, or report a failure")
async def handoff_finish(
    handoff_id: str, payload: HandoffFinish, request: Request
) -> dict[str, str]:
    user = await _person(request)
    await _store(request).finish_handoff(user.id, handoff_id, payload.status)
    return {"status": payload.status}


@router.post("/billing/handoff/exchange", include_in_schema=False)
async def handoff_exchange(payload: HandoffExchange, request: Request) -> dict[str, Any]:
    """The browser trades the app's one-time token for a short session (website only)."""
    store = _store(request)
    local = getattr(request.app.state, "local_auth", None)
    if local is None:
        raise ApiError(503, "unavailable", "sign-in is not available on this server")
    row = await store.use_handoff(payload.token)
    user = AuthUser(id=row["user_id"], email=row["email"], name=row.get("display_name"))
    session = await local.open_handoff_session(user)
    return {
        "access_token": session.token,
        "expires_at": session.expires_at.isoformat(),
        "email": user.email,
        "handoff_id": row["id"],
        "org_id": row.get("org_id"),
    }


# ---- organisation plans by request ------------------------------------------------


@router.post("/org-requests", status_code=201, summary="Ask for an organisation plan")
async def create_org_request(payload: OrgRequestCreate, request: Request) -> dict[str, Any]:
    user = await _person(request)
    fields = payload.model_dump()
    fields["billing_email"] = fields.get("billing_email") or user.email
    return await _store(request).create_org_request(user.id, fields)


@router.get("/org-requests", summary="Your requests for an organisation plan")
async def my_org_requests(request: Request) -> list[dict[str, Any]]:
    user = await _person(request)
    return await _store(request).my_org_requests(user.id)


@router.delete("/org-requests/{request_id}", status_code=204, summary="Withdraw a request")
async def withdraw_org_request(request_id: str, request: Request) -> None:
    user = await _person(request)
    await _store(request).withdraw_org_request(user.id, request_id)
