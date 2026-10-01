"""The pages a claim was checked against before, so they are read again.

The same forward checked twice gave two verdicts: False on a BBC page that the second
search never returned, then Unconfirmed on a search that found other pages
(2026-09-27). Search results change from one call to the next; a page that spoke to a
claim yesterday still speaks to it today. So the pages that were cited for a claim -
a source that took a side, or showed a narrower version of it - are put back on the
reading list when the same claim is checked again, beside whatever search finds now.
Search can add to the evidence; it can no longer make it disappear.

"The same claim" was once only the same normalised text, and that was not enough:
"DMK wins the 2026 Tamil Nadu elections." read False on the phone, on India Today and
Indian Express, while "DMK won the 2026 Tamil Nadu election." on the website started
from nothing and read Unconfirmed (2026-10-01). One claim, two wordings, two answers.

So it is also the same claim in other words: the nearest earlier claims by meaning
(their stored embeddings), each confirmed by the same-claim question before its pages
are used - because "Rs 5,000 a month" and "Rs 6,000 a month" are near neighbours in
any similarity measure and different claims. Only public pages and their addresses
are remembered, never what was sent.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("factify.knowledge.memory")

# At most this many remembered pages are added to one claim's reading list.
MOST = 4

# How close in meaning an earlier claim must be before it is asked about at all, and
# how many are asked about.
NEAR = 0.82
NEIGHBOURS = 4

# The pages cited for these claims, newest first.
_PAGES = """
    SELECT e.citation_url, max(e.publisher) AS publisher,
           max(s.title) AS title, max(e.observed_at) AS seen
      FROM evidence e
      JOIN claim c ON c.id = e.claim_id
      LEFT JOIN source_snapshot s ON s.id = e.snapshot_id
     WHERE c.normalized_text = ANY(%s)
       AND e.kind IN ('corroboration', 'quote', 'attribution')
       AND (e.direction IN ('supports', 'contradicts')
            OR e.match_basis->>'metric' LIKE 'passage_narrower%%')
     GROUP BY e.citation_url
     ORDER BY seen DESC
     LIMIT %s
"""

# Earlier claims nearest in meaning that were cited against something.
_NEIGHBOURS = """
    SELECT c.text, c.normalized_text, 1 - (c.embedding <=> %s::vector) AS near
      FROM claim c
     WHERE c.embedding IS NOT NULL
       AND c.normalized_text <> %s
       AND EXISTS (SELECT 1 FROM evidence e WHERE e.claim_id = c.id)
     ORDER BY c.embedding <=> %s::vector
     LIMIT %s
"""


@dataclass(frozen=True, slots=True)
class RememberedPage:
    url: str
    publisher: str | None
    title: str | None


class EvidenceMemory:
    """Pages cited for a claim, or for the same claim in other words, in earlier checks."""

    def __init__(
        self,
        database: Any,
        *,
        embedder: Any | None = None,
        same_claim: Callable[[str, str], Awaitable[bool | None]] | None = None,
    ) -> None:
        self._database = database
        # Both optional: without them only the same wording is remembered.
        self._embedder = embedder
        self._same_claim = same_claim

    async def pages(
        self, normalized_text: str, *, text: str = "", most: int = MOST
    ) -> list[RememberedPage]:
        if not normalized_text.strip():
            return []
        try:
            wordings = [normalized_text, *await self._same_claims(normalized_text, text)]
            async with self._database.connection() as conn:
                cursor = await conn.execute(_PAGES, (wordings, most))
                rows = await cursor.fetchall()
        except Exception:
            # Memory is a help, never a dependency: without it the check searches as
            # it always did.
            logger.exception("remembered pages could not be read")
            return []
        return [
            RememberedPage(
                url=_value(row, "citation_url", 0),
                publisher=_value(row, "publisher", 1),
                title=_value(row, "title", 2),
            )
            for row in rows
        ]

    async def _same_claims(self, normalized_text: str, text: str) -> list[str]:
        """Earlier wordings of this same claim, confirmed one by one."""
        if self._embedder is None or self._same_claim is None or not text.strip():
            return []
        result = await asyncio.to_thread(self._embedder.embed_one, text)
        if not result.succeeded or result.single is None:
            return []
        vector = "[" + ",".join(f"{value:.6f}" for value in result.single) + "]"
        async with self._database.connection() as conn:
            cursor = await conn.execute(
                _NEIGHBOURS, (vector, normalized_text, vector, NEIGHBOURS * 3)
            )
            rows = await cursor.fetchall()

        candidates: dict[str, str] = {}
        for row in rows:
            other = _value(row, "normalized_text", 1)
            if float(_value(row, "near", 2)) >= NEAR and other not in candidates:
                candidates[other] = _value(row, "text", 0)
            if len(candidates) >= NEIGHBOURS:
                break
        if not candidates:
            return []
        answers = await asyncio.gather(
            *(self._same_claim(text, other) for other in candidates.values()),
            return_exceptions=True,
        )
        return [
            normalized
            for normalized, answer in zip(candidates, answers, strict=True)
            if answer is True
        ]


def _value(row: Any, name: str, index: int) -> Any:
    return row[name] if isinstance(row, dict) else row[index]
