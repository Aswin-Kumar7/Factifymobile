"""Sources about the claim, and only the claim (2026-09-28).

Found on the phone: a report of another match, or of another year's final, read as
support or contradiction for a claim about one particular final; and a shared
fact-check whose quoted viral post was checked as though the fact-check asserted it.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.api.verify import _without_the_reviewed_claim
from app.domain.enums import Direction, EvidenceKind, Method, Tier
from app.extraction.claims import ExtractedClaims
from app.sources.verification import _other_occurrence
from tests.unit.factories import claim, evidence

pytestmark = pytest.mark.unit

FINAL = "India beat Australia in the 2024 T20 World Cup final."


def _report(excerpt: str, *, published: date | None = None, title: str | None = None) -> object:
    return evidence(
        kind=EvidenceKind.CORROBORATION,
        direction=Direction.SUPPORTS,
        tier=Tier.D,
        method=Method.PASSAGE_ENTAILMENT,
        source_excerpt=excerpt,
        published_on=published,
        title=title,
    )


class TestAnotherOccurrence:
    def test_another_match_of_the_tournament_is_not_the_final(self) -> None:
        item = _report(
            "India beat Australia by 24 runs in the Super Eight match in St Lucia.",
            title="India beat Australia, India won by 24 runs",
        )
        assert _other_occurrence(item, claim(text=FINAL)) == "another match"  # type: ignore[arg-type]

    def test_a_report_of_the_final_that_mentions_the_semi_final_stays(self) -> None:
        item = _report("After beating England in the semi-final, India won the final.")
        assert _other_occurrence(item, claim(text=FINAL)) is None  # type: ignore[arg-type]

    def test_news_from_before_the_claimed_year_cannot_report_it(self) -> None:
        item = _report(
            "Indians are nursing broken hearts after the team lost to Australia in the "
            "World Cup final on Sunday.",
            published=date(2023, 11, 20),
        )
        assert _other_occurrence(item, claim(text=FINAL)) == "published before the event"  # type: ignore[arg-type]

    def test_an_earlier_report_naming_the_year_stays(self) -> None:
        item = _report(
            "ISRO plans to launch Gaganyaan's first crewed flight in 2027.",
            published=date(2025, 3, 1),
        )
        target = claim(text="ISRO will launch Gaganyaan's first crewed flight in 2027.")
        assert _other_occurrence(item, target) is None  # type: ignore[arg-type]

    def test_a_much_later_report_of_something_that_recurs_is_a_later_one(self) -> None:
        item = _report(
            "India won the T20 World Cup for a record third time, beating New Zealand.",
            published=date(2026, 3, 9),
        )
        target = claim(text="India won the 2024 T20 World Cup.")
        assert _other_occurrence(item, target) == "a later occurrence"  # type: ignore[arg-type]

    def test_a_preview_from_before_the_day_is_not_a_report(self) -> None:
        """ "ISRO will launch Aditya-L1 on September 2" was read as a smaller version of
        "ISRO launched Aditya-L1 on 2 September 2023" (2026-09-28)."""
        item = _report(
            "ISRO will launch Aditya-L1 from Sriharikota on September 2.",
            published=date(2023, 8, 28),
        )
        target = claim(text="ISRO launched Aditya-L1 on 2 September 2023 from Sriharikota.")
        assert _other_occurrence(item, target) == "published before the event"  # type: ignore[arg-type]

    def test_a_preview_is_neither_support_nor_contradiction(self) -> None:
        item = _report(
            "India are just one win away from ending their World Cup drought as they face "
            "South Africa in the final of the T20 World Cup 2024 in Barbados.",
            published=date(2024, 6, 29),
        )
        target = claim(text="India won the 2024 T20 World Cup.")
        assert _other_occurrence(item, target) == "a preview, written before the outcome"  # type: ignore[arg-type]

    def test_a_report_of_the_outcome_is_not_a_preview(self) -> None:
        item = _report("India beat South Africa to win the final, ahead of a victory parade.")
        target = claim(text="India won the 2024 T20 World Cup.")
        assert _other_occurrence(item, target) is None  # type: ignore[arg-type]

    def test_standings_after_another_round_are_not_the_final_standings(self) -> None:
        item = _report(
            "After the eighth round, Uzbekistan and Germany share the top spot with 14 "
            "match points, with India in the joint second spot."
        )
        target = claim(
            text="After 11 rounds, India and Germany shared second place with 18 points."
        )
        assert _other_occurrence(item, target) == "another round"  # type: ignore[arg-type]

    def test_a_year_less_claim_from_a_news_page_is_about_that_page_s_moment(self) -> None:
        from app.sources.base import current_reference_date

        item = _report(
            "The Supreme Court sought responses from the Centre, the RBI and NPCI on a PIL.",
            published=date(2020, 10, 15),
        )
        target = claim(text="The Supreme Court issued notices to the Centre, RBI and NPCI.")
        token = current_reference_date.set(date(2026, 9, 28))
        try:
            assert _other_occurrence(item, target) == "an earlier occurrence"  # type: ignore[arg-type]
            recent = _report("Notices issued.", published=date(2026, 9, 28))
            assert _other_occurrence(recent, target) is None  # type: ignore[arg-type]
        finally:
            current_reference_date.reset(token)
        # A message with no date of its own is not held to one.
        assert _other_occurrence(item, target) is None  # type: ignore[arg-type]

    def test_a_report_from_the_day_itself_stays(self) -> None:
        item = _report("Aditya-L1 lifted off from Sriharikota.", published=date(2023, 9, 2))
        target = claim(text="ISRO launched Aditya-L1 on September 2, 2023.")
        assert _other_occurrence(item, target) is None  # type: ignore[arg-type]

    def test_a_later_look_back_at_a_one_off_event_stays(self) -> None:
        item = _report(
            "Two years after Chandrayaan-3 landed near the lunar south pole, ISRO is "
            "preparing Chandrayaan-4.",
            published=date(2025, 8, 23),
        )
        target = claim(text="Chandrayaan-3 landed near the Moon's south pole on 23 August 2023.")
        assert _other_occurrence(item, target) is None  # type: ignore[arg-type]

    def test_a_fact_check_is_never_set_aside_for_its_date(self) -> None:
        """An older debunk of the same video is exactly what answers a "today" claim."""
        item = evidence(source_excerpt="This video is from 2019.", published_on=date(2020, 1, 1))
        target = claim(text="This video shows floods in Assam in 2026.")
        assert _other_occurrence(item, target) is None


class TestASharedFactCheck:
    def test_the_viral_post_it_examines_is_set_aside_and_its_findings_kept(self) -> None:
        post = claim(
            claim_id="cl_1",
            text=(
                "एक्स यूजर ‘Promila’ ने 25 सितंबर 2026 को एक वीडियो शेयर करते हुए कैप्शन में "
                "लिखा कि वित्त मंत्री निर्मला सीतारमण सादगी से रहने वाले अपने पिता से मिलने पहुंचीं।"
            ),
        )
        finding = claim(
            claim_id="cl_2",
            text=(
                "वीडियो में दिख रहे बुजुर्ग व्यक्ति वित्त मंत्री निर्मला सीतारमण के पिता नहीं, "
                "बल्कि महाकवि सुब्रमण्यम भारती के भांजे केवी कृष्णन हैं।"
            ),
        )
        reviewed = ("सादगी से रहने वाले पिता से मिलने पहुंचीं वित्त मंत्री निर्मला सीतारमण।",)

        kept = _without_the_reviewed_claim(ExtractedClaims(claims=(post, finding)), reviewed)

        assert [c.id for c in kept.claims] == ["cl_2"]

    def test_nothing_is_set_aside_when_every_claim_would_be(self) -> None:
        only = claim(text="Sitharaman went to meet her father who lives simply.")
        kept = _without_the_reviewed_claim(
            ExtractedClaims(claims=(only,)), ("Sitharaman went to meet her father",)
        )
        assert kept.claims == (only,)


class TestNewsTooFreshToConfirm:
    """Hindustan Times on a scheme launched that morning: four claims confirmed, the
    headline Unconfirmed, because nobody else had reported it yet (2026-09-28)."""

    @staticmethod
    async def _check(published: date) -> object:
        from datetime import UTC, datetime  # noqa: F401
        from uuid import uuid4

        from app.intake.normalizer import normalise_text
        from app.sources.base import current_reference_date
        from tests.unit.test_orchestration import _claim, _economy_orchestrator, _fact_check

        token = current_reference_date.set(published)
        try:
            return await _economy_orchestrator([_fact_check(None)]).verify(
                normalise_text("A scheme launched this morning."),
                case_id=uuid4(),
                claims=[_claim()],
            )
        finally:
            current_reference_date.reset(token)

    @pytest.mark.anyio
    async def test_an_unconfirmed_claim_from_today_s_news_is_too_recent(self) -> None:
        from datetime import UTC, datetime

        from app.domain.enums import Action

        result = await self._check(datetime.now(UTC).date())

        assert result.claims[0].decision.rule_id == "rule.developing_window"  # type: ignore[attr-defined]
        assert result.action is Action.WAIT_AND_RECHECK  # type: ignore[attr-defined]

    @pytest.mark.anyio
    async def test_last_month_s_news_is_not(self) -> None:
        from datetime import UTC, datetime, timedelta

        result = await self._check(datetime.now(UTC).date() - timedelta(days=30))

        assert result.claims[0].decision.rule_id != "rule.developing_window"  # type: ignore[attr-defined]


class TestStoredFactChecksByMeaning:
    """A stored debunk that shares few words with the claim - more so across
    languages - is shortlisted by meaning, and still verified before use."""

    class _Embedder:
        def embed(self, texts: list[str], *, language: object = None) -> object:
            from app.embeddings.text import EmbeddingResult

            def vector(text: str) -> tuple[float, ...]:
                lowered = text.casefold()
                return (1.0, 0.0) if "laptop" in lowered else (0.0, 1.0)

            return EmbeddingResult(vectors=tuple(vector(t) for t in texts))

    def test_a_paraphrased_debunk_is_shortlisted_and_the_api_still_asked(self) -> None:
        import asyncio

        from tests.unit.test_verdict_fixes import _record, _Resolver

        resolver = _Resolver(
            [_record("PIB: message about the PM Laptop Yojana is fake", "https://pib/1")]
        )
        resolver._embedder = self._Embedder()  # type: ignore[assignment]

        found = asyncio.run(
            resolver.candidates(claim(text="Centre giving free laptops to every student."))
        )

        assert "https://pib/1" in [c.url for c in found]
        assert resolver.asked == 1  # a match by meaning never skips the API


class TestASharedFactCheckIsAnsweredByItsRating:
    """Someone shares a certified fact-checker's check of a viral claim: the claim it
    examines is answered by its rating, cross-checked against other fact-checkers, and
    only its main finding is checked beside it (2026-09-29)."""

    PAGE = "https://www.boomlive.in/fact-check/pm-scheme-fake-12345"
    VIRAL = "Govt to pay Rs 5000 a month to every woman"

    @staticmethod
    def _review(text: str, rating: str | None = "False") -> Any:
        from app.extraction.claimreview import ClaimReview

        return ClaimReview(
            claim_reviewed=text, rating=rating, publisher="BOOM", published_at=None, url=None
        )

    def _shared(self) -> Any:
        from app.api.verify import _shared_fact_check

        shared = _shared_fact_check((self._review(self.VIRAL),), self.PAGE)
        assert shared is not None
        return shared

    def test_a_certified_fact_checker_s_one_rated_claim_is_what_answers(self) -> None:
        shared = self._shared()

        assert shared.certified
        assert shared.record.url == self.PAGE
        assert shared.record.rating == "False"

    def test_not_for_a_news_site_a_roundup_or_a_rating_we_do_not_read(self) -> None:
        from app.api.verify import _shared_fact_check

        news = "https://www.ndtv.com/india-news/some-story-123"
        assert _shared_fact_check((self._review(self.VIRAL),), news) is None
        roundup = (self._review(self.VIRAL), self._review("A viral video is from 2019"))
        assert _shared_fact_check(roundup, self.PAGE) is None
        assert _shared_fact_check((self._review(self.VIRAL, "Satire"),), self.PAGE) is None

    def test_a_formerly_certified_fact_checker_answers_but_is_not_called_certified(self) -> None:
        from app.api.verify import _shared_fact_check

        shared = _shared_fact_check(
            (self._review(self.VIRAL),), "https://www.altnews.in/viral-claim-is-false/"
        )

        assert shared is not None
        assert not shared.certified

    def test_the_claim_it_examines_leads_and_only_its_main_finding_is_checked(self) -> None:
        from app.api.verify import _answered_by_the_fact_check
        from app.domain.enums import Importance, Severity
        from app.sources.factcheck import SHARED_CLAIM_ID

        main = claim(
            claim_id="cl_1",
            text="No such scheme exists, the ministry said.",
            importance=Importance.HEADLINE,
            severity=Severity.CRITICAL,
        )
        detail = claim(
            claim_id="cl_2",
            text="The message has circulated since 2023.",
            importance=Importance.SUPPORTING_DETAIL,
        )

        answered = _answered_by_the_fact_check(
            ExtractedClaims(claims=(detail, main)),
            self._shared(),
            restated=(),
            source=f"Fact check: {self.VIRAL}? No.",
            page_start=0,
            content_hash="sha256:page",
            input_kind="url",
        )

        examined, finding = answered.claims
        assert examined.id == SHARED_CLAIM_ID
        assert examined.text == self.VIRAL
        assert examined.importance is Importance.HEADLINE
        assert examined.anchor.char_start == len("Fact check: ")
        # The main finding, checked as a detail: the rating carries the answer.
        assert finding.id == "cl_1"
        assert finding.importance is Importance.SUPPORTING_DETAIL
        assert finding.severity is Severity.HIGH

    def test_a_forwarded_message_keeps_its_own_claims(self) -> None:
        from app.api.verify import _answered_by_the_fact_check
        from app.domain.claim import ClaimAnchor

        def at(claim_id: str, start: int) -> Any:
            return claim(
                claim_id=claim_id,
                text=f"Claim {claim_id}.",
                anchor=ClaimAnchor(
                    input_kind="text", content_hash="sha256:x", char_start=start, char_end=start + 5
                ),
            )

        answered = _answered_by_the_fact_check(
            ExtractedClaims(claims=(at("cl_1", 3), at("cl_2", 60), at("cl_3", 90))),
            self._shared(),
            restated=(),
            source="x" * 120,
            page_start=50,
            content_hash="sha256:x",
            input_kind="text",
        )

        assert [c.id for c in answered.claims] == ["cl_reviewed", "cl_2", "cl_1"]

    def test_the_fact_check_is_listed_first_and_the_api_asked_for_others(self) -> None:
        import asyncio

        from app.sources.factcheck import SHARED_CLAIM_ID, current_shared_review
        from tests.unit.test_verdict_fixes import _record, _Resolver

        # A stored record close enough to answer on its own, which would skip the API.
        resolver = _Resolver([_record(self.VIRAL, "https://ours/2")])
        token = current_shared_review.set(self._shared())
        try:
            found = asyncio.run(
                resolver.candidates(claim(claim_id=SHARED_CLAIM_ID, text=self.VIRAL))
            )
        finally:
            current_shared_review.reset(token)

        assert found[0].url == self.PAGE
        assert resolver.asked == 1  # cross-checked
        assert "https://api/1" in [c.url for c in found]

    @staticmethod
    async def _verify(claim_id: str, shared: Any) -> Any:
        from uuid import uuid4

        from app.intake.normalizer import normalise_url
        from app.sources.factcheck import current_shared_review
        from app.sources.verification import page_key
        from tests.unit.test_orchestration import _economy_orchestrator
        from tests.unit.test_verdict_fixes import _Resolver

        class _Kept(_Resolver):
            # Keeps what the API returned, as the real query does, so it can be read.
            async def _query_api(self, claim: Any) -> list[Any]:
                records = await super()._query_api(claim)
                self._api_cache.update({record.url: record for record in records})
                return records

        page = TestASharedFactCheckIsAnsweredByItsRating.PAGE
        token = current_shared_review.set(shared)
        try:
            return await _economy_orchestrator([_Kept([])]).verify(
                normalise_url(page),
                case_id=uuid4(),
                claims=[
                    claim(claim_id=claim_id, text=TestASharedFactCheckIsAnsweredByItsRating.VIRAL)
                ],
                own_pages=frozenset({page_key(page)}),
            )
        finally:
            current_shared_review.reset(token)

    @pytest.mark.anyio
    async def test_its_rating_decides_and_is_said_with_the_other_fact_checkers(self) -> None:
        from app.domain.enums import Action, ClaimStatus
        from app.domain.evidence import is_shared_review
        from app.sources.factcheck import SHARED_CLAIM_ID

        result = await self._verify(SHARED_CLAIM_ID, self._shared())

        outcome = result.claims[0]
        assert outcome.decision.status is ClaimStatus.CONTRADICTED
        # The person's own page is this claim's evidence all the same: it rated it.
        assert any(is_shared_review(e.match_basis.metric) for e in outcome.evidence)
        assert outcome.explanation == (
            "This link is a fact-check by BOOM, a certified fact-checker. Its rating of "
            "this claim: “False”. 1 other source says the same."
        )
        assert result.action is Action.DO_NOT_SHARE

    @pytest.mark.anyio
    async def test_for_any_other_claim_the_page_is_still_the_person_s_own(self) -> None:
        from app.domain.evidence import is_shared_review

        result = await self._verify("cl_1", self._shared())

        assert not any(is_shared_review(e.match_basis.metric) for e in result.claims[0].evidence)
        assert self.PAGE not in [e.citation_url for e in result.claims[0].evidence]

    def test_its_own_rating_is_not_re_read_by_the_source_check(self) -> None:
        import asyncio

        from app.domain.evidence import SHARED_REVIEW, MatchBasis
        from app.sources.verification import SourceVerification

        class _Checker:
            asked = 0

            async def check_sources(self, _claim: str, _sources: object) -> None:
                _Checker.asked += 1

        class _Ranker:
            def credibility(self, _url: object) -> None:
                return None

        rating = evidence(
            citation_url=self.PAGE,
            basis=MatchBasis(metric=SHARED_REVIEW, value=1.0, threshold=0.95),
        )
        verified = asyncio.run(
            SourceVerification(checker=_Checker(), ranker=_Ranker()).check(
                claim(text=self.VIRAL), [rating]
            )
        )

        assert _Checker.asked == 0
        assert [e.citation_url for e in verified.evidence] == [self.PAGE]


class TestAFactCheckPageThatWillNotServeUs:
    """bangla.boomlive.in answers our fetcher with 403: its rating is looked up where
    the fact-checker filed it, the fact-check index, by the page's address."""

    PAGE = "https://bangla.boomlive.in/fact-check/some-viral-claim-32197"

    class _Fetcher:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload
            self.asked: list[str] = []

        async def fetch(self, url: str, **_: Any) -> Any:
            import json
            from datetime import UTC, datetime

            from app.security.fetcher import FetchResult

            self.asked.append(url)
            body = json.dumps(self.payload).encode()
            return FetchResult(
                url=url,
                final_url=url,
                status_code=200,
                content_type="application/json",
                body=body,
                byte_count=len(body),
                fetched_at=datetime.now(UTC),
            )

    def _resolver(self, payload: dict[str, Any]) -> Any:
        from app.sources.factcheck import FactCheckResolver
        from tests.unit.test_verdict_fixes import _Governor

        return FactCheckResolver(
            records=[],
            governor=_Governor(),
            api_available=True,
            fetcher=self._Fetcher(payload),  # type: ignore[arg-type]
            endpoint="https://index.example/claims:search",
            api_key="test-key",
        )

    def test_the_page_s_own_rating_is_found_by_its_address(self) -> None:
        import asyncio

        resolver = self._resolver(
            {
                "claims": [
                    {
                        "text": "Another claim",
                        "claimReview": [{"url": "https://bangla.boomlive.in/fact-check/x-1"}],
                    },
                    {
                        "text": "ভিডিও দাবি করে স্মৃতি ইরানি দেবী দুর্গাকে অসম্মান করেছেন",
                        "claimReview": [
                            {
                                "url": "http://www.bangla.boomlive.in/fact-check/some-viral-claim-32197/",
                                "textualRating": "মিথ্যা",
                                "publisher": {"name": "BOOM", "site": "boomlive.in"},
                            }
                        ],
                    },
                ]
            }
        )

        [record] = asyncio.run(resolver.published_ratings(self.PAGE))

        assert record.url == self.PAGE
        assert record.publisher == "BOOM"
        # A Bengali rating is read as the false rating it is.
        from app.domain.enums import Relation

        assert record.verdict is Relation.CONTRADICTS
        assert "reviewPublisherSiteFilter=bangla.boomlive.in" in resolver._fetcher.asked[0]

    def test_nothing_when_the_index_does_not_list_the_page(self) -> None:
        import asyncio

        resolver = self._resolver({"claims": []})

        assert asyncio.run(resolver.published_ratings(self.PAGE)) == []

    @pytest.mark.parametrize(
        "rating",
        ["মিথ্যা", "தவறு", "తప్పు", "ಸುಳ್ಳು", "തെറ്റ്", "ਝੂਠ", "ખોટું", "खोटे", "ମିଥ୍ୟା", "جھوٹ"],
    )
    def test_a_false_rating_in_each_language_is_read(self, rating: str) -> None:
        from app.domain.enums import Relation
        from app.sources.factcheck import FactCheckRecord

        record = FactCheckRecord(
            claim_text="x", normalized_text="x", url="https://f/1", rating=rating, publisher=None
        )
        assert record.verdict is Relation.CONTRADICTS
