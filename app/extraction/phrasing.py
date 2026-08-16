"""Template phrasing (M21).

The user-facing wording is assembled, not generated. Two consequences, and both are
the point rather than a side effect:

  - the response path costs zero quota, so a verdict renders even after the day's
    model budget is gone;
  - the wording cannot assert more than the evidence supports, because there is no
    step in which a model chooses the words.

The kill-switch drill in the plan — revoke the model key, confirm the verdict is
unchanged — passes because of this module. Without it, "AI phrases, never decides"
would be a claim about intent rather than about the code.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import Action, ClaimStatus, MediaProvenance, SourceRisk
from app.extraction.language import Language

# English and Hindi only, because those are the languages there is evaluation data
# for. Adding a language means adding templates and fixtures, not a translate call.
_SUPPORTED = (Language.ENGLISH, Language.HINDI, Language.HINGLISH)

_STATUS: dict[ClaimStatus, dict[str, str]] = {
    ClaimStatus.SUPPORTED: {
        "en": "Supported by cited sources",
        "hi": "उद्धृत स्रोतों द्वारा समर्थित",
    },
    ClaimStatus.CONTRADICTED: {
        "en": "Contradicted by cited evidence",
        "hi": "उद्धृत साक्ष्य द्वारा खंडित",
    },
    ClaimStatus.MISLEADING_CONTEXT: {
        "en": "Real content, misleading context",
        "hi": "वास्तविक सामग्री, भ्रामक संदर्भ",
    },
    ClaimStatus.UNVERIFIED: {
        "en": "Could not be verified",
        "hi": "सत्यापित नहीं किया जा सका",
    },
}

_ACTION: dict[Action, dict[str, str]] = {
    Action.SAFE_TO_SHARE: {
        "en": "Safe to share.",
        "hi": "साझा करना सुरक्षित है।",
    },
    Action.SHARE_WITH_CONTEXT: {
        "en": "Share only with context.",
        "hi": "केवल संदर्भ के साथ साझा करें।",
    },
    Action.SHARE_WITH_CORRECTION: {
        "en": "Share only with a correction.",
        "hi": "केवल सुधार के साथ साझा करें।",
    },
    Action.DO_NOT_SHARE: {
        "en": "Do not share.",
        "hi": "साझा न करें।",
    },
    Action.WAIT_AND_RECHECK: {
        "en": "Too recent to check. Wait for coverage.",
        "hi": "जाँच के लिए बहुत नया। कवरेज की प्रतीक्षा करें।",
    },
    Action.SEND_TO_REVIEW: {
        "en": "Sent for human review.",
        "hi": "मानवीय समीक्षा के लिए भेजा गया।",
    },
}

_PROVENANCE: dict[MediaProvenance, dict[str, str]] = {
    MediaProvenance.PROVENANCE_FOUND: {
        "en": "Content credentials found and valid",
        "hi": "कंटेंट क्रेडेंशियल मिले और वैध हैं",
    },
    MediaProvenance.RECYCLED_OR_MISATTRIBUTED: {
        "en": "This media has appeared before, in another context",
        "hi": "यह मीडिया पहले, किसी अन्य संदर्भ में आ चुका है",
    },
    MediaProvenance.UNKNOWN: {
        "en": "No provenance information available",
        "hi": "कोई उत्पत्ति जानकारी उपलब्ध नहीं",
    },
}

_SOURCE_RISK: dict[SourceRisk, dict[str, str]] = {
    SourceRisk.LOW: {"en": "Established publisher", "hi": "स्थापित प्रकाशक"},
    SourceRisk.MEDIUM: {"en": "Limited publisher transparency", "hi": "सीमित प्रकाशक पारदर्शिता"},
    SourceRisk.HIGH: {"en": "Publisher carries risk signals", "hi": "प्रकाशक में जोखिम संकेत"},
    SourceRisk.UNKNOWN: {"en": "Publisher not assessed", "hi": "प्रकाशक का आकलन नहीं"},
}

_CANNOT_ESTABLISH: dict[str, str] = {
    "en": "What Facify cannot establish",
    "hi": "Facify क्या स्थापित नहीं कर सकता",
}

_NOT_CHECKED: dict[str, str] = {
    "en": "Not checked",
    "hi": "जाँचा नहीं गया",
}

_ADVISORY_EXCLUDED: dict[str, str] = {
    "en": "Forensic signals — not used in this verdict",
    "hi": "फोरेंसिक संकेत — इस निर्णय में उपयोग नहीं किए गए",
}

_ORIGINS: dict[str, str] = {
    "en": "{documents} articles, {origins} independent origins",
    "hi": "{documents} लेख, {origins} स्वतंत्र स्रोत",
}


def _locale(language: Language | str | None) -> str:
    """Hinglish reads Hindi content in Latin script, so it takes English wording.

    Rendering Devanagari to someone who types Hindi in Latin script would be a worse
    result than plain English, which they already read.
    """
    if language in (Language.HINDI, "hi"):
        return "hi"
    return "en"


@dataclass(frozen=True, slots=True)
class RenderedVerdict:
    """Every string the interface shows, assembled from templates and citations."""

    status_line: str
    action_line: str
    provenance_line: str
    source_risk_line: str
    reasons: tuple[str, ...]
    corroboration_line: str | None = None
    cannot_establish_heading: str = ""
    not_checked: tuple[str, ...] = ()
    advisory_heading: str = ""


def render(
    *,
    status: ClaimStatus,
    action: Action,
    provenance: MediaProvenance = MediaProvenance.UNKNOWN,
    source_risk: SourceRisk = SourceRisk.UNKNOWN,
    reasons: tuple[str, ...] = (),
    language: Language | str | None = Language.ENGLISH,
    document_count: int = 0,
    origin_count: int = 0,
    capacity_notes: tuple[str, ...] = (),
) -> RenderedVerdict:
    """Assemble the response. No model call happens anywhere below this line.

    `capacity_notes` come from the governor and are surfaced verbatim, because a
    result that quietly omits what it could not check is not an honest result.
    """
    locale = _locale(language)

    corroboration = None
    if document_count or origin_count:
        corroboration = _ORIGINS[locale].format(documents=document_count, origins=origin_count)

    return RenderedVerdict(
        status_line=_STATUS[status][locale],
        action_line=_ACTION[action][locale],
        provenance_line=_PROVENANCE[provenance][locale],
        source_risk_line=_SOURCE_RISK[source_risk][locale],
        reasons=reasons,
        corroboration_line=corroboration,
        cannot_establish_heading=_CANNOT_ESTABLISH[locale],
        not_checked=tuple(f"{_NOT_CHECKED[locale]}: {note}" for note in capacity_notes),
        advisory_heading=_ADVISORY_EXCLUDED[locale],
    )


def supported_languages() -> tuple[Language, ...]:
    """What we claim to support, which is what we have evaluation data for."""
    return _SUPPORTED
