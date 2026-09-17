"""Destination validation (M09).

Pure functions, no network. Separated from the fetcher so the rules can be tested
exhaustively without a socket, and so there is one place to read when asking "can we
reach this address?".

The service fetches URLs an attacker chooses, from inside our own network. Every
address it is about to open a connection to is checked against the ranges that lead
somewhere private — loopback, RFC1918, link-local (which includes the cloud metadata
endpoint), carrier-grade NAT, multicast and the rest.

The check runs on the initial URL **and on every redirect hop**. A destination that
looks public on the first request and points at an internal address on the second is
the standard way this guard gets bypassed.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})

# Blocked by address property rather than by an explicit range list, so a range we
# never thought of is still caught. `is_global` is False for every private,
# loopback, link-local, multicast, reserved and unspecified address.
#
# 169.254.169.254 — the cloud metadata endpoint, and the single most valuable target
# for an SSRF against a hosted service — is link-local, so it is already covered.
# It is named here because a reader looking for it should find it.
_EXTRA_BLOCKED_V4 = (
    ipaddress.ip_network("169.254.0.0/16"),  # link-local, incl. metadata endpoint
    ipaddress.ip_network("100.64.0.0/10"),  # carrier-grade NAT
    ipaddress.ip_network("192.0.0.0/24"),  # IETF protocol assignments
)

_EXTRA_BLOCKED_V6 = (
    ipaddress.ip_network("fc00::/7"),  # unique local
    ipaddress.ip_network("fe80::/10"),  # link-local
    ipaddress.ip_network("::ffff:0:0/96"),  # IPv4-mapped — a bypass vector
)


class BlockedDestination(Exception):
    """The destination is not one this service is permitted to reach.

    Carries the reason so it can be recorded on the case. A blocked fetch is a
    recorded outcome that leads to abstention, never an exception that reaches the
    user as a verdict.
    """

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"blocked destination {url}: {reason}")


@dataclass(frozen=True, slots=True)
class Destination:
    """A validated target: the URL, its host, and every address it resolves to."""

    url: str
    host: str
    port: int
    addresses: tuple[str, ...]


# NAT64 well-known prefix (RFC 6052): a DNS64 resolver embeds a real IPv4 address in
# the low 32 bits of an IPv6 address under this prefix. Networks that run NAT64/DNS64
# hand these back for ordinary public hosts.
_NAT64_WELL_KNOWN = ipaddress.ip_network("64:ff9b::/96")


def is_blocked_address(address: str) -> str | None:
    """Return the reason this address is unreachable, or None if it is allowed."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return "not a valid IP address"

    # A NAT64 address is validated by the IPv4 it carries, not its IPv6 wrapper. On a
    # DNS64 network an ordinary public API resolves to e.g. 64:ff9b::6439:fbcd, whose
    # IPv6 form reads as "reserved" and would be blocked — but it is the public IPv4
    # 100.57.251.205. This *narrows* the guard rather than skipping it: a NAT64 address
    # embedding 10.0.0.1 (64:ff9b::a00:1) still fails the IPv4 private-range check.
    if ip.version == 6 and ip in _NAT64_WELL_KNOWN:
        embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        return is_blocked_address(str(embedded))

    # Each property is checked explicitly. `is_global` alone is not sufficient:
    # multicast and some reserved ranges report as global, so relying on it would
    # have let 224.0.0.1 through — a real gap this test suite caught.
    # Ordered most-specific first, because the reason is recorded on the case and
    # "link-local" tells an operator far more than "private" when the address in
    # question is the metadata endpoint.
    for label, blocked in (
        ("loopback", ip.is_loopback),
        ("link-local", ip.is_link_local),
        ("multicast", ip.is_multicast),
        ("reserved", ip.is_reserved),
        ("unspecified", ip.is_unspecified),
        ("private", ip.is_private),
        ("not globally routable", not ip.is_global),
    ):
        if blocked:
            return f"{ip} is {label}"

    extra = _EXTRA_BLOCKED_V6 if ip.version == 6 else _EXTRA_BLOCKED_V4
    for network in extra:
        if ip in network:
            return f"{ip} is inside blocked range {network}"

    return None


def validate_url(url: str) -> tuple[str, int]:
    """Check the scheme and shape of a URL. Returns (host, port).

    Rejects everything that is not plain HTTP or HTTPS. `file:`, `gopher:`, `ftp:`
    and friends are not transport we ever need, and each is a documented SSRF
    escalation path.
    """
    parts = urlsplit(url)

    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise BlockedDestination(url, f"scheme {parts.scheme!r} is not permitted")

    if not parts.hostname:
        raise BlockedDestination(url, "no host in URL")

    if "@" in (parts.netloc or ""):
        # Credentials in a URL are both a smuggling trick and a thing we must never
        # send, so the URL is refused rather than sanitised.
        raise BlockedDestination(url, "credentials in URL are not permitted")

    try:
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise BlockedDestination(url, "invalid port") from exc

    return parts.hostname, port


Resolver = Callable[[str, int], list[str]]


def resolve_and_validate(url: str, *, resolver: Resolver | None = None) -> Destination:
    """Resolve the host and reject if **any** resolved address is unreachable.

    Every address is checked, not just the first. A hostname that resolves to one
    public and one private address is refused outright: which one a connection
    actually uses is not something the caller controls.
    """
    host, port = validate_url(url)

    # A bare IP in the URL skips DNS entirely and is checked directly.
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        resolve = resolver or _default_resolver
        try:
            addresses = resolve(host, port)
        except OSError as exc:
            raise BlockedDestination(url, f"host does not resolve: {exc}") from exc

    if not addresses:
        raise BlockedDestination(url, "host resolved to no addresses")

    for address in addresses:
        reason = is_blocked_address(address)
        if reason is not None:
            raise BlockedDestination(url, reason)

    return Destination(url=url, host=host, port=port, addresses=tuple(addresses))


def _default_resolver(host: str, port: int) -> list[str]:
    """Every address the host resolves to, IPv4 and IPv6."""
    infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))
