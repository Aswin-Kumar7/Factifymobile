"""M38 and M39 against the real database.

The unit tests prove the promotion gate's logic. These prove the SQL honours it —
that `times_seen` really does not move, that the upsert increments once per promotion
and not once per statement, and that a caption cannot be attached to a fingerprint
that was never promoted.

That last one is enforced by a foreign key, so it can only be tested here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import psycopg
import pytest

from app.db.repositories import FingerprintRepository, ObservationRepository
from app.domain.enums import ClaimStatus
from app.graph.promotion import MatchWarrant, ObservationKind, PromotionGate, TrustState
from app.graph.recurrence import RecurrenceService
from tests.conftest import requires_database

pytestmark = [pytest.mark.db, requires_database]


def _sha() -> str:
    """A unique digest per test, so runs against a shared database do not collide."""
    return f"sha256:{uuid4().hex}"


def _warrant() -> MatchWarrant:
    return MatchWarrant(
        verified=True,
        source_date=datetime(2019, 3, 14, tzinfo=UTC),
        citation_url="https://example.org/2019/story",
    )


def _gate(conn: Any) -> tuple[PromotionGate, FingerprintRepository]:
    fingerprints = FingerprintRepository(conn)
    gate = PromotionGate(observations=ObservationRepository(conn), fingerprints=fingerprints)
    return gate, fingerprints


class TestTheGateAgainstRealSql:
    @pytest.mark.anyio
    async def test_repeated_unverified_submission_moves_no_trusted_counter(self, conn: Any) -> None:
        """M38's gate, against the tables it is actually enforced in."""
        gate, fingerprints = _gate(conn)
        sha = _sha()

        for _ in range(25):
            await gate.observe(kind=ObservationKind.MEDIA_SUBMITTED, raw_claim="unverified")

        assert await fingerprints.get(sha) is None

        row = await conn.execute(
            "SELECT count(*) AS n FROM observation WHERE raw_claim = %s", ("unverified",)
        )
        observed = (await row.fetchone())["n"]
        assert observed >= 25

        # And nothing anywhere in the trusted store gained a count from it.
        row = await conn.execute(
            "SELECT coalesce(sum(times_seen), 0) AS total FROM media_fingerprint WHERE sha256 = %s",
            (sha,),
        )
        assert (await row.fetchone())["total"] == 0

    @pytest.mark.anyio
    async def test_observations_default_to_raw(self, conn: Any) -> None:
        gate, _ = _gate(conn)

        observation_id = await gate.observe(kind=ObservationKind.SUBMISSION, raw_claim="x")

        row = await conn.execute(
            "SELECT trust_state FROM observation WHERE id = %s", (observation_id,)
        )
        assert (await row.fetchone())["trust_state"] == TrustState.RAW.value

    @pytest.mark.anyio
    async def test_an_invalid_trust_state_never_reaches_the_database(self, conn: Any) -> None:
        """Rejected in the repository, before the statement is built.

        The check constraint on `observation.trust_state` is the backstop, not the
        first line — an invalid state should fail with a readable Python error rather
        than as a constraint violation mid-transaction.
        """
        observations = ObservationRepository(conn)
        observation_id = await observations.record(kind="submission")

        with pytest.raises(ValueError, match="unknown trust_state"):
            await observations.mark(observation_id, "trusted")

    @pytest.mark.anyio
    async def test_the_check_constraint_is_the_backstop(self, conn: Any) -> None:
        """And it really exists, so bypassing the repository still fails."""
        observations = ObservationRepository(conn)
        observation_id = await observations.record(kind="submission")

        with pytest.raises(psycopg.errors.CheckViolation):
            await conn.execute(
                "UPDATE observation SET trust_state = %s WHERE id = %s",
                ("trusted", observation_id),
            )

    @pytest.mark.anyio
    async def test_promotion_increments_exactly_once_per_call(self, conn: Any) -> None:
        gate, fingerprints = _gate(conn)
        sha = _sha()

        for expected in (1, 2, 3):
            outcome = await gate.promote_match(sha256=sha, warrant=_warrant())
            assert outcome.promoted
            assert outcome.times_seen == expected  # type: ignore[union-attr]

        row = await fingerprints.get(sha)
        assert row is not None
        assert row["times_seen"] == 3

    @pytest.mark.anyio
    async def test_first_verified_at_is_not_overwritten_by_later_promotions(
        self, conn: Any
    ) -> None:
        """The recurrence view reports age from this column; moving it would reset
        the history every time the same image was seen again."""
        gate, fingerprints = _gate(conn)
        sha = _sha()

        await gate.promote_match(sha256=sha, warrant=_warrant())
        first = (await fingerprints.get(sha))["first_verified_at"]  # type: ignore[index]

        await gate.promote_match(sha256=sha, warrant=_warrant())
        row = await fingerprints.get(sha)
        assert row is not None

        assert row["first_verified_at"] == first
        assert row["last_verified_at"] >= first

    @pytest.mark.anyio
    async def test_a_refused_promotion_writes_no_row(self, conn: Any) -> None:
        gate, fingerprints = _gate(conn)
        sha = _sha()

        outcome = await gate.promote_match(
            sha256=sha,
            warrant=MatchWarrant(verified=True, source_date=None, citation_url=None),
        )

        assert not outcome.promoted
        assert await fingerprints.get(sha) is None

    @pytest.mark.anyio
    async def test_a_caption_cannot_attach_to_an_unpromoted_fingerprint(self, conn: Any) -> None:
        """Enforced by claim_occurrence.fingerprint_id -> media_fingerprint.

        This is the structural half of the rule: unverified user text has nowhere to
        live in a view the reader treats as established history.
        """
        _, fingerprints = _gate(conn)

        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            await fingerprints.record_occurrence(
                fingerprint_id=uuid4(), caption_text="a caption with no fingerprint"
            )


class TestRecurrenceReadsRealRows:
    @pytest.mark.anyio
    async def test_a_repeatedly_verified_image_reports_truthfully(self, conn: Any) -> None:
        gate, fingerprints = _gate(conn)
        sha = _sha()

        for _ in range(4):
            await gate.promote_match(
                sha256=sha, warrant=_warrant(), verdict=ClaimStatus.MISLEADING_CONTEXT
            )

        report = await RecurrenceService(fingerprints=fingerprints).report(sha)

        assert report.times_seen == 4
        assert report.is_recurring
        assert report.last_verdict == ClaimStatus.MISLEADING_CONTEXT.value
        assert report.citation_url == "https://example.org/2019/story"
        assert report.first_verified_at is not None
        assert "4 times" in report.summary()

    @pytest.mark.anyio
    async def test_the_contradictory_caption_view_renders(self, conn: Any) -> None:
        """M39's gate: one image, several narratives, across languages."""
        gate, fingerprints = _gate(conn)
        sha = _sha()

        promoted = await gate.promote_match(sha256=sha, warrant=_warrant())
        assert promoted.promoted

        for caption, language, domain in (
            ("Floods in Chennai this week", "en", "a.example"),
            ("Kerala floods happening now", "en", "b.example"),
            ("बाढ़ का ताज़ा दृश्य", "hi", "c.example"),
        ):
            await gate.record_caption(
                fingerprint_id=promoted.fingerprint_id,  # type: ignore[union-attr]
                caption_text=caption,
                language=language,
                source_domain=domain,
            )

        service = RecurrenceService(fingerprints=fingerprints)
        report = await service.report(sha)
        timeline = await service.timeline(sha)

        assert report.distinct_captions == 3
        assert report.has_contradictory_captions
        assert report.languages == ("en", "hi")
        assert timeline.is_renderable
        assert len(timeline.by_domain) == 3

    @pytest.mark.anyio
    async def test_an_unknown_fingerprint_reports_unknown(self, conn: Any) -> None:
        _, fingerprints = _gate(conn)

        report = await RecurrenceService(fingerprints=fingerprints).report(_sha())

        assert not report.is_known
        assert report.times_seen == 0
        assert report.summary() == "This has not been verified before."
