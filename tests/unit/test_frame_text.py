"""The words shown in a video (contract 1.8): every keyframe read, each line once.

The text reader is stood in for: these test what is done with the lines it returns,
and which frames it is given. The frames themselves are taken by real ffmpeg where it
is installed, from clips built here whose colour says the second they were made at.
"""

from __future__ import annotations

import asyncio
import io
import shutil
import subprocess
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from app.extraction.local_ocr import LocalFirstOcr, LocalOcr, LocalReading, OcrLine
from app.media import frame_text
from app.media.frame_text import (
    MAX_CHARACTERS,
    FramesText,
    _coverage_order,
    local_reader,
    read_frames_text,
)
from app.media.video import (
    CLOSING_SECONDS,
    OPENING_SECONDS,
    READ_FRAMES,
    READ_SECONDS,
    SETTLED_SECONDS,
    KeyframeExtractor,
    clearest,
    clock,
    ffmpeg_available,
    pass_timeout,
    reading_moments,
)

pytestmark = pytest.mark.unit

requires_ffmpeg = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg is not installed")


class _Reader:
    """Our own text reader, stood in for: the lines each frame holds, as read."""

    def __init__(
        self,
        frames: dict[bytes, list[tuple[str, float]]],
        *,
        broken: frozenset[bytes] = frozenset(),
        clock: SimpleNamespace | None = None,
    ) -> None:
        self._frames = frames
        self._broken = broken
        self._clock = clock
        self.asked: list[bytes] = []

    def read(self, data: bytes) -> LocalReading | None:
        self.asked.append(data)
        if self._clock is not None:
            self._clock.now += 1.0
        if data in self._broken:
            raise ValueError("not a picture")
        lines = tuple(
            OcrLine(text=text, confidence=confidence, top=10.0 * row, left=0.0)
            for row, (text, confidence) in enumerate(self._frames.get(data, []))
        )
        return LocalReading(lines=lines, elapsed_ms=1.0)


def _read(reader: object, frames: list[bytes], **options: object) -> FramesText:
    return asyncio.run(read_frames_text(reader, frames, **options))  # type: ignore[arg-type]


# ------------------------------------------------------------------- what is kept


def test_every_frame_is_read_and_its_words_kept_in_the_order_shown() -> None:
    reader = _Reader(
        {
            b"f1": [("BREAKING NEWS", 0.97)],
            b"f2": [("Every woman to get Rs 5,000 a month", 0.95)],
            b"f3": [("Scheme starts on 1 November", 0.99)],
        }
    )

    read = _read(reader, [b"f1", b"f2", b"f3"])

    assert reader.asked == [b"f1", b"f2", b"f3"]
    assert read.text == (
        "BREAKING NEWS\nEvery woman to get Rs 5,000 a month\nScheme starts on 1 November"
    )
    assert (read.frames_read, read.frames_total) == (3, 3)
    assert read.complete
    assert read.reason is None


def test_a_caption_held_over_several_frames_is_kept_once() -> None:
    """The same caption on every frame of a shot, and a channel's name in the corner:
    the same line however its case and spacing were read."""
    reader = _Reader(
        {
            b"f1": [("NEWS 24", 0.96), ("Every woman to get Rs 5,000", 0.95)],
            b"f2": [("news  24", 0.97), ("EVERY WOMAN TO GET RS 5,000", 0.95)],
            b"f3": [("News 24", 0.96), ("Scheme starts in November", 0.99)],
        }
    )

    read = _read(reader, [b"f1", b"f2", b"f3"])

    assert read.text.splitlines() == [
        # The surer reading of the channel's name, where it first appeared.
        "news 24",
        "Every woman to get Rs 5,000",
        "Scheme starts in November",
    ]


def test_a_line_misread_by_a_letter_is_the_same_line_and_the_surer_reading_stays() -> None:
    reader = _Reader(
        {
            b"f1": [("Government annovnces free electricity for farmers", 0.86)],
            b"f2": [("Government announces free electricity for farmers", 0.98)],
        }
    )

    read = _read(reader, [b"f1", b"f2"])

    assert read.text == "Government announces free electricity for farmers"


def test_lines_with_different_numbers_are_never_one_line() -> None:
    """A ticker moving on is a new claim, however alike the rest of it reads."""
    reader = _Reader(
        {
            b"f1": [("Sensex up 200 points in early trade", 0.97)],
            b"f2": [("Sensex up 250 points in early trade", 0.97)],
        }
    )

    read = _read(reader, [b"f1", b"f2"])

    assert read.text.splitlines() == [
        "Sensex up 200 points in early trade",
        "Sensex up 250 points in early trade",
    ]


def test_lines_the_reader_is_unsure_of_are_left_out() -> None:
    """At 0.74 the Devanagari reader was reading another script as garbage."""
    reader = _Reader(
        {
            b"f1": [("पाँच हज़ार रुपये हर महीने", 0.96), ("ਸ਼ਬਦ ਜੋ ਪੜ੍ਹੇ ਨਹੀਂ", 0.74)],
            b"f2": [("on the bar", 0.80), ("just under it", 0.79)],
        }
    )

    read = _read(reader, [b"f1", b"f2"])

    assert read.text.splitlines() == ["पाँच हज़ार रुपये हर महीने", "on the bar"]


def test_marks_with_no_letter_or_digit_are_left_out() -> None:
    reader = _Reader({b"f1": [("—", 0.99), ("|", 0.95), ("Rs 5,000", 0.97), ("• •", 0.9)]})

    assert _read(reader, [b"f1"]).text == "Rs 5,000"


def test_a_tickers_next_figures_are_not_kept_again() -> None:
    """A business channel's ticker: the same words with new figures on every frame
    filled most of an RBI clip's text (2026-10-03). A sentence with a number in it
    is still a new claim when its number changes."""
    reader = _Reader(
        {
            b"f1": [
                ("NIFTY 50 24602.25", 0.97),
                ("USD-INR 6.94% 2036 YLD", 0.96),
                ("RBI keeps repo rate at 5.25%", 0.99),
            ],
            b"f2": [("NIFTY 50 24603.15", 0.97), ("USD-INR 6.95% 2036 YLD", 0.96), ("1", 0.99)],
            b"f3": [("Sensex up 200 points", 0.97), ("Sensex up 250 points", 0.97)],
        }
    )

    assert _read(reader, [b"f1", b"f2", b"f3"]).text.splitlines() == [
        "NIFTY 50 24602.25",
        "USD-INR 6.94% 2036 YLD",
        "RBI keeps repo rate at 5.25%",
        "Sensex up 200 points",
        "Sensex up 250 points",
    ]


def test_more_than_the_cap_is_cut_off_at_a_whole_line() -> None:
    lines = [(f"Line {index:03d} " + "x" * 90, 0.97) for index in range(60)]
    reader = _Reader({b"f1": lines[:30], b"f2": lines[30:]})

    read = _read(reader, [b"f1", b"f2"])

    assert len(read.text) <= MAX_CHARACTERS
    assert read.text.splitlines()[-1].startswith("Line ")
    assert len(read.text.splitlines()[-1]) == len(lines[0][0])
    assert read.cut_off
    assert (read.frames_read, read.frames_total) == (2, 2)
    assert not read.complete


# ---------------------------------------------------------------- what was not read


def test_a_frame_that_cannot_be_read_is_counted_as_unread() -> None:
    reader = _Reader(
        {b"f1": [("BREAKING NEWS", 0.97)], b"f3": [("Scheme starts in November", 0.99)]},
        broken=frozenset({b"f2"}),
    )

    read = _read(reader, [b"f1", b"f2", b"f3"])

    assert read.text == "BREAKING NEWS\nScheme starts in November"
    assert (read.frames_read, read.frames_total) == (2, 3)
    assert not read.complete
    assert read.reason is None


def test_when_no_frame_can_be_read_it_says_so() -> None:
    reader = _Reader({}, broken=frozenset({b"f1", b"f2"}))

    read = _read(reader, [b"f1", b"f2"])

    assert read.text == ""
    assert (read.frames_read, read.frames_total) == (0, 2)
    assert read.reason is not None and read.reason.startswith("failed")


def test_frames_with_no_words_on_them_are_read_all_the_same() -> None:
    """A clip with nothing written on it has been read in full: there is no text."""
    read = _read(_Reader({}), [b"f1", b"f2"])

    assert read.text == ""
    assert read.complete
    assert read.reason is None


def test_without_a_text_reader_nothing_is_read_and_it_says_why() -> None:
    read = _read(None, [b"f1", b"f2"])

    assert (read.text, read.frames_read, read.frames_total) == ("", 0, 2)
    assert read.reason is not None and read.reason.startswith("unavailable")


def test_a_reader_whose_models_did_not_load_is_unavailable() -> None:
    class _Unloaded:
        def read(self, data: bytes) -> LocalReading | None:
            return None

    read = _read(_Unloaded(), [b"f1", b"f2"])

    assert read.frames_read == 0
    assert read.reason is not None and read.reason.startswith("unavailable")


def test_no_frames_is_nothing_to_read() -> None:
    read = _read(_Reader({}), [])

    assert (read.text, read.frames_read, read.frames_total) == ("", 0, 0)
    assert read.complete


def test_a_reading_cut_short_by_its_budget_covers_the_whole_clip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each frame takes a second here; with two and a half, the first, last and middle
    frames are read - not the first three - and their words stay in the order shown."""
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(frame_text, "time", SimpleNamespace(perf_counter=lambda: clock.now))
    frames = [bytes([index]) for index in range(5)]
    reader = _Reader({frame: [(f"caption {frame[0]}", 0.97)] for frame in frames}, clock=clock)

    read = _read(reader, frames, budget_seconds=2.5)

    assert reader.asked == [bytes([0]), bytes([4]), bytes([2])]
    assert read.text.splitlines() == ["caption 0", "caption 2", "caption 4"]
    assert (read.frames_read, read.frames_total) == (3, 5)
    assert not read.complete


def test_the_coverage_order_spreads_and_reads_every_frame_once() -> None:
    assert _coverage_order(5) == [0, 4, 2, 1, 3]
    assert _coverage_order(1) == [0]
    for count in range(30):
        assert sorted(_coverage_order(count)) == list(range(count))


def test_the_text_reader_is_our_own_without_the_hosted_one() -> None:
    """Frames go to our own reader only: two dozen frames to a paid model would cost
    more than the check."""
    local = LocalOcr(directory="nowhere")
    hosted = object()

    assert local_reader(LocalFirstOcr(local=local, hosted=hosted)) is local
    assert LocalFirstOcr(local=local, hosted=hosted).local is local
    assert local_reader(local) is local
    assert local_reader(hosted) is None
    assert local_reader(None) is None


# ------------------------------------------------------------ which frames are read
#
# Frames are read across the whole clip (2026-10-03): one keyframe of the first 90
# seconds was read, and an RBI clip's "REPO RATE UNCHANGED AT 5.25%" card, shown from
# 1:53 to its end, was never seen.


def test_the_opening_and_the_last_second_are_always_read() -> None:
    moments, after_cuts = reading_moments(129.0, most=24)

    assert moments[0] == OPENING_SECONDS
    assert moments[-1] == pytest.approx(129.0 - CLOSING_SECONDS)
    assert moments == sorted(moments)
    assert len(moments) <= 24
    assert after_cuts == 0
    # About every six seconds across all of it, not bunched at the start.
    gaps = [later - earlier for earlier, later in pairwise(moments)]
    assert max(gaps) < 7.0


def test_a_long_clip_is_read_to_the_end_of_its_window() -> None:
    moments, _ = reading_moments(600.0, most=24)

    assert len(moments) == 24
    assert moments[-1] > 599
    gaps = [later - earlier for earlier, later in pairwise(moments)]
    assert max(gaps) < 30


def test_a_frame_is_read_just_after_each_cut_but_not_too_many() -> None:
    moments, after_cuts = reading_moments(129.0, most=24, cuts=[21.08, 35.96])

    assert after_cuts == 2
    assert any(abs(moment - (21.08 + SETTLED_SECONDS)) < 0.01 for moment in moments)
    assert any(abs(moment - (35.96 + SETTLED_SECONDS)) < 0.01 for moment in moments)
    assert len(moments) <= 24

    busy, after_cuts = reading_moments(60.0, most=12, cuts=[float(t) for t in range(1, 59)])
    assert len(busy) <= 12
    assert after_cuts <= 12 // 3
    assert busy[0] == OPENING_SECONDS
    assert busy[-1] == pytest.approx(60.0 - CLOSING_SECONDS)


def test_a_clip_of_a_few_seconds_is_read_at_its_start_and_its_end() -> None:
    moments, _ = reading_moments(2.84, most=24)

    assert moments == [OPENING_SECONDS, pytest.approx(2.84 - CLOSING_SECONDS)]
    assert reading_moments(0.4, most=24)[0] == [pytest.approx(0.0)]
    assert reading_moments(0.0, most=24) == ([], 0)


def _picture(fill: int, *, blur: bool = False) -> bytes:
    """A striped picture: sharp edges, unless blurred."""
    from PIL import ImageFilter

    picture = Image.new("L", (320, 180), fill)
    pixels = picture.load()
    assert pixels is not None
    for x in range(0, 320, 8):
        for y in range(180):
            pixels[x, y] = 255 - fill
    if blur:
        picture = picture.filter(ImageFilter.GaussianBlur(4))
    out = io.BytesIO()
    picture.convert("RGB").save(out, "JPEG", quality=95)
    return out.getvalue()


def test_the_frame_caught_in_a_wipe_is_not_the_one_read() -> None:
    settled = _picture(40)
    wipe = _picture(200)  # unlike the frames either side of it

    assert clearest([settled, wipe, settled, settled]) != 1
    assert clearest([wipe, settled, settled]) != 0


def test_a_blurred_frame_is_not_the_one_read() -> None:
    sharp = _picture(40)
    soft = _picture(40, blur=True)

    assert clearest([soft, soft, sharp, sharp]) in (2, 3)
    assert clearest([sharp]) == 0
    assert clearest([b"not a picture", sharp]) == 1


def test_moments_are_written_as_people_write_them() -> None:
    assert clock(0) == "0:00"
    assert clock(7_400) == "0:07"
    assert clock(129_010) == "2:09"
    assert clock(3_723_000) == "1:02:03"


def test_a_long_decode_is_given_longer() -> None:
    assert pass_timeout(90) == 90.0
    assert pass_timeout(30) == 90.0
    assert pass_timeout(600) == pytest.approx(243.0)


def test_the_reading_extractor_reads_ten_minutes_in_the_background() -> None:
    background = KeyframeExtractor.reading()
    quick = KeyframeExtractor.reading(quick=True)

    assert (background._read_seconds, background._read_frames) == (READ_SECONDS, READ_FRAMES)
    assert (quick._read_seconds, quick._read_frames) == (90, 8)
    # The picture checks keep their keyframes as they were.
    assert background._max_seconds == quick._max_seconds == 90
    assert background._max_keyframes == 12


def _clip(path: Path, *, seconds: int, cuts: bool) -> bytes:
    """A small clip whose green says the second (4 levels a second), and, with
    `cuts`, whose red flips every second - a scene change each second."""
    red = "255*mod(floor(T),2)" if cuts else "0"
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=160x120:d={seconds}:r=10,geq=r='{red}':g='4*T':b='0'",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        timeout=60,
    )
    return path.read_bytes()


def _second_of(frame: bytes) -> float:
    """When a frame of `_clip` was made, read back from its green.

    The frames are limited-range video written as JPEG (`_JPEG_COMPAT`), so 0-255
    comes back as about 16-235.
    """
    with Image.open(io.BytesIO(frame)) as image:
        green = np.asarray(image.convert("RGB"))[:, :, 1]
    return (float(green.mean()) - 16) * 255 / 219 / 4


@requires_ffmpeg
def test_frames_are_read_across_the_whole_clip_with_their_moments(tmp_path: Path) -> None:
    video = _clip(tmp_path / "steady.mp4", seconds=50, cuts=False)

    extracted = asyncio.run(KeyframeExtractor(read_seconds=600, read_frames=8).extract(video))

    assert extracted.succeeded
    read = extracted.read
    assert read is not None and read.reason is None
    assert 6 <= len(read.frames) <= 8
    assert not read.cut_off
    assert read.window_seconds == pytest.approx(50, abs=0.2)
    stamps = [frame.timestamp_ms / 1000 for frame in read.frames]
    assert stamps == sorted(stamps)
    assert stamps[0] < 1.5 and stamps[-1] > 48.5
    # Each frame is from the moment it says it is from.
    for frame in read.frames:
        assert _second_of(frame.data) == pytest.approx(frame.timestamp_ms / 1000, abs=0.6)
    # The picture checks' keyframes are taken as before.
    assert len(extracted.even_frames) == 8


@requires_ffmpeg
def test_a_clip_longer_than_the_window_is_read_to_the_window_and_said_to_be(
    tmp_path: Path,
) -> None:
    video = _clip(tmp_path / "long.mp4", seconds=30, cuts=True)

    extracted = asyncio.run(KeyframeExtractor(read_seconds=12, read_frames=6).extract(video))

    read = extracted.read
    assert read is not None
    assert read.cut_off
    assert read.window_seconds == pytest.approx(12)
    assert read.duration_seconds == pytest.approx(30, abs=0.2)
    assert max(frame.timestamp_ms for frame in read.frames) <= 12_000
    # A cut every second, and still never more than the cap.
    assert len(read.frames) <= 6


@requires_ffmpeg
def test_without_a_read_window_no_frames_are_taken_to_read(tmp_path: Path) -> None:
    video = _clip(tmp_path / "short.mp4", seconds=4, cuts=False)

    assert asyncio.run(KeyframeExtractor().extract(video)).read is None
