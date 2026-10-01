"""Live audit manifest (M46).

The answer to "how do you know it works" that is not the demo.

A demo is chosen to succeed. This is a fixed set of real public URLs, real public
media and real fact-check pages, collected during operation and re-run whole — so
the numbers describe the system rather than the selection.

Three rules shape everything here, and all three exist to stop the manifest from
flattering the system:

  - **Never substitute hand-authored evidence.** When a live source changes,
    disappears or rate-limits, that is recorded as a failure and the item abstains.
    A manifest that repairs itself measures the repair.
  - **At least 35 genuine-content items.** Below that the false-positive rate is not
    reportable: with five items the observable rates jump from 0% to 20% with one
    failure, and no reading distinguishes a safe system from an unsafe one. Genuine
    articles are the cheapest category to collect, so this costs collection time
    rather than build time.
  - **Abstention is reported, never optimised.** A falling abstention rate means the
    system has stopped refusing, which is the opposite of the design intent. It
    appears in the report as an observation with no target attached.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "audit-manifest.json"

# The floor below which the false-positive rate is not reportable. Not a target to
# reach and stop at — a floor below which the measurement is meaningless.
MIN_GENUINE_ITEMS = 35


class Category(StrEnum):
    """What an item is there to exercise.

    Coverage across all of these is what makes the report a description of the
    system rather than of whichever path happened to be easy.
    """

    GENUINE = "genuine"
    FACT_CHECKED = "fact_checked"
    RECYCLED_MEDIA = "recycled_media"
    FABRICATED_ATTRIBUTION = "fabricated_attribution"
    OFFICIAL_DOCUMENT = "official_document"
    DEVELOPING = "developing"
    PROVENANCE = "provenance"
    ADVERSARIAL = "adversarial"


class Expectation(StrEnum):
    """What a correct system should conclude.

    `ABSTAIN` is a first-class expectation, not a failure state. Several categories
    exist precisely to check that the system refuses when it should.
    """

    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    MISLEADING_CONTEXT = "MISLEADING_CONTEXT"
    ABSTAIN = "ABSTAIN"


@dataclass(frozen=True, slots=True)
class ManifestItem:
    """One real, public thing to verify, with what it was expected to yield.

    `retrieved_at` and `content_hash` are recorded at collection. If the page later
    changes, the hash no longer matches and the run records that rather than quietly
    scoring against different content.
    """

    id: str
    category: Category
    expectation: Expectation
    url: str | None = None
    text: str | None = None
    media_url: str | None = None
    language: str = "en"
    publisher: str | None = None
    retrieved_at: str | None = None
    content_hash: str | None = None
    reviewer_label: str | None = None
    note: str = ""

    @property
    def is_genuine(self) -> bool:
        return self.category is Category.GENUINE

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "category": self.category.value,
            "expectation": self.expectation.value,
            "url": self.url,
            "text": self.text,
            "media_url": self.media_url,
            "language": self.language,
            "publisher": self.publisher,
            "retrieved_at": self.retrieved_at,
            "content_hash": self.content_hash,
            "reviewer_label": self.reviewer_label,
            "note": self.note,
        }

    @classmethod
    def from_json(cls, payload: dict[str, object]) -> ManifestItem:
        def text(key: str) -> str | None:
            value = payload.get(key)
            return str(value) if value else None

        return cls(
            id=str(payload["id"]),
            category=Category(str(payload["category"])),
            expectation=Expectation(str(payload["expectation"])),
            url=text("url"),
            text=text("text"),
            media_url=text("media_url"),
            language=str(payload.get("language", "en")),
            publisher=text("publisher"),
            retrieved_at=text("retrieved_at"),
            content_hash=text("content_hash"),
            reviewer_label=text("reviewer_label"),
            note=str(payload.get("note", "")),
        )


@dataclass(slots=True)
class Manifest:
    """The whole set, plus when it was collected."""

    items: list[ManifestItem] = field(default_factory=list)
    collected_at: str = ""
    corpus_version: str = ""

    @property
    def genuine_count(self) -> int:
        return sum(1 for item in self.items if item.is_genuine)

    @property
    def meets_genuine_floor(self) -> bool:
        return self.genuine_count >= MIN_GENUINE_ITEMS

    def by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.items:
            counts[item.category.value] = counts.get(item.category.value, 0) + 1
        return dict(sorted(counts.items()))

    def shortfall(self) -> str | None:
        """Why this manifest cannot yet support a reported false-positive rate."""
        if self.meets_genuine_floor:
            return None
        return (
            f"only {self.genuine_count} genuine-content items, floor is "
            f"{MIN_GENUINE_ITEMS}. Below the floor a single failure moves the "
            "observed rate by more than the target itself, so no false-positive "
            "figure may be reported from this run."
        )

    def save(self, path: Path | None = None) -> Path:
        target = path or MANIFEST_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "collected_at": self.collected_at,
                    "corpus_version": self.corpus_version,
                    "min_genuine_items": MIN_GENUINE_ITEMS,
                    "items": [item.to_json() for item in self.items],
                },
                indent=1,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return target

    @classmethod
    def load(cls, path: Path | None = None) -> Manifest:
        source = path or MANIFEST_PATH
        payload = json.loads(source.read_text(encoding="utf-8"))
        return cls(
            items=[ManifestItem.from_json(row) for row in payload["items"]],
            collected_at=str(payload.get("collected_at", "")),
            corpus_version=str(payload.get("corpus_version", "")),
        )


def content_hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def stamp() -> str:
    return datetime.now(UTC).isoformat()
