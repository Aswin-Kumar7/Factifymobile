"""The picture checks: what can be said about an uploaded picture or video itself.

Four questions, asked of every upload, each answered independently and each allowed to
come back "could not check" without taking the others with it:

  - **Content credentials** - who signed it, and whether the file says an AI tool made
    it (`provenance.py`). A fact about the file.
  - **Earlier copies** - where the picture has appeared online before, and the oldest
    dated appearance (`discovery.py`, reverse image search). A citable fact about
    the picture's history - the finding that catches an old photo passed off as new.
  - **AI-generation and face-swap signals** - a hosted detector's estimate
    (`synthetic.py`). An advisory.
  - **Editing signals** - noise consistency and the frequency spectrum
    (`forensics.py`). An advisory.

None of it decides a verdict. The verdict is about what the picture's text claims, and
it comes from cited sources; this report sits beside it. The signals travel as
`Advisory` objects, which no verdict function accepts, and the report is a separate
field of the response - there is no path from here into `decide`.

For a video the same questions are asked of a few still frames (`video.py`), and the
report says how many.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from PIL import Image, UnidentifiedImageError

from app.domain.evidence import Advisory
from app.media import forensics, provenance
from app.media.discovery import DiscoveryResult, UnavailableDiscovery
from app.media.forensics import ForensicPanel
from app.media.provenance import ProvenanceReport
from app.media.synthetic import SyntheticReading, UnavailableDetector
from app.observability.logging import event
from app.security.fetcher import FetchResult, SecureFetcher
from app.sources.temporal import DatedInstance

logger = logging.getLogger("factify.media.report")

# How many frames of a video are sent to the paid checks. Each is one reverse image
# search and one detector call; three frames cover a clip's opening, middle and end.
FRAMES_SEARCHED = 3
FRAMES_DETECTED = 2


class Discovers(Protocol):
    async def discover(self, image: bytes) -> DiscoveryResult: ...


class Detects(Protocol):
    async def read(self, image: bytes, *, mime: str = ...) -> SyntheticReading: ...


@dataclass(frozen=True, slots=True)
class MediaReport:
    kind: str  # "image" or "video"
    credentials: ProvenanceReport
    history: DiscoveryResult
    synthetic: SyntheticReading
    editing: ForensicPanel
    frames: int | None = None
    # Our own copy of the earliest earlier appearance, for the side-by-side.
    earliest_thumbnail: str | None = None
    advisories: tuple[Advisory, ...] = field(default_factory=tuple)

    @property
    def earliest(self) -> DatedInstance | None:
        return self.history.oldest


class ThumbnailStore:
    """Small copies of earlier appearances, served from our own address.

    The app never loads a third-party image directly: that would tell the site who
    looked at the picture, and whether it was checked. A copy is taken once, shrunk,
    and kept in memory for an hour - long enough to look at the answer, and no record
    of anything the person sent.
    """

    def __init__(self, *, keep_seconds: float = 3600.0, most: int = 300) -> None:
        self._keep = keep_seconds
        self._most = most
        self._items: OrderedDict[str, tuple[float, bytes]] = OrderedDict()

    def put(self, data: bytes) -> str:
        self._forget_old()
        key = uuid.uuid4().hex
        self._items[key] = (time.monotonic(), data)
        while len(self._items) > self._most:
            self._items.popitem(last=False)
        return key

    def get(self, key: str) -> bytes | None:
        self._forget_old()
        item = self._items.get(key)
        return item[1] if item else None

    def _forget_old(self) -> None:
        now = time.monotonic()
        for key in [k for k, (made, _) in self._items.items() if now - made > self._keep]:
            del self._items[key]


def _shrunk(data: bytes, *, side: int = 320) -> bytes | None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            picture = image.convert("RGB")
            picture.thumbnail((side, side))
            out = io.BytesIO()
            picture.save(out, "JPEG", quality=80)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        return None


class MediaInspector:
    """Runs the picture checks for one upload."""

    def __init__(
        self,
        *,
        discovery: Discovers | None = None,
        detector: Detects | None = None,
        fetcher: SecureFetcher | None = None,
        thumbnails: ThumbnailStore | None = None,
    ) -> None:
        self._discovery: Discovers = discovery or UnavailableDiscovery()
        self._detector: Detects = detector or UnavailableDetector()
        self._fetcher = fetcher
        self.thumbnails = thumbnails or ThumbnailStore()

    async def inspect_image(self, data: bytes, *, mime: str = "image/jpeg") -> MediaReport:
        credentials, editing, synthetic, history = await asyncio.gather(
            _guarded(asyncio.to_thread(provenance.read, data, filename="upload"), _no_credentials),
            _guarded(asyncio.to_thread(forensics.analyse, data, artifact_ref="upload"), _no_panel),
            _guarded(self._detector.read(data, mime=mime), _no_reading),
            _guarded(self._discovery.discover(data), _no_history),
        )
        return await self._finish(
            kind="image",
            credentials=credentials,
            history=history,
            synthetic=synthetic,
            editing=editing,
            artifact_ref="upload",
        )

    async def inspect_video(self, video: bytes, frames: list[bytes]) -> MediaReport:
        """A video, from its still frames: the opening, middle and end of the clip."""
        picked = _spread(frames, FRAMES_SEARCHED)
        credentials = await _guarded(
            asyncio.to_thread(provenance.read, video, filename="upload.mp4"), _no_credentials
        )
        editing = await _guarded(asyncio.to_thread(forensics.analyse_keyframes, frames), _no_panel)
        readings = await asyncio.gather(
            *(
                _guarded(self._detector.read(frame, mime="image/jpeg"), _no_reading)
                for frame in _spread(frames, FRAMES_DETECTED)
            )
        )
        histories = await asyncio.gather(
            *(_guarded(self._discovery.discover(frame), _no_history) for frame in picked)
        )
        return await self._finish(
            kind="video",
            credentials=credentials,
            history=_merged(histories),
            synthetic=_strongest(readings),
            editing=editing,
            artifact_ref="frames",
            frames=len(frames),
        )

    async def _finish(
        self,
        *,
        kind: str,
        credentials: ProvenanceReport,
        history: DiscoveryResult,
        synthetic: SyntheticReading,
        editing: ForensicPanel,
        artifact_ref: str,
        frames: int | None = None,
    ) -> MediaReport:
        thumbnail = await self._copy_of(history.oldest)
        report = MediaReport(
            kind=kind,
            credentials=credentials,
            history=history,
            synthetic=synthetic,
            editing=editing,
            frames=frames,
            earliest_thumbnail=thumbnail,
            advisories=(*editing.advisories, *synthetic.advisories(artifact_ref=artifact_ref)),
        )
        event(
            logger,
            "picture checks done",
            module="media.report",
            outcome="ok",
            kind=kind,
            credentials=credentials.present,
            declares_ai=credentials.declares_ai,
            earlier_pages=len(history.pages),
            dated=len(history.instances),
            detector_checked=synthetic.checked,
            frames=frames,
        )
        return report

    async def _copy_of(self, earliest: DatedInstance | None) -> str | None:
        """Our own small copy of the earliest appearance, or None."""
        if earliest is None or not earliest.image_url or self._fetcher is None:
            return None
        response = await self._fetcher.fetch(earliest.image_url, provider="matched_image")
        if not isinstance(response, FetchResult) or not (response.content_type or "").startswith(
            "image/"
        ):
            return None
        shrunk = await asyncio.to_thread(_shrunk, response.body)
        return self.thumbnails.put(shrunk) if shrunk else None


def _spread(frames: list[bytes], most: int) -> list[bytes]:
    """Up to `most` frames, spread across the clip rather than bunched at its start."""
    if len(frames) <= most:
        return list(frames)
    step = (len(frames) - 1) / (most - 1)
    return [frames[int(index * step + 0.5)] for index in range(most)]


def _merged(histories: list[DiscoveryResult]) -> DiscoveryResult:
    """One history for a clip: every page found for any of its frames."""
    pages = {page.url: page for history in histories for page in history.pages}
    instances = {i.url: i for history in histories for i in history.instances}
    if not pages:
        reasons = [h.reason for h in histories if h.reason]
        skipped = any(h.provider_skipped for h in histories)
        return DiscoveryResult(
            reason=reasons[0] if reasons else "no matching pages found",
            provider_skipped=skipped,
        )
    return DiscoveryResult(pages=tuple(pages.values()), instances=tuple(instances.values()))


def _strongest(readings: list[SyntheticReading]) -> SyntheticReading:
    """The highest of each likelihood across the frames that were read."""
    checked = [r for r in readings if r.checked]
    if not checked:
        return readings[0] if readings else SyntheticReading(reason="no frame to read")
    generated = [r.generated for r in checked if r.generated is not None]
    swapped = [r.face_swap for r in checked if r.face_swap is not None]
    return SyntheticReading(
        generated=max(generated) if generated else None,
        face_swap=max(swapped) if swapped else None,
    )


async def _guarded(work: Any, fallback: Any) -> Any:
    """One check's answer; a check that fails reports that, and takes nothing else down."""
    try:
        return await work
    except Exception as error:
        logger.exception("a picture check failed")
        return fallback(f"{type(error).__name__}")


def _no_credentials(reason: str) -> ProvenanceReport:
    return ProvenanceReport(present=False, reason=f"unreadable: {reason}")


def _no_panel(reason: str) -> ForensicPanel:
    return ForensicPanel(reason=reason)


def _no_reading(reason: str) -> SyntheticReading:
    return SyntheticReading(reason=f"failed: {reason}")


def _no_history(reason: str) -> DiscoveryResult:
    return DiscoveryResult(reason=f"failed: {reason}")


def days_before(earliest: DatedInstance | None, *, now: datetime | None = None) -> int | None:
    """How many days before now the picture was already online."""
    if earliest is None:
        return None
    moment = now or datetime.now(UTC)
    published = earliest.published_at
    if published.tzinfo is None:
        published = published.replace(tzinfo=UTC)
    return max(0, (moment - published).days)
