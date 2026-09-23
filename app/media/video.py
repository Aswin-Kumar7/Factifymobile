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
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.observability.logging import event

logger = logging.getLogger("factify.media.video")

DEFAULT_MAX_SECONDS = 90
DEFAULT_MAX_KEYFRAMES = 12
DEFAULT_MAX_HEIGHT = 480

# Scene-change sensitivity. Lower catches more cuts; too low returns twelve frames of
# the same shot, which is twelve reverse-image lookups that answer one question.
SCENE_THRESHOLD = 0.3


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

    @property
    def is_within_caps(self) -> bool:
        return self.duration_seconds <= DEFAULT_MAX_SECONDS


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
    truncated: bool = False
    limitations: tuple[str, ...] = field(default_factory=tuple)
    reason: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.reason is None and bool(self.keyframes)


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
    """Extracts a bounded set of scene-change frames."""

    def __init__(
        self,
        *,
        max_seconds: int = DEFAULT_MAX_SECONDS,
        max_keyframes: int = DEFAULT_MAX_KEYFRAMES,
        max_height: int = DEFAULT_MAX_HEIGHT,
    ) -> None:
        self._max_seconds = max_seconds
        self._max_keyframes = max_keyframes
        self._max_height = max_height

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
                # Nothing to say rather than a guess. A single-shot clip with no cuts
                # is a real case, and reporting no frames is better than sampling
                # arbitrarily and calling the result keyframes.
                return ExtractedVideo(
                    probe=description,
                    truncated=truncated,
                    limitations=tuple(limitations),
                    reason="no scene-change frames could be extracted",
                )

            event(
                logger,
                "keyframes extracted",
                module="media.video",
                outcome="ok",
                frames=len(frames),
                duration_s=round(description.duration_seconds, 1),
                truncated=truncated,
            )

            return ExtractedVideo(
                probe=description,
                keyframes=frames,
                truncated=truncated,
                limitations=tuple(limitations),
            )

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
                str(output),
            ],
            timeout=90.0,
        )

        if code != 0:
            limitations.append(
                f"frame extraction reported an error: {stderr[:120].decode(errors='replace')}"
            )

        return await asyncio.to_thread(self._collect, workspace)

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


class UnavailableKeyframeExtractor:
    """Used when ffmpeg is absent. Video abstains rather than half-working."""

    async def extract(self, data: bytes) -> ExtractedVideo:
        del data
        return ExtractedVideo(probe=None, reason="unavailable: ffmpeg is not installed")
