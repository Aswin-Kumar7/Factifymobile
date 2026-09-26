"""How a false or misleading claim misleads (contract 1.3).

The app teaches one lesson beside a False or Misleading answer — "a picture
published earlier, shared again as if new", "a figure changed". Which lesson is read
off what was already decided: the claim's status, its type, and the kind of evidence
behind it. Nothing here changes a status or a confidence; it names a pattern in a
decision that is already made.

The rule was the app's own until 1.3 (`teaching_line.dart`) and moved here so every
client names the same technique. The app keeps it as the fallback for older servers.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.domain.enums import ClaimStatus, ClaimType, Direction, EvidenceKind, Technique

_REFUTED = frozenset({ClaimStatus.CONTRADICTED, ClaimStatus.MISLEADING_CONTEXT})


def technique_for(
    status: ClaimStatus,
    claim_type: ClaimType,
    evidence: Iterable[tuple[EvidenceKind, Direction]],
) -> Technique | None:
    """The technique a refuted claim shows, or None.

    None for anything not refuted — a technique named on a true or undecided claim
    would call it a manipulation — and for a plain false EVENT. That type is the
    catch-all for a health myth, a scam or a rumour, and "distorted event" taught the
    wrong lesson more often than the right one when the app used to show it.
    """
    if status not in _REFUTED:
        return None

    # An earlier publication of the same picture is the most specific finding there
    # is, so it decides before the claim's type does.
    if claim_type is ClaimType.MEDIA and any(
        kind is EvidenceKind.MEDIA_MATCH and direction is not Direction.SUPPORTS
        for kind, direction in evidence
    ):
        return Technique.RECYCLED_MEDIA

    if status is ClaimStatus.MISLEADING_CONTEXT:
        return Technique.MISSING_CONTEXT

    return {
        ClaimType.QUOTE: Technique.MISATTRIBUTED_QUOTE,
        ClaimType.ATTRIBUTION: Technique.MISATTRIBUTED_QUOTE,
        ClaimType.STATISTIC: Technique.TWISTED_NUMBER,
        ClaimType.IDENTITY: Technique.WRONG_IDENTITY,
    }.get(claim_type)
