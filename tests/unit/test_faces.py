"""The face-swap detector (2026-09-27): which faces are judged, how they are cut, and
how their estimates become one - with the models faked, so none of it needs PyTorch,
OpenCV or 1.3 GB of weights.

Held here:

  - the face is cut as GenD's own pipeline cut it: upright on its landmarks, square,
    1.3x the face;
  - faces under 48 px are skipped, at most five are judged, largest first, and a
    picture reads as its highest estimate;
  - a video is judged on the largest face in each of at most 12 frames, and reads as
    the mean of its three highest;
  - no face is "no face" (no likelihood), never a score of zero;
  - missing, half-downloaded or broken weights leave the detector unavailable, which
    the check reports as "not checked".

The last test runs the real models, when their files are on this machine.
"""

from __future__ import annotations

import io
import json
import math
import threading
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.media.detectors import faces
from app.media.detectors.faces import MAX_FRAMES, Face, FaceScore, FaceSwapDetector
from app.media.detectors.gend.align import TEMPLATE, align_face, crop_size, similarity

pytestmark = pytest.mark.unit

MODELS = Path(".cache/models")
GEND_SAMPLES = Path(".cache/src/GenD/datasets/FF")


def _png(
    size: tuple[int, int] = (640, 480), colour: tuple[int, int, int] = (90, 120, 150)
) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, format="PNG")
    return buffer.getvalue()


def _face(x: float, y: float, side: float) -> Face:
    """A face whose landmarks sit on the template inside its box."""
    return Face(
        box=(x, y, side, side),
        landmarks=TEMPLATE * side + np.array([x, y]),
        confidence=0.95,
    )


def _safetensors(path: Path, *, complete: bool = True) -> None:
    header = json.dumps({"w": {"dtype": "F32", "shape": [4], "data_offsets": [0, 16]}}).encode()
    body = bytes(16 if complete else 5)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(len(header).to_bytes(8, "little") + header + body)


def _installed(directory: Path, *, complete: bool = True) -> None:
    (directory / "yunet").mkdir(parents=True, exist_ok=True)
    (directory / "yunet" / "face_detection_yunet_2023mar.onnx").write_bytes(b"onnx")
    _safetensors(directory / "gend-pe-l" / "model.safetensors", complete=complete)


def _available(detector: FaceSwapDetector) -> bool:
    # Read through a call, so the type checker does not carry an earlier
    # `assert not detector.available` forward.
    return detector.available


class _Judge:
    """Returns the scores it is given, in order, and remembers what it was shown."""

    def __init__(self, scores: list[float]) -> None:
        self.scores = list(scores)
        self.shown: list[Image.Image] = []

    def __call__(self, crops: list[Image.Image]) -> list[float]:
        self.shown.extend(crops)
        taken, self.scores = self.scores[: len(crops)], self.scores[len(crops) :]
        return taken


Install = Callable[..., tuple[FaceSwapDetector, _Judge]]


@pytest.fixture
def fake_models(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Install:
    """A detector whose files are 'there' and whose models are the fakes given."""

    def install(
        found: list[Face] | None = None, scores: list[float] | None = None
    ) -> tuple[FaceSwapDetector, _Judge]:
        _installed(tmp_path)
        judge = _Judge(scores or [0.5] * 64)
        monkeypatch.setattr(faces, "_libraries_installed", lambda: True)
        monkeypatch.setattr(faces, "_load_finder", lambda path: lambda picture: list(found or []))
        monkeypatch.setattr(faces, "_load_judge", lambda weights, **kw: judge)
        return FaceSwapDetector(directory=str(tmp_path)), judge

    return install


# --- the crop -----------------------------------------------------------------------


def test_crop_is_the_face_with_thirty_percent_context() -> None:
    # Landmarks exactly on the template at 200 px: the crop is 1.3 x 200.
    assert crop_size(TEMPLATE * 200 + 40) == 260


def test_crop_turns_a_tilted_face_upright() -> None:
    angle = math.radians(25)
    rotation = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    landmarks = (TEMPLATE * 150) @ rotation.T + np.array([300.0, 120.0])

    size = crop_size(landmarks)
    target = (TEMPLATE + 0.15) * size / 1.3
    moved = np.hstack([landmarks, np.ones((5, 1))]) @ similarity(landmarks, target).T
    assert size == 195
    assert np.allclose(moved, target, atol=1e-6)

    # And the pixels follow: a dot painted on each landmark lands on the template.
    canvas = np.zeros((600, 700, 3), dtype=np.uint8)
    for x, y in landmarks:
        canvas[round(y) - 3 : round(y) + 4, round(x) - 3 : round(x) + 4] = 255
    crop = np.asarray(align_face(Image.fromarray(canvas), landmarks))
    assert crop.shape == (size, size, 3)
    for x, y in target:
        assert crop[round(y), round(x)].min() > 200


# --- which faces are judged -----------------------------------------------------------


def test_small_faces_are_skipped(fake_models: Install) -> None:
    detector, judge = fake_models(found=[_face(10, 10, 30), _face(200, 100, 120)], scores=[0.2])
    result = detector.score(_png())
    assert result == FaceScore(faces=1, likelihood=0.2, threshold=0.5)
    assert len(judge.shown) == 1


def test_at_most_five_faces_largest_first_and_the_highest_counts(fake_models: Install) -> None:
    sides = [60, 150, 90, 200, 70, 120, 110, 80]
    found = [_face(10 + i * 70, 10, side) for i, side in enumerate(sides)]
    detector, judge = fake_models(found=found, scores=[0.1, 0.3, 0.9, 0.2, 0.4])

    result = detector.score(_png((1200, 800)))

    assert result is not None
    assert result.faces == 5
    assert result.likelihood == 0.9
    assert result.raised
    shown = [crop.width for crop in judge.shown]
    assert shown == sorted(shown, reverse=True)
    assert shown[0] == crop_size(_face(0, 0, 200).landmarks)
    assert shown[-1] == crop_size(_face(0, 0, 90).landmarks)


def test_a_picture_with_no_face_has_no_likelihood(fake_models: Install) -> None:
    detector, judge = fake_models(found=[])
    result = detector.score(_png())
    assert result == FaceScore(faces=0, likelihood=None, threshold=0.5)
    assert not result.raised
    assert judge.shown == []


def test_an_unreadable_picture_is_not_checked(fake_models: Install) -> None:
    detector, _ = fake_models(found=[_face(100, 100, 100)])
    assert detector.score(b"not a picture") is None


# --- video keyframes ------------------------------------------------------------------


def test_frames_read_as_the_mean_of_the_three_highest(fake_models: Install) -> None:
    detector, _ = fake_models(found=[_face(100, 100, 100)], scores=[0.1, 0.9, 0.8, 0.2, 0.7])
    result = detector.score_frames([_png() for _ in range(5)])
    assert result is not None
    assert result.faces == 5
    assert result.likelihood == pytest.approx(0.8)


def test_fewer_than_three_faces_are_averaged_as_they_are(fake_models: Install) -> None:
    detector, _ = fake_models(found=[_face(100, 100, 100)], scores=[0.2, 0.6])
    result = detector.score_frames([_png(), _png()])
    assert result is not None
    assert result.likelihood == pytest.approx(0.4)


def test_only_the_largest_face_in_each_frame_is_judged(fake_models: Install) -> None:
    detector, judge = fake_models(found=[_face(10, 10, 80), _face(200, 100, 160)])
    detector.score_frames([_png() for _ in range(3)])
    assert [crop.width for crop in judge.shown] == [crop_size(_face(0, 0, 160).landmarks)] * 3


def test_at_most_twelve_frames_are_judged(fake_models: Install) -> None:
    detector, judge = fake_models(found=[_face(100, 100, 100)])
    result = detector.score_frames([_png() for _ in range(30)])
    assert result is not None
    assert result.faces == MAX_FRAMES
    assert len(judge.shown) == MAX_FRAMES


def test_frames_without_faces_have_no_likelihood(fake_models: Install) -> None:
    detector, _ = fake_models(found=[])
    assert detector.score_frames([_png(), b"broken"]) == FaceScore(0, None, 0.5)


# --- availability ---------------------------------------------------------------------


def test_unavailable_without_its_files(tmp_path: Path) -> None:
    detector = FaceSwapDetector(directory=str(tmp_path))
    assert not detector.available
    assert detector.score(_png()) is None
    assert detector.score_frames([_png()]) is None


def test_unavailable_while_the_weights_are_still_downloading(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _installed(tmp_path, complete=False)
    monkeypatch.setattr(faces, "_libraries_installed", lambda: True)
    loads: list[Path] = []
    monkeypatch.setattr(faces, "_load_judge", lambda weights, **kw: loads.append(weights))
    detector = FaceSwapDetector(directory=str(tmp_path))
    assert not detector.available
    assert detector.score(_png()) is None
    assert loads == []

    # Finished: now it loads, because a download in progress was never a failure.
    _safetensors(tmp_path / "gend-pe-l" / "model.safetensors")
    monkeypatch.setattr(faces, "_load_finder", lambda path: lambda picture: [])
    monkeypatch.setattr(faces, "_load_judge", lambda weights, **kw: _Judge([]))
    assert _available(detector)
    assert detector.score(_png()) == FaceScore(0, None, 0.5)


def test_unavailable_without_its_libraries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _installed(tmp_path)
    monkeypatch.setattr(faces, "_libraries_installed", lambda: False)
    detector = FaceSwapDetector(directory=str(tmp_path))
    assert not detector.available
    assert detector.score(_png()) is None


def test_weights_that_fail_to_load_leave_it_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _installed(tmp_path)
    monkeypatch.setattr(faces, "_libraries_installed", lambda: True)
    monkeypatch.setattr(faces, "_load_finder", lambda path: lambda picture: [])

    def broken(weights: Path, **kw: object) -> None:
        raise RuntimeError("Error(s) in loading state_dict")

    monkeypatch.setattr(faces, "_load_judge", broken)
    detector = FaceSwapDetector(directory=str(tmp_path))

    assert detector.score(_png()) is None
    assert not detector.available
    assert "could not be loaded" in caplog.text


def test_loads_once_however_many_checks_arrive_together(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _installed(tmp_path)
    monkeypatch.setattr(faces, "_libraries_installed", lambda: True)
    monkeypatch.setattr(faces, "_load_finder", lambda path: lambda picture: [])
    loads: list[int] = []

    def slow(weights: Path, **kw: object) -> _Judge:
        loads.append(1)
        time.sleep(0.05)
        return _Judge([])

    monkeypatch.setattr(faces, "_load_judge", slow)
    detector = FaceSwapDetector(directory=str(tmp_path))
    threads = [threading.Thread(target=detector.load) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert loads == [1]


# --- the real models ------------------------------------------------------------------


@pytest.mark.model
def test_real_models_on_gend_own_samples() -> None:
    """GenD's own FaceForensics++ examples: a DeepFakes frame and the real frame it
    was made from. Needs the weights in .cache/models and a GenD clone in .cache/src."""
    detector = FaceSwapDetector(directory=str(MODELS))
    real = sorted((GEND_SAMPLES / "real" / "000").glob("*.png"))
    fake = sorted((GEND_SAMPLES / "DF" / "000_003").glob("*.png"))
    if not detector.available or not real or not fake:
        pytest.skip("GenD weights, YuNet or GenD's sample frames are not on this machine")

    real_score = detector.score(real[0].read_bytes())
    fake_score = detector.score(fake[0].read_bytes())
    assert real_score is not None and fake_score is not None
    assert real_score.faces == fake_score.faces == 1
    assert real_score.likelihood is not None and fake_score.likelihood is not None
    assert real_score.likelihood < 0.5 <= fake_score.likelihood

    frames = detector.score_frames([path.read_bytes() for path in fake])
    assert frames is not None
    assert frames.faces == len(fake)
    assert frames.raised

    assert detector.score(_png()) == FaceScore(faces=0, likelihood=None, threshold=0.5)
