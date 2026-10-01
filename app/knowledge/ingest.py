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

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import feedparser

from app.db.repositories import CorpusRepository, SourceRepository
from app.embeddings.text import TextEmbedder
from app.extraction.claimreview import ClaimReview, read_claim_reviews
from app.extraction.language import Language, detect
from app.extraction.web import extract
from app.intake.normalizer import _canonical_url
from app.knowledge.clustering import OriginClusterer
from app.knowledge.minhash import sign
from app.knowledge.registry import (
    FeedDefinition,
    FeedRegistry,
    failures_behind,
    window_start,
)
from app.observability.logging import event
from app.security.fetcher import FetchFailure, FetchResult, SecureFetcher

logger = logging.getLogger("factify.ingest")

# Enough of an item to cluster on and to quote in a citation; far short of the
# article. Wire reprints diverge in their tails, so the opening is also the part that
# actually carries the near-duplicate signal.
EXCERPT_CHARS = 1200

# How many articles to fetch per feed per tick. Bounded because a tick fetching every
# item of every feed would take minutes and hammer publishers; the newest items are
# the ones a fresh corpus needs and the ones a syndication wave is carrying now.
DEFAULT_BODY_FETCH_LIMIT = 20

# Below this, an extraction is a navigation wrapper or a paywall stub rather than an
# article, and the feed excerpt is the better clustering text.
_MIN_BODY_CHARS = 400


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
    body: str = ""
    # The page's own ClaimReview verdicts, when it is a fact-check with markup.
    reviews: tuple[ClaimReview, ...] = ()

    @property
    def clustering_text(self) -> str:
        """What the near-duplicate signature is computed over.

        Title and body together: an outlet reprinting a wire story usually rewrites
        the headline and keeps the body, so using the headline alone would miss most
        syndication and using it not at all would lose a useful signal.

        The *article* body when it could be fetched, and the feed excerpt only as a
        fallback. That distinction is what makes M26 work at all. Each CMS truncates
        its RSS excerpt at a different length, so the Jaccard between two truncations
        of one wire story is bounded by where the two feeds happened to cut — not by
        how similar the articles are. Measured on the same three PTI stories: 0.301,
        0.265 and 0.205 on excerpts, against 0.787, 0.792 and 0.770 on bodies. The
        first set clusters nothing at any sane threshold; the second clusters cleanly
        at the shipped 0.5.

        Only the signature and a short excerpt are persisted, never the body, so this
        stays inside M25's rule against republishing full article text.
        """
        return f"{self.title}\n{self.body or self.excerpt}"


@dataclass(slots=True)
class TickResult:
    """What one scheduled tick did, in enough detail to debug it later."""

    feeds_attempted: int = 0
    feeds_skipped_unchanged: int = 0
    feeds_failed: int = 0
    items_seen: int = 0
    items_new: int = 0
    items_hydrated: int = 0
    clusters_created: int = 0
    multi_outlet_clusters: int = 0
    # ClaimReview verdicts read from fact-checkers' pages and recorded.
    factchecks_kept: int = 0
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
        body_fetch_limit: int = DEFAULT_BODY_FETCH_LIMIT,
    ) -> None:
        self._fetcher = fetcher
        self._registry = registry
        self._corpus = corpus
        self._sources = sources
        self._clusterer = clusterer
        self._embedder = embedder
        self._body_fetch_limit = body_fetch_limit

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
                feed_id=feed_id,
                run_id=run_id,
                definition=definition,
                result=result,
                failures_before=failures_behind(int(str(row.get("backoff_seconds") or 0))),
            )

        result.multi_outlet_clusters = len(self._clusterer.multi_outlet_clusters())
        event(
            logger,
            "ingestion tick complete",
            module="knowledge.ingest",
            outcome="ok",
            feeds=result.feeds_attempted,
            items_new=result.items_new,
            items_hydrated=result.items_hydrated,
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
        failures_before: int = 0,
    ) -> None:
        response = await self._fetcher.fetch(definition.url, provider="feed")

        if isinstance(response, FetchFailure):
            result.feeds_failed += 1
            result.failures.append(f"{definition.publisher}: {response.reason}")
            await self._registry.fail(
                run_id=run_id,
                feed_id=feed_id,
                reason=response.reason,
                consecutive_failures=failures_before + 1,
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

        items = await self._hydrate(items, result=result)

        new_count = await self._store(items, source_id=source_id, response=response, result=result)

        await self._registry.complete(
            run_id=run_id,
            feed_id=feed_id,
            item_count=new_count,
            cadence_minutes=definition.cadence_minutes,
        )

    async def _hydrate(
        self, items: tuple[IngestedItem, ...], *, result: TickResult
    ) -> tuple[IngestedItem, ...]:
        """Fetch each item's article and attach its extracted body.

        This is what makes origin clustering see syndication. Clustering on feed
        excerpts measurably cannot: the same PTI story reached 0.301 across two
        outlets on excerpts and 0.787 on bodies, and the threshold sits between them.

        Bounded and best-effort. A page that will not load keeps its excerpt and is
        still ingested — an un-hydrated item clusters worse, which is a degraded
        signal, not a failure. Ingestion is a background job precisely so it can
        afford this; nothing here is on a user request path.
        """
        if self._body_fetch_limit <= 0:
            return items

        targets = items[: self._body_fetch_limit]
        responses = await asyncio.gather(
            *(self._fetcher.fetch(item.canonical_url, provider="article") for item in targets),
            return_exceptions=True,
        )

        hydrated: list[IngestedItem] = []
        for item, response in zip(targets, responses, strict=True):
            if not isinstance(response, FetchResult):
                hydrated.append(item)
                continue

            article = extract(response.text, url=item.canonical_url)
            # A fact-checker's verdict, exactly as it published it (ClaimReview): the
            # rating its headline may not carry. Recorded in `_store`.
            reviews = tuple(read_claim_reviews(response.text, page_url=response.final_url))

            # A near-empty extraction means the page was a wrapper, a paywall or a
            # JavaScript shell. The excerpt is better than a fragment, so keep it.
            if len(article.body) < _MIN_BODY_CHARS:
                hydrated.append(replace(item, reviews=reviews))
                continue

            hydrated.append(replace(item, body=article.body, reviews=reviews))
            result.items_hydrated += 1

        return tuple(hydrated) + items[self._body_fetch_limit :]

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

            for review in item.reviews:
                await self._corpus.record_factcheck(
                    claim_text=review.claim_reviewed,
                    normalized_text=" ".join(review.claim_reviewed.lower().split()),
                    url=review.url or item.canonical_url,
                    rating=review.rating,
                    publisher=review.publisher or item.publisher,
                    published_at=review.published_at or item.published_at,
                    snapshot_id=snapshot_id,
                )
                result.factchecks_kept += 1

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
