"""Content credentials (M36, P1).

Reads C2PA manifests where they exist, and says honestly that they usually do not.

Three rules govern how a manifest is read, and all three are about *not* over-reading
it:

  - A missing manifest is **unknown**, never evidence of fakery. Almost nothing
    carries one. Platforms strip credentials during reprocessing and a screenshot
    severs the binding entirely — which describes essentially every input this
    product actually receives.
  - A valid manifest is **not** evidence that the depicted event is true. It binds an
    assertion to an asset. A signed photograph of a staged scene is a validly signed
    photograph of a staged scene.
  - A valid manifest binds bytes to a signer. That is a real, checkable statement,
    and it is the only one made here.

P1 by design: this module is deliberately off the critical path, because spending
build time on a signal that returns unknown for the dominant input distribution would
be time not spent on the paths that resolve real cases.

**Declared AI generation** is read too (2026-09-27): the IPTC digital source type an
AI tool writes into its own output - OpenAI, Adobe Firefly and Google sign theirs with
"trainedAlgorithmicMedia" - from a manifest, or from the file's XMP metadata where
there is no manifest. It is the one AI-generation signal that is not a guess: the file
says so itself. It is reported as what the file says, trusted signer or not, and like
everything here it never enters a verdict.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domain.enums import SyntheticSignal
from app.observability.logging import event

logger = logging.getLogger("factify.media.provenance")

NAME = "c2pa"


@dataclass(frozen=True, slots=True)
class Ingredient:
    """One asset that went into this one — the edit chain, as the manifest tells it."""

    title: str | None
    relationship: str | None
    validated: bool = False


@dataclass(frozen=True, slots=True)
class ProvenanceReport:
    """What the credentials say, or that there are none.

    `present=False` is the overwhelmingly common outcome and is not a negative
    finding. `is_unknown` exists so callers cannot accidentally read absence as a
    result — they have to handle the third state explicitly.
    """

    present: bool
    valid: bool = False
    signer: str | None = None
    created_at: datetime | None = None
    assertions: tuple[str, ...] = field(default_factory=tuple)
    ingredients: tuple[Ingredient, ...] = field(default_factory=tuple)
    validation_errors: tuple[str, ...] = field(default_factory=tuple)
    reason: str | None = None
    # What the file says made it (an IPTC digital source type such as
    # "trainedAlgorithmicMedia"), and the tool it names. From the manifest, or from
    # XMP metadata when there is none; None when nothing is declared.
    digital_source: str | None = None
    generator: str | None = None
    # The manifest is intact but its signer is on no trust list checked here - a
    # self-signed or unknown credential. Readable, never citable.
    untrusted_signer: bool = False

    @property
    def declares_ai(self) -> bool:
        """The file itself says a trained model made or composited it."""
        return self.digital_source in _AI_SOURCES

    @property
    def is_unknown(self) -> bool:
        """No manifest, or none readable. The normal case; not a finding."""
        return not self.present

    @property
    def signal(self) -> SyntheticSignal:
        """What this contributes, in the only vocabulary that can leave this module.

        A valid manifest is `CONFIRMED_BY_PROVENANCE` — an asset bound to a signer.
        Everything else is `NO_SIGNAL`. There is deliberately no path to
        `ADVISORY_SUSPICION`: an invalid or absent manifest says nothing suspicious,
        it says nothing at all.
        """
        if self.present and self.valid:
            return SyntheticSignal.CONFIRMED_BY_PROVENANCE
        return SyntheticSignal.NO_SIGNAL

    @property
    def summary(self) -> str:
        """What the user is told, phrased so it cannot be over-read."""
        if not self.present:
            return (
                "No content credentials found. This is normal — most images and video "
                "carry none, and sharing platforms remove them. It is not a sign that "
                "the content is fake."
            )
        if not self.valid:
            errors = "; ".join(self.validation_errors) or "unspecified"
            return (
                f"Content credentials are present but did not validate ({errors}). "
                "The credential could not be trusted; this says nothing about whether "
                "the content is real."
            )
        return (
            f"Content credentials validated. Signed by {self.signer or 'an unnamed signer'}. "
            "This confirms who signed these bytes and what edits were declared — it does "
            "not confirm that the depicted event happened."
        )


def _load_c2pa() -> Any | None:
    """Import the reader if it is installed. Absence is a normal configuration."""
    try:
        import c2pa
    except ImportError:
        return None
    return c2pa


def available() -> bool:
    return _load_c2pa() is not None


def read(data: bytes, *, filename: str = "upload") -> ProvenanceReport:
    """Read content credentials out of an asset.

    Every failure path lands on the same answer — unknown — because every one of them
    means the same thing: we could not read a credential. None of them mean the
    content is suspect.
    """
    module = _load_c2pa()
    if module is None:
        return ProvenanceReport(
            present=False, reason="unavailable: the c2pa reader is not installed"
        )

    try:
        manifest_json = _read_manifest(module, data, filename)
    except Exception as exc:
        event(
            logger,
            "content credentials unreadable",
            module="media.provenance",
            outcome="skipped",
            failure_reason=type(exc).__name__,
        )
        return ProvenanceReport(present=False, reason=f"unreadable: {type(exc).__name__}")

    if not manifest_json:
        return ProvenanceReport(
            present=False,
            reason="no manifest in this asset",
            digital_source=declared_source(data),
        )

    return _parse(manifest_json)


def _read_manifest(module: Any, data: bytes, filename: str) -> dict[str, Any] | None:
    """Call whichever reader API this c2pa build exposes.

    The Python binding has changed shape across releases. Rather than pin behaviour to
    one version, try the current entry point and fall back; an unrecognised build
    returns nothing, which lands on unknown like every other failure.

    The reader takes a stream, not bytes: handed the bytes it failed on every upload,
    and every one was reported as having no credentials. The format is read from the
    bytes too - uploads are named by their hash, so a PNG was read as a JPEG.
    """
    import json

    reader = getattr(module, "Reader", None)
    if reader is not None:
        try:
            with reader(_format_of(data, filename), io.BytesIO(data)) as handle:
                return dict(json.loads(handle.json()))
        except Exception as exc:
            if "ManifestNotFound" in type(exc).__name__:
                return None
            raise

    legacy = getattr(module, "read_file", None)
    if legacy is not None:
        return dict(json.loads(legacy(filename, None)))

    return None


def _format_of(data: bytes, filename: str) -> str:
    """The media type, from the file's first bytes; the name only as a fallback."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp":
        return "video/mp4"
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpeg"
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "mp4": "video/mp4"}.get(
        suffix, "image/jpeg"
    )


# IPTC digital source types meaning a trained model made the picture, or part of it.
# https://cv.iptc.org/newscodes/digitalsourcetype/
_AI_SOURCES = frozenset({"trainedAlgorithmicMedia", "compositeWithTrainedAlgorithmicMedia"})
_SOURCE_TERM = re.compile(rb"digitalsourcetype/([A-Za-z]+)")


def declared_source(data: bytes) -> str | None:
    """The IPTC digital source type written in the file's own metadata, if any.

    XMP is stored as plain text inside JPEG, PNG and WebP files, so the term is read
    straight from the bytes - no manifest, no library. Platforms strip metadata as
    readily as credentials, so absence means nothing; presence means the file says it.
    """
    found = _SOURCE_TERM.search(data)
    return found.group(1).decode("ascii") if found else None


def _actions(active: dict[str, Any]) -> list[dict[str, Any]]:
    """The actions the manifest records (`c2pa.actions` and its versions)."""
    actions: list[dict[str, Any]] = []
    for item in active.get("assertions", []) or []:
        if str(item.get("label", "")).startswith("c2pa.actions"):
            data = item.get("data") or {}
            actions.extend(a for a in data.get("actions", []) or [] if isinstance(a, dict))
    return actions


def _agent_name(agent: Any) -> str | None:
    if isinstance(agent, dict):
        name = agent.get("name")
        return str(name) if name else None
    return str(agent) if agent else None


def _parse(manifest_json: dict[str, Any]) -> ProvenanceReport:
    """Turn a manifest store into the report, reading only what is defensible."""
    active_label = manifest_json.get("active_manifest")
    manifests = manifest_json.get("manifests", {})
    active = manifests.get(active_label, {}) if active_label else {}

    if not active:
        return ProvenanceReport(present=False, reason="manifest store contains no active manifest")

    status = manifest_json.get("validation_status", []) or []
    errors = tuple(
        str(item.get("code", "unknown"))
        for item in status
        if str(item.get("code", "")).startswith(("signing", "claim", "assertion"))
    )
    # An unknown signer is its own finding, not a broken credential: the manifest is
    # intact and says what it says; only nobody we trust vouches for it.
    untrusted = errors == ("signingCredential.untrusted",)

    source: str | None = None
    agent: str | None = None
    for action in _actions(active):
        term = str(action.get("digitalSourceType") or "").rstrip("/").rsplit("/", 1)[-1]
        if term:
            source = term
            agent = _agent_name(action.get("softwareAgent")) or agent
            if term in _AI_SOURCES:
                break
    if agent is None:
        generators = active.get("claim_generator_info") or []
        if generators and isinstance(generators[0], dict):
            agent = _agent_name(generators[0])

    signature = active.get("signature_info", {}) or {}

    created_at: datetime | None = None
    raw_time = signature.get("time")
    if isinstance(raw_time, str):
        try:
            created_at = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except ValueError:
            created_at = None

    ingredients = tuple(
        Ingredient(
            title=item.get("title"),
            relationship=item.get("relationship"),
            validated=not item.get("validation_status"),
        )
        for item in active.get("ingredients", []) or []
    )

    assertions = tuple(
        str(item.get("label", ""))
        for item in active.get("assertions", []) or []
        if item.get("label")
    )

    report = ProvenanceReport(
        present=True,
        valid=not errors,
        signer=signature.get("issuer"),
        created_at=created_at,
        assertions=assertions,
        ingredients=ingredients,
        validation_errors=errors,
        digital_source=source,
        generator=agent,
        untrusted_signer=untrusted,
    )

    event(
        logger,
        "content credentials read",
        module="media.provenance",
        outcome="ok",
        valid=report.valid,
        ingredients=len(ingredients),
    )

    return report
