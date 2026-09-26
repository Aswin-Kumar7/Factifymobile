"""Contract 1.3: claim locations, the technique, and the receipt carried inline.

What is held here:

  - a claim's `input_anchor` points back at the claim's own words in what was
    submitted, even when line breaks, double spaces or curly quotes sit inside it;
  - `technique` is never named on a SUPPORTED or UNVERIFIED claim, by the rule or by
    the contract;
  - 1.3 is additive: every 1.2 field is still there, unchanged, and the new ones are
    optional, so a 1.2 client reads a 1.3 answer exactly as it did before;
  - the receipt rides inline when one exists, and a receipt that cannot be read never
    holds the answer back.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.api.schemas import (
    CONTRACT_VERSION,
    ClaimResponse,
    InputAnchorResponse,
    StrengthResponse,
    VerifyResponse,
    claim_anchor_response,
)
from app.api.verify import to_response, with_receipt
from app.domain.claim import ClaimAnchor
from app.domain.enums import (
    Action,
    ClaimStatus,
    ClaimType,
    Direction,
    EvidenceKind,
    Technique,
)
from app.extraction.claims import ClaimPipeline
from app.extraction.llm import ExtractionOutcome, ProposedAnchor, ProposedClaim
from app.orchestration.pipeline import ClaimOutcome, VerificationResult
from app.verdict.engine import CaseDecision, Decision
from app.verdict.strength import evidence_strength
from app.verdict.technique import technique_for
from tests.unit import factories

pytestmark = pytest.mark.unit


def _proposal(text: str) -> ProposedClaim:
    return ProposedClaim.model_validate(
        {
            "text": text,
            "claim_type": "EVENT",
            "severity": "HIGH",
            "importance": "MAIN_THESIS",
            "source_anchor": ProposedAnchor(paragraph_index=0),
        }
    )


class _Extractor:
    def __init__(self, *texts: str) -> None:
        self._claims = tuple(_proposal(text) for text in texts)

    async def extract_claims(self, text: str) -> ExtractionOutcome:
        del text
        return ExtractionOutcome(claims=self._claims)


# ------------------------------------------------------------------- claim locations


class TestClaimLocations:
    """The offsets are into the text as sent, so the app underlines the right words."""

    MESSAGE = (
        "FORWARDED AS RECEIVED!!\n\n"
        "The  government announced a relief scheme\nfor farmers on Thursday.\n"
        "Officials said “applications would open next month” across every district."
    )

    async def _anchored(self, *claims: str) -> list[tuple[str, str]]:
        pipeline = ClaimPipeline(_Extractor(*claims))
        result = await pipeline.extract(self.MESSAGE, content_hash="sha256:msg")
        spans = []
        for claim in result.claims:
            start, end = claim.anchor.char_start, claim.anchor.char_end
            assert start is not None and end is not None
            spans.append((claim.text, self.MESSAGE[start:end]))
        return spans

    async def test_a_claim_spanning_a_line_break_points_at_its_own_words(self) -> None:
        [(_, underlined)] = await self._anchored(
            "The government announced a relief scheme for farmers on Thursday"
        )
        # The span is the sender's text, double space and line break included -
        # before the fix it was shifted by every collapsed space before it.
        assert underlined == ("The  government announced a relief scheme\nfor farmers on Thursday")

    async def test_a_claim_after_curly_quotes_is_not_shifted(self) -> None:
        [(_, underlined)] = await self._anchored(
            'Officials said "applications would open next month"'
        )
        assert underlined == "Officials said “applications would open next month”"

    async def test_every_span_holds_the_claims_words(self) -> None:
        spans = await self._anchored(
            "The government announced a relief scheme for farmers",
            "applications would open next month across every district",
        )
        assert len(spans) == 2
        for claim, underlined in spans:
            # Whole, or - where the text breaks it up, as the quote marks do here -
            # its longest run; never words from elsewhere.
            said = " ".join(underlined.lower().replace("“", "").replace("”", "").split())
            assert len(said.split()) >= 4
            assert said in claim.lower()

    def test_the_response_carries_the_claims_location(self) -> None:
        claim = factories.claim(
            anchor=ClaimAnchor(
                input_kind="text", content_hash="sha256:x", char_start=4, char_end=40
            )
        )
        response = to_response(_result([_outcome(claim, ClaimStatus.UNVERIFIED, [])]))

        assert response.claims[0].input_anchor == InputAnchorResponse(char_start=4, char_end=40)

    def test_an_anchor_with_only_a_paragraph_is_not_sent(self) -> None:
        # Nothing to underline; the app finds the words itself.
        assert claim_anchor_response(factories.claim().anchor) is None
        assert claim_anchor_response({"paragraph_index": 2, "char_start": None}) is None
        assert claim_anchor_response({"char_start": 0, "char_end": 9}) == InputAnchorResponse(
            char_start=0, char_end=9
        )


# ------------------------------------------------------------------------ technique


_EVERY_EVIDENCE = [(kind, direction) for kind in EvidenceKind for direction in Direction]


class TestTechnique:
    @pytest.mark.parametrize("status", [ClaimStatus.SUPPORTED, ClaimStatus.UNVERIFIED])
    @pytest.mark.parametrize("claim_type", list(ClaimType))
    def test_never_named_on_a_supported_or_unconfirmed_claim(
        self, status: ClaimStatus, claim_type: ClaimType
    ) -> None:
        assert technique_for(status, claim_type, _EVERY_EVIDENCE) is None

    def test_the_contract_refuses_one_on_a_supported_claim(self) -> None:
        with pytest.raises(ValueError, match="technique is named only"):
            ClaimResponse(
                id="cl_1",
                text="A claim.",
                claim_type=ClaimType.STATISTIC,
                status=ClaimStatus.UNVERIFIED,
                severity="HIGH",
                importance="MAIN_THESIS",
                reason="r",
                rule_id="r",
                rule_version="v",
                strength=StrengthResponse(score=0, band="none", version="v"),
                technique=Technique.TWISTED_NUMBER,
            )

    @pytest.mark.parametrize(
        ("claim_type", "expected"),
        [
            (ClaimType.QUOTE, Technique.MISATTRIBUTED_QUOTE),
            (ClaimType.ATTRIBUTION, Technique.MISATTRIBUTED_QUOTE),
            (ClaimType.STATISTIC, Technique.TWISTED_NUMBER),
            (ClaimType.IDENTITY, Technique.WRONG_IDENTITY),
            # A plain false event - a myth, a scam - teaches no technique.
            (ClaimType.EVENT, None),
            (ClaimType.MEDIA, None),
        ],
    )
    def test_a_contradicted_claim_is_named_by_its_type(
        self, claim_type: ClaimType, expected: Technique | None
    ) -> None:
        found = technique_for(
            ClaimStatus.CONTRADICTED,
            claim_type,
            [(EvidenceKind.FACT_CHECK, Direction.CONTRADICTS)],
        )
        assert found is expected

    def test_an_earlier_publication_of_the_picture_decides_first(self) -> None:
        for status in (ClaimStatus.CONTRADICTED, ClaimStatus.MISLEADING_CONTEXT):
            found = technique_for(
                status, ClaimType.MEDIA, [(EvidenceKind.MEDIA_MATCH, Direction.CONTRADICTS)]
            )
            assert found is Technique.RECYCLED_MEDIA

    def test_a_match_that_supports_the_picture_is_not_recycling(self) -> None:
        found = technique_for(
            ClaimStatus.MISLEADING_CONTEXT,
            ClaimType.MEDIA,
            [(EvidenceKind.MEDIA_MATCH, Direction.SUPPORTS)],
        )
        assert found is Technique.MISSING_CONTEXT

    def test_misleading_context_otherwise_is_missing_context(self) -> None:
        found = technique_for(
            ClaimStatus.MISLEADING_CONTEXT,
            ClaimType.STATISTIC,
            [(EvidenceKind.CORROBORATION, Direction.CONTEXTUALIZES)],
        )
        assert found is Technique.MISSING_CONTEXT

    def test_the_response_names_it_only_where_the_claim_was_refuted(self) -> None:
        refuted = factories.claim(claim_type=ClaimType.STATISTIC, claim_id="cl_1")
        backed = factories.claim(claim_type=ClaimType.STATISTIC, claim_id="cl_2")
        against = [factories.evidence(claim_id="cl_1")]
        behind = [factories.evidence(claim_id="cl_2", direction=Direction.SUPPORTS)]

        response = to_response(
            _result(
                [
                    _outcome(refuted, ClaimStatus.CONTRADICTED, against),
                    _outcome(backed, ClaimStatus.SUPPORTED, behind),
                ]
            )
        )

        assert response.claims[0].technique is Technique.TWISTED_NUMBER
        assert response.claims[1].technique is None


# ------------------------------------------------------------------ compatibility

# The 1.2 contract, written out so a change to it cannot pass unnoticed.
_CLAIM_1_2 = {
    "id", "text", "claim_type", "status", "severity", "importance", "reason", "rule_id",
    "rule_version", "strength", "evidence", "confidence", "explanation", "search",
    "sources_looked_at",
}  # fmt: skip
_RESULT_1_2 = {
    "case_id", "contract_version", "verdict", "confidence", "summary", "action",
    "action_reason", "rule_version", "claims", "advisories", "source_risk",
    "media_provenance", "recurrence", "skipped", "completeness_note", "image_reading",
    "receipt_url", "retrieved_at", "from_cache", "elapsed_ms",
}  # fmt: skip


class TestAdditiveOnly:
    def test_the_version_is_1_3(self) -> None:
        assert CONTRACT_VERSION == "1.3"

    def test_every_1_2_field_is_kept_and_the_new_ones_are_optional(self) -> None:
        for model, old, new in (
            (ClaimResponse, _CLAIM_1_2, {"input_anchor", "technique"}),
            (VerifyResponse, _RESULT_1_2, {"receipt", "request_id"}),
        ):
            fields = model.model_fields
            assert set(fields) == old | new
            assert all(not fields[name].is_required() for name in new)

    def test_a_1_3_answer_without_the_new_fields_is_the_1_2_answer(self) -> None:
        claim = factories.claim(
            claim_type=ClaimType.QUOTE,
            anchor=ClaimAnchor(
                input_kind="text", content_hash="sha256:x", char_start=0, char_end=12
            ),
        )
        response = to_response(
            _result([_outcome(claim, ClaimStatus.CONTRADICTED, [factories.evidence()])])
        )
        wire = response.model_dump(mode="json")
        assert wire["claims"][0]["technique"] == "MISATTRIBUTED_QUOTE"

        # What a 1.2 client keeps: everything but the three new keys.
        old = {k: v for k, v in wire.items() if k not in {"receipt", "request_id"}}
        old["claims"] = [
            {k: v for k, v in c.items() if k not in {"input_anchor", "technique"}}
            for c in wire["claims"]
        ]
        reread = VerifyResponse.model_validate(old).model_dump(mode="json")
        assert reread.pop("receipt") is None
        assert reread.pop("request_id") is None
        for item in reread["claims"]:
            assert item.pop("input_anchor") is None
            assert item.pop("technique") is None
        assert reread == old


# ------------------------------------------------------------------------ receipt


class _Receipts:
    def __init__(self, payload: dict[str, Any] | None = None, *, fails: bool = False) -> None:
        self.payload = payload
        self.fails = fails
        self.asked: list[UUID] = []

    async def for_case(self, case_id: UUID) -> dict[str, Any] | None:
        self.asked.append(case_id)
        if self.fails:
            raise RuntimeError("database unavailable")
        return self.payload


def _request(receipts: Any) -> Any:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(receipt_reader=receipts)))


class TestReceiptInline:
    ISSUED = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)

    async def test_the_receipt_rides_with_the_answer(self) -> None:
        receipts = _Receipts(
            {"receipt_id": "rcpt_44e09b1f", "verified": True, "issued_at": self.ISSUED}
        )
        response = to_response(_result([]))

        sent = await with_receipt(_request(receipts), response)

        assert receipts.asked == [UUID(response.case_id)]
        assert sent.receipt is not None
        assert sent.receipt.receipt_id == "rcpt_44e09b1f"
        assert sent.receipt.verified is True
        assert sent.receipt.issued_at == self.ISSUED
        assert sent.receipt_url == "/v1/receipts/rcpt_44e09b1f"

    async def test_a_receipt_that_no_longer_verifies_says_so(self) -> None:
        receipts = _Receipts({"receipt_id": "r1", "verified": False, "issued_at": self.ISSUED})
        sent = await with_receipt(_request(receipts), to_response(_result([])))
        assert sent.receipt is not None and sent.receipt.verified is False

    async def test_no_receipt_and_an_unreadable_one_leave_the_answer_as_it_is(self) -> None:
        response = to_response(_result([]))
        for receipts in (None, _Receipts(None), _Receipts(fails=True)):
            assert await with_receipt(_request(receipts), response) == response


# --------------------------------------------------------------------------- helpers


def _outcome(claim: Any, status: ClaimStatus, evidence: list[Any]) -> ClaimOutcome:
    return ClaimOutcome(
        claim=claim,
        decision=Decision(
            status=status,
            rule_id="r",
            reason="because",
            supporting_evidence_ids=tuple(item.id for item in evidence),
            confidence=80 if status.is_decisive else None,
        ),
        strength=evidence_strength(evidence),
        evidence=evidence,
    )


def _result(claims: list[ClaimOutcome]) -> VerificationResult:
    return VerificationResult(
        case_id=uuid4(),
        content_hash="sha256:demo",
        action=Action.SEND_TO_REVIEW,
        case_decision=CaseDecision(action=Action.SEND_TO_REVIEW, rule_id="r", reason="because"),
        claims=claims,
    )
