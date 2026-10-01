"""The Factify admin panel's API: for staff only (app_user.is_staff, or an email in
FACTIFY_AUTH__STAFF_EMAILS). Every change is written to the audit log with who made
it and why."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.accounts import AuthUser
from app.api.orgs import _person, _store
from app.orgs.errors import forbidden

router = APIRouter(prefix="/v1/admin", tags=["admin"])


class Credits(BaseModel):
    amount: int = Field(ge=-1_000_000, le=1_000_000)
    reason: str = Field(min_length=3, max_length=300)


class Status(BaseModel):
    status: str
    reason: str = Field(default="", max_length=300)


class Disabled(BaseModel):
    disabled: bool


class Decision(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)
    grant_credits: int = Field(default=0, ge=0, le=1_000_000)


async def _staff(request: Request) -> AuthUser:
    user = await _person(request)
    if not await _store(request).is_staff(
        user.id, user.email, request.app.state.settings.auth.staff_emails
    ):
        raise forbidden("staff only")
    return user


@router.get("/stats", summary="Platform usage")
async def stats(request: Request) -> dict[str, Any]:
    await _staff(request)
    return await _store(request).admin_stats()


@router.get("/orgs", summary="Search organisations")
async def orgs(request: Request, q: str = "") -> list[dict[str, Any]]:
    await _staff(request)
    return await _store(request).admin_orgs(q.strip())


@router.post("/orgs/{org_id}/credits", summary="Grant or remove organisation credits")
async def org_credits(org_id: str, payload: Credits, request: Request) -> dict[str, str]:
    user = await _staff(request)
    from datetime import UTC, datetime

    await _store(request).add_credits(
        org_id,
        payload.amount,
        reason="grant" if payload.amount > 0 else "adjustment",
        actor=user.id,
        request_key=f"admin:{user.id}:{datetime.now(UTC).timestamp()}",
        note=payload.reason,
    )
    return {"status": "ok"}


@router.post("/orgs/{org_id}/status", summary="Suspend or restore an organisation")
async def org_status(org_id: str, payload: Status, request: Request) -> dict[str, str]:
    user = await _staff(request)
    await _store(request).set_org_status(org_id, payload.status, user.id, payload.reason)
    return {"status": "ok"}


@router.get("/users", summary="Search people")
async def users(request: Request, q: str = "") -> list[dict[str, Any]]:
    await _staff(request)
    return await _store(request).admin_users(q.strip())


@router.post("/users/{user_id}/credits", summary="Grant personal credits")
async def user_credits(user_id: str, payload: Credits, request: Request) -> dict[str, str]:
    user = await _staff(request)
    await _store(request).grant_user(user_id, payload.amount, user.id, payload.reason)
    return {"status": "ok"}


@router.post("/users/{user_id}/disabled", summary="Disable or enable a person")
async def user_disabled(user_id: str, payload: Disabled, request: Request) -> dict[str, str]:
    user = await _staff(request)
    if user_id == user.id:
        raise forbidden("you can't disable yourself")
    await _store(request).set_user_disabled(user_id, payload.disabled, user.id)
    return {"status": "ok"}


@router.get("/keys", summary="Search API keys by prefix or name")
async def keys(request: Request, q: str = "") -> list[dict[str, Any]]:
    await _staff(request)
    return await _store(request).admin_keys(q.strip())


@router.delete("/orgs/{org_id}/keys/{key_id}", status_code=204, summary="Revoke any key")
async def revoke_key(org_id: str, key_id: str, request: Request) -> Response:
    user = await _staff(request)
    await _store(request).revoke_key(org_id, key_id, user.id)
    return Response(status_code=204)


@router.get("/audit", summary="Admin and billing actions")
async def audit(request: Request) -> list[dict[str, Any]]:
    await _staff(request)
    return await _store(request).admin_audit()


@router.get("/org-requests", summary="Requests for an organisation plan")
async def org_requests(request: Request, status: str | None = None) -> list[dict[str, Any]]:
    await _staff(request)
    return await _store(request).org_requests(status or None)


@router.post("/org-requests/{request_id}", summary="Approve or reject a request")
async def decide(request_id: str, payload: Decision, request: Request) -> dict[str, Any]:
    user = await _staff(request)
    return await _store(request).decide_org_request(
        request_id,
        user.id,
        approve=payload.approve,
        note=payload.note,
        grant_credits=payload.grant_credits if payload.approve else 0,
    )
