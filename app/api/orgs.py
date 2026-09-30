# ruff: noqa: E501
"""Organisations: the dashboard's API (docs/website-dashboard-plan.md).

Owners manage the organisation, its members, keys, billing and domains; developers
manage their own API keys; members see their own usage. Every rule is checked here -
the website only hides what a role can't use. These endpoints need a signed-in
person: an API key can run checks, never manage an organisation.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from app.accounts import AuthUser
from app.api.accounts import signed_in
from app.orgs import payments
from app.orgs.errors import ApiError, bad_request, forbidden
from app.orgs.store import KEY_ROLES, OrgStore

logger = logging.getLogger("factify.api.orgs")

router = APIRouter(prefix="/v1", tags=["organisations"])

_DOMAIN = re.compile(r"^(?=.{3,253}$)([a-z0-9-]{1,63}\.)+[a-z]{2,63}$")
_PUBLIC_MAIL = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "proton.me"}


# ---- request bodies -------------------------------------------------------------


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    billing_email: str | None = Field(default=None, max_length=254)


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    billing_email: str | None = Field(default=None, max_length=254)
    gst_number: str | None = Field(default=None, max_length=20)
    monthly_spend_limit: int | None = Field(default=None, ge=0)
    clear_spend_limit: bool = False
    shared_history: bool | None = None


class MemberUpdate(BaseModel):
    role: str | None = None
    monthly_limit: int | None = Field(default=None, ge=0)
    clear_limit: bool = False
    status: str | None = None


class InviteCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: str = "member"
    monthly_limit: int | None = Field(default=None, ge=0)


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    note: str | None = Field(default=None, max_length=200)
    monthly_limit: int | None = Field(default=None, ge=0)
    expires_days: int | None = Field(default=None, ge=1, le=730)
    ip_allowlist: list[str] = Field(default_factory=list, max_length=20)


class KeyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    note: str | None = Field(default=None, max_length=200)
    monthly_limit: int | None = Field(default=None, ge=0)
    clear_limit: bool = False
    ip_allowlist: list[str] | None = Field(default=None, max_length=20)


class OrderCreate(BaseModel):
    pack: str


class PaymentConfirm(BaseModel):
    order_id: str
    payment_id: str
    signature: str


class DomainCreate(BaseModel):
    domain: str = Field(min_length=3, max_length=253)


class DomainUpdate(BaseModel):
    auto_join: bool | None = None
    default_role: str | None = None


# ---- access ----------------------------------------------------------------------


def _store(request: Request) -> OrgStore:
    store = getattr(request.app.state, "orgs", None)
    if store is None:
        raise ApiError(503, "unavailable", "organisations are not available on this server")
    return store  # type: ignore[no-any-return]


async def _person(request: Request) -> AuthUser:
    user = await signed_in(request)
    if user is None:
        raise ApiError(401, "sign_in_required", "sign in first")
    if getattr(request.state, "via_key", False):
        raise forbidden("API keys can run checks, not manage an organisation; sign in")
    return user


async def _access(request: Request, org_id: str, *roles: str) -> tuple[AuthUser, dict[str, Any]]:
    """The signed-in person and their membership, if their role is one of `roles`
    (any role when none are given). Factify staff may look at any organisation."""
    user = await _person(request)
    store = _store(request)
    member = await store.member(org_id, user.id)
    if member is None:
        if await store.is_staff(user.id, user.email, request.app.state.settings.auth.staff_emails):
            return user, {"role": "owner", "status": "active", "staff": True}
        raise forbidden("you are not a member of this organisation")
    if member["status"] != "active":
        raise forbidden("your membership of this organisation is suspended")
    if roles and member["role"] not in roles:
        raise forbidden()
    return user, member


# ---- organisations ---------------------------------------------------------------


@router.get("/orgs", summary="Your organisations")
async def my_orgs(request: Request) -> list[dict[str, Any]]:
    user = await _person(request)
    return await _store(request).my_orgs(user.id)


@router.post("/orgs", status_code=status.HTTP_201_CREATED, summary="Create an organisation")
async def create_org(payload: OrgCreate, request: Request) -> dict[str, Any]:
    user = await _person(request)
    return await _store(request).create_org(
        user_id=user.id, name=payload.name, billing_email=payload.billing_email or user.email
    )


@router.get("/orgs/{org_id}", summary="An organisation, its pool and this month's spend")
async def get_org(org_id: str, request: Request) -> dict[str, Any]:
    _, member = await _access(request, org_id)
    org = await _store(request).org(org_id)
    org["my_role"] = member["role"]
    # Factify staff looking at someone else's organisation, not a member of it.
    org["viewing_as_staff"] = bool(member.get("staff"))
    org["my_monthly_limit"] = member.get("monthly_limit")
    org["alerts"] = _alerts(org)
    return org


def _alerts(org: dict[str, Any]) -> list[dict[str, str]]:
    """What an owner should know now: a low pool, a monthly cap nearly reached."""
    alerts = []
    balance = int(org.get("balance") or 0) - int(org.get("held") or 0)
    spend = int(org.get("month_spend") or 0)
    if balance <= 0:
        alerts.append({"level": "error", "text": "The credit pool is empty; checks are refused."})
    elif spend and balance < spend * 0.2:
        alerts.append(
            {"level": "warning", "text": "Credits are running low for this month's pace."}
        )
    cap = org.get("monthly_spend_limit")
    if cap:
        used = spend / cap
        for mark in (1.0, 0.8, 0.5):
            if used >= mark:
                alerts.append(
                    {
                        "level": "error" if mark == 1.0 else "warning",
                        "text": f"{int(mark * 100)}% of the monthly spending limit is used.",
                    }
                )
                break
    return alerts


@router.patch("/orgs/{org_id}", summary="Change the organisation's settings")
async def update_org(org_id: str, payload: OrgUpdate, request: Request) -> dict[str, Any]:
    user, _ = await _access(request, org_id, "owner")
    fields = payload.model_dump(exclude_none=True, exclude={"clear_spend_limit"})
    if payload.clear_spend_limit:
        fields["monthly_spend_limit"] = None
    return await _store(request).update_org(org_id, user.id, fields)


@router.delete("/orgs/{org_id}", status_code=204, summary="Close the organisation")
async def close_org(org_id: str, request: Request) -> Response:
    user, _ = await _access(request, org_id, "owner")
    await _store(request).close_org(org_id, user.id)
    return Response(status_code=204)


# ---- members and invites -----------------------------------------------------------


@router.get("/orgs/{org_id}/members", summary="Members, their roles, limits and spend")
async def members(org_id: str, request: Request) -> list[dict[str, Any]]:
    user, member = await _access(request, org_id)
    rows = await _store(request).members(org_id)
    if member["role"] != "owner":
        # Members see who is in the organisation, not what each spends.
        rows = [
            {
                k: v
                for k, v in r.items()
                if k
                not in ("month_spend", "monthly_limit", "keys", "lifetime_spend", "last_active_at")
            }
            if r["user_id"] != user.id
            else r
            for r in rows
        ]
    return rows


@router.patch("/orgs/{org_id}/members/{user_id}", summary="Change a member's role, limit or status")
async def update_member(
    org_id: str, user_id: str, payload: MemberUpdate, request: Request
) -> dict[str, str]:
    user, _ = await _access(request, org_id, "owner")
    fields = payload.model_dump(exclude_none=True, exclude={"clear_limit"})
    if payload.clear_limit:
        fields["monthly_limit"] = None
    await _store(request).update_member(org_id, user_id, user.id, fields)
    return {"status": "ok"}


@router.delete("/orgs/{org_id}/members/{user_id}", status_code=204, summary="Remove a member")
async def remove_member(org_id: str, user_id: str, request: Request) -> Response:
    user, member = await _access(request, org_id)
    # Owners remove anyone; anyone may leave.
    if member["role"] != "owner" and user_id != user.id:
        raise forbidden()
    await _store(request).remove_member(org_id, user_id, user.id)
    return Response(status_code=204)


@router.get("/orgs/{org_id}/invites", summary="Open invitations")
async def invites(org_id: str, request: Request) -> list[dict[str, Any]]:
    await _access(request, org_id, "owner")
    return await _store(request).invites(org_id)


@router.post("/orgs/{org_id}/invites", status_code=201, summary="Invite someone by email")
async def invite(org_id: str, payload: InviteCreate, request: Request) -> dict[str, Any]:
    user, _ = await _access(request, org_id, "owner")
    row, token = await _store(request).create_invite(
        org_id, user.id, email=payload.email, role=payload.role, monthly_limit=payload.monthly_limit
    )
    auth = request.app.state.settings.auth
    base = (auth.web_url or auth.public_url or "").rstrip("/")
    # No email is sent from here yet: the owner copies the link to the person.
    row["link"] = f"{base}/invite/{token}"
    return row


@router.delete("/orgs/{org_id}/invites/{invite_id}", status_code=204, summary="Withdraw an invite")
async def revoke_invite(org_id: str, invite_id: str, request: Request) -> Response:
    user, _ = await _access(request, org_id, "owner")
    await _store(request).revoke_invite(org_id, invite_id, user.id)
    return Response(status_code=204)


@router.get("/invites/{token}", summary="An invitation, before accepting it")
async def invite_info(token: str, request: Request) -> dict[str, Any]:
    row = await _store(request).invite_by_token(token)
    return {
        "org_name": row["org_name"],
        "email": row["email"],
        "role": row["role"],
        "expires_at": row["expires_at"],
        "accepted": bool(row.get("accepted_at")),
    }


@router.post("/invites/{token}/accept", summary="Join the organisation")
async def accept_invite(token: str, request: Request) -> dict[str, Any]:
    user = await _person(request)
    row = await _store(request).accept_invite(token, user_id=user.id, email=user.email)
    return {"org_id": row["org_id"], "org_name": row["org_name"], "role": row["role"]}


# ---- API keys --------------------------------------------------------------------


@router.get("/orgs/{org_id}/keys", summary="API keys: all for owners, your own otherwise")
async def keys(org_id: str, request: Request) -> list[dict[str, Any]]:
    user, member = await _access(request, org_id, *KEY_ROLES)
    return await _store(request).keys(
        org_id, created_by=None if member["role"] == "owner" else user.id
    )


@router.post("/orgs/{org_id}/keys", status_code=201, summary="Create an API key (shown once)")
async def create_key(org_id: str, payload: KeyCreate, request: Request) -> dict[str, Any]:
    user, _ = await _access(request, org_id, *KEY_ROLES)
    row, key = await _store(request).create_key(
        org_id,
        user.id,
        name=payload.name,
        note=payload.note,
        monthly_limit=payload.monthly_limit,
        expires_days=payload.expires_days,
        ip_allowlist=[ip.strip() for ip in payload.ip_allowlist if ip.strip()],
    )
    row["key"] = key
    return row


async def _own_key(request: Request, org_id: str, key_id: str) -> AuthUser:
    user, member = await _access(request, org_id, *KEY_ROLES)
    key = await _store(request).key(org_id, key_id)
    if member["role"] != "owner" and key.get("created_by") != user.id:
        raise forbidden("you can only manage your own keys")
    return user


@router.patch("/orgs/{org_id}/keys/{key_id}", summary="Rename a key or change its limits")
async def update_key(
    org_id: str, key_id: str, payload: KeyUpdate, request: Request
) -> dict[str, str]:
    user = await _own_key(request, org_id, key_id)
    fields = payload.model_dump(exclude_none=True, exclude={"clear_limit"})
    if payload.clear_limit:
        fields["monthly_limit"] = None
    await _store(request).update_key(org_id, key_id, user.id, fields)
    return {"status": "ok"}


@router.post("/orgs/{org_id}/keys/{key_id}/rotate", summary="Replace a key; the old one works 24 h")
async def rotate_key(org_id: str, key_id: str, request: Request) -> dict[str, Any]:
    user = await _own_key(request, org_id, key_id)
    row, key = await _store(request).rotate_key(org_id, key_id, user.id)
    row["key"] = key
    return row


@router.delete("/orgs/{org_id}/keys/{key_id}", status_code=204, summary="Revoke a key")
async def revoke_key(org_id: str, key_id: str, request: Request) -> Response:
    user = await _own_key(request, org_id, key_id)
    await _store(request).revoke_key(org_id, key_id, user.id)
    return Response(status_code=204)


# ---- usage, audit, history ------------------------------------------------------------


@router.get("/orgs/{org_id}/usage", summary="Credits used, by day, member and key")
async def usage(org_id: str, request: Request, days: int = 30, format: str = "json") -> Any:
    user, member = await _access(request, org_id)
    days = max(1, min(days, 366))
    data = await _store(request).usage(
        org_id, days=days, user_id=None if member["role"] == "owner" else user.id
    )
    if format == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["when", "credits", "reason", "member", "key", "note"])
        for row in data["ledger"]:
            writer.writerow(
                [row["created_at"], row["delta"], row["reason"], row.get("email") or "",
                 row.get("key_name") or "", row.get("note") or ""]
            )  # fmt: skip
        return Response(
            out.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="factify-usage-{days}d.csv"'},
        )
    return data


@router.get("/orgs/{org_id}/audit", summary="Who did what in the organisation")
async def audit(org_id: str, request: Request) -> list[dict[str, Any]]:
    await _access(request, org_id, "owner")
    return await _store(request).audit_log(org_id)


@router.get("/orgs/{org_id}/history", summary="The shared history of checks (if switched on)")
async def history(org_id: str, request: Request) -> dict[str, Any]:
    await _access(request, org_id)
    store = _store(request)
    org = await store.org(org_id)
    if not org.get("shared_history"):
        return {"enabled": False, "checks": []}
    return {"enabled": True, "checks": await store.history(org_id)}


# ---- billing ------------------------------------------------------------------------


def _razorpay(request: Request) -> payments.Razorpay:
    billing = request.app.state.settings.billing
    if not billing.razorpay_key_id or not billing.razorpay_key_secret:
        raise ApiError(503, "payments_unavailable", "payments are not set up on this server")
    return payments.Razorpay(
        billing.razorpay_key_id,
        billing.razorpay_key_secret.get_secret_value(),
        billing.razorpay_webhook_secret.get_secret_value()
        if billing.razorpay_webhook_secret
        else None,
    )


@router.get("/billing/packs", summary="Credit packs and their prices")
async def packs(request: Request) -> dict[str, Any]:
    billing = request.app.state.settings.billing
    key = billing.razorpay_key_id or ""
    return {
        "packs": [
            {"id": p.id, "name": p.name, "credits": p.credits, "price_inr": p.price_inr}
            for p in payments.PACKS
        ],
        "available": bool(key and billing.razorpay_key_secret),
        "test_mode": key.startswith("rzp_test_"),
        "costs": {
            "text": request.app.state.settings.auth.check_cost,
            "link": request.app.state.settings.auth.check_cost,
            "picture": request.app.state.settings.auth.check_cost,
            "pdf": request.app.state.settings.auth.check_cost,
            "video": request.app.state.settings.auth.video_check_cost,
        },
    }


@router.post("/orgs/{org_id}/billing/orders", summary="Start buying a credit pack")
async def create_order(org_id: str, payload: OrderCreate, request: Request) -> dict[str, Any]:
    user, _ = await _access(request, org_id, "owner")
    chosen = payments.pack(payload.pack)
    if chosen is None:
        raise bad_request("unknown pack")
    razorpay = _razorpay(request)
    amount = chosen.price_inr * 100
    try:
        order_id = await razorpay.create_order(
            amount_paise=amount,
            receipt=f"org-{org_id[:8]}-{int(datetime.now(UTC).timestamp())}",
            notes={"org_id": org_id, "pack": chosen.id},
        )
    except payments.PaymentsUnavailable as error:
        logger.warning("razorpay order failed: %s", error)
        raise ApiError(502, "payments_unavailable", "the payment could not be started") from error
    store = _store(request)
    await store.create_payment(
        org_id, user.id, order_id=order_id, pack=chosen.id, credits=chosen.credits,
        amount_paise=amount, test_mode=razorpay.test_mode,
    )  # fmt: skip
    org = await store.org(org_id)
    return {
        "order_id": order_id,
        "key_id": razorpay.key_id,
        "amount": amount,
        "currency": "INR",
        "name": "Factify",
        "description": f"{chosen.name} pack: {chosen.credits:,} credits",
        "prefill": {"email": org.get("billing_email") or user.email},
        "test_mode": razorpay.test_mode,
    }


@router.post("/orgs/{org_id}/billing/confirm", summary="Confirm a payment Razorpay completed")
async def confirm_payment(org_id: str, payload: PaymentConfirm, request: Request) -> dict[str, Any]:
    user, _ = await _access(request, org_id, "owner")
    if not _razorpay(request).payment_is_genuine(
        payload.order_id, payload.payment_id, payload.signature
    ):
        raise bad_request("the payment's signature doesn't match", "bad_signature")
    row = await _store(request).mark_paid(payload.order_id, payload.payment_id, user.id)
    if row is None or row["org_id"] != org_id:
        raise bad_request("unknown order")
    return {"status": "paid", "credits": row["credits"]}


@router.post("/billing/razorpay/webhook", include_in_schema=False)
async def razorpay_webhook(request: Request) -> JSONResponse:
    """Razorpay's own word that an order was paid - credits once, even if the
    browser never came back."""
    body = await request.body()
    if not _razorpay(request).webhook_is_genuine(
        body, request.headers.get("x-razorpay-signature", "")
    ):
        return JSONResponse({"detail": "bad signature"}, status_code=400)
    try:
        import json

        event = json.loads(body)
    except ValueError:
        return JSONResponse({"detail": "bad body"}, status_code=400)
    paid = payments.paid_order(event)
    if paid is not None:
        await _store(request).mark_paid(paid[0], paid[1], "razorpay")
    return JSONResponse({"status": "ok"})


@router.get("/orgs/{org_id}/billing/payments", summary="Payments")
async def payment_list(org_id: str, request: Request) -> list[dict[str, Any]]:
    await _access(request, org_id, "owner")
    return await _store(request).payments(org_id)


@router.get(
    "/orgs/{org_id}/billing/payments/{payment_id}/invoice",
    response_class=HTMLResponse,
    summary="A printable invoice",
)
async def invoice(org_id: str, payment_id: str, request: Request) -> HTMLResponse:
    await _access(request, org_id, "owner")
    p = await _store(request).payment(org_id, payment_id)
    if p["status"] != "paid":
        raise bad_request("only a paid order has an invoice")
    from html import escape

    amount = p["amount_paise"] / 100
    test = (
        "<p style='color:#b45309'><b>Test mode: no money was charged.</b></p>"
        if p["test_mode"]
        else ""
    )
    return HTMLResponse(
        f"""<!doctype html><html><head><meta charset="utf-8"><title>Invoice {escape(p["id"][:8])}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{font:15px/1.6 system-ui,sans-serif;max-width:680px;margin:40px auto;padding:0 20px;color:#1c1b18}}
table{{width:100%;border-collapse:collapse;margin:20px 0}}td,th{{border-bottom:1px solid #e2ded4;padding:8px;text-align:left}}
h1{{font-family:Georgia,serif}}@media print{{button{{display:none}}}}</style></head><body>
<h1>Factify - Invoice</h1>{test}
<p>Invoice no. FCT-{escape(p["id"][:8].upper())}<br>Date: {escape(str(p.get("paid_at") or "")[:10])}</p>
<p><b>Billed to</b><br>{escape(p["org_name"])}<br>{escape(p.get("billing_email") or "")}
{("<br>GSTIN: " + escape(p["gst_number"])) if p.get("gst_number") else ""}</p>
<table><tr><th>Item</th><th>Credits</th><th>Amount</th></tr>
<tr><td>{escape(p["pack"].title())} credit pack</td><td>{p["credits"]:,}</td><td>&#8377;{amount:,.2f}</td></tr>
<tr><th colspan="2">Total (INR)</th><th>&#8377;{amount:,.2f}</th></tr></table>
<p>Razorpay order {escape(p["order_id"])}<br>Payment {escape(p.get("payment_id") or "")}</p>
<button onclick="print()">Print or save as PDF</button></body></html>"""
    )


# ---- domains and sign-in -------------------------------------------------------------


@router.get("/orgs/{org_id}/domains", summary="Verified domains")
async def domains(org_id: str, request: Request) -> list[dict[str, Any]]:
    await _access(request, org_id, "owner")
    rows = await _store(request).domains(org_id)
    for row in rows:
        row["record_name"] = f"_factify.{row['domain']}"
        row["record_value"] = f"factify-verify={row['token']}"
    return rows


@router.post("/orgs/{org_id}/domains", status_code=201, summary="Add a domain to verify")
async def add_domain(org_id: str, payload: DomainCreate, request: Request) -> dict[str, Any]:
    user, _ = await _access(request, org_id, "owner")
    domain = payload.domain.strip().lower().removeprefix("@")
    if not _DOMAIN.match(domain) or domain in _PUBLIC_MAIL:
        raise bad_request("enter your organisation's own domain, like example.com")
    row = await _store(request).add_domain(org_id, domain, user.id)
    row["record_name"] = f"_factify.{domain}"
    row["record_value"] = f"factify-verify={row['token']}"
    return row


@router.post("/orgs/{org_id}/domains/{domain}/verify", summary="Check the domain's DNS record")
async def verify_domain(org_id: str, domain: str, request: Request) -> dict[str, Any]:
    user, _ = await _access(request, org_id, "owner")
    store = _store(request)
    row = next((d for d in await store.domains(org_id) if d["domain"] == domain), None)
    if row is None:
        raise bad_request("add the domain first")
    try:
        records = await payments.txt_records(f"_factify.{domain}")
    except Exception as error:
        raise ApiError(502, "dns_unavailable", "DNS could not be checked; try again") from error
    if f"factify-verify={row['token']}" not in records:
        return {"verified": False, "found": records}
    await store.mark_domain(org_id, domain, user.id, {"verified_at": datetime.now(UTC)})
    return {"verified": True}


@router.patch("/orgs/{org_id}/domains/{domain}", summary="Auto-join and its default role")
async def update_domain(
    org_id: str, domain: str, payload: DomainUpdate, request: Request
) -> dict[str, str]:
    user, _ = await _access(request, org_id, "owner")
    if payload.default_role is not None and payload.default_role not in ("developer", "member"):
        raise bad_request("unknown role")
    await _store(request).mark_domain(
        org_id, domain, user.id, payload.model_dump(exclude_none=True)
    )
    return {"status": "ok"}


@router.delete("/orgs/{org_id}/domains/{domain}", status_code=204, summary="Remove a domain")
async def remove_domain(org_id: str, domain: str, request: Request) -> Response:
    user, _ = await _access(request, org_id, "owner")
    await _store(request).remove_domain(org_id, domain, user.id)
    return Response(status_code=204)
