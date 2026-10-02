"""Claims and their anchors (M05).

A claim without an anchor cannot exist. The anchor is what lets a finding point at
the exact paragraph, character range, page or frame it came from, and without it a
verdict is an assertion rather than an audit trail.
"""

from __future__ import annotations

import re
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import (
    ClaimType,
    CoverageExpectation,
    Importance,
    Severity,
    SourceRisk,
)


class ClaimAnchor(BaseModel):
    """Where in the input this claim was asserted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_kind: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    section: str | None = None
    paragraph_index: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    page_number: int | None = None
    frame_start_ms: int | None = None
    frame_end_ms: int | None = None

    @model_validator(mode="after")
    def _locates_something(self) -> Self:
        """An anchor that points nowhere is not an anchor."""
        located = any(
            field is not None
            for field in (
                self.paragraph_index,
                self.char_start,
                self.page_number,
                self.frame_start_ms,
            )
        )
        if not located:
            raise ValueError(
                "anchor must locate the claim: give a paragraph, character offset, page or frame"
            )
        return self


class Claim(BaseModel):
    """One atomic, checkable assertion.

    `severity` and `importance` are assigned at extraction and consumed by the case
    rollup, where "material" is these two fields rather than a judgement call.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    text: str = Field(min_length=1)
    claim_type: ClaimType
    severity: Severity
    importance: Importance
    anchor: ClaimAnchor

    normalized_text: str = ""
    language: str | None = None
    coverage_expectation: CoverageExpectation | None = None
    entities: tuple[str, ...] = ()

    # Queries that would find sources addressing this claim, from extraction. The
    # claim's own sentence retrieves its topic; these ask the question behind it.
    search_phrases: tuple[str, ...] = ()
    location: str | None = None

    # The claim as one self-contained English sentence: written by the extractor from
    # the whole document (pronouns and shorthand resolved), or machine-translated when
    # it gave none. For finding and reading sources - most fact-checks and national
    # reporting are published in English - and never shown to anyone as the claim.
    english_text: str = ""

    # Set by the corroboration and source-risk tracks. They are inputs to the rules,
    # not evidence themselves — an origin count is a property of the evidence set.
    independent_origin_count: int = Field(default=0, ge=0)
    document_count: int = Field(default=0, ge=0)
    source_risk: SourceRisk = SourceRisk.UNKNOWN
    within_developing_window: bool = False

    @property
    def reading_text(self) -> str:
        """The claim as the source readers see it: its own words, with the English
        beside them when it was made in another language."""
        if self.english_text and self.english_text.casefold() != self.text.casefold():
            # For an English claim the line is its meaning in full ("NASA launched
            # Chandrayaan-3" for "NASA launched it"), not a translation.
            said = "In full" if (self.language or "en") == "en" else "In English"
            return f"{self.text}\n({said}: {self.english_text})"
        return self.text

    @property
    def search_text(self) -> str:
        """The claim to search the web with and to rank results against: its
        self-contained English version when there is one - context and all, "NASA
        launched Chandrayaan-3" for "NASA launched it" - else its own words."""
        return self.english_text or self.text

    @property
    def matching_text(self) -> str:
        """For matching by words or embeddings against mostly English sources: the
        English translation for the ten newer languages, the claim itself otherwise.
        Hindi keeps its own words, which the multilingual embeddings were measured on.
        """
        if self.english_text and (self.language or "en") not in ("en", "hi", "hi-Latn"):
            return self.english_text
        return self.text

    @property
    def is_checkable(self) -> bool:
        """What evidence can settle. Opinion cannot, and neither can a prediction.

        Prediction was missing here, and richer retrieval turned that omission into a
        live false positive: "India will win the 2027 Cricket World Cup" came back
        **SAFE_TO_SHARE**, carried by two outlets writing about India's prospects. The
        extractor had typed it `PREDICTION` correctly; nothing downstream did anything
        with that. With search snippets the claim had never gathered enough support to
        reach a verdict, so the gap stayed hidden until the reader was given whole
        articles.

        No amount of evidence settles a statement about an event that has not happened.
        Coverage of a forecast is evidence that the forecast was made, which is a
        different claim, and treating the two as one is how a system ends up telling
        someone it is safe to share a tip on a tournament nobody has played.
        """
        return self.claim_type not in {ClaimType.OPINION, ClaimType.PREDICTION}

    @property
    def is_material(self) -> bool:
        """The rollup's definition, stated once so no caller has to interpret it.

        Material means the claim carries the document — a headline or main thesis —
        or is severe enough that being wrong about it matters regardless of position.
        """
        return self.importance in {
            Importance.HEADLINE,
            Importance.MAIN_THESIS,
        } or self.severity in {Severity.HIGH, Severity.CRITICAL}


# A claim about what a picture or video shows: who is pictured, what it is a photo of.
_DEPICTS = re.compile(
    r"\b(?:pictured|appears? to be|are seen|is seen|are shown|is shown|selfie|"
    r"(?:photo(?:graph)?|picture|image|video|clip|footage)s? (?:shows?|of))\b",
    re.IGNORECASE,
)


def depicts(claim: Claim) -> bool:
    """Whether a claim is about what a picture or video shows."""
    return any(_DEPICTS.search(text) for text in (claim.search_text, claim.text) if text)


# Claims about material - who said what, what a picture or video shows - which alone
# can be genuine and shown out of context.
_MATERIAL_TYPES = frozenset({ClaimType.QUOTE, ClaimType.ATTRIBUTION, ClaimType.MEDIA})


def about_material(claim: Claim) -> bool:
    """Whether a claim is about words, a picture or footage, which alone can be
    genuine and presented out of context: a quote or an attribution, a claim about
    what a picture or video shows, or the claim that a post's footage was taken at
    its event (`app/extraction/llm.py` `_footage_claim`).

    Not a claim that an event happened. BOOM's "Cropped video falsely claims Iran
    President touched Hindu seer's feet" says the event did not happen, and the video
    is genuine: read as out of context, that FALSE would have read MISLEADING.
    """
    return (
        claim.claim_type in _MATERIAL_TYPES or claim.anchor.section == "footage" or depicts(claim)
    )
