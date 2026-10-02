"""The text an uploaded picture or video is checked from: labelled blocks (2026-10-03).

A picture or a video says things in more than one way: the words on it, what is said
in it, and what it shows - who is in it, under which channel's logo, with a FAKE stamp
across it. Claims used to be found in the words alone, and in one frame's words for a
video, so a claim the picture itself made - eight leaders in a selfie, one of whom
died in 2024 - could never be checked. Each way is now one block of the text claims
are found in, headed by a label line ending in ':' that Factify wrote:

    Text in the picture:
    ...

    What the picture shows (described by Factify):
    ...

The labels are a convention shared with claim extraction, which is told they are
Factify's, not the author's, and that a "(described by Factify)" block is Factify's
own neutral account of the visuals - what the picture presents, never evidence for
it. They are written here once so every reader uses the same words.

Pure: no input or output.
"""

from __future__ import annotations

from app.extraction.reading import Composed, Reading, picture_text_label

# The labels, exactly. A picture's text is "Text in the picture", or "Text in
# picture 2 of 3" in a post with several (`picture_text_label`).
PICTURE_DESCRIBED = "What the picture shows (described by Factify)"
SPOKEN_IN_VIDEO = "Spoken in the video"
TEXT_IN_VIDEO = "Text shown in the video"
VIDEO_DESCRIBED = "What the video shows (described by Factify)"
POST_TEXT = "Post text"
QUOTED_POST = "Quoted post"

__all__ = [
    "PICTURE_DESCRIBED",
    "POST_TEXT",
    "QUOTED_POST",
    "SPOKEN_IN_VIDEO",
    "TEXT_IN_VIDEO",
    "VIDEO_DESCRIBED",
    "compose",
    "described",
    "picture_text_label",
]

_BETWEEN = "\n\n"


def compose(reading: Reading) -> Composed:
    """Every part with text as "<label>:\\n<text>", a blank line apart, and where each
    part's text sits in the result.

    Unlike `Reading.document()`, a description is part of it: for an upload, what the
    picture shows is something claims are found in. A part with no label is written
    bare, so a PDF's text composes to exactly that text.
    """
    pieces: list[str] = []
    spans: list[tuple[int, int, int]] = []
    at = 0
    for index, part in enumerate(reading.parts):
        if not part.text.strip():
            continue
        if pieces:
            pieces.append(_BETWEEN)
            at += len(_BETWEEN)
        if part.label:
            head = f"{part.label.rstrip(': ')}:\n"
            pieces.append(head)
            at += len(head)
        pieces.append(part.text)
        spans.append((index, at, at + len(part.text)))
        at += len(part.text)
    return Composed(text="".join(pieces), spans=tuple(spans))


def described(description: str) -> str:
    """A description as one paragraph.

    Whose name the picture carries is in the description, as the reader is asked to
    say; the reader's separate `publisher` is not added to it. Read off a tiny logo,
    it can be wrong ("Q World" for CNN's, 2026-10-03), and a wrong name in the text
    claims are found in would be checked as the picture's.
    """
    return " ".join(description.split())
