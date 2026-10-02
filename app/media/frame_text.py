"""The words shown in a video, read from its frames on our own server.

A video's claim is often written on it rather than said: a headline card, a news
ticker, captions burned in over music. Until now one frame was read - the middle
keyframe, as a picture - so words shown before or after it were never checked. Here
every keyframe is read by our own text reader (`LocalOcr`, PP-OCRv5), and what was
read is put together in the order it appeared, each line once.

Our own reader only, never the hosted one: two dozen frames sent to a paid model
would cost more than the check, and a frame whose text is thin is little loss when
the frames around it show the same words.

What is kept:

  - Lines read with a confidence of 0.8 or more. The Devanagari reader "read" a
    Tamil card as garbage at 0.74 and a Bengali one at 0.73 (2026-09-28), while real
    Hindi and English text reads at 0.96-1.00. One line is judged here, not a whole
    picture, so the bar is the line's own, below the 0.88 mean at which a picture's
    reading is trusted without the hosted reader (`ENOUGH_CONFIDENCE`).
  - Each line once. A caption held over a run of frames, a channel's name in every
    corner: a line that is the same as one already kept, ignoring case and spacing,
    or nearly so (a similarity ratio above 0.9: one misread letter in a headline),
    is dropped, and of the two the one read more surely is kept, where the first was.
    Never two lines with different numbers in them: a ticker going from "Sensex up
    200" to "Sensex up 250" is two claims, and a number is what a claim most often
    turns on. A digit misread is then kept twice, which costs a repeated line; the
    other way would cost a claim.
  - A market ticker's figures once. A line that is mostly digits ("NIFTY 50
    24602.25") is kept while it shows a word not shown before, and not again with
    each new tick (`_figures`).
  - At most 4000 characters; more is said to be cut off.

What is read is text to check, as a pasted message is, and the frames are only where
it was found. It is never evidence and decides nothing on its own.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Protocol

from app.extraction.local_ocr import LocalFirstOcr, LocalOcr, LocalReading, OcrLine
from app.observability.logging import event

logger = logging.getLogger("factify.media.frame_text")

MIN_CONFIDENCE = 0.8
# Above this similarity two lines are one line read twice.
DUPLICATE_RATIO = 0.9
# A line this much digits is a ticker's figures (`_figures`).
FIGURES_SHARE = 0.4
# The words in a line, in any script: runs of letters (and the marks that go with
# them), without digits.
_WORDS = re.compile(r"[^\W\d_]+")
MAX_CHARACTERS = 4000

# The numbers in a line, in any script's digits: Devanagari ones (०-९) included.
_NUMBERS = re.compile(r"\d+")


class ReadsLines(Protocol):
    """Our own text reader, as `LocalOcr` is: the lines in one picture."""

    def read(self, data: bytes) -> LocalReading | None: ...


@dataclass(frozen=True, slots=True)
class FramesText:
    """The words shown in a video, each line once, in the order they appeared."""

    text: str
    # Frames the reader read (with or without words on them), of those it was given.
    frames_read: int
    frames_total: int
    # More was shown than is kept (`MAX_CHARACTERS`).
    cut_off: bool = False
    # Why nothing was read: no reader here, or every frame failed.
    reason: str | None = None

    @property
    def complete(self) -> bool:
        """Every frame was read and everything read was kept."""
        return self.frames_read == self.frames_total and not self.cut_off


def local_reader(ocr: object) -> LocalOcr | None:
    """Our own text reader from the server's picture reader (`app.state.ocr`).

    The local half of `LocalFirstOcr`; None when pictures are read by the hosted
    model alone, which is not asked to read frames.
    """
    if isinstance(ocr, LocalFirstOcr):
        return ocr.local
    if isinstance(ocr, LocalOcr):
        return ocr
    return None


async def read_frames_text(
    local: ReadsLines | None,
    frames: Sequence[bytes],
    *,
    budget_seconds: float | None = None,
) -> FramesText:
    """Every frame read for its words, the lines kept as the module says.

    With `budget_seconds`, reading stops once that much time has gone (after at
    least one frame), and the frames are read so that any first few cover the whole
    clip (`_coverage_order`): a reading cut short then misses the words between the
    frames read rather than the end of the video. Never raises.
    """
    total = len(frames)
    if not frames:
        return FramesText(text="", frames_read=0, frames_total=0)
    if local is None:
        return FramesText(
            text="", frames_read=0, frames_total=total, reason="unavailable: no text reader here"
        )

    started = time.perf_counter()
    read: dict[int, tuple[OcrLine, ...]] = {}
    failures = 0
    order = _coverage_order(total) if budget_seconds is not None else list(range(total))
    for index in order:
        if budget_seconds is not None and read and time.perf_counter() - started > budget_seconds:
            break
        try:
            # One frame at a time, each off the event loop: the reader already uses
            # every thread it is given, and a cancelled check stops between frames.
            reading = await asyncio.to_thread(local.read, frames[index])
        except Exception:
            if not failures:
                logger.exception("a video frame could not be read for its text")
            failures += 1
            continue
        if reading is None:
            # No reader could be loaded; none will be for the next frame either.
            return FramesText(
                text="",
                frames_read=0,
                frames_total=total,
                reason="unavailable: the text reader could not be loaded",
            )
        read[index] = reading.lines

    found = [line for index in sorted(read) for line in read[index]]
    kept, dropped = _distinct(found)
    text, cut_off = _capped(kept)
    event(
        logger,
        "frames read for text",
        module="media.frame_text",
        outcome="ok" if text else ("failed" if not read else "empty"),
        provider="local",
        frames_read=len(read),
        frames_total=total,
        failures=failures,
        lines=len(kept),
        duplicates=dropped,
        characters=len(text),
        cut_off=cut_off,
        latency_ms=round((time.perf_counter() - started) * 1000),
    )
    return FramesText(
        text=text,
        frames_read=len(read),
        frames_total=total,
        cut_off=cut_off,
        reason=None if read else "failed: no frame could be read",
    )


def _distinct(lines: Sequence[OcrLine]) -> tuple[list[str], int]:
    """The lines worth keeping, each once, in order; and how many repeats were dropped.

    A line below `MIN_CONFIDENCE`, or with fewer than two letters or digits in it (a
    rule, a bullet, a stray mark or a lone "1"), is not kept at all. Nor is a market
    ticker's next tick: a line mostly of digits ("NIFTY 50 24602.25") whose words
    have all been shown already is dropped, and so is a line of bare figures after
    the first - a business channel's ticker filled four fifths of an RBI clip's text
    with them (2026-10-03).
    """
    kept: list[tuple[str, str, float]] = []  # (compared form, as shown, confidence)
    # Every word in the lines kept, and whether a line of figures alone was kept.
    said: set[str] = set()
    bare_figures = False
    dropped = 0
    for line in lines:
        if line.confidence < MIN_CONFIDENCE:
            continue
        shown = " ".join(line.text.split())
        if sum(character.isalnum() for character in shown) < 2:
            continue
        compared = shown.casefold()
        words = set(_WORDS.findall(compared))
        if _figures(compared) and (words <= said if words else bare_figures):
            # The ticker again: words already shown, with its figures moved on.
            dropped += 1
            continue
        said |= words
        bare_figures = bare_figures or (not words and _figures(compared))
        twin = next((at for at, (other, _, _) in enumerate(kept) if _alike(compared, other)), None)
        if twin is None:
            kept.append((compared, shown, line.confidence))
            continue
        dropped += 1
        if line.confidence > kept[twin][2]:
            # The surer reading of the same line, where the line first appeared.
            kept[twin] = (compared, shown, line.confidence)
    return [shown for _, shown, _ in kept], dropped


def _figures(line: str) -> bool:
    """Whether a line is mostly figures: at least `FIGURES_SHARE` of its letters and
    digits are digits. "Sensex up 200" is a sentence with a number in it; "USD-INR
    6.94% 2036 YLD" is a ticker."""
    characters = [character for character in line if character.isalnum()]
    digits = sum(character.isdigit() for character in characters)
    return bool(characters) and digits >= FIGURES_SHARE * len(characters)


def _alike(one: str, other: str) -> bool:
    """Whether two lines (already casefolded) are the same line read twice."""
    if one == other:
        return True
    if _NUMBERS.findall(one) != _NUMBERS.findall(other):
        return False
    matcher = SequenceMatcher(None, one, other, autojunk=False)
    # The cheap upper bounds first: most pairs of lines are nothing alike.
    return (
        matcher.real_quick_ratio() > DUPLICATE_RATIO
        and matcher.quick_ratio() > DUPLICATE_RATIO
        and matcher.ratio() > DUPLICATE_RATIO
    )


def _capped(lines: Sequence[str]) -> tuple[str, bool]:
    """The lines, one to a row, up to `MAX_CHARACTERS`; and whether any were left out."""
    pieces: list[str] = []
    size = 0
    for line in lines:
        extra = len(line) + (1 if pieces else 0)
        if size + extra > MAX_CHARACTERS:
            return "\n".join(pieces), True
        pieces.append(line)
        size += extra
    return "\n".join(pieces), False


def _coverage_order(count: int) -> list[int]:
    """Frame indices so that any first few are spread across the clip.

    The first and last, then the middle, then the middle of each half, and so on:
    for five frames 0, 4, 2, 1, 3.
    """
    if count <= 2:
        return list(range(count))
    order = [0, count - 1]
    spans = deque([(0, count - 1)])
    while spans:
        low, high = spans.popleft()
        if high - low < 2:
            continue
        middle = (low + high) // 2
        order.append(middle)
        spans.append((low, middle))
        spans.append((middle, high))
    return order
