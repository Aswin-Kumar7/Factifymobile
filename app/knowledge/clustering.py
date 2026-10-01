"""Origin clustering (M26).

Counts independent sources, not articles. Twenty Indian outlets carrying one PTI wire
copy is **one** source wearing twenty mastheads, and without this rule corroboration
is theatre: a fabricated story picked up by a syndication network would look
overwhelmingly corroborated.

The clustering threshold is the whole difficulty. Set it too low and independent
reporting on the same event collapses into one origin, understating real
corroboration. Set it too high and lightly-edited reprints count separately,
overstating it. The default below is calibrated against the failure that matters
more: **overstating corroboration produces a confident wrong SUPPORTED**, while
understating it produces an abstention.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from app.knowledge.minhash import Signature, sign
from app.observability.logging import event

logger = logging.getLogger("factify.clustering")

# Estimated Jaccard above which two documents are treated as one origin.
#
# A wire reprint typically shares 60-90% of its shingles with the original: outlets
# change the headline, add a local first paragraph and cut the tail. Independently
# written coverage of the same event shares far less, because two journalists do not
# choose the same five-word windows.
#
# 0.5 sits between those populations and errs toward merging. Merging costs an
# understated origin count and therefore an abstention; not merging costs an
# overstated count and therefore a wrong SUPPORTED.
DEFAULT_THRESHOLD = 0.5


@dataclass(slots=True)
class Cluster:
    """A group of documents judged to share one origin."""

    id: str
    signature: Signature
    canonical_publisher: str | None = None
    canonical_url: str | None = None
    first_seen_at: datetime | None = None
    members: list[str] = field(default_factory=list)
    publishers: set[str] = field(default_factory=set)

    @property
    def member_count(self) -> int:
        return len(self.members)

    @property
    def is_multi_outlet(self) -> bool:
        """Carried by two or more distinct publishers — a real syndication event.

        This is the M26 gate: if the live corpus never produces one of these, either
        the threshold is mistuned or the feed mix is too narrow, and both are cheap
        to fix early and expensive to discover during evaluation.
        """
        return len(self.publishers) > 1


@dataclass(frozen=True, slots=True)
class Assignment:
    """Where a document landed, and how confident that placement was."""

    cluster_id: str
    similarity: float
    created_new: bool


class OriginClusterer:
    """Assigns documents to origin clusters by near-duplicate similarity.

    In-memory and linear: it compares a new document against known cluster
    representatives. At feed volumes — a few thousand recent items — that is
    milliseconds, and it avoids an LSH index whose parameters would be a second thing
    to calibrate. When the corpus outgrows it, banding is the change, not the concept.
    """

    def __init__(self, *, threshold: float = DEFAULT_THRESHOLD) -> None:
        self._threshold = threshold
        self._clusters: dict[str, Cluster] = {}
        self._counter = 0

    @property
    def clusters(self) -> tuple[Cluster, ...]:
        return tuple(self._clusters.values())

    def assign(
        self,
        *,
        document_id: str,
        text: str,
        publisher: str | None = None,
        url: str | None = None,
        published_at: datetime | None = None,
    ) -> Assignment:
        """Place a document in an existing cluster, or start a new one."""
        signature = sign(text)

        best_id: str | None = None
        best_similarity = 0.0

        for cluster_id, cluster in self._clusters.items():
            similarity = signature.similarity(cluster.signature)
            if similarity > best_similarity:
                best_id, best_similarity = cluster_id, similarity

        if best_id is not None and best_similarity >= self._threshold:
            cluster = self._clusters[best_id]
            cluster.members.append(document_id)
            if publisher:
                cluster.publishers.add(publisher)

            # The earliest known instance is the canonical one: in a syndication
            # wave the first publisher to carry it is the closest thing to an origin.
            if published_at and (
                cluster.first_seen_at is None or published_at < cluster.first_seen_at
            ):
                cluster.first_seen_at = published_at
                cluster.canonical_publisher = publisher or cluster.canonical_publisher
                cluster.canonical_url = url or cluster.canonical_url

            if cluster.is_multi_outlet:
                event(
                    logger,
                    "multi-outlet origin cluster",
                    module="knowledge.clustering",
                    outcome="ok",
                    similarity=round(best_similarity, 4),
                    publishers=len(cluster.publishers),
                    members=cluster.member_count,
                )

            return Assignment(cluster_id=best_id, similarity=best_similarity, created_new=False)

        self._counter += 1
        cluster_id = f"oc_{self._counter}"
        self._clusters[cluster_id] = Cluster(
            id=cluster_id,
            signature=signature,
            canonical_publisher=publisher,
            canonical_url=url,
            first_seen_at=published_at,
            members=[document_id],
            publishers={publisher} if publisher else set(),
        )

        return Assignment(cluster_id=cluster_id, similarity=best_similarity, created_new=True)

    def distinct_origins(self, document_ids: list[str]) -> int:
        """How many independent origins these documents represent.

        The number corroboration actually needs. A document not in any cluster counts
        as its own origin, so an unclustered set is not silently reported as zero.
        """
        if not document_ids:
            return 0

        wanted = set(document_ids)
        origins: set[str] = set()
        placed: set[str] = set()

        for cluster_id, cluster in self._clusters.items():
            members = wanted & set(cluster.members)
            if members:
                origins.add(cluster_id)
                placed |= members

        # Anything not in a cluster is its own origin.
        origins |= {f"unclustered:{doc}" for doc in wanted - placed}

        return len(origins)

    def multi_outlet_clusters(self) -> tuple[Cluster, ...]:
        """Clusters carried by more than one publisher — the gate's evidence."""
        return tuple(cluster for cluster in self._clusters.values() if cluster.is_multi_outlet)


@dataclass(frozen=True, slots=True)
class CorroborationCount:
    """Both numbers, because showing only one of them is the mistake.

    The interface renders "3 articles, 2 origin clusters" precisely so a reader can
    see the difference between coverage and confirmation.
    """

    documents: int
    origins: int

    @property
    def is_syndicated(self) -> bool:
        """More documents than origins means at least one reprint is in the set."""
        return self.documents > self.origins

    def __str__(self) -> str:
        return f"{self.documents} articles, {self.origins} independent origins"
