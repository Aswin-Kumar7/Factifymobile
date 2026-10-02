"""The judging rules that turned true news into Unconfirmed (audit of 2026-10-02).

Forty-five real inputs, nineteen right. In most of the failures search had found the
reports - or the debunk - and they were lost while sources were judged:

- the source check threw away a support the reader had called narrower when the check
  itself said TRUE ("read contextualizes, check said TRUE": 23 times in nine checks);
- a denial could never contradict a fake quote, because every contradiction of a
  QUOTE or ATTRIBUTION claim was demoted to context;
- "the Army said", "police said" reports were held as someone else's word;
- a report that confirmed an event but left out one bundled detail was rejected;
- background details rated CRITICAL held back a headline three outlets carried;
- "treat it as likely false" was said beside debunks, opinions and supported stories;
- newsroom fact-check desks counted as ordinary news;
- a forecast's "by 2035" dated the claim, and set WHO's own debunk aside;
- every YouTube link was "2 characters from youturn.in";
- Azure's content filter refused terror news and nothing asked again.

Each rule below is held with crafted evidence, offline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.domain import (
    Action,
    ClaimStatus,
    ClaimType,
    CoverageExpectation,
    Credibility,
    Direction,
    EvidenceKind,
    Importance,
    MatchBasis,
    Method,
    Severity,
    Tier,
)
from app.domain.enums import Relation
from app.domain.evidence import NARROWER_SCOPE, is_narrower_scope, is_partial_scope
from app.extraction.model_wire import WireFormat
from app.observability.logging import _PAYLOAD_KEY
from app.security.fetcher import FetchFailure, FetchResult
from app.sources.base import SourceSnapshot, current_reference_date
from app.sources.credibility import SourceCredibility
from app.sources.reasoning import (
    _CHECK_SOURCES_INSTRUCTION,
    _CHECK_SOURCES_SCHEMA,
    _SYSTEM_INSTRUCTION,
    ATTRIBUTED_SUPPORT,
    ModelRoute,
    Passage,
    PassageReasoner,
    SourceCheck,
    SourceReading,
    _ReasoningResponse,
    event_years,
    is_attributed_support,
    older_than_the_claim,
)
from app.sources.risk import detect_typosquat
from app.sources.verification import SourceVerification, _other_occurrence
from app.sources.websearch import WebSearchResolver
from app.verdict.engine import blocks_clearance, decide, holds_back, is_central, roll_up
from tests.unit.factories import claim, evidence

# --------------------------------------------------------------------- helpers


def _item(read: str, host: str = "thehindu.com", **overrides: Any) -> Any:
    """A web source as the first reader left it."""
    direction, metric = {
        "supports": (Direction.SUPPORTS, "passage_entailment: r"),
        "contradicts": (Direction.CONTRADICTS, "passage_entailment: r"),
        "narrower": (Direction.CONTEXTUALIZES, f"{NARROWER_SCOPE}: r"),
        "attributed": (Direction.CONTEXTUALIZES, f"{ATTRIBUTED_SUPPORT}: r"),
        "context": (Direction.CONTEXTUALIZES, "passage_entailment: r"),
    }[read]
    return evidence(
        kind=EvidenceKind.CORROBORATION,
        direction=direction,
        tier=Tier.D,
        method=Method.PASSAGE_ENTAILMENT,
        basis=MatchBasis(metric=metric, value=0.9, threshold=0.0),
        citation_url=f"https://www.{host}/story",
        publisher=host,
        **overrides,
    )


class _Checker:
    """Answers the source check with one reading for every source, and records them."""

    def __init__(self, verdict: str | None, **reading: Any) -> None:
        self.verdict = verdict
        self.reading = {"addresses_claim": True, **reading}
        self.sent: list[tuple[str, str]] = []

    async def check_sources(self, claim_text: str, sources: list[tuple[str, str]]) -> Any:
        self.sent = sources
        if self.verdict is None:
            return None
        return SourceCheck(
            readings={
                i: SourceReading(verdict=self.verdict, reason="why", **self.reading)
                for i in range(len(sources))
            },
            explanation="",
        )


class _Ranker:
    def credibility(self, _url: str | None) -> Credibility:
        return Credibility.MEDIUM


def _verified(checker: _Checker, items: list[Any], text: str = "A claim.") -> Any:
    return asyncio.run(
        SourceVerification(checker=checker, ranker=_Ranker()).check(claim(text=text), items)
    )


# ------------------------------------------------- 1. the checking bug


class TestACheckThatSaysTrueKeepsTheSupport:
    """Rising Kashmir's report of the Budgam encounter, India Today's of the EOS-05
    launch from Sriharikota and The Hindu's of the Koder House fire were read as
    narrower, the check said TRUE about the claim, and each was rejected."""

    @pytest.mark.parametrize("read", ["narrower", "attributed", "supports"])
    def test_true_about_the_claim_is_support(self, read: str) -> None:
        verified = _verified(_Checker("TRUE"), [_item(read)])

        [kept] = verified.evidence
        assert kept.direction is Direction.SUPPORTS
        assert not is_narrower_scope(kept.match_basis.metric)
        assert not is_attributed_support(kept.match_basis.metric)
        assert verified.rejected == 0

    def test_true_but_about_something_else_is_still_rejected(self) -> None:
        verified = _verified(_Checker("TRUE", addresses_claim=False), [_item("narrower")])

        assert verified.evidence == []

    def test_a_contradiction_the_check_calls_true_is_not_turned_into_support(self) -> None:
        verified = _verified(_Checker("TRUE"), [_item("contradicts")])

        assert verified.evidence == []

    def test_the_outcome_names_what_the_reader_said(self, caplog: Any) -> None:
        with caplog.at_level(logging.INFO, logger="factify.sources.verification"):
            _verified(_Checker("TRUE"), [_item("narrower")])

        logged = json.dumps([getattr(r, "__dict__", {}) for r in caplog.records], default=str)
        assert "kept (supports; read narrower)" in logged


class TestANarrowerReadingTheCheckCallsPartly:
    """The comment said a narrower source the check agreed was PARTLY is kept; the
    code also wanted "states a detail differently", and four were thrown away."""

    def test_nothing_stated_differently_is_part_of_the_claim(self) -> None:
        """A smaller version states something smaller. Two reports each carrying half
        of a fire officer's account of the Koder House fire, and three that did not
        say Baghel "repeatedly" alleged a conspiracy, were kept as smaller versions
        and two true reports read "partly true" (2026-10-02). They are kept as what
        they are: part of the claim - not narrower, not support."""
        checker = _Checker("PARTLY", smaller_version=True, states_differently=False)

        [kept] = _verified(checker, [_item("narrower")]).evidence

        assert kept.direction is Direction.CONTEXTUALIZES
        assert not is_narrower_scope(kept.match_basis.metric)
        assert is_partial_scope(kept.match_basis.metric)

    def test_a_smaller_version_states_something_smaller(self) -> None:
        checker = _Checker("PARTLY", smaller_version=True, states_differently=True)

        [kept] = _verified(checker, [_item("narrower")]).evidence

        assert is_narrower_scope(kept.match_basis.metric)

    def test_one_that_only_leaves_details_out_is_support(self) -> None:
        checker = _Checker("PARTLY", core_established=True)

        [kept] = _verified(checker, [_item("narrower")]).evidence

        assert kept.direction is Direction.SUPPORTS

    def test_neither_smaller_nor_the_core_is_rejected(self) -> None:
        """The Atal Pension Yojana against a scam's "Atal Free Pension Scheme"."""
        checker = _Checker("PARTLY", addresses_claim=False, states_differently=True)

        assert _verified(checker, [_item("narrower")]).evidence == []

    def test_another_group_of_people_is_never_a_smaller_version(self) -> None:
        checker = _Checker("PARTLY", smaller_version=True, other_group=True)

        assert _verified(checker, [_item("narrower")]).evidence == []

    @pytest.mark.parametrize("verdict", ["PARTLY", "UNCLEAR"])
    @pytest.mark.parametrize("differs", [True, False])
    def test_a_smaller_version_with_the_core_is_never_full_support(
        self, verdict: str, differs: bool
    ) -> None:
        """Two reports of a proposal for "Govt has approved Rs 5,000 a month for every
        woman": both readers found a smaller version, and the check's "the core is
        established" must not turn them into support that clears the forward -
        whatever it answered on stating a detail differently. A proposal for a
        decision is stated differently (the check is told so)."""
        checker = _Checker(
            verdict, smaller_version=True, core_established=True, states_differently=differs
        )

        kept = _verified(checker, [_item("narrower"), _item("narrower", "ndtv.com")]).evidence

        assert all(e.direction is not Direction.SUPPORTS for e in kept)
        if verdict == "PARTLY" and differs:
            assert len(kept) == 2
            assert all(is_narrower_scope(e.match_basis.metric) for e in kept)

    def test_two_such_reports_leave_the_forward_partly_true(self) -> None:
        checker = _Checker(
            "PARTLY", smaller_version=True, core_established=True, states_differently=True
        )
        kept = _verified(checker, [_item("narrower"), _item("narrower", "ndtv.com")]).evidence

        decision = decide(claim(independent_origin_count=0), kept)

        assert decision.status is ClaimStatus.MISLEADING_CONTEXT

    def test_the_check_is_told_a_proposal_is_stated_differently(self) -> None:
        told = " ".join(_CHECK_SOURCES_INSTRUCTION.split())

        assert "a proposal, plan, demand or expectation where the claim says decided" in told
        assert "some, most or part where the claim says all, every or the whole" in told
        assert "a passage that states none of them differently is never one" in told


class TestAnAttributedReadingTheCheckCallsPartly:
    """A politician's claim the article keeps its distance from is support only on the
    check's own finding that the core is established - never on PARTLY alone."""

    def test_another_group_of_people_is_not_support(self) -> None:
        checker = _Checker("PARTLY", other_group=True)

        assert _verified(checker, [_item("attributed")]).evidence == []

    def test_partly_without_the_core_is_not_support(self) -> None:
        assert _verified(_Checker("PARTLY"), [_item("attributed")]).evidence == []

    def test_partly_with_the_core_is_support(self) -> None:
        [kept] = _verified(
            _Checker("PARTLY", core_established=True), [_item("attributed")]
        ).evidence

        assert kept.direction is Direction.SUPPORTS

    def test_a_smaller_version_stated_differently_is_narrower(self) -> None:
        checker = _Checker("PARTLY", smaller_version=True, states_differently=True)

        [kept] = _verified(checker, [_item("attributed")]).evidence

        assert is_narrower_scope(kept.match_basis.metric)

    def test_a_plain_support_keeps_its_old_rule(self) -> None:
        """Read as support and nothing stated differently: India Today on the
        Aditya-L1 launch, without naming the launch site."""
        [kept] = _verified(_Checker("PARTLY"), [_item("supports")]).evidence

        assert kept.direction is Direction.SUPPORTS


# --------------------------------------- 4. one missing detail is not a rejection


class TestAReportThatLeavesOutOneDetail:
    """Six reports of the 2013 Jhiram Ghati ambush were each UNCLEAR for not naming the
    Darbha police station; the Guardian and ESPN on City's misstated accounts for not
    repeating "2009-2018"."""

    CLAIM = (
        "Maoists ambushed a convoy of Congress leaders on May 25, 2013, on a national "
        "highway in Jhiram Ghati under the Darbha police station limits."
    )

    @pytest.mark.parametrize("read", ["supports", "narrower", "attributed"])
    def test_the_core_confirmed_is_support(self, read: str) -> None:
        checker = _Checker("UNCLEAR", core_established=True)

        [kept] = _verified(checker, [_item(read)], self.CLAIM).evidence

        assert kept.direction is Direction.SUPPORTS

    def test_six_reports_carry_the_claim(self) -> None:
        hosts = ["moneycontrol.com", "thequint.com", "timesofindia.com", "thewire.in"]
        items = [_item("narrower", host) for host in hosts]

        verified = _verified(_Checker("UNCLEAR", core_established=True), items, self.CLAIM)

        assert len(verified.evidence) == 4
        assert all(e.direction is Direction.SUPPORTS for e in verified.evidence)

    def test_a_detail_stated_differently_still_rejects(self) -> None:
        checker = _Checker("UNCLEAR", core_established=True, states_differently=True)

        assert _verified(checker, [_item("supports")], self.CLAIM).evidence == []

    def test_without_the_core_it_is_still_unclear(self) -> None:
        assert _verified(_Checker("UNCLEAR"), [_item("supports")], self.CLAIM).evidence == []

    def test_a_contradiction_is_never_rescued_as_support(self) -> None:
        checker = _Checker("UNCLEAR", core_established=True)

        assert _verified(checker, [_item("contradicts")], self.CLAIM).evidence == []

    def test_the_check_is_asked_for_it_before_its_verdict(self) -> None:
        item = _CHECK_SOURCES_SCHEMA["properties"]["sources"]["items"]
        order = list(item["properties"])

        assert "core_established" in item["required"]
        assert order.index("core_established") < order.index("verdict")
        assert "core_established" in _CHECK_SOURCES_INSTRUCTION


class TestAnAttributedSupportNeedsTheCheck:
    def test_it_is_sent_to_the_check(self) -> None:
        checker = _Checker("UNCLEAR")

        verified = _verified(checker, [_item("attributed"), _item("context", "ndtv.com")])

        assert len(checker.sent) == 1
        assert verified.evidence == []
        assert verified.context_only == 1

    def test_without_a_check_it_is_not_cited(self) -> None:
        """A check that could not run keeps the evidence it has, unweighed; a support
        held back as someone else's word was never evidence until confirmed."""
        verified = _verified(_Checker(None), [_item("attributed"), _item("narrower", "x.in")])

        assert verified.checked is False
        assert [is_narrower_scope(e.match_basis.metric) for e in verified.evidence] == [True]


# ----------------------------------------------- 2 and 3. the reader's demotions


def _judge(
    relation: str,
    *,
    asserted_by: str = "THE_ARTICLE",
    basis: str = "DENIES",
    scope: str = "FULL",
    claim_type: str = "EVENT",
    claim_text: str = "A claim.",
    fact_check: bool = False,
) -> Any:
    body = "The quote attributed to him is fabricated, and he made no such statement."
    response = _ReasoningResponse.model_validate(
        {
            "judgements": [
                {
                    "passage_index": 0,
                    "relation": relation,
                    "asserted_by": asserted_by,
                    "contradiction_basis": basis,
                    "scope": scope,
                    "quote": body,
                    "reason": "r",
                    "relevance": 0.9,
                }
            ]
        }
    )
    reasoner = PassageReasoner.__new__(PassageReasoner)
    reasoner._model_id = "test"
    return reasoner._verify(
        response,
        [Passage(index=0, text=body, char_start=0, char_end=len(body))],
        claim_type=claim_type,
        claim_text=claim_text,
        fact_check=fact_check,
    )


class TestAFakeQuoteCanBeCalledFalse:
    """Alt News, BOOM and Bhatia's own denial of the "dimaagi Naxal" quote, and WHO's
    clarification that it issued no cancer warning, were all demoted to context."""

    QUOTE = (
        'Gaurav Bhatia said that Swatantra Bhardwaj is a "dimaagi Naxal" and has nothing '
        "to do with the BJP government."
    )

    def test_a_denial_that_it_was_said_contradicts(self) -> None:
        [judged] = _judge("CONTRADICTS", claim_type="ATTRIBUTION", claim_text=self.QUOTE).judgements

        assert judged.relation is Relation.CONTRADICTS
        assert judged.basis == "DENIES"

    def test_for_a_quote_too(self) -> None:
        [judged] = _judge("CONTRADICTS", claim_type="QUOTE", claim_text=self.QUOTE).judgements

        assert judged.relation is Relation.CONTRADICTS

    def test_an_incompatible_account_counts_only_from_a_fact_check(self) -> None:
        news = _judge(
            "CONTRADICTS", basis="INCOMPATIBLE", claim_type="ATTRIBUTION", claim_text=self.QUOTE
        )
        desk = _judge(
            "CONTRADICTS",
            basis="INCOMPATIBLE",
            claim_type="ATTRIBUTION",
            claim_text=self.QUOTE,
            fact_check=True,
        )

        assert news.judgements[0].relation is Relation.CONTEXTUALIZES
        assert desk.judgements[0].relation is Relation.CONTRADICTS

    def test_refuting_what_was_said_is_still_not_a_contradiction(self) -> None:
        outcome = _judge(
            "CONTRADICTS",
            basis="REFUTES_REPORTED_CONTENT",
            claim_type="ATTRIBUTION",
            claim_text=self.QUOTE,
        )

        assert outcome.judgements == ()

    def test_the_reader_is_told_what_a_denial_of_a_quote_is(self) -> None:
        assert "the quote is fabricated or misattributed" in _SYSTEM_INSTRUCTION
        assert "misattributed" in _CHECK_SOURCES_INSTRUCTION


class TestNewsWrittenTheArmySaid:
    def test_someone_elses_word_is_held_for_the_check(self) -> None:
        [judged] = _judge("SUPPORTS", asserted_by="SOMEONE_ELSE").judgements

        assert judged.relation is Relation.CONTEXTUALIZES
        assert judged.attributed is True
        assert judged.marker == ATTRIBUTED_SUPPORT

    def test_a_statement_nobody_makes_is_plain_context(self) -> None:
        [judged] = _judge("SUPPORTS", asserted_by="NOBODY").judgements

        assert judged.relation is Relation.CONTEXTUALIZES
        assert judged.attributed is False
        assert judged.marker == "passage_entailment"

    def test_the_reader_is_told_how_news_is_written(self) -> None:
        assert '"one terrorist was killed, the Army said"' in _SYSTEM_INSTRUCTION
        assert "the Army said" in _CHECK_SOURCES_INSTRUCTION

    def test_leaving_a_detail_out_is_not_a_narrower_version(self) -> None:
        assert "Not mentioning a detail is not a smaller version" in _SYSTEM_INSTRUCTION

    def test_the_web_resolver_records_the_marker(self) -> None:
        snapshot = _snapshot("https://www.thehindu.com/news/national/budgam/article1.ece")

        class _Reader:
            async def judge(self, *_args: object, **_kwargs: object) -> object:
                return SimpleNamespace(
                    succeeded=True,
                    reason=None,
                    passages_read=1,
                    best=lambda: SimpleNamespace(
                        relation=Relation.CONTEXTUALIZES,
                        quote=snapshot.text[:60],
                        reason="the Army said",
                        relevance=0.9,
                        narrower=False,
                        basis="",
                        marker=ATTRIBUTED_SUPPORT,
                    ),
                )

        relation = asyncio.run(_resolver(_Reader()).relate(claim(), snapshot))

        assert is_attributed_support(relation.metric)


class TestTheCitedPassage:
    def test_a_support_on_someones_word_outranks_plain_context(self) -> None:
        """Cited behind a more relevant paragraph about the area, "police said one
        terrorist was killed" never reached the source check."""
        from app.sources.reasoning import PassageJudgement, ReasoningOutcome

        def judged(relevance: float, *, attributed: bool) -> PassageJudgement:
            return PassageJudgement(
                passage_index=0,
                relation=Relation.CONTEXTUALIZES,
                quote="q",
                reason="r",
                relevance=relevance,
                char_start=0,
                char_end=1,
                attributed=attributed,
            )

        area, police = judged(0.9, attributed=False), judged(0.8, attributed=True)

        assert ReasoningOutcome(judgements=(area, police)).best() is police


class TestAFactCheckOfWhatWasSaidIsNotADenialThatItWasSaid:
    """ "Modi said there are no detention centres in India" is true; a fact-check
    rating the statement false agrees that he said it."""

    def test_the_check_is_told(self) -> None:
        assert "does not dispute that they said it" in _CHECK_SOURCES_INSTRUCTION
        assert "UNCLEAR, never FALSE" in _CHECK_SOURCES_INSTRUCTION

    def test_the_reader_is_told(self) -> None:
        assert "does not dispute that they said it, is REFUTES_REPORTED_CONTENT" in (
            " ".join(_SYSTEM_INSTRUCTION.split())
        )

    def test_and_the_check_settles_it(self) -> None:
        """Kept by the reader as a fact-check's contradiction, rejected when the check
        answers UNCLEAR for it."""
        quote = _item("contradicts", "indiatoday.in")

        assert _verified(_Checker("UNCLEAR"), [quote]).evidence == []


class TestTheLogSaysWhichRuleDemoted:
    def test_each_rule_is_counted_by_name(self, caplog: Any) -> None:
        with caplog.at_level(logging.INFO, logger="factify.sources.reasoning"):
            _judge("SUPPORTS", scope="NARROWER")

        [record] = [r for r in caplog.records if r.getMessage() == "judgements demoted to context"]
        assert record.__dict__[_PAYLOAD_KEY]["detail"]["rules"] == {"scope": 1}
        assert not any("someone else's claim" in r.getMessage() for r in caplog.records)


# ------------------------------------------------------- 8. the year guard


class TestAForecastYearIsNotWhenItHappened:
    CLAIM = (
        "The World Health Organization has warned that if adulteration is not stopped, "
        "87 percent of Indians may suffer from cancer by 2035."
    )

    def test_a_target_year_is_not_an_event_year(self) -> None:
        assert event_years(self.CLAIM) == set()
        assert event_years("India launched EOS-05 in 2026 and plans more by 2030.") == {2026}
        assert event_years("2035 तक 87 प्रतिशत भारतीयों को कैंसर") == set()
        assert event_years("by the end of 2027 every village will be connected") == set()

    def test_the_quints_debunk_is_not_set_aside(self) -> None:
        quint = evidence(
            kind=EvidenceKind.CORROBORATION,
            direction=Direction.CONTRADICTS,
            citation_url="https://www.thequint.com/news/webqoof/who-cancer-milk",
            source_excerpt="WHO has not issued any such advisory about milk adulteration.",
        ).model_copy(update={"published_on": date(2018, 10, 20)})

        assert _other_occurrence(quint, claim(text=self.CLAIM)) is None

    def test_a_real_event_year_still_guards(self) -> None:
        old = evidence(
            kind=EvidenceKind.CORROBORATION,
            citation_url="https://www.thehindu.com/x",
            source_excerpt="ISRO launched the satellite.",
        ).model_copy(update={"published_on": date(2019, 1, 1)})

        assert _other_occurrence(old, claim(text="ISRO launched EOS-05 in 2026.")) is not None

    def test_the_readers_own_guard_agrees(self) -> None:
        assert not older_than_the_claim(self.CLAIM, "no such advisory", date(2026, 8, 3))
        assert older_than_the_claim("Notes can be exchanged in 2026.", "in 2016", None)

    def test_a_target_still_dates_the_claim(self) -> None:
        """A 2026 page saying India aims for 500 GW by 2030: the 2021 reports that set
        the target are not "an earlier occurrence" of an undated claim."""
        cop26 = evidence(
            kind=EvidenceKind.CORROBORATION,
            citation_url="https://www.thehindu.com/cop26",
            source_excerpt="India will reach 500 GW of non-fossil capacity by 2030, Modi said.",
        ).model_copy(update={"published_on": date(2021, 11, 2)})
        target = claim(
            text="India has set a target of 500 GW of non-fossil fuel capacity by 2030.",
            claim_type=ClaimType.EVENT,
        )

        token = current_reference_date.set(date(2026, 9, 30))
        try:
            assert _other_occurrence(cop26, target) is None
        finally:
            current_reference_date.reset(token)

    def test_an_undated_claim_still_guards(self) -> None:
        old = evidence(
            kind=EvidenceKind.CORROBORATION,
            citation_url="https://www.thehindu.com/old",
            source_excerpt="The Supreme Court issued notice to the Centre.",
        ).model_copy(update={"published_on": date(2020, 1, 1)})
        undated = claim(text="The Supreme Court issued notice to the Centre and the RBI.")

        token = current_reference_date.set(date(2026, 9, 30))
        try:
            assert _other_occurrence(old, undated) == "an earlier occurrence"
        finally:
            current_reference_date.reset(token)


# ------------------------------------------------- 7. newsroom fact-check desks


def _snapshot(url: str, title: str = "") -> SourceSnapshot:
    return SourceSnapshot(
        id="web:test",
        url=url,
        final_url=url,
        content_hash="sha256:test",
        fetched_at=datetime.now(UTC),
        text=(
            "The Army said one terrorist was killed in the encounter in Budgam on Tuesday "
            "night, after troops challenged suspects during a joint search operation."
        ),
        title=title,
    )


def _resolver(reasoner: Any = None) -> WebSearchResolver:
    return WebSearchResolver(
        fetcher=None,  # type: ignore[arg-type]
        reasoner=reasoner,
        provider="tavily",
        endpoint="https://example.invalid/search",
        api_key="k",
        credibility=SourceCredibility.load(),
    )


class TestANewsroomFactCheckDeskIsAFactCheck:
    @pytest.mark.parametrize(
        ("url", "title"),
        [
            (
                "https://www.thequint.com/news/webqoof/pmjdy-providing-direct-cash-fact-check",
                "PMJDY is not giving direct cash",
            ),
            (
                "https://www.indiatoday.in/fact-check/story/viral-claim-about-who-1234",
                "No, WHO did not issue this warning",
            ),
            ("https://www.thehindu.com/news/national/article1.ece", "Fact Check: no such scheme"),
            (
                "https://timesofindia.indiatimes.com/times-fact-check/news/x/articleshow/1.cms",
                "Viral video of a flooded station is old",
            ),
            ("https://factcheck.afp.com/doc.afp.com.36XY", "Old photo shared as new"),
            (
                "https://www.news18.com/india/viral-claim-1.html",
                "No such scheme exists | Fact Check",
            ),
        ],
    )
    def test_a_desk_page_is_tier_c(self, url: str, title: str) -> None:
        tier, kind, method = _resolver().classify(_snapshot(url, title))

        assert (tier, kind, method) == (Tier.C, EvidenceKind.FACT_CHECK, Method.CLAIM_REVIEW)

    @pytest.mark.parametrize(
        ("url", "title"),
        [
            # A news headline with a fact-checker's words is still news.
            ("https://www.indiatoday.in/india/story/fake-call-centre-busted-1", "Fake call centre"),
            ("https://www.thequint.com/news/politics/viral-video-row", "Viral video row"),
            # A desk's address on a host we do not list is not made credible by it.
            ("https://someblog.example/fact-check/x", "Fact Check: x"),
            # News about fact-check units is news: the words in a slug or a headline
            # are not the desk's label.
            (
                "https://www.thehindu.com/news/national/bombay-hc-strikes-down-fact-check-unit-rules/article1.ece",
                "Bombay HC strikes down fact-check unit rules",
            ),
            (
                "https://indianexpress.com/article/india/govt-factcheck-unit-notified-9123/",
                "Govt notifies factcheck unit under IT Rules",
            ),
            (
                "https://www.thehindu.com/news/national/article2.ece",
                "Fact-check unit: Supreme Court stays the Centre's notification",
            ),
            ("https://www.ndtv.com/india-news/what-is-a-fact-check", "What is a fact check?"),
        ],
    )
    def test_anything_else_is_reporting(self, url: str, title: str) -> None:
        _, kind, _ = _resolver().classify(_snapshot(url, title))

        assert kind is EvidenceKind.CORROBORATION

    def test_the_reader_is_told_it_is_reading_a_fact_check(self) -> None:
        seen: dict[str, object] = {}

        class _Reader:
            async def judge(self, *_args: object, **kwargs: object) -> object:
                seen.update(kwargs)
                return SimpleNamespace(
                    succeeded=True, reason=None, passages_read=1, best=lambda: None
                )

        url = "https://www.thequint.com/news/webqoof/fake-quote-gaurav-bhatia"
        asyncio.run(_resolver(_Reader()).relate(claim(), _snapshot(url, "Fake quote")))

        assert seen["fact_check"] is True


# ----------------------------------------------------- 9. the look-alike warning


class TestALookAlikeWarning:
    CREDIBLE = frozenset({"youturn.in", "thehindu.com", "bbc.co.uk"})

    @pytest.mark.parametrize(
        "host", ["www.youtube.com", "m.youtube.com", "youtube.com", "news.bbc.co.uk", "youturn.in"]
    )
    def test_a_known_platform_or_listed_host_imitates_nothing(self, host: str) -> None:
        assert detect_typosquat(host, self.CREDIBLE) is None

    def test_a_real_look_alike_is_still_flagged(self) -> None:
        assert detect_typosquat("youturns.in", self.CREDIBLE) is not None
        assert detect_typosquat("thehindu.co.in", self.CREDIBLE) is not None


# ------------------------------------------------------- 5. severity, rule 4b


class TestOnlyTheHeadlineHoldsTheVerdictBack:
    def test_severity_alone_does_not_block_a_clearance(self) -> None:
        detail = claim(importance=Importance.SUPPORTING_DETAIL, severity=Severity.CRITICAL)

        assert not blocks_clearance(detail)
        assert blocks_clearance(claim(importance=Importance.HEADLINE, severity=Severity.LOW))

    def test_but_a_critical_claim_is_still_central(self) -> None:
        detail = claim(importance=Importance.SUPPORTING_DETAIL, severity=Severity.CRITICAL)

        assert is_central(detail)
        assert not is_central(claim(importance=Importance.BACKGROUND, severity=Severity.HIGH))

    @staticmethod
    def _headline() -> Any:
        headline = claim(
            importance=Importance.HEADLINE,
            severity=Severity.CRITICAL,
            independent_origin_count=3,
            document_count=3,
        )
        hosts = ("indiatoday.in", "theprint.in", "thehindu.com")
        return headline, decide(headline, [_item("supports", host) for host in hosts])

    @staticmethod
    def _detail(n: int, **fields: Any) -> Any:
        return claim(
            claim_id=f"cl_{n}",
            importance=Importance.SUPPORTING_DETAIL,
            severity=Severity.CRITICAL,
            **fields,
        )

    def test_news_4_reads_true(self) -> None:
        """Headline carried by three outlets; CRITICAL details each reported, too thinly
        to decide (one outlet) or in dispute (27 or 29 killed)."""
        headline, supported = self._headline()
        thin = [self._detail(n, independent_origin_count=1, document_count=1) for n in (2, 5)]
        toll = self._detail(3)
        conflicting = decide(
            toll, [_item("supports", "deccanchronicle.com"), _item("contradicts", "indiatoday.in")]
        )

        outcome = roll_up(
            [
                (headline, supported),
                (thin[0], decide(thin[0], [_item("supports", "thequint.com")])),
                (toll, conflicting),
                (thin[1], decide(thin[1], [_item("supports", "thehindu.com")])),
            ]
        )

        assert conflicting.status is ClaimStatus.UNVERIFIED
        assert outcome.action is Action.SAFE_TO_SHARE
        assert "including 3 critical" in outcome.reason
        assert "minor" not in outcome.reason

    def test_a_critical_detail_nothing_reports_still_holds_it_back(self) -> None:
        """ "Papaya leaf juice cures dengue in two days" under a true headline that
        Delhi's hospitals now treat dengue free."""
        headline, supported = self._headline()
        remedy = self._detail(2)

        outcome = roll_up([(headline, supported), (remedy, decide(remedy, []))])

        assert outcome.action is Action.SEND_TO_REVIEW
        assert holds_back(remedy, decide(remedy, []))

    def test_but_never_background(self) -> None:
        headline, supported = self._headline()
        history = claim(
            claim_id="cl_2", importance=Importance.BACKGROUND, severity=Severity.CRITICAL
        )

        outcome = roll_up([(headline, supported), (history, decide(history, []))])

        assert outcome.action is Action.SAFE_TO_SHARE

    def test_a_high_detail_is_still_minor(self) -> None:
        headline, supported = self._headline()
        aside = claim(claim_id="cl_2", importance=Importance.SUPPORTING_DETAIL)

        outcome = roll_up([(headline, supported), (aside, decide(aside, []))])

        assert outcome.action is Action.SAFE_TO_SHARE
        assert "1 minor detail(s)" in outcome.reason


class TestTwoCautiousOutletsDoNotOutvoteAWire:
    """Reuters reported the Delhi chief minister's account as the claim put it; The
    Hill and Hindustan Times more cautiously. The case read partly true."""

    def _narrower(self, host: str, credibility: Credibility = Credibility.MEDIUM) -> Any:
        return _item("narrower", host).model_copy(update={"credibility": credibility})

    def test_a_highly_credible_full_support_holds_rule_4b_off(self) -> None:
        reuters = _item("supports", "reuters.com").model_copy(
            update={"credibility": Credibility.HIGH}
        )

        decision = decide(
            claim(independent_origin_count=1, document_count=1),
            [reuters, self._narrower("thehill.com"), self._narrower("hindustantimes.com")],
        )

        assert decision.status is ClaimStatus.UNVERIFIED

    def test_unless_an_equally_credible_source_shows_the_smaller_version(self) -> None:
        reuters = _item("supports", "reuters.com").model_copy(
            update={"credibility": Credibility.HIGH}
        )

        decision = decide(
            claim(independent_origin_count=1, document_count=1),
            [reuters, self._narrower("bbc.com", Credibility.HIGH)],
        )

        assert decision.status is ClaimStatus.MISLEADING_CONTEXT

    def test_without_one_two_narrower_publishers_still_decide(self) -> None:
        decision = decide(
            claim(), [self._narrower("thehill.com"), self._narrower("hindustantimes.com")]
        )

        assert decision.status is ClaimStatus.MISLEADING_CONTEXT


# ----------------------------------------------- 6. "treat it as likely false"


def _outcome(
    status: ClaimStatus, importance: Importance, items: list[Any], note: str | None
) -> Any:
    from app.orchestration.pipeline import ClaimOutcome
    from app.verdict.engine import Decision
    from app.verdict.strength import evidence_strength

    return ClaimOutcome(
        claim=claim(importance=importance),
        decision=Decision(
            status=status,
            rule_id="rule.x",
            reason="r",
            supporting_evidence_ids=tuple(e.id for e in items) if status.is_decisive else (),
        ),
        strength=evidence_strength([]),
        evidence=items,
        explanation=note,
    )


class TestLikelyFalseOnlyWhereNothingReportsIt:
    def _note(self, items: list[Any], **fields: Any) -> str | None:
        from app.orchestration.pipeline import _unreported_note

        subject = claim(coverage_expectation=CoverageExpectation.HIGH, **fields)
        return _unreported_note(subject, items)

    def test_nothing_found_still_says_so(self) -> None:
        assert self._note([]) is not None

    @pytest.mark.parametrize("read", ["contradicts", "narrower"])
    def test_a_source_that_reports_it_otherwise_silences_it(self, read: str) -> None:
        """Beside The Quint's debunk of the same PMJDY forward (fake-1)."""
        assert self._note([_item(read)]) is None

    def test_never_for_an_opinion(self) -> None:
        """An unchecked "America deserved 9-Eleven" was called likely false (media-8)."""
        assert self._note([], claim_type=ClaimType.OPINION) is None
        assert self._note([], claim_type=ClaimType.PREDICTION) is None

    def test_never_for_a_critical_detail(self) -> None:
        """yt-2's misstated-accounts detail spoke for a case Reuters and BBC carried."""
        detail = {"importance": Importance.SUPPORTING_DETAIL, "severity": Severity.CRITICAL}
        assert self._note([], **detail) is None

    def test_a_confirmed_story_drops_it_from_every_claim(self) -> None:
        """yt-2: Reuters and the BBC carried the headline, and a detail of the same
        story read "treat it as likely false"."""
        from app.orchestration.pipeline import _UNREPORTED, _without_unreported_notes

        outcomes = [
            _outcome(ClaimStatus.SUPPORTED, Importance.HEADLINE, [_item("supports")], None),
            _outcome(ClaimStatus.UNVERIFIED, Importance.MAIN_THESIS, [], _UNREPORTED["en"]),
        ]

        _without_unreported_notes(outcomes)

        assert outcomes[1].explanation is None

    def test_a_supported_detail_does_not_vouch_for_an_invented_scheme(self) -> None:
        """The "National Sports Scholarship 2026-27" flyer: "apply on the National
        Scholarship Portal", supported by the portal itself, must not take "likely
        false" off the invented scheme it was hung on."""
        from app.orchestration.pipeline import _UNREPORTED, _without_unreported_notes

        portal = _item("supports", "scholarships.gov.in").model_copy(
            update={"credibility": Credibility.HIGH}
        )
        outcomes = [
            _outcome(ClaimStatus.UNVERIFIED, Importance.HEADLINE, [], _UNREPORTED["en"]),
            _outcome(ClaimStatus.UNVERIFIED, Importance.SUPPORTING_DETAIL, [portal], None),
            _outcome(ClaimStatus.SUPPORTED, Importance.SUPPORTING_DETAIL, [portal], None),
        ]

        _without_unreported_notes(outcomes)

        assert outcomes[0].explanation == _UNREPORTED["en"]

    def test_a_supported_aside_does_not_vouch_for_an_invented_headline(self) -> None:
        from app.orchestration.pipeline import _UNREPORTED, _without_unreported_notes

        outcomes = [
            _outcome(ClaimStatus.UNVERIFIED, Importance.HEADLINE, [], _UNREPORTED["hi"]),
            _outcome(ClaimStatus.SUPPORTED, Importance.BACKGROUND, [_item("supports")], None),
        ]

        _without_unreported_notes(outcomes)

        assert outcomes[0].explanation == _UNREPORTED["hi"]


# --------------------------------------------------- 10. the content filter


class _Wire:
    """A provider that refuses the first request on its content policy."""

    def __init__(self, first: Any, *, gemini: bool = False) -> None:
        self.first = first
        self.gemini = gemini
        self.bodies: list[dict[str, Any]] = []
        self.urls: list[str] = []
        self.answer: dict[str, Any] = {"judgements": []}

    async def post_json(self, url: str, body: dict[str, Any], **_kwargs: Any) -> Any:
        self.bodies.append(body)
        self.urls.append(url)
        if len(self.bodies) == 1:
            return self.first
        return _answered(url, self.answer, gemini=self.gemini)


def _answered(url: str, answer: dict[str, Any], *, gemini: bool = False) -> FetchResult:
    text = json.dumps(answer)
    shape = (
        {"candidates": [{"content": {"parts": [{"text": text}]}}]}
        if gemini
        else {"choices": [{"message": {"content": text}}]}
    )
    envelope = json.dumps(shape).encode()
    return FetchResult(
        url=url,
        final_url=url,
        status_code=200,
        content_type="application/json",
        body=envelope,
        byte_count=len(envelope),
        fetched_at=datetime.now(UTC),
    )


class _Governor:
    def __init__(self) -> None:
        self.grants: list[str] = []

    async def acquire(self, provider: str) -> object:
        self.grants.append(provider)
        return object()


_FILTERED = FetchFailure(
    url="https://x.openai.azure.com/openai/v1/chat/completions",
    reason=(
        "provider returned 400 (content_filter: The response was filtered due to the "
        "prompt triggering Azure OpenAI's content management policy.)"
    ),
    kind="provider_error",
)


AZURE = "https://x.openai.azure.com/openai/v1/chat/completions"


def _reasoner(wire: _Wire, governor: _Governor, fallback: str | ModelRoute | None) -> Any:
    route = (
        ModelRoute(endpoint=AZURE, api_key="k", model_id=fallback, api_format=WireFormat.OPENAI)
        if isinstance(fallback, str)
        else fallback
    )
    return PassageReasoner(
        fetcher=wire,
        governor=governor,
        endpoint=AZURE,
        api_key="k",
        model_id="gpt-5.6-luna",
        api_format=WireFormat.OPENAI,
        fallback=route,
    )


def _passages() -> list[Passage]:
    text = "Terrorists opened fire and one terrorist was killed in the Budgam encounter."
    return [Passage(index=0, text=text, char_start=0, char_end=len(text))]


class TestAContentFilterRefusalIsAskedAgain:
    def test_the_fallback_model_reads_what_the_first_refused(self) -> None:
        wire, governor = _Wire(_FILTERED), _Governor()

        outcome = asyncio.run(
            _reasoner(wire, governor, "gpt-4.1-mini").judge("c", _passages(), screen=False)
        )

        assert outcome.succeeded
        assert outcome.model_id == "gpt-4.1-mini"
        assert [body["model"] for body in wire.bodies] == ["gpt-5.6-luna", "gpt-4.1-mini"]
        assert governor.grants == ["llm", "llm"]

    def test_the_fallback_may_be_another_provider(self) -> None:
        """The same Azure resource's content policy refused gpt-4.1-mini too, on the
        same Budgam passages (2026-10-02): another provider is the fallback that reads
        them, metered under its own name."""
        wire, governor = _Wire(_FILTERED, gemini=True), _Governor()
        gemini = ModelRoute(
            endpoint="https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            api_key="g",
            model_id="gemini-3.8-flash",
            api_format=WireFormat.GEMINI,
            provider="video_reader",
        )

        outcome = asyncio.run(
            _reasoner(wire, governor, gemini).judge("c", _passages(), screen=False)
        )

        assert outcome.succeeded
        assert outcome.model_id == "gemini-3.8-flash"
        assert "gemini-3.8-flash:generateContent" in wire.urls[1]
        assert governor.grants == ["llm", "video_reader"]

    def test_the_source_check_is_asked_again_too(self) -> None:
        wire = _Wire(_FILTERED)
        wire.answer = {
            "sources": [
                {
                    "index": 0,
                    "reason": "r",
                    "smaller_version": False,
                    "states_differently": False,
                    "other_group": False,
                    "addresses_claim": True,
                    "core_established": True,
                    "verdict": "UNCLEAR",
                }
            ]
        }
        answer = asyncio.run(
            _reasoner(wire, _Governor(), "gpt-4.1-mini").check_sources("c", [("p", "passage")])
        )

        assert answer is not None
        assert answer.readings[0].core_established is True

    def test_without_a_fallback_the_refusal_stands(self) -> None:
        wire = _Wire(_FILTERED)

        outcome = asyncio.run(
            _reasoner(wire, _Governor(), None).judge("c", _passages(), screen=False)
        )

        assert not outcome.succeeded
        assert "content_filter" in (outcome.reason or "")
        assert len(wire.bodies) == 1

    def test_another_failure_is_not_retried(self) -> None:
        timeout = FetchFailure(url="u", reason="request timed out", kind="timeout")
        wire = _Wire(timeout)

        outcome = asyncio.run(
            _reasoner(wire, _Governor(), "gpt-4.1-mini").judge("c", _passages(), screen=False)
        )

        assert not outcome.succeeded
        assert len(wire.bodies) == 1

    def test_the_same_model_is_not_a_fallback(self) -> None:
        wire = _Wire(_FILTERED)

        asyncio.run(
            _reasoner(wire, _Governor(), "gpt-5.6-luna").judge("c", _passages(), screen=False)
        )

        assert len(wire.bodies) == 1


def _withheld_answer(url: str = AZURE, *, gemini: bool = False) -> FetchResult:
    """A 200 whose answer the provider's filter withheld."""
    shape: dict[str, Any] = (
        {"candidates": [{"finishReason": "SAFETY"}]}
        if gemini
        else {"choices": [{"finish_reason": "content_filter", "message": {"content": None}}]}
    )
    envelope = json.dumps(shape).encode()
    return FetchResult(
        url=url,
        final_url=url,
        status_code=200,
        content_type="application/json",
        body=envelope,
        byte_count=len(envelope),
        fetched_at=datetime.now(UTC),
    )


class TestAWithheldAnswerIsARefusalToo:
    """Azure's filter also answers 200 with finish_reason "content_filter" and no
    content, which failed as "schema validation failed" and was never asked again."""

    def test_it_is_asked_of_the_fallback(self) -> None:
        wire = _Wire(_withheld_answer())

        outcome = asyncio.run(
            _reasoner(wire, _Governor(), "gpt-4.1-mini").judge("c", _passages(), screen=False)
        )

        assert outcome.succeeded
        assert [body["model"] for body in wire.bodies] == ["gpt-5.6-luna", "gpt-4.1-mini"]

    def test_without_a_fallback_it_says_why(self) -> None:
        outcome = asyncio.run(
            _reasoner(_Wire(_withheld_answer()), _Governor(), None).judge(
                "c", _passages(), screen=False
            )
        )

        assert not outcome.succeeded
        assert "content_filter" in (outcome.reason or "")
        assert "schema" not in (outcome.reason or "")

    def test_a_gemini_safety_stop_is_one(self) -> None:
        gemini = ModelRoute(
            endpoint="https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            api_key="g",
            model_id="gemini-3.8-flash",
            api_format=WireFormat.GEMINI,
        )
        wire = _Wire(_FILTERED)
        wire.answer = {}

        async def withheld(url: str, body: dict[str, Any], **_kwargs: Any) -> Any:
            wire.bodies.append(body)
            return _FILTERED if len(wire.bodies) == 1 else _withheld_answer(url, gemini=True)

        wire.post_json = withheld  # type: ignore[method-assign]
        outcome = asyncio.run(
            _reasoner(wire, _Governor(), gemini).judge("c", _passages(), screen=False)
        )

        assert not outcome.succeeded
        assert "SAFETY" in (outcome.reason or "")

    def test_an_ordinary_answer_is_untouched(self) -> None:
        wire = _Wire(_answered(AZURE, {"judgements": []}))

        outcome = asyncio.run(
            _reasoner(wire, _Governor(), "gpt-4.1-mini").judge("c", _passages(), screen=False)
        )

        assert outcome.succeeded
        assert len(wire.bodies) == 1


def test_the_versions_moved_so_old_answers_are_not_served() -> None:
    from app.sources.reasoning import REASONER_VERSION
    from app.sources.risk import VERSION as RISK_VERSION
    from app.sources.websearch import VERSION as SEARCH_VERSION
    from app.verdict.engine import RULE_VERSION

    for version in (REASONER_VERSION, RULE_VERSION, SEARCH_VERSION, RISK_VERSION):
        assert version >= "2026.10.03.1"
