"""How a check spends its time (work package E, phase 1).

Held here: a background check keeps time to search and read however long reading its
input took, and never runs past what the apps wait for; its main claims are finished
first; a search waiting for its turn never holds a slot a page could be read in; and
the time running out is said as the time running out - with the time the check
really had - never as a provider being down.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import uuid4

import pytest

from app.domain.enums import Importance, Severity
from app.domain.evidence import Evidence
from app.governor.governor import ProviderUnavailable, SkipReason
from app.intake.normalizer import normalise_text
from app.orchestration import pipeline
from app.orchestration.pipeline import (
    BACKGROUND_CEILING_SECONDS,
    BACKGROUND_MIN_READING_SECONDS,
    MIN_READING_SECONDS,
    REASONING_TARGET_SECONDS,
    Orchestrator,
    SkippedCheck,
)
from app.sources.base import check_seconds
from app.sources.verification import SourceVerification, Verified
from tests.unit.factories import claim, evidence

pytestmark = pytest.mark.unit

_BACKGROUND = 300.0


class _NullCache:
    async def get_verdict(self, parts: Any) -> None:
        return None


class _Governor:
    async def try_acquire(self, provider: str) -> object:
        return object()


class _Reader:
    """A resolver that reads with a model, so the orchestrator keeps the long budget."""

    name = "corpus"
    version = "v"
    reads_sources = True

    async def candidates(self, claim: Any) -> list[Any]:
        return []


def _orchestrator(resolvers: list[Any] | None = None, **options: Any) -> Orchestrator:
    chosen: list[Any] = resolvers if resolvers is not None else [_Reader()]
    return Orchestrator(
        cache=_NullCache(),  # type: ignore[arg-type]
        governor=_Governor(),
        resolvers=chosen,
        extractor_version="test",
        **options,
    )


class _Background:
    """Runs what is inside as a check the app follows in the background."""

    def __init__(self, seconds: float = _BACKGROUND) -> None:
        self.seconds = seconds

    def __enter__(self) -> None:
        self._token = check_seconds.set(self.seconds)

    def __exit__(self, *_: object) -> None:
        check_seconds.reset(self._token)


async def _deadline_of(orchestrator: Orchestrator, *, spent: float) -> tuple[float, float, Any]:
    """(deadline - started, deadline - now, the budget the check says it had) for a
    check whose input took `spent` seconds to read before checking began."""
    seen: dict[str, Any] = {}

    async def _resolve_all(claims: list[Any], **kwargs: Any) -> list[Any]:
        seen["deadline"] = kwargs["deadline"]
        seen["now"] = time.perf_counter()
        seen["budget"] = pipeline._check_budget.get()
        return []

    orchestrator._resolve_all = _resolve_all  # type: ignore[method-assign]
    started = time.perf_counter() - spent
    await orchestrator.verify(
        normalise_text("A claim to check."), case_id=uuid4(), claims=[claim()], started_at=started
    )
    return seen["deadline"] - started, seen["deadline"] - seen["now"], seen["budget"]


class TestTheBackgroundDeadline:
    """A post with a ten-minute video spends minutes being read before checking
    starts; counted against the same five minutes, it left the claims nothing."""

    async def test_a_quick_read_keeps_the_usual_budget(self) -> None:
        with _Background():
            total, _, budget = await _deadline_of(_orchestrator(), spent=10.0)

        assert total == pytest.approx(_BACKGROUND, abs=0.5)
        assert budget == pytest.approx(_BACKGROUND, abs=0.5)

    async def test_a_long_read_still_leaves_the_minimum_to_search_and_read(self) -> None:
        with _Background():
            total, left, budget = await _deadline_of(_orchestrator(), spent=200.0)

        assert left == pytest.approx(BACKGROUND_MIN_READING_SECONDS, abs=0.5)
        assert total == pytest.approx(200.0 + BACKGROUND_MIN_READING_SECONDS, abs=0.5)
        # Said as the time the check really had, not the five minutes it started with.
        assert budget == pytest.approx(total, abs=0.01)

    async def test_never_past_what_the_apps_wait_for(self) -> None:
        """Nor so close to it that deciding and storing the answer runs past it: the
        app released today stops polling at about four hundred seconds."""
        with _Background():
            total, left, _ = await _deadline_of(_orchestrator(), spent=350.0)

        assert total == pytest.approx(
            BACKGROUND_CEILING_SECONDS - pipeline._BACKGROUND_TAIL_SECONDS, abs=0.5
        )
        assert total <= 400.0
        assert left < BACKGROUND_MIN_READING_SECONDS

    async def test_a_check_someone_waits_on_is_unchanged(self) -> None:
        total, _, _ = await _deadline_of(_orchestrator(), spent=0.0)
        assert total == pytest.approx(REASONING_TARGET_SECONDS, abs=0.5)

        _, left, _ = await _deadline_of(_orchestrator(), spent=30.0)
        assert left == pytest.approx(MIN_READING_SECONDS, abs=0.5)

    async def test_the_budget_is_forgotten_when_the_check_ends(self) -> None:
        with _Background():
            await _deadline_of(_orchestrator(), spent=200.0)

        assert pipeline._check_budget.get() is None


class TestTheSourceCheckKeepsItsReserve:
    """In the background the source check waits its turn under the model's
    per-minute ceiling: six seconds left most of them timed out in the queue."""

    async def _read_by(self) -> float:
        orchestrator = _orchestrator(verification=object())
        seen: list[float | None] = []

        async def _run_resolver(resolver: Any, claim: Any, *, read_by: float | None = None) -> Any:
            seen.append(read_by)
            return [], None, 0

        orchestrator._run_resolver = _run_resolver  # type: ignore[method-assign]
        deadline = time.perf_counter() + 100.0
        await orchestrator._run_stage([_Reader()], claim(), skipped=[], deadline=deadline)  # type: ignore[list-item]
        assert seen[0] is not None
        return deadline - seen[0]

    async def test_twenty_seconds_in_the_background(self) -> None:
        with _Background():
            assert await self._read_by() == pytest.approx(20.0)

    async def test_six_for_a_check_someone_waits_on(self) -> None:
        assert await self._read_by() == pytest.approx(6.0)


class _Search:
    """The open-web search: notes which claims were searched, in order, and how many
    were being searched at once."""

    name = "web_search"
    version = "v"
    fallback = True
    reads_sources = True

    def __init__(self, *, takes: float = 0.0) -> None:
        self.takes = takes
        self.started: list[str] = []
        self.running = 0
        self.most = 0

    async def candidates(self, claim: Any) -> list[Any]:
        self.started.append(claim.id)
        self.running += 1
        self.most = max(self.most, self.running)
        try:
            await asyncio.sleep(self.takes)
        finally:
            self.running -= 1
        return []


class _Probe(_Search):
    """The same, as a resolver that is not the search: it takes a fetch slot, so only
    the claims at a time limit how many run together."""

    name = "corpus"
    fallback = False


def _seven_claims() -> list[Any]:
    return [
        claim(claim_id="background", importance=Importance.BACKGROUND),
        claim(claim_id="detail_1", importance=Importance.SUPPORTING_DETAIL),
        claim(claim_id="headline", importance=Importance.HEADLINE),
        claim(claim_id="detail_2", importance=Importance.SUPPORTING_DETAIL),
        claim(claim_id="thesis", importance=Importance.MAIN_THESIS),
        claim(
            claim_id="critical",
            importance=Importance.SUPPORTING_DETAIL,
            severity=Severity.CRITICAL,
        ),
        claim(claim_id="detail_3", importance=Importance.SUPPORTING_DETAIL),
    ]


class TestTheMainClaimsFinishFirst:
    """Started all at once, a seven-claim article's details took as many slots as its
    headline, and the claims the verdict rests on were still unread at the deadline."""

    async def test_three_at_a_time_in_the_background_most_important_first(self) -> None:
        search = _Probe(takes=0.05)
        claims = _seven_claims()

        with _Background():
            result = await _orchestrator([search]).verify(
                normalise_text("A long article."), case_id=uuid4(), claims=claims
            )

        assert search.most == 3
        assert search.started[:3] == ["headline", "thesis", "critical"]
        assert sorted(search.started) == sorted(c.id for c in claims)
        # Still answered in the page's order.
        assert [o.claim.id for o in result.claims] == [c.id for c in claims]

    async def test_a_check_someone_waits_on_starts_every_claim_at_once(self) -> None:
        search = _Probe(takes=0.05)

        await _orchestrator([search]).verify(
            normalise_text("A long article."), case_id=uuid4(), claims=_seven_claims()
        )

        assert search.most == 7

    async def test_a_claim_left_without_time_is_not_searched_and_says_so(self) -> None:
        """Its queries would be paid for and every page found cut off unread."""
        search = _Search()
        orchestrator = _orchestrator([search], verification=object())
        skipped: list[SkippedCheck] = []
        pipeline_token = pipeline._check_budget.set(380.0)
        try:
            with _Background():
                found = await orchestrator._run_stage(
                    [search],  # type: ignore[list-item]
                    claim(),
                    skipped=skipped,
                    # 25 s left less the source check's 20 s reserve: 5 s to read.
                    deadline=time.perf_counter() + 25.0,
                )
        finally:
            pipeline._check_budget.reset(pipeline_token)

        assert found == []
        assert search.started == []
        (gap,) = skipped
        assert gap.check == "web_search"
        assert gap.kind == "deadline"
        assert gap.reason == "deadline of 380s reached before it was searched"

    async def test_with_time_left_it_is_searched(self) -> None:
        search = _Search()
        orchestrator = _orchestrator([search], verification=object())

        with _Background():
            await orchestrator._run_stage(
                [search],  # type: ignore[list-item]
                claim(),
                skipped=[],
                deadline=time.perf_counter() + 60.0,
            )

        assert search.started == ["cl_1"]

    async def test_out_of_time_it_reads_as_timed_out(self) -> None:
        orchestrator = _orchestrator([_Search()])

        async def _run_stage(resolvers: list[Any], claim: Any, **kwargs: Any) -> list[Any]:
            kwargs["skipped"].append(
                SkippedCheck(
                    check="web_search",
                    reason="deadline of 300s reached before it was searched",
                    kind="deadline",
                )
            )
            return []

        orchestrator._run_stage = _run_stage  # type: ignore[method-assign]
        result = await orchestrator.verify(
            normalise_text("A claim."), case_id=uuid4(), claims=[claim()]
        )

        assert result.claims[0].search == "timed_out"


class TestASearchHoldsNoFetchSlot:
    """A search waiting for its turn under the provider's pacing held a fetch slot,
    and pages already found sat unread behind it."""

    async def test_a_search_asks_under_its_own_ceiling(self) -> None:
        orchestrator = _orchestrator()
        fetch_slots = orchestrator._semaphore._value
        search_slots = orchestrator._search_gate._value
        seen: dict[str, int] = {}

        class _Watching(_Search):
            async def candidates(self, claim: Any) -> list[Any]:
                seen["fetch"] = orchestrator._semaphore._value
                seen["search"] = orchestrator._search_gate._value
                return []

        await orchestrator._run_resolver(_Watching(), claim())  # type: ignore[arg-type]

        assert seen == {"fetch": fetch_slots, "search": search_slots - 1}

    async def test_every_other_resolver_still_takes_a_fetch_slot(self) -> None:
        orchestrator = _orchestrator()
        fetch_slots = orchestrator._semaphore._value
        search_slots = orchestrator._search_gate._value
        seen: dict[str, int] = {}

        class _Corpus(_Reader):
            async def candidates(self, claim: Any) -> list[Any]:
                seen["fetch"] = orchestrator._semaphore._value
                seen["search"] = orchestrator._search_gate._value
                return []

        await orchestrator._run_resolver(_Corpus(), claim())  # type: ignore[arg-type]

        assert seen == {"fetch": fetch_slots - 1, "search": search_slots}

    def test_the_search_ceiling_is_shared_with_a_media_view(self) -> None:
        orchestrator = _orchestrator()
        view = orchestrator.with_resolvers([])

        assert view._search_gate is orchestrator._search_gate
        assert view._semaphore is orchestrator._semaphore


class _Hangs(_Reader):
    name = "web_search"

    async def candidates(self, claim: Any) -> list[Any]:
        await asyncio.sleep(30)
        return []


class TestRunningOutOfTimeIsSaidAsSuch:
    """Every background check that ran out of time was said to have had 55 seconds,
    and a source check that ran out of time read "model provider unavailable"."""

    async def test_the_timeout_names_the_time_the_check_had(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(pipeline, "_RESOLVER_GRACE_SECONDS", 0.01)
        orchestrator = _orchestrator([_Hangs()])
        skipped: list[SkippedCheck] = []
        token = pipeline._check_budget.set(352.4)
        try:
            await orchestrator._run_stage(
                [_Hangs()],  # type: ignore[list-item]
                claim(),
                skipped=skipped,
                deadline=time.perf_counter(),
            )
        finally:
            pipeline._check_budget.reset(token)

        (gap,) = skipped
        assert gap.reason == "deadline of 352s exceeded"
        assert gap.kind == "deadline"

    def test_without_a_moved_budget_the_background_budget_is_named(self) -> None:
        with _Background():
            assert _orchestrator()._budget() == _BACKGROUND
        assert _orchestrator()._budget() == REASONING_TARGET_SECONDS

    async def test_pages_left_unread_are_a_deadline_and_a_refused_search_a_provider(
        self,
    ) -> None:
        orchestrator = _orchestrator()

        async def _run_resolver(resolver: Any, claim: Any, *, read_by: float | None = None) -> Any:
            if resolver.name == "slow":
                return [], "2 of 6 sources not read before the deadline", 4
            return [], SkipReason.CAPACITY_LIMITED.value, 0

        class _Named(_Reader):
            def __init__(self, name: str) -> None:
                self.name = name

        orchestrator._run_resolver = _run_resolver  # type: ignore[method-assign]
        skipped: list[SkippedCheck] = []
        await orchestrator._run_stage(
            [_Named("slow"), _Named("refused")],  # type: ignore[list-item]
            claim(),
            skipped=skipped,
            deadline=None,
        )

        assert [(gap.check, gap.kind) for gap in skipped] == [
            ("slow", "deadline"),
            ("refused", "provider"),
        ]

    async def test_a_source_check_out_of_time_is_not_an_outage(self) -> None:
        class _OutOfTime:
            async def check(self, claim: Any, items: list[Evidence], *, budget: Any) -> Verified:
                return Verified(evidence=items, explanation=None, checked=False, timed_out=True)

        skipped: list[SkippedCheck] = []
        await _orchestrator(verification=_OutOfTime())._verify_sources(
            claim(), [evidence()], skipped=skipped
        )

        assert skipped == [
            SkippedCheck(
                check="source_verification",
                reason="no time left to check the sources",
                kind="deadline",
            )
        ]

    async def test_a_source_check_the_provider_did_not_answer_still_says_so(self) -> None:
        class _Down:
            async def check(self, claim: Any, items: list[Evidence], *, budget: Any) -> Verified:
                return Verified(evidence=items, explanation=None, checked=False)

        skipped: list[SkippedCheck] = []
        await _orchestrator(verification=_Down())._verify_sources(
            claim(), [evidence()], skipped=skipped
        )

        assert skipped == [
            SkippedCheck(
                check="source_verification", reason="model provider unavailable", kind="provider"
            )
        ]


class _Checker:
    def __init__(self, *, takes: float) -> None:
        self.takes = takes

    async def check_sources(self, claim_text: str, sources: list[Any]) -> Any:
        await asyncio.sleep(self.takes)
        return None


class _Ranker:
    def credibility(self, url_or_domain: str | None) -> Any:
        return "HIGH"


class TestTheSourceCheckSaysWhyItDidNotRun:
    async def _check(self, *, takes: float, budget: float) -> Verified:
        from app.domain import Direction

        verification = SourceVerification(checker=_Checker(takes=takes), ranker=_Ranker())
        items = [evidence(direction=Direction.CONTRADICTS, citation_url="https://apnews.com/1")]
        return await verification.check(claim(), items, budget=budget)

    async def test_out_of_time(self) -> None:
        verified = await self._check(takes=5.0, budget=0.05)
        assert (verified.checked, verified.timed_out) == (False, True)

    async def test_no_answer_in_time_is_not_a_timeout(self) -> None:
        verified = await self._check(takes=0.0, budget=5.0)
        assert (verified.checked, verified.timed_out) == (False, False)


class _SecondRound(_Search):
    """A search that finds nothing, and a model that would write a second round."""

    def __init__(self) -> None:
        super().__init__()
        self.rounds = 0

    async def follow_up_queries(self, claim: Any, notes: list[str]) -> list[str]:
        self.rounds += 1
        return ["a sharper query"]


class TestASkippedSecondRoundIsSaid:
    """A central claim owed a second round that the clock left out read as though it
    had had one, and was cached as complete."""

    async def _follow_up(self, *, background: bool) -> tuple[list[SkippedCheck], int]:
        search = _SecondRound()
        skipped: list[SkippedCheck] = []
        orchestrator = _orchestrator([search])
        deadline = time.perf_counter() + 20.0  # under the 45 s a round needs
        fallback: list[Any] = [search]
        if background:
            with _Background():
                more = await orchestrator._follow_up(
                    fallback, claim(), [], skipped=skipped, deadline=deadline, tally=[0]
                )
        else:
            more = await orchestrator._follow_up(
                fallback, claim(), [], skipped=skipped, deadline=deadline, tally=[0]
            )
        assert more == []
        return skipped, search.rounds

    async def test_in_the_background_it_is_recorded(self) -> None:
        skipped, rounds = await self._follow_up(background=True)

        assert skipped == [
            SkippedCheck(
                check="follow_up_search",
                reason="too little time left for a second search round",
                kind="deadline",
            )
        ]
        assert rounds == 0

    async def test_a_check_someone_waits_on_never_had_the_time_and_says_nothing(self) -> None:
        skipped, rounds = await self._follow_up(background=False)

        assert skipped == []
        assert rounds == 0

    async def test_the_claim_still_reads_as_searched(self) -> None:
        """Its first round stands; only "deadline" gaps make a search timed out."""
        search = _SecondRound()
        orchestrator = _orchestrator([search])

        with _Background():
            result = await orchestrator.verify(
                normalise_text("A headline."),
                case_id=uuid4(),
                claims=[claim(importance=Importance.HEADLINE)],
                # Started long ago: under a minute is left to search and read.
                started_at=(
                    time.perf_counter()
                    - BACKGROUND_CEILING_SECONDS
                    + pipeline._BACKGROUND_TAIL_SECONDS
                    + 30.0
                ),
            )

        (outcome,) = result.claims
        assert outcome.search == "searched"
        assert any(gap.check == "follow_up_search" for gap in result.skipped)
        assert search.rounds == 0


class TestAnUnavailableSearchIsStillAProviderGap:
    async def test_a_refused_search_is_not_a_timeout(self) -> None:
        class _Refused(_Search):
            async def candidates(self, claim: Any) -> list[Any]:
                raise ProviderUnavailable("web_search", SkipReason.PROVIDER_ERROR)

        result = await _orchestrator([_Refused()]).verify(
            normalise_text("A claim."), case_id=uuid4(), claims=[claim()]
        )

        (outcome,) = result.claims
        assert outcome.search == "unavailable"
        assert [(gap.check, gap.kind) for gap in result.skipped] == [("web_search", "provider")]


class _Primary(_Search):
    """The corpus and the fact-check API: a resolver the claim reads before searching."""

    name = "corpus"
    fallback = False


class TestALateClaimIsDecidedFromNothing:
    """A claim whose turn came after reading had to stop still ran its stages past the
    deadline in waves of three, and was said to be skipped twice - the second time for
    a search round it never had."""

    async def test_past_the_reading_time_nothing_runs_and_it_is_said_once(self) -> None:
        primary, search = _Primary(), _SecondRound()
        orchestrator = _orchestrator([primary, search])
        skipped: list[SkippedCheck] = []

        with _Background():
            outcome = await orchestrator._resolve_claim(
                claim(importance=Importance.HEADLINE),
                skipped=skipped,
                deadline=time.perf_counter() - 1.0,
            )

        assert (primary.started, search.started, search.rounds) == ([], [], 0)
        assert skipped == [
            SkippedCheck(
                check="web_search",
                reason=f"deadline of {_BACKGROUND:.0f}s reached before it was searched",
                kind="deadline",
            )
        ]
        assert outcome.search == "timed_out"

    async def test_a_search_skipped_for_time_is_not_owed_a_second_round(self) -> None:
        """Its first stage ran; its search did not, so no second round is missing."""
        primary, search = _Primary(), _SecondRound()
        orchestrator = _orchestrator([primary, search])
        skipped: list[SkippedCheck] = []

        with _Background():
            outcome = await orchestrator._resolve_claim(
                claim(importance=Importance.HEADLINE),
                skipped=skipped,
                # Five seconds: the primary stage runs, a search would not finish.
                deadline=time.perf_counter() + 5.0,
            )

        assert primary.started == ["cl_1"]
        assert (search.started, search.rounds) == ([], 0)
        assert [gap.check for gap in skipped] == ["web_search"]
        assert outcome.search == "timed_out"

    async def test_with_time_left_every_stage_runs(self) -> None:
        primary, search = _Primary(), _SecondRound()
        orchestrator = _orchestrator([primary, search])

        with _Background():
            outcome = await orchestrator._resolve_claim(
                claim(importance=Importance.HEADLINE),
                skipped=[],
                deadline=time.perf_counter() + 120.0,
            )

        assert (primary.started, search.started) == (["cl_1"], ["cl_1", "cl_1"])
        assert search.rounds == 1
        assert outcome.search == "searched"

    async def test_a_check_someone_waits_on_is_never_late(self) -> None:
        """It starts every claim at once; past its deadline each is cut off as before."""
        primary, search = _Primary(), _SecondRound()
        orchestrator = _orchestrator([primary, search])

        await orchestrator._resolve_claim(claim(), skipped=[], deadline=time.perf_counter() - 1.0)

        assert primary.started == ["cl_1"]
