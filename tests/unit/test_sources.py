"""M27–M32 — evidence retrieval.

The tests that matter here are the ones about restraint: what each resolver refuses
to conclude, and why.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.enums import CoverageExpectation, Relation, SourceRisk
from app.knowledge.clustering import OriginClusterer
from app.sources.attribution import find_cited_sources
from app.sources.base import (
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
from app.sources.factcheck import (
    FactCheckRecord,
    FactCheckResolver,
    parse_rating_from_title,
)
from app.sources.reasoning import (
    _SYSTEM_INSTRUCTION,
    Passage,
    PassageJudgement,
    PassageReasoner,
    ReasoningOutcome,
    _ReasoningResponse,
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
        def __init__(self, outcome: object) -> None:
            self._outcome = outcome
            self.calls = 0

        async def judge(self, claim_text: str, passages: list[object]) -> object:
            self.calls += 1
            return self._outcome

    @staticmethod
    def _outcome(relation: Relation | None) -> ReasoningOutcome:
        if relation is None:
            return ReasoningOutcome(judgements=(), passages_read=1)
        return ReasoningOutcome(
            judgements=(
                PassageJudgement(
                    relation=relation,
                    quote="rated this False",
                    reason="r",
                    relevance=0.9,
                    passage_index=0,
                ),
            ),
            passages_read=1,
        )

    @pytest.mark.anyio
    async def test_a_reader_that_sees_no_relation_rejects_the_rating(self) -> None:
        reader = self._Reader(self._outcome(None))

        assert not await self._resolver(reader)._addresses(claim(), self._record())
        assert reader.calls == 1

    @pytest.mark.anyio
    async def test_an_explicit_not_relevant_also_rejects(self) -> None:
        """`best()` ranks NOT_RELEVANT last but still returns it."""
        reader = self._Reader(self._outcome(Relation.NOT_RELEVANT))

        assert not await self._resolver(reader)._addresses(claim(), self._record())

    @pytest.mark.anyio
    async def test_a_reader_that_finds_the_claim_addressed_accepts(self) -> None:
        reader = self._Reader(self._outcome(Relation.CONTRADICTS))

        assert await self._resolver(reader)._addresses(claim(), self._record())

    @pytest.mark.anyio
    async def test_without_a_reader_the_score_decides_alone(self) -> None:
        """Degrades open: refusing everything would disable the strongest evidence
        class whenever no model is configured, rather than loosening one check."""
        assert await self._resolver(None)._addresses(claim(), self._record())

    @pytest.mark.anyio
    async def test_a_reader_outage_does_not_drop_the_evidence(self) -> None:
        reader = self._Reader(ReasoningOutcome(reason="provider failed"))

        assert await self._resolver(reader)._addresses(claim(), self._record())


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
                self, claim_text: str, passages: list[object], *, title: str | None = None
            ) -> ReasoningOutcome:
                seen["title"] = title
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
