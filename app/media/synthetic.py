"""The AI-generation and face-swap signal (2026-09-27).

A hosted detector (Sightengine's `genai` and `deepfake` models) reads a picture and
returns two likelihoods: that a generator made it, and that a face in it was swapped or
AI-modified. They answer the problem the platform is named for - synthetic media - and
they are the weakest kind of signal this product shows: a classifier's estimate,
calibrated on someone else's data, degraded by the recompression every forward goes
through. So they are handled exactly like the forensic panel (`forensics.py`):

  - they leave this module only as `Advisory` objects, which no verdict function
    accepts, so they can never make anything True or False;
  - they are shown as what they are - "a detector's estimate" - with the number, and
    never rounded into a label like "fake";
  - a detector that cannot be reached says so; it never reads as "not AI-generated".

Since 2026-09-28 the detectors run on our own server (`app/media/detectors`): an
AI-picture model, a voice model for a video's sound, and - when switched on - a
second picture model that must agree and a face-swap model. The hosted detector is kept
as an option; a picture read on our server is never sent anywhere.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.domain.enums import SyntheticSignal
from app.domain.evidence import Advisory
from app.governor.governor import Governor, ProviderUnavailable
from app.observability.logging import event
from app.security.fetcher import FetchResult, SecureFetcher

logger = logging.getLogger("factify.media.synthetic")

PROVIDER = "synthetic"
VERSION = "sightengine.genai+deepfake"
MODELS = "genai,deepfake"

# At or above these a signal is raised as a suspicion. Sightengine's own guidance is
# 0.5 for both; set higher here because a false "AI-made" on a real photograph is the
# costlier error for a person deciding whether to believe it. Our own models carry
# their own boundaries on each reading (`generated_at`, ...), set from their makers'
# calibration and our measurements (scripts/eval_models.py).
GENERATED_AT = 0.7
FACE_SWAP_AT = 0.7
SECOND_AT = 0.5
VOICE_AT = 0.5

# What the two AI-picture models said together.
LIKELY_AI = "likely_ai"
UNCLEAR = "unclear"
NO_SIGN = "no_sign"


@dataclass(frozen=True, slots=True)
class SyntheticReading:
    """What the detectors said about one picture or clip, or why they said nothing."""

    generated: float | None = None
    face_swap: float | None = None
    reason: str | None = None
    # A second AI-picture model, which must agree before anything is called likely
    # AI-made: detectors differ by 20-40 points on the same generator (DailyBench).
    second_opinion: float | None = None
    generated_at: float = GENERATED_AT
    second_at: float = SECOND_AT
    face_swap_at: float = FACE_SWAP_AT
    # How many faces the face model judged; None when the face check did not run.
    faces: int | None = None
    # A video's sound: the likelihood that the voice was made by a speech generator.
    voice: float | None = None
    voice_at: float = VOICE_AT
    # Read by our own models, on our own server.
    on_server: bool = False
    models: tuple[str, ...] = ()

    @property
    def checked(self) -> bool:
        return self.reason is None

    @property
    def outcome(self) -> str | None:
        """likely_ai only when every AI-picture model that read it agrees; unclear when
        they disagree. Never "real": a detector that sees nothing proves nothing."""
        if self.generated is None:
            return None
        votes = [self.generated >= self.generated_at]
        if self.second_opinion is not None:
            votes.append(self.second_opinion >= self.second_at)
        if all(votes):
            return LIKELY_AI
        if any(votes):
            return UNCLEAR
        return NO_SIGN

    def advisories(self, *, artifact_ref: str) -> tuple[Advisory, ...]:
        """The reading as advisories - the only form in which it leaves this module."""
        version = "+".join(self.models) if self.models else VERSION
        found: list[Advisory] = []
        if self.generated is not None:
            estimate = (
                f"Two AI-image detectors on our server read this picture: {self.generated:.0%} "
                f"and {self.second_opinion:.0%} likely made by an image generator"
                if self.second_opinion is not None
                else f"An AI-image detector estimates a {self.generated:.0%} likelihood "
                "that this picture was made by an image generator"
            )
            found.append(
                Advisory(
                    id=f"adv:generated:{artifact_ref}",
                    provider="ai_generation",
                    signal=(
                        SyntheticSignal.ADVISORY_SUSPICION
                        if self.outcome == LIKELY_AI
                        else SyntheticSignal.NO_SIGNAL
                    ),
                    note=f"{estimate}. A detector's estimate, not a finding.",
                    score=round(self.generated, 4),
                    provider_version=version,
                    artifact_ref=artifact_ref,
                )
            )
        if self.face_swap is not None:
            found.append(
                Advisory(
                    id=f"adv:face_swap:{artifact_ref}",
                    provider="face_swap",
                    signal=(
                        SyntheticSignal.ADVISORY_SUSPICION
                        if self.face_swap >= self.face_swap_at
                        else SyntheticSignal.NO_SIGNAL
                    ),
                    note=(
                        f"A deepfake detector estimates a {self.face_swap:.0%} likelihood "
                        "that a face in this picture was swapped or AI-modified. A "
                        "detector's estimate, not a finding."
                    ),
                    score=round(self.face_swap, 4),
                    provider_version=version,
                    artifact_ref=artifact_ref,
                )
            )
        if self.voice is not None:
            found.append(
                Advisory(
                    id=f"adv:voice:{artifact_ref}",
                    provider="cloned_voice",
                    signal=(
                        SyntheticSignal.ADVISORY_SUSPICION
                        if self.voice >= self.voice_at
                        else SyntheticSignal.NO_SIGNAL
                    ),
                    note=(
                        f"A voice detector estimates a {self.voice:.0%} likelihood that the "
                        "speech in this video was made by a speech generator. Experimental, "
                        "and weak on Hindi and on forwarded audio: an estimate, not a finding."
                    ),
                    score=round(self.voice, 4),
                    provider_version=version,
                    artifact_ref=artifact_ref,
                )
            )
        return tuple(found)


class SightengineDetector:
    """Asks Sightengine's `genai` and `deepfake` models about one picture."""

    def __init__(
        self,
        *,
        fetcher: SecureFetcher,
        governor: Governor,
        endpoint: str,
        account: str,
        secret: str,
    ) -> None:
        self._fetcher = fetcher
        self._governor = governor
        self._endpoint = endpoint
        self._account = account
        self._secret = secret

    async def read(self, image: bytes, *, mime: str = "image/jpeg") -> SyntheticReading:
        try:
            await self._governor.acquire(PROVIDER)
        except ProviderUnavailable as unavailable:
            return SyntheticReading(reason=f"unavailable: {unavailable.reason.value}")

        response = await self._fetcher.post_multipart(
            self._endpoint,
            {"models": MODELS, "api_user": self._account, "api_secret": self._secret},
            {"media": ("picture", image, mime)},
            provider=PROVIDER,
        )
        if not isinstance(response, FetchResult):
            return SyntheticReading(reason=f"provider failed: {response.reason}")

        reading = parse(response.text)
        event(
            logger,
            "synthetic media signal read",
            module="media.synthetic",
            outcome="ok" if reading.checked else "degraded",
            provider=PROVIDER,
            failure_reason=reading.reason,
        )
        return reading


def parse(body: str) -> SyntheticReading:
    """The two likelihoods from a response, or why there are none.

    A face-swap score is only present when there was a face to judge; its absence is
    "no face", never a score of zero.
    """
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return SyntheticReading(reason="unreadable provider response")
    if not isinstance(payload, dict) or payload.get("status") != "success":
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        message = error.get("message") if isinstance(error, dict) else None
        return SyntheticReading(reason=f"provider refused: {message or 'no reason given'}")

    kinds = payload.get("type") or {}
    return SyntheticReading(
        generated=_likelihood(kinds.get("ai_generated")),
        face_swap=_likelihood(kinds.get("deepfake")),
    )


def _likelihood(value: object) -> float | None:
    if isinstance(value, int | float) and 0 <= value <= 1:
        return float(value)
    return None


class UnavailableDetector:
    """Used when no detector is configured: says so, and reads nothing."""

    async def read(self, image: bytes, *, mime: str = "image/jpeg") -> SyntheticReading:
        del image, mime
        return SyntheticReading(reason="unavailable: no AI-image detector is configured")
