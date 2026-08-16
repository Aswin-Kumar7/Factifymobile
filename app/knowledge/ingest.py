"""The ingestion worker (M25).

Keeps the corpus minutes-fresh from live public sources. Runs as a short-lived job
triggered from outside, and exits — it is never part of the request path.

Three boundaries that matter more than the mechanics:

**It never blocks a verification.** Ingestion supplies freshness and breadth. A
user-supplied URL is fetched immediately on the request path regardless of what the
corpus knows, so a stalled feed can never make someone wait.

**It never creates trusted evidence.** An ingested item is corpus material. It
becomes usable evidence only when the same validators that judge a user request
accept it — the ingestion path has no privileged route into the evidence table.

**It never republishes.** Titles, dates, publishers, links and a short excerpt are
stored; article bodies are not. What evidence needs is a citation and the sentence
that matters, and keeping more than that would be republishing someone else's work.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import feedparser

from app.db.repositories import CorpusRepository, SourceRepository
from app.embeddings.text import TextEmbedder
from app.extraction.language import Language, detect
from app.intake.normalizer import _canonical_url
from app.knowledge.clustering import OriginClusterer
from app.knowledge.minhash import sign
from app.knowledge.registry import FeedDefinition, FeedRegistry, window_start
from app.observability.logging import event
from app.security.fetcher import FetchFailure, FetchResult, SecureFetcher

logger = logging.getLogger("facify.ingest")

# Enough of an item to cluster on and to quote in a citation; far short of the
# article. Wire reprints diverge in their tails, so the opening is also the part that
# actually carries the near-duplicate signal.
EXCERPT_CHARS = 1200


@dataclass(frozen=True, slots=True)
class IngestedItem:
    """One corpus item, as read from a feed."""

    canonical_url: str
    content_hash: str
    title: str
    excerpt: str
    publisher: str
    published_at: datetime | None
    language: str

    @property
    def clustering_text(self) -> str:
        """What the near-duplicate signature is computed over.

        Title and body together: an outlet reprinting a wire story usually rewrites
        the headline and keeps the body, so using the headline alone would miss most
        syndication and using it not at all would lose a useful signal.
        """
        return f"{self.title}\n{self.excerpt}"


@dataclass(slots=True)
class TickResult:
    """What one scheduled tick did, in enough detail to debug it later."""

    feeds_attempted: int = 0
    feeds_skipped_unchanged: int = 0
    feeds_failed: int = 0
    items_seen: int = 0
    items_new: int = 0
    clusters_created: int = 0
    multi_outlet_clusters: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        """A tick succeeds even when individual feeds fail — that is the design."""
        return self.feeds_attempted > 0


def _parse_published(entry: Any) -> datetime | None:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not parsed:
        return None
    try:
        year, month, day, hour, minute, second = (int(part) for part in parsed[:6])
        return datetime(year, month, day, hour, minute, second, tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _clean(text: str) -> str:
    """Strip markup a feed put in a summary field, without a full HTML parse."""
    import re

    without_tags = re.sub(r"<[^>]+>", " ", text or "")
    return " ".join(without_tags.split())


def parse_feed(body: bytes, *, publisher: str) -> tuple[IngestedItem, ...]:
    """Turn a feed body into corpus items.

    `feedparser` is used rather than a strict XML parse because real feeds are not
    well-formed: mismatched encodings, three different date conventions, namespaces
    that come and go. Being lenient here is not sloppiness — a feed we refuse to
    parse is a publisher we silently stop hearing from.
    """
    parsed = feedparser.parse(body)
    items: list[IngestedItem] = []

    for entry in parsed.entries:
        link = getattr(entry, "link", "") or ""
        title = _clean(getattr(entry, "title", "") or "")
        if not link or not title:
            continue

        summary = _clean(
            getattr(entry, "summary", "")
            or (entry.content[0].value if getattr(entry, "content", None) else "")
        )
        excerpt = summary[:EXCERPT_CHARS]
        canonical = _canonical_url(link)

        # Content-addressed on title plus excerpt rather than the URL, so the same
        # story republished at a new URL is recognised as already seen.
        digest = hashlib.sha256(f"{title}\n{excerpt}".encode()).hexdigest()

        items.append(
            IngestedItem(
                canonical_url=canonical,
                content_hash=f"sha256:{digest}",
                title=title,
                excerpt=excerpt,
                publisher=publisher,
                published_at=_parse_published(entry),
                language=str(detect(f"{title} {excerpt}").language),
            )
        )

    return tuple(items)


class IngestionWorker:
    """Runs one tick: a bounded batch of due feeds, each independently."""

    def __init__(
        self,
        *,
        fetcher: SecureFetcher,
        registry: FeedRegistry,
        corpus: CorpusRepository,
        sources: SourceRepository,
        clusterer: OriginClusterer,
        embedder: TextEmbedder | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._registry = registry
        self._corpus = corpus
        self._sources = sources
        self._clusterer = clusterer
        self._embedder = embedder

    async def tick(self, definitions: dict[str, FeedDefinition], *, limit: int = 5) -> TickResult:
        """Fetch and ingest a bounded batch of due feeds.

        Every feed is handled independently. One publisher being down is not an
        incident here, and must not stop the other four in the batch.
        """
        result = TickResult()
        window = window_start()

        for row in await self._registry.due(limit):
            feed_id = UUID(str(row["id"]))
            url = str(row["url"])
            definition = definitions.get(url)

            if definition is None:
                # Present in the database but no longer declared in the registry.
                # Skipped rather than fetched: the allowlist is the authority.
                continue

            run_id = await self._registry.claim_window(feed_id=feed_id, window_start=window)
            if run_id is None:
                # Another trigger already holds this window. Not an error — this is
                # the idempotency lock doing exactly what it exists for.
                continue

            result.feeds_attempted += 1
            await self._ingest_feed(
                feed_id=feed_id, run_id=run_id, definition=definition, result=result
            )

        result.multi_outlet_clusters = len(self._clusterer.multi_outlet_clusters())
        event(
            logger,
            "ingestion tick complete",
            module="knowledge.ingest",
            outcome="ok",
            feeds=result.feeds_attempted,
            items_new=result.items_new,
            failed=result.feeds_failed,
            multi_outlet_clusters=result.multi_outlet_clusters,
        )
        return result

    async def _ingest_feed(
        self,
        *,
        feed_id: UUID,
        run_id: UUID,
        definition: FeedDefinition,
        result: TickResult,
    ) -> None:
        response = await self._fetcher.fetch(definition.url, provider="feed")

        if isinstance(response, FetchFailure):
            result.feeds_failed += 1
            result.failures.append(f"{definition.publisher}: {response.reason}")
            await self._registry.fail(
                run_id=run_id, feed_id=feed_id, reason=response.reason, consecutive_failures=1
            )
            return

        if response.status_code == 304:
            result.feeds_skipped_unchanged += 1
            await self._registry.skip(
                run_id=run_id, feed_id=feed_id, cadence_minutes=definition.cadence_minutes
            )
            return

        source_id = await self._sources.upsert_source(
            domain=definition.domain,
            publisher=definition.publisher,
            source_class=definition.source_class,
        )

        items = parse_feed(response.body, publisher=definition.publisher)
        result.items_seen += len(items)
        new_count = await self._store(items, source_id=source_id, response=response, result=result)

        await self._registry.complete(
            run_id=run_id,
            feed_id=feed_id,
            item_count=new_count,
            cadence_minutes=definition.cadence_minutes,
        )

    async def _store(
        self,
        items: tuple[IngestedItem, ...],
        *,
        source_id: UUID,
        response: FetchResult,
        result: TickResult,
    ) -> int:
        new_count = 0

        # One embedding batch per feed rather than one call per item: encoding 40
        # items individually pays the per-call overhead 40 times for no benefit.
        # Keyed by item so an unembeddable language (M22 refuses Hinglish) simply
        # has no entry rather than shifting every subsequent vector by one.
        vectors = self._embed(items)

        for item in items:
            snapshot_id = await self._sources.record_snapshot(
                source_id=source_id,
                url=item.canonical_url,
                final_url=response.final_url,
                content_hash=item.content_hash,
                http_status=response.status_code,
                excerpt=item.excerpt[:500],
                title=item.title,
                published_at=item.published_at,
                extraction_method="feedparser",
                extraction_route="feed.rss",
            )

            item_id = await self._corpus.upsert_item(
                canonical_url=item.canonical_url,
                content_hash=item.content_hash,
                title=item.title,
                excerpt=item.excerpt[:500],
                publisher=item.publisher,
                published_at=item.published_at,
                language=item.language,
                source_id=source_id,
                snapshot_id=snapshot_id,
                embedding=vectors.get(item.content_hash),
                minhash_signature=sign(item.clustering_text).to_bytes(),
            )
            new_count += 1

            assignment = self._clusterer.assign(
                document_id=str(item_id),
                text=item.clustering_text,
                publisher=item.publisher,
                url=item.canonical_url,
                published_at=item.published_at,
            )
            if assignment.created_new:
                result.clusters_created += 1

        result.items_new += new_count
        return new_count

    def _embed(self, items: tuple[IngestedItem, ...]) -> dict[str, list[float]]:
        """Embed a batch, tolerating a language the model cannot represent.

        Hinglish items come back without vectors by design (M22). They are still
        stored and still clustered — MinHash works on romanised text — they simply
        rely on lexical retrieval rather than semantic.
        """
        if self._embedder is None or not items:
            return {}

        embeddable = [item for item in items if item.language in {Language.ENGLISH, Language.HINDI}]
        if not embeddable:
            return {}

        outcome = self._embedder.embed(
            [item.clustering_text for item in embeddable], language=embeddable[0].language
        )
        if not outcome.succeeded:
            return {}

        # Keyed by content hash rather than returned positionally: an item the model
        # declined would otherwise shift every subsequent vector onto the wrong row.
        return {
            item.content_hash: list(vector)
            for item, vector in zip(embeddable, outcome.vectors, strict=False)
        }
