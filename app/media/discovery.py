"""Reverse-image discovery (M34).

Stage two, and the only path to media older than the corpus. A corpus built over
fifteen days holds no imagery from 2019, so without this the flagship case — a real
2019 photograph presented as today's event — cannot resolve no matter how good the
local matcher is.

**Discovery and dating are separate steps, and conflating them is the mistake.** The
provider returns page URLs, titles and scores. It does not return publication dates.
The date comes from fetching those pages and reading their own metadata — which is
also what produces the anchored excerpt the evidence contract requires. Reverse image
search is the detective; the matched page is the citation; the archive is the notary
when a date is contested.

**Privacy.** The image is submitted as raw bytes. A user's private upload is never
made publicly reachable to satisfy a provider that would prefer a URL — that rule
comes from M10 and is honoured here rather than worked around.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime

from app.extraction.web import extract
from app.governor.governor import Governor, ProviderUnavailable
from app.observability.logging import event
from app.security.fetcher import FetchResult, SecureFetcher
from app.sources.temporal import DatedInstance

logger = logging.getLogger("factify.media.discovery")

PROVIDER = "vision"

# How many matched pages are worth fetching. The provider returns a long tail, and
# each fetch costs time on a request with a 3-8 second budget. The oldest instance is
# what matters and it is rarely the twentieth result.
MAX_PAGES_TO_FETCH = 6


@dataclass(frozen=True, slots=True)
class MatchingPage:
    """A page the provider says carries this image. Not yet dated, not yet evidence."""

    url: str
    title: str | None = None
    score: float = 0.0
    full_match: bool = True

    @property
    def is_worth_fetching(self) -> bool:
        """Partial matches are often crops of unrelated images sharing a texture."""
        return self.full_match


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Where else this image exists, and when — or why we do not know."""

    pages: tuple[MatchingPage, ...] = ()
    instances: tuple[DatedInstance, ...] = ()
    reason: str | None = None
    provider_skipped: bool = False

    @property
    def succeeded(self) -> bool:
        return self.reason is None

    @property
    def oldest(self) -> DatedInstance | None:
        return min(self.instances, key=lambda i: i.published_at) if self.instances else None

    @property
    def undated_pages(self) -> int:
        """Pages found but not datable. Reported, because it bounds the finding."""
        return len(self.pages) - len(self.instances)


class ReverseImageDiscovery:
    """Finds where an image has appeared before, then dates those appearances."""

    def __init__(
        self,
        *,
        fetcher: SecureFetcher,
        governor: Governor,
        endpoint: str,
        api_key: str,
        max_pages: int = MAX_PAGES_TO_FETCH,
    ) -> None:
        self._fetcher = fetcher
        self._governor = governor
        self._endpoint = endpoint
        self._api_key = api_key
        self._max_pages = max_pages

    async def discover(self, image: bytes) -> DiscoveryResult:
        """Submit the image, fetch what comes back, and date it.

        Called only on a local miss. Running this on content the corpus already knows
        would spend a scarce daily unit to learn something already recorded.
        """
        try:
            await self._governor.acquire(PROVIDER)
        except ProviderUnavailable as unavailable:
            return DiscoveryResult(
                reason=f"unavailable: {unavailable.reason.value}", provider_skipped=True
            )

        response = await self._fetcher.post_json(
            self._endpoint,
            {
                "requests": [
                    {
                        # Raw bytes, so no upload is ever exposed publicly (M10).
                        "image": {"content": base64.b64encode(image).decode("ascii")},
                        "features": [{"type": "WEB_DETECTION", "maxResults": 20}],
                    }
                ]
            },
            provider=PROVIDER,
            headers={"x-goog-api-key": self._api_key},
        )

        if not isinstance(response, FetchResult):
            return DiscoveryResult(reason=f"provider failed: {response.reason}")

        try:
            pages = self._parse(response.text)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            return DiscoveryResult(reason=f"unreadable provider response: {type(exc).__name__}")

        if not pages:
            return DiscoveryResult(reason="no matching pages found")

        instances = await self._date(pages)

        event(
            logger,
            "reverse image discovery complete",
            module="media.discovery",
            outcome="ok",
            provider=PROVIDER,
            pages=len(pages),
            dated=len(instances),
        )

        return DiscoveryResult(pages=pages, instances=instances)

    def _parse(self, body: str) -> tuple[MatchingPage, ...]:
        """Read the matched pages out of the provider response.

        Note what is deliberately not read: there is no date field to read. The
        provider does not return one, which is why the next step exists.
        """
        payload = json.loads(body)
        detection = payload["responses"][0].get("webDetection", {})

        pages = [
            MatchingPage(
                url=entry["url"],
                title=entry.get("pageTitle"),
                score=float(entry.get("score", 0.0)),
                full_match=bool(entry.get("fullMatchingImages")),
            )
            for entry in detection.get("pagesWithMatchingImages", [])
            if entry.get("url")
        ]

        pages.sort(key=lambda page: (not page.full_match, -page.score))
        return tuple(pages)

    async def _date(self, pages: tuple[MatchingPage, ...]) -> tuple[DatedInstance, ...]:
        """Fetch each matched page and read its own publication date.

        This is where a page URL becomes a citation. A page that will not load, or
        that carries no date, contributes nothing rather than a guess — an undated
        appearance cannot establish that anything predates anything.
        """
        instances: list[DatedInstance] = []

        for page in pages[: self._max_pages]:
            if not page.is_worth_fetching:
                continue

            response = await self._fetcher.fetch(page.url, provider="matched_page")
            if not isinstance(response, FetchResult):
                continue

            article = extract(response.text, url=page.url)
            if article.published_at is None:
                continue

            instances.append(
                DatedInstance(
                    url=response.final_url,
                    published_at=article.published_at,
                    publisher=article.publisher,
                    method="matched_page_date",
                )
            )

        return tuple(instances)


class UnavailableDiscovery:
    """Used when reverse image search is not configured.

    Returns nothing. A local miss with no discovery available means the media
    question abstains — which is correct, and much better than the alternative of
    treating "we could not look" as "there is nothing to find".
    """

    async def discover(self, image: bytes) -> DiscoveryResult:
        del image
        return DiscoveryResult(
            reason="unavailable: reverse image discovery is not configured",
            provider_skipped=True,
        )


def instances_from_local_match(
    *, source_date: datetime | None, citation_url: str | None, publisher: str | None
) -> tuple[DatedInstance, ...]:
    """Turn a local corpus hit into a dated instance the temporal resolver can use.

    Keeps the two discovery paths — corpus and provider — feeding one dating step, so
    a cached answer and a fresh one produce the same shape of finding.
    """
    if source_date is None or not citation_url:
        return ()

    return (
        DatedInstance(
            url=citation_url,
            published_at=source_date,
            publisher=publisher,
            method="matched_page_date",
        ),
    )
