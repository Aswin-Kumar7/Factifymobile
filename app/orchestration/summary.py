"""The one plain sentence that speaks for a whole case.

Shared by the live response and the ledger read-back, so a repeat check shows the
same summary as the first one. Pure selection over claims that already carry their
explanations; nothing here writes one.
"""

from __future__ import annotations

from app.domain.enums import ClaimStatus, Importance, Verdict

# The claim statuses that carry each verdict, for choosing which claim's explanation
# speaks for the whole case.
_STATUS_FOR_VERDICT = {
    Verdict.TRUE: {ClaimStatus.SUPPORTED},
    Verdict.FALSE: {ClaimStatus.CONTRADICTED},
    # What makes it only partly true: the claim that is wrong, or the one sources
    # confirm only in a smaller version.
    Verdict.PARTLY_TRUE: {ClaimStatus.CONTRADICTED, ClaimStatus.MISLEADING_CONTEXT},
    Verdict.MISLEADING: {ClaimStatus.CONTRADICTED, ClaimStatus.MISLEADING_CONTEXT},
}
_IMPORTANCE_RANK = {
    Importance.HEADLINE: 0,
    Importance.MAIN_THESIS: 1,
    Importance.SUPPORTING_DETAIL: 2,
    Importance.BACKGROUND: 3,
}


def case_summary(
    verdict: Verdict, claims: list[tuple[ClaimStatus, Importance, str | None]]
) -> str | None:
    """One plain sentence for the whole case: the explanation of the claim that decided it.

    For a FALSE verdict that is the refuted claim, for TRUE the supported one, and in
    both cases the most important such claim, so the sentence a person reads is about
    what the piece actually asserts. UNCONFIRMED speaks only from a claim that was
    itself left unconfirmed. When no such claim has an explanation there is no
    sentence, and the app says what the verdict means in its own words.

    It used to fall back to any claim with an explanation. A TV graphic passing off
    the 2023 withdrawal of Rs 2000 notes as today's news came back Unconfirmed with
    the sentence written for its one confirmed claim - "Therefore, the claim ... is
    true" - under the grey badge, telling the reader the opposite of the answer.
    """
    deciding = _STATUS_FOR_VERDICT.get(verdict, {ClaimStatus.UNVERIFIED})
    ranked = sorted(claims, key=lambda item: _IMPORTANCE_RANK.get(item[1], 4))
    for claim_status, _, explanation in ranked:
        if explanation and claim_status in deciding:
            return explanation
    return None
