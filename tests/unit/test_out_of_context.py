"""Genuine, and shown out of context (re-test of 2026-10-02).

A 2.8-second clip of Netanyahu at the UN saying "America deserved 9/11" - quoting
Hasan Piker, which the clip cut off - came back TRUE 89: Newschecker's and Snopes's
own explanations of how it was cut were counted as confirmation, because nothing could
say "the words are real, the meaning is not". Real heatwave news illustrated with
traffic lights burned in a fire, and a flydubai attack illustrated with an old easyJet
clip, came back "partly true" for the same reason.

Each rule below is held with crafted evidence, offline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain import (
    Action,
    ClaimStatus,
    ClaimType,
    Credibility,
    Direction,
    EvidenceKind,
    Importance,
    MatchBasis,
    Method,
    Severity,
    Tier,
    Verdict,
)
from app.domain.enums import Relation
from app.domain.evidence import (
    NARROWER_SCOPE,
    OUT_OF_CONTEXT,
    SHARED_REVIEW,
    is_out_of_context,
)
from app.orchestration.pipeline import _reports_on
from app.sources.base import SourceSnapshot
from app.sources.corpus import CorpusResolver
from app.sources.factcheck import FactCheckRecord, FactCheckResolver, parse_rating_from_title
from app.sources.reasoning import (
    _CHECK_SOURCES_INSTRUCTION,
    _CHECK_SOURCES_SCHEMA,
    ATTRIBUTED_SUPPORT,
    REASONER_VERSION,
    SourceCheck,
    SourceReading,
    is_attributed_support,
)
from app.sources.verification import SourceVerification, dedupe
from app.verdict.engine import (
    NARROWER_RULE,
    OUT_OF_CONTEXT_RULE,
    RULE_VERSION,
    Decision,
    decide,
    roll_up,
)
from app.verdict.explain import explain
from tests.unit.factories import claim, evidence

pytestmark = pytest.mark.unit

QUOTE = 'The speaker in the video said, "America deserved 9-Eleven."'


def _framed(
    host: str = "snopes.com",
    *,
    kind: EvidenceKind = EvidenceKind.CORROBORATION,
    credibility: Credibility | None = Credibility.MEDIUM,
) -> Any:
    """A source the check found calls the material genuine but misframed."""
    return evidence(
        kind=kind,
        direction=Direction.CONTEXTUALIZES,
        tier=Tier.C if kind is EvidenceKind.FACT_CHECK else Tier.D,
        method=Method.PASSAGE_ENTAILMENT,
        basis=MatchBasis(
            metric=f"{OUT_OF_CONTEXT}: he said the words while quoting Hasan Piker",
            value=0.9,
            threshold=0.5,
        ),
        citation_url=f"https://www.{host}/netanyahu-clip",
        publisher=host,
        source_excerpt="the clip omitted the words identifying Hasan Piker as the speaker",
        credibility=credibility,
    )


def _report(
    read: str, host: str, credibility: Credibility | None = Credibility.MEDIUM, **fields: Any
) -> Any:
    direction, metric = {
        "supports": (Direction.SUPPORTS, "passage_entailment: r"),
        "contradicts": (Direction.CONTRADICTS, "passage_entailment: r"),
        "narrower": (Direction.CONTEXTUALIZES, f"{NARROWER_SCOPE}: r"),
        "attributed": (Direction.CONTEXTUALIZES, f"{ATTRIBUTED_SUPPORT}: r"),
    }[read]
    return evidence(
        kind=EvidenceKind.CORROBORATION,
        direction=direction,
        tier=Tier.D,
        method=Method.PASSAGE_ENTAILMENT,
        basis=MatchBasis(metric=metric, value=0.9, threshold=0.5),
        citation_url=f"https://www.{host}/story",
        publisher=host,
        credibility=credibility,
        **fields,
    )


# ------------------------------------------------------------------ the rule


class TestTheRule:
    def test_a_fact_check_finding_outranks_reports_of_the_words(self) -> None:
        """Two outlets repeat the words; a fact-check says the clip cut them."""
        subject = claim(claim_type=ClaimType.QUOTE, independent_origin_count=2)
        items = [
            _framed("newschecker.in", kind=EvidenceKind.FACT_CHECK, credibility=None),
            _report("supports", "ndtv.com"),
            _report("supports", "thehindu.com"),
        ]

        decision = decide(subject, items)

        assert decision.status is ClaimStatus.MISLEADING_CONTEXT
        assert decision.rule_id == OUT_OF_CONTEXT_RULE
        assert decision.supporting_evidence_ids == (items[0].id,)

    def test_one_highly_credible_source_is_enough(self) -> None:
        decision = decide(claim(), [_framed(credibility=Credibility.HIGH)])

        assert decision.rule_id == OUT_OF_CONTEXT_RULE

    def test_or_two_independent_publishers(self) -> None:
        decision = decide(claim(), [_framed("snopes.com"), _framed("newschecker.in")])

        assert decision.rule_id == OUT_OF_CONTEXT_RULE

    def test_one_ordinary_report_decides_nothing(self) -> None:
        decision = decide(claim(), [_framed()])

        assert decision.status is ClaimStatus.UNVERIFIED

    def test_a_credible_denial_still_decides_it_false(self) -> None:
        """After every contradiction: "he never said it" stays a refutation."""
        denial = _report("contradicts", "reuters.com", Credibility.HIGH)

        decision = decide(claim(), [_framed(credibility=Credibility.HIGH), denial])

        assert decision.status is ClaimStatus.CONTRADICTED

    def test_a_split_between_reports_is_explained_by_it(self) -> None:
        """One outlet repeats the words, another calls them not his: undecided
        without the finding, out of context with it."""
        items = [
            _report("supports", "ndtv.com"),
            _report("contradicts", "thehindu.com"),
        ]
        assert decide(claim(), items).rule_id == "rule.conflicting_evidence"

        framed = _framed("newschecker.in", kind=EvidenceKind.FACT_CHECK)

        assert decide(claim(), [*items, framed]).rule_id == OUT_OF_CONTEXT_RULE

    def test_a_shared_fact_check_rated_missing_context(self) -> None:
        shared = evidence(
            direction=Direction.CONTEXTUALIZES,
            basis=MatchBasis(metric=SHARED_REVIEW, value=1.0, threshold=0.8),
        )

        assert decide(claim(), [shared]).rule_id == OUT_OF_CONTEXT_RULE

    def test_reports_of_the_words_do_not_lower_its_confidence(self) -> None:
        alone = decide(claim(), [_framed(credibility=Credibility.HIGH)])
        beside = decide(
            claim(independent_origin_count=1),
            [_framed(credibility=Credibility.HIGH), _report("supports", "ndtv.com")],
        )

        assert alone.confidence == beside.confidence

    def test_the_versions_moved(self) -> None:
        assert RULE_VERSION >= "2026.10.03.2"
        assert REASONER_VERSION >= "2026.10.03.5"


class TestTheCase:
    def test_the_clip_reads_misleading(self) -> None:
        """media-8: one claim, the quote, found out of context."""
        quote = claim(claim_type=ClaimType.QUOTE, importance=Importance.HEADLINE)

        case = roll_up([(quote, decide(quote, [_framed(credibility=Credibility.HIGH)]))])

        assert case.action is Action.SHARE_WITH_CONTEXT
        assert case.verdict is Verdict.MISLEADING

    def test_misframed_footage_outranks_a_detail_reported_in_part(self) -> None:
        """ig-7: real heatwave news, side details reported smaller, and footage of
        fire damage shown as heat damage."""
        headline = claim(importance=Importance.HEADLINE, independent_origin_count=2)
        detail = claim(claim_id="cl_2", importance=Importance.SUPPORTING_DETAIL)
        footage = claim(claim_id="cl_3", importance=Importance.SUPPORTING_DETAIL)
        narrower = [_report("narrower", "france24.com"), _report("narrower", "un.org")]

        case = roll_up(
            [
                (headline, decide(headline, [_report("supports", "indiatoday.in")])),
                (detail, decide(detail, narrower)),
                (footage, decide(footage, [_framed(credibility=Credibility.HIGH)])),
            ]
        )

        assert decide(detail, narrower).rule_id == NARROWER_RULE
        assert case.rule_id == "rollup.misleading_material"
        assert case.verdict is Verdict.MISLEADING

    def test_a_smaller_version_alone_is_still_partly_true(self) -> None:
        headline = claim(importance=Importance.HEADLINE, independent_origin_count=2)
        detail = claim(claim_id="cl_2", importance=Importance.SUPPORTING_DETAIL)

        case = roll_up(
            [
                (headline, decide(headline, [_report("supports", "indiatoday.in")])),
                (
                    detail,
                    decide(detail, [_report("narrower", "a.in"), _report("narrower", "b.in")]),
                ),
            ]
        )

        assert case.rule_id == "rollup.partly_true"

    def test_it_is_explained_as_what_it_is(self) -> None:
        framed = _framed("newschecker.in", kind=EvidenceKind.FACT_CHECK)
        decision = Decision(
            status=ClaimStatus.MISLEADING_CONTEXT,
            rule_id=OUT_OF_CONTEXT_RULE,
            reason="r",
            supporting_evidence_ids=(framed.id,),
        )

        line = explain(decision.status, [framed], decision.supporting_evidence_ids, language="en")
        hindi = explain(decision.status, [framed], decision.supporting_evidence_ids, language="hi")

        assert line is not None and "out of context" in line
        assert "narrower" not in line
        assert hindi is not None and "संदर्भ" in hindi

    def test_it_reports_on_the_claim(self) -> None:
        """So "nothing reports this, treat it as likely false" is never said beside it."""
        assert _reports_on(_framed())


# ------------------------------------------------------------ the source check


class _Checker:
    def __init__(self, verdict: str, **reading: Any) -> None:
        self.verdict = verdict
        self.reading = {"addresses_claim": True, **reading}
        self.sent: list[tuple[str, str]] = []

    async def check_sources(self, claim_text: str, sources: list[tuple[str, str]]) -> Any:
        self.sent = sources
        return SourceCheck(
            readings={
                i: SourceReading(verdict=self.verdict, reason="quoting Piker", **self.reading)
                for i in range(len(sources))
            },
            explanation="",
        )


class _Ranker:
    def credibility(self, _url: str | None) -> Credibility:
        return Credibility.HIGH


def _verified(checker: _Checker, items: list[Any]) -> Any:
    return asyncio.run(
        SourceVerification(checker=checker, ranker=_Ranker()).check(claim(text=QUOTE), items)
    )


class TestTheSourceCheck:
    @pytest.mark.parametrize("read", ["supports", "attributed", "narrower"])
    def test_a_support_found_out_of_context_is_kept_as_that(self, read: str) -> None:
        """Snopes: "said the words while quoting Hasan Piker", read as support."""
        verified = _verified(_Checker("TRUE", out_of_context=True), [_report(read, "snopes.com")])

        [kept] = verified.evidence
        assert kept.direction is Direction.CONTEXTUALIZES
        assert is_out_of_context(kept.match_basis.metric)

    def test_a_denial_of_genuine_footage_is_kept_as_out_of_context(self) -> None:
        """India Today: the clip is the easyJet incident of July 2025, not flydubai."""
        item = _report(
            "contradicts",
            "indiatoday.in",
            source_excerpt="The viral video is of an easyJet flight from Luton to Glasgow in 2025.",
        )

        [kept] = _verified(_Checker("FALSE", out_of_context=True), [item]).evidence

        assert is_out_of_context(kept.match_basis.metric)

    @pytest.mark.parametrize(
        "excerpt",
        [
            "The picture is AI-generated and was never taken at the summit.",
            "Bhatia denied making the statement and called the graphic fake.",
            "The quote is fabricated.",
        ],
    )
    def test_a_fake_is_never_softened(self, excerpt: str) -> None:
        item = _report("contradicts", "altnews.in", source_excerpt=excerpt)

        [kept] = _verified(_Checker("FALSE", out_of_context=True), [item]).evidence

        assert kept.direction is Direction.CONTRADICTS

    @pytest.mark.parametrize("read", ["supports", "contradicts"])
    def test_a_fake_ruled_out_is_not_a_fake_named(self, read: str) -> None:
        """Snopes, verbatim: the check answered FALSE and out of context, and the
        words "digitally altered" - ruled out - kept it from being either."""
        snopes = (
            "While the clip was authentic, meaning not generated with artificial "
            "intelligence or digitally altered, it omits critical context from "
            "Netanyahu's full remarks. He was not expressing his personal belief."
        )
        item = _report(read, "snopes.com", source_excerpt=snopes)

        [kept] = _verified(_Checker("FALSE", out_of_context=True), [item]).evidence

        assert is_out_of_context(kept.match_basis.metric)

    def test_a_published_rating_of_false_is_never_softened(self) -> None:
        """BOOM's ClaimReview: "BOOM Fact Check rated this False: Old photograph of
        Prime Minister Narendra Modi and Home Minister Amit Shah" (ig-5)."""
        rated = evidence(
            basis=MatchBasis(metric="claim_similarity", value=0.9, threshold=0.62),
            source_excerpt="BOOM Fact Check rated this False: Old photograph of PM Modi.",
        )

        [kept] = _verified(_Checker("FALSE", out_of_context=True), [rated]).evidence

        assert kept.direction is Direction.CONTRADICTS

    def test_a_support_the_check_calls_a_fabrication_is_not_kept(self) -> None:
        item = _report("supports", "altnews.in", source_excerpt="The quote is fabricated.")

        assert _verified(_Checker("FALSE", out_of_context=True), [item]).evidence == []

    def test_not_about_the_claim_is_rejected(self) -> None:
        checker = _Checker("TRUE", out_of_context=True, addresses_claim=False)

        assert _verified(checker, [_report("supports", "snopes.com")]).evidence == []

    def test_without_the_finding_a_support_stays_support(self) -> None:
        [kept] = _verified(_Checker("TRUE"), [_report("supports", "snopes.com")]).evidence

        assert kept.direction is Direction.SUPPORTS

    def test_a_rating_of_missing_context_is_kept_when_about_the_claim(self) -> None:
        rated = _framed("newschecker.in", kind=EvidenceKind.FACT_CHECK, credibility=None)

        [kept] = _verified(_Checker("UNCLEAR"), [rated]).evidence
        rejected = _verified(_Checker("UNCLEAR", addresses_claim=False), [rated])

        assert is_out_of_context(kept.match_basis.metric)
        assert rejected.evidence == []

    def test_the_rating_outranks_a_reading_of_the_same_page(self) -> None:
        rated = _framed("newschecker.in", kind=EvidenceKind.FACT_CHECK)
        read = rated.model_copy(
            update={
                "id": "ev_read",
                "direction": Direction.SUPPORTS,
                "kind": EvidenceKind.CORROBORATION,
                "tier": Tier.D,
                "match_basis": MatchBasis(metric="passage_entailment: r", value=0.9, threshold=0.5),
            }
        )

        kept, duplicates = dedupe([read, rated])

        assert duplicates == 1
        assert [item.id for item in kept] == [rated.id]

    def test_the_log_carries_the_checks_answers(self, caplog: Any) -> None:
        with caplog.at_level(logging.INFO, logger="factify.sources.verification"):
            _verified(
                _Checker("PARTLY", smaller_version=True, out_of_context=True),
                [_report("supports", "snopes.com")],
            )

        logged = json.dumps([getattr(r, "__dict__", {}) for r in caplog.records], default=str)
        assert "smaller,out_of_context" in logged

    def test_the_check_is_asked_before_its_verdict(self) -> None:
        item = _CHECK_SOURCES_SCHEMA["properties"]["sources"]["items"]
        order = list(item["properties"])

        assert "out_of_context" in item["required"]
        assert order.index("out_of_context") < order.index("verdict")
        assert "out_of_context" in _CHECK_SOURCES_INSTRUCTION
        assert "AI-made" in _CHECK_SOURCES_INSTRUCTION


# ------------------------------------------------------------- ratings, corpus


class TestARatingOfMissingContext:
    def test_a_clipped_video_headline_is_read(self) -> None:
        title = "Did Benjamin Netanyahu Say ‘America Deserved 9/11’? No, Clipped Video Goes Viral"

        assert parse_rating_from_title(title) == "clipped"

    @pytest.mark.parametrize(
        ("title", "rating"),
        [
            ("Fake: clipped video of the minister goes viral", "fake"),
            ("Morphed and cropped image of the PM shared", None),
            ("Old video of a flood shared as Assam 2026", None),
        ],
    )
    def test_a_fake_or_tampered_picture_is_not_one(self, title: str, rating: str | None) -> None:
        assert parse_rating_from_title(title) == rating

    @pytest.mark.parametrize("rating", ["Missing Context", "Out of context", "Clipped"])
    def test_it_is_neither_true_nor_false(self, rating: str) -> None:
        record = FactCheckRecord(
            claim_text="c", normalized_text="c", url="u", rating=rating, publisher=None
        )

        assert record.verdict is Relation.CONTEXTUALIZES

    def test_false_still_wins(self) -> None:
        record = FactCheckRecord(
            claim_text="c", normalized_text="c", url="u", rating="False, clipped", publisher=None
        )

        assert record.verdict is Relation.CONTRADICTS

    async def test_it_is_cited_as_out_of_context(self) -> None:
        text = "Did Benjamin Netanyahu Say America Deserved 9/11? No, Clipped Video Goes Viral"
        record = FactCheckRecord(
            claim_text=text,
            normalized_text=text.lower(),
            url="https://newschecker.in/fact-check/netanyahu-america-deserved-9-11",
            rating=parse_rating_from_title(text),
            publisher="Newschecker",
            published_at=datetime(2026, 9, 26, tzinfo=UTC),
            retrieved_at=datetime(2026, 9, 26, tzinfo=UTC),
        )
        resolver = FactCheckResolver(records=[record], api_available=False)  # type: ignore[arg-type]
        subject = claim(claim_type=ClaimType.QUOTE, text=text)

        [candidate] = await resolver.candidates(subject)
        snapshot = await resolver.snapshot(candidate)
        assert snapshot is not None
        relation = await resolver.relate(subject, snapshot)

        assert relation.relation is Relation.CONTEXTUALIZES
        assert relation.metric.startswith(OUT_OF_CONTEXT)
        assert "clipped" in relation.excerpt


def _page(title: str, url: str) -> SourceSnapshot:
    text = (
        "The viral clip shows Benjamin Netanyahu saying America deserved 9/11 at the UN "
        "General Assembly. In the full speech he was quoting Hasan Piker."
    )
    return SourceSnapshot(
        id="corpus:test",
        url=url,
        final_url=url,
        content_hash="sha256:test",
        fetched_at=datetime.now(UTC),
        text=text,
        title=title,
    )


class TestTheCorpusWordMatch:
    CLAIM = "Benjamin Netanyahu said America deserved 9/11 at the UN General Assembly."

    def _related(self, title: str, url: str) -> Any:
        resolver = CorpusResolver.__new__(CorpusResolver)
        resolver._embedder = None
        return asyncio.run(resolver._relate_lexically(claim(text=self.CLAIM), _page(title, url)))

    def test_a_fact_check_page_is_never_word_overlap_support(self) -> None:
        relation = self._related(
            "Did Benjamin Netanyahu Say 'America Deserved 9/11'? No, Clipped Video Goes Viral",
            "https://newschecker.in/fact-check/netanyahu-america-deserved-9-11",
        )

        assert relation.relation is Relation.CONTEXTUALIZES
        assert is_attributed_support(relation.metric)

    def test_a_news_report_is_unchanged(self) -> None:
        relation = self._related(
            "Netanyahu addresses the UN General Assembly",
            "https://www.thehindu.com/news/international/netanyahu-un-speech",
        )

        assert relation.relation is Relation.SUPPORTS


def test_a_held_back_fact_check_is_not_cited_without_the_check() -> None:
    """With the check down, a word match on a debunk is never counted as support."""

    class _Down:
        async def check_sources(self, claim_text: str, sources: list[tuple[str, str]]) -> Any:
            return None

    held = _report("attributed", "newschecker.in")

    verified = asyncio.run(
        SourceVerification(checker=_Down(), ranker=_Ranker()).check(claim(text=QUOTE), [held])
    )

    assert verified.checked is False
    assert verified.evidence == []


def test_a_severity_is_irrelevant_to_the_rule() -> None:
    """The finding decides a CRITICAL claim as it does any other."""
    critical = claim(severity=Severity.CRITICAL)

    assert decide(critical, [_framed(credibility=Credibility.HIGH)]).rule_id == OUT_OF_CONTEXT_RULE
