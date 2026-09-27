"""The pages a claim was checked against before, so they are read again.

The same forward checked twice gave two verdicts: False on a BBC page that the second
search never returned, then Unconfirmed on a search that found other pages
(2026-09-27). Search results change from one call to the next; a page that spoke to a
claim yesterday still speaks to it today. So the pages that were cited for a claim -
a source that took a side, or showed a narrower version of it - are put back on the
reading list when the same claim is checked again, beside whatever search finds now.
Search can add to the evidence; it can no longer make it disappear.

"The same claim" is the same normalised text, deliberately strict: "Rs 5,000 a month"
and "Rs 6,000 a month" are near neighbours in any similarity measure and different
claims. Only public pages and their addresses are remembered, never what was sent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("factify.knowledge.memory")

# At most this many remembered pages are added to one claim's reading list.
MOST = 3


@dataclass(frozen=True, slots=True)
class RememberedPage:
    url: str
    publisher: str | None
    title: str | None


class EvidenceMemory:
    """Pages cited for a claim in earlier checks, newest first."""

    def __init__(self, database: Any) -> None:
        self._database = database

    async def pages(self, normalized_text: str, *, most: int = MOST) -> list[RememberedPage]:
        if not normalized_text.strip():
            return []
        try:
            async with self._database.connection() as conn:
                cursor = await conn.execute(
                    """
                    SELECT e.citation_url, max(e.publisher) AS publisher,
                           max(s.title) AS title, max(e.observed_at) AS seen
                      FROM evidence e
                      JOIN claim c ON c.id = e.claim_id
                      LEFT JOIN source_snapshot s ON s.id = e.snapshot_id
                     WHERE c.normalized_text = %s
                       AND e.kind IN ('corroboration', 'quote', 'attribution')
                       AND (e.direction IN ('supports', 'contradicts')
                            OR e.match_basis->>'metric' LIKE 'passage_narrower%%')
                     GROUP BY e.citation_url
                     ORDER BY seen DESC
                     LIMIT %s
                    """,
                    (normalized_text, most),
                )
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


def _value(row: Any, name: str, index: int) -> Any:
    return row[name] if isinstance(row, dict) else row[index]
