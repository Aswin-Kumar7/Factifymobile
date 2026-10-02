"""A link to a post on X, Instagram or YouTube, checked on everything it holds (1.8).

The post's words, its pictures read like uploaded pictures, its video read like an
uploaded video, YouTube's page and thumbnail, and the article it links to - and what
could not be read said part by part. The platforms, the readers and the models are
all stood in for.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

import app.api.verify as verify_module
from app.api.post_checks import YOUTUBE_LIMIT, checked_post
from app.api.schemas import VerifyRequest, VerifyResponse
from app.cache.keys import text_hash
from app.domain.enums import Action
from app.extraction.claims import ExtractedClaims
from app.extraction.language import detect
from app.extraction.ocr import OcrOutcome
from app.extraction.reading import WITHHELD_SUMMARY, Gap, GapCode, gap
from app.extraction.social import Downloaded, PostMedia, SocialPost
from app.intake.normalizer import InputType, normalise_url
from app.intake.social_urls import READER_VERSION, recognise
from app.sources.base import check_seconds
from app.sources.verification import page_key
from app.verdict.engine import CaseDecision
from tests.unit import images
from tests.unit.factories import claim
from tests.unit.test_orchestration import _result
from tests.unit.test_upload_reading import _Inspector

pytestmark = pytest.mark.unit

X_URL = "https://x.com/dailybharatupd/status/1973412345678901234?s=20&t=share"
X_POST = "https://x.com/dailybharatupd/status/1973412345678901234"
PICTURE = "https://pbs.twimg.com/media/Gabc123.jpg?name=large"
SAID = "BIG BREAKING: RBI to withdraw all ₹500 notes from 1 November. Share with everyone!"
CARD = "RESERVE BANK OF INDIA\nPRESS RELEASE\n₹500 notes to be withdrawn from circulation"
SHOWS = "A document styled as an RBI press release, with the bank's emblem at the top."


def _x_post(**fields: Any) -> SocialPost:
    ref = recognise(X_POST)
    assert ref is not None
    base: dict[str, Any] = {
        "ref": ref,
        "author_name": "Daily Bharat Updates",
        "handle": "dailybharatupd",
        "published_at": datetime(2026, 10, 1, 14, 12, tzinfo=UTC),
        "text": SAID,
        "text_route": "x.syndication",
        "language": "en",
        "media": (PostMedia(kind="image", url=PICTURE),),
    }
    base.update(fields)
    return SocialPost(**base)


class _Platform:
    """The social reader, stood in for: one post, and the media it can download."""

    def __init__(self, post: SocialPost, media: dict[str, bytes | Gap] | None = None) -> None:
        self.post = post
        self.media = {PICTURE: images.original()} if media is None else media
        self.reads: list[Any] = []
        self.downloads: list[tuple[str, int | None]] = []

    def handles(self, ref: Any) -> bool:
        return True

    async def read(self, ref: Any) -> SocialPost:
        self.reads.append(ref)
        return self.post

    async def download(
        self, media: PostMedia, *, max_bytes: int, max_seconds: int | None = None
    ) -> Downloaded | Gap:
        self.downloads.append((media.url, max_seconds))
        got = self.media.get(media.url)
        if isinstance(got, Gap):
            return got
        if got is None:
            return gap(
                "picture_text",
                GapCode.PICTURE_UNREAD,
                "A picture in the post could not be downloaded.",
            )
        return Downloaded(
            data=got, mime="video/mp4" if media.kind != "image" else "image/jpeg", url=media.url
        )


class _Pictures:
    """The picture reader, stood in for."""

    def __init__(self, outcome: OcrOutcome | None = None) -> None:
        self.read: list[bytes] = []
        self.outcome = outcome or OcrOutcome(
            text=CARD, language=detect(CARD), description=SHOWS, kind="DOCUMENT", text_area=0.4
        )

    async def transcribe(self, image: bytes, *, mime_type: str = "") -> OcrOutcome:
        self.read.append(image)
        return self.outcome


class _KeepingInspector(_Inspector):
    """The picture checks, which also keep a small copy for the answer to show."""

    def keep_picture(self, data: bytes) -> str:
        return "0123456789abcdef0123456789abcdef"


class _Checker:
    """Claim extraction and the orchestrator, stood in for."""

    def __init__(self, claims: tuple[Any, ...] = (claim(),), hit: Any = None) -> None:
        self.claims = claims
        self.hit = hit
        self.documents: list[tuple[str, dict[str, Any]]] = []
        self.probed: list[tuple[Any, int]] = []
        self.verified: list[dict[str, Any]] = []
        self.platform: _Platform | None = None

    async def extract(self, text: str, **kwargs: Any) -> ExtractedClaims:
        self.documents.append((text, kwargs))
        return ExtractedClaims(claims=self.claims)

    async def cached(self, intake: Any, *, case_id: UUID) -> Any:
        self.probed.append((intake, len(self.platform.reads) if self.platform else 0))
        return self.hit

    async def verify(self, intake: Any, *, case_id: UUID, claims: Any, **kwargs: Any) -> Any:
        self.verified.append({"intake": intake, "claims": list(claims), **kwargs})
        if kwargs.get("synthetic") is not None:
            self.verified[-1]["ai"] = await kwargs["synthetic"]()
        action = Action.SAFE_TO_SHARE if claims else Action.SEND_TO_REVIEW
        decision = CaseDecision(action=action, rule_id="r", reason="because")
        return _result(case_id=case_id, action=action, case_decision=decision)


def _app(
    platform: _Platform,
    checker: _Checker,
    *,
    pictures: _Pictures | None = None,
    inspector: Any = None,
    vendor: str | None = None,
) -> Any:
    from app.main import create_app

    app = create_app()
    checker.platform = platform
    app.state.social_reader = platform
    app.state.claim_pipeline = checker
    app.state.orchestrator = checker
    app.state.ocr = pictures or _Pictures()
    app.state.media_inspector = inspector
    if vendor is not None:

        class _Vendor:
            async def _vendor_extract(self, url: str) -> str:
                return vendor or ""

        app.state.web_search_resolver = _Vendor()
    return app


async def _check(app: Any, body: dict[str, Any]) -> dict[str, Any]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://factify.test") as api:
        response = await api.post("/v1/verify", json=body)
    assert response.status_code == 200, response.text
    answer: dict[str, Any] = response.json()
    return answer


class TestAnXPostWithAPicture:
    async def test_its_words_and_its_picture_are_checked_together(self) -> None:
        platform, checker, pictures = _Platform(_x_post()), _Checker(), _Pictures()
        app = _app(platform, checker, pictures=pictures)

        body = await _check(app, {"url": X_URL})

        # Asked the cache by the post's own identity, before anything was read.
        [(probed, reads_before)] = checker.probed
        assert reads_before == 0
        assert probed.cache_identity == normalise_url(X_URL).cache_identity
        assert READER_VERSION == "2026.10.02.3"
        # The picture was downloaded and read like an uploaded one.
        assert platform.downloads == [(PICTURE, None)]
        assert len(pictures.read) == 1
        [(document, kwargs)] = checker.documents
        assert document.index(f"Post text:\n{SAID}") < document.index(
            f"Text in the picture:\n{CARD}"
        )
        assert f"What the picture shows (described by Factify):\n{SHOWS}" in document
        assert kwargs["content_hash"] == text_hash(document)
        assert kwargs["input_kind"] == "url"

        verified = checker.verified[0]
        assert verified["intake"].input_type is InputType.URL
        assert verified["intake"].cache_identity == probed.cache_identity
        assert page_key(X_POST) in verified["own_pages"]
        assert verified["partial_input"] is False
        assert verified["noted"] == []

        read = body["input_read"]
        assert (read["kind"], read["platform"], read["handle"]) == (
            "social_post",
            "x",
            "dailybharatupd",
        )
        assert read["author"] == "Daily Bharat Updates" and read["complete"] is True
        assert [part["kind"] for part in read["parts"]] == [
            "post_text",
            "picture_text",
            "picture_description",
        ]
        for part in read["parts"]:
            assert part["checked"]
            assert document[part["char_start"] : part["char_end"]] == part["text"]
        assert body["image_reading"]["text"] == CARD

    async def test_its_picture_checks_stand_beside_the_answer(self) -> None:
        platform, checker = _Platform(_x_post()), _Checker()
        # A photograph, not a designed card: the detector's word stands.
        photo = OcrOutcome(text="", description="Eight leaders in one selfie.", kind="PHOTO")
        app = _app(platform, checker, pictures=_Pictures(photo), inspector=_KeepingInspector())

        body = await _check(app, {"url": X_URL})

        assert body["media_report"]["kind"] == "image"
        assert body["media_report"]["detector"]["agreement"] == "likely_ai"
        assert body["media_reports"] == []
        assert checker.verified[0]["ai"] is True
        [picture] = [p for p in body["input_read"]["parts"] if p["kind"] == "picture_text"]
        assert picture["media_url"].startswith("/v1/media/thumbnails/")

    async def test_a_picture_that_could_not_be_downloaded_is_said_and_the_words_are_checked(
        self,
    ) -> None:
        platform, checker = _Platform(_x_post(), media={}), _Checker()
        app = _app(platform, checker)

        body = await _check(app, {"url": X_URL})

        [(document, _)] = checker.documents
        assert document == f"Post text:\n{SAID}"
        verified = checker.verified[0]
        assert verified["partial_input"] is True
        assert [(n.check, n.kind) for n in verified["noted"]] == [("image_text", "reading")]
        read = body["input_read"]
        assert read["checked_partially"] is True and read["verdict_withheld"] is False
        [missed] = read["gaps"]
        assert (missed["code"], missed["blocking"]) == ("picture_unread", True)
        assert missed["detail"] == "The post's picture could not be downloaded."

    async def test_a_picture_whose_reader_broke_is_one_picture_unread(self) -> None:
        class _Broken:
            async def transcribe(self, image: bytes, *, mime_type: str = "") -> OcrOutcome:
                raise TimeoutError("the reader hung")

        platform, checker = _Platform(_x_post()), _Checker()
        app = _app(platform, checker)
        app.state.ocr = _Broken()

        body = await _check(app, {"url": X_URL})

        [missed] = body["input_read"]["gaps"]
        assert missed["code"] == "picture_unread"
        assert "TimeoutError" in missed["detail"]
        assert checker.documents[0][0] == f"Post text:\n{SAID}"

    async def test_a_picture_only_post_whose_picture_failed_is_held_back(self) -> None:
        platform = _Platform(_x_post(text="😱😱"), media={})
        checker = _Checker()
        app = _app(platform, checker)

        body = await _check(app, {"url": X_URL})

        assert checker.documents == []
        assert checker.verified[0]["claims"] == [] and checker.verified[0]["fresh"] is True
        assert body["summary"] == WITHHELD_SUMMARY["en"]
        assert body["input_read"]["verdict_withheld"] is True
        assert any(s["check"] == "claim_extraction" for s in body["skipped"])
        assert not verify_module.billable(VerifyResponse.model_validate(body))

    async def test_a_wordless_photograph_is_asked_its_own_questions(self) -> None:
        photo = OcrOutcome(text="", description="A flooded street at dusk.", kind="PHOTO")
        platform, checker = _Platform(_x_post(text="")), _Checker()
        app = _app(platform, checker, pictures=_Pictures(photo))

        body = await _check(app, {"url": X_URL})

        # No words of its own: nothing to find claims in, and Factify's account of it
        # is not checked as if it were the post's.
        assert checker.documents == []
        verified = checker.verified[0]
        assert verified["claims"] == []
        assert verified["intake"].input_type is InputType.IMAGE
        assert verified["intake"].cache_identity == normalise_url(X_URL).cache_identity
        described = next(
            p for p in body["input_read"]["parts"] if p["kind"] == "picture_description"
        )
        assert described["checked"] is False

    async def test_a_repeat_is_answered_before_the_post_is_read(self) -> None:
        platform = _Platform(_x_post())
        checker = _Checker(hit=_result(from_cache=True))
        app = _app(platform, checker)

        body = await _check(app, {"url": X_URL})

        assert body["from_cache"] is True
        assert platform.reads == [] and platform.downloads == []

    async def test_a_post_s_address_pasted_as_a_message_is_the_post(self) -> None:
        platform, checker = _Platform(_x_post()), _Checker()
        app = _app(platform, checker)

        body = await _check(app, {"text": f"{X_URL} via the X app"})

        assert len(platform.reads) == 1
        assert body["input_read"]["kind"] == "social_post"

    async def test_a_message_that_says_more_than_the_link_is_a_message(self) -> None:
        platform, checker = _Platform(_x_post()), _Checker()
        app = _app(platform, checker)

        body = await _check(
            app, {"text": f"The RBI is withdrawing every ₹500 note from November {X_URL}"}
        )

        assert platform.reads == []
        assert body["input_read"]["kind"] == "text"


class TestWhatAPostLinksTo:
    async def test_the_article_is_read_and_is_never_its_own_evidence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        article = "https://www.hindustantimes.com/india-news/rbi-notes-101.html"
        text = "RBI says ₹500 notes remain legal tender\n\nThe Reserve Bank said on Wednesday..."

        async def read(request: Any, url: str) -> Any:
            assert url == article
            return verify_module.LinkedPage(text, route="vendor_extract", total_chars=len(text))

        monkeypatch.setattr(verify_module, "_read_linked_article", read)
        platform = _Platform(_x_post(media=(), links=(article,)))
        checker = _Checker()
        app = _app(platform, checker)

        body = await _check(app, {"url": X_URL})

        [(document, _)] = checker.documents
        assert f"Linked article (hindustantimes.com):\n{text}" in document
        assert page_key(article) in checker.verified[0]["own_pages"]
        kinds = [p["kind"] for p in body["input_read"]["parts"]]
        assert kinds == ["post_text", "linked_article"]

    async def test_a_short_link_to_an_article_is_read_as_a_link(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def read(request: Any, url: str) -> Any:
            return verify_module.LinkedPage("A story with a claim in it, read whole.")

        monkeypatch.setattr(verify_module, "_read_linked_article", read)
        tco = recognise("https://t.co/AbCdEf123")
        assert tco is not None
        platform = _Platform(SocialPost(ref=tco, not_a_post_url="https://example.org/story"))
        checker = _Checker()
        app = _app(platform, checker)

        body = await _check(app, {"url": "https://t.co/AbCdEf123"})

        assert body["input_read"]["kind"] == "link"
        assert body["input_read"]["url"] == "https://example.org/story"


class TestAPostWithAVideo:
    VIDEO = "https://video.twimg.com/ext_tw_video/1/pu/vid/720x1280/a.mp4"

    def _post(self, videos: int = 1) -> SocialPost:
        return _x_post(
            media=tuple(
                PostMedia(kind="video", url=f"{self.VIDEO}?{index}", duration_seconds=12.0)
                for index in range(videos)
            )
        )

    async def test_a_quick_check_says_the_video_needs_a_background_check(self) -> None:
        platform, checker = _Platform(self._post()), _Checker()
        app = _app(platform, checker)

        body = await _check(app, {"url": X_URL})

        assert platform.downloads == []
        [missed] = body["input_read"]["gaps"]
        assert (missed["code"], missed["blocking"]) == ("needs_background", True)
        assert checker.verified[0]["partial_input"] is True

    async def test_past_the_second_video_of_an_album_is_said_unread(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def unreadable(request: Any, data: bytes, *, window: int) -> Any:
            return SimpleNamespace(reason="no frames could be taken"), None

        monkeypatch.setattr(verify_module, "read_video", unreadable)
        platform = _Platform(self._post(videos=3), media={})
        platform.media = {f"{self.VIDEO}?{i}": b"\x00" * 64 for i in range(3)}
        checker = _Checker()
        app = _app(platform, checker)
        budget = check_seconds.set(300.0)
        try:
            response = await checked_post(
                SimpleNamespace(app=app),  # type: ignore[arg-type]
                VerifyRequest(url=X_URL),
                normalise_url(X_URL),
                recognise(X_POST),  # type: ignore[arg-type]
                case_id=uuid4(),
                arrived=0.0,
            )
        finally:
            check_seconds.reset(budget)

        # Two downloaded, each for the read window; the third never.
        assert [url for url, _ in platform.downloads] == [f"{self.VIDEO}?0", f"{self.VIDEO}?1"]
        assert {seconds for _, seconds in platform.downloads} == {600}
        gaps = [(g.code, g.blocking, g.detail) for g in response.input_read.gaps]  # type: ignore[union-attr]
        assert (
            "video_unread",
            False,
            "The post has 3 videos; Factify read the first 2.",
        ) in gaps
        assert (
            "video_unread",
            True,
            "Video 1 of 2 could not be read (no frames could be taken).",
        ) in gaps
        assert checker.verified[0]["partial_input"] is True


@pytest.mark.skipif(
    not __import__("app.media.video", fromlist=["ffmpeg_available"]).ffmpeg_available(),
    reason="ffmpeg is not installed",
)
class TestAPostSVideoIsReadLikeAnUpload:
    async def test_what_is_said_shown_and_seen_are_checked_with_the_post_s_words(
        self, tmp_path: Any
    ) -> None:
        from app.extraction.local_ocr import LocalFirstOcr
        from tests.unit.test_frame_text import _clip
        from tests.unit.test_upload_reading import SAID as SPOKEN
        from tests.unit.test_upload_reading import _Describer, _Ears, _FrameWords, _heard

        clip = _clip(tmp_path / "clip.mp4", seconds=14, cuts=False)
        video = "https://video.twimg.com/ext_tw_video/9/pu/vid/a.mp4"
        post = _x_post(media=(PostMedia(kind="video", url=video, duration_seconds=14.0),))
        platform = _Platform(post, media={video: clip})
        checker = _Checker()
        app = _app(platform, checker)
        app.state.ocr = LocalFirstOcr(local=_FrameWords(), hosted=_Describer())  # type: ignore[arg-type]
        app.state.speech_reader = _Ears(_heard())
        budget = check_seconds.set(300.0)
        try:
            response = await checked_post(
                SimpleNamespace(app=app),  # type: ignore[arg-type]
                VerifyRequest(url=X_URL),
                normalise_url(X_URL),
                recognise(X_POST),  # type: ignore[arg-type]
                case_id=uuid4(),
                arrived=0.0,
            )
        finally:
            check_seconds.reset(budget)

        [(document, _)] = checker.documents
        assert document.index("Post text:") < document.index(f"Said in the video:\n{SPOKEN}")
        assert "Text shown in the video:\nNDTV Profit" in document
        assert "What the video shows (described by Factify):" in document
        assert response.speech is not None and response.speech.text == SPOKEN
        kinds = [part.kind for part in response.input_read.parts]  # type: ignore[union-attr]
        assert kinds == ["post_text", "transcript", "on_screen_text", "video_description"]
        assert any(item.check == "video_frames" for item in response.skipped)
        assert checker.verified[0]["partial_input"] is False


class TestAYouTubeVideo:
    SHORT = "https://www.youtube.com/shorts/ikPJlAdAuaE"
    THUMBNAIL = "https://i.ytimg.com/vi/ikPJlAdAuaE/hqdefault.jpg"
    PAGE = "Leopard enters a house in Nashik village, residents flee. Captions: look at it!"

    def _post(self) -> SocialPost:
        ref = recognise(self.SHORT)
        assert ref is not None
        return SocialPost(
            ref=ref,
            author_name="Wild India",
            title="Leopard attacks man in Nashik village",
            text_route="youtube.oembed",
            thumbnail_url=self.THUMBNAIL,
        )

    def _platform(self) -> _Platform:
        return _Platform(self._post(), media={self.THUMBNAIL: images.original(seed=3)})

    async def test_without_a_video_reader_it_is_read_from_its_page_and_thumbnail(self) -> None:
        thumbnail = OcrOutcome(
            text="LEOPARD ATTACK", description="A leopard on a village street at night."
        )
        platform, checker = self._platform(), _Checker()
        app = _app(platform, checker, pictures=_Pictures(thumbnail), vendor=self.PAGE)

        body = await _check(app, {"url": self.SHORT})

        [(probed, _)] = checker.probed
        assert probed.cache_identity.endswith("|video:not_watched")
        [(document, _)] = checker.documents
        assert document.startswith("Title:\nLeopard attacks man in Nashik village")
        assert f"Description:\n{self.PAGE}" in document
        assert "Text in the video's thumbnail:\nLEOPARD ATTACK" in document
        assert "What the video's thumbnail shows (described by Factify):" in document
        verified = checker.verified[0]
        assert verified["partial_input"] is False
        assert verified["intake"].cache_identity == probed.cache_identity

        read = body["input_read"]
        assert read["platform"] == "youtube" and read["verdict_withheld"] is False
        [missed] = read["gaps"]
        assert (missed["code"], missed["blocking"]) == ("video_unread", False)
        assert read["limits"] == [YOUTUBE_LIMIT]
        assert read["checked_partially"] is False

    async def test_with_nothing_in_it_to_check_it_is_held_back_not_refused(self) -> None:
        platform, checker = self._platform(), _Checker(claims=())
        app = _app(platform, checker, vendor=self.PAGE)

        body = await _check(app, {"url": self.SHORT})

        assert body["claims"] == []
        assert body["input_read"]["verdict_withheld"] is True
        assert body["summary"] == WITHHELD_SUMMARY["en"]

    async def test_with_a_video_reader_the_video_is_watched(self) -> None:
        from app.extraction.video_reader import VideoReading

        class _Watcher:
            async def read_youtube(self, video_id: str, *, max_seconds: int) -> VideoReading:
                assert video_id == "ikPJlAdAuaE"
                return VideoReading(
                    transcript="The leopard was rescued by the forest department.",
                    shows="A leopard in a village street.",
                    limited=True,
                    seconds_read=60,
                )

        platform, checker = self._platform(), _Checker()
        app = _app(platform, checker, vendor=self.PAGE)
        app.state.video_reader = _Watcher()

        body = await _check(app, {"url": self.SHORT})

        [(probed, _)] = checker.probed
        assert probed.cache_identity.endswith("|video:watched")
        [(document, _)] = checker.documents
        assert "Spoken in the video:\nThe leopard was rescued" in document
        # Its gaps are said, and none holds the answer back.
        assert all(not g["blocking"] for g in body["input_read"]["gaps"])
        assert checker.verified[0]["partial_input"] is False
        # Watched: its thumbnail is not read as well.
        assert platform.downloads == []


class TestAPostThatCannotBeRead:
    async def test_a_deleted_post_is_held_back_with_what_the_platform_said(self) -> None:
        ref = recognise(X_POST)
        assert ref is not None
        gone = gap("post", GapCode.POST_UNAVAILABLE, "X says this post does not exist.")
        platform, checker = _Platform(SocialPost(ref=ref, gaps=(gone,))), _Checker()
        app = _app(platform, checker)

        body = await _check(app, {"url": X_URL})

        assert checker.documents == []
        read = body["input_read"]
        assert read["verdict_withheld"] is True
        assert [g["code"] for g in read["gaps"]] == ["post_unavailable"]
        post_text = next(s for s in body["skipped"] if s["check"] == "post_text")
        assert post_text["kind"] == "reading"


def test_the_readers_version_moved_with_the_wiring() -> None:
    """Text-only verdicts cached under a post's identity before its pictures were read
    must not be served for it now."""
    assert READER_VERSION == "2026.10.02.3"
    assert asyncio.iscoroutinefunction(checked_post)
