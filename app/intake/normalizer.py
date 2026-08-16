"""Intake normalisation (M15).

Turns any accepted input into a case with content objects, computing identity before
anything else happens. Identity first is what makes the cache probe possible, and the
cache probe is what stops an external call from ever being the first thing a request
does.

The case and its objects are written **before** any work begins, so a request that
fails validation, times out or gets blocked still leaves a record of the attempt. A
verification we refused to do is as much a fact about the system as one we completed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum

from app.cache.keys import content_hash, text_hash
from app.extraction.language import Detection, detect
from app.security.uploads import MediaKind, UploadRejected, validate_upload


class InputType(StrEnum):
    """What the caller supplied. Matches the schema's CHECK constraint."""

    TEXT = "text"
    URL = "url"
    IMAGE = "image"
    PDF = "pdf"
    VIDEO = "video"


class IntakeRejected(Exception):
    """The input cannot be processed, with a reason worth recording."""

    def __init__(self, reason: str, *, kind: str = "invalid") -> None:
        self.reason = reason
        self.kind = kind
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ContentObject:
    """One piece of content, identified before it is examined."""

    kind: str
    sha256: str
    data: bytes | None = None
    text: str | None = None
    source_url: str | None = None
    mime_type: str | None = None
    byte_size: int | None = None
    width: int | None = None
    height: int | None = None
    location_stripped: bool = False

    @property
    def is_media(self) -> bool:
        return self.kind in {"image", "video", "frame"}


@dataclass(frozen=True, slots=True)
class NormalisedIntake:
    """Everything the pipeline needs to start, and nothing it has to re-derive."""

    input_type: InputType
    objects: tuple[ContentObject, ...]
    cache_identity: str
    language: Detection
    consent_to_process_media: bool = False
    extraction_route: str = ""
    notes: tuple[str, ...] = field(default=())

    @property
    def primary(self) -> ContentObject:
        return self.objects[0]


def _canonical_url(url: str) -> str:
    """Strip the parts of a URL that identify a click rather than a document.

    Tracking parameters make the same article a different cache key for every
    person who shares it, which would defeat the one mechanism that keeps repeat
    content free.
    """
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url.strip())
    tracking_prefixes = ("utm_", "fbclid", "gclid", "igshid", "mc_", "ref", "s_cid")

    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not any(key.lower().startswith(prefix) for prefix in tracking_prefixes)
    ]

    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    # A default port carries no information and would fork the cache key.
    for default in (":80", ":443"):
        if netloc.endswith(default):
            netloc = netloc.rsplit(":", 1)[0]

    path = parts.path.rstrip("/") or "/"

    return urlunsplit((scheme, netloc, path, urlencode(kept), ""))


def normalise_text(text: str, *, consent: bool = False) -> NormalisedIntake:
    """Pasted text — the simplest path, and the most common one in practice."""
    if not text.strip():
        raise IntakeRejected("no text supplied")

    identity = text_hash(text)
    language = detect(text)

    return NormalisedIntake(
        input_type=InputType.TEXT,
        objects=(ContentObject(kind="text", sha256=identity, text=text),),
        cache_identity=identity,
        language=language,
        consent_to_process_media=consent,
        extraction_route="text.direct",
    )


def normalise_url(url: str, *, consent: bool = False) -> NormalisedIntake:
    """A link. Canonicalised before hashing, so shares of one article collapse.

    Note what does *not* happen here: no fetch. Normalisation is local, the cache is
    probed on the canonical form, and only a miss justifies going to the network.
    """
    canonical = _canonical_url(url)
    if not canonical or "://" not in canonical:
        raise IntakeRejected(f"not a usable URL: {url!r}")

    identity = f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"

    return NormalisedIntake(
        input_type=InputType.URL,
        objects=(ContentObject(kind="url", sha256=identity, source_url=canonical),),
        cache_identity=identity,
        language=detect(""),
        consent_to_process_media=consent,
        extraction_route="url.canonicalised",
        notes=("canonicalised",) if canonical != url.strip() else (),
    )


def normalise_upload(
    data: bytes,
    *,
    max_bytes: int,
    declared_type: str | None = None,
    consent: bool = False,
) -> NormalisedIntake:
    """An uploaded file. Type is decided by the bytes, never by the client.

    Validation returns *sanitised* bytes — EXIF location already removed — and those
    are what the content object carries, so the original cannot be persisted by
    forgetting a step later.
    """
    try:
        validated = validate_upload(data, max_bytes=max_bytes, declared_type=declared_type)
    except UploadRejected as rejected:
        raise IntakeRejected(rejected.reason, kind=rejected.kind) from rejected

    kind_map = {
        MediaKind.IMAGE: InputType.IMAGE,
        MediaKind.PDF: InputType.PDF,
        MediaKind.VIDEO: InputType.VIDEO,
    }
    input_type = kind_map.get(validated.kind)
    if input_type is None:
        raise IntakeRejected(f"unsupported upload type {validated.kind}", kind="unsupported")

    # Identity is computed over the sanitised bytes, so the same photograph shared
    # with and without location metadata is one cache entry rather than two.
    identity = content_hash(validated.data)

    notes: list[str] = []
    if validated.location_stripped:
        notes.append("exif location removed")
    if declared_type and not validated.mime_type.startswith(declared_type.split("/")[0]):
        notes.append(f"declared {declared_type}, detected {validated.mime_type}")

    return NormalisedIntake(
        input_type=input_type,
        objects=(
            ContentObject(
                kind=input_type.value,
                sha256=identity,
                data=validated.data,
                mime_type=validated.mime_type,
                byte_size=validated.byte_size,
                width=validated.width,
                height=validated.height,
                location_stripped=validated.location_stripped,
            ),
        ),
        cache_identity=identity,
        language=detect(""),
        consent_to_process_media=consent,
        extraction_route=f"upload.{validated.mime_type}",
        notes=tuple(notes),
    )
