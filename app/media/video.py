"""Video keyframes (M35).

Verifies video context without downloading, storing or analysing whole videos.

The insight the whole module rests on: twelve frames and a caption resolve the
overwhelmingly common case, which is real footage under a false date or a false
place. Nothing here attempts to determine whether a face was swapped — that is a
different question, it is answered advisorily in M37, and pretending otherwise would
be the failure this product exists to avoid.

Caps are enforced before any decode, because a decode is the expensive, attackable
step. First 90 seconds, ≤480p, at most twelve scene-change keyframes: forensic and
contextual signals do not need more, and the free-tier compute allowance cannot
afford more.

What a clip shows is read separately (`FramesRead`, 2026-10-03). The keyframes above
are for the picture checks; to read a clip's words and pictures, one keyframe from
its first 90 seconds was not enough. A news clip about the RBI put "REPO RATE
UNCHANGED AT 5.25%" on screen from 1:53 to its end, and the frame read was a wipe at
0:36 with the Governor hidden behind blue bars. So frames are now taken across the
whole clip, up to ten minutes in a background check: its opening, its last second,
evenly between, and just after each cut, each the clearest of a few taken a moment
apart, so a transition or a blur is not the frame read.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import math
import re
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError

from app.observability.logging import event

logger = logging.getLogger("factify.media.video")

DEFAULT_MAX_SECONDS = 90
DEFAULT_MAX_KEYFRAMES = 12
# Frames spread evenly across a clip for the face model (`ExtractedVideo.even_frames`).
# Eight: on 100 videos, sixteen caught one more face swap in fifty at twice the time.
EVEN_FRAMES = 8
# At up to this height, not the keyframes' 480: the face model judges a face, and at
# 480 lines a 1080p face lost enough that 2 of 50 real videos read swapped and 7 more
# swaps were missed than at full size (2026-09-30).
EVEN_MAX_HEIGHT = 1080
DEFAULT_MAX_HEIGHT = 480

# Scene-change sensitivity. Lower catches more cuts; too low returns twelve frames of
# the same shot, which is twelve reverse-image lookups that answer one question.
SCENE_THRESHOLD = 0.3

# How long one decoding pass over the clip may run: 90 s for the default 90-second
# window, as it always was, and 0.3 s more for each second beyond it (243 s for ten
# minutes). A kill switch for a decoder that spins, not a budget.
PASS_TIMEOUT_S = 90.0
PASS_TIMEOUT_PER_SECOND = 0.3

# ----------------------------------------------------------------- reading frames
#
# What a background check reads of a clip's pictures: its first ten minutes, the same
# window as its speech (`app/media/speech.py`) and as `social.max_video_seconds`, in at
# most 24 frames. A quick read takes 90 seconds and eight.
READ_SECONDS = 600
READ_FRAMES = 24
QUICK_READ_SECONDS = 90
QUICK_READ_FRAMES = 8
# A frame about every six seconds while the cap allows: a news card or a caption
# stays on screen longer than that. Past 2:20 the 24 frames are simply spread wider.
READ_EVERY_SECONDS = 6.0
# The first frame is taken a moment in, past a fade from black; the last this long
# before the end - the last second, where a news clip puts its summary card.
OPENING_SECONDS = 0.3
CLOSING_SECONDS = 0.5
# A frame for a cut is taken this long after it: the new shot has settled, past the
# wipe or the dissolve that brought it in.
SETTLED_SECONDS = 0.8
# At most this share of the frames go to cuts; the rest are spread evenly.
CUT_SHARE = 1 / 3
# Around each moment a few frames are taken, this far apart, and the clearest is
# read (`clearest`).
CANDIDATES = 4
CANDIDATE_STEP_SECONDS = 0.35
# Frames are read for their words, which need more lines than the picture checks'.
READ_MAX_HEIGHT = 720
# Frames taken at once: each is its own short ffmpeg run.
READ_CONCURRENCY = 2
# The cuts a scene pass reports, at most; more are thinned evenly.
MAX_CUTS = 60

_PTS_TIME = re.compile(r"pts_time:\s*([0-9]+(?:\.[0-9]+)?)")


class VideoRejected(Exception):
    def __init__(self, reason: str, *, kind: str = "invalid") -> None:
        self.reason = reason
        self.kind = kind
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class VideoProbe:
    """What the container says about itself, read before anything is decoded."""

    duration_seconds: float
    width: int
    height: int
    codec: str
    container: str


@dataclass(frozen=True, slots=True)
class Keyframe:
    """One extracted frame and the moment it came from.

    `timestamp_ms` is what a claim anchor cites, so a finding can point at the second
    of the clip it applies to rather than at the clip as a whole.
    """

    index: int
    timestamp_ms: int
    data: bytes

    @property
    def anchor(self) -> dict[str, int]:
        return {"frame_start_ms": self.timestamp_ms, "frame_end_ms": self.timestamp_ms}


@dataclass(frozen=True, slots=True)
class ExtractedVideo:
    """Frames, the probe, and an honest account of what was skipped."""

    probe: VideoProbe | None
    keyframes: tuple[Keyframe, ...] = ()
    # Frames spread evenly across the clip, for the face model: a talking head has no
    # scene changes, and three keyframes gave a face swap three chances to show.
    even_frames: tuple[Keyframe, ...] = ()
    truncated: bool = False
    limitations: tuple[str, ...] = field(default_factory=tuple)
    reason: str | None = None
    # The frames taken to read what the clip shows, when they were asked for
    # (`KeyframeExtractor(read_seconds=...)`).
    read: FramesRead | None = None

    @property
    def succeeded(self) -> bool:
        return self.reason is None and bool(self.keyframes)


@dataclass(frozen=True, slots=True)
class FramesRead:
    """Frames taken across a clip to read its words and its pictures, in time order.

    Each frame's `timestamp_ms` is the moment it was taken. `window_seconds` is how
    far into the clip they reach: the whole clip, or the read window when the clip is
    longer (`cut_off`), and what the answer says was read.
    """

    frames: tuple[Keyframe, ...] = ()
    window_seconds: float = 0.0
    duration_seconds: float = 0.0
    # How many of the frames were taken just after a cut.
    after_cuts: int = 0
    reason: str | None = None
    # These are the picture checks' keyframes, from the clip's opening stretch, read
    # because none could be taken across it (`reason` says why).
    from_keyframes: bool = False

    @property
    def cut_off(self) -> bool:
        """The clip runs past what was read."""
        return self.duration_seconds - self.window_seconds > 1.0

    @property
    def first_ms(self) -> int | None:
        return self.frames[0].timestamp_ms if self.frames else None

    @property
    def last_ms(self) -> int | None:
        return self.frames[-1].timestamp_ms if self.frames else None


def pass_timeout(seconds: float) -> float:
    """How long one decoding pass over `seconds` of a clip may run."""
    return PASS_TIMEOUT_S + PASS_TIMEOUT_PER_SECOND * max(0.0, seconds - DEFAULT_MAX_SECONDS)


def clock(milliseconds: int | float) -> str:
    """A moment in a clip as people write it: 0:07, 2:09, 1:02:03."""
    seconds = max(0, int(milliseconds // 1000))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def reading_moments(
    window: float, *, most: int, cuts: Sequence[float] = ()
) -> tuple[list[float], int]:
    """The moments a clip's frames are read at, in order, and how many follow a cut.

    The opening and the last second always; a moment just after each cut, up to a
    third of `most`; and the rest spread evenly between, about every six seconds
    while `most` allows. No two closer than a clip of this length can afford, so a
    cut a second after the opening does not spend a frame on the same picture.
    """
    if window <= 0 or most <= 0:
        return [], 0
    last = max(0.0, window - CLOSING_SECONDS)
    first = min(OPENING_SECONDS, last)
    if most == 1 or last - first < 0.2:
        return [first], 0
    apart = max(0.5, min(2.0, (last - first) / most))

    chosen: list[float] = [first, last]

    def room(moment: float) -> bool:
        return first <= moment <= last and all(abs(moment - other) >= apart for other in chosen)

    settled = [cut + SETTLED_SECONDS for cut in cuts]
    settled = [moment for moment in settled if room(moment)]
    allowed = max(0, min(most - 2, int(most * CUT_SHARE)))
    if len(settled) > allowed:
        settled = _thinned(settled, allowed)
    after_cuts = 0
    for moment in settled:
        if room(moment):
            chosen.append(moment)
            after_cuts += 1

    # What is left of `most` is spread over the whole clip, never spent at its start.
    slots = most - len(chosen)
    spaced = max(2, min(slots + 2, math.ceil((last - first) / READ_EVERY_SECONDS) + 1))
    for step in range(1, spaced - 1):
        moment = first + (last - first) * step / (spaced - 1)
        if room(moment):
            chosen.append(moment)
    return sorted(chosen), after_cuts


def _thinned(values: Sequence[float], most: int) -> list[float]:
    """Up to `most` of the values, spread across them rather than the first few."""
    if most <= 0:
        return []
    if len(values) <= most:
        return list(values)
    if most == 1:
        return [values[len(values) // 2]]
    step = (len(values) - 1) / (most - 1)
    return [values[int(index * step + 0.5)] for index in range(most)]


def clearest(pictures: Sequence[bytes]) -> int:
    """Which of a few frames taken a moment apart is the one to read.

    A frame in a wipe or a dissolve is unlike the frames either side of it, and a
    frame caught mid-pan or mid-fade is soft. So of the frames that are at least half
    as sharp as the sharpest, the steadiest - the one most like a neighbour - is
    read, and of two equally steady the sharper. A picture that cannot be opened is
    never chosen while another can be.
    """
    if len(pictures) <= 1:
        return 0
    greys = [_grey(picture) for picture in pictures]
    usable = [index for index, grey in enumerate(greys) if grey is not None]
    if not usable:
        return 0
    sharp = {index: _sharpness(greys[index]) for index in usable}  # type: ignore[arg-type]
    best = max(sharp.values())
    steady: dict[int, float] = {}
    for index in usable:
        here = greys[index]
        assert here is not None
        near = [
            float(np.mean(np.abs(here - other)))
            for other in (
                greys[index - 1] if index > 0 else None,
                greys[index + 1] if index + 1 < len(greys) else None,
            )
            if other is not None and other.shape == here.shape
        ]
        steady[index] = min(near) if near else 255.0
    eligible = [index for index in usable if sharp[index] >= 0.5 * best] or usable
    return min(eligible, key=lambda index: (round(steady[index], 1), -sharp[index]))


# The size frames are compared and judged at: small enough to be quick, large enough
# that a caption's edges still count towards how sharp a frame is.
_COMPARE_WIDTH = 320


def _grey(picture: bytes) -> np.ndarray | None:
    try:
        with Image.open(io.BytesIO(picture)) as image:
            grey = image.convert("L")
            height = max(1, round(grey.height * _COMPARE_WIDTH / max(1, grey.width)))
            return np.asarray(grey.resize((_COMPARE_WIDTH, height)), dtype=np.float32)
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def _sharpness(grey: np.ndarray) -> float:
    """The variance of the Laplacian: how much fine edge the picture holds."""
    if grey.shape[0] < 3 or grey.shape[1] < 3:
        return 0.0
    middle = grey[1:-1, 1:-1]
    edges = 4.0 * middle - grey[:-2, 1:-1] - grey[2:, 1:-1] - grey[1:-1, :-2] - grey[1:-1, 2:]
    return float(edges.var())


async def _run(
    command: list[str],
    *,
    timeout: float = 60.0,  # noqa: ASYNC109 — must live here; see the docstring
) -> tuple[int, bytes, bytes]:
    """Run a subprocess with a hard timeout.

    The timeout is not optional: ffmpeg on a malformed container can spin, and this
    runs inside a request budget measured in seconds. It is a parameter rather than an
    `asyncio.timeout` block at the call site because only the runner can kill the
    child — cancelling the await from outside would abandon a running ffmpeg, and a
    leaked decoder on a malicious upload is the denial-of-service the caps prevent.

    Run in a thread rather than through `asyncio.create_subprocess_exec`, because that
    call raises `NotImplementedError` on Windows under the selector event loop — which
    is the policy psycopg requires, so the two cannot coexist. A thread works under
    every loop and every platform, and ffmpeg invocations are rare and already far
    more expensive than the thread that hosts them.
    """
    try:
        # A fixed argument list, never a shell, and every element is either a literal
        # or a path this process created — no user string reaches the command line.
        completed = await asyncio.to_thread(
            subprocess.run,
            command,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        # `run` kills the child before raising, so nothing is left behind.
        raise VideoRejected("processing exceeded its time limit", kind="timeout") from None

    return completed.returncode, completed.stdout, completed.stderr


# Lets the JPEG writer take limited-range video (see `_scene_frames`).
_JPEG_COMPAT = ("-strict", "-1")


def ffmpeg_available() -> bool:
    """Whether the toolchain is present. Absence degrades; it does not crash."""
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


async def probe(path: Path) -> VideoProbe:
    """Read the container's own description before decoding anything."""
    code, stdout, _ = await _run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        timeout=20.0,
    )
    if code != 0:
        raise VideoRejected("not a readable video container")

    try:
        payload = json.loads(stdout)
        video_stream = next(
            stream for stream in payload["streams"] if stream.get("codec_type") == "video"
        )
    except (json.JSONDecodeError, KeyError, StopIteration) as exc:
        raise VideoRejected(f"no video stream found: {type(exc).__name__}") from exc

    return VideoProbe(
        duration_seconds=float(payload.get("format", {}).get("duration", 0.0)),
        width=int(video_stream.get("width", 0)),
        height=int(video_stream.get("height", 0)),
        codec=str(video_stream.get("codec_name", "unknown")),
        container=str(payload.get("format", {}).get("format_name", "unknown")),
    )


class KeyframeExtractor:
    """Extracts a bounded set of scene-change frames.

    With `read_seconds`, also the frames to read what the clip shows (`FramesRead`):
    up to `read_frames` of them across its first `read_seconds`. The keyframes for the
    picture checks are taken exactly as before either way.
    """

    def __init__(
        self,
        *,
        max_seconds: int = DEFAULT_MAX_SECONDS,
        max_keyframes: int = DEFAULT_MAX_KEYFRAMES,
        max_height: int = DEFAULT_MAX_HEIGHT,
        read_seconds: int | None = None,
        read_frames: int = READ_FRAMES,
    ) -> None:
        self._max_seconds = max_seconds
        self._max_keyframes = max_keyframes
        self._max_height = max_height
        self._read_seconds = read_seconds
        self._read_frames = read_frames

    @classmethod
    def reading(cls, *, quick: bool = False, read_seconds: int | None = None) -> KeyframeExtractor:
        """The extractor for a check that reads the clip: ten minutes and 24 frames in
        the background, 90 seconds and eight in a quick check."""
        if quick:
            return cls(
                read_seconds=min(read_seconds or QUICK_READ_SECONDS, QUICK_READ_SECONDS),
                read_frames=QUICK_READ_FRAMES,
            )
        return cls(read_seconds=read_seconds or READ_SECONDS, read_frames=READ_FRAMES)

    async def extract(self, data: bytes) -> ExtractedVideo:
        """Decode a bounded prefix and return its scene-change frames."""
        if not ffmpeg_available():
            return ExtractedVideo(probe=None, reason="unavailable: ffmpeg is not installed")

        limitations: list[str] = []

        with tempfile.TemporaryDirectory(prefix="factify-video-") as workspace:
            root = Path(workspace)
            source = root / "input"
            # Off the event loop: an upload can be tens of megabytes, and writing it
            # inline would stall every other in-flight request for the duration.
            await asyncio.to_thread(source.write_bytes, data)

            try:
                description = await probe(source)
            except VideoRejected as rejected:
                return ExtractedVideo(probe=None, reason=rejected.reason)

            truncated = description.duration_seconds > self._max_seconds
            if truncated:
                limitations.append(
                    f"analysed the first {self._max_seconds}s of "
                    f"{description.duration_seconds:.0f}s"
                )

            frames = await self._scene_frames(source, root, limitations)

            if not frames:
                # A single-shot clip has no cuts - a phone video of one scene, the
                # commonest forward there is. Three frames spread across it are taken
                # instead, and the limitation says so, rather than calling them
                # keyframes or checking nothing.
                frames = await self._spread_frames(
                    source, root, min(description.duration_seconds, self._max_seconds)
                )
                if frames:
                    limitations.append("no scene changes; three evenly spaced frames were used")

            if not frames:
                # Nothing to say rather than a guess.
                return ExtractedVideo(
                    probe=description,
                    truncated=truncated,
                    limitations=tuple(limitations),
                    reason="no scene-change frames could be extracted",
                )

            seconds = min(description.duration_seconds, self._max_seconds)
            even = await self._even_frames(source, root, seconds)
            read = (
                await self._frames_to_read(source, root, description.duration_seconds)
                if self._read_seconds
                else None
            )

            event(
                logger,
                "keyframes extracted",
                module="media.video",
                outcome="ok",
                frames=len(frames),
                even_frames=len(even),
                read_frames=len(read.frames) if read is not None else None,
                read_after_cuts=read.after_cuts if read is not None else None,
                read_window_s=round(read.window_seconds, 1) if read is not None else None,
                duration_s=round(description.duration_seconds, 1),
                truncated=truncated,
            )

            return ExtractedVideo(
                probe=description,
                keyframes=frames,
                even_frames=even,
                truncated=truncated,
                limitations=tuple(limitations),
                read=read,
            )

    async def _frames_to_read(self, source: Path, workspace: Path, duration: float) -> FramesRead:
        """The frames that show what the clip is, across its read window (`FramesRead`).

        Never raises: a clip whose frames cannot be taken says why in `reason`.
        """
        assert self._read_seconds is not None
        window = min(duration, float(self._read_seconds))
        if window <= 0:
            return FramesRead(duration_seconds=duration, reason="the video has no length")
        try:
            cuts = await self._cut_times(source, window)
        except VideoRejected:
            # Out of time: the frames are spread evenly instead.
            cuts = []
        moments, after_cuts = reading_moments(window, most=self._read_frames, cuts=cuts)
        folder = workspace / "read"
        folder.mkdir()
        gate = asyncio.Semaphore(READ_CONCURRENCY)

        async def taken(index: int, moment: float) -> Keyframe | None:
            async with gate:
                return await self._clearest_near(source, folder, index, moment, duration)

        found = await asyncio.gather(
            *(taken(index, moment) for index, moment in enumerate(moments))
        )
        frames = tuple(frame for frame in found if frame is not None)
        return FramesRead(
            frames=frames,
            window_seconds=round(window, 2),
            duration_seconds=round(duration, 2),
            after_cuts=after_cuts,
            reason=None if frames else "no frame could be taken from the video",
        )

    async def _cut_times(self, source: Path, window: float) -> list[float]:
        """When the picture changes in the read window, in seconds: one decoding pass.

        Only the reference frames are decoded (`-skip_frame noref`), which is enough
        to see a cut and saves most of the work on a long clip.
        """
        code, _, stderr = await _run(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostdin",
                "-v",
                "info",
                "-skip_frame",
                "noref",
                "-t",
                f"{window:.3f}",
                "-i",
                str(source),
                "-an",
                "-sn",
                "-vf",
                f"select='gt(scene,{SCENE_THRESHOLD})',showinfo",
                "-f",
                "null",
                "-",
            ],
            timeout=pass_timeout(window),
        )
        if code != 0:
            return []
        times = sorted(
            {
                round(float(found), 2)
                for line in stderr.decode("utf-8", "replace").splitlines()
                if "showinfo" in line
                for found in _PTS_TIME.findall(line)
            }
        )
        return _thinned(times, MAX_CUTS)

    async def _clearest_near(
        self, source: Path, folder: Path, index: int, moment: float, duration: float
    ) -> Keyframe | None:
        """The clearest of a few frames taken a moment apart around `moment`; None when
        none could be taken. Never raises: one frame lost is not the video lost, and a
        file error here used to fail every frame of the check through `gather`."""
        try:
            return await self._clearest_frame(source, folder, index, moment, duration)
        except Exception:
            logger.exception("a frame to read could not be taken at %.1fs", moment)
            return None

    async def _clearest_frame(
        self, source: Path, folder: Path, index: int, moment: float, duration: float
    ) -> Keyframe | None:
        span = CANDIDATE_STEP_SECONDS * (CANDIDATES - 1)
        start = max(0.0, moment - span / 2)
        if duration > 0 and start + span > duration - 0.05:
            start = max(0.0, duration - 0.05 - span)
        pattern = folder / f"at-{index:03d}-%d.jpg"
        try:
            code, _, _ = await _run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-ss",
                    f"{start:.3f}",
                    "-i",
                    str(source),
                    "-t",
                    f"{span + 0.1:.3f}",
                    "-an",
                    "-vf",
                    f"fps={1 / CANDIDATE_STEP_SECONDS:.4f},scale=-2:'min({READ_MAX_HEIGHT},ih)'",
                    "-frames:v",
                    str(CANDIDATES),
                    "-q:v",
                    "2",
                    *_JPEG_COMPAT,
                    str(pattern),
                ],
                timeout=30.0,
            )
        except VideoRejected:
            return None
        if code != 0:
            return None

        def collect() -> list[bytes]:
            return [
                path.read_bytes()
                for path in sorted(
                    folder.glob(f"at-{index:03d}-*.jpg"),
                    key=lambda path: int(path.stem.rsplit("-", 1)[1]),
                )
            ]

        candidates = await asyncio.to_thread(collect)
        if not candidates:
            return None
        chosen = await asyncio.to_thread(clearest, candidates)
        taken_at = start + chosen * CANDIDATE_STEP_SECONDS
        return Keyframe(index=index, timestamp_ms=int(taken_at * 1000), data=candidates[chosen])

    async def _scene_frames(
        self, source: Path, workspace: Path, limitations: list[str]
    ) -> tuple[Keyframe, ...]:
        """Ask ffmpeg for frames where the picture actually changes."""
        output = workspace / "frame-%03d.jpg"

        code, _, stderr = await _run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-t",
                str(self._max_seconds),
                "-i",
                str(source),
                "-vf",
                f"select='gt(scene,{SCENE_THRESHOLD})',scale=-2:{self._max_height}",
                "-vsync",
                "vfr",
                "-frames:v",
                str(self._max_keyframes),
                "-q:v",
                "3",
                # ffmpeg 8 refuses to write a JPEG from limited-range video without it
                # ("Non full-range YUV is non-standard"), and every keyframe was lost:
                # the face check then read three spread frames instead of up to twelve
                # (2026-10-01). Older ffmpeg accepts it and changes nothing.
                *_JPEG_COMPAT,
                str(output),
            ],
            timeout=90.0,
        )

        if code != 0:
            limitations.append(
                f"frame extraction reported an error: {stderr[:120].decode(errors='replace')}"
            )

        return await asyncio.to_thread(self._collect, workspace)

    async def _even_frames(
        self, source: Path, workspace: Path, seconds: float
    ) -> tuple[Keyframe, ...]:
        """`EVEN_FRAMES` frames spread evenly across the clip, in one pass."""
        if seconds <= 0:
            return ()
        folder = workspace / "even"
        folder.mkdir()
        code, _, _ = await _run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-t",
                str(self._max_seconds),
                "-i",
                str(source),
                "-vf",
                f"fps={EVEN_FRAMES / seconds:.5f},scale=-2:'min({EVEN_MAX_HEIGHT},ih)'",
                "-frames:v",
                str(EVEN_FRAMES),
                "-q:v",
                "3",
                *_JPEG_COMPAT,
                str(folder / "even-%03d.jpg"),
            ],
            timeout=90.0,
        )
        if code != 0:
            return ()

        def collect() -> tuple[Keyframe, ...]:
            paths = sorted(folder.glob("even-*.jpg"))
            step = seconds / max(len(paths), 1)
            return tuple(
                Keyframe(index=index, timestamp_ms=int(index * step * 1000), data=path.read_bytes())
                for index, path in enumerate(paths)
            )

        return await asyncio.to_thread(collect)

    async def _spread_frames(
        self, source: Path, workspace: Path, seconds: float
    ) -> tuple[Keyframe, ...]:
        """One frame at a tenth, half and nine tenths of the clip."""
        frames: list[Keyframe] = []
        for index, share in enumerate((0.1, 0.5, 0.9)):
            moment = max(0.0, seconds * share)
            target = workspace / f"spread-{index}.jpg"
            code, _, _ = await _run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-ss",
                    f"{moment:.2f}",
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    "-vf",
                    f"scale=-2:{self._max_height}",
                    "-q:v",
                    "3",
                    *_JPEG_COMPAT,
                    str(target),
                ],
                timeout=30.0,
            )
            if code == 0 and target.exists():
                data = await asyncio.to_thread(target.read_bytes)
                frames.append(Keyframe(index=index, timestamp_ms=int(moment * 1000), data=data))
        return tuple(frames)

    @staticmethod
    def _collect(workspace: Path) -> tuple[Keyframe, ...]:
        """Read the written frames off disk. Threaded, like the write that fed it."""
        return tuple(
            Keyframe(
                index=index,
                # Approximate: scene-change output does not carry precise timestamps
                # without a second pass, and an approximate anchor into a 90-second
                # clip is still far better than none.
                timestamp_ms=0,
                data=path.read_bytes(),
            )
            for index, path in enumerate(sorted(workspace.glob("frame-*.jpg")))
        )
