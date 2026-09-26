"""What a check is doing while someone watches it (contract 1.3, v5 Checking screen).

The Checking screen used to show a timer and three steps it could not tick off,
because the server said nothing until it answered. It now says what it is doing as it
does it: which step it is on, each source as it is opened and whether it had anything
to say about the claim, and how many sources have so far. The app draws its scanner
from these, so what moves on screen is what is happening.

Only what a check is doing travels here, never what it is about: no submitted text,
no claim, no page address - a publisher's name and domain, a step, a count. The same
rule as the ledger (`deployment.md`): nothing that was checked is kept, and these
events are forgotten minutes after the check ends.

Keyed by the id the app watches: the case id of a deep check, which it learns from the
202, or for a normal check a `request_id` it made up and sent with the request, so it
can start listening before the answer - which is the whole check - comes back.

In-process by default. Cloud Run runs several instances, and a stream can land on
another one than the check; `RedisProgressBus` carries the events between them.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.domain.enums import Direction

logger = logging.getLogger("factify.progress")

# The three steps every check goes through, in order.
STEPS = ("read", "search", "compare")

# Kinds of event that end a stream.
_FINAL = frozenset({"done", "error"})

# A channel nobody finishes - a stream opened for a check that never started - is
# dropped after this; a finished one is kept this long for a late or polling reader.
_IDLE_SECONDS = 600.0
_KEEP_SECONDS = 600.0
# Bounds memory against a flood of made-up ids: the oldest channels go first.
_MAX_CHANNELS = 2_000
# Events per check. A deep check reads a few dozen pages; this is far above that.
_MAX_EVENTS = 400

_KEY = re.compile(r"^[0-9a-fA-F-]{32,36}$")


def valid_key(key: str) -> bool:
    """A key is a UUID the client or the server made - nothing else is listened on."""
    return bool(_KEY.fullmatch(key))


class ProgressBus(Protocol):
    async def publish(self, key: str, event: dict[str, Any]) -> None: ...

    def subscribe(self, key: str) -> AsyncIterator[dict[str, Any]]: ...

    async def since(self, key: str, after: int) -> tuple[list[dict[str, Any]], bool]: ...


# ------------------------------------------------------------------- in-process bus


@dataclass(slots=True)
class _Channel:
    created: float
    events: list[dict[str, Any]] = field(default_factory=list)
    finished: float | None = None
    changed: asyncio.Event = field(default_factory=asyncio.Event)


class LocalProgressBus:
    """Events held in this process, replayed to anyone who starts listening late."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._channels: OrderedDict[str, _Channel] = OrderedDict()

    def _channel(self, key: str) -> _Channel:
        self._forget_old()
        channel = self._channels.get(key)
        if channel is None:
            channel = _Channel(created=self._clock())
            self._channels[key] = channel
            while len(self._channels) > _MAX_CHANNELS:
                self._channels.popitem(last=False)
        return channel

    def _forget_old(self) -> None:
        now = self._clock()
        for key in list(self._channels):
            channel = self._channels[key]
            if channel.finished is not None:
                expired = now - channel.finished > _KEEP_SECONDS
            else:
                expired = now - channel.created > _IDLE_SECONDS and not channel.events
            if expired:
                del self._channels[key]

    async def publish(self, key: str, event: dict[str, Any]) -> None:
        channel = self._channel(key)
        if channel.finished is not None or len(channel.events) >= _MAX_EVENTS:
            return
        channel.events.append({**event, "seq": len(channel.events) + 1})
        if event.get("type") in _FINAL:
            channel.finished = self._clock()
        channel.changed.set()
        channel.changed = asyncio.Event()

    async def subscribe(self, key: str) -> AsyncIterator[dict[str, Any]]:
        """Every event so far, then each new one, until the check ends."""
        channel = self._channel(key)
        sent = 0
        while True:
            while sent < len(channel.events):
                event = channel.events[sent]
                sent += 1
                yield event
                if event.get("type") in _FINAL:
                    return
            if channel.finished is not None:
                return
            await channel.changed.wait()

    async def since(self, key: str, after: int) -> tuple[list[dict[str, Any]], bool]:
        """The events after `after`, and whether the check has ended (polling)."""
        channel = self._channels.get(key)
        if channel is None:
            return [], False
        return channel.events[max(0, after) :], channel.finished is not None


# ------------------------------------------------------------------------ Redis bus


class RedisProgressBus:
    """The same events carried through Redis, for more than one instance.

    Each event is appended to a list, so a late reader replays it, and published on a
    channel, so a live reader hears it at once. The list expires with the check.
    `client` is a `redis.asyncio.Redis`; it is passed in so this module imports no
    Redis package unless one is configured (`progress_bus`).
    """

    def __init__(self, client: Any, *, prefix: str = "factify:progress:") -> None:
        self._redis = client
        self._prefix = prefix

    def _log(self, key: str) -> str:
        return f"{self._prefix}{key}:log"

    def _topic(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def publish(self, key: str, event: dict[str, Any]) -> None:
        log = self._log(key)
        # The list's new length is the event's number: one atomic step, whichever
        # instance publishes.
        seq = int(await self._redis.rpush(log, ""))
        if seq > _MAX_EVENTS:
            await self._redis.rpop(log)
            return
        stamped = json.dumps({**event, "seq": seq}, separators=(",", ":"))
        await self._redis.lset(log, seq - 1, stamped)
        await self._redis.expire(log, int(_KEEP_SECONDS))
        await self._redis.publish(self._topic(key), stamped)

    async def subscribe(self, key: str) -> AsyncIterator[dict[str, Any]]:
        # Listening starts before the replay, so nothing published in between is lost;
        # the sequence number drops what arrives twice.
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._topic(key))
        try:
            sent = 0
            for raw in await self._redis.lrange(self._log(key), 0, -1):
                if not raw:
                    continue
                event = json.loads(raw)
                sent = event["seq"]
                yield event
                if event.get("type") in _FINAL:
                    return
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                if message is None:
                    continue
                event = json.loads(message["data"])
                if event["seq"] <= sent:
                    continue
                sent = event["seq"]
                yield event
                if event.get("type") in _FINAL:
                    return
        finally:
            await pubsub.unsubscribe(self._topic(key))
            await pubsub.aclose()

    async def since(self, key: str, after: int) -> tuple[list[dict[str, Any]], bool]:
        raw = await self._redis.lrange(self._log(key), max(0, after), -1)
        events = [json.loads(item) for item in raw if item]
        return events, any(event.get("type") in _FINAL for event in events)


def progress_bus(redis_url: str | None) -> ProgressBus:
    """Redis when a URL is configured, this process otherwise."""
    if not redis_url:
        return LocalProgressBus()
    import redis.asyncio as redis  # type: ignore[import-not-found]  # optional extra

    return RedisProgressBus(redis.from_url(redis_url, decode_responses=True))


# --------------------------------------------------------------- one check's events


def initials(name: str) -> str:
    """Two or three letters for an avatar: "Press Trust of India" -> "PTI"."""
    words = [w for w in re.split(r"[\s\-_.]+", name) if w and w[0].isalnum()]
    capitals = [w[0] for w in words if w[0].isupper() or w[0].isdigit()]
    if len(capitals) >= 2:
        return "".join(capitals[:3]).upper()
    first = words[0] if words else name
    return first[:2].upper() or "?"


class CheckProgress:
    """The events of one check, published as they happen.

    Several claims are checked at once and one site can be read for more than one of
    them, so sources are tracked by domain: started once, done when its last read
    ends, with evidence if any read found some. A page the source check later decides
    is not about the claim is taken back, so the count the screen ends on is the count
    of sources the answer cites.
    """

    def __init__(
        self, bus: ProgressBus, key: str, *, names: Callable[[str], str | None] | None = None
    ) -> None:
        self._bus = bus
        self.key = key
        self._names = names
        self._step = -1
        self._reading: dict[str, int] = {}
        self._publisher: dict[str, str] = {}
        # Domains with evidence, per claim, before and after the source check.
        self._found: dict[str, set[str]] = {}
        self._shown = 0
        self._lock = asyncio.Lock()

    async def _send(self, event: dict[str, Any]) -> None:
        try:
            await self._bus.publish(self.key, event)
        except Exception:
            # Progress is for watching. A bus that fails must never fail the check.
            logger.exception("progress event not published")

    async def step(self, name: str) -> None:
        """Move to a later step; a step already passed is not gone back to."""
        index = STEPS.index(name)
        async with self._lock:
            if index <= self._step:
                return
            self._step = index
        await self._send({"type": "step", "step": name})

    def _label(self, domain: str, publisher: str | None) -> str:
        named = publisher or (self._names(domain) if self._names else None)
        return named or domain

    async def source_started(self, url: str, publisher: str | None = None) -> None:
        domain = _domain(url)
        if not domain:
            return
        async with self._lock:
            first = domain not in self._reading and domain not in self._publisher
            self._reading[domain] = self._reading.get(domain, 0) + 1
            label = self._publisher.setdefault(domain, self._label(domain, publisher))
            again = not first and self._reading[domain] == 1
        if first or again:
            await self._send(
                {
                    "type": "source_started",
                    "publisher": label,
                    "domain": domain,
                    "initials": initials(label),
                }
            )

    async def source_done(self, url: str, *, claim_id: str, found: bool) -> None:
        domain = _domain(url)
        if not domain:
            return
        async with self._lock:
            left = max(0, self._reading.get(domain, 1) - 1)
            self._reading[domain] = left
            if found:
                self._found.setdefault(claim_id, set()).add(domain)
            if left:
                return
            outcome = "evidence" if self._has_evidence(domain) else "not_relevant"
            count = self._count()
        await self._send(
            {
                "type": "source_done",
                "publisher": self._publisher.get(domain, domain),
                "domain": domain,
                "outcome": outcome,
            }
        )
        await self._count_changed(count)

    async def verified(self, claim_id: str, citation_urls: list[str]) -> None:
        """The sources the source check kept for a claim; any it dropped are taken back."""
        async with self._lock:
            before = {d for ids in self._found.values() for d in ids}
            self._found[claim_id] = {_domain(url) for url in citation_urls if _domain(url)}
            after = {d for ids in self._found.values() for d in ids}
            dropped = sorted(before - after)
            count = self._count()
        for domain in dropped:
            await self._send(
                {
                    "type": "source_done",
                    "publisher": self._publisher.get(domain, domain),
                    "domain": domain,
                    "outcome": "not_relevant",
                }
            )
        await self._count_changed(count)

    async def done(self, case_id: str) -> None:
        await self._send({"type": "done", "case_id": case_id})

    async def error(self, code: str) -> None:
        await self._send({"type": "error", "code": code})

    def _has_evidence(self, domain: str) -> bool:
        return any(domain in found for found in self._found.values())

    def _count(self) -> int:
        return len({d for found in self._found.values() for d in found})

    async def _count_changed(self, count: int) -> None:
        if count == self._shown:
            return
        self._shown = count
        await self._send({"type": "evidence_count", "n": count})


_ADDRESSES = frozenset({Direction.SUPPORTS, Direction.CONTRADICTS, Direction.CONTEXTUALIZES})


def addresses_claim(item: Any) -> bool:
    """Whether a piece of evidence speaks to the claim - "Evidence found" on screen.

    A source-risk signal is about the publisher, not the claim, and is not counted.
    """
    return getattr(item, "direction", None) in _ADDRESSES


def _domain(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host.removeprefix("www.")


# The check being watched, if any. Set by the endpoint; read by the pipeline, whose
# source reads run in tasks that inherit it.
current_progress: ContextVar[CheckProgress | None] = ContextVar("current_progress", default=None)
