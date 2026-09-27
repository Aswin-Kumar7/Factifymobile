"""What our own model may answer about a page: only that it is not about the claim.

`local_reading` returns an outcome only for a page none of whose passages is about the
claim; `None` sends the page to the hosted reader, which answers everything else.

The boundary was measured on 2,390 claim/sentence pairs from past checks
(scripts/eval_models.py stance, 2026-09-28): at a relevance of 0.05 the reranker
keeps 99.5% of the sentences the hosted reader cited as evidence, and passes on
two-thirds of sentences paired with an unrelated claim.

Support was meant to be answered locally too, and was withdrawn on the same
measurement. Where the English NLI model was 97% sure a sentence stated the claim,
the hosted reader had read 12 of 90 as contradicting it; the model saw 8 of 302 of
the hosted reader's contradictions. A reader that confident and that wrong must not
decide, so it does not: every page about the claim is read by the hosted model, as
before, and only the ones about something else are spared the call.
"""

from __future__ import annotations

from typing import Any

LOCAL_MODEL_ID = "local:gte-multilingual-reranker"

# Below this, no passage on the page is about the claim. Keeps 99.5% of cited
# sentences in the measurement above.
IRRELEVANT_BELOW = 0.05


def local_reading(
    stance: Any,
    claim_text: str,
    passages: list[Any],
    title: str | None,
    claim_type: str | None,
) -> Any | None:
    """An empty ReasoningOutcome when no passage is about the claim, else None."""
    from app.sources.reasoning import ReasoningOutcome

    del title, claim_type
    if not passages or not stance.can_gate:
        return None
    relevance = stance.relevance(claim_text, [p.text for p in passages])
    if relevance is None or max(relevance) >= IRRELEVANT_BELOW:
        return None
    return ReasoningOutcome(model_id=LOCAL_MODEL_ID, passages_read=len(passages))


def local_same_claim(stance: Any, claim_text: str, reviewed_text: str) -> bool | None:
    """False when a fact-check's reviewed claim is not about this claim at all;
    otherwise None, and the hosted model is asked."""
    if not stance.can_gate:
        return None
    relevance = stance.relevance(claim_text, [reviewed_text])
    if relevance is not None and relevance[0] < IRRELEVANT_BELOW:
        return False
    return None
