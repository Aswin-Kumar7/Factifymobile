"""M38 and M39 — the promotion gate and the recurrence views.

The M38 gate ("repeatedly submitting the same unverified content increments
observations and does not move any trusted counter") is asserted here against
recording repositories, and again in tests/db against real Postgres. This version
proves the gate logic; that one proves the SQL honours it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.domain.enums import ClaimStatus
from app.graph.promotion import (
    MatchWarrant,
    ObservationKind,
    PromotionBasis,
    PromotionGate,
    TrustState,
)
from app.graph.recurrence import (
    MIN_SIGHTINGS_TO_CALL_IT_RECURRING,
    CaptionTimeline,
    CaptionVariant,
    RecurrenceReport,
    RecurrenceService,
)

pytestmark = pytest.mark.unit


class RecordingObservations:
    """Stands in for ObservationRepository, remembering what it was told."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.marks: list[tuple[UUID, str]] = []

    async def record(self, **kwargs: Any) -> UUID:
        identifier = uuid4()
        self.records.append({"id": identifier, **kwargs})
        return identifier

    async def mark(self, observation_id: UUID, trust_state: str) -> None:
        self.marks.append((observation_id, trust_state))

    async def count_for_case(self, case_id: UUID) -> int:
        return sum(1 for r in self.records if r.get("case_id") == case_id)


class RecordingFingerprints:
    """Stands in for FingerprintRepository, with the real upsert semantics.

    `promote` increments on conflict exactly as the SQL does, so a test that expects
    the counter to stay still is testing the gate rather than a fake that cannot
    count.
    """

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.captions: dict[UUID, list[dict[str, Any]]] = {}
        self.promote_calls = 0

    async def promote(
        self,
        *,
        sha256: str,
        phash: str | None = None,
        last_verdict: str | None = None,
        source_date: datetime | None = None,
        citation_url: str | None = None,
    ) -> UUID:
        self.promote_calls += 1
        now = datetime.now(UTC)

        if sha256 in self.rows:
            row = self.rows[sha256]
            row["times_seen"] += 1
            row["last_verified_at"] = now
            row["last_verdict"] = last_verdict or row["last_verdict"]
            row["source_date"] = source_date or row["source_date"]
            row["citation_url"] = citation_url or row["citation_url"]
            return UUID(str(row["id"]))

        identifier = uuid4()
        self.rows[sha256] = {
            "id": identifier,
            "sha256": sha256,
            "phash": phash,
            "times_seen": 1,
            "first_verified_at": now,
            "last_verified_at": now,
            "last_verdict": last_verdict,
            "source_date": source_date,
            "citation_url": citation_url,
        }
        return identifier

    async def get(self, sha256: str) -> dict[str, Any] | None:
        return self.rows.get(sha256)

    async def record_occurrence(
        self,
        *,
        fingerprint_id: UUID,
        caption_text: str | None = None,
        claim_id: UUID | None = None,
        case_id: UUID | None = None,
        language: str | None = None,
        source_domain: str | None = None,
    ) -> UUID:
        identifier = uuid4()
        self.captions.setdefault(fingerprint_id, []).append(
            {
                "id": identifier,
                "observed_at": datetime.now(UTC),
                "caption_text": caption_text,
                "claim_id": claim_id,
                "case_id": case_id,
                "language": language,
                "source_domain": source_domain,
            }
        )
        return identifier

    # Named to match FingerprintRepository exactly. A stub whose method names drift
    # from the real repository passes tests the production path would fail.
    async def occurrences(self, fingerprint_id: UUID) -> list[dict[str, Any]]:
        return sorted(self.captions.get(fingerprint_id, []), key=lambda r: r["observed_at"])


def _gate() -> tuple[PromotionGate, RecordingObservations, RecordingFingerprints]:
    observations = RecordingObservations()
    fingerprints = RecordingFingerprints()
    gate = PromotionGate(observations=observations, fingerprints=fingerprints)  # type: ignore[arg-type]
    return gate, observations, fingerprints


def _good_warrant() -> MatchWarrant:
    return MatchWarrant(
        verified=True,
        source_date=datetime(2019, 3, 14, tzinfo=UTC),
        citation_url="https://example.org/2019/story",
        matched_sha256="sha256:original",
    )


# ------------------------------------------------------------------ M38 · the gate


class TestTheRecurrenceCounterAttack:
    """M38's gate. This is the reason the module exists."""

    @pytest.mark.anyio
    async def test_repeated_unverified_submission_moves_no_trusted_counter(self) -> None:
        """Five hundred submissions of the same fabricated image prove nothing."""
        gate, observations, fingerprints = _gate()

        for _ in range(500):
            await gate.observe(kind=ObservationKind.MEDIA_SUBMITTED, raw_claim="a fabricated image")

        assert len(observations.records) == 500
        assert fingerprints.promote_calls == 0
        assert fingerprints.rows == {}

    @pytest.mark.anyio
    async def test_an_unverified_match_is_refused(self) -> None:
        gate, _, fingerprints = _gate()

        outcome = await gate.promote_match(
            sha256="sha256:x",
            warrant=MatchWarrant(verified=False, source_date=None, citation_url=None),
        )

        assert not outcome.promoted
        assert fingerprints.promote_calls == 0

    @pytest.mark.anyio
    async def test_a_verified_match_without_a_date_is_refused(self) -> None:
        """'This image existed before' is not a finding. *When* is the finding."""
        gate, _, fingerprints = _gate()

        outcome = await gate.promote_match(
            sha256="sha256:x",
            warrant=MatchWarrant(
                verified=True, source_date=None, citation_url="https://example.org/x"
            ),
        )

        assert not outcome.promoted
        assert "no publication date" in outcome.reason  # type: ignore[union-attr]
        assert fingerprints.promote_calls == 0

    @pytest.mark.anyio
    async def test_a_verified_dated_match_without_a_citation_is_refused(self) -> None:
        gate, _, fingerprints = _gate()

        outcome = await gate.promote_match(
            sha256="sha256:x",
            warrant=MatchWarrant(
                verified=True, source_date=datetime(2019, 3, 14, tzinfo=UTC), citation_url=None
            ),
        )

        assert not outcome.promoted
        assert fingerprints.promote_calls == 0

    @pytest.mark.anyio
    async def test_a_reviewed_finding_still_needs_a_citation(self) -> None:
        """Review says a human judged it sound, not that a source exists."""
        gate, _, fingerprints = _gate()

        outcome = await gate.promote_reviewed(sha256="sha256:x", citation_url="")

        assert not outcome.promoted
        assert fingerprints.promote_calls == 0


class TestPromotionWhenWarranted:
    @pytest.mark.anyio
    async def test_a_validated_match_promotes(self) -> None:
        gate, _, fingerprints = _gate()

        outcome = await gate.promote_match(
            sha256="sha256:x", warrant=_good_warrant(), verdict=ClaimStatus.MISLEADING_CONTEXT
        )

        assert outcome.promoted
        assert outcome.basis is PromotionBasis.VALIDATED_MATCH  # type: ignore[union-attr]
        assert outcome.times_seen == 1  # type: ignore[union-attr]
        assert fingerprints.rows["sha256:x"]["citation_url"] == "https://example.org/2019/story"

    @pytest.mark.anyio
    async def test_a_reviewed_finding_promotes(self) -> None:
        gate, _, fingerprints = _gate()

        outcome = await gate.promote_reviewed(
            sha256="sha256:x", citation_url="https://example.org/reviewed"
        )

        assert outcome.promoted
        assert outcome.basis is PromotionBasis.REVIEWED_FINDING  # type: ignore[union-attr]
        assert fingerprints.rows["sha256:x"]["citation_url"] == "https://example.org/reviewed"

    @pytest.mark.anyio
    async def test_repeated_verified_matches_do_increment(self) -> None:
        """The counter is not frozen — it moves for the right reason."""
        gate, _, fingerprints = _gate()

        for _ in range(3):
            outcome = await gate.promote_match(sha256="sha256:x", warrant=_good_warrant())

        assert outcome.times_seen == 3  # type: ignore[union-attr]
        assert fingerprints.rows["sha256:x"]["times_seen"] == 3

    @pytest.mark.anyio
    async def test_promotion_marks_its_observation(self) -> None:
        gate, observations, _ = _gate()

        observation_id = await gate.observe(kind=ObservationKind.MEDIA_SUBMITTED)
        await gate.promote_match(
            sha256="sha256:x", warrant=_good_warrant(), observation_id=observation_id
        )

        assert observations.marks == [(observation_id, TrustState.PROMOTED.value)]

    @pytest.mark.anyio
    async def test_observing_never_marks_anything_promoted(self) -> None:
        gate, observations, _ = _gate()

        await gate.observe(kind=ObservationKind.SUBMISSION, raw_claim="something")

        assert observations.marks == []

    @pytest.mark.anyio
    async def test_an_empty_caption_records_nothing(self) -> None:
        gate, _, fingerprints = _gate()

        assert await gate.record_caption(fingerprint_id=uuid4(), caption_text=None) is None
        assert await gate.record_caption(fingerprint_id=uuid4(), caption_text="") is None
        assert fingerprints.captions == {}


# ----------------------------------------------------------- M39 · the read views


def _variant(
    caption: str, *, days_ago: int = 0, language: str = "en", domain: str = "x.example"
) -> CaptionVariant:
    return CaptionVariant(
        caption=caption,
        observed_at=datetime.now(UTC) - timedelta(days=days_ago),
        language=language,
        source_domain=domain,
    )


class TestRecurrenceReport:
    def test_an_unknown_fingerprint_says_so(self) -> None:
        report = RecurrenceReport(sha256="sha256:unknown")

        assert not report.is_known
        assert not report.is_recurring
        assert report.summary() == "This has not been verified before."

    def test_one_sighting_is_not_recurring(self) -> None:
        report = RecurrenceReport(sha256="x", times_seen=1)

        assert report.is_known
        assert not report.is_recurring
        assert "once" in report.summary()

    def test_the_recurring_threshold_holds(self) -> None:
        below = RecurrenceReport(sha256="x", times_seen=MIN_SIGHTINGS_TO_CALL_IT_RECURRING - 1)
        at = RecurrenceReport(sha256="x", times_seen=MIN_SIGHTINGS_TO_CALL_IT_RECURRING)

        assert not below.is_recurring
        assert at.is_recurring

    def test_age_is_measured_from_our_first_verification(self) -> None:
        """Not from the source date — the corpus is weeks old, and claiming to have
        watched something since 2019 would be a lie told by an off-by-one field."""
        report = RecurrenceReport(
            sha256="x",
            times_seen=4,
            first_verified_at=datetime.now(UTC) - timedelta(days=45),
            source_date=datetime(2019, 3, 14, tzinfo=UTC),
        )

        assert report.age == "over 1 months"
        assert "2019" not in report.summary()

    def test_contradictory_captions_are_detected(self) -> None:
        report = RecurrenceReport(
            sha256="x",
            times_seen=3,
            captions=(
                _variant("Floods in Chennai"),
                _variant("Floods in Kerala"),
                _variant("बाढ़ का दृश्य", language="hi"),
            ),
        )

        assert report.has_contradictory_captions
        assert report.distinct_captions == 3
        assert report.languages == ("en", "hi")
        assert "3 different captions" in report.summary()
        assert "2 languages" in report.summary()

    def test_the_same_caption_repeated_is_not_contradictory(self) -> None:
        report = RecurrenceReport(
            sha256="x",
            times_seen=3,
            captions=(_variant("Floods in Chennai"), _variant("  floods in chennai  ")),
        )

        assert report.distinct_captions == 1
        assert not report.has_contradictory_captions

    def test_the_summary_never_states_an_uncounted_number(self) -> None:
        report = RecurrenceReport(sha256="x", times_seen=2, captions=(_variant("One story"),))

        summary = report.summary()
        assert "2 times" in summary
        assert "captions" not in summary


class TestCaptionTimeline:
    def test_one_caption_is_not_a_timeline(self) -> None:
        timeline = CaptionTimeline(sha256="x", variants=(_variant("Only story"),))

        assert not timeline.is_renderable

    def test_two_distinct_captions_render(self) -> None:
        timeline = CaptionTimeline(sha256="x", variants=(_variant("Story A"), _variant("Story B")))

        assert timeline.is_renderable

    def test_domains_are_counted(self) -> None:
        timeline = CaptionTimeline(
            sha256="x",
            variants=(
                _variant("A", domain="a.example"),
                _variant("B", domain="a.example"),
                _variant("C", domain="b.example"),
            ),
        )

        assert timeline.by_domain == (("a.example", 2), ("b.example", 1))

    def test_the_span_covers_oldest_to_newest(self) -> None:
        timeline = CaptionTimeline(
            sha256="x", variants=(_variant("A", days_ago=10), _variant("B", days_ago=2))
        )

        span = timeline.span
        assert span is not None
        assert span[0] < span[1]

    def test_an_empty_timeline_has_no_span(self) -> None:
        assert CaptionTimeline(sha256="x").span is None


class TestRecurrenceReadsOnlyPromotedRows:
    """M39's rule: never count unpromoted observations in a user-facing figure."""

    @pytest.mark.anyio
    async def test_observations_alone_produce_an_unknown_report(self) -> None:
        gate, observations, fingerprints = _gate()

        for _ in range(50):
            await gate.observe(kind=ObservationKind.MEDIA_SUBMITTED, raw_claim="same image")

        # The read path is wired to the fingerprint store and has no route to the
        # observation table at all — the isolation is structural, not a filter that
        # could be forgotten.
        service = RecurrenceService(fingerprints=fingerprints)  # type: ignore[arg-type]
        report = await service.report("sha256:whatever")

        assert len(observations.records) == 50
        assert not report.is_known
        assert report.times_seen == 0

    @pytest.mark.anyio
    async def test_an_empty_caption_is_not_a_variant(self) -> None:
        """A promoted fingerprint with no caption must not render an empty row."""
        gate, _, fingerprints = _gate()

        promoted = await gate.promote_match(sha256="sha256:x", warrant=_good_warrant())
        assert promoted.promoted
        await fingerprints.record_occurrence(
            fingerprint_id=promoted.fingerprint_id,  # type: ignore[union-attr]
            caption_text=None,
        )

        report = await RecurrenceService(fingerprints=fingerprints).report("sha256:x")  # type: ignore[arg-type]

        assert report.is_known
        assert report.captions == ()


class TestTheFullWriteThenReadPath:
    """M39's gate, driven through both services rather than constructed by hand."""

    @pytest.mark.anyio
    async def test_a_repeatedly_verified_image_reports_truthfully(self) -> None:
        gate, _, fingerprints = _gate()

        for _ in range(4):
            await gate.promote_match(
                sha256="sha256:recycled",
                warrant=_good_warrant(),
                verdict=ClaimStatus.MISLEADING_CONTEXT,
            )

        report = await RecurrenceService(fingerprints=fingerprints).report("sha256:recycled")  # type: ignore[arg-type]

        assert report.times_seen == 4
        assert report.is_recurring
        assert report.first_verified_at is not None
        assert report.last_verdict == ClaimStatus.MISLEADING_CONTEXT.value
        assert report.citation_url == "https://example.org/2019/story"
        assert "4 times" in report.summary()

    @pytest.mark.anyio
    async def test_one_image_several_narratives_renders(self) -> None:
        """The demo beat: one photograph, contradictory stories, across languages."""
        gate, _, fingerprints = _gate()

        promoted = await gate.promote_match(sha256="sha256:recycled", warrant=_good_warrant())
        assert promoted.promoted
        fingerprint_id = promoted.fingerprint_id  # type: ignore[union-attr]

        for caption, language, domain in (
            ("Floods in Chennai this week", "en", "a.example"),
            ("Kerala floods happening now", "en", "b.example"),
            ("बाढ़ का ताज़ा दृश्य", "hi", "c.example"),
        ):
            await gate.record_caption(
                fingerprint_id=fingerprint_id,
                caption_text=caption,
                language=language,
                source_domain=domain,
            )

        service = RecurrenceService(fingerprints=fingerprints)  # type: ignore[arg-type]
        report = await service.report("sha256:recycled")
        timeline = await service.timeline("sha256:recycled")

        assert report.distinct_captions == 3
        assert report.has_contradictory_captions
        assert report.languages == ("en", "hi")
        assert timeline.is_renderable
        assert len(timeline.by_domain) == 3
        assert timeline.span is not None

    @pytest.mark.anyio
    async def test_captions_cannot_attach_without_a_promotion(self) -> None:
        """Unverified user text must never reach a view read as established history.

        Enforced by the schema — claim_occurrence.fingerprint_id references
        media_fingerprint — so there is no fingerprint id to attach to until
        something has been promoted.
        """
        gate, _, fingerprints = _gate()

        refused = await gate.promote_match(
            sha256="sha256:x",
            warrant=MatchWarrant(verified=True, source_date=None, citation_url=None),
        )

        assert not refused.promoted
        assert not hasattr(refused, "fingerprint_id")
        assert fingerprints.captions == {}
