"""True news reported in part is not "partly true" (re-test of 2026-10-02).

- Reports that each carried part of a claim, and stated none of it differently, were
  kept as smaller versions, and rule 4b made true reports "partly true": the Koder
  House fire (news-3), the Jhiram Ghati sentences (news-4), the RBI Governor's
  assessment (media-7). A smaller version states something smaller; leaving a detail
  out is part of the claim.
- A critical detail five outlets reported in part held news-4 back as though nothing
  had reported it.
- yt-2's headline was decided as narrower from three corpus items, and never searched.
- x-3's headline ended on one origin while The Tribune and Hindustan Times, stating its
  exact figure, were read the same minute for the claim beside it.

Each rule below is held with crafted evidence, offline.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.domain import (
    Action,
    ClaimStatus,
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
from app.domain.evidence import NARROWER_SCOPE, PARTIAL_SCOPE, is_partial_scope
from app.intake.normalizer import normalise_text
from app.orchestration.pipeline import Orchestrator, _reports_on, _search_settled
from app.sources.base import (
    SourceCandidate,
    SourceRelation,
    SourceSnapshot,
    current_check,
    current_follow_up,
    current_own_pages,
)
from app.sources.credibility import SourceCredibility
from app.sources.reasoning import SourceCheck, SourceReading
from app.sources.verification import SourceVerification, page_key
from app.sources.websearch import WebSearchResolver
from app.verdict.engine import (
    NARROWER_RULE,
    OUT_OF_CONTEXT_RULE,
    REPORTED_IN_PART_RULE,
    Decision,
    decide,
    holds_back,
    roll_up,
)
from app.verdict.explain import narrower_note
from tests.unit.factories import claim, evidence

pytestmark = pytest.mark.unit


def _item(read: str, host: str, **fields: Any) -> Any:
    metric = {
        "supports": "passage_entailment: r",
        "narrower": f"{NARROWER_SCOPE}: r",
        "partial": f"{PARTIAL_SCOPE}: does not say repeatedly",
    }[read]
    return evidence(
        kind=EvidenceKind.CORROBORATION,
        direction=Direction.SUPPORTS if read == "supports" else Direction.CONTEXTUALIZES,
        tier=Tier.D,
        method=Method.PASSAGE_ENTAILMENT,
        basis=MatchBasis(metric=metric, value=0.9, threshold=0.5),
        citation_url=f"https://www.{host}/story",
        publisher=host,
        credibility=Credibility.MEDIUM,
        **fields,
    )


class _Checker:
    def __init__(self, verdict: str, **reading: Any) -> None:
        self.verdict = verdict
        self.reading = {"addresses_claim": True, **reading}

    async def check_sources(self, claim_text: str, sources: list[tuple[str, str]]) -> Any:
        return SourceCheck(
            readings={
                i: SourceReading(verdict=self.verdict, reason="leaves the fine out", **self.reading)
                for i in range(len(sources))
            },
            explanation="",
        )


class _Ranker:
    def credibility(self, _url: str | None) -> Credibility:
        return Credibility.MEDIUM


def _verified(checker: _Checker, items: list[Any]) -> list[Any]:
    verified = asyncio.run(
        SourceVerification(checker=checker, ranker=_Ranker()).check(claim(), items)
    )
    return list(verified.evidence)


# ------------------------------------------------------------- the source check


class TestTheSourceCheck:
    @pytest.mark.parametrize("verdict", ["PARTLY", "UNCLEAR"])
    def test_a_narrower_reading_that_states_nothing_differently_is_part(self, verdict: str) -> None:
        """news-4: Deccan Chronicle, India Today and NIE report the sentences and
        leave out the charges and the fine: "read narrower, check said UNCLEAR"."""
        [kept] = _verified(_Checker(verdict), [_item("narrower", "deccanchronicle.com")])

        assert kept.direction is Direction.CONTEXTUALIZES
        assert is_partial_scope(kept.match_basis.metric)

    def test_a_detail_stated_differently_is_still_a_smaller_version(self) -> None:
        checker = _Checker("PARTLY", smaller_version=True, states_differently=True)

        [kept] = _verified(checker, [_item("narrower", "thehindu.com")])

        assert kept.match_basis.metric.startswith(NARROWER_SCOPE)

    def test_another_group_of_people_is_never_part_of_the_claim(self) -> None:
        checker = _Checker("UNCLEAR", other_group=True)

        assert _verified(checker, [_item("narrower", "thehindu.com")]) == []

    def test_not_about_the_claim_is_not_part_of_it(self) -> None:
        checker = _Checker("UNCLEAR", addresses_claim=False)

        assert _verified(checker, [_item("narrower", "thehindu.com")]) == []

    def test_a_plain_support_is_never_made_partial(self) -> None:
        """Only a reading the first reader already found narrower."""
        assert _verified(_Checker("UNCLEAR"), [_item("supports", "thehindu.com")]) == []

    @pytest.mark.parametrize("verdict", ["PARTLY", "UNCLEAR"])
    def test_a_smaller_version_is_never_part_of_it(self, verdict: str) -> None:
        """smaller_version without states_differently: a proposal reported for a
        claim of a decision stays narrower, never part of the claim."""
        checker = _Checker(verdict, smaller_version=True, states_differently=False)

        kept = _verified(checker, [_item("narrower", "thehindu.com")])

        assert not any(is_partial_scope(e.match_basis.metric) for e in kept)
        if verdict == "PARTLY":
            [narrower] = kept
            assert narrower.match_basis.metric.startswith(NARROWER_SCOPE)


class TestAnInflatedCriticalDetail:
    """ "Govt approved Rs 5,000/month for every woman", where outlets report only a
    proposal: the check says smaller and forgets to say it states it differently."""

    def test_it_still_holds_the_case_back_from_true(self) -> None:
        headline = claim(importance=Importance.HEADLINE, independent_origin_count=2)
        detail = claim(
            claim_id="cl_2",
            text="Govt approved Rs 5,000/month for every woman.",
            importance=Importance.SUPPORTING_DETAIL,
            severity=Severity.CRITICAL,
        )
        checker = _Checker("PARTLY", smaller_version=True, states_differently=False)
        reports = _verified(
            checker,
            [
                _item("narrower", "thewire.in", claim_id="cl_2"),
                _item("narrower", "ndtv.com", claim_id="cl_2"),
            ],
        )
        decision = decide(detail, reports)

        case = roll_up(
            [
                (
                    headline,
                    decide(
                        headline,
                        [_item("supports", "thehindu.com"), _item("supports", "indiatoday.in")],
                    ),
                ),
                (detail, decision),
            ]
        )

        assert decision.rule_id != REPORTED_IN_PART_RULE
        assert case.verdict is not Verdict.TRUE


# ---------------------------------------------------------------------- the rules


class TestTheRules:
    def test_two_publishers_reporting_part_of_it_leave_it_reported(self) -> None:
        decision = decide(claim(), [_item("partial", "thewire.in"), _item("partial", "ndtv.com")])

        assert decision.status is ClaimStatus.UNVERIFIED
        assert decision.rule_id == REPORTED_IN_PART_RULE

    def test_one_is_not_enough(self) -> None:
        decision = decide(claim(), [_item("partial", "thewire.in")])

        assert decision.rule_id == "rule.no_qualifying_evidence"

    def test_it_is_never_a_smaller_version(self) -> None:
        """Rule 4b never sees it: three reports leaving "repeatedly" out made a true
        detail misleading."""
        items = [_item("partial", host) for host in ("thewire.in", "toi.in", "nie.in")]

        assert decide(claim(), items).status is not ClaimStatus.MISLEADING_CONTEXT

    def test_nor_support(self) -> None:
        items = [_item("partial", host) for host in ("thewire.in", "toi.in", "nie.in")]

        assert decide(claim(independent_origin_count=3), items).status is not (
            ClaimStatus.SUPPORTED
        )

    def test_a_critical_detail_reported_in_part_does_not_hold_the_story_back(self) -> None:
        detail = claim(importance=Importance.SUPPORTING_DETAIL, severity=Severity.CRITICAL)
        decision = decide(detail, [_item("partial", "thewire.in"), _item("partial", "ndtv.com")])

        assert not holds_back(detail, decision)

    def test_but_a_headline_reported_in_part_still_does(self) -> None:
        headline = claim(importance=Importance.HEADLINE)
        decision = decide(headline, [_item("partial", "thewire.in"), _item("partial", "ndtv.com")])

        assert holds_back(headline, decision)

    def test_news_4_reads_true(self) -> None:
        """The headline carried by four outlets; the charges-and-fine detail and the
        "repeatedly alleged" detail each reported in part."""
        headline = claim(
            importance=Importance.HEADLINE, severity=Severity.CRITICAL, independent_origin_count=4
        )
        charges = claim(
            claim_id="cl_5", importance=Importance.SUPPORTING_DETAIL, severity=Severity.CRITICAL
        )
        conspiracy = claim(
            claim_id="cl_7", importance=Importance.SUPPORTING_DETAIL, independent_origin_count=1
        )
        hosts = ("thehindu.com", "theprint.in", "deccanchronicle.com", "indiatoday.in")
        partial = [_item("partial", host) for host in ("deccanchronicle.com", "indiatoday.in")]

        case = roll_up(
            [
                (headline, decide(headline, [_item("supports", host) for host in hosts])),
                (charges, decide(charges, partial)),
                (
                    conspiracy,
                    decide(
                        conspiracy,
                        [_item("supports", "tribuneindia.com"), *partial],
                    ),
                ),
            ]
        )

        assert case.action is Action.SAFE_TO_SHARE

    def test_an_inflated_forward_is_still_partly_true(self) -> None:
        """Rs 5,000 for every woman, against two states' smaller schemes."""
        forward = claim(importance=Importance.HEADLINE)
        smaller = [_item("narrower", "thehindu.com"), _item("narrower", "ndtv.com")]

        case = roll_up([(forward, decide(forward, smaller))])

        assert decide(forward, smaller).rule_id == NARROWER_RULE
        assert case.rule_id == "rollup.partly_true"

    def test_a_side_detail_reported_smaller_leaves_a_confirmed_story_true(self) -> None:
        """news-3: the fire is confirmed by four outlets; one detail (which floor it
        began on) is reported in less detail. The story is true; the detail is shown as
        partly true on its own line."""
        headline = claim(importance=Importance.HEADLINE, independent_origin_count=4)
        detail = claim(
            claim_id="cl_4", importance=Importance.SUPPORTING_DETAIL, severity=Severity.HIGH
        )
        hosts = ("thehindu.com", "theprint.in", "deccanchronicle.com", "indiatoday.in")
        smaller = [_item("narrower", "timesofindia.com"), _item("narrower", "ndtv.com")]

        detail_decision = decide(detail, smaller)
        case = roll_up(
            [
                (headline, decide(headline, [_item("supports", host) for host in hosts])),
                (detail, detail_decision),
            ]
        )

        assert detail_decision.rule_id == NARROWER_RULE
        assert case.action is Action.SAFE_TO_SHARE
        assert "smaller version" in case.reason

    def test_a_critical_detail_reported_smaller_still_makes_it_partly_true(self) -> None:
        """Rs 5,000 for every woman as a CRITICAL detail under a true headline."""
        headline = claim(importance=Importance.HEADLINE, independent_origin_count=3)
        detail = claim(
            claim_id="cl_4", importance=Importance.SUPPORTING_DETAIL, severity=Severity.CRITICAL
        )
        hosts = ("thehindu.com", "theprint.in", "deccanchronicle.com")
        smaller = [_item("narrower", "timesofindia.com"), _item("narrower", "ndtv.com")]

        case = roll_up(
            [
                (headline, decide(headline, [_item("supports", host) for host in hosts])),
                (detail, decide(detail, smaller)),
            ]
        )

        assert case.rule_id == "rollup.partly_true"

    def test_a_side_detail_reported_smaller_with_nothing_central_confirmed_is_not_true(
        self,
    ) -> None:
        headline = claim(importance=Importance.HEADLINE)
        detail = claim(
            claim_id="cl_4", importance=Importance.SUPPORTING_DETAIL, severity=Severity.HIGH
        )
        smaller = [_item("narrower", "timesofindia.com"), _item("narrower", "ndtv.com")]

        case = roll_up([(headline, decide(headline, [])), (detail, decide(detail, smaller))])

        assert case.action is not Action.SAFE_TO_SHARE

    def test_it_reports_on_the_claim_and_says_so(self) -> None:
        item = _item("partial", "thewire.in")

        note = narrower_note([item], language="en")

        assert _reports_on(item)
        assert note is not None and note.startswith("Sources report part of this")


# -------------------------------------------------------------- searching further


class TestANarrowerAnswerDoesNotEndTheSearch:
    def test_only_a_smaller_version_leaves_the_search_open(self) -> None:
        def decided(rule: str, status: ClaimStatus) -> Decision:
            return Decision(status=status, rule_id=rule, reason="r", supporting_evidence_ids=("e",))

        assert not _search_settled(decided(NARROWER_RULE, ClaimStatus.MISLEADING_CONTEXT))
        assert _search_settled(decided(OUT_OF_CONTEXT_RULE, ClaimStatus.MISLEADING_CONTEXT))
        assert _search_settled(decided("rule.factcheck_contradiction", ClaimStatus.CONTRADICTED))
        assert not _search_settled(
            Decision(status=ClaimStatus.UNVERIFIED, rule_id="rule.no_evidence", reason="r")
        )

    @pytest.mark.anyio
    async def test_corpus_items_read_as_narrower_still_send_the_claim_to_the_web(self) -> None:
        """yt-2: Outlook, Al Jazeera and the Economic Times, from the corpus, read as
        narrower; the web search that held the Premier League's own words never ran."""
        corpus, web = _Corpus(), _Web()
        orchestrator = Orchestrator(
            cache=_NullCache(),  # type: ignore[arg-type]
            governor=_Refusing(),  # type: ignore[arg-type]
            resolvers=[corpus, web],  # type: ignore[list-item]
            extractor_version="test",
        )

        result = await orchestrator.verify(
            normalise_text("Manchester City were found guilty of all charges."),
            case_id=uuid4(),
            claims=[claim(importance=Importance.HEADLINE)],
        )

        assert corpus.asked == ["cl_1"]
        assert web.asked == ["cl_1"]
        assert result.claims[0].decision.rule_id == NARROWER_RULE


class _NullCache:
    async def get_verdict(self, parts: Any) -> None:
        return None


class _Refusing:
    async def try_acquire(self, provider: str) -> Any:
        from app.governor.governor import Skip, SkipReason

        return Skip(provider=provider, reason=SkipReason.NOT_CONFIGURED)


class _Stub:
    version = "v"
    allowed_domains: frozenset[str] = frozenset()
    tier = Tier.D
    kind = EvidenceKind.CORROBORATION

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def snapshot(self, candidate: Any) -> Any:
        return SourceSnapshot(
            id=f"snap:{candidate.url}",
            url=candidate.url,
            final_url=candidate.url,
            content_hash=f"sha256:{candidate.url}",
            fetched_at=datetime.now(UTC),
            text="City were found guilty of most of the charges.",
        )


class _Corpus(_Stub):
    name = "corpus"
    method = Method.ORIGIN_CLUSTER_COUNT
    fallback = False

    async def candidates(self, claim: Any) -> list[Any]:
        self.asked.append(claim.id)
        return [
            SourceCandidate(url=f"https://www.{host}/city", publisher=host)
            for host in ("outlookindia.com", "economictimes.com")
        ]

    async def relate(self, claim: Any, snapshot: Any) -> Any:
        return SourceRelation(
            relation=Relation.CONTEXTUALIZES,
            validator=self.name,
            validator_version="v",
            excerpt="found guilty of most of the charges",
            anchor={"char_start": 9, "char_end": 44},
            metric=f"{NARROWER_SCOPE}: most, not all",
            value=0.9,
            threshold=0.5,
        )


class _Web(_Stub):
    name = "web_search"
    method = Method.PASSAGE_ENTAILMENT
    fallback = True

    async def candidates(self, claim: Any) -> list[Any]:
        self.asked.append(claim.id)
        return []


# ------------------------------------------------- a second round's sibling pages


def _rows(*pages: tuple[str, str]) -> list[dict[str, Any]]:
    return [{"url": url, "title": title, "content": title} for url, title in pages]


class _Reader:
    async def judge(self, *_args: Any, **_kwargs: Any) -> Any:
        from app.sources.reasoning import ReasoningOutcome

        return ReasoningOutcome(passages_read=1)


def _resolver(rows: list[dict[str, Any]]) -> WebSearchResolver:
    resolver = WebSearchResolver(
        fetcher=None,  # type: ignore[arg-type]
        reasoner=_Reader(),  # type: ignore[arg-type]
        provider="tavily",
        endpoint="https://api.tavily.example/search",
        api_key="k",
        credibility=SourceCredibility(
            frozenset(
                {"tribuneindia.com", "hindustantimes.com", "newindianexpress.com", "pib.gov.in"}
            )
        ),
    )

    async def _search(query: str, *, domains: tuple[str, ...] = ()) -> list[dict[str, Any]]:
        return rows

    resolver._search = _search  # type: ignore[method-assign]
    return resolver


GST = "Gross GST revenue collected for October 2025 is Rs 1,95,936 crore."
TRIBUNE = (
    "https://www.tribuneindia.com/news/business/gst-collections-october",
    "Gross GST collections for October 2025 at Rs 1,95,936 crore, up 4.6 per cent",
)
HT = (
    "https://www.hindustantimes.com/business/gst-october-2025",
    "GST revenue for October 2025 rises 4.6% to Rs 1,95,936 crore",
)
UNRELATED = ("https://www.hindustantimes.com/cricket/score", "India beat Australia in Perth")
NIE = (
    "https://www.newindianexpress.com/business/gst-october",
    "October GST collection Rs 1,95,936 crore",
)


class TestASecondRoundReadsWhatTheCheckFoundForItsOtherClaims:
    def _second_round(
        self, *, own: frozenset[str] = frozenset(), judged: tuple[str, ...] = ()
    ) -> list[str]:
        resolver = _resolver(_rows(TRIBUNE, HT, UNRELATED))
        headline = claim(claim_id="cl_1", text=GST)
        base = claim(claim_id="cl_2", text="It is 4.6% more than Rs 1,87,346 crore a year ago.")
        check = current_check.set("case-x3")
        shared = current_own_pages.set(own)
        try:
            asyncio.run(resolver.candidates(base))  # the other claim's first round
            for url in judged:
                resolver._judged.setdefault("cl_1", set()).add(page_key(url))
            resolver._search = _searching_only(NIE)  # type: ignore[method-assign]
            token = current_follow_up.set(("October 2025 GST collection figure",))
            try:
                found = asyncio.run(resolver.candidates(headline))
            finally:
                current_follow_up.reset(token)
        finally:
            current_own_pages.reset(shared)
            current_check.reset(check)
        return [candidate.url for candidate in found]

    def test_pages_found_for_another_claim_are_offered(self) -> None:
        urls = self._second_round()

        assert NIE[0] in urls
        assert TRIBUNE[0] in urls
        assert HT[0] in urls

    def test_never_a_page_about_something_else(self) -> None:
        assert UNRELATED[0] not in self._second_round()

    def test_never_one_already_judged_for_this_claim(self) -> None:
        assert TRIBUNE[0] not in self._second_round(judged=(TRIBUNE[0],))

    def test_never_the_persons_own_page_or_outlet(self) -> None:
        urls = self._second_round(own=frozenset({page_key("https://www.tribuneindia.com/x")}))

        assert TRIBUNE[0] not in urls

    def test_a_first_round_offers_none(self) -> None:
        resolver = _resolver(_rows(TRIBUNE))
        check = current_check.set("case-x3b")
        try:
            asyncio.run(resolver.candidates(claim(claim_id="cl_2", text="Another claim.")))
            resolver._search = _searching_only(NIE)  # type: ignore[method-assign]
            found = asyncio.run(resolver.candidates(claim(claim_id="cl_1", text=GST)))
        finally:
            current_check.reset(check)

        assert [candidate.url for candidate in found] == [NIE[0]]


def _searching_only(page: tuple[str, str]) -> Any:
    async def _search(query: str, *, domains: tuple[str, ...] = ()) -> list[dict[str, Any]]:
        return _rows(page)

    return _search
