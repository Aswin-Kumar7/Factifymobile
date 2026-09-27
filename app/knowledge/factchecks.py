"""The fact-checks we have, and keeping the ones a check comes across.

Two places a published fact-check reaches the service from:

  - the fact-checkers' own feeds, ingested like any other outlet (`ingest.py`), whose
    pages carry the verdict as ClaimReview markup;
  - the Google Fact Check Tools API, asked when nothing held locally matches.

Every fact-check the API points at is kept: its page is fetched from the
fact-checker - through the same SSRF-guarded client as everything else - and the
ClaimReview on it recorded in `factcheck_record`. Recorded from the publisher's own
page, not from the API's reply: the page is the published verdict, and the API is
only how we found it. So the next check of the same claim, or a close one, finds it
here and never asks the API at all.

In the background, after the answer is sent: nothing here is on a request path.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from app.db.repositories import CorpusRepository
from app.extraction.claimreview import read_claim_reviews
from app.observability.logging import event
from app.security.fetcher import FetchResult
from app.sources.factcheck import FactCheckRecord, parse_rating_from_title

logger = logging.getLogger("factify.knowledge.factchecks")

# Pages kept from one lookup: the API ranks by relevance, and the tail is noise.
_PER_LOOKUP = 5


def _normalised(text: str) -> str:
    return " ".join(text.lower().split())


async def load_factcheck_records(database: Any) -> list[FactCheckRecord]:
    """Every fact-check held: the kept ClaimReviews, then the ingested headlines.

    A kept ClaimReview carries the fact-checker's own rating and the exact claim it
    reviewed; an ingested headline carries whatever rating its wording shows, if any.
    Where both describe the same page, the ClaimReview is the one used.
    """
    async with database.connection() as conn:
        cursor = await conn.execute(
            """
            SELECT claim_text, url, rating, publisher, published_at, retrieved_at
              FROM factcheck_record
            """
        )
        kept = list(await cursor.fetchall())
        cursor = await conn.execute(
            """
            SELECT ci.title, ci.canonical_url, ci.publisher, ci.published_at
              FROM corpus_item ci
              JOIN source s ON s.id = ci.source_id
             WHERE s.source_class = 'factchecker'
               AND ci.canonical_url IS NOT NULL
            """
        )
        ingested = list(await cursor.fetchall())

    records = [
        FactCheckRecord(
            claim_text=str(row["claim_text"]),
            normalized_text=_normalised(str(row["claim_text"])),
            url=str(row["url"]),
            rating=row["rating"],
            publisher=row["publisher"],
            published_at=row["published_at"],
            retrieved_at=row["retrieved_at"],
        )
        for row in kept
    ]
    reviewed_pages = {record.url for record in records}
    records += [
        FactCheckRecord(
            claim_text=str(row["title"] or ""),
            normalized_text=_normalised(str(row["title"] or "")),
            url=str(row["canonical_url"]),
            rating=parse_rating_from_title(str(row["title"] or "")),
            publisher=row["publisher"],
            published_at=row["published_at"],
            retrieved_at=row["published_at"],
        )
        for row in ingested
        if str(row["canonical_url"]) not in reviewed_pages
    ]
    return records


class FactCheckKeeper:
    """Keeps the fact-checks a check came across, so the next one finds them here."""

    def __init__(
        self,
        *,
        database: Any,
        fetcher: Any,
        on_kept: Callable[[list[FactCheckRecord]], None] | None = None,
    ) -> None:
        self._database = database
        self._fetcher = fetcher
        self.on_kept = on_kept
        # Pages already kept or being kept this process: never fetched twice.
        self._seen: set[str] = set()
        # Held so a background task is not collected before it finishes.
        self._tasks: set[asyncio.Task[int]] = set()

    def remember(self, urls: list[str]) -> None:
        """Keep these fact-check pages, in the background."""
        fresh = [url for url in dict.fromkeys(urls) if url and url not in self._seen]
        if not fresh:
            return
        self._seen.update(fresh)
        task = asyncio.create_task(self.keep(fresh[:_PER_LOOKUP]))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def keep(self, urls: list[str]) -> int:
        """Fetch each page, read its ClaimReview and record it. How many were kept."""
        kept: list[FactCheckRecord] = []
        for url in urls:
            try:
                response = await self._fetcher.fetch(url, provider="factcheck_page")
            except Exception:
                logger.warning("a fact-check page could not be fetched: %s", url)
                continue
            if not isinstance(response, FetchResult) or not 200 <= response.status_code < 300:
                continue
            reviews = read_claim_reviews(response.text, page_url=response.final_url)
            if not reviews:
                # No markup: nothing exact to keep. Its headline still reaches us, if
                # the fact-checker is one we ingest.
                continue
            host = urlsplit(response.final_url).netloc.removeprefix("www.")
            try:
                async with self._database.connection() as conn:
                    repository = CorpusRepository(conn)
                    for review in reviews:
                        page = review.url or response.final_url
                        await repository.record_factcheck(
                            claim_text=review.claim_reviewed,
                            normalized_text=_normalised(review.claim_reviewed),
                            url=page,
                            rating=review.rating,
                            publisher=review.publisher or host,
                            published_at=review.published_at,
                        )
                        kept.append(
                            FactCheckRecord(
                                claim_text=review.claim_reviewed,
                                normalized_text=_normalised(review.claim_reviewed),
                                url=page,
                                rating=review.rating,
                                publisher=review.publisher or host,
                                published_at=review.published_at,
                                retrieved_at=review.published_at,
                            )
                        )
            except Exception:
                logger.exception("a fact-check could not be kept")
        event(
            logger,
            "fact-checks kept",
            module="knowledge.factchecks",
            outcome="ok",
            pages=len(urls),
            kept=len(kept),
        )
        if kept and self.on_kept is not None:
            self.on_kept(kept)
        return len(kept)
