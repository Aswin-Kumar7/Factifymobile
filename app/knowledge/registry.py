"""Feed registry and the ingestion trigger (M24).

Owns the allowlisted source list and the single lock that makes a duplicated trigger
a provable no-op.

Two rules about *where* scheduling runs, both learned the expensive way by other
people:

  - **Never inside the web process.** Instances scale to zero and multiply, so an
    in-process timer either stops firing or fires N times. The trigger comes from
    outside and the work runs as a job that exits.
  - **Never from CI.** Scheduled workflows on a public repository are disabled
    automatically after a period of inactivity — silently, and precisely during the
    post-hackathon window when a freshening corpus is the thing being demonstrated.
    A public repository is also the wrong home for credentials.
"""

from __future__ import annotations

import hmac
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from app.db.repositories import FeedRepository
from app.observability.logging import event

logger = logging.getLogger("facify.registry")

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "feeds.json"

# A small batch per tick, not the whole registry. A tick that tries to fetch thirty
# feeds takes thirty timeouts to fail and holds a job open the whole time; five
# means a stuck feed delays one tick and the next one moves on.
DEFAULT_BATCH_SIZE = 5

# Per-domain backoff after a failure, doubling to a ceiling. A feed that is down
# stays out of the rotation instead of consuming a slot every tick.
BACKOFF_BASE_SECONDS = 300
BACKOFF_CEILING_SECONDS = 6 * 3600


@dataclass(frozen=True, slots=True)
class FeedDefinition:
    """One allowlisted source as declared in the registry file."""

    url: str
    publisher: str
    source_class: str
    cadence_minutes: int = 30
    allowed_for_primary_check: bool = False
    carries_wire: bool = False

    @property
    def domain(self) -> str:
        return urlsplit(self.url).netloc.lower()

    @property
    def is_factchecker(self) -> bool:
        """Only these can produce Tier C evidence. News is corroboration material."""
        return self.source_class == "factchecker"


def load_registry(path: Path | None = None) -> tuple[FeedDefinition, ...]:
    """Read the allowlist. Data, not code — adding a source is a review, not a deploy."""
    payload = json.loads((path or REGISTRY_PATH).read_text(encoding="utf-8"))

    definitions = tuple(
        FeedDefinition(
            url=entry["url"],
            publisher=entry["publisher"],
            source_class=entry["source_class"],
            cadence_minutes=int(entry.get("cadence_minutes", 30)),
            allowed_for_primary_check=bool(entry.get("allowed_for_primary_check", False)),
            carries_wire=bool(entry.get("carries_wire", False)),
        )
        for entry in payload["feeds"]
    )

    urls = [definition.url for definition in definitions]
    if len(set(urls)) != len(urls):
        raise ValueError("registry contains duplicate feed URLs")

    # The M26 gate needs syndicated duplicates to collapse, and national mastheads
    # measurably do not provide them — they write their own copy. A registry with no
    # wire-carrying outlet cannot satisfy that gate however long ingestion runs, so
    # the condition is caught here at load rather than as a mysteriously empty
    # cluster table days later.
    if not any(definition.carries_wire for definition in definitions):
        raise ValueError(
            "registry contains no outlet marked carries_wire; origin clustering would "
            "have no syndicated duplicates to collapse and the M26 gate cannot pass"
        )

    return definitions


def backoff_for(consecutive_failures: int) -> int:
    """Exponential, capped. A dead feed must not occupy a slot every tick."""
    if consecutive_failures <= 0:
        return 0
    return int(min(BACKOFF_BASE_SECONDS * 2 ** (consecutive_failures - 1), BACKOFF_CEILING_SECONDS))


def authenticate_trigger(supplied: str | None, expected: str | None) -> bool:
    """Verify the scheduler's shared secret.

    Constant-time comparison: the endpoint is reachable from the internet, and a
    timing-variable check on a fixed secret is worth avoiding for the cost of one
    function call. A missing configured secret denies rather than allows, so an
    unconfigured deployment cannot be triggered by anyone.
    """
    if not expected or not supplied:
        return False
    return hmac.compare_digest(supplied, expected)


class FeedRegistry:
    """Synchronises the declared allowlist into the database and hands out work."""

    def __init__(self, repository: FeedRepository) -> None:
        self._repository = repository

    async def sync(self, definitions: tuple[FeedDefinition, ...]) -> int:
        """Register every declared feed. Idempotent, so it can run at every boot."""
        for definition in definitions:
            await self._repository.register(
                url=definition.url,
                domain=definition.domain,
                publisher=definition.publisher,
            )

        event(
            logger,
            "feed registry synchronised",
            module="knowledge.registry",
            outcome="ok",
            feeds=len(definitions),
        )
        return len(definitions)

    async def due(self, limit: int = DEFAULT_BATCH_SIZE) -> list[dict[str, object]]:
        """The bounded batch this tick will attempt."""
        return await self._repository.due(limit)

    async def claim_window(self, *, feed_id: UUID, window_start: datetime) -> UUID | None:
        """Take the lock for this feed and window.

        `None` means another trigger already holds it. That is the whole idempotency
        story: a duplicated scheduler firing is not deduplicated after the fact, it
        simply never starts.
        """
        return await self._repository.start_run(feed_id=feed_id, window_start=window_start)

    async def complete(
        self,
        *,
        run_id: UUID,
        feed_id: UUID,
        item_count: int,
        cadence_minutes: int,
        cursor: str | None = None,
    ) -> None:
        await self._repository.finish_run(
            run_id=run_id, status="complete", item_count=item_count, cursor=cursor
        )
        await self._repository.reschedule(
            feed_id=feed_id,
            next_fetch_at=datetime.now(UTC) + timedelta(minutes=cadence_minutes),
            backoff_seconds=0,
        )

    async def fail(
        self,
        *,
        run_id: UUID,
        feed_id: UUID,
        reason: str,
        consecutive_failures: int,
    ) -> None:
        """Record a failure and push the feed out with backoff.

        A feed failure is never allowed to fail the tick: the other four feeds in the
        batch still have work to do, and a publisher having a bad afternoon is not an
        incident on our side.
        """
        delay = backoff_for(consecutive_failures)

        await self._repository.finish_run(run_id=run_id, status="failed", failure_reason=reason)
        await self._repository.reschedule(
            feed_id=feed_id,
            next_fetch_at=datetime.now(UTC) + timedelta(seconds=delay),
            backoff_seconds=delay,
        )

        event(
            logger,
            "feed fetch failed",
            module="knowledge.registry",
            outcome="error",
            failure_reason=reason,
            level=logging.WARNING,
            backoff_seconds=delay,
            consecutive_failures=consecutive_failures,
        )

    async def skip(self, *, run_id: UUID, feed_id: UUID, cadence_minutes: int) -> None:
        """Record an unchanged feed. Cheap, and worth distinguishing from a failure."""
        await self._repository.finish_run(run_id=run_id, status="skipped")
        await self._repository.reschedule(
            feed_id=feed_id,
            next_fetch_at=datetime.now(UTC) + timedelta(minutes=cadence_minutes),
        )


def window_start(now: datetime | None = None, *, minutes: int = 15) -> datetime:
    """The current scheduling window, truncated.

    Truncation is what makes the lock work: two triggers a few seconds apart resolve
    to the same window and therefore to the same unique key, so the second one loses.
    """
    moment = now or datetime.now(UTC)
    return moment.replace(minute=(moment.minute // minutes) * minutes, second=0, microsecond=0)
