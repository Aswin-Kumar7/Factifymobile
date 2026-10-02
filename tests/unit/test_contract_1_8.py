"""Contract 1.8: what was read from the input, and answers held back when it was not.

Asserted here:

  - the new shapes, their defaults, and the rules they refuse to break;
  - that every 1.7 field is unchanged, so an app built before 1.8 keeps working;
  - the sample responses in tests/fixtures/contract/, which the website and the app
    are built against, are exactly what the models produce - and their offsets are
    the offsets `Reading.document()` writes;
  - the new case rule: checked from part of the input, an answer is never TRUE;
  - the pipeline's hooks: what could not be read reaches the answer and keeps it out
    of the cache;
  - the configuration for reading social posts and videos, off until configured.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.schemas import (
    CONTRACT_VERSION,
    AdvisoryResponse,
    ClaimResponse,
    ImageReadingResponse,
    InputReadResponse,
    MediaProvenanceResponse,
    MediaReportResponse,
    ReadGapResponse,
    ReadPartResponse,
    ReceiptSummaryResponse,
    RecurrenceResponse,
    SkippedCheckResponse,
    SourceProfileResponse,
    SpeechResponse,
    VerifyRequest,
    VerifyResponse,
)
from app.config import Settings, SocialSettings
from app.domain.enums import (
    Action,
    ClaimStatus,
    Importance,
    Severity,
    SourceRisk,
    Verdict,
)
from app.extraction.reading import (
    CONTEXT_ONLY,
    WITHHELD_SUMMARY,
    GapCode,
    PartKind,
    Reading,
    ReadPart,
)
from app.intake.normalizer import normalise_text
from app.orchestration import pipeline
from app.orchestration.pipeline import (
    BACKGROUND_CEILING_SECONDS,
    BACKGROUND_MIN_READING_SECONDS,
    BACKGROUND_SECONDS,
    Orchestrator,
    SkippedCheck,
)
from app.verdict.engine import (
    NARROWER_RULE,
    PARTLY_READ_REASON,
    PARTLY_READ_RULE,
    RULE_VERSION,
    Decision,
    roll_up,
)
from tests.unit.factories import claim

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "contract"
SAMPLES = (
    "link_complete",
    "link_withheld",
    "x_photo_post",
    "instagram_reel_partial",
    "youtube_video",
    "video_upload",
)


def _sample(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return loaded


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


# --------------------------------------------------------------------- compatibility

# The 1.7 fields of the three models 1.8 adds to, with their types, written out so a
# change to any of them cannot pass unnoticed.
_VERIFY_RESPONSE_1_7: dict[str, Any] = {
    "case_id": str,
    "contract_version": str,
    "verdict": Verdict,
    "confidence": int | None,
    "summary": str | None,
    "action": Action,
    "action_reason": str,
    "rule_version": str,
    "claims": tuple[ClaimResponse, ...],
    "advisories": tuple[AdvisoryResponse, ...],
    "source_risk": SourceRisk,
    "source_profile": SourceProfileResponse | None,
    "media_provenance": MediaProvenanceResponse | None,
    "recurrence": RecurrenceResponse | None,
    "skipped": tuple[SkippedCheckResponse, ...],
    "completeness_note": str | None,
    "image_reading": ImageReadingResponse | None,
    "media_report": MediaReportResponse | None,
    "speech": SpeechResponse | None,
    "receipt_url": str | None,
    "receipt": ReceiptSummaryResponse | None,
    "request_id": str | None,
    "retrieved_at": datetime,
    "from_cache": bool,
    "elapsed_ms": int,
}
_VERIFY_REQUEST_1_7: dict[str, Any] = {
    "url": str | None,
    "text": str | None,
    "language": str | None,
    "mode": str,
    "consent_to_process_media": bool,
    "recheck": bool,
}
_SKIPPED_1_7: dict[str, Any] = {"check": str, "reason": str}


class TestAdditiveOnly:
    def test_the_version_is_1_8(self) -> None:
        assert CONTRACT_VERSION == "1.8"
        assert VerifyResponse.model_fields["contract_version"].default == "1.8"

    @pytest.mark.parametrize(
        ("model", "old", "new"),
        [
            (VerifyResponse, _VERIFY_RESPONSE_1_7, {"input_read", "media_reports"}),
            (VerifyRequest, _VERIFY_REQUEST_1_7, {"accept_partial"}),
            (SkippedCheckResponse, _SKIPPED_1_7, {"kind"}),
        ],
    )
    def test_every_1_7_field_is_kept_as_it_was_and_the_new_ones_are_optional(
        self, model: Any, old: dict[str, Any], new: set[str]
    ) -> None:
        fields = model.model_fields
        for name, annotation in old.items():
            assert fields[name].annotation == annotation, name
        assert set(fields) == set(old) | new
        assert not any(fields[name].is_required() for name in new)

    def test_the_new_fields_default_to_what_a_1_7_answer_meant(self) -> None:
        answer = VerifyResponse(
            case_id="c",
            action=Action.SEND_TO_REVIEW,
            action_reason="r",
            rule_version=RULE_VERSION,
            retrieved_at=datetime(2026, 10, 2),
        )

        assert answer.input_read is None
        assert answer.media_reports == ()
        assert SkippedCheckResponse(check="x", reason="y").kind == "other"
        assert VerifyRequest(text="hello").accept_partial is False

    def test_a_1_7_answer_still_reads_as_1_8(self) -> None:
        """A stored or cached 1.7 answer, with none of the new fields, still validates."""
        payload = _sample("link_complete")
        for key in ("input_read", "media_reports"):
            payload.pop(key)
        for item in payload["skipped"]:
            item.pop("kind")

        answer = VerifyResponse.model_validate(payload)

        assert answer.input_read is None
        assert answer.media_reports == ()

    def test_a_1_7_app_finds_every_field_it_reads(self) -> None:
        for name in SAMPLES:
            assert set(_VERIFY_RESPONSE_1_7) <= set(_sample(name))

    def test_check_what_was_read_is_a_request_field(self) -> None:
        assert VerifyRequest(url="https://x.com/i/status/1", accept_partial=True).accept_partial
        with pytest.raises(ValidationError):
            VerifyRequest(text="hello", accept_partial_typo=True)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------- shapes


def _part(**more: Any) -> ReadPartResponse:
    base: dict[str, Any] = {"kind": "post_text", "text": "t", "checked": True, "route": "x"}
    return ReadPartResponse(**(base | more))


def _gap(blocking: bool = True) -> ReadGapResponse:
    return ReadGapResponse(part="post_text", code="text_truncated", detail="d", blocking=blocking)


class TestTheShapes:
    def test_a_part_needs_what_it_is_its_words_whether_checked_and_how_it_was_read(self) -> None:
        required = {
            name for name, info in ReadPartResponse.model_fields.items() if info.is_required()
        }
        assert required == {"kind", "text", "checked", "route"}
        part = _part()
        assert part.complete is True
        assert (part.media_url, part.char_start, part.char_end, part.seconds_read) == (
            None,
            None,
            None,
            None,
        )

    def test_a_gap_says_everything_or_nothing(self) -> None:
        required = {
            name for name, info in ReadGapResponse.model_fields.items() if info.is_required()
        }
        assert required == {"part", "code", "detail", "blocking"}

    def test_an_input_read_defaults_to_complete_and_checked(self) -> None:
        read = InputReadResponse(kind="text")
        assert (read.complete, read.verdict_withheld, read.checked_partially) == (
            True,
            False,
            False,
        )
        assert (read.parts, read.gaps, read.limits) == ((), (), ())

    def test_complete_is_true_exactly_when_no_gap_was_recorded(self) -> None:
        InputReadResponse(kind="link", complete=False, gaps=(_gap(),))
        with pytest.raises(ValidationError, match="complete"):
            InputReadResponse(kind="link", complete=True, gaps=(_gap(),))
        with pytest.raises(ValidationError, match="complete"):
            InputReadResponse(kind="link", complete=False)

    def test_an_answer_is_not_both_withheld_and_checked_from_part(self) -> None:
        with pytest.raises(ValidationError, match="both withheld"):
            InputReadResponse(
                kind="link",
                complete=False,
                gaps=(_gap(),),
                verdict_withheld=True,
                checked_partially=True,
            )

    def test_checked_partially_needs_a_blocking_gap_it_checked_past(self) -> None:
        InputReadResponse(kind="link", complete=False, gaps=(_gap(),), checked_partially=True)
        with pytest.raises(ValidationError, match="blocking gap"):
            InputReadResponse(
                kind="link", complete=False, gaps=(_gap(blocking=False),), checked_partially=True
            )

    def test_the_shapes_are_frozen(self) -> None:
        part = _part()
        with pytest.raises(ValidationError):
            part.text = "changed"  # type: ignore[misc]

    def test_the_contract_names_every_part_kind_and_gap_code(self) -> None:
        """The clients word each code; the contract must list every one they can meet."""
        changelog = (
            Path(__file__).resolve().parents[2] / "docs" / "contract-changelog.md"
        ).read_text(encoding="utf-8")
        for code in GapCode:
            assert f"`{code.value}`" in changelog, code
            assert code.value in (ReadGapResponse.__doc__ or ""), code
        for kind in PartKind:
            assert f"`{kind.value}`" in changelog, kind


# -------------------------------------------------------------------------- samples


def _rebuilt(read: dict[str, Any]) -> Reading:
    """The response's parts, as the reading they were sent from."""
    return Reading(
        kind=read["kind"],
        parts=tuple(
            ReadPart(kind=PartKind(p["kind"]), text=p["text"], route=p["route"], label=p["label"])
            for p in read["parts"]
        ),
    )


class TestTheSamples:
    """The website and the app are built against these files; they must not drift."""

    def test_every_sample_is_there(self) -> None:
        assert {path.stem for path in FIXTURES.glob("*.json")} == set(SAMPLES)

    @pytest.mark.parametrize("name", SAMPLES)
    def test_a_sample_is_exactly_what_the_model_writes(self, name: str) -> None:
        payload = _sample(name)

        answer = VerifyResponse.model_validate(payload)

        assert answer.model_dump(mode="json") == payload
        assert answer.contract_version == "1.8"
        assert answer.rule_version == RULE_VERSION
        assert answer.input_read is not None

    @pytest.mark.parametrize("name", SAMPLES)
    def test_a_part_s_offsets_are_where_the_document_puts_it(self, name: str) -> None:
        read = _sample(name)["input_read"]
        composed = _rebuilt(read).document()
        spans = {index: (start, end) for index, start, end in composed.spans}

        for index, part in enumerate(read["parts"]):
            assert part["checked"] is (PartKind(part["kind"]) not in CONTEXT_ONLY)
            if part["char_start"] is None:
                # Only a part that is not in the document, or an answer never checked.
                assert not part["checked"] or read["verdict_withheld"]
                continue
            assert spans[index] == (part["char_start"], part["char_end"])
            assert composed.text[part["char_start"] : part["char_end"]] == part["text"]

    @pytest.mark.parametrize("name", SAMPLES)
    def test_every_claim_is_anchored_in_a_checked_part(self, name: str) -> None:
        payload = _sample(name)
        composed = _rebuilt(payload["input_read"]).document()
        parts = payload["input_read"]["parts"]

        for item in payload["claims"]:
            anchor = item["input_anchor"]
            index = composed.part_at(anchor["char_start"])
            assert index is not None, item["id"]
            assert parts[index]["checked"]
            assert anchor["char_end"] <= parts[index]["char_end"]

    @pytest.mark.parametrize("name", SAMPLES)
    def test_the_reading_and_the_skipped_checks_agree(self, name: str) -> None:
        payload = _sample(name)
        read = payload["input_read"]
        reading_skips = [s for s in payload["skipped"] if s["kind"] == "reading"]

        assert read["complete"] is (not read["gaps"])
        # A gap that holds the answer back is also said where an older app looks.
        if any(gap["blocking"] for gap in read["gaps"]):
            assert reading_skips
            assert payload["completeness_note"]
        assert {gap["code"] for gap in read["gaps"]} <= {code.value for code in GapCode}

    def test_the_withheld_shape(self) -> None:
        payload = _sample("link_withheld")
        read = payload["input_read"]

        assert read["verdict_withheld"] is True
        assert read["checked_partially"] is False
        assert read["complete"] is False
        assert any(gap["blocking"] for gap in read["gaps"])
        assert payload["verdict"] == "UNCONFIRMED"
        assert payload["confidence"] is None
        assert payload["claims"] == []
        assert payload["summary"] == WITHHELD_SUMMARY["en"]
        # An older app, which knows nothing of `input_read`, must not read this as
        # "nothing to fact-check": the skipped list says the input was not checked.
        assert {"check": "claim_extraction", "kind": "reading"}.items() <= next(
            s for s in payload["skipped"] if s["check"] == "claim_extraction"
        ).items()

    def test_the_partly_checked_shape(self) -> None:
        payload = _sample("instagram_reel_partial")
        read = payload["input_read"]

        assert read["checked_partially"] is True
        assert read["verdict_withheld"] is False
        assert payload["verdict"] == "UNCONFIRMED"
        assert payload["action"] == "WAIT_AND_RECHECK"
        assert payload["action_reason"] == PARTLY_READ_REASON
        assert all(item["status"] == "SUPPORTED" for item in payload["claims"])
        transcript = next(p for p in read["parts"] if p["kind"] == "transcript")
        assert transcript["complete"] is False
        assert transcript["seconds_read"] < transcript["seconds_total"]

    def test_a_post_s_other_pictures_have_their_own_reports(self) -> None:
        payload = _sample("x_photo_post")
        pictures = [p for p in payload["input_read"]["parts"] if p["kind"] == "picture_text"]

        assert payload["media_report"] is not None
        assert len(payload["media_reports"]) == len(pictures) - 1
        assert all(p["media_url"].startswith("/v1/media/thumbnails/") for p in pictures)

    def test_a_youtube_video_says_what_its_reading_could_not_check(self) -> None:
        payload = _sample("youtube_video")

        assert payload["input_read"]["platform"] == "youtube"
        assert payload["input_read"]["limits"]
        assert payload["media_report"] is None
        assert payload["input_read"]["complete"] is True


# ------------------------------------------------------------------- the case rule


def _supported() -> Decision:
    return Decision(
        status=ClaimStatus.SUPPORTED,
        rule_id="rule.independent_corroboration",
        reason="supported",
        supporting_evidence_ids=("ev_1",),
        confidence=90,
    )


def _contradicted() -> Decision:
    return Decision(
        status=ClaimStatus.CONTRADICTED,
        rule_id="rule.factcheck_contradiction",
        reason="contradicted",
        supporting_evidence_ids=("ev_2",),
        confidence=92,
    )


class TestPartlyRead:
    def test_what_was_read_supported_is_unconfirmed_not_true(self) -> None:
        main = claim()

        whole = roll_up([(main, _supported())])
        part = roll_up([(main, _supported())], partial_input=True)

        assert whole.verdict is Verdict.TRUE
        assert part.action is Action.WAIT_AND_RECHECK
        assert part.verdict is Verdict.UNCONFIRMED
        assert part.rule_id == PARTLY_READ_RULE == "rollup.partly_read"
        assert part.reason == PARTLY_READ_REASON
        assert part.confidence is None
        assert part.rule_version == RULE_VERSION

    def test_a_contradiction_in_what_was_read_still_stands(self) -> None:
        main = claim()

        case = roll_up([(main, _contradicted())], partial_input=True)

        assert case.action is Action.DO_NOT_SHARE
        assert case.verdict is Verdict.FALSE
        assert case.confidence == 92

    def test_a_partial_truth_in_what_was_read_still_stands(self) -> None:
        main = claim(importance=Importance.HEADLINE)
        detail = claim(claim_id="cl_2", importance=Importance.MAIN_THESIS)

        case = roll_up([(main, _contradicted()), (detail, _supported())], partial_input=True)

        assert case.verdict is Verdict.PARTLY_TRUE

    def test_a_smaller_version_confirmed_is_still_partly_true(self) -> None:
        main = claim(severity=Severity.HIGH)
        narrower = Decision(
            status=ClaimStatus.MISLEADING_CONTEXT,
            rule_id=NARROWER_RULE,
            reason="narrower",
            supporting_evidence_ids=("ev_3",),
            confidence=80,
        )

        assert roll_up([(main, narrower)], partial_input=True).verdict is Verdict.PARTLY_TRUE

    def test_an_undecided_answer_is_left_as_it_was(self) -> None:
        main = claim()
        undecided = Decision(
            status=ClaimStatus.UNVERIFIED, rule_id="rule.no_evidence", reason="nothing found"
        )

        whole = roll_up([(main, undecided)])
        part = roll_up([(main, undecided)], partial_input=True)

        assert part == whole

    def test_the_rules_changed_so_the_version_did(self) -> None:
        assert RULE_VERSION >= "2026.10.02.1"


# ---------------------------------------------------------------- pipeline hooks


class _RecordingCache:
    def __init__(self) -> None:
        self.written: list[dict[str, Any]] = []

    async def get_verdict(self, parts: Any) -> None:
        return None

    async def put_verdict(self, parts: Any, payload: dict[str, Any], **_: Any) -> None:
        self.written.append(payload)


class _NoGovernor:
    async def try_acquire(self, provider: str) -> Any:
        from app.governor.governor import Skip, SkipReason

        return Skip(provider=provider, reason=SkipReason.DISABLED)


def _orchestrator(cache: _RecordingCache) -> Orchestrator:
    return Orchestrator(
        cache=cache,
        governor=_NoGovernor(),
        resolvers=[],
        extractor_version="test",
    )


_UNREAD = SkippedCheck(
    check="speech", reason="the speech in the video could not be read", kind="reading"
)


class TestThePipelineHooks:
    def test_a_skipped_check_is_other_unless_said(self) -> None:
        assert SkippedCheck(check="x", reason="y").kind == "other"
        assert (
            _UNREAD.describe()
            == "speech was not checked: the speech in the video could not be read"
        )

    def test_the_background_budget_floor_and_ceiling(self) -> None:
        assert BACKGROUND_MIN_READING_SECONDS == 150.0
        assert BACKGROUND_CEILING_SECONDS == 420.0
        assert BACKGROUND_MIN_READING_SECONDS < BACKGROUND_SECONDS < BACKGROUND_CEILING_SECONDS

    @pytest.mark.anyio
    async def test_a_whole_reading_is_cached_as_before(self) -> None:
        cache = _RecordingCache()

        result = await _orchestrator(cache).verify(
            normalise_text("The bank will be shut on Monday."), case_id=uuid4(), claims=[claim()]
        )

        assert result.skipped == []
        assert len(cache.written) == 1

    @pytest.mark.anyio
    async def test_what_could_not_be_read_is_reported_and_never_cached(self) -> None:
        cache = _RecordingCache()

        result = await _orchestrator(cache).verify(
            normalise_text("The bank will be shut on Monday."),
            case_id=uuid4(),
            claims=[claim()],
            noted=[_UNREAD],
        )

        assert result.skipped[0] == _UNREAD
        assert "speech was not checked" in (result.completeness_note() or "")
        assert cache.written == []

    @pytest.mark.anyio
    async def test_checking_part_of_the_input_reaches_the_case_rule(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[bool] = []
        real = roll_up

        def spy(*args: Any, **kwargs: Any) -> Any:
            seen.append(kwargs.get("partial_input", False))
            return real(*args, **kwargs)

        monkeypatch.setattr(pipeline, "roll_up", spy)
        cache = _RecordingCache()

        await _orchestrator(cache).verify(
            normalise_text("The bank will be shut on Monday."),
            case_id=uuid4(),
            claims=[claim()],
            noted=[_UNREAD],
            partial_input=True,
        )

        assert seen == [True]
        assert cache.written == []

    @pytest.mark.anyio
    async def test_partial_input_with_no_gap_named_still_says_so(self) -> None:
        """Checked from part of the input, the answer always says it, and is not kept."""
        cache = _RecordingCache()

        result = await _orchestrator(cache).verify(
            normalise_text("The bank will be shut on Monday."),
            case_id=uuid4(),
            claims=[claim()],
            partial_input=True,
        )

        assert [item.kind for item in result.skipped] == ["reading"]
        assert cache.written == []

    @pytest.mark.anyio
    async def test_the_served_orchestrator_passes_both_through(self) -> None:
        from app.orchestration.composition import ServedOrchestrator

        received: dict[str, Any] = {}

        class _Inner:
            async def verify(self, intake: Any, **kwargs: Any) -> Any:
                received.update(kwargs)
                result = pipeline.VerificationResult(
                    case_id=kwargs["case_id"],
                    content_hash="sha256:x",
                    action=Action.SEND_TO_REVIEW,
                    case_decision=roll_up([]),
                    from_cache=True,  # nothing to persist
                )
                return result

        served = ServedOrchestrator(database=None, orchestrator=_Inner())  # type: ignore[arg-type]
        await served.verify(
            normalise_text("x y z"),
            case_id=uuid4(),
            claims=[claim()],
            noted=[_UNREAD],
            partial_input=True,
        )

        assert received["noted"] == [_UNREAD]
        assert received["partial_input"] is True


# ------------------------------------------------------------------ configuration


class TestConfiguration:
    def test_reading_posts_is_on_and_needs_no_credential(self) -> None:
        social = _settings().social

        assert social == SocialSettings()
        assert social.enabled is True
        assert social.platforms == ("x", "instagram", "youtube")
        assert (social.max_pictures, social.max_video_seconds, social.youtube_max_seconds) == (
            4,
            600,
            1800,
        )
        assert (social.per_minute_cap, social.timeout_seconds) == (30, 15.0)
        assert social.instagram_reels_via_ytdlp is True

    def test_an_unknown_platform_refuses_to_boot(self) -> None:
        with pytest.raises(ValidationError, match="myspace"):
            _settings(social={"platforms": ["x", "myspace"]})
        assert _settings(social={"platforms": ["x", "facebook"]}).social.platforms == (
            "x",
            "facebook",
        )

    def test_the_video_reader_is_off_until_configured(self) -> None:
        settings = _settings()

        assert settings.providers["video_reader"] is settings.video_reader
        assert not settings.video_reader.usable
        assert settings.models.video_reading == ""

    def test_the_video_reader_must_name_its_model(self) -> None:
        reader = {"enabled": True, "api_key": "k", "endpoint": "https://g.example/{model}"}

        with pytest.raises(ValidationError, match=r"models\.video_reading is unset"):
            _settings(video_reader=reader)
        configured = _settings(video_reader=reader, models={"video_reading": "gemini-x"})
        assert configured.video_reader.usable

    def test_the_video_reader_must_speak_gemini(self) -> None:
        reader = {
            "enabled": True,
            "api_key": "k",
            "endpoint": "https://openai.example/v1/chat/completions",
            "api_format": "openai",
        }

        with pytest.raises(ValidationError, match="gemini format"):
            _settings(video_reader=reader, models={"video_reading": "some-model"})

    def test_an_enabled_video_reader_with_no_endpoint_refuses_to_boot(self) -> None:
        with pytest.raises(ValidationError, match="video_reader"):
            _settings(
                video_reader={"enabled": True, "api_key": "k"},
                models={"video_reading": "gemini-x"},
            )

    def test_read_from_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FACTIFY_SOCIAL__PLATFORMS", '["x","instagram"]')
        monkeypatch.setenv("FACTIFY_SOCIAL__MAX_PICTURES", "2")
        monkeypatch.setenv("FACTIFY_VIDEO_READER__ENABLED", "true")
        monkeypatch.setenv("FACTIFY_VIDEO_READER__API_KEY", "from-env")
        monkeypatch.setenv(
            "FACTIFY_VIDEO_READER__ENDPOINT",
            "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        )
        monkeypatch.setenv("FACTIFY_VIDEO_READER__PER_MINUTE_CAP", "5")
        monkeypatch.setenv("FACTIFY_MODELS__VIDEO_READING", "gemini-3-flash")

        settings = Settings(_env_file=None)

        assert settings.social.platforms == ("x", "instagram")
        assert settings.social.max_pictures == 2
        assert settings.video_reader.usable
        assert settings.video_reader.per_minute_cap == 5
        assert settings.models.video_reading == "gemini-3-flash"

    def test_every_new_variable_is_in_the_example_configuration(self) -> None:
        example = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
        names = [f"FACTIFY_SOCIAL__{name.upper()}" for name in SocialSettings.model_fields]
        names += [
            f"FACTIFY_VIDEO_READER__{name}"
            for name in ("ENABLED", "API_KEY", "ENDPOINT", "PER_MINUTE_CAP", "DAILY_CAP")
        ]
        names.append("FACTIFY_MODELS__VIDEO_READING")

        assert [name for name in names if name not in example] == []
