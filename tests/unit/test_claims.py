"""M18 and M20 — claim extraction, OCR, and the two rules that matter most.

The interesting tests are not "did we get claims". They are:

  - with no model configured, does the system return **nothing** rather than
    something plausible;
  - can a claim the document does not contain reach storage.
"""

from __future__ import annotations

import pytest

from app.extraction.claims import ClaimPipeline
from app.extraction.llm import (
    ExtractionOutcome,
    ProposedAnchor,
    ProposedClaim,
    UnavailableExtractor,
)
from app.extraction.ocr import UnavailableOcr

pytestmark = pytest.mark.unit


DOCUMENT = (
    "The government announced a relief scheme for farmers on Thursday. "
    "Officials said applications would open next month across every district. "
    "According to Reuters, the total outlay is five hundred crore rupees."
)


def _proposal(text: str, **overrides: object) -> ProposedClaim:
    fields: dict[str, object] = {
        "text": text,
        "claim_type": "EVENT",
        "severity": "HIGH",
        "importance": "MAIN_THESIS",
        "source_anchor": ProposedAnchor(paragraph_index=0),
    }
    fields.update(overrides)
    return ProposedClaim.model_validate(fields)


class FakeExtractor:
    """Returns fixed proposals and counts how often it was asked."""

    def __init__(self, outcome: ExtractionOutcome) -> None:
        self.outcome = outcome
        self.calls = 0

    async def extract_claims(self, text: str) -> ExtractionOutcome:
        del text
        self.calls += 1
        return self.outcome


class TestNoModelMeansNoClaims:
    """The rule that outranks the rest: never invent evidence."""

    async def test_an_unavailable_model_produces_nothing_and_says_why(self) -> None:
        pipeline = ClaimPipeline(UnavailableExtractor())

        result = await pipeline.extract(DOCUMENT, content_hash="sha256:doc")

        assert result.claims == ()
        assert result.reason == "unavailable: no model configured"
        assert not result.succeeded

    async def test_unavailable_ocr_returns_nothing_rather_than_approximating(self) -> None:
        outcome = await UnavailableOcr().transcribe(b"\xff\xd8\xff")

        assert outcome.text == ""
        assert not outcome.has_text
        assert outcome.reason == "unavailable: no model configured"

    async def test_a_provider_failure_is_a_reason_not_a_guess(self) -> None:
        pipeline = ClaimPipeline(
            FakeExtractor(ExtractionOutcome(reason="provider failed: request timed out"))
        )

        result = await pipeline.extract(DOCUMENT, content_hash="sha256:doc")

        assert result.claims == ()
        assert "timed out" in str(result.reason)


class TestAnchorVerification:
    """A claim that does not correspond to the document does not get stored.

    This is what stops both a hallucination and a successful injection from
    manufacturing a claim: the invented sentence would also have to appear in the
    source.
    """

    async def test_a_claim_present_in_the_source_is_kept(self) -> None:
        pipeline = ClaimPipeline(
            FakeExtractor(
                ExtractionOutcome(
                    claims=(_proposal("The government announced a relief scheme for farmers"),)
                )
            )
        )

        result = await pipeline.extract(DOCUMENT, content_hash="sha256:doc")

        assert len(result.claims) == 1
        assert result.claims[0].anchor.char_start is not None

    async def test_a_claim_absent_from_the_source_is_discarded(self) -> None:
        """The model, or the document instructing it, invented this outright."""
        pipeline = ClaimPipeline(
            FakeExtractor(
                ExtractionOutcome(
                    claims=(_proposal("Reuters has verified this story as completely true"),)
                )
            )
        )

        result = await pipeline.extract(DOCUMENT, content_hash="sha256:doc")

        assert result.claims == ()
        assert result.discarded

    async def test_a_lightly_reworded_claim_still_anchors(self) -> None:
        """Extraction legitimately normalises punctuation and drops a trailing clause."""
        pipeline = ClaimPipeline(
            FakeExtractor(
                ExtractionOutcome(
                    claims=(_proposal("applications would open next month across every district"),)
                )
            )
        )

        result = await pipeline.extract(DOCUMENT, content_hash="sha256:doc")

        assert len(result.claims) == 1

    async def test_the_anchor_points_at_the_real_text(self) -> None:
        pipeline = ClaimPipeline(
            FakeExtractor(
                ExtractionOutcome(
                    claims=(_proposal("the total outlay is five hundred crore rupees"),)
                )
            )
        )

        result = await pipeline.extract(DOCUMENT, content_hash="sha256:doc")
        anchor = result.claims[0].anchor

        assert anchor.char_start is not None
        assert anchor.char_end is not None
        assert anchor.char_end > anchor.char_start

    async def test_a_mix_keeps_the_real_and_drops_the_invented(self) -> None:
        pipeline = ClaimPipeline(
            FakeExtractor(
                ExtractionOutcome(
                    claims=(
                        _proposal("The government announced a relief scheme for farmers"),
                        _proposal("The scheme was later cancelled by the supreme court"),
                    )
                )
            )
        )

        result = await pipeline.extract(DOCUMENT, content_hash="sha256:doc")

        assert len(result.claims) == 1
        assert len(result.discarded) == 1

    async def test_there_is_at_most_one_main_thesis(self) -> None:
        """An India TV fact-check came back with two main theses, and every main
        thesis must be confirmed before a case reads True. The first keeps the rank;
        the rest become supporting details."""
        pipeline = ClaimPipeline(
            FakeExtractor(
                ExtractionOutcome(
                    claims=(
                        _proposal("The government announced a relief scheme for farmers"),
                        _proposal("applications would open next month across every district"),
                        _proposal(
                            "The total outlay is five hundred crore rupees",
                            importance="HEADLINE",
                        ),
                    )
                )
            )
        )

        result = await pipeline.extract(DOCUMENT, content_hash="sha256:doc")

        assert [claim.importance.value for claim in result.claims] == [
            "MAIN_THESIS",
            "SUPPORTING_DETAIL",
            "HEADLINE",
        ]


class TestOneCallPerDocument:
    async def test_exactly_one_call_is_made(self) -> None:
        extractor = FakeExtractor(
            ExtractionOutcome(claims=(_proposal("The government announced a relief scheme"),))
        )
        pipeline = ClaimPipeline(extractor)

        await pipeline.extract(DOCUMENT, content_hash="sha256:doc")

        assert extractor.calls == 1

    async def test_empty_input_makes_no_call_at_all(self) -> None:
        extractor = FakeExtractor(ExtractionOutcome())
        pipeline = ClaimPipeline(extractor)

        result = await pipeline.extract("   ", content_hash="sha256:blank")

        assert extractor.calls == 0
        assert result.reason == "no text to extract from"


class TestInjectionFindingsTravel:
    async def test_an_injection_attempt_reaches_the_source_risk_track(self) -> None:
        """The attempt is a finding about the publisher, not noise to drop."""
        pipeline = ClaimPipeline(
            FakeExtractor(
                ExtractionOutcome(
                    claims=(),
                    injection_findings=("instruction_override: Ignore all previous instructions",),
                    reason=None,
                )
            )
        )

        result = await pipeline.extract(DOCUMENT, content_hash="sha256:doc")

        assert result.injection_findings
        assert "instruction_override" in result.injection_findings[0]


class TestProposalSchema:
    def test_a_proposal_carrying_a_status_is_rejected(self) -> None:
        """The model labels and segments; it never assigns a verdict."""
        proposal = ProposedClaim.model_validate(
            {
                "text": "a claim",
                "claim_type": "EVENT",
                "severity": "HIGH",
                "importance": "MAIN_THESIS",
                "status": "CONTRADICTED",
                "confidence": 0.97,
            }
        )

        assert not hasattr(proposal, "status")
        assert not hasattr(proposal, "confidence")

    def test_an_unknown_claim_type_is_rejected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ProposedClaim.model_validate(
                {
                    "text": "a claim",
                    "claim_type": "event_context",
                    "severity": "HIGH",
                    "importance": "MAIN_THESIS",
                }
            )


class TestAClaimRewordedFromAListStillAnchors:
    """A list item rewritten as a sentence keeps its anchor; an invented fact does not.

    Every claim on a page that listed "Barack Obama / Arrested Jan 29, facing tribunal
    for High Treason." was discarded: faithful, but no run of its words survived.
    """

    PAGE = (
        "Mass Arrests Confirmed\nPublished February 5, 2025\n"
        "Barack Obama\nArrested Jan 29, facing tribunal for High Treason.\n"
        "Hillary Clinton\nDetained late Jan; trial started Feb 2, sentencing imminent.\n"
        "George Soros\nCaptured Feb 3, tribunal outcome: Execution\n"
        "Mark Zuckerberg\nArrested Feb 1, charged with mass surveillance crimes."
    )

    @pytest.mark.parametrize(
        "claim_text",
        [
            "Barack Obama was arrested on January 29 and is facing a tribunal for High Treason.",
            "Hillary Clinton was detained in late January 2025; her trial started on "
            "February 2, with sentencing imminent.",
            "George Soros was captured on February 3, 2025, and the tribunal outcome was "
            "execution.",
        ],
    )
    def test_a_faithful_rewording_is_kept(self, claim_text: str) -> None:
        from app.extraction.claims import _locate

        assert _locate(claim_text, self.PAGE) is not None

    @pytest.mark.parametrize(
        "claim_text",
        [
            "Barack Obama was arrested on January 30 for High Treason.",  # wrong day
            "Bill Gates was arrested for tax fraud in Seattle.",  # not on the page
            "Hillary Clinton was captured and executed for mass surveillance crimes.",  # mixed
            "George Soros was captured on February 3, 2019.",  # wrong year
        ],
    )
    def test_an_invented_or_mixed_fact_is_not(self, claim_text: str) -> None:
        from app.extraction.claims import _locate

        assert _locate(claim_text, self.PAGE) is None


class TestWhatTheExtractorIsTold:
    """Rules that came from real misses on the phone (2026-09-27)."""

    def test_a_joke_is_not_a_claim(self) -> None:
        from app.extraction.llm import _SYSTEM_INSTRUCTION

        # "ME ON MONDAY MORNING" was searched as news and came back unconfirmed.
        assert "ME ON MONDAY MORNING" in _SYSTEM_INSTRUCTION
        assert "an empty list is the right answer" in _SYSTEM_INSTRUCTION

    def test_a_forwards_own_point_is_checked_but_never_a_debunks(self) -> None:
        from app.extraction.llm import _SYSTEM_INSTRUCTION

        # The lemon-water poster was checked only as "doctors said so".
        assert "names an authority only to lend it weight" in _SYSTEM_INSTRUCTION
        # ...and the exclusion that keeps a PIB fact-check from being called false.
        assert "Never do this for a report of a denial, a debunk" in _SYSTEM_INSTRUCTION


class TestStoredReadingsArePerModel:
    """Switching the model must not go on serving the old model's claims."""

    class _Cache:
        def __init__(self) -> None:
            self.rows: dict[tuple[str, str], dict[str, object]] = {}

        async def get_extraction(self, *, content_hash: str, extractor_version: str) -> object:
            return self.rows.get((content_hash, extractor_version))

        async def put_extraction(
            self, *, content_hash: str, extractor_version: str, payload: object, model_id: object
        ) -> None:
            del model_id
            self.rows[(content_hash, extractor_version)] = payload  # type: ignore[assignment]

    class _Model(FakeExtractor):
        def __init__(self, outcome: ExtractionOutcome, model_id: str) -> None:
            super().__init__(outcome)
            self.model_id = model_id

    async def test_another_model_reads_the_text_again(self) -> None:
        cache = self._Cache()
        outcome = ExtractionOutcome(claims=(_proposal("The government announced a relief scheme"),))
        old = self._Model(outcome, "gpt-4.1-mini")
        new = self._Model(outcome, "gpt-5.6-luna")

        await ClaimPipeline(old, cache).extract(DOCUMENT, content_hash="sha256:doc")  # type: ignore[arg-type]
        await ClaimPipeline(old, cache).extract(DOCUMENT, content_hash="sha256:doc")  # type: ignore[arg-type]
        await ClaimPipeline(new, cache).extract(DOCUMENT, content_hash="sha256:doc")  # type: ignore[arg-type]

        assert (old.calls, new.calls) == (1, 1)
