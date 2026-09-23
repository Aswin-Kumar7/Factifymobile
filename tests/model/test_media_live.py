"""The M33 gate against real weights, and M35 against real ffmpeg.

    FACTIFY_MODEL_TESTS=1 uv run pytest -m model

The unit-level version of this gate proves the matcher's logic with a stub embedder.
It would pass with any threshold at all. This one runs the real CLIP encoder, so it is
the test that can actually fail when the threshold is wrong — and it did: 0.96,
inherited from M23, rejected three of every four genuine re-shares. The measurement
behind the replacement is in docs/ops-notes.md.

Run on real photographs, never on the synthetic fixtures. CLIP embeds semantic
content, and every synthetic pattern is semantically "an abstract picture with
coloured shapes" — measured, a recompressed copy of one scored 0.9248 against itself
while two unrelated scenes scored 0.9491. Tests skip rather than run on that.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.embeddings.image import ImageEmbedder
from app.media.forensics import analyse_keyframes
from app.media.hashing import CANDIDATE_DISTANCE, fingerprint, phash
from app.media.matching import LocalMatcher, StoredMedia
from app.media.video import KeyframeExtractor, ffmpeg_available
from tests.model import photographs

requires_weights = pytest.mark.skipif(
    os.environ.get("FACTIFY_MODEL_TESTS") != "1",
    reason="set FACTIFY_MODEL_TESTS=1 to download model weights and run these",
)

pytestmark = [pytest.mark.model, requires_weights]

CACHE = Path(".cache/model-tests")


@pytest.fixture(scope="module")
def photos() -> list[bytes]:
    found = photographs.find(limit=8)
    if len(found) < 2:
        pytest.skip(
            "no real photographs found on this machine; CLIP verification cannot be "
            "tested on synthetic patterns (see tests/model/photographs.py)"
        )
    return found


@pytest.fixture(scope="module")
def embedder() -> ImageEmbedder:
    return ImageEmbedder(cache_dir=str(CACHE))


def _encode(embedder: ImageEmbedder, data: bytes, name: str, tmp: Path) -> tuple[float, ...]:
    path = tmp / name
    path.write_bytes(data)
    result = embedder.embed([str(path)])
    assert result.vectors, result.reason
    return result.vectors[0]


def _stored(
    identifier: str, data: bytes, embedding: tuple[float, ...], *, dated: bool = True
) -> StoredMedia:
    marks = fingerprint(data)
    return StoredMedia(
        id=identifier,
        sha256=marks.sha256,
        dhash=marks.dhash,
        phash=marks.phash,
        embedding=embedding,
        source_date=datetime(2019, 3, 14, tzinfo=UTC) if dated else None,
        citation_url="https://example.org/2019/story" if dated else None,
        publisher="Example Wire",
    )


class TestMatchingGateWithRealWeights:
    """M33's gate: recycled matches, visually similar but distinct does not."""

    def test_every_recycled_photograph_matches_its_original(
        self, embedder: ImageEmbedder, photos: list[bytes], tmp_path: Path
    ) -> None:
        """The flagship case: a real photograph, re-shared, found in the corpus.

        Asserted across every available photograph rather than one, because a single
        pair passing says nothing about a threshold.
        """
        matcher = LocalMatcher(embedder=embedder)
        missed: list[str] = []

        for index, photo in enumerate(photos):
            recycled = photographs.recycled(photo)
            corpus = [
                _stored("original", photo, _encode(embedder, photo, f"o{index}.jpg", tmp_path))
            ]

            result = matcher.match(
                fingerprint(recycled),
                corpus=corpus,
                query_embedding=_encode(embedder, recycled, f"r{index}.jpg", tmp_path),
            )

            if not result.found:
                missed.append(f"photo {index}: {result.reason}")
            else:
                assert result.is_citable

        assert not missed, (
            f"{len(missed)} of {len(photos)} recycled photographs were missed: {missed}"
        )

    def test_no_pair_of_distinct_photographs_matches(
        self, embedder: ImageEmbedder, photos: list[bytes], tmp_path: Path
    ) -> None:
        """The hard negative, over every pair. A false match here is the worst
        failure available: a confident, cited, wrong answer."""
        matcher = LocalMatcher(embedder=embedder)
        vectors = [
            _encode(embedder, photo, f"d{i}.jpg", tmp_path) for i, photo in enumerate(photos)
        ]

        false_matches: list[str] = []
        for i, photo in enumerate(photos):
            corpus = [
                _stored(f"other{j}", other, vectors[j]) for j, other in enumerate(photos) if j != i
            ]
            result = matcher.match(fingerprint(photo), corpus=corpus, query_embedding=vectors[i])

            if result.found:
                false_matches.append(
                    f"photo {i} matched {result.matched.id if result.matched else '?'} "
                    f"at {result.similarity:.4f}"
                )

        assert not false_matches, f"false media matches: {false_matches}"

    def test_a_screenshot_of_a_photograph_matches_it(
        self, embedder: ImageEmbedder, photos: list[bytes], tmp_path: Path
    ) -> None:
        """Most submissions arrive as a screenshot of a forward, so this path
        carries more real traffic than the clean-image one."""
        matcher = LocalMatcher(embedder=embedder)
        found = 0

        for index, photo in enumerate(photos):
            shot = photographs.screenshotted(photo)
            corpus = [
                _stored("original", photo, _encode(embedder, photo, f"s{index}.jpg", tmp_path))
            ]

            result = matcher.match(
                fingerprint(shot),
                corpus=corpus,
                query_embedding=_encode(embedder, shot, f"t{index}.jpg", tmp_path),
            )
            found += int(result.found)

        assert found == len(photos), f"only {found} of {len(photos)} screenshots were matched"

    def test_crop_recall_is_recorded_not_asserted(
        self, embedder: ImageEmbedder, photos: list[bytes], tmp_path: Path
    ) -> None:
        """Cropping is where the hash gate genuinely gives out.

        Measured, not asserted: an 8% crop moves pHash past the candidate distance
        for roughly a third of images, so a passing assertion here would be a
        threshold tuned until the test went green rather than a property that holds.
        """
        matcher = LocalMatcher(embedder=embedder)
        found = 0
        distances: list[int] = []

        for index, photo in enumerate(photos):
            crop = photographs.cropped(photo)
            distances.append(phash(photo).distance(phash(crop)))
            corpus = [
                _stored("original", photo, _encode(embedder, photo, f"c{index}.jpg", tmp_path))
            ]

            result = matcher.match(
                fingerprint(crop),
                corpus=corpus,
                query_embedding=_encode(embedder, crop, f"p{index}.jpg", tmp_path),
            )
            found += int(result.found)

        print(  # noqa: T201 — the measurement is the point of this test
            f"\ncrop recall: {found}/{len(photos)} matched; "
            f"pHash distances {sorted(distances)}, gate <= {CANDIDATE_DISTANCE}"
        )
        assert found >= 1, "cropping defeated local matching entirely"


needs_ffmpeg = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg is not installed")


@needs_ffmpeg
class TestVideoWithRealFfmpeg:
    """M35 and M37's 'renders on a real video case'."""

    @staticmethod
    def _clip(tmp_path: Path) -> bytes:
        """Build a short clip with real scene cuts, using ffmpeg itself."""
        import subprocess

        parts = []
        for index, colour in enumerate(("red", "blue", "green", "yellow")):
            part = tmp_path / f"part{index}.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c={colour}:s=320x240:d=2,noise=alls=20:allf=t",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(part),
                ],
                check=True,
            )
            parts.append(part)

        listing = tmp_path / "parts.txt"
        listing.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts), encoding="utf-8")

        output = tmp_path / "clip.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-c",
                "copy",
                str(output),
            ],
            check=True,
        )
        return output.read_bytes()

    def test_keyframes_are_extracted_from_scene_cuts(self, tmp_path: Path) -> None:
        result = asyncio.run(KeyframeExtractor().extract(self._clip(tmp_path)))

        assert result.succeeded, result.reason
        assert result.probe is not None
        assert 1 <= len(result.keyframes) <= 12

    def test_caps_are_enforced(self, tmp_path: Path) -> None:
        result = asyncio.run(KeyframeExtractor(max_keyframes=2).extract(self._clip(tmp_path)))

        assert len(result.keyframes) <= 2

    def test_a_non_video_is_rejected_rather_than_crashing(self) -> None:
        result = asyncio.run(KeyframeExtractor().extract(b"this is not a video"))

        assert not result.succeeded
        assert result.reason is not None

    def test_the_forensic_panel_renders_on_a_real_video_case(self, tmp_path: Path) -> None:
        """M37's gate, on the input it was written for."""
        extracted = asyncio.run(KeyframeExtractor().extract(self._clip(tmp_path)))
        assert extracted.succeeded, extracted.reason

        panel = analyse_keyframes([frame.data for frame in extracted.keyframes])

        assert panel.rendered
        assert panel.advisories
        assert "not used in the verdict" in panel.header
