"""Media matching (M33).

Stage one of media verification: free, fast, and correct for content we have already
seen. A hit here answers "is this recycled?" without spending a single external unit.

The whole module is shaped by one sentence from the plan: **a false media match is
the worst possible failure, because it produces a confident, cited, wrong answer.**
Everything below follows from taking that seriously.

  - A 64-bit hash proposes candidates. It never concludes. Two unrelated photographs
    of a crowd can land within a few bits of each other.
  - Every candidate is verified by image embedding before it can become evidence,
    and the embedding is itself only a *verification* — it cannot be decisive alone
    either, because CLIP scores two different pictures of the same kind of scene at
    0.956 (M23).
  - Even a verified match is not evidence until a **source date** exists. "This image
    appeared somewhere before" is not a finding; "this image was published by Reuters
    on 14 March 2019" is.
  - Every attempt is recorded, misses included. The near-miss log is the only thing
    that makes threshold calibration possible later, and discarding it would leave
    the threshold permanently unjustified.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from app.embeddings.image import ImageEmbedder, UnavailableImageEmbedder
from app.media.hashing import CANDIDATE_DISTANCE, MediaFingerprint, PerceptualHash
from app.observability.logging import event

logger = logging.getLogger("factify.media.matching")


@dataclass(frozen=True, slots=True)
class StoredMedia:
    """A fingerprint already in the corpus, with whatever is known about it."""

    id: str
    sha256: str
    dhash: PerceptualHash | None = None
    phash: PerceptualHash | None = None
    embedding: tuple[float, ...] | None = None
    source_date: datetime | None = None
    citation_url: str | None = None
    publisher: str | None = None

    @property
    def is_dated(self) -> bool:
        """Whether a match against this could ever become evidence."""
        return self.source_date is not None and bool(self.citation_url)


@dataclass(frozen=True, slots=True)
class MatchAttempt:
    """One comparison, whatever its outcome.

    Recorded for every candidate including rejections — this is the near-miss log.
    """

    candidate_id: str
    metric: str
    distance: float
    threshold: float
    verified: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class MatchResult:
    """What local matching concluded, and everything it tried."""

    matched: StoredMedia | None = None
    method: str = ""
    similarity: float = 0.0
    attempts: tuple[MatchAttempt, ...] = ()
    candidates_considered: int = 0
    reason: str = ""

    @property
    def found(self) -> bool:
        return self.matched is not None

    @property
    def is_citable(self) -> bool:
        """A match becomes evidence only when it carries a dated citation.

        Without this, 'we have seen this image before' would be presented as a
        finding, when the finding is always about *when* and *where*.
        """
        return self.matched is not None and self.matched.is_dated


# The threshold a candidate must clear *after* surviving the pHash gate — which is a
# different population from the one M23 calibrated 0.96 against, and therefore a
# different number. Measured on 22 real photographs, 66 re-share variants (hard
# downscale + q55, screenshot re-encode, 8% crop) and 231 cross-image pairs:
#
#   the pHash gate at <=12 admitted   53 of 66 same-picture variants
#                          and only    2 of 231 different-picture pairs
#   same-picture scores past the gate  0.8829 - 1.0000, median 0.9642
#   different-picture scores past it   0.8649 and 0.9188
#
# So the hash gate, not the embedding, is what rejects unrelated images: 229 of 231
# never reach this comparison at all. Holding 0.96 here discards 55% of genuine
# re-shares to re-reject a population that was already gone, which is the flagship
# recycled-photograph case failing silently.
#
# 0.93 keeps 50 of 66 with no false match and 0.0112 of margin over the highest
# surviving impostor. The negative sample is only two pairs, so this is provisional
# and re-measured against the real corpus once it carries volume — recorded in
# docs/ops-notes.md rather than left as a bare constant.
VERIFICATION_THRESHOLD = 0.93


class LocalMatcher:
    """Stage one: exact identity, then hash candidates, then embedding verification."""

    def __init__(
        self,
        *,
        embedder: ImageEmbedder | UnavailableImageEmbedder,
        candidate_distance: int = CANDIDATE_DISTANCE,
        verification_threshold: float = VERIFICATION_THRESHOLD,
    ) -> None:
        self._embedder = embedder
        self._candidate_distance = candidate_distance
        self._verification_threshold = verification_threshold

    def match(
        self,
        fingerprint: MediaFingerprint,
        *,
        corpus: list[StoredMedia],
        query_embedding: tuple[float, ...] | None = None,
    ) -> MatchResult:
        """Find whether this image is already known.

        Returns the attempts alongside the result so the caller can persist misses;
        a matcher that only reported successes would be untunable.
        """
        attempts: list[MatchAttempt] = []

        # Exact bytes. The one identifier that is proof by itself, so it short-
        # circuits before any approximate comparison.
        for stored in corpus:
            if stored.sha256 == fingerprint.sha256:
                attempts.append(
                    MatchAttempt(
                        candidate_id=stored.id,
                        metric="sha256",
                        distance=0.0,
                        threshold=0.0,
                        verified=True,
                    )
                )
                return MatchResult(
                    matched=stored,
                    method="exact_hash",
                    similarity=1.0,
                    attempts=tuple(attempts),
                    candidates_considered=1,
                )

        candidates = self._shortlist(fingerprint, corpus, attempts)

        if not candidates:
            return MatchResult(
                attempts=tuple(attempts),
                candidates_considered=len(corpus),
                reason="no perceptual-hash candidate within range",
            )

        if query_embedding is None:
            # Refusing rather than falling back to hash distance. Accepting a
            # candidate here would be exactly the collision this module exists to
            # catch — a confident, cited, wrong answer.
            return MatchResult(
                attempts=tuple(attempts),
                candidates_considered=len(candidates),
                reason=(
                    f"{len(candidates)} hash candidate(s) found but no embedding was "
                    "available to verify them; a hash match alone is not a match"
                ),
            )

        return self._verify(candidates, query_embedding, attempts, considered=len(corpus))

    def _shortlist(
        self,
        fingerprint: MediaFingerprint,
        corpus: list[StoredMedia],
        attempts: list[MatchAttempt],
    ) -> list[tuple[StoredMedia, int]]:
        """Hash candidates, using whichever hash the stored item carries.

        pHash is preferred where both exist: it survives cropping, which is what
        happens to an image on its third re-share.
        """
        shortlist: list[tuple[StoredMedia, int]] = []

        for stored in corpus:
            distance: int | None = None
            metric = ""

            if stored.phash is not None:
                distance = fingerprint.phash.distance(stored.phash)
                metric = "phash_hamming"
            elif stored.dhash is not None:
                distance = fingerprint.dhash.distance(stored.dhash)
                metric = "dhash_hamming"

            if distance is None:
                continue

            within = distance <= self._candidate_distance
            if not within:
                # Recorded even though it lost: the distribution of rejections is
                # what a threshold is calibrated against.
                attempts.append(
                    MatchAttempt(
                        candidate_id=stored.id,
                        metric=metric,
                        distance=float(distance),
                        threshold=float(self._candidate_distance),
                        verified=False,
                        reason="outside candidate range",
                    )
                )
                continue

            shortlist.append((stored, distance))

        shortlist.sort(key=lambda pair: pair[1])
        return shortlist

    def _verify(
        self,
        candidates: list[tuple[StoredMedia, int]],
        query_embedding: tuple[float, ...],
        attempts: list[MatchAttempt],
        *,
        considered: int,
    ) -> MatchResult:
        """Verify each candidate visually. Hash distance decides nothing here."""
        for stored, hash_distance in candidates:
            if stored.embedding is None:
                attempts.append(
                    MatchAttempt(
                        candidate_id=stored.id,
                        metric="phash_hamming",
                        distance=float(hash_distance),
                        threshold=float(self._candidate_distance),
                        verified=False,
                        reason="candidate has no embedding to verify against",
                    )
                )
                continue

            verification = self._embedder.verify(
                query_embedding, stored.embedding, threshold=self._verification_threshold
            )

            attempts.append(
                MatchAttempt(
                    candidate_id=stored.id,
                    metric="clip_cosine",
                    distance=verification.similarity,
                    threshold=verification.threshold,
                    verified=verification.verified,
                    reason=verification.reason or "",
                )
            )

            if verification.verified:
                event(
                    logger,
                    "media match verified",
                    module="media.matching",
                    outcome="ok",
                    hash_distance=hash_distance,
                    similarity=round(verification.similarity, 4),
                    dated=stored.is_dated,
                )
                return MatchResult(
                    matched=stored,
                    method="near_duplicate_verified",
                    similarity=verification.similarity,
                    attempts=tuple(attempts),
                    candidates_considered=considered,
                )

        return MatchResult(
            attempts=tuple(attempts),
            candidates_considered=considered,
            reason=(
                f"{len(candidates)} hash candidate(s) failed visual verification; "
                "a perceptual hash alone does not identify an image"
            ),
        )
