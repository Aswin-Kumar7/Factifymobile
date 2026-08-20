"""Media verification wiring — turning an uploaded image into something answerable.

`/v1/verify/file` called `orchestrator.verify(intake, claims=[])`, and resolvers run
per claim, so an image submitted for verification ran **no checks at all**: no
provenance read, no fingerprint, no match attempt. Six images returned six clean
200s with nothing in them, which reads exactly like six images that were checked and
found unremarkable.

Two things are needed and neither existed. An image has to become a claim before
anything can be said about it, and the media resolvers take their findings at
construction — the provenance report and the match result are computed per request,
not held for the life of the process.

**The claim this builds is deliberately narrow.** An image asserts nothing on its own;
what a forward asserts is that the picture shows what the caption says, and there is
no caption here. So the claim is about the image's provenance and prior publication —
the only questions a picture alone can be asked — and it is phrased that way rather
than as a proposition about the world that nothing could settle.
"""

from __future__ import annotations

import logging
import os
from contextlib import suppress
from typing import Any

from app.domain.claim import Claim, ClaimAnchor
from app.domain.enums import ClaimType, Importance, Severity
from app.embeddings.image import ImageEmbedder, UnavailableImageEmbedder
from app.intake.normalizer import NormalisedIntake
from app.media import provenance
from app.media.hashing import HashFailed, fingerprint
from app.media.matching import LocalMatcher, StoredMedia
from app.observability.logging import event
from app.sources.base import SourceResolver
from app.sources.media import MediaMatchResolver, ProvenanceResolver

logger = logging.getLogger("facify.orchestration.media")

# How much of the fingerprint corpus to compare against. `LocalMatcher` shortlists by
# Hamming distance in memory, so this bounds the work rather than the accuracy.
CORPUS_LIMIT = 5000


class MediaVerification:
    """Prepares the claim and the resolvers for one uploaded image."""

    def __init__(
        self,
        *,
        database: Any,
        embedder: ImageEmbedder | UnavailableImageEmbedder | None = None,
    ) -> None:
        self._database = database
        self._embedder = embedder or UnavailableImageEmbedder()

    async def prepare(
        self, intake: NormalisedIntake
    ) -> tuple[list[Claim], list[SourceResolver]]:
        """Everything needed to verify this image, or nothing if it is not one."""
        primary = intake.primary
        if not primary.is_media or primary.data is None:
            return [], []

        try:
            marks = fingerprint(primary.data)
        except HashFailed as error:
            # An unreadable image is not a suspicious one. No claim is raised, so the
            # case abstains rather than reporting a forensic finding about a file we
            # could not decode.
            event(
                logger,
                "image could not be fingerprinted",
                module="orchestration.media",
                outcome="skipped",
                failure_reason=str(error),
            )
            return [], []

        # Provenance is read directly from the bytes. A missing manifest means
        # unknown, never fakery — most genuine photographs carry no C2PA manifest.
        report = provenance.read(primary.data, filename=primary.sha256)

        corpus = await self._stored_media()
        matcher = LocalMatcher(embedder=self._embedder)
        result = matcher.match(
            marks, corpus=corpus, query_embedding=self._embed(primary.data)
        )

        event(
            logger,
            "image prepared for verification",
            module="orchestration.media",
            outcome="ok",
            corpus_size=len(corpus),
            matched=result.matched is not None,
            has_manifest=report.present,
        )

        claim = Claim(
            id=f"claim:media:{primary.sha256[:32]}",
            text=(
                "This image has been published before, at a date and by a publisher "
                "that can be cited."
            ),
            claim_type=ClaimType.MEDIA,
            severity=Severity.MEDIUM,
            importance=Importance.MAIN_THESIS,
            anchor=ClaimAnchor(
                input_kind="image",
                content_hash=primary.sha256,
                char_start=0,
            ),
            language=intake.language.language.value,
        )

        resolvers: list[SourceResolver] = [
            ProvenanceResolver(report=report),
            MediaMatchResolver(result=result),
        ]
        return [claim], resolvers

    def _embed(self, data: bytes) -> tuple[float, ...] | None:
        """CLIP vector for the uploaded image, or `None`.

        Required, not optional: `LocalMatcher` refuses to confirm a near-duplicate
        without one, so passing `None` meant only byte-identical images could ever
        match. Every forward is recompressed on its way through a chat app, so that
        limit excluded the entire case this feature exists for — the original matched
        and a 480px re-save of it did not.

        `None` when the model is unavailable, which keeps the refusal intact rather
        than substituting a weaker comparison.
        """
        import tempfile

        # The embedder reads from disk, and the upload only exists in memory.
        with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as handle:
            handle.write(data)
            path = handle.name

        try:
            outcome = self._embedder.embed([path])
        finally:
            with suppress(OSError):
                os.unlink(path)

        return outcome.vectors[0] if outcome.vectors else None

    async def _stored_media(self) -> list[StoredMedia]:
        """The fingerprint corpus to compare against.

        Currently empty in this deployment — `media_fingerprint` holds no rows,
        because nothing populates it yet. That is reported honestly rather than
        hidden: with an empty corpus every image correctly finds no match, and the
        response says no earlier publication was found rather than implying the
        picture is new.
        """
        from app.media.hashing import PerceptualHash

        async with self._database.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT id::text, sha256, phash::text AS phash, embedding::text AS embedding,
                       source_date, citation_url
                  FROM facify.media_fingerprint
                 WHERE sha256 IS NOT NULL
                 LIMIT %s
                """,
                (CORPUS_LIMIT,),
            )
            rows = list(await cursor.fetchall())

        stored: list[StoredMedia] = []
        for row in rows:
            stored.append(
                StoredMedia(
                    id=str(row["id"]),
                    sha256=str(row["sha256"]),
                    # Stored as bit(64); the algorithm travels with the value because
                    # `PerceptualHash.distance` refuses to compare across algorithms.
                    # The table carries phash only — there is no dhash column, so the
                    # matcher shortlists on phash alone here.
                    phash=(
                        PerceptualHash.from_bit_string(str(row["phash"]), "phash")
                        if row.get("phash")
                        else None
                    ),
                    embedding=_vector(row.get("embedding")),
                    source_date=row.get("source_date"),
                    citation_url=row.get("citation_url"),
                )
            )
        return stored


def _vector(raw: object) -> tuple[float, ...] | None:
    """Parse a pgvector literal back into floats.

    Returned as text by the query because psycopg has no native adapter registered
    for the type here. A row with no embedding yields `None`, which the matcher reads
    as "cannot be verified" rather than as "does not match".
    """
    if not raw:
        return None
    try:
        return tuple(float(part) for part in str(raw).strip("[]").split(",") if part)
    except ValueError:
        return None
