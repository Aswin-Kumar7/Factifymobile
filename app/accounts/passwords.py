"""Password hashing: scrypt, from the standard library.

A password is never stored, only `scrypt$N$r$p$salt$hash`: memory-hard, salted per
person, and self-describing, so the cost can be raised later without breaking the
hashes already stored (each is checked with the parameters it was made with).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

# RFC 7914's interactive-login parameters: about 16 MB and a few tens of milliseconds.
_N = 2**14
_R = 8
_P = 1
_LENGTH = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_LENGTH)
    return "$".join(
        [
            "scrypt",
            str(_N),
            str(_R),
            str(_P),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, stored: str | None) -> bool:
    """Whether this password made this hash. False for anything malformed."""
    if not stored:
        return False
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(base64.b64decode(expected)),
        )
    except (ValueError, TypeError):
        return False
    # Constant-time, so how much of a guess was right cannot be timed.
    return hmac.compare_digest(digest, base64.b64decode(expected))
