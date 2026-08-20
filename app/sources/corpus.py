"""Corpus retrieval — the evidence path the ingestion pipeline was built to feed.

Until this module existed, nothing queried `corpus_item`. The HNSW index on its
embedding column was created by the initial migration, 2,063 of 2,064 rows carry a
vector, and no code path ever ran a similarity search against them. Every verdict
therefore rested on the fact-check resolver alone, and the corpus was dead weight.

Retrieval here is **hybrid on purpose**, not as a nod to best practice:

  - Dense alone cannot serve a large share of real inputs. `app.embeddings.text`
    records that the model "cannot represent romanised Hindi at all", and romanised
    Hindi is ordinary in the forwards this system exists to check. For those claims
    the dense leg returns nothing and the lexical leg is the only retrieval there is.
  - Lexical alone misses paraphrase, which is most of how a claim travels.

The two legs are fused with Reciprocal Rank Fusion because it needs neither tuning
nor labelled data, and we have neither.

**Widening recall here is safe, and that is the whole point.** The evidence gate sits
downstream and is structural: `relate` must locate its excerpt inside text that was
actually fetched, `build_evidence` refuses a relation with no excerpt, and
`snapshot_id` is required. Retrieval can afford to be generous because no amount of
generosity can manufacture a citation. A system that generated its citations could
not make this trade.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.domain.claim import Claim
from app.domain.enums import EvidenceKind, Method, Relation, Tier
from app.embeddings.image import cosine
from app.embeddings.text import TextEmbedder
from app.extraction.web import extract
from app.knowledge.clustering import DEFAULT_THRESHOLD
from app.knowledge.minhash import Signature
from app.observability.logging import event
from app.security.fetcher import FetchResult, SecureFetcher
from app.sources.base import (
    SourceCandidate,
    SourceRelation,
    SourceSnapshot,
    insufficient,
    locate_excerpt,
)
from app.sources.corpus_text import is_navigation
from app.sources.reasoning import REASONER_VERSION, PassageReasoner, split_passages

logger = logging.getLogger("facify.sources.corpus")

NAME = "corpus"
VERSION = "2026.08.1"

# How many rows each leg contributes before fusion. Deliberately wider than the
# shortlist: fusion can only reorder what it is given, so starving a leg here is a
# recall loss no reranking recovers.
DENSE_K = 30
LEXICAL_K = 30

# The RRF constant. 60 is the value from the original formulation and is not tuned
# here — tuning it against our own corpus with no labelled set would be fitting noise.
RRF_K = 60

# Candidates that get fetched. Each one costs an HTTP round trip inside an 8 second
# budget, which is what bounds this rather than any property of the ranking.
SHORTLIST = 6

# Candidates that get *read* by the model, out of the shortlist above.
#
# Reading is metered and word overlap is not, which changes the arithmetic
# completely. One call per source per claim means a two-claim submission over the
# full shortlist is twelve calls plus extraction — roughly four verifications
# against a fifty-a-day cap, which is not a product.
#
# Three is where the value is. The shortlist is RRF-ordered, so the sources that
# actually answer the claim are at the top; positions four to six are the tail that
# usually produces NOT_RELEVANT. Those still get fetched and still get the lexical
# treatment, so nothing is dropped — it is judged more cheaply and more weakly, and
# the ledger records which mechanism was used.
REASONED_CANDIDATES = 3

# Recency windows, in days.
#
# Retrieval had no date handling at all: `published_at` was selected and carried but
# never filtered or ranked on, so a claim about this week could be answered with an
# article from 2019 — and the corpus does span back that far. For a system checking
# forwards, that is not a stale result, it is a wrong one, because the claim is
# almost always about something recent and an old article about the same subject is
# a different event.
#
# Two windows rather than one cutoff: the narrow window is what we want, the wide one
# is what we accept rather than abstaining. A fact-check published four months ago is
# still the right answer to a claim recirculating today.
RECENT_WINDOW_DAYS = 45
WIDE_WINDOW_DAYS = 365

# Below this many rows the narrow window is treated as too thin to rely on and the
# search widens. Set at the shortlist size: fewer candidates than we intend to fetch
# means the window, not the corpus, is the limit.
THIN_RESULT_COUNT = SHORTLIST

# Share of a claim's significant words that must appear in a sentence before that
# sentence is quotable as bearing on the claim. Two thresholds, because "this article
# says the same thing" and "this article is about the same thing" are different
# findings and collapsing them would overstate the weaker one.
SUPPORT_OVERLAP = 0.60
CONTEXT_OVERLAP = 0.35

# The semantic gate, and the reason it exists. Measured over the probe set:
#
#     case            truth    lexical   cosine
#     reworded        REAL        83%     0.85
#     hinglish        REAL        38%     0.71
#     entity          REAL       100%     0.69
#     verbatim        REAL        62%     0.64
#     paraphrase      REAL        40%     0.53   <- lowest true match
#     absent          FALSE       43%     0.45   <- highest false match
#     injection       FALSE       12%     0.21
#
# Lexical overlap **cannot** separate these: `absent` scores 43%, above two genuine
# matches. It found an article about a footbridge — just not the collapse the claim
# described — and word overlap has no way to tell those apart. Cosine does, with true
# matches bottoming out at 0.53 and false ones topping out at 0.45.
#
# 0.50 sits in that gap. The margin is narrow and the sample is seven cases, so this
# is a measured threshold rather than a validated one; widen the probe set before
# trusting it further. Erring low would admit topical near-misses as evidence, which
# is the failure that matters here.
SEMANTIC_GATE = 0.50

# Lexical bar used when no vector is available for the claim and the gate above
# cannot be evaluated. Raised to the support level: without the semantic check the
# only defence against a topical near-miss is demanding much heavier word coverage.
LEXICAL_ONLY_OVERLAP = 0.60

_STOP = frozenset(
    "the a an of to in on at for and or but is are was were be been being by with "
    "from as that this these those it its has have had will would could should may "
    "not no so if then than there here he she they them his her their our your".split()
)

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z0-9ऀ-ॿ]+")


def significant_words(text: str) -> set[str]:
    """Content words, lowercased. Devanagari is included in the word pattern so the
    Hindi path is not silently reduced to punctuation."""
    return {w for w in _WORD.findall(text.lower()) if len(w) > 2 and w not in _STOP}


def overlap(claim_text: str, candidate_text: str) -> float:
    """Share of the claim's significant words present in the candidate.

    Asymmetric on purpose: a long article containing every word of a short claim
    should score 1.0. Jaccard would punish it for being long, which is backwards for
    the question being asked here.
    """
    claim_words = significant_words(claim_text)
    if not claim_words:
        return 0.0
    return len(claim_words & significant_words(candidate_text)) / len(claim_words)


def reciprocal_rank_fusion(rankings: list[list[str]], *, k: int = RRF_K) -> dict[str, float]:
    """Fuse ranked id lists into one score per id.

    Rank-based rather than score-based because the two legs produce incomparable
    numbers — cosine distance and lexical overlap share no scale, and normalising
    them against each other would invent a relationship that does not exist.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for position, item_id in enumerate(ranking):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + position + 1)
    return scores


def best_sentence(claim_text: str, article_text: str) -> tuple[str, float]:
    """The sentence in a fetched article that best bears on the claim.

    Returned verbatim from the article, which is what makes it quotable: it is then
    passed to `locate_excerpt` as the needle, and a needle taken from the haystack is
    one that exact substring matching can actually find.

    This is the fix for a real failure. `locate_excerpt` matches exactly, and the
    extractor paraphrases, so passing the *claim* as the needle discarded almost
    everything as "not found". The sentence is the unit that exists in both places.
    """
    best, best_score = "", 0.0
    for sentence in _SENTENCE.split(article_text):
        cleaned = " ".join(sentence.split())
        if len(cleaned) < 40 or is_navigation(cleaned):
            continue
        score = overlap(claim_text, cleaned)
        if score > best_score:
            best, best_score = cleaned, score
    return best, best_score


class CorpusResolver:
    """Finds ingested articles that bear on a claim, and quotes them.

    Tier D and `EMBEDDING_SIMILARITY`: a news article matching a claim is real
    evidence and never decisive on its own. The tier is declared here rather than per
    item so that no run of this resolver can promote its own finding.
    """

    name = NAME
    version = VERSION
    allowed_domains: frozenset[str] = frozenset()

    tier = Tier.D
    kind = EvidenceKind.CORROBORATION
    # `ORIGIN_CLUSTER_COUNT`, not `EMBEDDING_SIMILARITY`. The distinction the
    # validators table draws is between candidate generation and a conclusion, and
    # embeddings do only the former here: they shortlist, then the page is fetched
    # and a sentence is anchored in it, and that anchored sentence is the finding.
    #
    # Declaring it decisive-capable does not make one article decisive. Rule 4
    # additionally requires `claim.independent_origin_count >= 2`, so a single
    # matching outlet still falls through to `rule.insufficient_origins`. The gate is
    # the origin count, which is computed below from stored clustering rather than
    # asserted here.
    method = Method.ORIGIN_CLUSTER_COUNT

    def __init__(
        self,
        *,
        database: Any,
        embedder: TextEmbedder | None = None,
        fetcher: SecureFetcher | None = None,
        shortlist: int = SHORTLIST,
        reasoner: PassageReasoner | None = None,
    ) -> None:
        self._database = database
        self._embedder = embedder
        self._fetcher = fetcher or SecureFetcher(timeout_seconds=8.0)
        self._shortlist = shortlist
        # Optional so the resolver still works with no model configured. Without it
        # `relate` falls back to word overlap, which is weaker and says so.
        self._reasoner = reasoner
        # Which fetched pages are cheap enough to read, keyed by content hash.
        #
        # `relate` receives a snapshot and not the candidate, so the shortlist rank
        # is not otherwise reachable from where the decision has to be made. The hash
        # identifies the page, so a concurrent request for the same page reaches the
        # same answer; the cap keeps a long-running process from accumulating one
        # entry per page it has ever seen.
        self._reasonable: dict[str, bool] = {}

    async def search(self, claim: Claim) -> list[tuple[dict[str, Any], float]]:
        """Run both legs, fuse, and return rows with their fused score, best first.

        Separate from `candidates` because the corroboration signal needs the same
        result set. Searching twice would double the database work and, worse, could
        return two different sets for one claim — so the count and the citations
        would describe different things.

        Recency is applied as a search window that widens only when the narrow one
        comes back thin, rather than as a score penalty. A penalty still returns the
        2019 article when nothing newer exists, just further down, and a candidate
        that reaches the shortlist gets fetched and quoted regardless of its rank.
        """
        rows, rankings = await self._legs(claim, within_days=RECENT_WINDOW_DAYS)

        if sum(len(r) for r in rankings) < THIN_RESULT_COUNT:
            wide_rows, wide_rankings = await self._legs(claim, within_days=WIDE_WINDOW_DAYS)
            if sum(len(r) for r in wide_rankings) > sum(len(r) for r in rankings):
                rows, rankings = wide_rows, wide_rankings
                event(
                    logger,
                    "recency window widened",
                    module="sources.corpus",
                    outcome="ok",
                    from_days=RECENT_WINDOW_DAYS,
                    to_days=WIDE_WINDOW_DAYS,
                )

        if not rankings:
            return []

        # Recency is expressed by the window above and **not** by a ranking leg.
        #
        # A date ranking was tried here and had to be removed: RRF weights every leg
        # equally, so ranking the whole result set by date made the newest article
        # a top candidate whatever it was about. A claim about a Kerala jail
        # retrieved an unrelated corruption arrest from the same afternoon, because
        # it was newer. Freshness is a filter on what is eligible, never a reason to
        # prefer one eligible source over a more relevant one.
        fused = reciprocal_rank_fusion(rankings)
        ordered = sorted(fused.items(), key=lambda pair: -pair[1])
        return [(rows[i], score) for i, score in ordered if rows.get(i, {}).get("canonical_url")]

    async def _legs(
        self, claim: Claim, *, within_days: int
    ) -> tuple[dict[str, dict[str, Any]], list[list[str]]]:
        """Both retrieval legs over one time window."""
        rows: dict[str, dict[str, Any]] = {}
        rankings: list[list[str]] = []

        async with self._database.connection() as conn:
            dense = await self._dense(conn, claim, within_days=within_days)
            if dense:
                rankings.append([r["id"] for r in dense])
                rows.update({r["id"]: r for r in dense})

            lexical = await self._lexical(conn, claim, within_days=within_days)
            if lexical:
                rankings.append([r["id"] for r in lexical])
                rows.update({r["id"]: r for r in lexical})

        return rows, rankings

    async def candidates(self, claim: Claim) -> list[SourceCandidate]:
        """Hybrid shortlist: dense and lexical legs, fused by rank."""
        found = await self.search(claim)
        ordered = [(row["id"], score) for row, score in found][: self._shortlist]
        rows = {row["id"]: row for row, _ in found}

        event(
            logger,
            "corpus shortlist built",
            module="sources.corpus",
            outcome="ok",
            fused=len(found),
            shortlisted=len(ordered),
        )

        return [
            SourceCandidate(
                url=rows[item_id]["canonical_url"],
                # Rank is carried here because it is the only field that survives
                # into `snapshot`, where the read/skip decision is recorded.
                publisher=rows[item_id].get("publisher"),
                title=rows[item_id].get("title"),
                published_at=rows[item_id].get("published_at"),
                proposed_by=f"{NAME}:rrf:{position}",
                prior_score=score,
            )
            for position, (item_id, score) in enumerate(ordered)
            if rows.get(item_id, {}).get("canonical_url")
        ]

    async def _dense(self, conn: Any, claim: Claim, *, within_days: int) -> list[dict[str, Any]]:
        """Vector leg. Returns nothing — not zeros — when the claim's language is
        outside the model, so the lexical leg carries it alone rather than being
        polluted by a meaningless ranking."""
        if self._embedder is None:
            return []

        # ONNX inference is CPU-bound and synchronous. Called directly it blocks the
        # event loop for every embedding — and on the first request, for the model
        # load too — stalling every other in-flight request behind this one.
        result = await asyncio.to_thread(
            self._embedder.embed_one, claim.text, language=claim.language
        )
        if not result.vectors:
            event(
                logger,
                "dense leg unavailable; lexical only",
                module="sources.corpus",
                outcome="skipped",
                failure_reason=result.reason or "no vector",
            )
            return []

        vector = "[" + ",".join(str(v) for v in result.vectors[0]) + "]"
        cursor = await conn.execute(
            """
            SELECT id::text, canonical_url, title, publisher, published_at,
                   origin_cluster_id::text AS origin_cluster_id, minhash_signature
              FROM facify.corpus_item
             WHERE embedding IS NOT NULL AND canonical_url IS NOT NULL
               AND (published_at IS NULL OR published_at > now() - make_interval(days => %s))
             ORDER BY embedding <=> %s::vector
             LIMIT %s
            """,
            (within_days, vector, DENSE_K),
        )
        return list(await cursor.fetchall())

    async def _lexical(self, conn: Any, claim: Claim, *, within_days: int) -> list[dict[str, Any]]:
        """Full-text leg over title and excerpt.

        `websearch_to_tsquery` rather than `plainto_tsquery` because it degrades
        gracefully on the punctuation and stray quoting that arrives with forwarded
        messages instead of erroring on it.
        """
        terms = " ".join(sorted(significant_words(claim.text)))
        if not terms:
            return []

        cursor = await conn.execute(
            """
            SELECT id::text, canonical_url, title, publisher, published_at,
                   origin_cluster_id::text AS origin_cluster_id, minhash_signature
              FROM facify.corpus_item
             WHERE canonical_url IS NOT NULL
               AND (published_at IS NULL OR published_at > now() - make_interval(days => %s))
               AND to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(excerpt,''))
                   @@ websearch_to_tsquery('simple', %s)
             ORDER BY ts_rank(
                        to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(excerpt,'')),
                        websearch_to_tsquery('simple', %s)
                      ) DESC
             LIMIT %s
            """,
            (within_days, terms, terms, LEXICAL_K),
        )
        return list(await cursor.fetchall())

    async def snapshot(self, candidate: SourceCandidate) -> SourceSnapshot | None:
        """Fetch the article. The stored excerpt is capped at 500 characters, so the
        text worth quoting only exists after this call."""
        result = await self._fetcher.fetch(candidate.url, provider=NAME)
        if not isinstance(result, FetchResult):
            return None

        try:
            article = extract(result.text, url=candidate.url)
        except Exception:
            return None

        if not article.body:
            return None

        # Hash the bytes as fetched. This is the snapshot's identity and what the
        # receipt is signed over, so it must describe what came back rather than
        # what we made of it.
        digest = hashlib.sha256(result.body).hexdigest()

        self._remember_rank(digest, candidate.proposed_by)

        return SourceSnapshot(
            id=digest,
            url=candidate.url,
            final_url=result.final_url or candidate.url,
            content_hash=digest,
            fetched_at=result.fetched_at,
            text=article.body,
            title=article.title or candidate.title,
            publisher=candidate.publisher,
            published_at=article.published_at or candidate.published_at,
            http_status=result.status_code,
        )

    def _remember_rank(self, digest: str, proposed_by: str) -> None:
        """Record whether this page is inside the reading budget."""
        if len(self._reasonable) > 4096:
            self._reasonable.clear()
        try:
            rank = int(proposed_by.rsplit(":", 1)[-1])
        except ValueError:
            rank = 0
        self._reasonable[digest] = rank < REASONED_CANDIDATES

    async def relate(self, claim: Claim, snapshot: SourceSnapshot) -> SourceRelation:
        """Read the fetched article and say what it does to the claim.

        Two mechanisms, and the difference between them is reading versus counting.
        When a reasoner is configured the model reads whole paragraphs and returns a
        relation with a verbatim quote and a stated reason; the quote is then located
        in the passage it came from, and a quote that cannot be located discards the
        judgement. When no model is available this falls back to word overlap behind
        a semantic gate, which cannot detect contradiction and does not pretend to.
        """
        if self._reasoner is not None and self._reasonable.get(snapshot.content_hash, False):
            relation = await self._reason(claim, snapshot)
            if relation is not None:
                return relation

        return await self._relate_lexically(claim, snapshot)

    async def _reason(self, claim: Claim, snapshot: SourceSnapshot) -> SourceRelation | None:
        """The reading path. `None` means it could not run, not that it found nothing.

        The distinction matters: a provider outage must fall back to the weaker
        mechanism rather than silently reporting that a source says nothing.
        """
        assert self._reasoner is not None

        passages = split_passages(snapshot.text)
        if not passages:
            return None

        outcome = await self._reasoner.judge(claim.text, passages)
        if not outcome.succeeded:
            event(
                logger,
                "passage reasoning unavailable; falling back to lexical matching",
                module="sources.corpus",
                outcome="degraded",
                failure_reason=outcome.reason,
            )
            return None

        best = outcome.best()
        if best is None:
            # The model read the article and found nothing bearing on the claim.
            # That is an answer, and a stronger one than the lexical path can give.
            return insufficient(
                NAME,
                VERSION,
                f"read {outcome.passages_read} passages; none addresses this claim",
            )

        # Located again against the whole article rather than trusting the passage
        # offsets. The excerpt shown to a reader must be findable in the document
        # they can open, not only in the fragment the model was handed.
        excerpt, anchor = locate_excerpt(snapshot.text, best.quote)
        if not excerpt:
            return insufficient(
                NAME, VERSION, "the quoted passage could not be located in the fetched article"
            )

        return SourceRelation(
            relation=best.relation,
            validator=f"{NAME}+reasoner",
            validator_version=f"{VERSION}/{REASONER_VERSION}",
            excerpt=excerpt,
            anchor=anchor,
            # The reason travels in the metric so the ledger records *why* this
            # relation was assigned, not merely that it was.
            metric=f"passage_entailment: {best.reason}"[:200],
            value=best.relevance,
            threshold=0.0,
        )

    async def _relate_lexically(self, claim: Claim, snapshot: SourceSnapshot) -> SourceRelation:
        """The fallback. Word overlap behind a semantic gate.

        **Never returns CONTRADICTS**, and that limit is the reason the reading path
        exists: lexical overlap cannot tell "X happened" from "X did not happen",
        since the two share every significant word. Reporting contradiction from this
        signal would invent the finding most likely to be acted on.
        """
        sentence, score = best_sentence(claim.text, snapshot.text)
        if not sentence or score < CONTEXT_OVERLAP:
            return insufficient(
                NAME,
                VERSION,
                f"no sentence in the fetched article reaches {CONTEXT_OVERLAP:.0%} "
                f"claim-word coverage (best {score:.0%})",
            )

        similarity = await self._similarity(claim, sentence)
        if similarity is None:
            # No vector for this claim, so the gate cannot be evaluated. Fall back to
            # demanding much heavier word coverage rather than waving the sentence
            # through on a check that did not run.
            if score < LEXICAL_ONLY_OVERLAP:
                return insufficient(
                    NAME,
                    VERSION,
                    f"no vector for this claim; lexical-only matching requires "
                    f"{LEXICAL_ONLY_OVERLAP:.0%} coverage and the best was {score:.0%}",
                )
        elif similarity < SEMANTIC_GATE:
            return insufficient(
                NAME,
                VERSION,
                f"the closest sentence is about a related subject but not this claim "
                f"(similarity {similarity:.2f}, gate {SEMANTIC_GATE:.2f})",
            )

        excerpt, anchor = locate_excerpt(snapshot.text, sentence)
        if not excerpt:
            # The needle came out of this haystack, so an absence here means the
            # text changed under us between selection and location.
            return insufficient(NAME, VERSION, "selected sentence no longer locatable")

        return SourceRelation(
            relation=Relation.SUPPORTS if score >= SUPPORT_OVERLAP else Relation.CONTEXTUALIZES,
            validator=NAME,
            validator_version=VERSION,
            excerpt=excerpt,
            anchor=anchor,
            metric="claim_word_coverage+semantic_gate",
            value=score,
            threshold=SUPPORT_OVERLAP if score >= SUPPORT_OVERLAP else CONTEXT_OVERLAP,
        )

    async def _similarity(self, claim: Claim, sentence: str) -> float | None:
        """Cosine between the claim and a candidate sentence, or `None` when the
        model has no representation for one of them.

        `None` is not zero, and the distinction is load-bearing: zero would read as
        "definitely unrelated" and silently reject every claim in a language the
        model does not cover, which is exactly the population this system serves.
        """
        if self._embedder is None:
            return None

        result = await asyncio.to_thread(
            self._embedder.embed, [claim.text, sentence], language=claim.language
        )
        if len(result.vectors) != 2:
            return None
        return cosine(result.vectors[0], result.vectors[1])


@dataclass(frozen=True, slots=True)
class CorroborationSignal:
    """How many independent origins carry a claim, out of how large a corpus.

    Independence is what this measures and documents are not it: twenty outlets
    running one wire story is one origin wearing twenty mastheads, which is why the
    count comes from `origin_cluster_id` rather than from the number of rows.
    """

    document_count: int = 0
    independent_origin_count: int = 0
    corpus_size: int = 0

    def applied_to(self, claim: Claim) -> Claim:
        """The claim with the counts attached, ready for the verdict engine.

        `Claim` is frozen, so this returns a copy. The verdict engine reads these two
        fields directly in Rule 4, and before this existed nothing in the codebase
        ever set them — they were read and never written, so every corroborated claim
        fell through to `rule.insufficient_origins` no matter how many outlets
        carried it.
        """
        return claim.model_copy(
            update={
                "document_count": self.document_count,
                "independent_origin_count": self.independent_origin_count,
            }
        )


def count_origins(rows: list[dict[str, Any]]) -> int:
    """Independent origins among retrieved documents, by near-duplicate clustering.

    **Computed here rather than read from `origin_cluster_id`, because that column is
    null for all 2,064 corpus rows and `origin_cluster` holds none.** Trusting it
    would have counted every document as its own origin — so twenty outlets running
    one PTI wire story would have reported twenty independent origins and driven a
    confident SUPPORTED verdict off a single source. That is the exact failure the
    origin-cluster concept exists to prevent.

    The signatures are already stored, so the clustering costs no fetch. Greedy
    single-link over the retrieved set is enough at this size: the set is the
    shortlist, not the corpus.
    """
    signatures: list[tuple[str, Signature]] = []
    for row in rows:
        raw = row.get("minhash_signature")
        if raw:
            signatures.append((row["id"], Signature.from_bytes(bytes(raw))))

    # A document with no signature cannot be shown to duplicate another, so it counts
    # as its own origin. Erring the other way would silently merge distinct sources.
    unsigned = len(rows) - len(signatures)

    origins: list[list[Signature]] = []
    for _, signature in signatures:
        for cluster in origins:
            if any(signature.similarity(member) >= DEFAULT_THRESHOLD for member in cluster):
                cluster.append(signature)
                break
        else:
            origins.append([signature])

    return len(origins) + unsigned


class CorpusCorroboration:
    """Counts independent origins for a claim, using the corpus search.

    Deliberately reuses `CorpusResolver.search` rather than querying separately: two
    searches could return two different sets for one claim, and then the origin count
    would describe a set other than the one that produced the citations.
    """

    def __init__(self, *, resolver: CorpusResolver, database: Any) -> None:
        self._resolver = resolver
        self._database = database

    async def signal(self, claim: Claim, *, citation_urls: list[str]) -> CorroborationSignal:
        """Origins among the documents that actually support the claim.

        **Counted over citations, not over the retrieval shortlist.** Counting the
        shortlist was wrong and measurably so: for one probe the shortlist held six
        articles while exactly one of them passed the evidence gate, and the verdict
        engine was handed "6 independent origins" for a claim with a single source.
        That is a confident SUPPORTED built on one document — the failure this whole
        design exists to prevent.

        So the input here is the citation URLs of supporting evidence, and the count
        can never exceed the number of sources actually quoted.
        """
        if not citation_urls:
            return CorroborationSignal(corpus_size=await self._corpus_size())

        rows = await self._rows_for(citation_urls)

        return CorroborationSignal(
            document_count=len(citation_urls),
            independent_origin_count=count_origins(rows) if rows else len(citation_urls),
            corpus_size=await self._corpus_size(),
        )

    async def _rows_for(self, urls: list[str]) -> list[dict[str, Any]]:
        """The corpus rows behind these citations, for their stored signatures.

        Matched on `canonical_url` because that is where the citations came from. A
        citation with no matching row contributes no signature, and `count_origins`
        treats an unsigned document as its own origin rather than merging it away.
        """
        async with self._database.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT id::text, canonical_url, publisher, minhash_signature
                  FROM facify.corpus_item
                 WHERE canonical_url = ANY(%s)
                """,
                (list(urls),),
            )
            return list(await cursor.fetchall())

    async def _corpus_size(self) -> int:
        """How much was searched. Needed to interpret silence: finding nothing in
        two thousand items and finding nothing in ten are different answers."""
        async with self._database.connection() as conn:
            cursor = await conn.execute("SELECT count(*) AS n FROM facify.corpus_item")
            row = await cursor.fetchone()
        return int(row["n"]) if row else 0
