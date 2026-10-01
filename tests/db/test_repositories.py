"""M03 — a round-trip write and read through a repository for every aggregate.

Requires a real Postgres with pgvector:

    TEST_DATABASE_URL=postgresql://... uv run pytest -m db
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.db.repositories import (
    AuditRepository,
    BudgetRepository,
    CacheRepository,
    CaseRepository,
    ClaimRepository,
    CorpusRepository,
    EvidenceRepository,
    FeedRepository,
    FingerprintRepository,
    ObservationRepository,
    ReviewRepository,
    SourceRepository,
    VerdictRepository,
)
from tests.conftest import requires_database

pytestmark = [pytest.mark.db, requires_database]

ANCHOR: dict[str, Any] = {
    "input_kind": "url",
    "section": "article_body",
    "paragraph_index": 3,
    "char_start": 412,
    "char_end": 458,
    "content_hash": "sha256:fixture",
}


async def _case_with_claim(conn: Any) -> tuple[Any, Any]:
    case_id = await CaseRepository(conn).create(request_id="req-1", input_type="url")
    claim_id = await ClaimRepository(conn).create(
        case_id=case_id,
        text="The eruption happened in China on 14 August.",
        normalized_text="the eruption happened in china on 14 august",
        claim_type="EVENT",
        severity="HIGH",
        importance="MAIN_THESIS",
        anchor=ANCHOR,
    )
    return case_id, claim_id


async def _snapshot(conn: Any) -> Any:
    source_id = await SourceRepository(conn).upsert_source(
        domain="example.org", publisher="Example", source_class="news"
    )
    return await SourceRepository(conn).record_snapshot(
        source_id=source_id,
        url="https://example.org/story",
        final_url="https://example.org/story",
        content_hash="sha256:page",
        http_status=200,
        excerpt="The same image was published on 14 March 2019.",
    )


class TestCase:
    async def test_case_and_content_object_round_trip(self, conn: Any) -> None:
        case_id = await CaseRepository(conn).create(
            request_id="req-abc", input_type="image", language="hi"
        )
        object_id = await CaseRepository(conn).add_content_object(
            case_id=case_id, kind="image", sha256="sha256:image", mime_type="image/jpeg"
        )

        case = await CaseRepository(conn).get(case_id)
        objects = await CaseRepository(conn).content_objects(case_id)

        assert case is not None
        assert case["request_id"] == "req-abc"
        assert case["status"] == "pending"
        assert [o["id"] for o in objects] == [object_id]


class TestClaim:
    async def test_claim_is_stored_with_its_anchor(self, conn: Any) -> None:
        _, claim_id = await _case_with_claim(conn)

        claim = await (
            await conn.execute("SELECT * FROM claim WHERE id = %s", (claim_id,))
        ).fetchone()
        anchors = await ClaimRepository(conn).anchors(claim_id)

        assert claim is not None
        assert claim["claim_type"] == "EVENT"
        assert len(anchors) == 1
        assert anchors[0]["paragraph_index"] == 3
        assert anchors[0]["char_end"] == 458


class TestEvidence:
    async def test_evidence_round_trip(self, conn: Any) -> None:
        _, claim_id = await _case_with_claim(conn)
        snapshot_id = await _snapshot(conn)

        await EvidenceRepository(conn).add_evidence(
            claim_id=claim_id,
            tier="B",
            kind="dated_source",
            direction="contradicts",
            finding="Published by Example on 2019-03-14.",
            citation_url="https://example.org/original",
            snapshot_id=snapshot_id,
            source_excerpt="published on 14 March 2019",
            source_anchor={"paragraph_index": 2},
            method="matched_page_date",
            match_quality="STRONG",
            match_basis={"metric": "clip_cosine", "value": 0.94, "threshold": 0.90},
        )

        rows = await EvidenceRepository(conn).for_claim(claim_id)

        assert len(rows) == 1
        assert rows[0]["match_quality"] == "STRONG"
        assert rows[0]["match_basis"]["threshold"] == 0.90

    async def test_advisory_is_stored_apart_from_evidence(self, conn: Any) -> None:
        """Tier E never lands in the table the verdict engine reads."""
        case_id, claim_id = await _case_with_claim(conn)

        await EvidenceRepository(conn).add_advisory(
            case_id=case_id,
            provider="noise_inconsistency",
            signal="ADVISORY_SUSPICION",
            note="Not used in this verdict.",
            score=0.78,
        )

        assert await EvidenceRepository(conn).for_claim(claim_id) == []
        assert len(await EvidenceRepository(conn).advisories_for_case(case_id)) == 1


class TestVerdict:
    async def test_verdict_round_trip(self, conn: Any) -> None:
        _, claim_id = await _case_with_claim(conn)

        await VerdictRepository(conn).record(
            claim_id=claim_id,
            status="CONTRADICTED",
            action="DO_NOT_SHARE",
            reason="The asserted date is false.",
            rule_id="rule.dated_media_conflict",
            rule_version="2026.08.1",
            strength={"score": 0.91, "components": ["dated_media_match"]},
        )

        verdict = await VerdictRepository(conn).for_claim(claim_id)

        assert verdict is not None
        assert verdict["status"] == "CONTRADICTED"
        assert verdict["rule_version"] == "2026.08.1"


class TestObservationAndPromotion:
    async def test_repeated_submission_does_not_move_a_trusted_counter(self, conn: Any) -> None:
        """The obvious attack on a recurrence counter, closed at the repository."""
        case_id, _ = await _case_with_claim(conn)
        observations = ObservationRepository(conn)

        for _ in range(5):
            await observations.record(case_id=case_id, kind="media_probe")

        row = await (
            await conn.execute(
                "SELECT count(*) AS n FROM observation WHERE case_id = %s", (case_id,)
            )
        ).fetchone()
        assert row["n"] == 5
        assert await FingerprintRepository(conn).get("sha256:never-validated") is None

    async def test_promotion_moves_the_counter(self, conn: Any) -> None:
        fingerprints = FingerprintRepository(conn)

        await fingerprints.promote(sha256="sha256:validated", last_verdict="MISLEADING_CONTEXT")
        await fingerprints.promote(sha256="sha256:validated")

        record = await fingerprints.get("sha256:validated")

        assert record is not None
        assert record["times_seen"] == 2
        assert record["first_verified_at"] is not None

    async def test_occurrences_capture_contradictory_captions(self, conn: Any) -> None:
        fingerprint_id = await FingerprintRepository(conn).promote(sha256="sha256:recycled")

        for caption in ("Protests in France", "Riots in London", "Clashes in Delhi"):
            await FingerprintRepository(conn).record_occurrence(
                fingerprint_id=fingerprint_id, caption_text=caption
            )

        occurrences = await FingerprintRepository(conn).occurrences(fingerprint_id)

        assert [o["caption_text"] for o in occurrences] == [
            "Protests in France",
            "Riots in London",
            "Clashes in Delhi",
        ]

    async def test_near_misses_are_recorded_for_calibration(self, conn: Any) -> None:
        case_id = await CaseRepository(conn).create(request_id="r", input_type="image")
        object_id = await CaseRepository(conn).add_content_object(
            case_id=case_id, kind="image", sha256="sha256:candidate"
        )

        match_id = await FingerprintRepository(conn).record_match_attempt(
            content_object_id=object_id,
            metric="clip_cosine",
            distance=0.71,
            threshold=0.90,
            verified=False,
        )

        assert match_id is not None


class TestSourceAndRelations:
    async def test_snapshot_and_relation_round_trip(self, conn: Any) -> None:
        _, claim_id = await _case_with_claim(conn)
        snapshot_id = await _snapshot(conn)

        await SourceRepository(conn).record_relation(
            claim_id=claim_id,
            snapshot_id=snapshot_id,
            relation="INSUFFICIENT",
            validator="official_source",
            validator_version="1",
        )

        snapshot = await SourceRepository(conn).get_snapshot(snapshot_id)

        assert snapshot is not None
        assert snapshot["http_status"] == 200


class TestCorpus:
    async def test_corpus_item_and_origin_cluster_round_trip(self, conn: Any) -> None:
        corpus = CorpusRepository(conn)
        cluster_id = await corpus.create_cluster(
            minhash_signature=b"\x01\x02", canonical_publisher="Wire"
        )

        first = await corpus.upsert_item(
            canonical_url="https://a.example/story", content_hash="h1", publisher="A"
        )
        second = await corpus.upsert_item(
            canonical_url="https://b.example/story", content_hash="h1", publisher="B"
        )
        await corpus.assign_to_cluster(item_id=first, cluster_id=cluster_id)
        await corpus.assign_to_cluster(item_id=second, cluster_id=cluster_id)

        assert await corpus.distinct_origin_count([first, second]) == 1

    async def test_unclustered_items_count_as_distinct_origins(self, conn: Any) -> None:
        corpus = CorpusRepository(conn)
        first = await corpus.upsert_item(canonical_url="https://a.example/x", content_hash="h1")
        second = await corpus.upsert_item(canonical_url="https://b.example/y", content_hash="h2")

        assert await corpus.distinct_origin_count([first, second]) == 2

    async def test_factcheck_record_round_trip(self, conn: Any) -> None:
        record_id = await CorpusRepository(conn).record_factcheck(
            claim_text="A claim",
            normalized_text="a claim",
            url="https://factchecker.example/a",
            rating="False",
            publisher="Factchecker",
        )

        assert record_id is not None


class TestCache:
    async def test_verdict_cache_round_trip(self, conn: Any) -> None:
        cache = CacheRepository(conn)

        await cache.put_verdict(
            cache_key="key-1",
            status_json={"overall_action": "SEND_TO_REVIEW"},
            rule_version="2026.08.1",
            extractor_version="1",
            corpus_version="1",
            policy_profile="default",
        )
        cached = await cache.get_verdict("key-1")

        assert cached is not None
        assert cached["status_json"]["overall_action"] == "SEND_TO_REVIEW"

    async def test_expired_entry_is_not_served(self, conn: Any) -> None:
        cache = CacheRepository(conn)

        await cache.put_verdict(
            cache_key="key-expired",
            status_json={},
            rule_version="1",
            extractor_version="1",
            corpus_version="1",
            policy_profile="default",
            expires_at=datetime(2000, 1, 1, tzinfo=UTC),
        )

        assert await cache.get_verdict("key-expired") is None

    async def test_extraction_cache_round_trip(self, conn: Any) -> None:
        cache = CacheRepository(conn)

        await cache.put_extraction(
            content_hash="h", extractor_version="1", payload={"claims": []}, model_id="m"
        )
        cached = await cache.get_extraction(content_hash="h", extractor_version="1")

        assert cached is not None
        assert cached["payload"] == {"claims": []}


class TestBudget:
    async def test_consumption_stops_at_the_cap(self, conn: Any) -> None:
        budget = BudgetRepository(conn)

        taken = [await budget.consume(provider="vision", hard_cap=3) for _ in range(5)]

        assert taken == [1, 2, 3, None, None]
        usage = await budget.usage(provider="vision")
        assert usage is not None
        assert usage["used"] == 3


class TestFeed:
    async def test_duplicate_run_window_is_a_no_op(self, conn: Any) -> None:
        """The idempotency lock a duplicated scheduler trigger runs into."""
        feeds = FeedRepository(conn)
        feed_id = await feeds.register(url="https://news.example/rss", domain="news.example")
        window = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)

        first = await feeds.start_run(feed_id=feed_id, window_start=window)
        second = await feeds.start_run(feed_id=feed_id, window_start=window)

        assert first is not None
        assert second is None

    async def test_due_feeds_are_returned_in_a_bounded_batch(self, conn: Any) -> None:
        feeds = FeedRepository(conn)
        for index in range(5):
            await feeds.register(url=f"https://n{index}.example/rss", domain=f"n{index}.example")

        assert len(await feeds.due(limit=2)) == 2


class TestReview:
    async def test_human_label_is_recorded_beside_the_machine_verdict(self, conn: Any) -> None:
        case_id, _ = await _case_with_claim(conn)
        review = ReviewRepository(conn)

        item_id = await review.enqueue(
            case_id=case_id, reason="no citable evidence", machine_status="UNVERIFIED"
        )
        await review.record_human_label(
            item_id=item_id, human_label="CONTRADICTED", reviewer="analyst"
        )

        # This item specifically, not an empty table: the queue is shared, and a
        # labelled item leaving it is the behaviour under test either way.
        pending = await review.pending()
        assert item_id not in {row["id"] for row in pending}

    async def test_a_case_reported_twice_is_queued_once(self, conn: Any) -> None:
        # Report pressed twice, or again after reopening the result from History.
        from contextlib import asynccontextmanager

        from app.orchestration.adapters import PoolReviewQueue

        class _Database:
            @asynccontextmanager
            async def transaction(self) -> Any:
                yield conn

        case_id, _ = await _case_with_claim(conn)
        queue = PoolReviewQueue(_Database())  # type: ignore[arg-type]

        first = await queue.report(case_id)
        again = await queue.report(case_id)

        assert again == first
        cursor = await conn.execute("SELECT id FROM review_item WHERE case_id = %s", (case_id,))
        assert [row["id"] for row in await cursor.fetchall()] == [first]

        # Once a reviewer has labelled it, a new report is a new item.
        await ReviewRepository(conn).record_human_label(
            item_id=first, human_label="UNVERIFIED", reviewer="analyst"
        )
        assert await queue.report(case_id) != first


class TestAudit:
    async def test_audit_events_round_trip(self, conn: Any) -> None:
        case_id, _ = await _case_with_claim(conn)
        audit = AuditRepository(conn)

        await audit.record(actor="system", action="verdict.decided", case_id=case_id)
        await audit.record(actor="system", action="evidence.retrieved", case_id=case_id)

        events = await audit.for_case(case_id)

        assert [e["action"] for e in events] == ["verdict.decided", "evidence.retrieved"]
