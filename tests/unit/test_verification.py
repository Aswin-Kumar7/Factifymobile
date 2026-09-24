"""Source verification: one citation per page, only sources that take a side, and a
second opinion on whether each is about this claim at all."""

from __future__ import annotations

import asyncio
from typing import Any

from app.domain import Credibility, Direction, EvidenceKind
from app.sources.reasoning import SourceCheck, SourceReading
from app.sources.verification import SourceVerification, dedupe, page_key
from tests.unit.factories import claim, evidence


class _Checker:
    """Answers the source check from a script, and records what it was shown."""

    def __init__(self, readings: dict[int, tuple[bool, str]] | None, explanation: str = "") -> None:
        self._readings = readings
        self._explanation = explanation
        self.shown: list[list[tuple[str, str]]] = []

    async def check_sources(self, claim_text: str, sources: list[tuple[str, str]]) -> Any:
        self.shown.append(sources)
        if self._readings is None:
            return None
        return SourceCheck(
            readings={
                i: SourceReading(addresses_claim=a, verdict=v, reason="r")
                for i, (a, v) in self._readings.items()
            },
            explanation=self._explanation,
        )


class _Ranker:
    def credibility(self, url_or_domain: str | None) -> Credibility:
        return Credibility.HIGH if "apnews" in (url_or_domain or "") else Credibility.MEDIUM


def _run(checker: _Checker, items: list[Any]) -> Any:
    return asyncio.run(
        SourceVerification(checker=checker, ranker=_Ranker()).check(claim(), items)
    )


class TestOneCitationPerPage:
    """Full Fact's 5G page was cited three times for one claim, and crashed the screen."""

    def test_the_same_page_written_differently_is_one_page(self) -> None:
        assert page_key("https://www.fullfact.org/online/coronavirus-5G/") == page_key(
            "http://fullfact.org/online/coronavirus-5G?utm_source=x#top"
        )

    def test_repeats_collapse_to_one(self) -> None:
        url = "https://fullfact.org/online/coronavirus-5G/"
        unique, removed = dedupe([evidence(citation_url=url) for _ in range(3)])

        assert len(unique) == 1
        assert removed == 2

    def test_a_published_fact_check_is_the_copy_kept(self) -> None:
        url = "https://fullfact.org/online/coronavirus-5G/"
        report = evidence(kind=EvidenceKind.CORROBORATION, citation_url=url)
        adjudication = evidence(kind=EvidenceKind.FACT_CHECK, citation_url=url)

        unique, _ = dedupe([report, adjudication])

        assert unique[0].kind is EvidenceKind.FACT_CHECK


class TestOnlySourcesThatTakeASide:
    def test_a_context_source_is_not_cited(self) -> None:
        checker = _Checker({0: (True, "FALSE")})
        items = [
            evidence(direction=Direction.CONTEXTUALIZES, citation_url="https://a.com/1"),
            evidence(direction=Direction.CONTRADICTS, citation_url="https://b.com/2"),
        ]

        result = _run(checker, items)

        assert [e.citation_url for e in result.evidence] == ["https://b.com/2"]
        assert result.context_only == 1
        # And it was never sent to the model: nothing to check on a page that takes
        # no side.
        assert len(checker.shown[0]) == 1


class TestASecondOpinionOnRelevance:
    def test_a_source_that_is_not_about_this_claim_is_dropped(self) -> None:
        """A general page about the subject is not evidence about one specific claim."""
        items = [
            evidence(direction=Direction.SUPPORTS, citation_url="https://scholarships.gov.in"),
            evidence(direction=Direction.SUPPORTS, citation_url="https://apnews.com/x"),
        ]

        result = _run(_Checker({0: (False, "UNCLEAR"), 1: (True, "TRUE")}), items)

        assert [e.citation_url for e in result.evidence] == ["https://apnews.com/x"]
        assert result.rejected == 1

    def test_two_readings_that_disagree_drop_the_source(self) -> None:
        """The reader said it supports, the check says it refutes: the page is ambiguous."""
        items = [evidence(direction=Direction.SUPPORTS, citation_url="https://a.com/1")]

        result = _run(_Checker({0: (True, "FALSE")}), items)

        assert result.evidence == []

    def test_it_never_turns_a_source_to_the_other_side(self) -> None:
        items = [evidence(direction=Direction.CONTRADICTS, citation_url="https://a.com/1")]

        result = _run(_Checker({0: (True, "FALSE")}), items)

        assert result.evidence[0].direction is Direction.CONTRADICTS

    def test_a_source_the_check_did_not_mention_is_not_kept(self) -> None:
        """Silence is not confirmation."""
        items = [
            evidence(direction=Direction.SUPPORTS, citation_url="https://a.com/1"),
            evidence(direction=Direction.SUPPORTS, citation_url="https://b.com/2"),
        ]

        result = _run(_Checker({0: (True, "TRUE")}), items)

        assert [e.citation_url for e in result.evidence] == ["https://a.com/1"]

    def test_the_plain_explanation_is_returned(self) -> None:
        items = [evidence(direction=Direction.CONTRADICTS, citation_url="https://a.com/1")]

        result = _run(_Checker({0: (True, "FALSE")}, "PIB says no such scheme exists."), items)

        assert result.explanation == "PIB says no such scheme exists."


class TestAnOutageDoesNotDeleteEvidence:
    def test_evidence_is_kept_and_the_run_marked_unchecked(self) -> None:
        items = [evidence(direction=Direction.CONTRADICTS, citation_url="https://a.com/1")]

        result = _run(_Checker(None), items)

        assert len(result.evidence) == 1
        assert result.checked is False


class TestCredibilityComesFromTheList:
    def test_every_kept_source_is_weighed(self) -> None:
        items = [
            evidence(direction=Direction.SUPPORTS, citation_url="https://apnews.com/x"),
            evidence(direction=Direction.SUPPORTS, citation_url="https://thehindu.com/y"),
        ]

        result = _run(_Checker({0: (True, "TRUE"), 1: (True, "TRUE")}), items)

        assert [e.credibility for e in result.evidence] == [
            Credibility.HIGH,
            Credibility.MEDIUM,
        ]


class TestMediaFindingsAreNotRejudged:
    def test_a_media_match_passes_through(self) -> None:
        """No passage to read — its resolver already requires a date and a citation."""
        checker = _Checker({})
        items = [
            evidence(
                kind=EvidenceKind.MEDIA_MATCH,
                direction=Direction.CONTRADICTS,
                citation_url="https://archive.example/photo",
            )
        ]

        result = _run(checker, items)

        assert len(result.evidence) == 1
        assert checker.shown == []


class TestAnUncheckedSourceCarriesNoWeight:
    """Credibility is what lets one source decide a claim. Unchecked, it must not."""

    def test_no_credibility_when_the_check_could_not_run(self) -> None:
        items = [evidence(direction=Direction.CONTRADICTS, citation_url="https://apnews.com/1")]

        result = _run(_Checker(None), items)

        assert result.checked is False
        assert result.evidence[0].credibility is None

    def test_a_check_that_runs_out_of_time_counts_as_not_run(self) -> None:
        class _Slow(_Checker):
            async def check_sources(self, claim_text: str, sources: list[tuple[str, str]]) -> Any:
                await asyncio.sleep(5)
                return None

        items = [evidence(direction=Direction.CONTRADICTS, citation_url="https://apnews.com/1")]
        result = asyncio.run(
            SourceVerification(checker=_Slow(None), ranker=_Ranker()).check(
                claim(), items, budget=0.05
            )
        )

        assert result.checked is False
        assert result.evidence[0].credibility is None
