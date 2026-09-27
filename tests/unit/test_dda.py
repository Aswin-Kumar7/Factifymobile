"""DDA, the second AI-picture detector (app/media/detectors/dda.py).

Held here, without the 1.2 GB checkpoint or PyTorch:

  - the network sees exactly the pixels DDA's own code gives it: the central 336 x 336
    at the picture's resolution, black padding for small pictures, CLIP's
    normalisation - checked pixel for pixel against torchvision when it is installed;
  - a missing, broken or unloadable checkpoint makes the detector unavailable and
    every score None - never an exception, never a "not AI";
  - whatever the network returns, the likelihood is a probability, and the model is
    loaded once however many threads ask at the same moment.

The last test runs the real model (`uv run --extra models pytest -m model`).
"""

from __future__ import annotations

import io
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.media.detectors import dda
from app.media.detectors.dda import CROP, MEAN, STD, THRESHOLD, DdaDetector, DdaScore
from tests.unit import images

pytestmark = pytest.mark.unit

MODELS = Path(__file__).resolve().parents[2] / ".cache" / "models"
EVAL = Path(__file__).resolve().parents[2] / ".cache" / "eval" / "mllm"
CHECKPOINT_FOLDER, CHECKPOINT_FILE = dda.CHECKPOINT


def _png(picture: Image.Image) -> bytes:
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG")
    return buffer.getvalue()


def _noise(width: int, height: int, seed: int = 0) -> Image.Image:
    pixels = np.random.default_rng(seed).integers(0, 256, (height, width, 3), dtype=np.uint8)
    return Image.fromarray(pixels, "RGB")


def _with_checkpoint(tmp_path: Path) -> str:
    """A model folder whose checkpoint exists; the fake network never reads it."""
    folder = tmp_path / CHECKPOINT_FOLDER
    folder.mkdir(parents=True)
    (folder / CHECKPOINT_FILE).write_bytes(b"not read by the fake network")
    return str(tmp_path)


class _FakeNetwork:
    def __init__(self, logits: list[float]) -> None:
        self._logits = list(logits)
        self.inputs: list[np.ndarray] = []

    def __call__(self, array: np.ndarray) -> float:
        self.inputs.append(array)
        return self._logits.pop(0)


def _fake(monkeypatch: pytest.MonkeyPatch, network: _FakeNetwork) -> list[Path]:
    loads: list[Path] = []

    def load(path: Path, *, threads: int) -> _FakeNetwork:
        time.sleep(0.05)  # long enough for racing threads to arrive while it loads
        loads.append(path)
        return network

    monkeypatch.setattr(dda, "_load_network", load)
    return loads


# --- what the network sees ---------------------------------------------------------


@pytest.mark.parametrize("size", [(640, 480), (336, 336), (1001, 1000), (337, 900)])
def test_prepared_is_one_normalised_336_square(size: tuple[int, int]) -> None:
    array = dda.prepared(images.scene(1, size=size))
    assert array.shape == (1, 3, CROP, CROP)
    assert array.dtype == np.float32


def test_a_large_picture_is_cropped_not_resized() -> None:
    """The middle 336 pixels at full resolution: resizing would smooth away the
    traces DDA reads."""
    picture = _noise(1000, 800, seed=3)
    expected = np.asarray(picture)[232:568, 332:668]
    assert np.array_equal(np.asarray(dda.centre_crop(picture)), expected)


def test_normalisation_is_clips() -> None:
    grey = Image.new("RGB", (400, 400), (128, 64, 200))
    array = dda.prepared(grey)
    for channel, value in enumerate((128, 64, 200)):
        expected = (value / 255.0 - MEAN[channel]) / STD[channel]
        assert array[0, channel] == pytest.approx(np.full((CROP, CROP), expected), abs=1e-6)


def test_a_small_picture_is_padded_with_black() -> None:
    white = Image.new("RGB", (100, 50), (255, 255, 255))
    cropped = np.asarray(dda.centre_crop(white))
    assert cropped.shape == (CROP, CROP, 3)
    # torchvision puts the odd extra pixel on the right and bottom: 118 left, 143 top.
    assert (cropped[143:193, 118:218] == 255).all()
    assert cropped.sum() == 255 * 3 * 100 * 50


@pytest.mark.parametrize(
    "size", [(640, 480), (337, 337), (338, 341), (300, 500), (500, 300), (99, 101), (1, 1)]
)
def test_the_same_pixels_as_ddas_own_transform(size: tuple[int, int]) -> None:
    """DDA's inference.py, run beside ours: torchvision's CenterCrop, ToTensor and
    Normalize. Odd and even margins, and pictures smaller than the crop on one side,
    both sides and neither."""
    transforms = pytest.importorskip("torchvision.transforms")
    picture = _noise(*size, seed=size[0] * 7 + size[1])
    theirs = transforms.Compose(
        [
            transforms.CenterCrop(CROP),
            transforms.ToTensor(),
            transforms.Normalize(mean=list(MEAN), std=list(STD)),
        ]
    )(picture)
    assert np.array_equal(dda.prepared(picture)[0], theirs.numpy())


# --- when it cannot score ----------------------------------------------------------


def test_unavailable_when_the_checkpoint_is_missing(tmp_path: Path) -> None:
    detector = DdaDetector(directory=str(tmp_path))
    assert not detector.available
    assert detector.score(_png(images.scene(1))) is None
    assert not detector.available


def test_a_checkpoint_that_does_not_load_makes_it_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(path: Path, *, threads: int) -> dda.Network:
        raise RuntimeError("PytorchStreamReader failed reading zip archive")

    monkeypatch.setattr(dda, "_load_network", broken)
    detector = DdaDetector(directory=_with_checkpoint(tmp_path))
    assert detector.available  # the file is there, so a score is expected...
    assert detector.score(_png(images.scene(1))) is None
    assert not detector.available  # ...until the load has failed
    assert "could not be loaded" in caplog.text


def test_bytes_that_are_not_a_picture_score_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    network = _FakeNetwork([2.0])
    _fake(monkeypatch, network)
    detector = DdaDetector(directory=_with_checkpoint(tmp_path))
    assert detector.score(b"<html>not a picture</html>") is None
    assert network.inputs == []


# --- what it returns ---------------------------------------------------------------


def test_the_likelihood_is_always_a_probability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logits = [-1000.0, -4.0, 0.0, 4.0, 1000.0]
    network = _FakeNetwork(logits)
    _fake(monkeypatch, network)
    detector = DdaDetector(directory=_with_checkpoint(tmp_path))

    scores = [detector.score(_png(images.scene(seed))) for seed in range(len(logits))]

    likelihoods = [score.likelihood for score in scores if score is not None]
    assert len(likelihoods) == len(logits)
    assert all(0.0 <= value <= 1.0 for value in likelihoods)
    assert likelihoods == sorted(likelihoods)
    assert likelihoods[0] == 0.0 and likelihoods[-1] == 1.0
    assert likelihoods[2] == 0.5
    assert all(score is not None and score.threshold == THRESHOLD for score in scores)
    assert all(array.shape == (1, 3, CROP, CROP) for array in network.inputs)


def test_raised_at_the_threshold() -> None:
    assert DdaScore(likelihood=0.5, threshold=0.5).raised
    assert not DdaScore(likelihood=0.49, threshold=0.5).raised


def test_a_network_that_returns_nan_scores_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake(monkeypatch, _FakeNetwork([float("nan")]))
    detector = DdaDetector(directory=_with_checkpoint(tmp_path))
    assert detector.score(_png(images.scene(1))) is None


def test_loaded_once_however_many_threads_ask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loads = _fake(monkeypatch, _FakeNetwork([0.0] * 8))
    detector = DdaDetector(directory=_with_checkpoint(tmp_path))
    threads = [threading.Thread(target=detector.load) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    detector.score(_png(images.scene(1)))
    assert len(loads) == 1
    assert detector.available


# --- the real model ----------------------------------------------------------------


@pytest.mark.model
def test_the_real_model_scores_pictures() -> None:
    """The released checkpoint, on the CPU: a probability for every picture, the same
    one twice for the same bytes. Uses the evaluation pictures when they are on this
    machine (.cache/eval/mllm), a generated one otherwise."""
    pytest.importorskip("torch")
    if dda.model_path(str(MODELS), *dda.CHECKPOINT) is None:
        pytest.skip("the DDA checkpoint is not in .cache/models/dda")
    detector = DdaDetector(directory=str(MODELS))
    detector.load()
    assert detector.available

    found = sorted(EVAL.glob("*/*.*"))[:3] if EVAL.is_dir() else []
    pictures = [path.read_bytes() for path in found] or [_png(images.scene(1))]
    for data in pictures:
        first, second = detector.score(data), detector.score(data)
        assert first is not None and second is not None
        assert 0.0 <= first.likelihood <= 1.0
        assert first.threshold == THRESHOLD
        assert first.likelihood == pytest.approx(second.likelihood, abs=1e-6)
