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
"""

from __future__ import annotations

import logging
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
        return ProvenanceReport(present=False, reason="no manifest in this asset")

    return _parse(manifest_json)


def _read_manifest(module: Any, data: bytes, filename: str) -> dict[str, Any] | None:
    """Call whichever reader API this c2pa build exposes.

    The Python binding has changed shape across releases. Rather than pin behaviour to
    one version, try the current entry point and fall back; an unrecognised build
    returns nothing, which lands on unknown like every other failure.
    """
    import json

    reader = getattr(module, "Reader", None)
    if reader is not None:
        with reader(_format_for(filename), data) as handle:
            return dict(json.loads(handle.json()))

    legacy = getattr(module, "read_file", None)
    if legacy is not None:
        return dict(json.loads(legacy(filename, None)))

    return None


def _format_for(filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpeg"
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "mp4": "video/mp4"}.get(
        suffix, "image/jpeg"
    )


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
