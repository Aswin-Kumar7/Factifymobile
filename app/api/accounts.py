"""Accounts: sign-in configuration, the signed-in person's profile, and credits.

Every limit is decided here, on the server, from the credit ledger. The app shows the
balance it is given and the message it is sent; it never decides whether a check may
run.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.accounts import Account, AuthUser, IdentityUnavailable
from app.config import supabase_url_for

logger = logging.getLogger("factify.api.accounts")

router = APIRouter(prefix="/v1", tags=["accounts"])


class AuthConfigResponse(BaseModel):
    """What the app needs to sign someone in. All of it is public by design."""

    model_config = ConfigDict(frozen=True)

    enabled: bool
    supabase_url: str | None = None
    anon_key: str | None = None
    # Whether a check needs a signed-in person.
    required: bool = False
    providers: tuple[str, ...] = ()


class CreditsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    balance: int
    used: int
    checks: int
    check_cost: int
    deep_check_cost: int
    # False while plans do not exist: usage is recorded and nothing is refused.
    limited: bool


class AccountResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    email: str
    name: str | None = None
    avatar_url: str | None = None
    plan: str
    joined_at: str | None = None
    credits: CreditsResponse


class RenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)


async def signed_in(request: Request) -> AuthUser | None:
    """The person making this request, or None when it is anonymous.

    Called inside a route body rather than as a dependency, for the reason
    `verify` gives: an exception raised in a dependency lands before the request body
    is validated, and a malformed request would come back 401 instead of 422.
    """
    settings = request.app.state.settings
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header[:7].lower() == "bearer " else ""

    if not token:
        if settings.auth.required:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="sign in to check")
        return None

    identity = getattr(request.app.state, "identity", None)
    if identity is None:
        # Sign-in is not configured on this server, so there is no session to honour.
        return None

    try:
        user = await identity.verify(token)
    except IdentityUnavailable as outage:
        logger.warning("sign-in could not be checked: %s", outage)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="sign-in could not be checked; try again shortly",
        ) from outage
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="your session has ended; sign in again"
        )
    return user


def check_cost(request: Request, *, deep: bool) -> int:
    auth = request.app.state.settings.auth
    return int(auth.deep_check_cost if deep else auth.check_cost)


async def require_credit(request: Request, user: AuthUser | None, cost: int) -> None:
    """Refuse the check if this person cannot pay for it. Anonymous checks are not
    metered. While credits are not enforced this never refuses — and a ledger that
    cannot be read does not block a check either."""
    book = getattr(request.app.state, "credits", None)
    if user is None or book is None or cost == 0:
        return
    try:
        decision = await book.authorize(user, cost)
    except Exception:
        logger.exception("the credit ledger could not be read")
        if book.enforced:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="your credits could not be checked; try again shortly",
            ) from None
        return
    if not decision.allowed:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"out of credits: this check costs {decision.cost} and the balance is "
                f"{decision.balance}"
            ),
        )


async def charge(request: Request, user: AuthUser | None, cost: int, *, deep: bool) -> None:
    """Record what a finished check cost. Failed checks are never charged: this runs
    only after a check has produced its answer."""
    book = getattr(request.app.state, "credits", None)
    if user is None or book is None or cost == 0:
        return
    await book.charge(user, cost, "deep_check" if deep else "check")


@router.get("/auth/config", response_model=AuthConfigResponse, summary="How to sign in")
async def auth_config(request: Request) -> AuthConfigResponse:
    settings = request.app.state.settings
    project = supabase_url_for(settings)
    key = settings.auth.anon_key.get_secret_value() if settings.auth.anon_key else None
    enabled = bool(project and key and getattr(request.app.state, "identity", None))
    return AuthConfigResponse(
        enabled=enabled,
        supabase_url=project if enabled else None,
        anon_key=key if enabled else None,
        required=settings.auth.required,
        providers=("email", "google") if enabled else (),
    )


@router.get("/me", response_model=AccountResponse, summary="The signed-in person")
async def me(request: Request) -> AccountResponse:
    user = await _require_person(request)
    return _account_response(request, await _book(request).account(user))


@router.patch("/me", response_model=AccountResponse, summary="Change your display name")
async def rename(payload: RenameRequest, request: Request) -> AccountResponse:
    user = await _require_person(request)
    account = await _book(request).rename(user, payload.name.strip())
    return _account_response(request, account)


async def _require_person(request: Request) -> AuthUser:
    user = await signed_in(request)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="sign in to see your account")
    return user


def _book(request: Request):  # type: ignore[no-untyped-def]
    book = getattr(request.app.state, "credits", None)
    if book is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="accounts unavailable")
    return book


def _account_response(request: Request, account: Account) -> AccountResponse:
    auth = request.app.state.settings.auth
    book = _book(request)
    return AccountResponse(
        id=account.id,
        email=account.email,
        name=account.name,
        avatar_url=account.avatar_url,
        plan=account.plan,
        joined_at=account.joined_at.isoformat() if account.joined_at else None,
        credits=CreditsResponse(
            balance=account.balance,
            used=account.used,
            checks=account.checks,
            check_cost=auth.check_cost,
            deep_check_cost=auth.deep_check_cost,
            limited=book.enforced,
        ),
    )
