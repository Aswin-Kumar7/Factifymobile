"""M27–M32 — evidence retrieval.

The tests that matter here are the ones about restraint: what each resolver refuses
to conclude, and why.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.domain.enums import ClaimType, CoverageExpectation, Relation, SourceRisk
from app.governor.governor import ProviderUnavailable, SkipReason
from app.knowledge.clustering import OriginClusterer
from app.security.fetcher import FetchResult
from app.sources.attribution import find_cited_sources
from app.sources.base import (
    SourceCandidate,
    SourceRelation,
    SourceSnapshot,
    insufficient,
    keyword_overlap,
    locate_excerpt,
)
from app.sources.corroboration import (
    CorroborationResolver,
    silence_is_meaningful,
    within_developing_window,
)
from app.sources.credibility import SourceCredibility
from app.sources.factcheck import (
    FactCheckRecord,
    FactCheckResolver,
    parse_rating_from_title,
)
from app.sources.reasoning import (
    _SYSTEM_INSTRUCTION,
    Passage,
    PassageReasoner,
    ReasoningOutcome,
    _ReasoningResponse,
    select_passages,
    verify_quote,
)
from app.sources.risk import (
    SourceRiskProfiler,
    assess_domain_age,
    assess_transparency,
    detect_typosquat,
    injection_signal,
)
from app.sources.temporal import DatedInstance, TemporalResolver, oldest_instance
from app.sources.websearch import WebSearchResolver
from tests.unit.factories import claim

pytestmark = pytest.mark.unit

CREDIBLE = frozenset({"thehindu.com", "indianexpress.com", "ndtv.com", "altnews.in"})


class TestRelationContract:
    """A relation with no quoted text is an opinion about a page, not a finding."""

    def test_a_decisive_relation_without_an_excerpt_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="without an excerpt"):
            SourceRelation(
                relation=Relation.SUPPORTS, validator="v", validator_version="1", excerpt=""
            )

    def test_insufficient_may_have_no_excerpt(self) -> None:
        """The one relation that claims nothing, so it needs to quote nothing."""
        relation = insufficient("v", "1", "source unreachable")

        assert relation.relation is Relation.INSUFFICIENT
        assert not relation.is_citable
        assert relation.metric == "source unreachable"


class TestExcerptLocation:
    def test_a_present_phrase_is_located_with_offsets(self) -> None:
        excerpt, anchor = locate_excerpt(
            "The minister said the scheme would cover every district.", "the scheme would cover"
        )

        assert "scheme would cover" in excerpt
        assert anchor["char_end"] > anchor["char_start"]

    def test_an_absent_phrase_yields_nothing(self) -> None:
        """Callers turn this into INSUFFICIENT. A resolver must never invent a quote."""
        excerpt, anchor = locate_excerpt("A short article body.", "a sentence that is not there")

        assert excerpt == ""
        assert anchor == {}


class TestFactCheck:
    def _resolver(self, **overrides: object) -> FactCheckResolver:
        record = FactCheckRecord(
            claim_text="Government announces five thousand rupee monthly allowance for all farmers",
            normalized_text="government announces five thousand rupee monthly allowance farmers",
            url="https://www.altnews.in/fact-check-farmer-allowance/",
            rating="False",
            publisher="Alt News",
            published_at=datetime(2026, 6, 2, tzinfo=UTC),
            retrieved_at=datetime(2026, 8, 16, tzinfo=UTC),
        )
        return FactCheckResolver(records=[record], **overrides)  # type: ignore[arg-type]

    async def test_a_known_claim_resolves_with_citation_publisher_and_rating(self) -> None:
        """**The M27 gate**, and note the external API is not configured here.

        The record came from a fact-checker's own feed, retrieved live and persisted.
        """
        resolver = self._resolver(api_available=False)
        subject = claim(
            text="Government announces five thousand rupee monthly allowance for all farmers"
        )

        candidates = await resolver.candidates(subject)
        assert candidates

        snapshot = await resolver.snapshot(candidates[0])
        assert snapshot is not None

        relation = await resolver.relate(subject, snapshot)

        assert relation.relation is Relation.CONTRADICTS
        assert relation.is_citable
        assert "Alt News" in relation.excerpt
        assert "False" in relation.excerpt
        assert snapshot.url.startswith("https://www.altnews.in/")

    async def test_a_fact_check_about_a_different_claim_is_not_cited(self) -> None:
        """Citing it would attribute a verdict its author never gave."""
        resolver = self._resolver()
        subject = claim(text="The metro will run a reduced weekend service in Delhi")

        assert await resolver.candidates(subject) == []

    async def test_an_unrecognised_rating_produces_nothing(self) -> None:
        resolver = FactCheckResolver(
            records=[
                FactCheckRecord(
                    claim_text="A claim about a scheme for farmers announced by government",
                    normalized_text="claim scheme farmers government",
                    url="https://example.org/fc",
                    rating="Needs Context",
                    publisher="Someone",
                )
            ]
        )
        subject = claim(text="A claim about a scheme for farmers announced by government")

        candidates = await resolver.candidates(subject)
        snapshot = await resolver.snapshot(candidates[0])
        assert snapshot is not None

        relation = await resolver.relate(subject, snapshot)

        assert relation.relation is Relation.INSUFFICIENT
        assert "not one we interpret" in relation.metric

    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("Fact Check: This viral video is fake", "fake"),
            ("No, the government did not announce this — the claim is false", "false"),
            ("फैक्ट चेक: यह दावा फर्जी है", "फर्जी"),
            ("This image is misleading", "misleading"),
        ],
    )
    def test_ratings_are_read_from_headlines(self, title: str, expected: str) -> None:
        """Indian fact-checkers write the verdict into the headline; their RSS
        carries no ClaimReview markup, so that is where the rating lives."""
        assert parse_rating_from_title(title) == expected

    def test_a_headline_with_no_verdict_yields_none(self) -> None:
        assert parse_rating_from_title("Weekly roundup of things we checked") is None


class TestAttribution:
    @pytest.mark.parametrize(
        "text",
        [
            "According to Reuters, the total outlay is five hundred crore.",
            "As reported by the Times of India, applications open next month.",
            "In a circular by the Reserve Bank, the rule was changed.",
        ],
    )
    def test_cited_authorities_are_extracted(self, text: str) -> None:
        assert find_cited_sources(text)

    def test_a_claim_citing_nobody_yields_nothing(self) -> None:
        """A missed attribution costs one unrun check; a hallucinated one would send
        us to fetch a source the article never mentioned."""
        assert find_cited_sources("The scheme opens next month across every district.") == ()


class TestCorroboration:
    def _resolver(self) -> CorroborationResolver:
        return CorroborationResolver(clusterer=OriginClusterer())

    def test_enough_independent_origins_supports(self) -> None:
        clusterer = OriginClusterer()
        for index in range(3):
            clusterer.assign(
                document_id=f"d{index}",
                text=f"Independent report number {index} with entirely distinct wording here",
                publisher=f"Outlet {index}",
            )
        resolver = CorroborationResolver(clusterer=clusterer)

        result = resolver.assess(
            claim(), matching_document_ids=["d0", "d1", "d2"], corpus_size=5000
        )

        assert result.relation is Relation.SUPPORTS
        assert result.count.origins == 3

    def test_one_origin_abstains_rather_than_supporting(self) -> None:
        """One outlet reporting something is a source, not a corroboration."""
        clusterer = OriginClusterer()
        clusterer.assign(document_id="d0", text="A single report", publisher="Outlet")
        resolver = CorroborationResolver(clusterer=clusterer)

        result = resolver.assess(claim(), matching_document_ids=["d0"], corpus_size=5000)

        assert result.relation is Relation.INSUFFICIENT

    def test_one_origin_never_contradicts(self) -> None:
        """Thin coverage is not evidence against a claim."""
        clusterer = OriginClusterer()
        clusterer.assign(document_id="d0", text="A single report", publisher="Outlet")
        resolver = CorroborationResolver(clusterer=clusterer)

        result = resolver.assess(claim(), matching_document_ids=["d0"], corpus_size=5000)

        assert result.relation is not Relation.CONTRADICTS


class TestSilence:
    """Absence is evidence only when coverage was expected."""

    def test_a_high_expectation_claim_absent_from_a_large_corpus_is_meaningful(self) -> None:
        meaningful, why = silence_is_meaningful(
            claim(coverage_expectation=CoverageExpectation.HIGH),
            corpus_size=5000,
            developing=False,
        )

        assert meaningful
        assert "widely reported" in why

    def test_a_local_claim_absent_from_national_feeds_means_nothing(self) -> None:
        """Treating this as suspicious would penalise exactly the local reporting
        that has no national footprint."""
        meaningful, why = silence_is_meaningful(
            claim(coverage_expectation=CoverageExpectation.LOCAL),
            corpus_size=5000,
            developing=False,
        )

        assert not meaningful
        assert "need not appear" in why

    def test_silence_means_nothing_with_a_thin_corpus(self) -> None:
        """With little ingested, absence says more about us than about the claim."""
        meaningful, why = silence_is_meaningful(
            claim(coverage_expectation=CoverageExpectation.HIGH),
            corpus_size=10,
            developing=False,
        )

        assert not meaningful
        assert "corpus too small" in why

    def test_silence_means_nothing_inside_the_developing_window(self) -> None:
        meaningful, _ = silence_is_meaningful(
            claim(coverage_expectation=CoverageExpectation.HIGH),
            corpus_size=5000,
            developing=True,
        )

        assert not meaningful

    def test_an_unassessed_expectation_does_not_make_silence_meaningful(self) -> None:
        meaningful, _ = silence_is_meaningful(
            claim(coverage_expectation=None), corpus_size=5000, developing=False
        )

        assert not meaningful

    def test_meaningful_silence_becomes_negative_evidence(self) -> None:
        resolver = CorroborationResolver(clusterer=OriginClusterer())

        result = resolver.assess(
            claim(coverage_expectation=CoverageExpectation.HIGH),
            matching_document_ids=[],
            corpus_size=5000,
        )

        assert result.relation is Relation.CONTRADICTS
        assert result.is_negative_evidence


class TestDevelopingWindow:
    def test_a_very_recent_event_is_inside_the_window(self) -> None:
        now = datetime(2026, 8, 16, 12, tzinfo=UTC)

        assert within_developing_window(now - timedelta(minutes=30), now=now)

    def test_an_older_event_is_outside_it(self) -> None:
        now = datetime(2026, 8, 16, 12, tzinfo=UTC)

        assert not within_developing_window(now - timedelta(days=3), now=now)

    def test_a_claim_with_no_asserted_time_is_not_developing(self) -> None:
        assert not within_developing_window(None)

    def test_silence_inside_the_window_never_contradicts(self) -> None:
        """This is how a system avoids embarrassing itself on a true breaking story."""
        now = datetime(2026, 8, 16, 12, tzinfo=UTC)
        resolver = CorroborationResolver(clusterer=OriginClusterer())

        result = resolver.assess(
            claim(coverage_expectation=CoverageExpectation.HIGH),
            matching_document_ids=[],
            corpus_size=5000,
            asserted_at=now - timedelta(minutes=20),
            now=now,
        )

        assert result.relation is not Relation.CONTRADICTS
        assert result.within_developing_window


class TestTemporal:
    def _instance(self, year: int, *, archive: bool = False) -> DatedInstance:
        return DatedInstance(
            url=f"https://example.org/{year}",
            published_at=datetime(year, 3, 14, tzinfo=UTC),
            publisher="Example",
            method="archive_capture" if archive else "matched_page_date",
        )

    def test_content_older_than_asserted_contradicts(self) -> None:
        """The flagship finding: real image, wrong date."""
        finding = TemporalResolver().assess(
            asserted_at=datetime(2026, 8, 16, tzinfo=UTC), instances=[self._instance(2019)]
        )

        assert finding.relation is Relation.CONTRADICTS
        assert finding.is_recycled
        assert "year(s) earlier" in finding.gap_description
        assert "14 March 2019" in finding.reason

    def test_a_consistent_date_supports(self) -> None:
        finding = TemporalResolver().assess(
            asserted_at=datetime(2026, 3, 20, tzinfo=UTC), instances=[self._instance(2026)]
        )

        assert finding.relation is Relation.SUPPORTS

    def test_a_small_gap_is_not_a_finding(self) -> None:
        """A day covers timezone skew and late-evening publication."""
        finding = TemporalResolver().assess(
            asserted_at=datetime(2026, 3, 15, tzinfo=UTC), instances=[self._instance(2026)]
        )

        assert finding.relation is Relation.SUPPORTS

    def test_no_instances_abstains(self) -> None:
        finding = TemporalResolver().assess(asserted_at=datetime.now(UTC), instances=[])

        assert finding.relation is Relation.INSUFFICIENT

    def test_an_archive_capture_wins_a_tie(self) -> None:
        """A third-party capture is a timestamp the publisher could not edit."""
        same_day = [self._instance(2019), self._instance(2019, archive=True)]

        assert oldest_instance(same_day) is not None
        assert oldest_instance(same_day).is_archive_confirmed  # type: ignore[union-attr]

    def test_the_flagship_case_resolves_with_the_archive_disabled(self) -> None:
        """An archive outage on demo day must cost a confirmation, not the finding."""
        resolver = TemporalResolver(archive_enabled=False)

        finding = resolver.assess(
            asserted_at=datetime(2026, 8, 16, tzinfo=UTC), instances=[self._instance(2019)]
        )

        assert finding.relation is Relation.CONTRADICTS
        assert not resolver.needs_archive_confirmation(finding)

    def test_the_archive_is_consulted_only_for_a_borderline_gap(self) -> None:
        resolver = TemporalResolver(archive_enabled=True)

        borderline = resolver.assess(
            asserted_at=datetime(2026, 6, 1, tzinfo=UTC), instances=[self._instance(2026)]
        )
        egregious = resolver.assess(
            asserted_at=datetime(2026, 8, 16, tzinfo=UTC), instances=[self._instance(2019)]
        )

        assert resolver.needs_archive_confirmation(borderline)
        assert not resolver.needs_archive_confirmation(egregious)


class TestSourceRisk:
    def test_a_typosquat_is_detected(self) -> None:
        signal = detect_typosquat("thehindu.co.in", CREDIBLE)

        assert signal is not None
        assert signal.is_strong

    def test_a_credible_domain_is_not_flagged(self) -> None:
        assert detect_typosquat("indianexpress.com", CREDIBLE) is None

    def test_an_unrelated_domain_is_not_flagged(self) -> None:
        assert detect_typosquat("someblog.example", CREDIBLE) is None

    def test_a_very_young_domain_is_noted(self) -> None:
        now = datetime(2026, 8, 16, tzinfo=UTC)

        signal = assess_domain_age(now - timedelta(days=20), now=now)

        assert signal is not None
        assert "20 days ago" in signal.finding

    def test_an_established_domain_is_not_noted(self) -> None:
        now = datetime(2026, 8, 16, tzinfo=UTC)

        assert assess_domain_age(now - timedelta(days=4000), now=now) is None

    def test_missing_transparency_features_are_itemised(self) -> None:
        signals = assess_transparency("<html><body><p>An article.</p></body></html>")

        assert {signal.kind for signal in signals} == {"no_contact", "no_byline"}

    def test_a_transparent_site_produces_no_signals(self) -> None:
        html = "<a href='/about-us'>About Us</a><span>By Rahul Sharma</span>"

        assert assess_transparency(html) == ()

    def test_an_injection_attempt_is_a_strong_signal(self) -> None:
        """The one risk signal with no innocent explanation."""
        signal = injection_signal(("instruction_override: ignore all previous",))

        assert signal is not None
        assert signal.is_strong
        assert "hidden instructions" in signal.finding

    def test_risk_is_itemised_not_scored(self) -> None:
        """A reader sees checkable observations, not a number with no author."""
        profiler = SourceRiskProfiler(credible_domains=CREDIBLE)
        now = datetime(2026, 8, 16, tzinfo=UTC)

        profile = profiler.profile(
            "https://thehindu.co.in/story",
            html="<html><body><p>x</p></body></html>",
            registered_at=now - timedelta(days=15),
            now=now,
        )

        assert profile.level is SourceRisk.HIGH
        assert len(profile.findings) >= 3
        assert all(isinstance(finding, str) and finding for finding in profile.findings)

    def test_an_unassessed_publisher_is_unknown_not_low(self) -> None:
        profiler = SourceRiskProfiler(credible_domains=CREDIBLE)

        assert profiler.profile("https://example.org/x").level is SourceRisk.UNKNOWN

    def test_a_profile_carries_no_claim_information(self) -> None:
        """Source risk describes a publisher and never touches the claim track."""
        profiler = SourceRiskProfiler(credible_domains=CREDIBLE)

        profile = profiler.profile("https://example.org/x", html="<p>hi</p>")

        assert not hasattr(profile, "claim")
        assert not hasattr(profile, "status")


class TestKeywordOverlap:
    def test_a_source_carrying_the_claim_scores_high(self) -> None:
        overlap = keyword_overlap(
            "The government announced a relief scheme for farmers",
            "In New Delhi the government announced a relief scheme benefiting farmers.",
        )

        assert overlap > 0.8

    def test_an_unrelated_source_scores_low(self) -> None:
        overlap = keyword_overlap(
            "The government announced a relief scheme for farmers",
            "Metro services will run on a reduced schedule this weekend.",
        )

        assert overlap < 0.2


class TestFactCheckRelevanceIsRead:
    """A borderline adjudication is read before its rating is applied.

    Embeddings carry the subject far more than the predicate, so a check of
    "Chandrayaan sent footage of Earth" scores 0.63 against the true claim
    "Chandrayaan landed near the south pole" — close enough to pass a gate, and its
    False rating turned a true statement into DO_NOT_SHARE in a live run.

    What is asked is equivalence, not support. Asked as support, a Snopes check of
    whose ceasefire deal it was came back yes for the claim that a ceasefire happened
    — the reviewed claim takes the agreement for granted — and carried a False rating
    onto a true statement.
    """

    @staticmethod
    def _record() -> FactCheckRecord:
        return FactCheckRecord(
            claim_text="India's lunar spacecraft Chandrayaan 3 sent footage of Earth",
            normalized_text="india's lunar spacecraft chandrayaan 3 sent footage of earth",
            url="https://factcheck.afp.com/doc.afp.com.33TA7C4",
            rating="False",
            publisher="AFP Fact Check",
        )

    @staticmethod
    def _resolver(reasoner: object | None) -> FactCheckResolver:
        return FactCheckResolver(records=[], reasoner=reasoner)  # type: ignore[arg-type]

    class _Reader:
        """Answers the one question `_addresses` asks."""

        def __init__(self, verdict: bool | None) -> None:
            self._verdict = verdict
            self.calls = 0
            self.asked: tuple[str, str] | None = None

        async def same_claim(self, claim_text: str, reviewed_text: str) -> bool | None:
            self.calls += 1
            self.asked = (claim_text, reviewed_text)
            return self._verdict

    @pytest.mark.anyio
    async def test_a_different_claim_rejects_the_rating(self) -> None:
        reader = self._Reader(False)

        assert not await self._resolver(reader)._addresses(claim(), self._record())
        assert reader.calls == 1

    @pytest.mark.anyio
    async def test_the_same_claim_accepts_it(self) -> None:
        assert await self._resolver(self._Reader(True))._addresses(claim(), self._record())

    @pytest.mark.anyio
    async def test_both_statements_are_put_to_the_reader(self) -> None:
        """The comparison is of the two claims, and the rating is deliberately not
        named: "rated this False" asks whether you agree with a verdict, when the
        question is whether the verdict is even about this."""
        reader = self._Reader(True)

        await self._resolver(reader)._addresses(claim(), self._record())

        asked = reader.asked
        assert asked is not None
        assert asked[0] == claim().text
        assert asked[1] == self._record().claim_text
        assert "False" not in asked[1]

    @pytest.mark.anyio
    async def test_without_a_reader_the_score_decides_alone(self) -> None:
        """Degrades open: refusing everything would disable the strongest evidence
        class whenever no model is configured, rather than loosening one check."""
        assert await self._resolver(None)._addresses(claim(), self._record())

    @pytest.mark.anyio
    async def test_a_reader_outage_does_not_drop_the_evidence(self) -> None:
        """`None` is "could not ask", which must not read as "no"."""
        assert await self._resolver(self._Reader(None))._addresses(claim(), self._record())


class TestTheReaderIsToldWhatItIsReading:
    """A paragraph read in isolation cannot tell a debunk from an endorsement.

    "Myth: drinking cow urine cures COVID-19" is the same sentence whether the page
    sells the cure or refutes it, and in a live run a Mayo Clinic page and an NDTV
    page were each read as *supporting* the claim they exist to demolish. The
    headline is the signal that settles it, so the reader is given it — as context
    only, never as something it may quote.
    """

    @staticmethod
    def _passages() -> list[Passage]:
        return [Passage(index=0, text="Myth: cow urine cures COVID-19.", char_start=0, char_end=31)]

    def test_the_headline_reaches_the_prompt(self) -> None:
        rendered = PassageReasoner._render(
            None,  # type: ignore[arg-type]
            "cow urine cures COVID-19",
            self._passages(),
            "Fact check: cow urine does not cure COVID-19",
        )
        assert "ARTICLE TITLE: Fact check: cow urine does not cure COVID-19" in rendered

    def test_a_source_with_no_headline_renders_no_title_line(self) -> None:
        """An empty title must not become an empty label the model has to interpret."""
        rendered = PassageReasoner._render(
            None,  # type: ignore[arg-type]
            "cow urine cures COVID-19",
            self._passages(),
            "   ",
        )
        assert "ARTICLE TITLE" not in rendered

    def test_the_instruction_forbids_reading_a_restatement_as_support(self) -> None:
        """The rule the live misreads needed; stated, so its removal is a visible change."""
        assert "Restating a claim is not asserting it" in _SYSTEM_INSTRUCTION
        assert "never SUPPORTS" in _SYSTEM_INSTRUCTION

    @pytest.mark.anyio
    async def test_the_web_reader_passes_the_pages_own_title(self) -> None:
        """Threading it through the resolver is the half that is easy to forget."""
        seen: dict[str, object] = {}

        class _Reader:
            reads_sources = True

            async def judge(
                self,
                claim_text: str,
                passages: list[object],
                *,
                title: str | None = None,
                language: object | None = None,
                claim_type: str | None = None,
            ) -> ReasoningOutcome:
                seen["title"] = title
                seen["claim_type"] = claim_type
                return ReasoningOutcome(judgements=(), passages_read=len(passages))

        resolver = WebSearchResolver(
            fetcher=None,  # type: ignore[arg-type]
            reasoner=_Reader(),  # type: ignore[arg-type]
            provider="tavily",
            endpoint="https://example.invalid/search",
            api_key="k",
        )
        snapshot = SourceSnapshot(
            id="s1",
            url="https://www.mayoclinic.org/myths",
            final_url="https://www.mayoclinic.org/myths",
            content_hash="sha256:1",
            fetched_at=datetime.now(UTC),
            text="Myth: cow urine cures COVID-19. " + "There is no evidence for this. " * 8,
            title="COVID-19 myths debunked",
        )

        await resolver.relate(claim(), snapshot)

        assert seen["title"] == "COVID-19 myths debunked"


class TestSupportMustBeTheArticlesOwnVoice:
    """Three live misreads shared one shape, and the prompt could not stop them.

    CIDRAP describing "implausible conspiracy beliefs such as the idea that vaccines
    contained microchips", a PMC survey listing bleach-drinking among "highly
    dangerous practices", and NDTV reporting an MP's claim that cow urine cures
    COVID — each came back as SUPPORTS for the claim it was describing, because the
    passage really does contain the sentence. The model answers "who asserts this"
    correctly even when it gets the relation wrong, so the answer is enforced here.
    """

    @staticmethod
    def _response(relation: str, asserted_by: str) -> _ReasoningResponse:
        return _ReasoningResponse.model_validate(
            {
                "judgements": [
                    {
                        "passage_index": 0,
                        "relation": relation,
                        "asserted_by": asserted_by,
                        "quote": "vaccines contained microchips that could track people",
                        "reason": "r",
                        "relevance": 0.9,
                    }
                ]
            }
        )

    @staticmethod
    def _passages() -> list[Passage]:
        text = (
            "The second, smaller group adhered to implausible conspiracy beliefs such as "
            "the idea that vaccines contained microchips that could track people."
        )
        return [Passage(index=0, text=text, char_start=0, char_end=len(text))]

    def _judge(self, relation: str, asserted_by: str) -> ReasoningOutcome:
        reasoner = PassageReasoner.__new__(PassageReasoner)
        reasoner._model_id = "test"
        return reasoner._verify(self._response(relation, asserted_by), self._passages())

    def test_a_claim_the_article_only_reports_is_context_not_support(self) -> None:
        outcome = self._judge("SUPPORTS", "SOMEONE_ELSE")

        assert outcome.judgements[0].relation is Relation.CONTEXTUALIZES

    def test_a_claim_nobody_asserts_is_not_support_either(self) -> None:
        outcome = self._judge("SUPPORTS", "NOBODY")

        assert outcome.judgements[0].relation is Relation.CONTEXTUALIZES

    def test_the_articles_own_assertion_still_supports(self) -> None:
        """The rule must not make support unreachable — only unearned support."""
        outcome = self._judge("SUPPORTS", "THE_ARTICLE")

        assert outcome.judgements[0].relation is Relation.SUPPORTS

    def test_a_contradiction_is_untouched_by_who_said_it(self) -> None:
        """A denial reported as a denial is still a contradiction, as the prompt says,
        and the asymmetry is deliberate: the cautious direction is not clearing."""
        outcome = self._judge("CONTRADICTS", "SOMEONE_ELSE")

        assert outcome.judgements[0].relation is Relation.CONTRADICTS

    def test_an_older_response_without_the_field_is_read_as_the_articles_voice(self) -> None:
        """The field defaults rather than failing validation: a provider that drops an
        enum must degrade to the previous behaviour, not to no evidence at all."""
        response = _ReasoningResponse.model_validate(
            {
                "judgements": [
                    {
                        "passage_index": 0,
                        "relation": "SUPPORTS",
                        "quote": "vaccines contained microchips that could track people",
                        "reason": "r",
                        "relevance": 0.9,
                    }
                ]
            }
        )
        reasoner = PassageReasoner.__new__(PassageReasoner)
        reasoner._model_id = "test"

        outcome = reasoner._verify(response, self._passages())

        assert outcome.judgements[0].relation is Relation.SUPPORTS


class TestContradictionMustBeAboutThisClaim:
    """ "A giant tsunami hit Mumbai last week" came back CONTRADICTED.

    The three contradicting citations were NOAA on the 2004 Indian Ocean tsunami,
    Wikipedia on Krakatoa, and a report of an earthquake in Flores. The claim is
    merely absent from all of them, and rule 4 has always said absence of mention is
    not contradiction. Blocking an invented disaster looks like the right answer,
    which is exactly what makes it dangerous — the same mechanism blocks a true
    report of a breaking event, which nothing in the corpus mentions yet either.
    """

    @staticmethod
    def _passages() -> list[Passage]:
        text = (
            "The tsunami that followed killed more people than any other tsunami in "
            "recorded history, with 227,898 dead or missing across the Indian Ocean."
        )
        return [Passage(index=0, text=text, char_start=0, char_end=len(text))]

    def _judge(self, basis: str) -> ReasoningOutcome:
        response = _ReasoningResponse.model_validate(
            {
                "judgements": [
                    {
                        "passage_index": 0,
                        "relation": "CONTRADICTS",
                        "contradiction_basis": basis,
                        "quote": "with 227,898 dead or missing across the Indian Ocean",
                        "reason": "r",
                        "relevance": 0.8,
                    }
                ]
            }
        )
        reasoner = PassageReasoner.__new__(PassageReasoner)
        reasoner._model_id = "test"
        return reasoner._verify(response, self._passages())

    def test_a_passage_about_another_event_is_not_evidence_at_all(self) -> None:
        """Dropped rather than demoted: a different disaster is not context either."""
        assert self._judge("DIFFERENT_SUBJECT").judgements == ()

    def test_a_passage_answering_another_question_is_not_evidence_at_all(self) -> None:
        """Same topic, different question: dropped, like a different event.

        "Drinking cow urine cures cancer according to doctors" came back CONTRADICTED
        on a Full Fact page about whether the Cancer Act 1939 forbids doctors from
        discussing cures. Both are about doctors and cancer cures; neither says
        anything about cow urine. The reader's own reason gave it away — it had the
        passage "indirectly contradicting" the claim, which is to say not
        contradicting it.
        """
        assert self._judge("DIFFERENT_QUESTION").judgements == ()

    def test_a_study_with_no_result_is_context_not_contradiction(self) -> None:
        """On the subject, settling nothing: demoted rather than dropped.

        The other citation behind that same verdict was a PMC methods sentence —
        cow urine filtrate "was evaluated for antiproliferative and proapoptotic
        effects" in two breast-cancer cell lines. That says what was tested, never
        what was found. It is genuinely about the claim, so a reader should see it;
        it is not a refutation, so it must not be counted as one.
        """
        outcome = self._judge("NO_OUTCOME_STATED")

        assert outcome.judgements[0].relation is Relation.CONTEXTUALIZES

    def test_an_explicit_denial_still_contradicts(self) -> None:
        assert self._judge("DENIES").judgements[0].relation is Relation.CONTRADICTS

    def test_an_incompatible_fact_still_contradicts(self) -> None:
        assert self._judge("INCOMPATIBLE").judgements[0].relation is Relation.CONTRADICTS

    def test_a_missing_basis_keeps_the_contradiction(self) -> None:
        """A provider that drops the field degrades to the previous behaviour."""
        response = _ReasoningResponse.model_validate(
            {
                "judgements": [
                    {
                        "passage_index": 0,
                        "relation": "CONTRADICTS",
                        "quote": "with 227,898 dead or missing across the Indian Ocean",
                        "reason": "r",
                        "relevance": 0.8,
                    }
                ]
            }
        )
        reasoner = PassageReasoner.__new__(PassageReasoner)
        reasoner._model_id = "test"

        outcome = reasoner._verify(response, self._passages())

        assert outcome.judgements[0].relation is Relation.CONTRADICTS


class TestPassagesAreRankedNotTruncated:
    """The reader used to get `passages[:8]` — the *top* of the page.

    Measured on a real article retrieved for "garlic prevents COVID": passage 0 was the
    masthead logo, 1 a photo credit, 2 a "for more coronavirus coverage" line, 3 an
    unrelated market update. The evidence started at index 4. Reading whole pages
    without ranking would have handed the model more boilerplate, not more evidence.
    """

    CLAIM = "Eating garlic prevents infection with the new coronavirus."

    @staticmethod
    def _page() -> list[Passage]:
        boilerplate = [
            "Subscribe to our newsletter for the latest updates delivered to your inbox "
            "every morning, plus exclusive offers from our commercial partners today.",
            "Photo credit: our staff photographer, taken at the market earlier this year "
            "during the annual produce festival held in the city centre each spring.",
            "For more coverage of this topic, visit our landing page where all related "
            "reporting from our correspondents around the world is collected together.",
            "Update: California garlic nears harvest with the market riding high on "
            "strong export demand and favourable weather across the growing region.",
        ]
        evidence = [
            "The World Health Organization has addressed this directly: garlic is a "
            "healthy food that may have some antimicrobial properties, but there is no "
            "evidence from the current outbreak that eating garlic has protected people "
            "from the new coronavirus infection.",
            "Snopes rated the claim false, noting that no controlled study has shown any "
            "protective effect of garlic consumption against coronavirus infection in "
            "humans, and that the rumour spread from a single social media post.",
        ]
        texts = boilerplate + evidence
        out = []
        cursor = 0
        for index, text in enumerate(texts):
            out.append(
                Passage(index=index, text=text, char_start=cursor, char_end=cursor + len(text))
            )
            cursor += len(text) + 1
        return out

    def test_the_relevant_passages_are_chosen_over_the_first_ones(self) -> None:
        chosen = select_passages(self.CLAIM, self._page(), limit=2)

        assert {p.index for p in chosen} == {4, 5}

    def test_a_short_page_is_passed_through_untouched(self) -> None:
        """No ranking work when everything fits — and the order must not change."""
        page = self._page()

        assert select_passages(self.CLAIM, page, limit=99) == page

    def test_passages_come_back_in_document_order(self) -> None:
        """The model reads them as a page, not as a ranking."""
        chosen = select_passages(self.CLAIM, self._page(), limit=3)

        assert [p.index for p in chosen] == sorted(p.index for p in chosen)

    def test_near_duplicates_do_not_fill_the_budget(self) -> None:
        """MMR's job: five phrasings of one sentence is one fact, not five."""
        sentence = (
            "The World Health Organization says there is no evidence that eating garlic "
            "protects people from the new coronavirus infection at all."
        )
        page = [
            Passage(
                index=i,
                text=f"{sentence} Paragraph {i}.",
                char_start=i * 200,
                char_end=i * 200 + 190,
            )
            for i in range(5)
        ] + [
            Passage(
                index=5,
                text=(
                    "Health authorities in several countries have issued similar guidance "
                    "warning the public against unproven home remedies for the virus."
                ),
                char_start=1000,
                char_end=1150,
            )
        ]

        chosen = select_passages(self.CLAIM, page, limit=2)

        assert 5 in {p.index for p in chosen}


class TestThePageIsActuallyRead:
    """The web path used to cite search snippets and call them sources.

    Measured across every reader-based verdict this system had produced, the median
    cited quote was 209 characters. A citation requires locating a verbatim quote in
    the text we hold, so a snippet cannot support a quote that genuinely exists on the
    page — the abstention was manufactured by the retrieval, not found in the evidence.
    """

    ARTICLE = (
        "The World Health Organization has addressed this claim directly. Garlic is a "
        "healthy food that may have some antimicrobial properties, but there is no "
        "evidence from the current outbreak that eating garlic protects people from "
        "the new coronavirus. Health authorities in several countries have issued "
        "similar guidance warning against unproven home remedies.\n"
    ) * 3

    def _resolver(self, fetcher: object) -> WebSearchResolver:
        resolver = WebSearchResolver(
            fetcher=fetcher,  # type: ignore[arg-type]
            reasoner=None,
            provider="tavily",
            endpoint="https://example.invalid/search",
            api_key="k",
        )
        resolver._pages["https://www.who.int/a"] = {
            "url": "https://www.who.int/a",
            "title": "Myth busters",
            "content": "A short snippet of a few hundred characters at most.",
            "publisher": "who.int",
            "published_at": None,
        }
        return resolver

    class _Fetcher:
        """Our own fetch: succeeds, fails, or returns a block page."""

        def __init__(self, html: str | None, *, vendor: str = "") -> None:
            self._html = html
            self._vendor = vendor
            self.vendor_calls = 0

        async def fetch(self, url: str, *, provider: str = "web") -> object:
            if self._html is None:
                return SimpleNamespace(reason="blocked")
            return FetchResult(
                url=url,
                final_url=url,
                status_code=200,
                content_type="text/html",
                body=self._html.encode(),
                byte_count=len(self._html),
                fetched_at=datetime.now(UTC),
            )

        async def post_json(self, url: str, body: object, **kw: object) -> object:
            self.vendor_calls += 1
            payload = json.dumps({"results": [{"raw_content": self._vendor}]})
            return FetchResult(
                url=url,
                final_url=url,
                status_code=200,
                content_type="application/json",
                body=payload.encode(),
                byte_count=len(payload),
                fetched_at=datetime.now(UTC),
            )

    @pytest.mark.anyio
    async def test_our_own_fetch_is_used_when_the_page_answers_us(self) -> None:
        """Fourteen of twenty credible hosts do, and it costs nothing."""
        fetcher = self._Fetcher(
            f"<html><body><article><p>{self.ARTICLE}</p></article></body></html>"
        )

        snapshot = await self._resolver(fetcher).snapshot(
            SourceCandidate(url="https://www.who.int/a", proposed_by="web_search:tavily")
        )

        assert snapshot is not None
        assert snapshot.extraction_route == "web.fetched"
        assert len(snapshot.text) > 600
        assert fetcher.vendor_calls == 0

    @pytest.mark.anyio
    async def test_the_vendor_reads_the_pages_that_refuse_us(self) -> None:
        """NDTV, PIB, Reuters and AP all 403 us; the vendor holds that relationship."""
        fetcher = self._Fetcher(None, vendor=self.ARTICLE)

        snapshot = await self._resolver(fetcher).snapshot(
            SourceCandidate(url="https://www.who.int/a", proposed_by="web_search:tavily")
        )

        assert snapshot is not None
        assert snapshot.extraction_route == "web.tavily_extract"
        assert fetcher.vendor_calls == 1

    @pytest.mark.anyio
    async def test_a_block_page_is_not_mistaken_for_an_article(self) -> None:
        """403 bodies are short and parse to almost nothing — that must escalate."""
        fetcher = self._Fetcher(
            "<html><body><h1>Access Denied</h1></body></html>", vendor=self.ARTICLE
        )

        snapshot = await self._resolver(fetcher).snapshot(
            SourceCandidate(url="https://www.who.int/a", proposed_by="web_search:tavily")
        )

        assert snapshot is not None
        assert snapshot.extraction_route == "web.tavily_extract"

    @pytest.mark.anyio
    async def test_the_snippet_is_the_last_rung_and_is_labelled(self) -> None:
        """Better than nothing, but never presented as though it were the article."""
        fetcher = self._Fetcher(None, vendor="")

        snapshot = await self._resolver(fetcher).snapshot(
            SourceCandidate(url="https://www.who.int/a", proposed_by="web_search:tavily")
        )

        assert snapshot is not None
        assert snapshot.extraction_route == "web.snippet"


class TestMediaClaimsAreNotSearchedAsText:
    """An uploaded scam screenshot came back SAFE_TO_SHARE.

    The media path generates a provenance claim in our own words — "This image has
    been published before, at a date and by a publisher that can be cited" — and the
    text resolvers searched that sentence. It retrieved two university library guides
    on how to cite images and an NCBI print record, none of which had ever seen the
    image, and two of them read as *supporting*.

    Whether an image was published before is answerable by reverse-image search and
    C2PA provenance. A text index cannot answer it and must not appear to.
    """

    @pytest.mark.anyio
    async def test_the_web_search_does_not_run_for_a_media_claim(self) -> None:
        calls: list[str] = []

        class _Governor:
            async def try_acquire(self, provider: str) -> object:
                calls.append(provider)
                raise AssertionError("a media claim must not reach the search provider")

        resolver = WebSearchResolver(
            fetcher=None,  # type: ignore[arg-type]
            reasoner=None,
            provider="tavily",
            endpoint="https://example.invalid/search",
            api_key="k",
            governor=_Governor(),
        )

        assert await resolver.candidates(claim(claim_type=ClaimType.MEDIA)) == []
        assert calls == []

    @pytest.mark.anyio
    async def test_an_ordinary_claim_still_reaches_the_provider(self) -> None:
        """The guard must be about the claim type, not a blanket refusal."""
        seen: list[str] = []

        class _Governor:
            async def try_acquire(self, provider: str) -> object:
                seen.append(provider)
                raise ProviderUnavailable(provider, SkipReason.CAPACITY_LIMITED)

        resolver = WebSearchResolver(
            fetcher=None,  # type: ignore[arg-type]
            reasoner=None,
            provider="tavily",
            endpoint="https://example.invalid/search",
            api_key="k",
            governor=_Governor(),
        )

        with pytest.raises(ProviderUnavailable):
            await resolver.candidates(claim(claim_type=ClaimType.EVENT))
        assert seen == ["web_search"]


class TestSearchingTheQuestionBehindTheClaim:
    """The claim sentence alone retrieves the claim's topic, not a check of it.

    "Doctors confirm that drinking cow urine daily cures cancer" returned a WSJ
    video titled "Indian doctors use cow urine as medicine" and an NBC report —
    coverage of the practice, not a word on whether it works. The reader was then
    handed those pages and marked the claim CONTRADICTED on a Full Fact article
    about the Cancer Act 1939.

    Extraction has produced `search_phrases` for exactly this since it was written.
    Nothing read them: the field went into the schema, the model filled it with no
    instruction saying what for, and the conversion to `Claim` dropped it.
    """

    @staticmethod
    def _resolver() -> WebSearchResolver:
        return WebSearchResolver(
            fetcher=None,  # type: ignore[arg-type]
            reasoner=None,
            provider="tavily",
            endpoint="https://example.invalid/search",
            api_key="k",
        )

    def _run(self, subject: WebSearchResolver, target: object) -> tuple[list[str], list[dict]]:
        asked: list[str] = []

        async def _search(query: str) -> list[dict]:
            asked.append(query)
            return [{"url": f"https://example.test/{len(asked)}", "content": "x"}]

        subject._search = _search  # type: ignore[method-assign]
        rows = asyncio.run(subject._queries(target))
        return asked, rows

    def test_the_claims_own_phrases_are_searched_alongside_it(self) -> None:
        subject = self._resolver()
        asked, rows = self._run(
            subject,
            claim(
                text="Doctors confirm that drinking cow urine daily cures cancer.",
                search_phrases=("does cow urine cure cancer", "cow urine cancer evidence"),
            ),
        )

        assert asked[0] == "Doctors confirm that drinking cow urine daily cures cancer."
        assert "does cow urine cure cancer" in asked
        assert "cow urine cancer evidence" in asked
        assert len(rows) == 3

    def test_the_fan_out_is_capped(self) -> None:
        """Each query is a metered call, and the marginal result falls off fast."""
        subject = self._resolver()
        asked, _ = self._run(
            subject,
            claim(search_phrases=tuple(f"a distinct query number {n}" for n in range(9))),
        )

        assert len(asked) == 3

    def test_a_phrase_that_only_restates_the_claim_is_skipped(self) -> None:
        subject = self._resolver()
        asked, _ = self._run(
            subject,
            claim(text="The sky is green.", search_phrases=("the sky is green", "sky colour")),
        )

        assert asked == ["The sky is green.", "sky colour"]

    def test_one_failing_query_does_not_lose_the_others(self) -> None:
        """A search that could not run is an absence, never a failed verification."""
        subject = self._resolver()
        asked: list[str] = []

        async def _search(query: str) -> list[dict]:
            asked.append(query)
            if "boom" in query:
                raise RuntimeError("provider fell over")
            return [{"url": "https://example.test/kept", "content": "x"}]

        subject._search = _search  # type: ignore[method-assign]
        rows = asyncio.run(
            subject._queries(claim(text="A claim.", search_phrases=("boom query here",)))
        )

        assert len(asked) == 2
        assert [row["url"] for row in rows] == ["https://example.test/kept"]

    def test_the_same_url_from_two_queries_is_one_candidate(self) -> None:
        subject = self._resolver()

        async def _search(_query: str) -> list[dict]:
            return [{"url": "https://example.test/same", "content": "x"}]

        subject._search = _search  # type: ignore[method-assign]
        rows = asyncio.run(
            subject._queries(claim(text="A claim.", search_phrases=("another angle on it",)))
        )

        assert len(rows) == 1

    def test_each_query_reaches_the_front_of_the_shortlist(self) -> None:
        """Only a handful of pages are ever read, so order decides who is heard.

        Concatenating the queries' results left the claim query's whole first page
        ahead of everything else, so the supplementary queries changed the candidate
        count and nothing else: 8 candidates became 16 and the same three pages were
        read.
        """
        subject = self._resolver()

        async def _search(query: str) -> list[dict]:
            tag = "claim" if query.startswith("A claim") else query.split()[0]
            return [{"url": f"https://example.test/{tag}/{n}", "content": "x"} for n in range(5)]

        subject._search = _search  # type: ignore[method-assign]
        rows = asyncio.run(
            subject._queries(
                claim(text="A claim.", search_phrases=("beta question here", "gamma question here"))
            )
        )

        assert [row["url"] for row in rows[:3]] == [
            "https://example.test/claim/0",
            "https://example.test/beta/0",
            "https://example.test/gamma/0",
        ]


class TestASnippetCannotDecideAClaim:
    """`snapshot()` promised it; nothing enforced it.

    science.org served a Cloudflare "Enable JavaScript and cookies to continue"
    page, the ladder fell through to the search snippet, and 123 characters of
    vendor summary produced a decisive SUPPORTS for "drinking cow urine daily will
    cure a person of cancer" — from an article headlined "Indian scientists decry
    'infuriating' scheme to study benefits of cow dung, urine, and milk".

    A vendor summary is elided text and elision strips attribution: the article
    reports what proponents claim, the snippet states it flat. The reader's rules
    about who is speaking cannot be applied to text that no longer says.
    """

    @staticmethod
    def _snapshot(route: str) -> SourceSnapshot:
        body = (
            "Proponents describe curative properties of cow urine, dung and milk, "
            "including potential cancer treatments, and one says cow urine cured her "
            "breast cancer after doctors had given up on conventional therapy."
        )
        return SourceSnapshot(
            id="web:test",
            url="https://www.science.org/content/article/indian-scientists-decry",
            final_url="https://www.science.org/content/article/indian-scientists-decry",
            content_hash="sha256:test",
            fetched_at=datetime.now(UTC),
            text=body,
            extraction_route=route,
        )

    def _relate(self, route: str, relation: Relation) -> SourceRelation:
        snapshot = self._snapshot(route)
        quote = snapshot.text[:120]

        class _Reasoner:
            async def judge(self, *_args: object, **_kwargs: object) -> object:
                return SimpleNamespace(
                    succeeded=True,
                    reason=None,
                    passages_read=1,
                    best=lambda: SimpleNamespace(
                        relation=relation, quote=quote, reason="r", relevance=0.9
                    ),
                )

        resolver = WebSearchResolver(
            fetcher=None,  # type: ignore[arg-type]
            reasoner=_Reasoner(),
            provider="tavily",
            endpoint="https://example.invalid/search",
            api_key="k",
        )
        return asyncio.run(resolver.relate(claim(), snapshot))

    def test_a_snippet_cannot_support(self) -> None:
        assert self._relate("web.snippet", Relation.SUPPORTS).relation is Relation.CONTEXTUALIZES

    def test_a_snippet_cannot_contradict_either(self) -> None:
        """Both directions. A snippet that seems to refute has lost attribution too."""
        assert self._relate("web.snippet", Relation.CONTRADICTS).relation is Relation.CONTEXTUALIZES

    def test_the_demotion_says_so_in_the_metric(self) -> None:
        relation = self._relate("web.snippet", Relation.SUPPORTS)

        assert "search snippet" in relation.metric

    def test_a_page_we_actually_read_still_decides(self) -> None:
        """The cap is about the rung, not a blanket loss of nerve."""
        assert self._relate("web.fetched", Relation.SUPPORTS).relation is Relation.SUPPORTS
        assert self._relate("web.fetched", Relation.CONTRADICTS).relation is Relation.CONTRADICTS


class TestATypesetQuoteIsStillTheQuote:
    """Eight of nine judgements were discarded on typography, not on honesty.

    Measured on a one-day-old story read across Reuters, the BBC, the NYT, AP, NPR
    and PBS: retrieval found the sources, the reader judged them, and the quote gate
    threw almost all of it away. One PBS article carried six U+0027 apostrophes and
    three U+2019 ones in the same body, so there is no convention for a model to
    reproduce even when it is copying faithfully.
    """

    def test_a_curly_quote_matches_a_straight_one(self) -> None:
        page = 'Trump said he has an “obligation” to keep fake news out of the complex.'
        model = 'Trump said he has an "obligation" to keep fake news out of the complex.'

        assert verify_quote(model, page) is not None

    def test_a_curly_apostrophe_matches_a_straight_one(self) -> None:
        page = "The network’s coverage was described as relentlessly negative by the president."
        model = "The network's coverage was described as relentlessly negative by the president."

        assert verify_quote(model, page) is not None

    def test_an_em_dash_matches_a_hyphen(self) -> None:
        page = "Three outlets — CNN, MS NOW and Politico — were barred from the complex."
        model = "Three outlets - CNN, MS NOW and Politico - were barred from the complex."

        assert verify_quote(model, page) is not None

    def test_a_paraphrase_still_fails(self) -> None:
        """The gate is unchanged for everything it was built to catch."""
        page = 'Trump said he has an “obligation” to keep fake news out of the complex.'

        assert verify_quote("Trump claimed a duty to bar fake news from the complex.", page) is None

    def test_a_changed_word_still_fails(self) -> None:
        page = "The president barred three news organisations from the White House complex."
        model = "The president barred four news organisations from the White House complex."

        assert verify_quote(model, page) is None

    def test_invented_text_still_fails(self) -> None:
        page = "The president barred three news organisations from the White House complex."

        assert verify_quote("The president apologised to the barred organisations.", page) is None


class TestAQuoteClaimIsCorroboratedByReportedSpeech:
    """For "X said Y", an article reporting that X said Y is the corroboration.

    The attribution guard demotes a SUPPORTS whose passage merely reports what
    someone else claims — right for a factual claim, exactly backwards for a claim
    *about the saying*. Live, on a one-day-old Economic Times story: "Trump said he
    believes he has an obligation to prevent news organizations he considers fake
    news from entering the presidential complex" was answered UNVERIFIED while the
    BBC and NBC both carried it, because the reader saw Trump asserting the belief
    and the guard filed his own words as context rather than as evidence that he
    said them.
    """

    @staticmethod
    def _judge(claim_type: str | None) -> ReasoningOutcome:
        body = (
            "Trump said he believes he has an obligation to prevent news "
            "organizations he considers fake news from entering the complex."
        )
        passages = [Passage(index=0, text=body, char_start=0, char_end=len(body))]
        response = _ReasoningResponse.model_validate(
            {
                "judgements": [
                    {
                        "passage_index": 0,
                        "relation": "SUPPORTS",
                        # The model reads the inner belief as Trump's, which it is.
                        "asserted_by": "SOMEONE_ELSE",
                        "quote": body,
                        "reason": "r",
                        "relevance": 0.9,
                    }
                ]
            }
        )
        reasoner = PassageReasoner.__new__(PassageReasoner)
        reasoner._model_id = "test"
        return reasoner._verify(response, passages, claim_type=claim_type)

    def test_a_quote_claim_keeps_the_support(self) -> None:
        assert self._judge("QUOTE").judgements[0].relation is Relation.SUPPORTS

    def test_an_attribution_claim_keeps_it_too(self) -> None:
        assert self._judge("ATTRIBUTION").judgements[0].relation is Relation.SUPPORTS

    def test_an_event_claim_is_still_demoted(self) -> None:
        """The guard is unchanged where it was right: someone's claim is not a fact."""
        assert self._judge("EVENT").judgements[0].relation is Relation.CONTEXTUALIZES

    def test_an_unknown_claim_type_is_still_demoted(self) -> None:
        """Absent a type, keep the cautious behaviour rather than assume."""
        assert self._judge(None).judgements[0].relation is Relation.CONTEXTUALIZES


class TestADebunkIsNotTheThingItDebunks:
    """We told a reader not to share a government fact-check.

    Submitting newsonair.gov.in's report that the MEA had debunked a fabricated
    fire at an India-Israel defence facility produced DO_NOT_SHARE. The extracted
    claim — "the government has debunked claims that a massive fire broke out" — is
    true, and four sources were cited as contradicting it. They were not
    contradicting it: they were establishing that no fire broke out, which is what
    the government said and agrees with the claim.

    The reader matched the statement *inside* the claim instead of the claim. For a
    product people use to check forwarded fact-checks, blocking the fact-check is
    close to the worst answer available.
    """

    @staticmethod
    def _judge(basis: str) -> ReasoningOutcome:
        body = (
            "The Fact Check Unit of the Ministry of External Affairs said no such "
            "fire took place at any joint defence facility in Delhi."
        )
        passages = [Passage(index=0, text=body, char_start=0, char_end=len(body))]
        response = _ReasoningResponse.model_validate(
            {
                "judgements": [
                    {
                        "passage_index": 0,
                        "relation": "CONTRADICTS",
                        "contradiction_basis": basis,
                        "quote": body,
                        "reason": "r",
                        "relevance": 0.9,
                    }
                ]
            }
        )
        reasoner = PassageReasoner.__new__(PassageReasoner)
        reasoner._model_id = "test"
        return reasoner._verify(response, passages, claim_type="ATTRIBUTION")

    def test_refuting_what_the_claim_reports_is_not_contradicting_the_claim(self) -> None:
        assert self._judge("REFUTES_REPORTED_CONTENT").judgements == ()

    def test_even_a_confident_denial_only_contextualises(self) -> None:
        """Deliberate, and lopsided on purpose.

        A passage can only honestly contradict "A said B" by establishing that A did
        not say it, which is rare. Mistaking a refutation of B for a refutation of the
        claim is what actually happens, and it produced DO_NOT_SHARE on a government
        fact-check. Missing the rare genuine denial is the cheaper mistake, so a
        contradiction here is kept and shown but no longer decides.
        """
        assert self._judge("DENIES").judgements[0].relation is Relation.CONTEXTUALIZES


class TestAPersonalPageIsNotTheInstitution:
    """A university is credible about what the university did. A lecturer is not it.

    "IIT Madras inaugurated a robotics laboratory" was carried by PIB, the Times of
    India and the Indian Express, and abstained under `rule.conflicting_evidence`
    because one citation contradicted it: `home.iitm.ac.in/samuelgl/inauguration.html`,
    a faculty page about a different inauguration. The registrable domain is
    `iitm.ac.in` either way, so nothing downstream could tell the institution from
    one person on its domain.
    """

    @staticmethod
    def _credibility() -> SourceCredibility:
        return SourceCredibility.load()

    def test_a_personal_subdomain_is_not_citable(self) -> None:
        subject = self._credibility()

        assert not subject.is_credible("https://home.iitm.ac.in/samuelgl/inauguration.html")
        assert not subject.is_credible("https://people.mit.edu/someone/page.html")

    def test_a_tilde_path_is_the_same_convention(self) -> None:
        assert not self._credibility().is_credible("https://www.iitm.ac.in/~samuelgl/page.html")

    def test_the_institution_itself_still_is(self) -> None:
        """The narrowing must not cost us the university's own newsroom."""
        subject = self._credibility()

        assert subject.is_credible("https://www.iitm.ac.in/news/robotics-lab")
        assert subject.is_credible("https://www.mit.edu/news/story")


class TestOneCasesClaimsShareTheirReading:
    """Claims from one article retrieve one story's sources, over and over.

    Measured on an Economic Times commentary: seven claims extracted, the three
    eligible ones searched, fifteen page reads between them — bbc.com fetched three
    times, Reuters, AFP and Brookings twice each. Every repeat was a fresh network
    round trip for a page already in hand, inside a request with a 45 second budget
    that took 34.
    """

    @staticmethod
    def _resolver() -> WebSearchResolver:
        return WebSearchResolver(
            fetcher=None,  # type: ignore[arg-type]
            reasoner=None,
            provider="tavily",
            endpoint="https://example.invalid/search",
            api_key="k",
        )

    def test_a_page_is_read_once_for_a_whole_case(self) -> None:
        subject = self._resolver()
        reads: list[str] = []

        async def _read_uncached(url: str) -> tuple[str, str, str]:
            reads.append(url)
            return ("body text", "web.fetched", url)

        subject._read_uncached = _read_uncached  # type: ignore[method-assign]

        async def _drive() -> None:
            for _ in range(3):
                await subject._read("https://www.bbc.com/news/story")

        asyncio.run(_drive())

        assert reads == ["https://www.bbc.com/news/story"]

    def test_different_pages_are_still_read(self) -> None:
        """The cache is keyed by URL, not a blanket suppression."""
        subject = self._resolver()
        reads: list[str] = []

        async def _read_uncached(url: str) -> tuple[str, str, str]:
            reads.append(url)
            return ("body", "web.fetched", url)

        subject._read_uncached = _read_uncached  # type: ignore[method-assign]

        async def _drive() -> None:
            await subject._read("https://www.bbc.com/news/one")
            await subject._read("https://www.reuters.com/two")

        asyncio.run(_drive())

        assert len(reads) == 2

    def test_a_stale_entry_is_read_again(self) -> None:
        """Ninety seconds covers one case. It must not answer for a later one."""
        subject = self._resolver()
        reads: list[str] = []

        async def _read_uncached(url: str) -> tuple[str, str, str]:
            reads.append(url)
            return ("body", "web.fetched", url)

        subject._read_uncached = _read_uncached  # type: ignore[method-assign]
        url = "https://www.bbc.com/news/story"

        async def _drive() -> None:
            await subject._read(url)
            # Age the entry past the window rather than sleeping through it.
            when, value = subject._reads[url]
            subject._reads[url] = (when - 600.0, value)
            await subject._read(url)

        asyncio.run(_drive())

        assert len(reads) == 2
