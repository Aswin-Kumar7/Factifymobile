"""Who is asking: a Supabase Auth session token, checked with Supabase itself.

The app signs people in with Supabase (an emailed six-digit code, or Google) and sends
the session's access token with every request. The server does not take the app's
word for who that is: it asks Supabase's own `/auth/v1/user` endpoint, which answers
only for a token Supabase issued and has not expired or revoked.

Asked rather than verified locally on purpose. Checking a JWT's signature here would
need a crypto library this service does not carry, and would have to track Supabase's
signing-key rotation; asking Supabase needs neither and is always current. The answer
is remembered for a minute per token, so a person running several checks pays for one
round trip, not one per check.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from app.security.fetcher import FetchResult, SecureFetcher

# How long a verified token's answer is reused. Short, because a signed-out or deleted
# user should stop being accepted within a minute, not an hour.
_REMEMBER_SECONDS = 60.0
_REMEMBER_AT_MOST = 10_000


@dataclass(frozen=True, slots=True)
class AuthUser:
    """A signed-in person, as Supabase knows them."""

    id: str
    email: str
    name: str | None = None
    avatar_url: str | None = None


class IdentityUnavailable(Exception):
    """Supabase could not be asked. Not the same as "this token is not valid"."""


class SupabaseIdentity:
    def __init__(
        self,
        *,
        url: str,
        anon_key: str,
        fetcher: Any | None = None,
        clock: Any = time.monotonic,
    ) -> None:
        self._url = url.rstrip("/")
        self._anon_key = anon_key
        # The secure fetcher, like every other outbound call in this service.
        self._fetcher = fetcher or SecureFetcher(timeout_seconds=10.0)
        self._clock = clock
        self._remembered: dict[str, tuple[float, AuthUser]] = {}

    async def verify(self, token: str) -> AuthUser | None:
        """The person this token belongs to, or None if Supabase does not accept it.

        Raises `IdentityUnavailable` when Supabase cannot be reached: that is an
        outage, and answering it with "not signed in" would sign everyone out.
        """
        key = hashlib.sha256(token.encode()).hexdigest()
        now = self._clock()
        remembered = self._remembered.get(key)
        if remembered is not None and remembered[0] > now:
            return remembered[1]

        response = await self._fetcher.get_json(
            f"{self._url}/auth/v1/user",
            provider="supabase_auth",
            headers={"apikey": self._anon_key, "Authorization": f"Bearer {token}"},
        )
        if not isinstance(response, FetchResult):
            raise IdentityUnavailable(response.reason)

        if response.status_code in (401, 403):
            self._remembered.pop(key, None)
            return None
        if response.status_code >= 400:
            raise IdentityUnavailable(f"supabase returned {response.status_code}")

        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as error:
            raise IdentityUnavailable(
                "supabase answered with something that is not JSON"
            ) from error
        user = _user_from(payload if isinstance(payload, dict) else {})
        if user is None:
            return None

        if len(self._remembered) >= _REMEMBER_AT_MOST:
            self._remembered = {k: v for k, v in self._remembered.items() if v[0] > now}
        self._remembered[key] = (now + _REMEMBER_SECONDS, user)
        return user


def _user_from(payload: dict[str, Any]) -> AuthUser | None:
    user_id = payload.get("id")
    email = payload.get("email")
    if not user_id or not email:
        return None
    metadata = payload.get("user_metadata") or {}
    name = metadata.get("full_name") or metadata.get("name")
    avatar = metadata.get("avatar_url") or metadata.get("picture")
    return AuthUser(
        id=str(user_id),
        email=str(email),
        name=str(name) if name else None,
        avatar_url=str(avatar) if avatar else None,
    )
