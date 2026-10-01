"""The correction message (v5, 4.6): what is sent back to the chat.

Held here: a decided verdict always names the source behind it, with its link; an
Unconfirmed result never says "false" and names no source; the source named is the
deciding claim's strongest, not whichever came first; the Hindi message is Hindi
throughout, without the English summary; and the endpoint serves both and refuses
a language it has no template for.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.api.schemas import (
    ClaimResponse,
    EvidenceResponse,
    MatchBasisResponse,
    SourceAnchorResponse,
    StrengthResponse,
    VerifyResponse,
)
from app.orchestration.correction import correction_message
from app.verdict.engine import fabricated_news

PIB = "https://pib.gov.in/factcheck/5000-scheme"
BLOG = "https://example-blog.in/post"
SUMMARY = "No such Rs 5,000 scheme has been announced"


def _evidence(url: str, *, tier: str, direction: str, publisher: str | None) -> EvidenceResponse:
    return EvidenceResponse(
        id=f"ev-{tier}-{direction}",
        tier=tier,
        kind="fact_check",
        direction=direction,
        method="claim_review",
        finding="f",
        citation_url=url,
        snapshot_id="snap",
        source_excerpt="The claim is fake.",
        source_anchor=SourceAnchorResponse(),
        match_basis=MatchBasisResponse(metric="claim_similarity", value=0.8, threshold=0.6),
        match_quality="STRONG",
        publisher=publisher,
    )


def _claim(status: str, importance: str, *evidence: EvidenceResponse) -> ClaimResponse:
    return ClaimResponse(
        id=f"cl-{importance}",
        text="Every woman gets Rs 5,000 a month.",
        claim_type="EVENT",
        status=status,
        severity="HIGH",
        importance=importance,
        reason="r",
        rule_id="r",
        rule_version="v",
        strength=StrengthResponse(score=0.9, band="STRONG", version="v"),
        evidence=evidence,
    )


def _case(verdict: str, *claims: ClaimResponse, summary: str | None = SUMMARY) -> VerifyResponse:
    return VerifyResponse(
        case_id=str(uuid4()),
        verdict=verdict,
        summary=summary,
        action="DO_NOT_SHARE",
        action_reason="r",
        rule_version="v",
        claims=claims,
        retrieved_at=datetime.now(UTC),
    )


FALSE_CASE = _case(
    "FALSE",
    _claim(
        "CONTRADICTED",
        "HEADLINE",
        _evidence(BLOG, tier="D", direction="contradicts", publisher="A blog"),
        _evidence(PIB, tier="C", direction="contradicts", publisher="PIB Fact Check"),
    ),
)


class TestTheMessage:
    def test_a_false_verdict_names_its_source_and_link(self) -> None:
        built = correction_message(FALSE_CASE, "en")
        assert built.message == (
            "Hi! I checked this before forwarding. Factify says it's false: "
            f"{SUMMARY}. PIB Fact Check: {PIB}"
        )
        # The stronger tier is named first, though it was cited second.
        assert built.links == (PIB, BLOG)

    def test_unconfirmed_never_says_false_and_names_no_source(self) -> None:
        case = _case(
            "UNCONFIRMED",
            _claim("UNVERIFIED", "HEADLINE"),
            summary="We could not find reliable sources.",
        )
        for language in ("en", "hi"):
            built = correction_message(case, language)
            assert "false" not in built.message.lower()
            assert "झूठ" not in built.message
            assert built.links == ()

    def test_a_decided_verdict_without_a_source_claims_nothing(self) -> None:
        # The contract refuses a decided claim with no evidence at all; one whose only
        # item is a risk signal has nothing to name. No verdict word travels alone.
        case = _case(
            "FALSE",
            _claim(
                "CONTRADICTED",
                "HEADLINE",
                _evidence(BLOG, tier="D", direction="risk_signal", publisher="A blog"),
            ),
        )
        built = correction_message(case, "en")
        assert "false" not in built.message.lower() and built.links == ()

    def test_a_fabricated_news_picture_is_called_fabricated_not_unconfirmed(self) -> None:
        # rollup.fabricated_unreported: False with nothing published to contradict it.
        case = _case("FALSE", _claim("UNVERIFIED", "HEADLINE"), summary=None).model_copy(
            update={"action_reason": fabricated_news("Lithium found in Antarctica", 17).reason}
        )
        built = correction_message(case, "en")
        assert "likely fabricated" in built.message
        assert "made by AI" in built.message
        assert built.links == ()
        assert "गढ़ी हुई" in correction_message(case, "hi").message

    def test_the_source_comes_from_the_most_important_deciding_claim(self) -> None:
        case = _case(
            "FALSE",
            _claim(
                "CONTRADICTED",
                "SUPPORTING_DETAIL",
                _evidence(BLOG, tier="B", direction="contradicts", publisher="A blog"),
            ),
            _claim(
                "CONTRADICTED",
                "HEADLINE",
                _evidence(PIB, tier="C", direction="contradicts", publisher="PIB Fact Check"),
            ),
        )
        assert correction_message(case, "en").links == (PIB,)

    def test_a_supporting_source_never_carries_a_false_verdict(self) -> None:
        case = _case(
            "FALSE",
            _claim(
                "CONTRADICTED",
                "HEADLINE",
                _evidence(BLOG, tier="B", direction="supports", publisher="A blog"),
                _evidence(PIB, tier="C", direction="contradicts", publisher="PIB Fact Check"),
            ),
        )
        assert correction_message(case, "en").links == (PIB,)

    def test_misleading_and_true_have_their_own_words(self) -> None:
        misleading = _case(
            "MISLEADING",
            _claim(
                "MISLEADING_CONTEXT",
                "HEADLINE",
                _evidence(PIB, tier="C", direction="contextualizes", publisher=None),
            ),
            summary=None,
        )
        built = correction_message(misleading, "en")
        # No publisher stored: the site's own name stands in.
        assert built.message.endswith(f"Factify says it's misleading. pib.gov.in: {PIB}")

        true = _case(
            "TRUE",
            _claim(
                "SUPPORTED",
                "HEADLINE",
                _evidence(PIB, tier="C", direction="supports", publisher="PIB"),
            ),
        )
        assert "Factify says it's true" in correction_message(true, "en").message

    def test_the_hindi_message_is_hindi_throughout(self) -> None:
        built = correction_message(FALSE_CASE, "hi")
        assert built.message.startswith("नमस्ते!")
        assert "झूठ" in built.message
        assert SUMMARY not in built.message  # the English summary stays out
        assert "झूठ है। PIB Fact Check:" in built.message  # a Hindi full stop
        assert built.message.endswith(f"PIB Fact Check: {PIB}")

    def test_only_the_summarys_first_sentence_is_sent(self) -> None:
        case = _case(
            "FALSE",
            *FALSE_CASE.claims,
            summary=(
                "Doctors at Tata Memorial and factcheck.afp.com say there is no such cure. "
                "Other fact-checkers agree. One passage does not address it."
            ),
        )
        message = correction_message(case, "en").message
        assert "no such cure. PIB Fact Check:" in message
        assert "Other fact-checkers" not in message

    def test_a_long_summary_is_cut_at_a_word(self) -> None:
        case = _case(
            "FALSE",
            *FALSE_CASE.claims,
            summary="word " * 120,
        )
        message = correction_message(case, "en").message
        assert "word…" in message and "wor…" not in message


class _Cases:
    def __init__(self, case: VerifyResponse) -> None:
        self.case = case

    async def get(self, case_id: Any) -> VerifyResponse | None:
        return self.case if str(case_id) == self.case.case_id else None


class TestTheEndpoint:
    @pytest.fixture
    def client(self) -> Any:
        from fastapi.testclient import TestClient

        from app.main import create_app

        client = TestClient(create_app())
        client.app.state.case_reader = _Cases(FALSE_CASE)
        return client

    def test_both_languages_are_served(self, client: Any) -> None:
        url = f"/v1/cases/{FALSE_CASE.case_id}/correction-text"
        english = client.post(url, json={"language": "en"})
        assert english.status_code == 200
        assert english.json()["links"] == [PIB, BLOG]
        assert english.json()["message"].startswith("Hi!")

        hindi = client.post(url, json={"language": "hi"})
        assert hindi.status_code == 200 and hindi.json()["message"].startswith("नमस्ते")

    def test_an_unknown_language_or_case_is_refused(self, client: Any) -> None:
        url = f"/v1/cases/{FALSE_CASE.case_id}/correction-text"
        assert client.post(url, json={"language": "fr"}).status_code == 422
        missing = client.post(f"/v1/cases/{uuid4()}/correction-text", json={"language": "en"})
        assert missing.status_code == 404
