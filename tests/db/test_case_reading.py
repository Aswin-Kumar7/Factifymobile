"""What was read from an input, kept beside its case (0011), against a real database.

A case read back from the ledger - History after a check's 15 minutes in memory, a
repeat served from the cache - used to lose everything the ledger's rows do not hold:
the panel saying what was read and what could not be, the picture and video checks,
the website card, what was skipped, and the reason an answer was withheld.

Every test runs inside the `conn` fixture's rolled-back transaction, so nothing is
left in the shared database.

    TEST_DATABASE_URL=postgresql://... uv run pytest -m db tests/db/test_case_reading.py
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from app.api.schemas import VerifyResponse
from app.db.repositories import (
    CaseReadingRepository,
    CaseRepository,
    ClaimRepository,
    VerdictRepository,
)
from app.extraction.reading import WITHHELD_SUMMARY
from app.orchestration.ledger import (
    KEPT_FIELDS,
    CaseReader,
    CaseReadingStore,
    reading_payload,
)
from tests.conftest import requires_database

pytestmark = [pytest.mark.db, requires_database]

CONTRACT = Path(__file__).resolve().parents[1] / "fixtures" / "contract"
SAMPLES = sorted(path.stem for path in CONTRACT.glob("*.json"))

ANCHOR: dict[str, Any] = {
    "input_kind": "url",
    "section": "article_body",
    "paragraph_index": 0,
    "char_start": 0,
    "char_end": 40,
    "content_hash": "sha256:fixture",
}
LEDGER_RULES = "2026.10.01.3"
LEDGER_SUMMARY = "No source could be found that settles when the rule starts."


class _Database:
    """The test's rolled-back connection, handed out the way the pool hands one out.

    The pool runs each checkout inside a transaction; here that is a savepoint inside
    the test's own, so a write that fails is undone without spoiling the test.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[Any]:
        async with self._conn.transaction():
            yield self._conn


def _sent(sample: str, case_id: UUID, **update: Any) -> VerifyResponse:
    """A sample answer from the contract fixtures, as if sent for `case_id`."""
    data = json.loads((CONTRACT / f"{sample}.json").read_text("utf-8"))
    return VerifyResponse.model_validate({**data, "case_id": str(case_id), **update})


async def _case(conn: Any) -> UUID:
    return await CaseRepository(conn).create(request_id=f"req-{uuid4()}", input_type="url")


async def _with_unconfirmed_claim(conn: Any, case_id: UUID) -> None:
    """One recorded claim the sources did not settle, as the ledger writes it.

    Unconfirmed because a decisive status must carry citations, and this file is about
    what is kept beside the claims, not the evidence behind them.
    """
    claim_id = await ClaimRepository(conn).create(
        case_id=case_id,
        text="The new UPI rule starts on 1 November.",
        normalized_text="the new upi rule starts on 1 november",
        claim_type="EVENT",
        severity="HIGH",
        importance="MAIN_THESIS",
        anchor=ANCHOR,
    )
    await VerdictRepository(conn).record(
        claim_id=claim_id,
        status="UNVERIFIED",
        action="WAIT_AND_RECHECK",
        reason="No source settles it.",
        rule_id="rule.no_evidence",
        rule_version=LEDGER_RULES,
        strength={"score": 0.0, "band": "none", "version": "1", "explanation": LEDGER_SUMMARY},
    )


class TestRepository:
    async def test_a_reading_round_trips(self, conn: Any) -> None:
        case_id = await _case(conn)
        payload: dict[str, Any] = {
            "input_read": {"kind": "text", "parts": [{"text": "यह संदेश सच नहीं है", "n": 1}]},
            "skipped": [],
            "completeness_note": None,
        }

        await CaseReadingRepository(conn).put(case_id, payload)

        assert await CaseReadingRepository(conn).get(case_id) == payload

    async def test_a_case_with_nothing_kept_reads_none(self, conn: Any) -> None:
        assert await CaseReadingRepository(conn).get(await _case(conn)) is None

    async def test_a_second_write_for_a_case_replaces_the_first(self, conn: Any) -> None:
        case_id = await _case(conn)
        repo = CaseReadingRepository(conn)

        await repo.put(case_id, {"completeness_note": "first"})
        await repo.put(case_id, {"completeness_note": "finished"})

        assert await repo.get(case_id) == {"completeness_note": "finished"}

    async def test_a_reading_needs_its_case(self, conn: Any) -> None:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            async with conn.transaction():
                await CaseReadingRepository(conn).put(uuid4(), {"completeness_note": "orphan"})

    async def test_only_an_object_is_kept(self, conn: Any) -> None:
        case_id = await _case(conn)
        with pytest.raises(psycopg.errors.CheckViolation):
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO case_reading (case_id, payload) VALUES (%s, '[]'::jsonb)",
                    (case_id,),
                )

    async def test_the_reading_goes_with_its_case(self, conn: Any) -> None:
        case_id = await _case(conn)
        await CaseReadingRepository(conn).put(case_id, {"completeness_note": "kept"})

        await conn.execute("DELETE FROM verification_case WHERE id = %s", (case_id,))

        assert await CaseReadingRepository(conn).get(case_id) is None


class TestStore:
    async def test_an_answer_is_kept_as_it_was_sent(self, conn: Any) -> None:
        case_id = await _case(conn)
        sent = _sent("x_photo_post", case_id)
        store = CaseReadingStore(_Database(conn))

        await store.put(case_id, sent)

        kept = await store.get(case_id)
        assert kept == reading_payload(sent)
        assert kept is not None and set(kept) == set(KEPT_FIELDS)

    async def test_a_cached_answer_is_not_kept_again(self, conn: Any) -> None:
        case_id = await _case(conn)
        store = CaseReadingStore(_Database(conn))

        await store.put(case_id, _sent("link_complete", case_id, from_cache=True))

        assert await store.get(case_id) is None

    async def test_a_failed_write_is_swallowed_and_undone(self, conn: Any) -> None:
        # No ledger case to refer to - its own write failed - and the answer stands.
        orphan = uuid4()
        store = CaseReadingStore(_Database(conn))

        await store.put(orphan, _sent("link_complete", orphan))

        # Undone on its own, as the pool's transaction would undo it, and the
        # connection is still usable.
        assert await store.get(orphan) is None


class TestCaseReader:
    @pytest.mark.parametrize("sample", SAMPLES)
    async def test_every_sample_answer_reads_back_as_it_was_sent(
        self, conn: Any, sample: str
    ) -> None:
        case_id = await _case(conn)
        sent = _sent(sample, case_id)
        await CaseReadingStore(_Database(conn)).put(case_id, sent)

        read = await CaseReader(_Database(conn)).get(case_id)

        assert isinstance(read, VerifyResponse)
        for name in KEPT_FIELDS:
            assert getattr(read, name) == getattr(sent, name), name
        assert read.source_risk == sent.source_risk
        # Restored as the contract's own types, so it is sent as it was the first time.
        assert VerifyResponse.model_validate_json(read.model_dump_json()) == read

    async def test_history_shows_what_was_read_beside_the_ledgers_claims(self, conn: Any) -> None:
        case_id = await _case(conn)
        await _with_unconfirmed_claim(conn, case_id)
        sent = _sent("video_upload", case_id)
        await CaseReadingStore(_Database(conn)).put(case_id, sent)

        read = await CaseReader(_Database(conn)).get(case_id)

        assert read.input_read == sent.input_read
        assert read.speech == sent.speech
        assert read.media_report == sent.media_report
        # The claims, the summary and the rule version are what the ledger recorded.
        assert [claim.text for claim in read.claims] == ["The new UPI rule starts on 1 November."]
        assert read.summary == LEDGER_SUMMARY
        assert read.rule_version == LEDGER_RULES

    async def test_a_withheld_answer_reads_back_withheld_and_says_why(self, conn: Any) -> None:
        case_id = await _case(conn)
        sent = _sent("link_withheld", case_id)
        await CaseReadingStore(_Database(conn)).put(case_id, sent)

        read = await CaseReader(_Database(conn)).get(case_id)

        assert read.claims == ()
        assert read.verdict == "UNCONFIRMED"
        assert read.input_read is not None
        assert read.input_read.verdict_withheld is True
        assert read.summary == WITHHELD_SUMMARY["en"]
        assert read.skipped == sent.skipped

    async def test_a_case_kept_before_0011_reads_back_as_before(self, conn: Any) -> None:
        case_id = await _case(conn)
        await _with_unconfirmed_claim(conn, case_id)

        read = await CaseReader(_Database(conn)).get(case_id)

        assert read.input_read is None
        assert read.skipped == ()
        assert read.summary == LEDGER_SUMMARY
        assert len(read.claims) == 1
