"""The one sentence under a verdict never says the opposite of the verdict."""

from __future__ import annotations

import pytest

from app.domain.enums import ClaimStatus, Importance, Verdict
from app.orchestration.summary import case_summary

pytestmark = pytest.mark.unit

TRUE_SENTENCE = "Four outlets report the withdrawal; the claim is true."
UNREPORTED = "We searched official sources and found nothing reporting this."


def test_an_unconfirmed_answer_never_speaks_from_a_confirmed_claim() -> None:
    # The Rs 2000 TV graphic: the event confirmed, "announced today" not.
    claims = [
        (ClaimStatus.SUPPORTED, Importance.HEADLINE, TRUE_SENTENCE),
        (ClaimStatus.UNVERIFIED, Importance.SUPPORTING_DETAIL, UNREPORTED),
    ]
    assert case_summary(Verdict.UNCONFIRMED, claims) == UNREPORTED


def test_with_nothing_unconfirmed_to_quote_it_says_nothing() -> None:
    claims = [
        (ClaimStatus.SUPPORTED, Importance.HEADLINE, TRUE_SENTENCE),
        (ClaimStatus.UNVERIFIED, Importance.SUPPORTING_DETAIL, None),
    ]
    assert case_summary(Verdict.UNCONFIRMED, claims) is None


def test_a_decided_answer_speaks_from_its_most_important_deciding_claim() -> None:
    claims = [
        (ClaimStatus.UNVERIFIED, Importance.HEADLINE, UNREPORTED),
        (ClaimStatus.CONTRADICTED, Importance.SUPPORTING_DETAIL, "PIB says no such scheme."),
    ]
    assert case_summary(Verdict.FALSE, claims) == "PIB says no such scheme."


def test_a_decided_answer_without_its_own_sentence_borrows_none() -> None:
    # "Treat it as likely false" must not appear under a True badge.
    claims = [
        (ClaimStatus.SUPPORTED, Importance.HEADLINE, None),
        (ClaimStatus.UNVERIFIED, Importance.SUPPORTING_DETAIL, UNREPORTED),
    ]
    assert case_summary(Verdict.TRUE, claims) is None
