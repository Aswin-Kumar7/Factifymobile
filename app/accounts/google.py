"""Sign in with Google, through the browser, with this server as the OAuth client.

The app opens `/v1/auth/google/start` in the browser. The server sends the person to
Google's consent page; Google sends them back to `/v1/auth/google/callback` with a
one-time code, which the server exchanges - with its client secret, which never
leaves the server - for Google's ID token. The token is checked with Google, the
account is found or made (`LocalAuth.sign_in_google`), and the browser is sent to
`factify://auth-callback` with the new session in the link's fragment, which the app
is listening for.

Needs a Google Cloud OAuth client (web application) whose authorised redirect URI is
this server's `/v1/auth/google/callback`, reachable by the phone's browser.
"""

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from app.security.fetcher import FetchResult

_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
_EXCHANGE = "https://oauth2.googleapis.com/token"
_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}

# Where the browser may be sent back to: the app, and nowhere else.
APP_REDIRECT = "factify://auth-callback"

# How long a sign-in may take between leaving for Google and coming back.
_STATE_SECONDS = 600.0


class GoogleSignInFailed(Exception):
    """Google did not vouch for this person, or could not be asked."""


@dataclass(frozen=True, slots=True)
class GoogleProfile:
    sub: str
    email: str
    name: str | None
    picture: str | None


class GoogleOAuth:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        fetcher: Any,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._fetcher = fetcher
        self._clock = clock
        # state -> when it expires. One-time: a state is used once, then forgotten.
        self._states: dict[str, float] = {}
        # state -> where the sign-in returns: "app" (factify://) or "web".
        self._targets: dict[str, str] = {}

    def start(self, target: str = "app") -> str:
        """Google's consent page for a new sign-in, with a one-time state."""
        now = self._clock()
        self._states = {s: t for s, t in self._states.items() if t > now}
        self._targets = {s: t for s, t in self._targets.items() if s in self._states}
        state = secrets.token_urlsafe(24)
        self._states[state] = now + _STATE_SECONDS
        self._targets[state] = target
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "prompt": "select_account",
            }
        )
        return f"{_AUTHORIZE}?{query}"

    def target(self, state: str) -> str:
        """Where the sign-in that began with this state should return."""
        return self._targets.pop(state, "app")

    async def finish(self, *, code: str, state: str) -> GoogleProfile:
        """The person Google says this is. Raises when it cannot say so for certain."""
        expires = self._states.pop(state, None)
        if expires is None or expires < self._clock():
            # Not a sign-in this server started, or one abandoned too long ago.
            raise GoogleSignInFailed("unknown or expired sign-in")

        exchanged = await self._fetcher.post_form(
            _EXCHANGE,
            {
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": self._redirect_uri,
                "grant_type": "authorization_code",
            },
            provider="google_oauth",
        )
        id_token = _field(exchanged, "id_token")

        # Checked with Google rather than decoded here: the answer includes whether
        # the token is genuine, whom it was issued to, and whether the email is
        # verified - and keeps key rotation Google's problem.
        info = await self._fetcher.get_json(
            f"{_TOKENINFO}?{urlencode({'id_token': id_token})}", provider="google_oauth"
        )
        claims = _body(info)
        if claims.get("aud") != self._client_id or claims.get("iss") not in _ISSUERS:
            raise GoogleSignInFailed("the token was not issued to this app")
        if str(claims.get("email_verified")).lower() != "true" or not claims.get("email"):
            raise GoogleSignInFailed("Google has not verified this email")
        return GoogleProfile(
            sub=str(claims["sub"]),
            email=str(claims["email"]),
            name=claims.get("name"),
            picture=claims.get("picture"),
        )


def _body(result: Any) -> dict[str, Any]:
    if not isinstance(result, FetchResult) or result.status_code >= 400:
        raise GoogleSignInFailed("Google could not be asked")
    try:
        payload = json.loads(result.text)
    except json.JSONDecodeError as error:
        raise GoogleSignInFailed("Google answered with something that is not JSON") from error
    if not isinstance(payload, dict):
        raise GoogleSignInFailed("Google's answer had an unexpected shape")
    return payload


def _field(result: Any, name: str) -> str:
    value = _body(result).get(name)
    if not isinstance(value, str) or not value:
        raise GoogleSignInFailed(f"Google's answer had no {name}")
    return value
