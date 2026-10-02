"""What a link or a message was read as, and what is done when it was read in part (1.8).

The link path used to refuse a page with nothing checkable in it (422, "try pasting
the text of the page") and to check a page read only by its headline as if it were
the article. Now every answer says what was read and what was not (`input_read`,
`skipped[].kind == "reading"`); a page that could not be read is held back, not
refused, and not charged; one read in part is checked on what was read and is never
TRUE. Every reader and model is stood in for.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

import app.api.verify as verify_module
from app.api.schemas import InputReadResponse, ReadGapResponse, VerifyResponse
from app.cache.keys import text_hash
from app.domain.enums import Action
from app.extraction.claimreview import ClaimReview
from app.extraction.claims import ExtractedClaims
from app.extraction.reading import NOTHING_TO_CHECK_SUMMARY, WITHHELD_SUMMARY
from app.orchestration.background import BackgroundChecks, set_phase
from app.verdict.engine import CaseDecision
from tests.unit.factories import claim
from tests.unit.test_orchestration import _result

pytestmark = pytest.mark.unit

ARTICLE = (
    "The state cabinet on Friday approved a 12% rise in the minimum wage for unskilled "
    "workers, effective April 1, the labour minister told reporters in the capital. "
) * 4


class _Checker:
    """The claim extraction and the orchestrator, stood in for."""

    def __init__(self, claims: tuple[Any, ...] = (claim(),)) -> None:
        self.claims = claims
        self.documents: list[tuple[str, dict[str, Any]]] = []
        self.verified: list[dict[str, Any]] = []

    async def extract(self, text: str, **kwargs: Any) -> ExtractedClaims:
        self.documents.append((text, kwargs))
        return ExtractedClaims(claims=self.claims)

    async def cached(self, intake: Any, *, case_id: UUID) -> Any:
        return None

    async def verify(self, intake: Any, *, case_id: UUID, claims: Any, **kwargs: Any) -> Any:
        self.verified.append({"intake": intake, "claims": list(claims), **kwargs})
        decision = CaseDecision(
            action=Action.SEND_TO_REVIEW if not claims else Action.SAFE_TO_SHARE,
            rule_id="r",
            reason="because",
        )
        return _result(case_id=case_id, action=decision.action, case_decision=decision)


def _app(checker: _Checker, page: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    from app.main import create_app

    async def read(request: Any, url: str) -> Any:
        return page

    monkeypatch.setattr(verify_module, "_read_linked_article", read)
    app = create_app()
    app.state.claim_pipeline = checker
    app.state.orchestrator = checker
    return app


async def _post(app: Any, body: dict[str, Any]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://factify.test") as api:
        return await api.post("/v1/verify", json=body)


def _page(**fields: Any) -> verify_module.LinkedPage:
    base: dict[str, Any] = {
        "text": f"Minimum wage up 12%\n\n{ARTICLE}",
        "title": "Minimum wage up 12%",
        "body": ARTICLE,
        "route": "fetched",
        "total_chars": len(ARTICLE),
    }
    base.update(fields)
    return verify_module.LinkedPage(**base)


class TestALinkReadInFull:
    async def test_it_is_checked_and_says_what_was_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        checker = _Checker()
        app = _app(checker, _page(), monkeypatch)

        response = await _post(app, {"url": "https://example.org/wage"})

        assert response.status_code == 200
        [(document, kwargs)] = checker.documents
        # Exactly the text a link was always checked on: the headline, then the body.
        assert document == f"Minimum wage up 12%\n\n{ARTICLE}"
        # Keyed by what was read, not by the address.
        assert kwargs["content_hash"] == text_hash(document)
        read = response.json()["input_read"]
        assert (read["kind"], read["complete"], read["checked_partially"]) == ("link", True, False)
        assert read["url"] == "https://example.org/wage"
        assert [part["kind"] for part in read["parts"]] == ["title", "article"]
        for part in read["parts"]:
            assert document[part["char_start"] : part["char_end"]] == part["text"]
            assert part["route"] == "fetched"
        assert checker.verified[0]["partial_input"] is False
        assert checker.verified[0]["noted"] == []

    async def test_a_long_article_says_how_much_was_read_and_is_still_cached(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        checker = _Checker()
        app = _app(checker, _page(total_chars=30_000), monkeypatch)

        response = await _post(app, {"url": "https://example.org/wage"})

        body = response.json()
        [missed] = body["input_read"]["gaps"]
        assert (missed["code"], missed["blocking"]) == ("article_truncated", False)
        assert "12,000 characters of 30,000" in missed["detail"]
        assert {"check": "linked_page", "kind": "reading"}.items() <= body["skipped"][0].items()
        # Cut the same way every time: it does not keep the answer out of the cache.
        assert checker.verified[0]["noted"] == []
        assert verify_module._MAX_ARTICLE_CHARS == 12000


class TestALinkReadInPart:
    async def test_a_headline_only_page_is_checked_on_its_headline_and_never_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        summary = "The state cabinet on Friday approved a 12% rise in the minimum wage."
        page = _page(
            text=f"Minimum wage up 12%\n\n{summary}",
            body=summary,
            route="headline_summary",
            total_chars=len(summary),
            partial="only the page's headline and summary could be read, not the full article",
        )
        checker = _Checker()
        app = _app(checker, page, monkeypatch)

        response = await _post(app, {"url": "https://example.org/wage"})

        assert response.status_code == 200
        body = response.json()
        read = body["input_read"]
        assert read["checked_partially"] is True and read["verdict_withheld"] is False
        [missed] = read["gaps"]
        assert (missed["code"], missed["blocking"]) == ("headline_only", True)
        assert [part["kind"] for part in read["parts"]] == ["title", "description"]
        verified = checker.verified[0]
        assert verified["partial_input"] is True
        # Kept out of the cache: the article may be read in full next time.
        assert [(item.check, item.kind) for item in verified["noted"]] == [
            ("linked_page", "reading")
        ]

    async def test_a_page_that_could_not_be_read_is_held_back_not_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        checker = _Checker()
        app = _app(checker, None, monkeypatch)

        response = await _post(app, {"url": "https://example.org/wage"})

        assert response.status_code == 200
        body = response.json()
        assert checker.documents == []  # nothing was spent finding claims
        assert body["claims"] == []
        assert body["summary"] == WITHHELD_SUMMARY["en"]
        read = body["input_read"]
        assert read["verdict_withheld"] is True and read["complete"] is False
        [missed] = read["gaps"]
        assert (missed["code"], missed["blocking"]) == ("page_unread", True)
        # An older app is told the input was not checked.
        extraction = next(s for s in body["skipped"] if s["check"] == "claim_extraction")
        assert extraction["kind"] == "reading"
        assert checker.verified[0]["fresh"] is True
        assert verify_module.billable(VerifyResponse.model_validate(body)) is False

    async def test_a_headline_with_nothing_to_check_is_held_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        page = _page(
            text="Live updates",
            title="Live updates",
            body="",
            route="headline_summary",
            partial="only the page's headline and summary could be read, not the full article",
        )
        checker = _Checker(claims=())
        app = _app(checker, page, monkeypatch)

        body = (await _post(app, {"url": "https://example.org/live"})).json()

        assert body["input_read"]["verdict_withheld"] is True
        assert body["summary"] == WITHHELD_SUMMARY["en"]

    async def test_a_page_read_in_full_with_nothing_to_check_says_so(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        checker = _Checker(claims=())
        app = _app(checker, _page(), monkeypatch)

        body = (await _post(app, {"url": "https://example.org/wage"})).json()

        assert body["summary"] == NOTHING_TO_CHECK_SUMMARY["en"]
        assert body["input_read"]["complete"] is True
        assert body["input_read"]["verdict_withheld"] is False
        assert verify_module.billable(VerifyResponse.model_validate(body)) is False


class TestAMessageWithALink:
    async def test_a_link_that_would_not_open_is_said_and_the_message_is_checked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        checker = _Checker()
        app = _app(checker, None, monkeypatch)
        sent = "Banks will stay shut for five days from Monday. https://example.org/banks"

        body = (await _post(app, {"text": sent})).json()

        [(document, _)] = checker.documents
        assert document == sent
        read = body["input_read"]
        assert read["kind"] == "text"
        assert [part["kind"] for part in read["parts"]] == ["message"]
        [missed] = read["gaps"]
        assert (missed["code"], missed["blocking"]) == ("linked_page_unread", False)
        assert checker.verified[0]["partial_input"] is False

    async def test_the_linked_article_is_read_after_the_message_as_before(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        checker = _Checker()
        app = _app(checker, _page(), monkeypatch)
        sent = "Must read! https://example.org/wage"

        body = (await _post(app, {"text": sent})).json()

        [(document, kwargs)] = checker.documents
        assert document == f"{sent}\n\nMinimum wage up 12%\n\n{ARTICLE}"
        assert kwargs["content_hash"] == text_hash(document)
        parts = body["input_read"]["parts"]
        assert [part["kind"] for part in parts] == ["message", "linked_article"]
        assert body["input_read"]["complete"] is True


class TestAFactCheckPageItCannotAnswerBy:
    async def test_the_claim_it_debunks_is_checked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """India Today's and The Quint's desks are not on the fact-checker list, so the
        page's own rating does not answer the claim; the debunked HEADLINE used to be
        set aside all the same, and one supported finding answered TRUE (finding 6)."""
        viral = "Saturday has been declared a holiday for all public sector banks"
        page = _page(
            text=f"Fact Check: {viral}? No.\n\n{ARTICLE}",
            reviewed=(viral,),
            reviews=(
                ClaimReview(
                    claim_reviewed=viral,
                    rating="False",
                    publisher="India Today",
                    published_at=None,
                    url=None,
                ),
            ),
        )
        restated = claim(claim_id="cl_1", text=f"{viral} with immediate effect.")
        finding = claim(claim_id="cl_2", text="The finance ministry issued no such notice.")
        checker = _Checker(claims=(restated, finding))
        app = _app(checker, page, monkeypatch)

        await _post(app, {"url": "https://www.indiatoday.in/fact-check/story/x"})

        assert [item.id for item in checker.verified[0]["claims"]] == ["cl_1", "cl_2"]


class TestShowingWhatWasRead:
    def test_an_answer_held_back_or_a_link_with_nothing_to_check_is_not_charged(self) -> None:
        answer = verify_module.to_response(_result())

        def read(**fields: Any) -> InputReadResponse:
            return InputReadResponse(**fields)

        assert verify_module.billable(answer) is True
        withheld = read(
            kind="link",
            complete=False,
            gaps=(ReadGapResponse(part="page", code="page_unread", detail="x", blocking=True),),
            verdict_withheld=True,
        )
        assert not verify_module.billable(answer.model_copy(update={"input_read": withheld}))
        empty_link = answer.model_copy(update={"input_read": read(kind="social_post")})
        assert not verify_module.billable(empty_link)
        # A message with no claims is charged as it always was.
        assert verify_module.billable(answer.model_copy(update={"input_read": read(kind="text")}))

    async def test_what_was_read_is_kept_with_the_case_and_a_failure_breaks_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        kept: list[tuple[UUID, Any]] = []

        class _Readings:
            def __init__(self, fail: bool) -> None:
                self.fail = fail

            async def put(self, case_id: UUID, response: Any) -> None:
                if self.fail:
                    raise RuntimeError("database down")
                kept.append((case_id, response))

        for fail in (False, True):
            checker = _Checker()
            app = _app(checker, _page(), monkeypatch)
            app.state.case_readings = _Readings(fail)
            response = await _post(app, {"url": "https://example.org/wage"})
            assert response.status_code == 200

        [(case_id, stored)] = kept
        assert str(case_id) == stored.case_id
        assert stored.input_read is not None

    async def test_a_repeat_served_from_the_cache_shows_what_was_read_the_first_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        checker = _Checker()
        app = _app(checker, _page(total_chars=30_000), monkeypatch)
        first = (await _post(app, {"url": "https://example.org/wage"})).json()

        async def cached(intake: Any, *, case_id: UUID) -> Any:
            return _result(case_id=case_id, from_cache=True)

        checker.cached = cached  # type: ignore[method-assign]
        again = (await _post(app, {"url": "https://example.org/wage"})).json()

        assert again["from_cache"] is True
        assert again["input_read"] == first["input_read"]
        assert [s for s in again["skipped"] if s["kind"] == "reading"]


class TestThePhase:
    async def test_a_background_check_says_what_it_is_doing(self) -> None:
        import asyncio

        runs = BackgroundChecks()
        going = asyncio.Event()

        async def work(progress: Any) -> str:
            set_phase("reading_post")
            set_phase("not a phase")  # ignored
            await going.wait()
            set_phase("checking")
            return "done"

        run = runs.start("case-phase", work)
        await asyncio.sleep(0)
        assert run.phase == "reading_post"
        going.set()
        await run.task  # type: ignore[misc]
        assert run.phase == "checking"
        # Outside a background check it is said to nobody.
        set_phase("checking")

    async def test_the_progress_body_carries_it(self) -> None:
        import asyncio

        from app.main import create_app

        app = create_app()
        app.state.orchestrator = SimpleNamespace()
        runs: BackgroundChecks = app.state.background_checks
        hold = asyncio.Event()

        async def work(progress: Any) -> Any:
            set_phase("finding_claims")
            await hold.wait()

        case_id = str(uuid4())
        runs.start(case_id, work)
        await asyncio.sleep(0)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://factify.test") as api:
            polled = await api.get(f"/v1/cases/{case_id}")
        hold.set()

        assert polled.status_code == 202
        assert polled.json()["phase"] == "finding_claims"


@pytest.mark.skipif(
    not __import__("app.media.video", fromlist=["ffmpeg_available"]).ffmpeg_available(),
    reason="ffmpeg is not installed",
)
class TestAnUploadedVideo:
    async def test_a_repeat_is_answered_before_the_video_is_read(self, tmp_path: Any) -> None:
        """Its speech, frames and description were read again on every repeat, only to
        be served the stored verdict afterwards (round-1 note, 2026-10-03)."""
        from app.extraction.ocr import READER_VERSION
        from tests.unit.test_upload_reading import (
            _Describer,
            _FrameWords,
            _heard,
            _request,
            _video,
        )

        intake, data = _video(tmp_path)
        request, checker, ears = _request(
            speech=_heard(), describer=_Describer(), words=_FrameWords()
        )

        async def stored(intake: Any, *, case_id: UUID) -> Any:
            checker.probed.append(intake)
            return _result(case_id=case_id, from_cache=True)

        checker.cached = stored  # type: ignore[method-assign]

        response = await verify_module._checked_video(
            request, intake, data, case_id=uuid4(), recheck=False
        )

        assert response.from_cache is True
        assert ears.windows == []  # nothing was heard
        assert checker.documents == [] and checker.verified == []
        [probed] = checker.probed
        assert probed.cache_identity == f"{intake.cache_identity}|reader:{READER_VERSION}"

    async def test_speech_that_could_not_be_read_keeps_the_answer_from_true(
        self, tmp_path: Any
    ) -> None:
        from app.media.speech import SpeechOutcome
        from tests.unit.test_upload_reading import _Describer, _FrameWords, _request, _video

        intake, data = _video(tmp_path)
        failed = SpeechOutcome(status="failed", reason="the speech reader stopped")
        request, checker, _ = _request(speech=failed, describer=_Describer(), words=_FrameWords())

        response = await verify_module._checked_video(
            request, intake, data, case_id=uuid4(), recheck=False
        )

        assert checker.verified[0]["partial_input"] is True
        read = response.input_read
        assert read is not None and read.checked_partially and not read.verdict_withheld
