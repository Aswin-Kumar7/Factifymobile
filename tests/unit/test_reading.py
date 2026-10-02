"""What was read from an input, and the policy on what was not (contract 1.8).

The document claims are found in is built here, so its offsets are the offsets every
`input_anchor` is in: they are pinned exactly. So is the policy, because it decides
whether a person is given a verdict at all.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.extraction import reading as rd
from app.extraction.reading import (
    BLOCKING,
    CONTEXT_ONLY,
    DESCRIPTIONS,
    NOTHING_TO_CHECK_SUMMARY,
    WITHHELD_SUMMARY,
    Composed,
    Gap,
    GapCode,
    PartKind,
    Reading,
    ReadingPolicy,
    ReadPart,
    gap,
    picture_description_label,
    policy,
    served_policy,
)

pytestmark = pytest.mark.unit


def _part(kind: PartKind, text: str, label: str | None = None, **more: object) -> ReadPart:
    return ReadPart(kind=kind, text=text, route="test", label=label, **more)  # type: ignore[arg-type]


POST = "RBI to withdraw all ₹500 notes from 1 November. Share with everyone"
PICTURE = "Notes may be exchanged at any bank branch till 31 October"


def _post(*gaps: Gap, picture: str = PICTURE) -> Reading:
    return Reading(
        kind="social_post",
        platform="x",
        parts=(
            _part(PartKind.POST_TEXT, POST, "Post by Daily Updates (@daily) on X, 1 Oct 2026"),
            _part(PartKind.PICTURE_TEXT, picture, "Text in picture 1 of 1"),
            _part(PartKind.PICTURE_DESCRIPTION, "A document styled as a press release.", "Shows"),
        ),
        gaps=gaps,
    )


# ---------------------------------------------------------------------- the document


DESCRIBED = "A document styled as a press release."


class TestTheDocument:
    def test_each_checked_part_is_written_under_its_label_a_blank_line_apart(self) -> None:
        composed = _post().document()

        assert composed.text == (
            "Post by Daily Updates (@daily) on X, 1 Oct 2026:\n"
            f"{POST}\n\n"
            "Text in picture 1 of 1:\n"
            f"{PICTURE}\n\n"
            "Shows:\n"
            f"{DESCRIBED}"
        )

    def test_the_spans_are_the_parts_own_text_in_the_document(self) -> None:
        composed = _post().document()

        assert [index for index, _, _ in composed.spans] == [0, 1, 2]
        for index, start, end in composed.spans:
            assert composed.text[start:end] == _post().parts[index].text
        # The labels are Factify's words, not the post's: they sit outside every span.
        assert composed.spans[0][1] == len("Post by Daily Updates (@daily) on X, 1 Oct 2026:\n")

    def test_a_description_is_checked_under_its_label(self) -> None:
        """Since 2026-10-02 what a picture shows is checked: the claim a picture makes
        is often only in what it shows. It stays Factify's words, never the input's."""
        reading = _post()

        assert reading.parts[2].checked and reading.parts[2].described
        assert not reading.parts[0].described
        assert DESCRIBED in reading.document().text
        assert frozenset() == CONTEXT_ONLY
        assert {PartKind.PICTURE_DESCRIPTION, PartKind.VIDEO_DESCRIPTION} == DESCRIPTIONS
        assert all(_part(kind, "x").checked for kind in PartKind)

    def test_without_descriptions_the_input_s_own_words_are_left(self) -> None:
        """A wordless photograph is asked its own questions, not checked on Factify's
        account of it (`verify._to_check`)."""
        composed = _post().document(descriptions=False)

        assert DESCRIBED not in composed.text
        assert [index for index, _, _ in composed.spans] == [0, 1]
        assert composed.span_of(2) is None

    def test_a_pasted_message_composes_to_exactly_what_was_sent(self) -> None:
        """1.3 anchors are into the text as sent, line breaks and spaces included."""
        sent = "  Forwarded as received:\n\nबैंक कल बंद रहेंगे।  "
        composed = Reading(kind="text", parts=(_part(PartKind.MESSAGE, sent),)).document()

        assert composed.text == sent
        assert composed.spans == ((0, 0, len(sent)),)

    def test_a_part_with_no_text_is_left_out(self) -> None:
        """A picture read in full with no words in it is read, and adds nothing."""
        composed = _post(picture="  ").document()

        assert composed.text == (
            f"Post by Daily Updates (@daily) on X, 1 Oct 2026:\n{POST}\n\nShows:\n{DESCRIBED}"
        )
        assert [index for index, _, _ in composed.spans] == [0, 2]

    def test_a_label_ending_in_a_colon_is_not_given_a_second(self) -> None:
        reading = Reading(kind="video", parts=(_part(PartKind.TRANSCRIPT, "hello", "Said:"),))

        assert reading.document().text == "Said:\nhello"

    def test_part_at_finds_the_part_a_character_is_in(self) -> None:
        reading = _post()
        composed = reading.document()
        picture_at = composed.text.index("bank branch")

        assert reading.part_at(composed.text.index("₹500")) == 0
        assert reading.part_at(picture_at) == 1
        assert composed.part_at(picture_at) == 1
        # In a label, between parts, or past the end: Factify's words, nobody's claim.
        assert reading.part_at(0) is None
        assert reading.part_at(composed.spans[0][2]) is None
        assert reading.part_at(len(composed.text) + 5) is None

    def test_span_of_says_where_a_part_sits_or_that_it_is_not_there(self) -> None:
        composed = _post().document()

        start, end = composed.span_of(1) or (0, 0)
        assert composed.text[start:end] == PICTURE
        assert composed.span_of(3) is None  # there is no fourth part
        assert _post(picture="").document().span_of(1) is None  # nothing in it

    def test_an_empty_reading_composes_to_nothing(self) -> None:
        assert Reading(kind="link").document() == Composed(text="", spans=())


# ----------------------------------------------------------------------- the reading


class TestTheReading:
    def test_plus_adds_after_what_is_there(self) -> None:
        first = _part(PartKind.TITLE, "A headline")
        later = _part(PartKind.ARTICLE, "The body of the article.")
        missing = gap("article", GapCode.ARTICLE_TRUNCATED, "Only the opening was read.")
        reading = Reading(kind="link", parts=(first,), limits=("one",))

        grown = reading.plus(parts=(later,), gaps=(missing,), limits=("two",))

        assert grown.parts == (first, later)
        assert grown.gaps == (missing,)
        assert grown.limits == ("one", "two")
        assert reading.parts == (first,)  # frozen: the original is untouched

    def test_complete_means_no_gap_of_any_kind(self) -> None:
        assert _post().complete
        note = gap("picture_text", GapCode.FIRST_PICTURE_ONLY, "Only the first picture.")
        assert not _post(note).complete
        assert not _post(note).blocked

    def test_blocked_means_a_gap_that_could_decide_the_answer(self) -> None:
        cut = gap("post_text", GapCode.TEXT_TRUNCATED, "The post's text was cut short.")
        assert _post(cut).blocked

    @pytest.mark.parametrize(
        ("parts", "substantive"),
        [
            ((_part(PartKind.MESSAGE, "Banks shut tomorrow"),), True),
            ((_part(PartKind.MESSAGE, "Banks shut"),), False),
            # A picture read with no words in it can still be checked for its history.
            ((_part(PartKind.PICTURE_TEXT, ""),), True),
            # What a silent video shows is checked, so it is enough to check.
            ((_part(PartKind.VIDEO_DESCRIPTION, "A crowd gathers in a city square."),), True),
            ((_part(PartKind.PICTURE_DESCRIPTION, "A leopard"),), False),
            ((_part(PartKind.TITLE, "Big news"), _part(PartKind.DESCRIPTION, "Read more")), False),
            ((), False),
        ],
    )
    def test_substantive(self, parts: tuple[ReadPart, ...], substantive: bool) -> None:
        assert Reading(kind="link", parts=parts).substantive is substantive


# ------------------------------------------------------------------------ the policy


class TestThePolicy:
    BLOCKING_GAP = gap("transcript", GapCode.SPEECH_UNREAD, "The speech could not be read.")
    NOTE = gap("description", GapCode.DESCRIPTION_UNREAD, "The description was not read.")

    @pytest.mark.parametrize(
        ("gaps", "accept_partial", "expected"),
        [
            ((), False, ReadingPolicy.CHECK),
            ((), True, ReadingPolicy.CHECK),
            ((NOTE,), False, ReadingPolicy.CHECK),
            ((NOTE,), True, ReadingPolicy.CHECK),
            ((BLOCKING_GAP,), False, ReadingPolicy.WITHHOLD),
            ((BLOCKING_GAP,), True, ReadingPolicy.CHECK_PARTIALLY),
            ((NOTE, BLOCKING_GAP), False, ReadingPolicy.WITHHOLD),
            ((NOTE, BLOCKING_GAP), True, ReadingPolicy.CHECK_PARTIALLY),
        ],
    )
    def test_the_matrix(
        self, gaps: tuple[Gap, ...], accept_partial: bool, expected: ReadingPolicy
    ) -> None:
        assert policy(_post(*gaps), accept_partial=accept_partial) is expected

    @pytest.mark.parametrize("accept_partial", [False, True])
    def test_nothing_substantive_is_withheld_even_when_partial_is_accepted(
        self, accept_partial: bool
    ) -> None:
        """A headline-only page has nothing to check; "check what was read" checks nothing."""
        reading = Reading(
            kind="link",
            parts=(_part(PartKind.TITLE, "Big news"),),
            gaps=(gap("article", GapCode.HEADLINE_ONLY, "Only the headline could be read."),),
        )

        assert policy(reading, accept_partial=accept_partial) is ReadingPolicy.WITHHOLD

    def test_the_withheld_summary_is_fixed_wording_in_english_and_hindi(self) -> None:
        assert set(WITHHELD_SUMMARY) == {"en", "hi"}
        assert WITHHELD_SUMMARY["en"].startswith("Factify could not read all of this")
        assert all(sentence.strip() for sentence in WITHHELD_SUMMARY.values())
        assert set(NOTHING_TO_CHECK_SUMMARY) == {"en", "hi"}
        assert "nothing to fact-check" in NOTHING_TO_CHECK_SUMMARY["en"]


class TestThePolicyAsServed:
    """The owner's demo decision (2026-10-02): held back only when nothing that could be
    checked was read; otherwise checked on what was read, and never TRUE."""

    BLOCKING_GAP = TestThePolicy.BLOCKING_GAP
    NOTE = TestThePolicy.NOTE

    @pytest.mark.parametrize("accept_partial", [False, True])
    @pytest.mark.parametrize(
        ("gaps", "expected"),
        [
            ((), ReadingPolicy.CHECK),
            ((NOTE,), ReadingPolicy.CHECK),
            # A post whose video could not be read is checked on its words.
            ((BLOCKING_GAP,), ReadingPolicy.CHECK_PARTIALLY),
            ((NOTE, BLOCKING_GAP), ReadingPolicy.CHECK_PARTIALLY),
        ],
    )
    def test_a_blocking_gap_is_checked_past_whether_or_not_it_was_asked(
        self, gaps: tuple[Gap, ...], expected: ReadingPolicy, accept_partial: bool
    ) -> None:
        assert rd.WITHHOLD_WHEN_BLOCKED is False
        assert served_policy(_post(*gaps), accept_partial=accept_partial) is expected

    def test_a_picture_only_post_whose_picture_failed_is_held_back(self) -> None:
        reading = Reading(
            kind="social_post",
            parts=(_part(PartKind.POST_TEXT, "😱😱"),),
            gaps=(gap("picture_text", GapCode.PICTURE_UNREAD, "The picture failed."),),
        )

        assert served_policy(reading, accept_partial=True) is ReadingPolicy.WITHHOLD

    def test_package_0_s_withholding_is_one_switch_away(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rd, "WITHHOLD_WHEN_BLOCKED", True)

        assert served_policy(_post(self.BLOCKING_GAP), accept_partial=False) is (
            ReadingPolicy.WITHHOLD
        )
        assert served_policy(_post(self.BLOCKING_GAP), accept_partial=True) is (
            ReadingPolicy.CHECK_PARTIALLY
        )


class TestTheDescriptionLabels:
    @pytest.mark.parametrize(
        ("index", "total", "label"),
        [
            (1, 1, "What the picture shows (described by Factify)"),
            (2, 3, "What picture 2 of 3 shows (described by Factify)"),
        ],
    )
    def test_a_picture_s_description_says_it_is_factify_s(
        self, index: int, total: int, label: str
    ) -> None:
        assert picture_description_label(index, total) == label

    def test_the_thumbnail_labels_say_it_is_the_video_s_thumbnail(self) -> None:
        assert rd.THUMBNAIL_TEXT == "Text in the video's thumbnail"
        assert rd.THUMBNAIL_DESCRIBED.endswith("(described by Factify)")


# --------------------------------------------------------------------------- the gaps


class TestTheGaps:
    def test_every_gap_code_says_whether_it_blocks(self) -> None:
        assert set(BLOCKING) == set(GapCode)

    @pytest.mark.parametrize(
        "code",
        [
            GapCode.FIRST_PICTURE_ONLY,
            GapCode.ARTICLE_TRUNCATED,
            GapCode.DESCRIPTION_UNREAD,
            GapCode.LINKED_PAGE_UNREAD,
        ],
    )
    def test_the_notes_that_do_not_hold_the_answer_back(self, code: GapCode) -> None:
        assert gap("x", code, "detail").blocking is False

    @pytest.mark.parametrize(
        "code",
        sorted(
            set(GapCode)
            - {
                GapCode.FIRST_PICTURE_ONLY,
                GapCode.ARTICLE_TRUNCATED,
                GapCode.DESCRIPTION_UNREAD,
                GapCode.LINKED_PAGE_UNREAD,
            }
        ),
    )
    def test_everything_else_holds_it_back(self, code: GapCode) -> None:
        assert gap("x", code, "detail").blocking is True

    def test_a_reader_may_say_otherwise_for_one_gap(self) -> None:
        assert gap("x", GapCode.CUT_OFF, "detail", blocking=False).blocking is False


# ------------------------------------------------------------------------- the labels


class TestTheLabels:
    MOMENT = datetime(2026, 10, 2, 23, 59, tzinfo=UTC)

    def test_a_post_label_with_everything_known(self) -> None:
        assert (
            rd.post_label("x", name="Daily Updates", handle="@daily", published_at=self.MOMENT)
            == "Post by Daily Updates (@daily) on X, 2 Oct 2026"
        )

    @pytest.mark.parametrize(
        ("platform", "name", "handle", "when", "expected"),
        [
            ("instagram", None, "desi.news", None, "Post by @desi.news on Instagram"),
            ("youtube", "Taaza Khabar", None, None, "Post by Taaza Khabar on YouTube"),
            ("facebook", None, None, MOMENT, "Post on Facebook, 2 Oct 2026"),
            (None, None, None, None, "Post"),
        ],
    )
    def test_a_post_label_says_what_is_known(
        self,
        platform: str | None,
        name: str | None,
        handle: str | None,
        when: datetime | None,
        expected: str,
    ) -> None:
        assert rd.post_label(platform, name=name, handle=handle, published_at=when) == expected

    def test_a_quoted_post_label(self) -> None:
        assert rd.post_label("x", handle="source", quoted=True) == "Quoted post by @source on X"

    def test_picture_labels(self) -> None:
        assert rd.picture_text_label(2, 3) == "Text in picture 2 of 3"
        assert rd.picture_text_label(1, 1) == "Text in the picture"

    def test_a_linked_article_names_its_site(self) -> None:
        assert rd.linked_article_label("www.thehindu.com") == "Linked article (thehindu.com)"
        assert rd.linked_article_label(None) == "Linked article"

    def test_dates_do_not_follow_the_server_locale(self) -> None:
        assert [rd.label_date(datetime(2026, month, 1)) for month in (1, 6, 12)] == [
            "1 Jan 2026",
            "1 Jun 2026",
            "1 Dec 2026",
        ]
        assert rd.label_date(None) is None

    def test_the_fixed_labels(self) -> None:
        assert (rd.SAID_IN_VIDEO, rd.TEXT_IN_VIDEO) == (
            "Said in the video",
            "Text shown in the video",
        )
        assert (rd.TITLE, rd.DESCRIPTION, rd.ARTICLE) == ("Title", "Description", "Article")


def test_the_module_is_pure() -> None:
    """No input or output: it imports nothing but the standard library's data types."""
    source = Path(rd.__file__).read_text(encoding="utf-8")
    imported = {
        (node.module or "").split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert imported <= {"__future__", "dataclasses", "datetime", "enum", "typing"}
