"""The cache layer (M13).

Three surfaces, one purpose: make repeat content free. That is simultaneously the
cost model, the reason the demo survives a provider outage, and the mechanism behind
the compounding-moat claim — hit rate rises with usage, so marginal cost falls.

The probe runs **immediately after hashing and before any external call**. A cache
that sits behind the providers it is supposed to protect saves storage, not money.

Negative caching is deliberate and easy to get wrong. `UNVERIFIED` is by far the most
common answer, and re-running a full metered pipeline every time someone shares the
same unresolvable forward is how a daily quota disappears before lunch. But an
abstention is also the answer most likely to *change* — the corpus grows, a
fact-check gets published, the developing window closes — so negative entries carry a
much shorter life than decisive ones.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.cache.keys import CacheKeyParts
from app.db.repositories import CacheRepository, Conn
from app.observability.logging import event
from app.observability.metrics import metrics

logger = logging.getLogger("facify.cache")

# A decisive verdict rests on citations that were true when collected and stay true.
DECISIVE_TTL = timedelta(days=30)

# An abstention is the answer most likely to change underneath us.
NEGATIVE_TTL = timedelta(hours=6)

# Inside the developing-news window the answer is expected to change within the hour,
# so caching it for longer would serve "too recent to corroborate" after it stopped
# being true.
DEVELOPING_TTL = timedelta(minutes=30)

# Extraction is a pure function of the document and the extractor. It only expires so
# that a corpus of stale payloads does not grow without bound.
EXTRACTION_TTL = timedelta(days=14)


@dataclass(frozen=True, slots=True)
class CachedVerdict:
    """A verdict served from cache, with the time it was originally computed.

    `retrieved_at` is not optional and not decorative. A result shown to a user
    without saying when it was established is a claim about the present made from
    evidence about the past, and the interface has no way to be honest about that
    unless this value travels with the payload.
    """

    payload: dict[str, Any]
    retrieved_at: datetime
    rule_version: str
    is_negative: bool

    @property
    def age(self) -> timedelta:
        """How old the cached answer is, never negative.

        `retrieved_at` comes from the database clock and the comparison from this
        process's, and the two are not synchronised — a fresh entry routinely reads
        as a second in the future. Clamping is not cosmetic: the interface renders
        this, and "computed 1 second from now" is worse than "computed just now".
        """
        return max(timedelta(0), datetime.now(UTC) - self.retrieved_at)


class CacheService:
    """Reads and writes the three cache surfaces."""

    def __init__(self, conn: Conn) -> None:
        self._repository = CacheRepository(conn)

    # -- verdicts ---------------------------------------------------------------

    async def get_verdict(self, parts: CacheKeyParts) -> CachedVerdict | None:
        """Probe for a complete verdict.

        A hit requires every component of the key to match, so a rule-version bump
        cannot serve yesterday's logic — the key simply does not exist under the new
        version and the pipeline recomputes.
        """
        row = await self._repository.get_verdict(parts.derive())

        if row is None:
            metrics.record_cache_miss("verdict")
            return None

        metrics.record_cache_hit("verdict")
        event(
            logger,
            "verdict served from cache",
            module="cache",
            outcome="hit",
            rule_version=str(row["rule_version"]),
            negative=bool(row["is_negative"]),
        )
        return CachedVerdict(
            payload=dict(row["status_json"]),
            retrieved_at=row["created_at"],
            rule_version=str(row["rule_version"]),
            is_negative=bool(row["is_negative"]),
        )

    async def put_verdict(
        self,
        parts: CacheKeyParts,
        payload: dict[str, Any],
        *,
        case_id: object | None = None,
        is_negative: bool = False,
        developing: bool = False,
    ) -> None:
        """Store a verdict with a life appropriate to how settled it is."""
        if developing:
            ttl = DEVELOPING_TTL
        elif is_negative:
            ttl = NEGATIVE_TTL
        else:
            ttl = DECISIVE_TTL

        await self._repository.put_verdict(
            cache_key=parts.derive(),
            status_json=payload,
            rule_version=parts.rule_version,
            extractor_version=parts.extractor_version,
            corpus_version=parts.corpus_version,
            policy_profile=parts.policy_profile,
            case_id=case_id,  # type: ignore[arg-type]
            language=parts.language,
            is_negative=is_negative,
            expires_at=datetime.now(UTC) + ttl,
        )

    # -- extraction -------------------------------------------------------------

    async def get_extraction(
        self, *, content_hash: str, extractor_version: str
    ) -> dict[str, Any] | None:
        """Claims already extracted from this exact document.

        This is what makes the Day 13 evaluation affordable: re-running the audit
        manifest after a code change costs zero model calls, because the documents
        did not change and neither did the extractor.
        """
        row = await self._repository.get_extraction(
            content_hash=content_hash, extractor_version=extractor_version
        )

        if row is None:
            metrics.record_cache_miss("extraction")
            return None

        metrics.record_cache_hit("extraction")
        return dict(row["payload"])

    async def put_extraction(
        self,
        *,
        content_hash: str,
        extractor_version: str,
        payload: dict[str, Any],
        model_id: str | None = None,
    ) -> None:
        await self._repository.put_extraction(
            content_hash=content_hash,
            extractor_version=extractor_version,
            payload=payload,
            model_id=model_id,
            expires_at=datetime.now(UTC) + EXTRACTION_TTL,
        )

    # -- resolved URL text ------------------------------------------------------

    async def get_url_text(self, *, canonical_url: str, extractor_version: str) -> str | None:
        """Text already extracted from this URL.

        Keyed by URL rather than by body hash, because the point is to avoid the
        fetch itself: a viral link is fetched once, not ten thousand times.
        """
        row = await self._repository.get_extraction(
            content_hash=f"url:{canonical_url}", extractor_version=extractor_version
        )

        if row is None:
            metrics.record_cache_miss("url_text")
            return None

        metrics.record_cache_hit("url_text")
        text = row["payload"].get("text")
        return str(text) if text is not None else None

    async def put_url_text(
        self, *, canonical_url: str, extractor_version: str, text: str, final_url: str
    ) -> None:
        await self._repository.put_extraction(
            content_hash=f"url:{canonical_url}",
            extractor_version=extractor_version,
            payload={"text": text, "final_url": final_url},
            expires_at=datetime.now(UTC) + EXTRACTION_TTL,
        )
