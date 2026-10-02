"""One picture of a whole clip: a contact sheet of its frames, for the hosted reader.

What a video shows - who is speaking, where, under which channel's logo - is asked of
the hosted model once per video, not once per frame: two dozen frames sent one by one
would cost more than the check. So up to nine of the frames read for the clip's words
(`FramesRead`) are laid out in a grid, in time order, each with its moment written in
its corner, and the model describes the grid as the video it came from
(`OcrExtractor.describe_video`).

The nine are the ones that between them show the most of the clip: its opening and
its end, then each time the frame least like any already chosen, so ten frames of
one talking head do not crowd out the one card that says what the clip is about.

Pure: pictures in, a picture out.
"""

from __future__ import annotations

import io
import math
from collections.abc import Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from app.media.video import Keyframe, clock

# Frames on one sheet, at most: a three by three grid.
SHEET_FRAMES = 9
# Each frame fits in a square this size, so a nine-frame sheet of a 16:9 clip is about
# 1450 x 830 - legible to the model, and one ordinary picture's worth of tokens.
CELL = 480
GAP = 6
BACKGROUND = (24, 24, 24)
LABEL_SIZE = 18

# The size frames are compared at when choosing: enough to tell two shots apart.
_COMPARE = (48, 27)


def pick_for_sheet(frames: Sequence[Keyframe], most: int = SHEET_FRAMES) -> list[Keyframe]:
    """Up to `most` frames that between them show the clip, in time order.

    The first and the last, then repeatedly the frame least like any chosen so far
    (farthest-point sampling on small grey copies). A frame that cannot be opened is
    never chosen.
    """
    ordered = sorted(frames, key=lambda frame: frame.timestamp_ms)
    looks = {
        index: look
        for index, frame in enumerate(ordered)
        if (look := _look(frame.data)) is not None
    }
    usable = sorted(looks)
    if len(usable) <= most:
        return [ordered[index] for index in usable]
    chosen = [usable[0], usable[-1]]
    while len(chosen) < most:
        best, distance = None, -1.0
        for index in usable:
            if index in chosen:
                continue
            nearest = min(float(np.mean(np.abs(looks[index] - looks[other]))) for other in chosen)
            if nearest > distance:
                best, distance = index, nearest
        if best is None:
            break
        chosen.append(best)
    return [ordered[index] for index in sorted(chosen)]


def contact_sheet(frames: Sequence[Keyframe]) -> bytes | None:
    """The frames in a grid, left to right and top to bottom, each with its number and
    moment ("3 | 1:52") on the sheet just above it, as one JPEG; None when no frame
    can be opened.

    The label is never on the frame itself: in a corner it covered the CNN logo at
    the top left of a screen recording (2026-10-03).
    """
    pictures: list[tuple[Keyframe, Image.Image]] = []
    for frame in frames:
        picture = _opened(frame.data)
        if picture is not None:
            picture.thumbnail((CELL, CELL))
            pictures.append((frame, picture))
    if not pictures:
        return None
    count = len(pictures)
    columns = 1 if count == 1 else 2 if count <= 4 else 3
    rows = math.ceil(count / columns)
    width = max(picture.width for _, picture in pictures)
    height = max(picture.height for _, picture in pictures)
    font = _font()
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    left_edge, top_edge, _, bottom_edge = probe.textbbox((0, 0), "0 | 0:00", font=font)
    strip = math.ceil(bottom_edge - top_edge) + 8
    cell = height + strip
    sheet = Image.new(
        "RGB",
        (columns * width + (columns + 1) * GAP, rows * cell + (rows + 1) * GAP),
        BACKGROUND,
    )
    draw = ImageDraw.Draw(sheet)
    for number, (frame, picture) in enumerate(pictures):
        row, column = divmod(number, columns)
        left = GAP + column * (width + GAP)
        top = GAP + row * (cell + GAP)
        draw.text(
            (left + 2 - left_edge, top + 4 - top_edge),
            f"{number + 1} | {clock(frame.timestamp_ms)}",
            fill=(255, 255, 255),
            font=font,
        )
        sheet.paste(
            picture,
            (left + (width - picture.width) // 2, top + strip + (height - picture.height) // 2),
        )
    out = io.BytesIO()
    sheet.save(out, "JPEG", quality=85)
    return out.getvalue()


def _opened(data: bytes) -> Image.Image | None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            return image.convert("RGB")
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        return None


def _look(data: bytes) -> np.ndarray | None:
    picture = _opened(data)
    if picture is None:
        return None
    return np.asarray(picture.convert("L").resize(_COMPARE), dtype=np.float32)


def _font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=LABEL_SIZE)
    except TypeError:  # a Pillow too old to size its own font
        return ImageFont.load_default()
