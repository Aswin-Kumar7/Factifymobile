"""Claim extraction (M20).

Turns a document into atomic, anchored, checkable claims. The model's part is
segmentation and labelling; everything that decides anything happens elsewhere.

The gate that matters here is not "did we get claims" but **"can every claim be traced
back to real text"**. A model can hallucinate a sentence the document does not
contain, and a document can instruct the model to produce one. Both are caught by the
same check: the proposed span is verified against the source, and a claim whose anchor
does not resolve is discarded rather than stored.

That check is why a successful injection cannot manufacture a claim out of nothing —
it would have to also make the text it invented appear in the document.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol

from app.cache.service import CacheService
from app.domain.claim import Claim, ClaimAnchor
from app.domain.enums import Importance
from app.domain.typography import fold, fold_with_positions
from app.extraction.llm import EXTRACTOR_VERSION, ExtractionOutcome, ProposedClaim
from app.observability.logging import event

logger = logging.getLogger("factify.claims")


class Extractor(Protocol):
    """What the pipeline needs from a model client.

    A protocol rather than a base class, so a test double is a first-class
    implementation rather than a degraded subclass of the real one.
    """

    async def extract_claims(self, text: str) -> ExtractionOutcome: ...


# How much of a proposed claim must appear verbatim in the source before the anchor is
# believed. Not 100%: extraction legitimately normalises whitespace and drops a
# trailing clause. Low enough to survive that, high enough that an invented sentence
# cannot pass.
_ANCHOR_MATCH_THRESHOLD = 0.6

# A message this short whose claim is not found in it word for word: the sentence of
# the message the claim reads stands as the claim (`ClaimPipeline._verify`).
_SHORT_MESSAGE = 600
# Where one sentence of a message ends and the next begins: a line break, a full stop
# (a danda, a bar) and a space, or a colon opening a quotation - in 'venukolangara on
# August 13, 2026: "An old photograph ...' who posted comes first, then the caption.
_SENTENCE_BREAK = re.compile(r"\n|(?<=[.!?।|])\s+|(?<=:)\s*(?=[\"“])")
# How much of a discarded claim the log keeps: enough to tell which claim it was.
_LOGGED_CLAIM = 160
_RANK = {
    Importance.HEADLINE: 0,
    Importance.MAIN_THESIS: 1,
    Importance.SUPPORTING_DETAIL: 2,
    Importance.BACKGROUND: 3,
}


@dataclass(frozen=True, slots=True)
class ExtractedClaims:
    """Verified claims, plus everything discarded and why."""

    claims: tuple[Claim, ...] = ()
    model_id: str | None = None
    from_cache: bool = False
    reason: str | None = None
    discarded: tuple[str, ...] = ()
    injection_findings: tuple[str, ...] = ()
    # Set when the claims came from less than the whole source: a linked page whose
    # article could not be read, checked on its published headline and summary.
    partial_source: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.reason is None


def _normalise(text: str) -> str:
    # Typography folded as well as case and spacing. Without it a newsonair.gov.in
    # article produced six claims and all six were discarded as "not found in source",
    # the same failure the citation quote gate had before it learned the same rule.
    return fold(text)


class _Document:
    """A source as every claim checked against it reads it, built once per document.

    Folding a source and reading it as words took two passes over it for every claim
    not found word for word, and two more for each discard's reason, all on the event
    loop: a 50-page PDF with seven claims held every other check back for seconds
    (2026-10-02 review). The words are read only when a claim needs them.
    """

    __slots__ = ("_read", "folded", "origin", "source")

    def __init__(self, source: str) -> None:
        self.source = source
        self.folded, self.origin = fold_with_positions(source)
        self._read: _Source | None = None

    @property
    def read(self) -> _Source:
        if self._read is None:
            self._read = _Source.of(self.source, self.folded)
        return self._read


def _locate(
    claim_text: str, source: str, document: _Document | None = None
) -> tuple[int, int] | None:
    """Find the claim in the source, returning character offsets in `source` itself.

    Exact match first, then a longest-run fallback for the common case where the
    model tidied punctuation, then the claim's facts (`_locate_by_coverage`). If none
    finds it, the claim does not correspond to the document and is not stored.

    The search runs in folded text, whose whitespace is flattened; the offsets are
    carried back to the source's own characters, so a claim's location points at
    what the person sent - the app underlines it there - not at a tidied copy.
    """
    document = document or _Document(source)
    haystack = document.folded
    needle = _normalise(claim_text)
    if not needle:
        return None
    position = haystack.find(needle)
    if position != -1:
        found: tuple[int, int] | None = (position, position + len(needle))
    else:
        # Anything short of the claim word for word must give no number the source
        # does not: a claim keeping most of a sentence's words can still change the
        # one figure that matters.
        read = document.read
        numbers, names = _not_in_source(claim_text, _words(claim_text), read)
        if numbers:
            return None
        found = _longest_run(needle, haystack)
        if found is None and not names:
            # Matched by its facts, a claim may add plain words of its own, so it must
            # name no one the source does not. Not asked of a run of most of the
            # claim's own words: there the model's "the Central Government" for a
            # forward's "Central Govt", or "the Indian Army" for an article's "the
            # army", has always been kept, and a check run before it threw such
            # claims away from any text longer than a short message (2026-10-02).
            found = _locate_by_coverage(claim_text, read)
    if found is None:
        return None
    start, end = found
    return document.origin[start], document.origin[end - 1] + 1


def _longest_run(needle: str, haystack: str) -> tuple[int, int] | None:
    """The longest run of the claim's words in the folded source, when it is most of
    the claim, or None."""
    # A paraphrase keeps most of its subject and object intact; an invention does not.
    words = needle.split()
    for length in range(len(words), 2, -1):
        for start in range(len(words) - length + 1):
            fragment = " ".join(words[start : start + length])
            found = haystack.find(fragment)
            if found != -1 and length / len(words) >= _ANCHOR_MATCH_THRESHOLD:
                return found, found + len(fragment)

    return None


# Words that carry no fact of their own, so a claim is matched on the ones that do.
# "per cent" and "Rs" go with a number, which is matched on its own.
_FUNCTION_WORDS = frozenset(
    """a an the is are was were be been being has have had do does did will would shall
    should can could may might must and or but nor so yet of in on at to for from by with
    about as into onto over under after before during than that this these those which
    who whom whose what when where why how it its their there they them he she his her
    him we our you your i me my not no also just only very more most such both each
    said says say according per cent percent rs inr""".split()
    # The same in Hindi: postpositions, auxiliaries, and the "said that" a quote card's
    # claim adds ("गौरव भाटिया ने कहा कि ...") to words the card carries bare.
    + """का की के को में से पर और है हैं था थे थी हो हुआ हुई हुए ने कि कहा यह ये वह वे
    इस उस एक भी तो ही गया गई गए किया द्वारा लिए""".split()
)
_MONTHS = {
    "january": "jan", "february": "feb", "march": "mar", "april": "apr", "june": "jun",
    "july": "jul", "august": "aug", "september": "sep", "sept": "sep", "october": "oct",
    "november": "nov", "december": "dec",
}  # fmt: skip
# Written straight after a number, part of how it is written rather than a word:
# "11th", "1980s". And the short forms of a scale: "£900m" is "900 million".
_NUMBER_ENDINGS = frozenset({"st", "nd", "rd", "th", "s"})
_SCALES = {"m": "million", "mn": "million", "bn": "billion", "cr": "crore"}
# Short forms a forward writes for a word a claim spells out: "Central Govt" is the
# claim's "the Central Government".
_ABBREVIATIONS = {
    "govt": "government", "gov": "government", "dept": "department", "univ": "university",
    "intl": "international", "natl": "national", "corp": "corporation", "dist": "district",
    "pvt": "private", "rly": "railway", "hosp": "hospital",
}  # fmt: skip

# Share of a claim's fact-bearing words that one short stretch of the source must hold,
# with every number among them.
_COVERAGE_THRESHOLD = 0.8
# The same for a claim that adds a few plain words of its own (`_locate_by_coverage`):
# a lower share of all its words, and half of those that are neither a name nor a number.
_ADDED_WORDS_COVERAGE = 0.6
_YEAR = re.compile(r"(19|20)\d\d")


# How much of a word in an Indian script is its stem, in characters (code points).
_STEM = 5
# Joiners that shape a script's letters but carry no meaning of their own, and the
# soft hyphen, which only marks where a word may break.
_JOINERS = str.maketrans("", "", "‌‍­")
# Within a word, what joins two words or two numbers: hyphens and dashes of every kind
# ("Pakistan-ISI-linked", "13–65", "₹50,000–₹90,000") and a slash ("30/09/2026").
_JOINED = re.compile(r"[-‐‑–—―−/]+")
# What a word may be wrapped in: punctuation, quotation marks, brackets, and the
# currency and percent signs around a number, which is matched on its digits.
_WRAPPING = ".,;:!?()[]{}<>\"'‘’“”«»।|*#@…&+=~_`^₹$£€¥%"
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# A date written in numbers, day first as India writes it: "15.03.2027", "01/10/2026".
_DATE = re.compile(r"(\d{1,2})([./-])(\d{1,2})\2(\d{4}|\d{2})")
_MONTH_NUMBERS = dict(enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1))
# A Latin word, or a number, inside a word: "than900" is "than" and "900", the way a
# caption track runs a number into the word before it.
_PIECE = re.compile(r"\d+(?:[.,]\d+)*|[A-Za-z]+(?:'[A-Za-z]+)*")


@dataclass(frozen=True, slots=True)
class _Word:
    """A fact-bearing word, where it sits, whether it was written with a capital, and
    whether in capitals throughout, as an acronym is ("ISI", "MP")."""

    word: str
    start: int
    end: int
    capital: bool = False
    acronym: bool = False


def _number(digits: str) -> str:
    """A number as one form: grouping commas dropped - "2,36,013" and "236,013" are
    the same number - digits in any script written as 0-9, and no zero that changes
    nothing: "09 October" is the claim's "9 October", "6.50%" its "6.5%"."""
    number = "".join(str(unicodedata.decimal(ch, ch)) for ch in digits.replace(",", ""))
    whole, _, fraction = number.partition(".")
    whole, fraction = whole.lstrip("0") or "0", fraction.rstrip("0")
    return f"{whole}.{fraction}" if fraction else whole


def _numbers(written: str) -> list[str]:
    """The numbers a written number is matched by: itself, or a date's parts.

    "30.09.2026" is a date, not one number: an RBI notice "dated 30.09.2026" was not
    the claim's "30 September 2026", and its 2026 was "not in the source" (2026-10-02
    review). Indian circulars and gazettes write dates this way.
    """
    if written.count(".") >= 2:
        return [_number(part) for part in written.split(".") if part]
    return [_number(written)]


def _stem(word: str) -> str:
    """A plain English ending trimmed, so "arrested" matches "arrests", "declared"
    "declare" and "crores" "crore"."""
    if len(word) <= 4:
        return word
    if word.endswith("ing"):
        word = word[:-3]
    elif word.endswith("ed"):
        word = word[:-2]
    elif word.endswith("ies"):
        word = word[:-3] + "y"
    elif word.endswith("es") and word[:-2].endswith(("s", "x", "z", "ch", "sh")):
        word = word[:-2]
    elif word.endswith("s") and not word.endswith(("ss", "us", "is")):
        word = word[:-1]
    if len(word) > 4 and word.endswith("e"):
        word = word[:-1]
    return word


# A number a source spells out, as the claim may give it in digits: "seven men" in an
# article is the claim's "7 men". Only the source's word stands for the digits - a
# claim's own "seven", counting names the post lists, stays a word, so it is never a
# number the source does not give.
_NUMBER_WORDS = {
    _stem(word): str(value)
    for value, word in [
        *enumerate(
            """zero one two three four five six seven eight nine ten eleven twelve thirteen
            fourteen fifteen sixteen seventeen eighteen nineteen twenty""".split()
        ),
        *zip(
            range(30, 100, 10),
            "thirty forty fifty sixty seventy eighty ninety".split(),
            strict=True,
        ),
    ]
}


def _words(text: str) -> list[_Word]:
    """The fact-bearing words of a text, each with the span of what it came from.

    No function words, months abbreviated, a plain suffix trimmed. Words joined by a
    hyphen, a dash or a slash are words apart, a number is its digits wherever it is
    written, and a number run into a word is a word and a number: the anchor check
    threw away "a 10-time champion" against a caption's "10 time", "₹50,000 to
    ₹90,000" against "(₹50,000-₹90,000)", whose digits it read as one number, and
    the £900m at the heart of a BBC report against its caption's "more than900
    million pounds" (2026-10-02).

    In the Indian scripts a word carries its case ending: Kannada "2024ರ" (of 2024)
    and "2024ರಲ್ಲಿ" (in 2024), "ಆಸ್ಟ್ರೇಲಿಯಾವನ್ನು" and "ಆಸ್ಟ್ರೇಲಿಯಾ". gpt-5.6-luna split
    "India won the 2024 T20 World Cup and beat Australia in the final" into two claims
    and wrote the second in full, and it was discarded as not in the text (2026-09-28).
    So a number there is its digits and a word its first few letters.
    """
    found: list[_Word] = []
    for token in re.finditer(r"\S+", text):
        start, end = token.span()
        date = _DATE.fullmatch(token.group().strip(_WRAPPING))
        if date:
            # Its day, month and year, and the month by name: a circular's "postponed
            # to 15.03.2027" is the claim's "to 15 March 2027".
            day, month, year = (_number(part) for part in date.group(1, 3, 4))
            found.extend(_Word(number, start, end) for number in (day, month, year))
            if int(month) in _MONTH_NUMBERS:
                found.append(_Word(_MONTH_NUMBERS[int(month)], start, end))
            continue
        for part in _JOINED.split(token.group().translate(_JOINERS)):
            part = part.strip(_WRAPPING).replace("’", "'")
            if not part:
                continue
            if not part.isascii():
                if any(ch.isdigit() for ch in part):
                    found.extend(
                        _Word(number, start, end)
                        for written in _NUMBER.findall(part)
                        for number in _numbers(written)
                    )
                elif any(ch.isalpha() for ch in part) and part.lower() not in _FUNCTION_WORDS:
                    found.append(_Word(part.lower()[:_STEM], start, end))
                continue
            after_number = -1
            for piece in _PIECE.finditer(part):
                written = piece.group()
                if written[0].isdigit():
                    found.extend(_Word(number, start, end) for number in _numbers(written))
                    after_number = piece.end()
                    continue
                if len(written) > 2 and written[-1] == "s" and written[:-1].isupper():
                    # An acronym's plural, "SUVs" for the "(SUV)" a report writes.
                    written = written[:-1]
                word = written.lower()
                if piece.start() == after_number:
                    if word in _NUMBER_ENDINGS:
                        continue
                    if word in _SCALES:
                        # Stemmed like the word written out: "5cr" is "5 crores".
                        found.append(_Word(_stem(_SCALES[word]), start, end))
                        continue
                word = word.removesuffix("'s").replace("'", "")
                if not word or word in _FUNCTION_WORDS:
                    continue
                word = _stem(_MONTHS.get(word) or _ABBREVIATIONS.get(word, word))
                found.append(
                    _Word(
                        word,
                        start,
                        end,
                        capital=written[0].isupper(),
                        acronym=len(written) > 1 and written.isupper(),
                    )
                )
    return found


def _fact_words(text: str) -> list[str]:
    """The fact-bearing words of a text (`_words`), without where they sit."""
    return [word.word for word in _words(text)]


def _is_number(word: str) -> bool:
    return word[:1].isdigit()


# The longest acronym looked for: "ISRO", "NABARD", rarely more.
_ACRONYM_LETTERS = 6

# Two letters stand for too much to be read as any name with those initials: "MP" is
# Madhya Pradesh, a Member of Parliament or Mumbai Police, and "us" and "up" are words.
# A claim's "Mumbai Police" was taken as written by a post's "Local MP", and its
# "United States" by "officials told us" (2026-10-02 review). So two letters stand
# only for what they say in the news without a doubt - "AP" and "HP" are not here,
# and "MP" is only a Member of Parliament.
_TWO_LETTERS = {
    initials: frozenset({frozenset(_stem(word) for word in name.split())})
    for initials, name in {
        "pm": "prime minister", "cm": "chief minister", "up": "uttar pradesh",
        "mp": "member parliament", "us": "united states", "uk": "united kingdom",
        "un": "united nations", "sc": "supreme court", "hc": "high court",
    }.items()
}  # fmt: skip
# Endings that make a place its people: "Indian" for India, "Pakistani", "Iranian".
_PEOPLE_ENDINGS = ("ian", "n", "i")


def _stands_for(initials: str, words: frozenset[str]) -> bool:
    """Whether an acronym can stand for these words."""
    return len(initials) > 2 or words in _TWO_LETTERS.get(initials, frozenset())


def _runs(words: list[_Word]) -> Iterator[tuple[str, frozenset[str]]]:
    """Every stretch of two to six capitalised words in a row, with its initials.

    Six, so a page set in capitals is not read as one name thousands of words long.
    """
    run: list[str] = []
    for word in [*words, None]:
        if word is not None and word.capital and not _is_number(word.word):
            run.append(word.word)
            continue
        for first in range(len(run)):
            for last in range(first + 2, min(len(run), first + _ACRONYM_LETTERS) + 1):
                part = run[first:last]
                yield "".join(name[0] for name in part), frozenset(part)
        run = []


def _expansions(words: list[_Word]) -> dict[str, frozenset[str]]:
    """The acronyms a text spells out, by their initials: "Pakistan's Inter-Services
    Intelligence" spells out the ISI, and "Prime Minister" the PM."""
    spelled: dict[str, frozenset[str]] = {}
    for initials, part in _runs(words):
        spelled.setdefault(initials, part)
    return spelled


@dataclass(frozen=True, slots=True)
class _Names:
    """The words an English claim writes with a capital: its names.

    `inner` leaves out a word opening a sentence, where a capital is no sign of a name -
    unless a capitalised word follows it: "Mumbai Police arrested ..." opens with one.
    """

    every: frozenset[str]
    inner: frozenset[str]


def _names(claim_text: str, claim: list[_Word]) -> _Names | None:
    """The claim's names, or None when its script has no capitals to tell them by."""
    if not all(ch.isascii() for ch in claim_text if ch.isalpha()):
        return None
    openers: set[int] = set()
    tokens = [(token.start(), token.group()) for token in re.finditer(r"\S+", claim_text)]
    for index, (start, _) in enumerate(tokens):
        previous = tokens[index - 1][1] if index else ""
        following = tokens[index + 1][1].lstrip(_WRAPPING) if index + 1 < len(tokens) else ""
        opens = not previous or previous.rstrip("\"')]”’").endswith((".", "!", "?"))
        if opens and not following[:1].isupper():
            openers.add(start)
    capitals = [word for word in claim if word.capital and not _is_number(word.word)]
    return _Names(
        every=frozenset(word.word for word in capitals),
        inner=frozenset(word.word for word in capitals if word.start not in openers),
    )


@dataclass(frozen=True, slots=True)
class _Source:
    """A source as the anchor check reads it: folded, as words, the words it writes in
    capitals, and the names it spells out, by their initials."""

    folded: str
    words: list[_Word]
    vocabulary: frozenset[str]
    in_capitals: frozenset[str]
    spelled: dict[str, frozenset[frozenset[str]]]

    @classmethod
    def of(cls, source: str, folded: str) -> _Source:
        words = _words(folded)
        # Read again as written: the folded text has no capitals to tell names by.
        written = _words(source)
        spelled: dict[str, set[frozenset[str]]] = {}
        for initials, part in _runs(written):
            spelled.setdefault(initials, set()).add(part)
        vocabulary = {word.word for word in words}
        # A number the source spells out stands for its digits too.
        vocabulary |= {_NUMBER_WORDS[word] for word in vocabulary if word in _NUMBER_WORDS}
        return cls(
            folded=folded,
            words=words,
            vocabulary=frozenset(vocabulary),
            in_capitals=frozenset(word.word for word in written if word.acronym),
            spelled={initials: frozenset(parts) for initials, parts in spelled.items()},
        )

    def credited(self, claim: list[_Word], names: _Names | None) -> frozenset[str]:
        """The claim's names the source writes another way: spelled out where it
        writes the acronym in capitals, the acronym where it spells them out, and a
        place's people where it names the place, or the other way round."""
        if names is None:
            return frozenset()
        found = {
            word
            for initials, part in _runs(claim)
            if initials in self.in_capitals and _stands_for(initials, part)
            for word in part
        }
        found |= {
            word.word
            for word in claim
            if word.acronym
            and any(_stands_for(word.word, part) for part in self.spelled.get(word.word, ()))
        }
        found |= {name for name in names.every - self.vocabulary if self._place_of(name)}
        return frozenset(found)

    def _place_of(self, name: str) -> bool:
        """Whether the source names the place a name's people are of, or the people of
        a place the name is: "Indian" where it writes "India", and "India" where it
        writes "Indian"."""
        for ending in _PEOPLE_ENDINGS:
            place = name.removesuffix(ending)
            if place != name and len(place) >= 4 and place in self.vocabulary:
                return True
            if len(name) >= 4 and name + ending in self.vocabulary:
                return True
        return False


def _not_in_source(claim_text: str, claim: list[_Word], source: _Source) -> tuple[str, str]:
    """The numbers, then the names, a claim gives that the source does not, anywhere.

    A number is a fact the claim states, and so is a name it writes with a capital in
    mid-sentence ("arrested by Mumbai Police", "Narendra Modi" for a caption's "Prime
    Minister Ji"). A number missing from the whole source means the claim says
    something the source does not, however many of its other words are there; a name
    missing means it cannot be matched by its facts alone (`_locate`).
    """
    numbers = sorted({word.word for word in claim if _is_number(word.word)} - source.vocabulary)
    names = _names(claim_text, claim)
    if names is None:
        return ", ".join(numbers[:4]), ""
    missing = names.inner - source.vocabulary - source.credited(claim, names)
    return ", ".join(numbers[:4]), ", ".join(sorted(missing)[:4])


def _locate_by_coverage(claim_text: str, source: _Source) -> tuple[int, int] | None:
    """The shortest stretch of the source holding the claim's facts, or None.

    A claim extracted from a list is rewritten as a sentence, and no run of its words
    survives. On a page listing "Barack Obama / Arrested Jan 29, facing tribunal for
    High Treason.", the claim "Barack Obama was arrested on January 29 and is facing a
    tribunal for High Treason" matched four of fifteen words in a row and was
    discarded — as were all seven claims on the page, faithful every one.

    So the facts are matched rather than the wording: 80% of the claim's fact-bearing
    words, and every number, within a stretch of the source not much longer than the
    claim. A year is the one number allowed to come from elsewhere on the page — a
    list dated February 2025 says "Feb 3", and the claim rightly says "February 3,
    2025" — but it must still be on the page. An invented claim fails, because the
    facts it invents are not there; a claim assembled from words scattered across the
    page fails, because the stretch is bounded.

    A self-contained claim adds plain words the source leaves to the reader: "seven
    people", "espionage" for "spy", a role or a place spelled out. "Anas, Mohammad ...
    - arrested by Delhi police in Pakistan-ISI-linked spy agency bust" lost every claim
    to that (2026-10-02). So an English claim may also stand on 60% of its words when
    the stretch holds every name it writes with a capital - an acronym it spells out
    counts as written - every number, and half of its other words. A claim that names
    someone the source does not, or gives another number, still fails.
    """
    claim = _words(claim_text)
    wanted = [word.word for word in claim]
    if len(wanted) < 3:
        return None
    distinct = set(wanted)
    years = {word for word in distinct if _YEAR.fullmatch(word)}
    if any(year not in source.folded for year in years):
        return None
    numbers = {word for word in distinct - years if _is_number(word)}
    need = max(len(numbers), int(len(distinct) * _COVERAGE_THRESHOLD + 0.999))

    names = _names(claim_text, claim)
    # What each word of the source gives of the claim's: itself; the digits of a
    # number it spells out; and the claim's words that spell out an acronym it writes
    # in capitals.
    gives: dict[str, set[str]] = {word: {word} for word in distinct}
    for word, digits in _NUMBER_WORDS.items():
        if digits in distinct:
            gives.setdefault(word, set()).add(digits)
    for initials, part in _expansions(claim).items():
        if initials in source.in_capitals and _stands_for(initials, part):
            gives.setdefault(initials, set()).update(part & distinct)
    # Names the source writes another way, wherever it writes them, count as seen.
    credited = source.credited(claim, names) & distinct
    # What may add plain words: an English claim pinned to the source by a name or a
    # number. Without either, nothing ties its words to this stretch rather than any.
    named = set(names.every) if names is not None else set()
    added = names is not None and bool(named or numbers)
    plain = distinct - named - numbers - years
    need_added = int(len(distinct) * _ADDED_WORDS_COVERAGE + 0.999)

    def holds(seen: set[str]) -> bool:
        if not numbers <= seen:
            return False
        if len(seen | years) >= need:
            return True
        return (
            added
            and named <= seen
            and len(seen | years) >= need_added
            and 2 * len(plain & seen) >= len(plain)
        )

    # The source as fact-bearing words, each with where it sits in the folded text.
    positions = source.words
    span = max(12, 3 * len(distinct))
    best: tuple[int, int] | None = None
    for first in range(len(positions)):
        if positions[first].word not in gives:
            continue
        seen = set(credited)
        for last in range(first, min(len(positions), first + span)):
            seen |= gives.get(positions[last].word, set())
            if holds(seen):
                candidate = (positions[first].start, positions[last].end)
                if best is None or candidate[1] - candidate[0] < best[1] - best[0]:
                    best = candidate
                break
    return best


def _why_not_found(claim_text: str, source: str, document: _Document | None = None) -> str:
    """Why a claim was not found in the source, in a few words, for the log."""
    claim = _words(claim_text)
    read = (document or _Document(source)).read
    numbers, names = _not_in_source(claim_text, claim, read)
    if numbers:
        return f"a number it gives is not in the source: {numbers}"
    if names:
        return f"a name it gives is not in the source: {names}"
    if len({word.word for word in claim}) < 3:
        return "not in the source word for word, and too short to find by its facts"
    return "its words are not together in any one part of the source"


def _own_sentence(
    source: str, proposal: ProposedClaim, document: _Document | None = None
) -> str | None:
    """The sentence of a short message that a claim the model read in it is about.

    The message's own words, so nothing the model wrote is shown as the claim; the
    model's English, which says the same with its references resolved, is what is
    searched. Chosen by the facts the sentence shares with the claim - a number, or a
    word of four letters or more - and never a sentence Factify wrote: a label, or a
    description of a picture. Every number the claim gives must be in the message, so
    a claim that misread one cannot be checked in the message's name; and a reading
    that names someone the message does not must be one the sentence's own words can
    resolve to (`_names_someone_else`).
    """
    document = document or _Document(source)
    reading = _fact_words(f"{proposal.text} {proposal.standalone_english}")
    page = document.read.vocabulary
    if any(word not in page for word in reading if _is_number(word)):
        return None
    wanted = {word for word in reading if _is_number(word) or len(word) >= 4}

    sentences: list[str] = []
    described = False
    for line in source.splitlines():
        if line.strip().endswith(":"):
            # Factify's label for the part below it (`app.extraction.reading`).
            described = "described by factify" in line.casefold()
            continue
        if not described:
            sentences.extend(_SENTENCE_BREAK.split(line))

    # One sentence shares one fact to be the claim's; among several, two.
    candidates = [s.strip().strip("\"'“”‘’").strip() for s in sentences]
    candidates = [s for s in candidates if s]
    least = 1 if len(candidates) == 1 else 2
    best: tuple[tuple[int, int], str] | None = None
    for sentence in candidates:
        shared = len(wanted & set(_fact_words(sentence)))
        key = (shared, -len(sentence))
        if shared >= least and (best is None or key > best[0]):
            best = (key, sentence)
    if best is None or _names_someone_else(proposal, best[1], document):
        return None
    return best[1]


# Words a message names someone by without writing the name: a title, an honorific,
# the country or its government. "Our country's Prime Minister Ji" is Narendra Modi,
# and "desh" (the country) India.
_STANDS_IN = re.compile(
    r"\b(?:prime minister|chief minister|minister|pm|cm|president|governor|mantri|ji|"
    r"sahab|saheb|desh|country|nation|bharat|hindustan|sarkar|government|govt)\b"
)


def _names_someone_else(proposal: ProposedClaim, sentence: str, document: _Document) -> bool:
    """Whether a reading of a short message names someone the message never writes,
    in a sentence with no title or other word the name could stand for.

    The message's sentence is shown, but the model's English is what is searched: a
    "Mumbai Police arrested seven men" read from "seven men were held ... by the police
    in Delhi" would have been checked as Mumbai's police in the person's name (2026-10-02
    review). Asked only of a message in Latin letters: the English names a Hindi
    message's people in another script, and that cannot be compared.
    """
    letters = [ch for ch in document.source if ch.isalpha()]
    if not letters or sum(ch.isascii() for ch in letters) < 0.9 * len(letters):
        return False
    if _STANDS_IN.search(fold(sentence)):
        return False
    read = document.read
    return any(
        _not_in_source(text, _words(text), read)[1]
        for text in (proposal.text, proposal.standalone_english)
        if text
    )


def _to_claim(
    proposal: ProposedClaim,
    *,
    claim_id: str,
    source: str,
    content_hash: str,
    input_kind: str,
    language: str | None,
    document: _Document | None = None,
) -> Claim | None:
    """Convert a proposal into a stored claim, or reject it."""
    located = _locate(proposal.text, source, document)
    if located is None:
        return None

    char_start, char_end = located

    return Claim(
        id=claim_id,
        # An English claim is shown self-contained - "Chandrayaan-3's rover payloads
        # include APXS and LIBS" where the article says "Rover payloads include ..." -
        # since a claim listed as wrong has to say what it is about. Located, above,
        # by the document's exact words, which is what the anchor points at. A claim
        # in another language keeps its own words, and the app shows the English in
        # full beside it (`in_full` in the response).
        text=_shown(proposal, language),
        normalized_text=_normalise(proposal.text),
        claim_type=proposal.claim_type,
        severity=proposal.severity,
        importance=proposal.importance,
        coverage_expectation=proposal.coverage_expectation,
        entities=tuple(proposal.entities),
        search_phrases=tuple(proposal.search_phrases),
        location=proposal.location,
        language=language,
        # Written by the extractor, which saw the whole document: "NASA launched
        # Chandrayaan-3" where the claim's own words say "NASA launched it". A
        # translation of the claim alone kept the "it", and a NASA page about Artemis
        # II then "confirmed" it (2026-09-28).
        english_text=_standalone(proposal.standalone_english),
        anchor=ClaimAnchor(
            input_kind=input_kind,
            content_hash=content_hash,
            section=proposal.source_anchor.section,
            paragraph_index=proposal.source_anchor.paragraph_index,
            char_start=char_start,
            char_end=char_end,
        ),
    )


class ClaimPipeline:
    """Extraction, verification and caching around one model call per document."""

    def __init__(self, extractor: Extractor, cache: CacheService | None = None) -> None:
        self._extractor = extractor
        self._cache = cache
        # Stored readings are the model's, so they are kept per model: switching from
        # gpt-4.1-mini to gpt-5.6-luna would otherwise go on serving the old model's
        # claims for every text it had read before.
        model = getattr(extractor, "model_id", None)
        self._version = f"{EXTRACTOR_VERSION}+{model}" if model else EXTRACTOR_VERSION

    async def extract(
        self,
        text: str,
        *,
        content_hash: str,
        input_kind: str = "text",
        language: str | None = None,
    ) -> ExtractedClaims:
        """Extract claims from a document, at most one model call.

        A cache hit costs zero calls, which is what makes re-running the audit
        manifest after a code change affordable.
        """
        if not text.strip():
            return ExtractedClaims(reason="no text to extract from")

        if self._cache is not None:
            cached = await self._cache.get_extraction(
                content_hash=content_hash, extractor_version=self._version
            )
            if cached is not None:
                return self._from_cache(
                    cached,
                    source=text,
                    content_hash=content_hash,
                    input_kind=input_kind,
                    language=language,
                )

        outcome = await self._extractor.extract_claims(text)

        if not outcome.succeeded:
            # No claims and a stated reason. The case continues on media evidence or
            # abstains; nothing is invented to fill the gap.
            return ExtractedClaims(
                reason=outcome.reason, injection_findings=outcome.injection_findings
            )

        claims, discarded = self._verify(
            outcome.claims,
            source=text,
            content_hash=content_hash,
            input_kind=input_kind,
            language=language,
        )

        if self._cache is not None:
            await self._cache.put_extraction(
                content_hash=content_hash,
                extractor_version=self._version,
                payload={"claims": [claim.model_dump(mode="json") for claim in outcome.claims]},
                model_id=outcome.model_id,
            )

        return ExtractedClaims(
            claims=claims,
            model_id=outcome.model_id,
            discarded=discarded,
            injection_findings=outcome.injection_findings,
        )

    def _verify(
        self,
        proposals: tuple[ProposedClaim, ...],
        *,
        source: str,
        content_hash: str,
        input_kind: str,
        language: str | None,
    ) -> tuple[tuple[Claim, ...], tuple[str, ...]]:
        claims: list[Claim] = []
        discarded: list[str] = []
        # At most one headline and one main thesis, enforced rather than trusted: the
        # instruction says so, and an India TV fact-check still came back with two
        # main theses. Every one of them must be confirmed before a case can read
        # True, so a second one quietly raises the bar. Later ones become details.
        ranked_once: set[Importance] = set()
        document = _Document(source)

        for index, proposal in enumerate(proposals):
            if proposal.importance in (Importance.HEADLINE, Importance.MAIN_THESIS):
                if proposal.importance in ranked_once:
                    proposal = proposal.model_copy(
                        update={"importance": Importance.SUPPORTING_DETAIL}
                    )
                else:
                    ranked_once.add(proposal.importance)
            claim = _to_claim(
                proposal,
                claim_id=f"cl_{index + 1}",
                source=source,
                content_hash=content_hash,
                input_kind=input_kind,
                language=language,
                document=document,
            )
            if claim is None:
                discarded.append(proposal.text[:120])
                # The claim and why, so a discard can be traced to the claim it lost:
                # "anchor did not resolve" alone left a lost headline unexplained.
                why = _why_not_found(proposal.text, source, document)
                event(
                    logger,
                    "claim discarded: not found in source",
                    module="extraction.claims",
                    outcome="discarded",
                    failure_reason=f"anchor did not resolve: {why}",
                    claim=proposal.text[:_LOGGED_CLAIM],
                    importance=proposal.importance.value,
                )
                continue
            claims.append(claim)

        # A short message whose claim was read but not found word for word: the
        # sentence of the message the claim is about stands as the claim.
        # gpt-5.6-luna sometimes writes a Hinglish forward's claim in Devanagari or
        # English, and "Modi ji ne bola hai ki kal se desh ke sab petrol pump band
        # rahenge" came back with nothing to check (2026-09-30); an Instagram caption's
        # "our country's Prime Minister Ji" was read as Narendra Modi, which the
        # caption never writes, and the post had nothing to check (2026-10-02). The
        # person's own words are shown, so nothing invented can reach storage; the
        # model's English still drives the search.
        if not claims and len(source.strip()) <= _SHORT_MESSAGE:
            ranked = sorted(enumerate(proposals), key=lambda p: _RANK.get(p[1].importance, 9))
            for index, proposal in ranked:
                sentence = _own_sentence(source, proposal, document)
                own = (
                    _to_claim(
                        proposal.model_copy(update={"text": sentence}),
                        claim_id=f"cl_{index + 1}",
                        source=source,
                        content_hash=content_hash,
                        input_kind=input_kind,
                        language=language,
                        document=document,
                    )
                    if sentence
                    else None
                )
                if own is None:
                    continue
                claims.append(own)
                discarded = [text for text in discarded if text != proposal.text[:120]]
                event(
                    logger,
                    "claim kept as the message's own sentence",
                    module="extraction.claims",
                    outcome="ok",
                    claim=proposal.text[:_LOGGED_CLAIM],
                )
                break

        return tuple(claims), tuple(discarded)

    def _from_cache(
        self,
        payload: dict[str, Any],
        *,
        source: str,
        content_hash: str,
        input_kind: str,
        language: str | None,
    ) -> ExtractedClaims:
        raw = payload.get("claims", [])
        proposals = tuple(
            ProposedClaim.model_validate(item) for item in raw if isinstance(item, dict)
        )
        # Re-verified rather than trusted: a cached proposal is still a proposal, and
        # the anchor check is cheap next to the call it saved.
        claims, discarded = self._verify(
            proposals,
            source=source,
            content_hash=content_hash,
            input_kind=input_kind,
            language=language,
        )
        return ExtractedClaims(claims=claims, from_cache=True, discarded=discarded)


# Longest self-contained English sentence taken from the extractor. A claim is a
# sentence; anything far longer is the model writing an essay, not restating it.
_STANDALONE_CHARACTERS = 400


def _standalone(text: str) -> str:
    """The extractor's self-contained English version of a claim, tidied, or ""."""
    line = " ".join(text.split())
    return line if 0 < len(line) <= _STANDALONE_CHARACTERS else ""


def _shown(proposal: ProposedClaim, language: str | None) -> str:
    """The claim as a person reads it: for an English document, its self-contained
    version when the extractor wrote one; otherwise the document's own words."""
    standalone = _standalone(proposal.standalone_english)
    if not standalone or (language or "en") != "en":
        return proposal.text
    # A translation instead of the document's language, or a sentence about something
    # else, is not shown: it must share words with what the document says.
    own = set(_WORDS.findall(_normalise(proposal.text)))
    shared = own & set(_WORDS.findall(_normalise(standalone)))
    return standalone if own and len(shared) / len(own) >= 0.5 else proposal.text


# Words in Latin, digits and the Indian and Arabic scripts, less the danda.
_WORDS = re.compile(r"[a-z0-9ऀ-ॣ०-ൿ؀-ۿݐ-ݿ]+")
