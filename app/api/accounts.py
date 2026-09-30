"""Accounts: sign-in configuration, the signed-in person's profile, and credits.

Every limit is decided here, on the server, from the credit ledger. The app shows the
balance it is given and the message it is sent; it never decides whether a check may
run.
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from app.accounts import Account, AuthUser, IdentityUnavailable
from app.accounts.credits import SurveyAnswers
from app.accounts.google import APP_REDIRECT, GoogleSignInFailed
from app.accounts.local_auth import AuthRefused, IssuedSession
from app.security.ratelimit import RateLimit, SlidingWindowLimiter

logger = logging.getLogger("factify.api.accounts")

router = APIRouter(prefix="/v1", tags=["accounts"])


class AuthConfigResponse(BaseModel):
    """What the app needs to sign someone in. All of it is public by design."""

    model_config = ConfigDict(frozen=True)

    enabled: bool
    # Whether a check needs a signed-in person.
    required: bool = False
    # "password", and "google" once a Google OAuth client is configured.
    providers: tuple[str, ...] = ()
    min_password_length: int = 8


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)
    name: str | None = Field(default=None, max_length=60)


class SignInRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class SessionResponse(BaseModel):
    """A new session: the token the app sends with every request, and who it is for."""

    model_config = ConfigDict(frozen=True)

    access_token: str
    expires_at: str
    method: str
    email: str
    name: str | None = None


class CreditsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    balance: int
    used: int
    checks: int
    check_cost: int
    # Kept for an app built before 1.4, which reads it; there is one kind of check
    # now, so it is the same as `check_cost`.
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
    # True for a new account that has not answered or skipped the survey: the app
    # asks its four questions once, then never again on any phone.
    survey_due: bool = False


class RenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class SurveyRequest(BaseModel):
    """The survey's answers by key (app.accounts.credits), or `skipped`."""

    skipped: bool = False
    role: str | None = None
    places: list[str] = Field(default_factory=list, max_length=10)
    wants: list[str] = Field(default_factory=list, max_length=10)
    heard: str | None = None


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
        user: AuthUser | None = await identity.verify(token)
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


def check_cost(request: Request) -> int:
    return int(request.app.state.settings.auth.check_cost)


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


async def charge(request: Request, user: AuthUser | None, cost: int) -> None:
    """Record what a finished check cost. Failed checks are never charged: this runs
    only after a check has produced its answer."""
    book = getattr(request.app.state, "credits", None)
    if user is None or book is None or cost == 0:
        return
    await book.charge(user, cost, "check")


@router.get("/auth/config", response_model=AuthConfigResponse, summary="How to sign in")
async def auth_config(request: Request) -> AuthConfigResponse:
    settings = request.app.state.settings
    enabled = getattr(request.app.state, "local_auth", None) is not None
    google = getattr(request.app.state, "google_oauth", None) is not None
    providers: tuple[str, ...] = ()
    if enabled:
        providers = ("password", "google") if google else ("password",)
    return AuthConfigResponse(
        enabled=enabled,
        required=settings.auth.required,
        providers=providers,
        min_password_length=settings.auth.min_password_length,
    )


# Refusals, as HTTP: what the app shows is chosen from `detail`, which is the reason.
_REFUSED_STATUS = {
    "invalid_email": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "weak_password": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "email_taken": status.HTTP_409_CONFLICT,
    "use_google": status.HTTP_409_CONFLICT,
    "wrong_credentials": status.HTTP_401_UNAUTHORIZED,
}

# Password guessing is slowed per address and per network address: ten tries in
# fifteen minutes each, well past anyone mistyping.
_ATTEMPTS = RateLimit(requests=10, window_seconds=900)
_attempts = SlidingWindowLimiter()


def _throttle(request: Request, email: str) -> None:
    client = request.client.host if request.client else "unknown"
    for key in (f"email:{email.strip().lower()}", f"ip:{client}"):
        if not _attempts.check(key, _ATTEMPTS).allowed:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="too_many_attempts")


def _local(request: Request):  # type: ignore[no-untyped-def]
    auth = getattr(request.app.state, "local_auth", None)
    if auth is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="sign_in_unavailable")
    return auth


async def _welcome(request: Request, user: AuthUser) -> None:
    """Open the person's credit account (the signup grant) as they arrive."""
    book = getattr(request.app.state, "credits", None)
    if book is None:
        return
    try:
        await book.account(user, arriving=True)
    except Exception:
        # Credits are shown on the profile and are opened there too; a sign-in
        # never fails because the ledger could not be written at that moment.
        logger.exception("could not open the credit account at sign-in")


def _session(session: IssuedSession) -> SessionResponse:
    return SessionResponse(
        access_token=session.token,
        expires_at=session.expires_at.isoformat(),
        method=session.method,
        email=session.user.email,
        name=session.user.name,
    )


@router.post(
    "/auth/register",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account with an email and a password",
)
async def register(payload: RegisterRequest, request: Request) -> SessionResponse:
    auth = _local(request)
    _throttle(request, payload.email)
    try:
        session = await auth.register(
            email=payload.email, password=payload.password, name=payload.name
        )
    except AuthRefused as refused:
        raise HTTPException(_REFUSED_STATUS[refused.reason], detail=refused.reason) from None
    await _welcome(request, session.user)
    return _session(session)


@router.post(
    "/auth/login", response_model=SessionResponse, summary="Sign in with an email and a password"
)
async def login(payload: SignInRequest, request: Request) -> SessionResponse:
    auth = _local(request)
    _throttle(request, payload.email)
    try:
        session = await auth.sign_in(email=payload.email, password=payload.password)
    except AuthRefused as refused:
        raise HTTPException(_REFUSED_STATUS[refused.reason], detail=refused.reason) from None
    await _welcome(request, session.user)
    return _session(session)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, summary="End this session")
async def logout(request: Request) -> Response:
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header[:7].lower() == "bearer " else ""
    auth = getattr(request.app.state, "local_auth", None)
    if token and auth is not None:
        await auth.sign_out(token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/google/start", summary="Begin signing in with Google, in the browser")
async def google_start(request: Request) -> RedirectResponse:
    google = getattr(request.app.state, "google_oauth", None)
    if google is None:
        return RedirectResponse(f"{APP_REDIRECT}#{urlencode({'error': 'google_unavailable'})}")
    return RedirectResponse(google.start())


@router.get("/auth/google/callback", include_in_schema=False)
async def google_callback(
    request: Request, code: str = "", state: str = "", error: str = ""
) -> RedirectResponse:
    """Where Google sends the browser back. Ends at the app, signed in or not."""
    google = getattr(request.app.state, "google_oauth", None)
    auth = getattr(request.app.state, "local_auth", None)
    if error or google is None or auth is None or not code:
        reason = "google_cancelled" if error == "access_denied" else "google_failed"
        return RedirectResponse(f"{APP_REDIRECT}#{urlencode({'error': reason})}")
    try:
        profile = await google.finish(code=code, state=state)
        session = await auth.sign_in_google(
            sub=profile.sub, email=profile.email, name=profile.name, avatar_url=profile.picture
        )
    except (GoogleSignInFailed, AuthRefused) as failure:
        logger.warning("google sign-in failed: %s", failure)
        return RedirectResponse(f"{APP_REDIRECT}#{urlencode({'error': 'google_failed'})}")
    await _welcome(request, session.user)
    # In the fragment, so the session never reaches any server's logs on the way.
    fragment = urlencode(
        {
            "access_token": session.token,
            "expires_at": session.expires_at.isoformat(),
            "method": "google",
            "email": session.user.email,
        }
    )
    return RedirectResponse(f"{APP_REDIRECT}#{fragment}")


@router.get("/me", response_model=AccountResponse, summary="The signed-in person")
async def me(request: Request) -> AccountResponse:
    user = await _require_person(request)
    return _account_response(request, await _book(request).account(user))


@router.patch("/me", response_model=AccountResponse, summary="Change your display name")
async def rename(payload: RenameRequest, request: Request) -> AccountResponse:
    user = await _require_person(request)
    account = await _book(request).rename(user, payload.name.strip())
    return _account_response(request, account)


@router.put("/me/survey", response_model=AccountResponse, summary="Answer or skip the survey")
async def survey(payload: SurveyRequest, request: Request) -> AccountResponse:
    user = await _require_person(request)
    answers: SurveyAnswers | None = None
    if not payload.skipped:
        try:
            answers = SurveyAnswers(
                role=payload.role,
                places=tuple(payload.places),
                wants=tuple(payload.wants),
                heard=payload.heard,
            )
        except ValueError:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown_answer"
            ) from None
    return _account_response(request, await _book(request).answer_survey(user, answers))


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
            deep_check_cost=auth.check_cost,
            limited=book.enforced,
        ),
        survey_due=account.survey_due,
    )
