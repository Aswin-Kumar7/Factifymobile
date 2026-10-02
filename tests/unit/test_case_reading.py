"""What an answer showed, kept beside its case (0011) and read back with it.

A check's answer is held in memory for 15 minutes; after that a case is read back
from the ledger, whose rows hold the claims, their evidence and their verdicts and
nothing else. History opened later lost the panel saying what was read and what could
not be, the picture and video checks, the website card and what was skipped - and a
withheld answer lost the sentence saying why it was withheld.

Against an in-memory ledger that answers the statements `CaseReader` and
`CaseReadingStore` issue, and keeps Postgres's rule for a failed statement: the
transaction it ran in is aborted until a savepoint around it is rolled back.
`tests/db/test_case_reading.py` runs the same against a real database.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from app.api.schemas import AdvisoryResponse, VerifyResponse
from app.domain.enums import Action, SourceRisk, Verdict
from app.extraction.reading import WITHHELD_SUMMARY
from app.orchestration.ledger import (
    KEPT_FIELDS,
    CaseReader,
    CaseReadingStore,
    reading_payload,
    with_reading,
)

pytestmark = pytest.mark.unit

CONTRACT = Path(__file__).resolve().parents[1] / "fixtures" / "contract"
SAMPLES = sorted(path.stem for path in CONTRACT.glob("*.json"))

LEDGER_RULES = "2026.10.01.3"
LEDGER_SUMMARY = "No source could be found that settles when the rule starts."
OPENED = datetime(2026, 10, 2, 9, 20, 7, tzinfo=UTC)


class _Cursor:
    def __init__(self, rows: list[dict[str, Any]], rowcount: int = 0) -> None:
        self._rows = rows
        self.rowcount = rowcount

    async def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    async def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _Conn:
    """One checked-out connection to the in-memory ledger."""

    def __init__(self, ledger: _Ledger) -> None:
        self._ledger = ledger
        self.aborted = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        # A savepoint: rolled back on a failure inside it, which clears the abort.
        aborted = self.aborted
        try:
            yield
        except Exception:
            self.aborted = aborted
            raise

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _Cursor:
        if self.aborted:
            raise psycopg.errors.InFailedSqlTransaction("current transaction is aborted")
        try:
            return self._ledger.run(" ".join(sql.split()), params)
        except psycopg.Error:
            self.aborted = True
            raise


class _Ledger:
    """The rows `CaseReader` reads and `CaseReadingStore` writes, in memory."""

    def __init__(self, *, has_table: bool = True) -> None:
        self.cases: dict[UUID, dict[str, Any]] = {}
        self.claims: dict[UUID, list[dict[str, Any]]] = {}
        self.verdicts: dict[UUID, dict[str, Any]] = {}
        # As jsonb holds it: written as JSON text, read back decoded.
        self.readings: dict[UUID, str] = {}
        self.writes = 0
        self.has_table = has_table
        self.down = False

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[_Conn]:
        if self.down:
            raise psycopg.OperationalError("connection refused")
        conn = _Conn(self)
        yield conn
        if conn.aborted:
            # The pool commits on the way out; a transaction left aborted cannot be.
            raise psycopg.errors.InFailedSqlTransaction("commit of an aborted transaction")

    def run(self, sql: str, params: tuple[Any, ...]) -> _Cursor:
        if "case_reading" in sql:
            return self._reading(sql, params)
        if "FROM verification_case WHERE id" in sql:
            case = self.cases.get(params[0])
            return _Cursor([case] if case else [])
        if "FROM claim_anchor" in sql:
            return _Cursor([])
        if "FROM claim WHERE case_id" in sql:
            return _Cursor(self.claims.get(params[0], []))
        if "FROM verdict WHERE claim_id" in sql:
            verdict = self.verdicts.get(params[0])
            return _Cursor([verdict] if verdict else [])
        if "FROM evidence e" in sql:
            return _Cursor([])
        raise AssertionError(f"unexpected statement: {sql}")

    def _reading(self, sql: str, params: tuple[Any, ...]) -> _Cursor:
        if not self.has_table:
            raise psycopg.errors.UndefinedTable('relation "case_reading" does not exist')
        if sql.startswith("INSERT INTO case_reading"):
            case_id, payload = params
            if case_id not in self.cases:
                raise psycopg.errors.ForeignKeyViolation(
                    'insert on table "case_reading" violates foreign key constraint'
                )
            self.readings[case_id] = payload
            self.writes += 1
            return _Cursor([], rowcount=1)
        kept = self.readings.get(params[0])
        return _Cursor([] if kept is None else [{"payload": json.loads(kept)}])

    def case(self, *, language: str | None = None) -> UUID:
        case_id = uuid4()
        self.cases[case_id] = {"id": case_id, "created_at": OPENED, "language": language}
        return case_id

    def unconfirmed_claim(self, case_id: UUID) -> None:
        """One recorded claim the sources did not settle, as the ledger writes it."""
        claim_id = uuid4()
        self.claims.setdefault(case_id, []).append(
            {
                "id": claim_id,
                "text": "The new UPI rule starts on 1 November.",
                "language": "en",
                "claim_type": "EVENT",
                "severity": "HIGH",
                "importance": "MAIN_THESIS",
            }
        )
        self.verdicts[claim_id] = {
            "status": "UNVERIFIED",
            "action": "WAIT_AND_RECHECK",
            "reason": "No source settles it.",
            "rule_id": "rule.no_evidence",
            "rule_version": LEDGER_RULES,
            "strength_json": {
                "score": 0.0,
                "band": "none",
                "version": "1",
                "explanation": LEDGER_SUMMARY,
            },
        }


def _sent(sample: str, case_id: UUID, **update: Any) -> VerifyResponse:
    """A sample answer from the contract fixtures, as if sent for `case_id`."""
    data = json.loads((CONTRACT / f"{sample}.json").read_text("utf-8"))
    return VerifyResponse.model_validate({**data, "case_id": str(case_id), **update})


def _degraded(caplog: pytest.LogCaptureFixture, message: str) -> bool:
    return any(record.getMessage() == message for record in caplog.records)


class TestPayload:
    @pytest.mark.parametrize("sample", SAMPLES)
    def test_only_what_no_ledger_row_holds_is_kept(self, sample: str) -> None:
        payload = reading_payload(_sent(sample, uuid4()))

        assert set(payload) == set(KEPT_FIELDS)
        # The claims, the verdict and its sentence are the ledger's; the receipt and
        # the app's request id belong to the one response.
        assert not {"claims", "verdict", "summary", "receipt", "request_id"} & set(payload)
        # Stored as the API's own JSON.
        assert json.loads(json.dumps(payload)) == payload

    def test_the_fields_are_those_the_rows_cannot_hold(self) -> None:
        assert KEPT_FIELDS == (
            "input_read",
            "image_reading",
            "speech",
            "media_report",
            "media_reports",
            "source_profile",
            "skipped",
            "completeness_note",
            "advisories",
        )


class TestStore:
    @pytest.mark.parametrize("sample", SAMPLES)
    async def test_every_sample_answer_reads_back_as_it_was_sent(self, sample: str) -> None:
        ledger = _Ledger()
        case_id = ledger.case()
        sent = _sent(sample, case_id)

        await CaseReadingStore(ledger).put(case_id, sent)
        read = await CaseReader(ledger).get(case_id)

        assert isinstance(read, VerifyResponse)
        for name in KEPT_FIELDS:
            assert getattr(read, name) == getattr(sent, name), name
        # The link's risk level is its website card's, said again from it.
        assert read.source_risk == sent.source_risk
        # Restored as the contract's own types, so it is sent as it was the first time.
        assert VerifyResponse.model_validate_json(read.model_dump_json()) == read
        assert reading_payload(read) == reading_payload(sent)

    async def test_the_payload_reads_back_as_it_was_put(self) -> None:
        ledger = _Ledger()
        case_id = ledger.case()
        sent = _sent("x_photo_post", case_id)
        store = CaseReadingStore(ledger)

        await store.put(case_id, sent)

        assert await store.get(case_id) == reading_payload(sent)

    async def test_a_second_answer_for_a_case_replaces_the_first(self) -> None:
        ledger = _Ledger()
        case_id = ledger.case()
        store = CaseReadingStore(ledger)

        await store.put(case_id, _sent("link_withheld", case_id))
        await store.put(case_id, _sent("link_complete", case_id))

        kept = await store.get(case_id)
        assert kept is not None
        assert kept["input_read"]["verdict_withheld"] is False
        assert kept["skipped"] == []

    async def test_a_cached_answer_is_not_kept_again(self) -> None:
        # It belongs to the case it was first computed for, whose reading was kept
        # then; a thin repeat would overwrite it with less.
        ledger = _Ledger()
        case_id = ledger.case()

        await CaseReadingStore(ledger).put(
            case_id, _sent("link_complete", case_id, from_cache=True)
        )

        assert ledger.writes == 0

    async def test_an_answer_with_nothing_to_keep_writes_nothing(self) -> None:
        ledger = _Ledger()
        case_id = ledger.case()
        bare = VerifyResponse(
            case_id=str(case_id),
            action=Action.WAIT_AND_RECHECK,
            action_reason="Checked.",
            rule_version=LEDGER_RULES,
            retrieved_at=OPENED,
        )

        await CaseReadingStore(ledger).put(case_id, bare)

        assert ledger.writes == 0
        assert await CaseReadingStore(ledger).get(case_id) is None

    async def test_a_failed_write_is_logged_not_raised(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # No ledger case to refer to - its own write failed - and the answer stands.
        ledger = _Ledger()
        orphan = uuid4()

        with caplog.at_level(logging.INFO, logger="factify.ledger"):
            await CaseReadingStore(ledger).put(orphan, _sent("link_complete", orphan))

        assert ledger.readings == {}
        assert _degraded(caplog, "case reading not kept; the case will read back without it")

    async def test_a_database_that_is_down_costs_the_answer_nothing(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        ledger = _Ledger()
        case_id = ledger.case()
        ledger.down = True
        store = CaseReadingStore(ledger)

        with caplog.at_level(logging.INFO, logger="factify.ledger"):
            await store.put(case_id, _sent("video_upload", case_id))
            assert await store.get(case_id) is None

        assert _degraded(caplog, "case reading not kept; the case will read back without it")
        assert _degraded(caplog, "kept reading could not be read")

    async def test_a_database_0011_has_not_reached_costs_the_answer_nothing(self) -> None:
        ledger = _Ledger(has_table=False)
        case_id = ledger.case()
        store = CaseReadingStore(ledger)

        await store.put(case_id, _sent("video_upload", case_id))

        assert await store.get(case_id) is None


class TestCaseReader:
    async def test_history_shows_what_was_read_beside_the_ledgers_claims(self) -> None:
        ledger = _Ledger()
        case_id = ledger.case()
        ledger.unconfirmed_claim(case_id)
        advisory = AdvisoryResponse(
            id="adv_1",
            provider="image_detector",
            signal="ADVISORY_SUSPICION",
            note="The picture shows signs of being made by AI.",
            score=0.81,
        )
        sent = _sent("x_photo_post", case_id, advisories=[advisory.model_dump(mode="json")])
        await CaseReadingStore(ledger).put(case_id, sent)

        read = await CaseReader(ledger).get(case_id)

        assert read.input_read == sent.input_read
        assert read.input_read.platform == "x"
        assert read.image_reading == sent.image_reading
        assert read.media_report == sent.media_report
        assert read.media_reports == sent.media_reports
        assert read.advisories == (advisory,)
        # The claims, the summary and the rule version are what the ledger recorded,
        # not the copy of what was said about them.
        assert [claim.text for claim in read.claims] == ["The new UPI rule starts on 1 November."]
        assert read.summary == LEDGER_SUMMARY
        assert read.rule_version == LEDGER_RULES
        assert read.action == Action.WAIT_AND_RECHECK
        assert read.verdict == Verdict.UNCONFIRMED

    async def test_a_withheld_answer_reopened_says_why(self) -> None:
        ledger = _Ledger()
        case_id = ledger.case()
        sent = _sent("link_withheld", case_id)
        await CaseReadingStore(ledger).put(case_id, sent)

        read = await CaseReader(ledger).get(case_id)

        assert read.claims == ()
        assert read.verdict == Verdict.UNCONFIRMED
        assert read.input_read is not None
        assert read.input_read.verdict_withheld is True
        assert [gap.code for gap in read.input_read.gaps] == ["headline_only"]
        # The fixed sentence the withheld answer gave, which no claim row holds.
        assert read.summary == WITHHELD_SUMMARY["en"] == sent.summary
        assert read.skipped == sent.skipped
        assert read.source_profile == sent.source_profile
        assert read.source_risk == SourceRisk.MEDIUM

    @pytest.mark.parametrize(
        ("language", "said"),
        [
            ("hi", WITHHELD_SUMMARY["hi"]),
            # A language the sentence is not written in yet, and a case with none.
            ("ta", WITHHELD_SUMMARY["en"]),
            (None, WITHHELD_SUMMARY["en"]),
        ],
    )
    async def test_a_withheld_answer_says_why_in_the_cases_language(
        self, language: str | None, said: str
    ) -> None:
        ledger = _Ledger()
        case_id = ledger.case(language=language)
        await CaseReadingStore(ledger).put(case_id, _sent("link_withheld", case_id))

        read = await CaseReader(ledger).get(case_id)

        assert read.summary == said

    async def test_an_answer_that_was_not_withheld_gains_no_sentence(self) -> None:
        ledger = _Ledger()
        case_id = ledger.case()
        await CaseReadingStore(ledger).put(case_id, _sent("video_upload", case_id))

        read = await CaseReader(ledger).get(case_id)

        assert read.summary is None

    async def test_a_case_kept_before_0011_reads_back_as_before(self) -> None:
        ledger = _Ledger()
        case_id = ledger.case()
        ledger.unconfirmed_claim(case_id)

        read = await CaseReader(ledger).get(case_id)

        assert read.input_read is None
        assert read.skipped == ()
        assert read.source_risk == SourceRisk.UNKNOWN
        assert read.summary == LEDGER_SUMMARY
        assert len(read.claims) == 1

    async def test_a_database_0011_has_not_reached_still_serves_the_case(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # The failed read is under its own savepoint: the ledger's transaction is not
        # left aborted, and the case is served as one stored before 0011.
        ledger = _Ledger(has_table=False)
        case_id = ledger.case()
        ledger.unconfirmed_claim(case_id)

        with caplog.at_level(logging.INFO, logger="factify.ledger"):
            read = await CaseReader(ledger).get(case_id)

        assert len(read.claims) == 1
        assert read.input_read is None
        assert _degraded(caplog, "kept reading could not be read; case served without it")

    async def test_a_kept_reading_that_no_longer_reads_is_left_out_whole(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # A reading calling itself complete while naming a gap is refused, and with it
        # the rest of the copy: a half-restored answer is one that was never sent.
        ledger = _Ledger()
        case_id = ledger.case()
        ledger.unconfirmed_claim(case_id)
        kept = reading_payload(_sent("link_withheld", case_id))
        kept["input_read"]["complete"] = True
        ledger.readings[case_id] = json.dumps(kept)

        with caplog.at_level(logging.INFO, logger="factify.ledger"):
            read = await CaseReader(ledger).get(case_id)

        assert read.input_read is None
        assert read.skipped == ()
        assert read.source_profile is None
        assert read.summary == LEDGER_SUMMARY
        assert len(read.claims) == 1
        assert _degraded(caplog, "kept reading could not be read; case served without it")

    async def test_nothing_the_ledger_decides_is_taken_from_the_copy(self) -> None:
        ledger = _Ledger()
        case_id = ledger.case()
        ledger.unconfirmed_claim(case_id)
        kept = {
            **reading_payload(_sent("video_upload", case_id)),
            "verdict": "TRUE",
            "summary": "Written by someone else.",
            "claims": [],
            "rule_version": "forged",
        }
        ledger.readings[case_id] = json.dumps(kept)

        read = await CaseReader(ledger).get(case_id)

        assert read.verdict == Verdict.UNCONFIRMED
        assert read.summary == LEDGER_SUMMARY
        assert read.rule_version == LEDGER_RULES
        assert len(read.claims) == 1
        assert read.speech is not None

    async def test_an_unknown_case_is_still_none(self) -> None:
        assert await CaseReader(_Ledger()).get(uuid4()) is None


class TestWithReading:
    async def test_a_repeat_served_from_the_cache_can_carry_the_first_reading(self) -> None:
        # For an answer not read through `CaseReader`: the thin result of a cache hit.
        ledger = _Ledger()
        case_id = ledger.case()
        sent = _sent("instagram_reel_partial", case_id)
        store = CaseReadingStore(ledger)
        await store.put(case_id, sent)
        thin = VerifyResponse(
            case_id=str(case_id),
            action=Action.WAIT_AND_RECHECK,
            action_reason="Served from the cache.",
            rule_version=LEDGER_RULES,
            retrieved_at=OPENED,
            from_cache=True,
        )

        served = with_reading(thin, await store.get(case_id))

        assert served.input_read == sent.input_read
        assert served.speech == sent.speech
        assert served.skipped == sent.skipped
        assert served.from_cache is True
        assert served.action_reason == "Served from the cache."

    def test_nothing_kept_leaves_the_answer_as_it_is(self) -> None:
        response = _sent("link_complete", uuid4())

        assert with_reading(response, None) is response
        assert with_reading(response, {}) is response
