"""The picture checks (2026-09-27): credentials, earlier copies, the AI and editing
signals - and that none of them can decide a verdict.

Held here:

  - the credentials reader reads what a file says about itself, including that an AI
    tool made it, and never makes an untrusted credential citable;
  - the AI-image detector's answer is read into two likelihoods, and a detector that
    cannot be reached reads as "not checked", never as "not AI";
  - each check of a picture runs on its own: one failing leaves the others standing;
  - a video is checked from frames spread across it, even one with no scene cuts;
  - earlier copies are shown from our own address, not the third party's.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.api.schemas import media_report_to_response
from app.domain.enums import SyntheticSignal
from app.governor.governor import ProviderUnavailable, SkipReason
from app.media import provenance
from app.media.discovery import DiscoveryResult, MatchingPage, ReverseImageDiscovery
from app.media.report import MediaInspector, ThumbnailStore, _spread
from app.media.synthetic import SightengineDetector, SyntheticReading, parse
from app.media.video import KeyframeExtractor, ffmpeg_available
from app.security.fetcher import FetchFailure, FetchResult
from app.sources.media import ProvenanceResolver
from app.sources.temporal import DatedInstance
from tests.unit import factories

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "media"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _result(body: bytes, *, content_type: str = "application/json", url: str = "x") -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        status_code=200,
        content_type=content_type,
        body=body,
        byte_count=len(body),
        fetched_at=datetime.now(UTC),
    )


class _OpenGovernor:
    async def acquire(self, provider: str) -> None:
        return None


class _ClosedGovernor:
    async def acquire(self, provider: str) -> None:
        raise ProviderUnavailable(provider, SkipReason.DISABLED)


# ------------------------------------------------------------------ credentials


class TestContentCredentials:
    def test_a_file_that_says_an_ai_tool_made_it_is_read_as_saying_so(self) -> None:
        report = provenance.read(_fixture("ai_declared.jpg"), filename="upload")

        assert report.present
        assert report.declares_ai
        assert report.digital_source == "trainedAlgorithmicMedia"
        assert report.generator == "Test Image Model"

    def test_a_credential_from_an_unknown_signer_is_read_but_never_citable(self) -> None:
        report = provenance.read(_fixture("ai_declared.jpg"), filename="upload")

        assert report.untrusted_signer
        assert not report.valid
        # Tier A needs a credential we can vouch for; this one is self-signed.
        resolver = ProvenanceResolver(report=report)
        assert asyncio.run(resolver.candidates(factories.claim())) == []

    def test_a_camera_capture_is_not_called_ai(self) -> None:
        report = provenance.read(_fixture("camera.jpg"), filename="upload")
        assert report.present and not report.declares_ai
        assert report.digital_source == "digitalCapture"

    def test_ai_metadata_without_a_manifest_is_still_read(self) -> None:
        report = provenance.read(_fixture("xmp_ai.jpg"), filename="upload")
        assert not report.present
        assert report.declares_ai

    def test_nothing_declared_is_the_ordinary_case(self) -> None:
        report = provenance.read(_fixture("plain.jpg"), filename="upload")
        assert not report.present and not report.declares_ai
        assert report.reason == "no manifest in this asset"


# ------------------------------------------------------------------ the detector


class TestTheDetector:
    def test_both_likelihoods_are_read(self) -> None:
        reading = parse(
            json.dumps({"status": "success", "type": {"ai_generated": 0.93, "deepfake": 0.02}})
        )
        assert reading.checked
        assert reading.generated == 0.93
        assert reading.face_swap == 0.02

    def test_no_face_is_no_score_not_a_zero(self) -> None:
        reading = parse(json.dumps({"status": "success", "type": {"ai_generated": 0.1}}))
        assert reading.face_swap is None

    def test_a_refusal_is_a_reason_not_a_reading(self) -> None:
        reading = parse(json.dumps({"status": "failure", "error": {"message": "bad key"}}))
        assert not reading.checked
        assert "bad key" in (reading.reason or "")

    def test_its_readings_leave_only_as_advisories(self) -> None:
        advisories = SyntheticReading(generated=0.93, face_swap=0.1).advisories(
            artifact_ref="upload"
        )
        by_provider = {a.provider: a for a in advisories}
        assert by_provider["ai_generation"].signal is SyntheticSignal.ADVISORY_SUSPICION
        assert by_provider["face_swap"].signal is SyntheticSignal.NO_SIGNAL
        assert all("not a finding" in a.note for a in advisories)

    def test_it_uploads_the_picture_and_reads_the_answer(self) -> None:
        sent: dict[str, Any] = {}

        class Fetcher:
            async def post_multipart(
                self, url: str, fields: dict[str, str], files: Any, *, provider: str
            ) -> FetchResult:
                sent.update(url=url, fields=fields, files=files)
                return _result(
                    json.dumps({"status": "success", "type": {"ai_generated": 0.8}}).encode()
                )

        detector = SightengineDetector(
            fetcher=Fetcher(),  # type: ignore[arg-type]
            governor=_OpenGovernor(),  # type: ignore[arg-type]
            endpoint="https://api.sightengine.com/1.0/check.json",
            account="user-1",
            secret="s3cret",
        )
        reading = asyncio.run(detector.read(b"jpeg-bytes"))

        assert reading.generated == 0.8
        assert sent["fields"]["models"] == "genai,deepfake"
        assert sent["files"]["media"][1] == b"jpeg-bytes"

    def test_a_detector_that_is_off_says_not_checked(self) -> None:
        detector = SightengineDetector(
            fetcher=None,  # type: ignore[arg-type]
            governor=_ClosedGovernor(),  # type: ignore[arg-type]
            endpoint="e",
            account="a",
            secret="s",
        )
        reading = asyncio.run(detector.read(b"x"))
        assert not reading.checked and reading.generated is None


# ------------------------------------------------------------------ the inspector


class _Discovery:
    def __init__(self, result: DiscoveryResult) -> None:
        self.result = result
        self.asked = 0

    async def discover(self, image: bytes) -> DiscoveryResult:
        self.asked += 1
        return self.result


class _Detector:
    def __init__(self, reading: SyntheticReading | None = None, *, fails: bool = False) -> None:
        self.reading = reading or SyntheticReading(generated=0.2)
        self.fails = fails

    async def read(self, image: bytes, *, mime: str = "image/jpeg") -> SyntheticReading:
        if self.fails:
            raise RuntimeError("detector down")
        return self.reading


class _ImageFetcher:
    """Serves one picture for the thumbnail of the earliest appearance."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def fetch(self, url: str, *, provider: str = "web") -> FetchResult | FetchFailure:
        self.asked.append(url)
        return _result(_fixture("plain.jpg"), content_type="image/jpeg", url=url)


EARLIEST = DatedInstance(
    url="https://www.reuters.com/2019/flood",
    published_at=datetime(2019, 3, 12, tzinfo=UTC),
    publisher="Reuters",
    image_url="https://static.reuters.com/flood.jpg",
)
LATER = DatedInstance(
    url="https://example.org/2024/repost",
    published_at=datetime(2024, 5, 1, tzinfo=UTC),
)
FOUND = DiscoveryResult(
    pages=(MatchingPage(url=EARLIEST.url), MatchingPage(url=LATER.url)),
    instances=(LATER, EARLIEST),
)


class TestThePictureChecks:
    def test_every_check_is_run_and_the_earliest_copy_is_ours_to_show(self) -> None:
        fetcher = _ImageFetcher()
        inspector = MediaInspector(
            discovery=_Discovery(FOUND),
            detector=_Detector(SyntheticReading(generated=0.91, face_swap=None)),
            fetcher=fetcher,  # type: ignore[arg-type]
        )
        report = asyncio.run(inspector.inspect_image(_fixture("ai_declared.jpg")))

        assert report.credentials.declares_ai
        assert report.earliest == EARLIEST
        # The thumbnail was taken from the third party once, and is served by us.
        assert fetcher.asked == [EARLIEST.image_url]
        assert report.earliest_thumbnail is not None
        assert inspector.thumbnails.get(report.earliest_thumbnail) is not None
        providers = {a.provider for a in report.advisories}
        assert {"ai_generation", "local_forensics"} <= providers

        wire = media_report_to_response(report, thumbnails="/v1/media/thumbnails/")
        assert wire.credentials.status == "untrusted" and wire.credentials.declares_ai
        assert wire.history.status == "found" and wire.history.pages == 2
        assert wire.history.earliest is not None
        assert wire.history.earliest.publisher == "Reuters"
        assert wire.history.earliest.days_before is not None
        assert wire.history.earliest.days_before > 365
        assert wire.history.earliest.thumbnail_url == (
            f"/v1/media/thumbnails/{report.earliest_thumbnail}"
        )
        assert wire.detector.status == "checked" and wire.detector.generated == 0.91
        assert wire.editing.status == "checked"

    def test_one_check_failing_leaves_the_others_standing(self) -> None:
        inspector = MediaInspector(
            discovery=_Discovery(DiscoveryResult(reason="no matching pages found")),
            detector=_Detector(fails=True),
        )
        report = asyncio.run(inspector.inspect_image(_fixture("plain.jpg")))
        wire = media_report_to_response(report, thumbnails="/t/")

        assert wire.detector.status == "not_checked"
        assert wire.history.status == "none"
        assert wire.editing.status == "checked"
        assert wire.credentials.status == "none"

    def test_with_no_provider_configured_nothing_reads_as_clean(self) -> None:
        report = asyncio.run(MediaInspector().inspect_image(_fixture("plain.jpg")))
        wire = media_report_to_response(report, thumbnails="/t/")

        assert wire.history.status == "not_checked"
        assert wire.detector.status == "not_checked"

    def test_a_video_is_checked_across_its_frames(self) -> None:
        discovery = _Discovery(FOUND)
        inspector = MediaInspector(
            discovery=discovery,
            detector=_Detector(SyntheticReading(generated=0.3, face_swap=0.85)),
        )
        frames = [_fixture("plain.jpg")] * 7
        report = asyncio.run(inspector.inspect_video(b"not-a-real-video", frames))

        assert report.kind == "video" and report.frames == 7
        assert discovery.asked == 3  # the paid search, on three frames only
        assert report.synthetic.face_swap == 0.85
        assert report.earliest == EARLIEST

    def test_frames_are_spread_across_the_clip(self) -> None:
        frames = [bytes([i]) for i in range(10)]
        assert _spread(frames, 3) == [bytes([0]), bytes([5]), bytes([9])]
        assert _spread(frames[:2], 3) == frames[:2]


class TestThumbnails:
    def test_kept_for_an_hour_and_bounded(self) -> None:
        store = ThumbnailStore(most=2)
        first = store.put(b"a")
        store.put(b"b")
        store.put(b"c")
        assert store.get(first) is None  # the oldest went first

    def test_served_from_our_address_and_nothing_else(self) -> None:
        from fastapi.testclient import TestClient

        from app.main import create_app

        client = TestClient(create_app())
        inspector = MediaInspector()
        client.app.state.media_inspector = inspector
        key = inspector.thumbnails.put(b"\xff\xd8\xffjpeg")

        served = client.get(f"/v1/media/thumbnails/{key}")
        assert served.status_code == 200
        assert served.headers["content-type"] == "image/jpeg"
        assert client.get("/v1/media/thumbnails/" + "0" * 32).status_code == 404
        assert client.get("/v1/media/thumbnails/../../etc").status_code == 404


class TestReverseImageSearch:
    def test_each_page_keeps_its_copy_of_the_picture(self) -> None:
        discovery = ReverseImageDiscovery(
            fetcher=None,  # type: ignore[arg-type]
            governor=None,  # type: ignore[arg-type]
            endpoint="e",
            api_key="k",
        )
        pages = discovery._parse(
            json.dumps(
                {
                    "responses": [
                        {
                            "webDetection": {
                                "pagesWithMatchingImages": [
                                    {
                                        "url": "https://a.example/story",
                                        "score": 0.9,
                                        "fullMatchingImages": [{"url": "https://a.example/p.jpg"}],
                                    },
                                    {"url": "https://b.example/crop", "score": 0.95},
                                ]
                            }
                        }
                    ]
                }
            )
        )
        assert pages[0].url == "https://a.example/story"  # full matches first
        assert pages[0].image_url == "https://a.example/p.jpg"
        assert pages[1].image_url is None

    def test_the_matched_pages_are_dated_together(self) -> None:
        """Every page is being fetched before the first one has come back."""
        started: list[str] = []
        first_back: list[int] = []

        class SlowFetcher:
            async def fetch(self, url: str, *, provider: str = "web") -> FetchResult:
                started.append(url)
                await asyncio.sleep(0.1)
                first_back.append(len(started))
                html = (
                    "<html><head><meta property='article:published_time' "
                    "content='2019-03-12T10:00:00Z'></head><body><p>A flood.</p></body></html>"
                )
                return _result(html.encode(), content_type="text/html", url=url)

        discovery = ReverseImageDiscovery(
            fetcher=SlowFetcher(),  # type: ignore[arg-type]
            governor=None,  # type: ignore[arg-type]
            endpoint="e",
            api_key="k",
        )
        pages = tuple(MatchingPage(url=f"https://p{i}.example/") for i in range(5))
        instances = asyncio.run(discovery._date(pages))

        assert first_back[0] == 5
        assert len(instances) == 5
        assert all(i.published_at.year == 2019 for i in instances)


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg is not installed")
def test_a_single_shot_video_still_gives_frames(tmp_path: Path) -> None:
    """No scene cuts - one steady shot - and three frames are taken across it."""
    video = tmp_path / "steady.mp4"
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=160x120:d=3",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
    )
    extracted = asyncio.run(KeyframeExtractor().extract(video.read_bytes()))

    assert extracted.succeeded
    assert len(extracted.keyframes) == 3
    assert any("evenly spaced" in note for note in extracted.limitations)
    # And eight frames spread evenly across it, for the face model.
    assert len(extracted.even_frames) == 8


def test_an_old_copy_is_measured_in_days_before_the_check() -> None:
    from app.media.report import days_before

    now = datetime(2026, 9, 27, tzinfo=UTC)
    assert days_before(EARLIEST, now=now) == (now - EARLIEST.published_at).days
    assert days_before(None) is None
    assert days_before(DatedInstance(url="u", published_at=now + timedelta(days=2)), now=now) == 0
