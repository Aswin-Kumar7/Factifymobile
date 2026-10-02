"""What was read from an input, part by part, and what could not be (contract 1.8).

A link, a social post, a picture, a PDF or a video is read before anything in it is
checked, and the reading can fall short: a page that gives only its headline, a post
whose caption is cut at "… more", a video whose speech could not be heard. Until now
a short reading was checked as if it were the whole thing, and an answer about half a
post read exactly like an answer about all of it. This module is the record that
keeps the two apart.

A `Reading` holds the parts that were read, in the order a person meets them (the
post, then its pictures, then its video), and the gaps: what could not be read, and
whether that gap is large enough to hold the verdict back. `document()` joins the
parts claims are found in into the one text extraction reads, and says where each
part sits in it, so a claim's `input_anchor` can be traced to the part it came from.

A model's description of what a picture or a video shows is Factify's own words, never
evidence: nothing it says is taken as proof of anything. It is still part of the
document, under a label that says it is Factify's ("What the picture shows (described
by Factify)"), because the claim a picture or a video makes is often only in what it
shows - eight leaders in one selfie, a leopard in a village street - and a claim left
unread there was never checked (2026-10-02). The extraction prompt is told what those
labels mean (`app/extraction/llm.py`).

Pure: no input or output of any kind. The readers that fill a `Reading` live in
their own modules.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Literal

# ---------------------------------------------------------------------------- parts


class PartKind(StrEnum):
    """What a part of the reading is. Sent to the clients as `input_read.parts[].kind`."""

    # A pasted or forwarded message.
    MESSAGE = "message"
    # A social post's own words, and a post it quotes.
    POST_TEXT = "post_text"
    QUOTED_POST = "quoted_post"
    # A page's or a video's title and description, and an article's body.
    TITLE = "title"
    DESCRIPTION = "description"
    ARTICLE = "article"
    # An article a post or a message links to, read as part of it.
    LINKED_ARTICLE = "linked_article"
    # The words in a picture, and a model's account of what the picture shows.
    PICTURE_TEXT = "picture_text"
    PICTURE_DESCRIPTION = "picture_description"
    # What is said in a video, the words shown on its frames, and what it shows.
    TRANSCRIPT = "transcript"
    ON_SCREEN_TEXT = "on_screen_text"
    VIDEO_DESCRIPTION = "video_description"
    # A PDF's text, read from its text layer or its scanned pages.
    DOCUMENT_TEXT = "document_text"


# Factify's own account of what a picture or a video shows, not the input's words.
# Checked, under a label that says whose words they are, but never counted as what
# the input itself says (`app/api/verify.py` `_authored`), and left out of the
# document of a photograph with no words of its own (`Reading.document`).
DESCRIPTIONS: frozenset[PartKind] = frozenset(
    {PartKind.PICTURE_DESCRIPTION, PartKind.VIDEO_DESCRIPTION}
)

# Parts that are shown and never checked. Empty since 2026-10-02: the descriptions
# were here, and the claim a picture or a video made only in what it shows was never
# checked. Kept so a part kind can be made shown-only again in one place.
CONTEXT_ONLY: frozenset[PartKind] = frozenset()


class GapCode(StrEnum):
    """Why part of an input could not be read. The clients word each in their language.

    `detail` on the gap is the English fallback for a code a client does not know.
    """

    # A link gave its headline and summary only: a search listing, or a page behind a
    # login, consent or JavaScript wall.
    HEADLINE_ONLY = "headline_only"
    # A post's text was cut short: an X note tweet, an Instagram "… more" caption.
    TEXT_TRUNCATED = "text_truncated"
    # The post is deleted, protected or a story, or the platform shows it only to
    # someone signed in.
    POST_UNAVAILABLE = "post_unavailable"
    LOGIN_REQUIRED = "login_required"
    # A platform or a kind of post Factify does not read (Facebook, for now).
    NOT_SUPPORTED = "not_supported"
    # A post's picture could not be downloaded, or reading it failed. A picture read
    # in full that simply has no words in it is not a gap.
    PICTURE_UNREAD = "picture_unread"
    # The video could not be downloaded, or reading it failed.
    VIDEO_UNREAD = "video_unread"
    # The speech in a video could not be read: the reader failed or is not available.
    SPEECH_UNREAD = "speech_unread"
    # Reading stopped before the end: a video longer than the read cap, or a picture
    # or PDF whose reading ran out of room.
    CUT_OFF = "cut_off"
    # A scanned PDF has more pages than were read.
    PAGES_UNREAD = "pages_unread"
    # The video is too large to download, even at its lowest quality.
    TOO_LARGE = "too_large"
    # A video, sent as a quick check: videos are read only in a background check.
    NEEDS_BACKGROUND = "needs_background"
    # The reader this input needs is not set up on this server.
    READER_UNAVAILABLE = "reader_unavailable"
    # An album, of which the platform's public view shows the first picture only.
    FIRST_PICTURE_ONLY = "first_picture_only"
    # An article longer than what is read of it; its opening was read.
    ARTICLE_TRUNCATED = "article_truncated"
    # A YouTube video's description could not be read.
    DESCRIPTION_UNREAD = "description_unread"
    # An article a post or a message links to gave its headline only, and was left
    # out of what was checked.
    LINKED_PAGE_UNREAD = "linked_page_unread"
    # A submitted link whose page could not be read at all: not its article, not
    # even its headline.
    PAGE_UNREAD = "page_unread"


# Whether each gap, by default, holds the verdict back. A blocking gap is one where
# what is missing could be the very claim that decides the answer: the rest of a cut
# caption, the speech in a video. A non-blocking one leaves out something the answer
# does not rest on: the tail of a long article whose opening was read, an album's
# later pictures, a video's description. A reader may still say otherwise for a
# particular gap; this is the table the plan sets out, held in one place.
BLOCKING: dict[GapCode, bool] = {
    GapCode.HEADLINE_ONLY: True,
    GapCode.TEXT_TRUNCATED: True,
    GapCode.POST_UNAVAILABLE: True,
    GapCode.LOGIN_REQUIRED: True,
    GapCode.NOT_SUPPORTED: True,
    GapCode.PICTURE_UNREAD: True,
    GapCode.VIDEO_UNREAD: True,
    GapCode.SPEECH_UNREAD: True,
    GapCode.CUT_OFF: True,
    GapCode.PAGES_UNREAD: True,
    GapCode.TOO_LARGE: True,
    GapCode.NEEDS_BACKGROUND: True,
    GapCode.READER_UNAVAILABLE: True,
    GapCode.FIRST_PICTURE_ONLY: False,
    GapCode.ARTICLE_TRUNCATED: False,
    GapCode.DESCRIPTION_UNREAD: False,
    GapCode.LINKED_PAGE_UNREAD: False,
    GapCode.PAGE_UNREAD: True,
}


@dataclass(frozen=True, slots=True)
class ReadPart:
    """One thing read from the input, in the words it was read in.

    `route` says how it was read, so a misread can be traced to the reader that made
    it: x.syndication, x.oembed, instagram.embed, youtube.oembed, gemini.youtube,
    whisper, frames.ocr, ocr.local, ocr.hosted, fetched, vendor_extract,
    headline_summary, search_listing, pdf.text, pdf.ocr or pasted.

    `label` heads the part in the document ("Text in picture 1 of 2"); a part with no
    label is written bare, which keeps a pasted message's offsets exactly those of
    the text as it was sent.
    """

    kind: PartKind
    text: str
    route: str
    label: str | None = None
    # False when this part itself was read only in part (a cut-off transcript); the
    # gap that says why is in `Reading.gaps`.
    complete: bool = True
    note: str | None = None
    # The ThumbnailStore key of the picture this part was read from, so the client
    # shows it from our own address and never loads the platform's.
    media_key: str | None = None
    # For speech: how much of the video was heard, of how long it is.
    seconds_read: float | None = None
    seconds_total: float | None = None
    language: str | None = None

    @property
    def checked(self) -> bool:
        """Whether claims are found in this part. Every kind is, descriptions included."""
        return self.kind not in CONTEXT_ONLY

    @property
    def described(self) -> bool:
        """Factify's description of what a picture or video shows, not the input's words."""
        return self.kind in DESCRIPTIONS


@dataclass(frozen=True, slots=True)
class Gap:
    """Something that could not be read, and whether it holds the verdict back.

    `part` names what is missing: a part kind ("transcript", "picture_text") or the
    thing that has no part at all ("post", "video", "linked_page"). `detail` is one
    English sentence, the fallback for a client that does not know `code`.
    """

    part: str
    code: GapCode
    detail: str
    blocking: bool


def gap(part: str, code: GapCode, detail: str, *, blocking: bool | None = None) -> Gap:
    """A gap, blocking or not as `BLOCKING` says unless the reader knows better."""
    return Gap(
        part=part,
        code=code,
        detail=detail,
        blocking=BLOCKING[code] if blocking is None else blocking,
    )


# ------------------------------------------------------------------------- document

# Between two parts of the document: a blank line, so a label never runs into the
# end of the part before it.
_BETWEEN = "\n\n"


@dataclass(frozen=True, slots=True)
class Composed:
    """The document claims are extracted from, and where each part sits in it.

    `spans` holds (part index, start, end): the index into `Reading.parts`, and the
    characters of that part's text - its label excluded - in `text`. These are the
    offsets a claim's `input_anchor` is in.
    """

    text: str
    spans: tuple[tuple[int, int, int], ...] = ()

    def part_at(self, offset: int) -> int | None:
        """The index of the part whose text holds this character, or None.

        None for a character in a label or between parts: Factify wrote those.
        """
        for index, start, end in self.spans:
            if start <= offset < end:
                return index
        return None

    def span_of(self, index: int) -> tuple[int, int] | None:
        """Where a part's text sits in the document; None when it is not in it."""
        for part, start, end in self.spans:
            if part == index:
                return start, end
        return None


# ----------------------------------------------------------------------------- reading

ReadingKind = Literal["text", "link", "social_post", "image", "pdf", "video"]


@dataclass(frozen=True, slots=True)
class Reading:
    """Everything read from one input, what could not be, and who it came from."""

    kind: ReadingKind
    parts: tuple[ReadPart, ...] = ()
    gaps: tuple[Gap, ...] = ()
    # For a link or a post: where it is and who posted it, as the platform says.
    platform: str | None = None
    url: str | None = None
    author: str | None = None
    handle: str | None = None
    published_at: datetime | None = None
    # Limits that are not about reading, said beside it: "YouTube does not let
    # Factify download the video, so its AI, face-swap and voice checks did not run."
    limits: tuple[str, ...] = ()

    def plus(
        self,
        *,
        parts: tuple[ReadPart, ...] = (),
        gaps: tuple[Gap, ...] = (),
        limits: tuple[str, ...] = (),
    ) -> Reading:
        """This reading with more parts, gaps or limits after its own."""
        return replace(
            self,
            parts=(*self.parts, *parts),
            gaps=(*self.gaps, *gaps),
            limits=(*self.limits, *limits),
        )

    @property
    def complete(self) -> bool:
        """Everything was read: no gap of any kind."""
        return not self.gaps

    @property
    def blocked(self) -> bool:
        """Something that could decide the answer was not read."""
        return any(item.blocking for item in self.gaps)

    @property
    def substantive(self) -> bool:
        """Enough was read to check anything at all.

        A checked part of three words or more - what a picture or a video shows
        included, as it is checked - or a picture read in full: a picture with no
        words in it can still be checked for where it appeared before.
        """
        return any(
            part.kind is PartKind.PICTURE_TEXT or (part.checked and _words(part.text) >= 3)
            for part in self.parts
        )

    def document(self, *, descriptions: bool = True) -> Composed:
        """The checked parts as one text: each "<label>:\\n<text>", a blank line apart.

        A part with no label is written bare, and one with no text is left out. A
        pasted message on its own therefore composes to exactly the text that was
        sent, and its anchors stay where 1.3 put them. Without `descriptions`, what a
        picture or a video shows is left out too: the input's own words alone.
        """
        pieces: list[str] = []
        spans: list[tuple[int, int, int]] = []
        at = 0
        for index, part in enumerate(self.parts):
            if not part.checked or not part.text.strip():
                continue
            if not descriptions and part.described:
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

    def part_at(self, offset: int) -> int | None:
        """The part a character of `document()` belongs to, or None."""
        return self.document().part_at(offset)


def _words(text: str) -> int:
    return len(text.split())


# ------------------------------------------------------------------------------ policy


class ReadingPolicy(StrEnum):
    """What is done with a reading: check it, check what was read, or hold it back."""

    CHECK = "check"
    # Something that could decide the answer was not read, and the person asked to
    # check what was ("Check what was read"). The answer can then never be TRUE.
    CHECK_PARTIALLY = "check_partially"
    # Not checked, and nothing spent finding claims: the answer says what could not
    # be read and how to send it instead.
    WITHHOLD = "withhold"


def policy(reading: Reading, *, accept_partial: bool) -> ReadingPolicy:
    """Whether a reading is checked, checked as partial, or held back.

    Held back by default when something that could decide the answer was not read:
    a verdict on the half of a post that could be read reads exactly like one on the
    whole post, and the half not read may be the claim itself.
    """
    if not reading.substantive:
        return ReadingPolicy.WITHHOLD
    if reading.blocked:
        return ReadingPolicy.CHECK_PARTIALLY if accept_partial else ReadingPolicy.WITHHOLD
    return ReadingPolicy.CHECK


# Whether a reading with a blocking gap is held back when the person did not ask to
# check what was read. The owner's decision for the 3 October demo (2026-10-02): be
# conservative - hold an answer back only when nothing that could be checked was read
# at all (a picture-only post whose picture failed), and otherwise check what was read
# and say so (`CHECK_PARTIALLY`: never TRUE, the gaps shown). A post whose video could
# not be downloaded is still checked on its words. True withholds as package 0
# designed, with "Check what was read" to go on.
WITHHOLD_WHEN_BLOCKED = False


def served_policy(reading: Reading, *, accept_partial: bool) -> ReadingPolicy:
    """The policy `/v1/verify` applies: `policy`, under `WITHHOLD_WHEN_BLOCKED`."""
    return policy(reading, accept_partial=accept_partial or not WITHHOLD_WHEN_BLOCKED)


# What a withheld answer says, for a client that shows only `summary`. Fixed
# sentences, like the pipeline's `_UNREPORTED`, never a model's words.
WITHHELD_SUMMARY: dict[str, str] = {
    "en": (
        "Factify could not read all of this, so it has not given a verdict. Paste the "
        "text, upload the picture or video, or ask Factify to check only what it could read."
    ),
    "hi": (
        "Factify इसे पूरा नहीं पढ़ पाया, इसलिए इस पर कोई फ़ैसला नहीं दिया गया है। इसका "
        "टेक्स्ट चिपकाएँ, तस्वीर या वीडियो अपलोड करें, या Factify से सिर्फ़ उतना जाँचने को "
        "कहें जितना वह पढ़ पाया।"
    ),
}


# ------------------------------------------------------------------------------ labels
#
# The words that head each part, written here once so every reader labels the same
# way and the extraction prompt can be told what they are.

_PLATFORM_NAMES = {
    "x": "X",
    "instagram": "Instagram",
    "youtube": "YouTube",
    "facebook": "Facebook",
}

# English month names, not strftime's %b, which follows the server's locale.
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

SAID_IN_VIDEO = "Said in the video"
TEXT_IN_VIDEO = "Text shown in the video"
TITLE = "Title"
DESCRIPTION = "Description"
ARTICLE = "Article"


def platform_name(platform: str | None) -> str | None:
    """A platform as people write it: "x" is X, "youtube" is YouTube."""
    if not platform:
        return None
    return _PLATFORM_NAMES.get(platform.casefold(), platform)


def label_date(moment: datetime | None) -> str | None:
    """A date as "2 Oct 2026"."""
    if moment is None:
        return None
    return f"{moment.day} {_MONTHS[moment.month - 1]} {moment.year}"


def post_label(
    platform: str | None,
    *,
    name: str | None = None,
    handle: str | None = None,
    published_at: datetime | None = None,
    quoted: bool = False,
) -> str:
    """ "Post by {name} (@{handle}) on {Platform}, {d Mon yyyy}", with what is known."""
    handle = handle.lstrip("@") if handle else None
    if name and handle:
        who = f"{name} (@{handle})"
    elif name or handle:
        who = name or f"@{handle}"
    else:
        who = None
    label = "Quoted post" if quoted else "Post"
    if who:
        label += f" by {who}"
    if shown := platform_name(platform):
        label += f" on {shown}"
    if day := label_date(published_at):
        label += f", {day}"
    return label


# What an answer with no claims in it says when everything was read: nothing in it is
# something sources could confirm or refute. Fixed sentences, never a model's words.
NOTHING_TO_CHECK_SUMMARY: dict[str, str] = {
    "en": (
        "Factify read all of this and found nothing in it that sources could confirm "
        "or refute, so there is nothing to fact-check."
    ),
    "hi": (
        "Factify ने इसे पूरा पढ़ा, पर इसमें ऐसा कोई दावा नहीं मिला जिसे स्रोतों से जाँचा जा "
        "सके, इसलिए इसमें जाँचने लायक कुछ नहीं है।"
    ),
}


def picture_text_label(index: int, total: int) -> str:
    """ "Text in picture 2 of 3"; "Text in the picture" when there is only one."""
    if total <= 1:
        return "Text in the picture"
    return f"Text in picture {index} of {total}"


# Says a description is Factify's own: the extraction prompt knows this mark.
_DESCRIBED_BY = "(described by Factify)"


def picture_description_label(index: int, total: int) -> str:
    """ "What picture 2 of 3 shows (described by Factify)"; "What the picture shows
    (described by Factify)" when there is only one."""
    if total <= 1:
        return f"What the picture shows {_DESCRIBED_BY}"
    return f"What picture {index} of {total} shows {_DESCRIBED_BY}"


# A YouTube video's thumbnail, read as a picture: YouTube lets no server download the
# video itself, and the thumbnail is often where a fake Short's claim is shown.
THUMBNAIL_TEXT = "Text in the video's thumbnail"
THUMBNAIL_DESCRIBED = f"What the video's thumbnail shows {_DESCRIBED_BY}"


def linked_article_label(host: str | None) -> str:
    """ "Linked article (thehindu.com)"."""
    host = (host or "").removeprefix("www.")
    return f"Linked article ({host})" if host else "Linked article"
