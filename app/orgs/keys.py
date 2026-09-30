"""API keys: `fct_live_` + 32 random characters + a 6-character checksum.

The format follows GitHub's tokens: a prefix says what it is (so a leaked key can be
recognised by a scanner), and a CRC32 checksum lets a mistyped key be refused without
touching the database. Only the SHA-256 of a key is stored; the key itself is shown
once, when it is created.
"""

from __future__ import annotations

import hashlib
import secrets
import string
import zlib

PREFIX = "fct_live_"
_ALPHABET = string.ascii_letters + string.digits
_BODY = 32
_CHECK = 6
# What is shown in the dashboard to recognise a key: the prefix and 4 characters.
SHOWN = len(PREFIX) + 4


def _base62(number: int, width: int) -> str:
    out = []
    for _ in range(width):
        number, digit = divmod(number, 62)
        out.append(_ALPHABET[digit])
    return "".join(reversed(out))


def _checksum(body: str) -> str:
    return _base62(zlib.crc32(body.encode("ascii")), _CHECK)


def new_key() -> str:
    body = "".join(secrets.choice(_ALPHABET) for _ in range(_BODY))
    return f"{PREFIX}{body}{_checksum(body)}"


def looks_valid(key: str) -> bool:
    """The right shape and checksum. Says nothing about whether it exists."""
    if not key.startswith(PREFIX) or len(key) != len(PREFIX) + _BODY + _CHECK:
        return False
    rest = key[len(PREFIX) :]
    body, check = rest[:_BODY], rest[_BODY:]
    return all(c in _ALPHABET for c in rest) and _checksum(body) == check


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("ascii", "replace")).hexdigest()


def shown_part(key: str) -> str:
    return key[:SHOWN]


def new_token() -> str:
    """An invite link's token (not an API key)."""
    return secrets.token_urlsafe(24)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
