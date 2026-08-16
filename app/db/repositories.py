"""Repositories (M03) — one per aggregate.

Every statement against the database lives here. No other module issues SQL, so the
schema has exactly one set of callers and a column rename is a bounded change.

Later modules extend these classes with the queries they need; the shape established
here is that a repository takes a connection per call rather than holding one, which
keeps transaction control with the orchestrator that knows what must land together.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any, Self
from uuid import UUID

from psycopg import AsyncConnection

Row = dict[str, Any]
Conn = AsyncConnection[Row]


class _Repository:
    """Shared helpers. Not an abstraction — just the two calls every repo makes."""

    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    @classmethod
    def for_connection(cls, conn: Conn) -> Self:
        return cls(conn)

    async def _one(self, sql: str, params: tuple[Any, ...] = ()) -> Row | None:
        cursor = await self._conn.execute(sql, params)
        return await cursor.fetchone()

    async def _all(self, sql: str, params: tuple[Any, ...] = ()) -> list[Row]:
        cursor = await self._conn.execute(sql, params)
        return list(await cursor.fetchall())

    async def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        cursor = await self._conn.execute(sql, params)
        return cursor.rowcount


class CaseRepository(_Repository):
    """Cases and their content objects."""

    async def create(
        self,
        *,
        request_id: str,
        input_type: str,
        language: str | None = None,
        consent_to_process_media: bool = False,
    ) -> UUID:
        row = await self._one(
            """
            INSERT INTO verification_case (request_id, input_type, language,
                                     consent_to_process_media)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (request_id, input_type, language, consent_to_process_media),
        )
        assert row is not None
        return UUID(str(row["id"]))

    async def get(self, case_id: UUID) -> Row | None:
        return await self._one("SELECT * FROM verification_case WHERE id = %s", (case_id,))

    async def complete(
        self,
        case_id: UUID,
        *,
        overall_action: str,
        media_provenance: str,
        source_risk: str,
        latency_ms: int,
    ) -> None:
        await self._execute(
            """
            UPDATE verification_case
               SET status = 'complete',
                   overall_action = %s,
                   media_provenance = %s,
                   source_risk = %s,
                   latency_ms = %s,
                   completed_at = now()
             WHERE id = %s
            """,
            (overall_action, media_provenance, source_risk, latency_ms, case_id),
        )

    async def add_content_object(
        self,
        *,
        case_id: UUID,
        kind: str,
        sha256: str,
        phash: str | None = None,
        source_url: str | None = None,
        byte_size: int | None = None,
        mime_type: str | None = None,
    ) -> UUID:
        row = await self._one(
            """
            INSERT INTO content_object (case_id, kind, sha256, phash, source_url,
                                        byte_size, mime_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (case_id, kind, sha256, phash, source_url, byte_size, mime_type),
        )
        assert row is not None
        return UUID(str(row["id"]))

    async def content_objects(self, case_id: UUID) -> list[Row]:
        return await self._all(
            "SELECT * FROM content_object WHERE case_id = %s ORDER BY created_at",
            (case_id,),
        )


class ClaimRepository(_Repository):
    """Claims and their anchors. A claim is never stored without an anchor."""

    async def create(
        self,
        *,
        case_id: UUID,
        text: str,
        normalized_text: str,
        claim_type: str,
        severity: str,
        importance: str,
        anchor: dict[str, Any],
        language: str | None = None,
        coverage_expectation: str | None = None,
        entities: list[str] | None = None,
        dates: list[str] | None = None,
        location: str | None = None,
        extractor_model: str | None = None,
    ) -> UUID:
        """Insert a claim and its anchor together.

        The anchor is a required argument, not an optional follow-up call: an
        unanchored claim cannot be traced back to the source and must not exist.
        """
        row = await self._one(
            """
            INSERT INTO claim (case_id, text, normalized_text, language, claim_type,
                               severity, importance, coverage_expectation, entities,
                               dates, location, extractor_model)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                case_id,
                text,
                normalized_text,
                language,
                claim_type,
                severity,
                importance,
                coverage_expectation,
                json.dumps(entities or []),
                json.dumps(dates or []),
                location,
                extractor_model,
            ),
        )
        assert row is not None
        claim_id = UUID(str(row["id"]))

        await self._execute(
            """
            INSERT INTO claim_anchor (claim_id, input_kind, section, paragraph_index,
                                      char_start, char_end, page_number,
                                      frame_start_ms, frame_end_ms, content_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                claim_id,
                anchor["input_kind"],
                anchor.get("section"),
                anchor.get("paragraph_index"),
                anchor.get("char_start"),
                anchor.get("char_end"),
                anchor.get("page_number"),
                anchor.get("frame_start_ms"),
                anchor.get("frame_end_ms"),
                anchor["content_hash"],
            ),
        )
        return claim_id

    async def get(self, claim_id: UUID) -> Row | None:
        return await self._one("SELECT * FROM claim WHERE id = %s", (claim_id,))

    async def anchors(self, claim_id: UUID) -> list[Row]:
        return await self._all("SELECT * FROM claim_anchor WHERE claim_id = %s", (claim_id,))

    async def for_case(self, case_id: UUID) -> list[Row]:
        return await self._all(
            "SELECT * FROM claim WHERE case_id = %s ORDER BY created_at", (case_id,)
        )


class SourceRepository(_Repository):
    """Sources and the snapshots that back every citation."""

    async def upsert_source(
        self, *, domain: str, publisher: str | None = None, source_class: str = "unknown"
    ) -> UUID:
        row = await self._one(
            """
            INSERT INTO source (domain, publisher, source_class, last_seen_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (domain) DO UPDATE
                SET last_seen_at = now(),
                    publisher = COALESCE(EXCLUDED.publisher, source.publisher)
            RETURNING id
            """,
            (domain, publisher, source_class),
        )
        assert row is not None
        return UUID(str(row["id"]))

    async def record_snapshot(
        self,
        *,
        url: str,
        final_url: str,
        content_hash: str,
        source_id: UUID | None = None,
        http_status: int | None = None,
        content_type: str | None = None,
        byte_count: int | None = None,
        excerpt: str | None = None,
        title: str | None = None,
        published_at: datetime | None = None,
        extraction_method: str | None = None,
        extraction_route: str | None = None,
        redirect_chain: list[str] | None = None,
    ) -> UUID:
        row = await self._one(
            """
            INSERT INTO source_snapshot (source_id, url, final_url, http_status,
                                         content_type, byte_count, content_hash,
                                         excerpt, title, published_at,
                                         extraction_method, extraction_route,
                                         redirect_chain)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                source_id,
                url,
                final_url,
                http_status,
                content_type,
                byte_count,
                content_hash,
                excerpt,
                title,
                published_at,
                extraction_method,
                extraction_route,
                json.dumps(redirect_chain or []),
            ),
        )
        assert row is not None
        return UUID(str(row["id"]))

    async def get_snapshot(self, snapshot_id: UUID) -> Row | None:
        return await self._one("SELECT * FROM source_snapshot WHERE id = %s", (snapshot_id,))

    async def record_relation(
        self,
        *,
        claim_id: UUID,
        snapshot_id: UUID,
        relation: str,
        validator: str,
        validator_version: str,
        excerpt: str | None = None,
        source_anchor: dict[str, Any] | None = None,
    ) -> UUID:
        row = await self._one(
            """
            INSERT INTO source_relation (claim_id, snapshot_id, relation, excerpt,
                                         source_anchor, validator, validator_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                claim_id,
                snapshot_id,
                relation,
                excerpt,
                json.dumps(source_anchor) if source_anchor else None,
                validator,
                validator_version,
            ),
        )
        assert row is not None
        return UUID(str(row["id"]))


class EvidenceRepository(_Repository):
    """Evidence and advisory — separate tables because they are separate types.

    There is deliberately no method that writes an advisory row into `evidence`.
    """

    async def add_evidence(
        self,
        *,
        claim_id: UUID,
        tier: str,
        kind: str,
        direction: str,
        finding: str,
        citation_url: str,
        snapshot_id: UUID,
        source_excerpt: str,
        source_anchor: dict[str, Any],
        method: str,
        match_quality: str,
        match_basis: dict[str, Any],
        publisher: str | None = None,
        input_anchor: dict[str, Any] | None = None,
        provider: str | None = None,
        provider_version: str | None = None,
    ) -> UUID:
        row = await self._one(
            """
            INSERT INTO evidence (claim_id, tier, kind, direction, finding,
                                  citation_url, publisher, snapshot_id,
                                  source_excerpt, source_anchor, input_anchor,
                                  method, match_quality, match_basis, provider,
                                  provider_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                claim_id,
                tier,
                kind,
                direction,
                finding,
                citation_url,
                publisher,
                snapshot_id,
                source_excerpt,
                json.dumps(source_anchor),
                json.dumps(input_anchor) if input_anchor else None,
                method,
                match_quality,
                json.dumps(match_basis),
                provider,
                provider_version,
            ),
        )
        assert row is not None
        return UUID(str(row["id"]))

    async def for_claim(self, claim_id: UUID) -> list[Row]:
        return await self._all(
            "SELECT * FROM evidence WHERE claim_id = %s ORDER BY observed_at", (claim_id,)
        )

    async def add_advisory(
        self,
        *,
        case_id: UUID,
        provider: str,
        signal: str,
        note: str,
        content_object_id: UUID | None = None,
        score: float | None = None,
        provider_version: str | None = None,
        artifact_ref: str | None = None,
    ) -> UUID:
        row = await self._one(
            """
            INSERT INTO advisory (case_id, content_object_id, provider,
                                  provider_version, signal, score, note, artifact_ref)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                case_id,
                content_object_id,
                provider,
                provider_version,
                signal,
                score,
                note,
                artifact_ref,
            ),
        )
        assert row is not None
        return UUID(str(row["id"]))

    async def advisories_for_case(self, case_id: UUID) -> list[Row]:
        return await self._all("SELECT * FROM advisory WHERE case_id = %s", (case_id,))


class VerdictRepository(_Repository):
    async def record(
        self,
        *,
        claim_id: UUID,
        status: str,
        action: str,
        reason: str,
        rule_id: str,
        rule_version: str,
        strength: dict[str, Any],
    ) -> UUID:
        row = await self._one(
            """
            INSERT INTO verdict (claim_id, status, action, reason, rule_id,
                                 rule_version, strength_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (claim_id, status, action, reason, rule_id, rule_version, json.dumps(strength)),
        )
        assert row is not None
        return UUID(str(row["id"]))

    async def for_claim(self, claim_id: UUID) -> Row | None:
        return await self._one(
            "SELECT * FROM verdict WHERE claim_id = %s ORDER BY created_at DESC LIMIT 1",
            (claim_id,),
        )


class ObservationRepository(_Repository):
    """Observations and the promotion gate.

    Every request writes an observation regardless of outcome. Promotion into the
    trusted stores is a separate, explicit act — never a side effect of repetition.
    """

    async def record(
        self,
        *,
        kind: str,
        case_id: UUID | None = None,
        content_object_id: UUID | None = None,
        claim_id: UUID | None = None,
        raw_claim: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> UUID:
        row = await self._one(
            """
            INSERT INTO observation (case_id, content_object_id, claim_id, kind,
                                     raw_claim, detail)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                case_id,
                content_object_id,
                claim_id,
                kind,
                raw_claim,
                json.dumps(detail or {}),
            ),
        )
        assert row is not None
        return UUID(str(row["id"]))

    async def mark(self, observation_id: UUID, trust_state: str) -> None:
        if trust_state not in {"raw", "validated", "promoted"}:
            raise ValueError(f"unknown trust_state {trust_state!r}")
        await self._execute(
            "UPDATE observation SET trust_state = %s WHERE id = %s",
            (trust_state, observation_id),
        )

    async def count_for_case(self, case_id: UUID) -> int:
        row = await self._one(
            "SELECT count(*) AS n FROM observation WHERE case_id = %s", (case_id,)
        )
        assert row is not None
        return int(row["n"])


class FingerprintRepository(_Repository):
    """The trusted media store. Written only on promotion (M38)."""

    async def promote(
        self,
        *,
        sha256: str,
        phash: str | None = None,
        last_verdict: str | None = None,
        source_date: datetime | None = None,
        citation_url: str | None = None,
    ) -> UUID:
        """Record a validated match, incrementing the recurrence counter.

        This is the only path that moves `times_seen`. It is called on a validated
        match, never on a raw submission.
        """
        row = await self._one(
            """
            INSERT INTO media_fingerprint (sha256, phash, times_seen,
                                           first_verified_at, last_verified_at,
                                           last_verdict, source_date, citation_url)
            VALUES (%s, %s, 1, now(), now(), %s, %s, %s)
            ON CONFLICT (sha256) DO UPDATE
                SET times_seen = media_fingerprint.times_seen + 1,
                    last_verified_at = now(),
                    last_verdict = COALESCE(EXCLUDED.last_verdict,
                                            media_fingerprint.last_verdict),
                    source_date = COALESCE(EXCLUDED.source_date,
                                           media_fingerprint.source_date),
                    citation_url = COALESCE(EXCLUDED.citation_url,
                                            media_fingerprint.citation_url)
            RETURNING id
            """,
            (sha256, phash, last_verdict, source_date, citation_url),
        )
        assert row is not None
        return UUID(str(row["id"]))

    async def get(self, sha256: str) -> Row | None:
        return await self._one("SELECT * FROM media_fingerprint WHERE sha256 = %s", (sha256,))

    async def record_occurrence(
        self,
        *,
        fingerprint_id: UUID,
        caption_text: str | None = None,
        claim_id: UUID | None = None,
        case_id: UUID | None = None,
        language: str | None = None,
        source_domain: str | None = None,
    ) -> UUID:
        row = await self._one(
            """
            INSERT INTO claim_occurrence (fingerprint_id, claim_id, case_id,
                                          caption_text, language, source_domain)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (fingerprint_id, claim_id, case_id, caption_text, language, source_domain),
        )
        assert row is not None
        return UUID(str(row["id"]))

    async def occurrences(self, fingerprint_id: UUID) -> list[Row]:
        return await self._all(
            """
            SELECT * FROM claim_occurrence
             WHERE fingerprint_id = %s
             ORDER BY observed_at
            """,
            (fingerprint_id,),
        )

    async def record_match_attempt(
        self,
        *,
        content_object_id: UUID,
        metric: str,
        distance: float,
        threshold: float,
        verified: bool,
        source_object_id: UUID | None = None,
        source_date: datetime | None = None,
        citation_url: str | None = None,
    ) -> UUID:
        """Record every attempt, including misses.

        The near-miss log is what makes threshold calibration possible; discarding
        misses would leave the threshold un-tunable.
        """
        row = await self._one(
            """
            INSERT INTO media_match (content_object_id, source_object_id, metric,
                                     distance, threshold, verified, source_date,
                                     citation_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                content_object_id,
                source_object_id,
                metric,
                distance,
                threshold,
                verified,
                source_date,
                citation_url,
            ),
        )
        assert row is not None
        return UUID(str(row["id"]))


class CorpusRepository(_Repository):
    """The live corpus written by ingestion and searched by corroboration."""

    async def upsert_item(
        self,
        *,
        canonical_url: str,
        content_hash: str,
        title: str | None = None,
        excerpt: str | None = None,
        publisher: str | None = None,
        published_at: datetime | None = None,
        language: str | None = None,
        source_id: UUID | None = None,
        snapshot_id: UUID | None = None,
    ) -> UUID:
        row = await self._one(
            """
            INSERT INTO corpus_item (canonical_url, content_hash, title, excerpt,
                                     publisher, published_at, language, source_id,
                                     snapshot_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (canonical_url) DO UPDATE
                SET title = COALESCE(EXCLUDED.title, corpus_item.title),
                    excerpt = COALESCE(EXCLUDED.excerpt, corpus_item.excerpt)
            RETURNING id
            """,
            (
                canonical_url,
                content_hash,
                title,
                excerpt,
                publisher,
                published_at,
                language,
                source_id,
                snapshot_id,
            ),
        )
        assert row is not None
        return UUID(str(row["id"]))

    async def get_item(self, item_id: UUID) -> Row | None:
        return await self._one("SELECT * FROM corpus_item WHERE id = %s", (item_id,))

    async def create_cluster(
        self, *, minhash_signature: bytes, canonical_publisher: str | None = None
    ) -> UUID:
        row = await self._one(
            """
            INSERT INTO origin_cluster (minhash_signature, canonical_publisher)
            VALUES (%s, %s)
            RETURNING id
            """,
            (minhash_signature, canonical_publisher),
        )
        assert row is not None
        return UUID(str(row["id"]))

    async def assign_to_cluster(self, *, item_id: UUID, cluster_id: UUID) -> None:
        await self._execute(
            "UPDATE corpus_item SET origin_cluster_id = %s WHERE id = %s",
            (cluster_id, item_id),
        )
        await self._execute(
            "UPDATE origin_cluster SET member_count = member_count + 1 WHERE id = %s",
            (cluster_id,),
        )

    async def distinct_origin_count(self, item_ids: list[UUID]) -> int:
        """Count origins, never documents — the distinction corroboration rests on."""
        if not item_ids:
            return 0
        row = await self._one(
            """
            SELECT count(DISTINCT COALESCE(origin_cluster_id::text, id::text)) AS n
              FROM corpus_item
             WHERE id = ANY(%s)
            """,
            (item_ids,),
        )
        assert row is not None
        return int(row["n"])

    async def record_factcheck(
        self,
        *,
        claim_text: str,
        normalized_text: str,
        url: str,
        rating: str | None = None,
        publisher: str | None = None,
        language: str | None = None,
        published_at: datetime | None = None,
        snapshot_id: UUID | None = None,
    ) -> UUID:
        row = await self._one(
            """
            INSERT INTO factcheck_record (claim_text, normalized_text, rating,
                                          publisher, url, language, published_at,
                                          snapshot_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (url, normalized_text) DO UPDATE
                SET retrieved_at = now(),
                    rating = COALESCE(EXCLUDED.rating, factcheck_record.rating)
            RETURNING id
            """,
            (
                claim_text,
                normalized_text,
                rating,
                publisher,
                url,
                language,
                published_at,
                snapshot_id,
            ),
        )
        assert row is not None
        return UUID(str(row["id"]))


class CacheRepository(_Repository):
    """Verdict and extraction caches (M13 builds the policy on top of this)."""

    async def get_verdict(self, cache_key: str) -> Row | None:
        return await self._one(
            """
            SELECT * FROM verdict_cache
             WHERE cache_key = %s
               AND (expires_at IS NULL OR expires_at > now())
            """,
            (cache_key,),
        )

    async def put_verdict(
        self,
        *,
        cache_key: str,
        status_json: dict[str, Any],
        rule_version: str,
        extractor_version: str,
        corpus_version: str,
        policy_profile: str,
        case_id: UUID | None = None,
        language: str | None = None,
        is_negative: bool = False,
        expires_at: datetime | None = None,
    ) -> None:
        await self._execute(
            """
            INSERT INTO verdict_cache (cache_key, case_id, status_json, rule_version,
                                       extractor_version, corpus_version,
                                       policy_profile, language, is_negative,
                                       expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (cache_key) DO UPDATE
                SET status_json = EXCLUDED.status_json,
                    created_at = now(),
                    expires_at = EXCLUDED.expires_at
            """,
            (
                cache_key,
                case_id,
                json.dumps(status_json),
                rule_version,
                extractor_version,
                corpus_version,
                policy_profile,
                language,
                is_negative,
                expires_at,
            ),
        )

    async def get_extraction(self, *, content_hash: str, extractor_version: str) -> Row | None:
        return await self._one(
            """
            SELECT * FROM extraction_cache
             WHERE content_hash = %s AND extractor_version = %s
               AND (expires_at IS NULL OR expires_at > now())
            """,
            (content_hash, extractor_version),
        )

    async def put_extraction(
        self,
        *,
        content_hash: str,
        extractor_version: str,
        payload: dict[str, Any],
        model_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> None:
        await self._execute(
            """
            INSERT INTO extraction_cache (content_hash, extractor_version, payload,
                                          model_id, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (content_hash, extractor_version) DO UPDATE
                SET payload = EXCLUDED.payload, created_at = now()
            """,
            (content_hash, extractor_version, json.dumps(payload), model_id, expires_at),
        )


class BudgetRepository(_Repository):
    """Daily per-provider counters. The governor (M14) enforces policy on top."""

    async def try_consume(self, *, provider: str, cap: int, day: date | None = None) -> bool:
        """Atomically take one unit if the cap allows. False means capacity reached.

        The increment and the ceiling check are the same statement, so two concurrent
        requests cannot both take the final unit.
        """
        day = day or datetime.now(UTC).date()
        await self._execute(
            """
            INSERT INTO call_budget (provider, day, used, cap)
            VALUES (%s, %s, 0, %s)
            ON CONFLICT (provider, day) DO UPDATE SET cap = EXCLUDED.cap
            """,
            (provider, day, cap),
        )
        row = await self._one(
            """
            UPDATE call_budget
               SET used = used + 1
             WHERE provider = %s AND day = %s AND used < cap
            RETURNING used
            """,
            (provider, day),
        )
        return row is not None

    async def usage(self, *, provider: str, day: date | None = None) -> Row | None:
        day = day or datetime.now(UTC).date()
        return await self._one(
            "SELECT * FROM call_budget WHERE provider = %s AND day = %s", (provider, day)
        )


class FeedRepository(_Repository):
    """Feed registry and run ledger (M24, M25)."""

    async def register(
        self,
        *,
        url: str,
        domain: str,
        publisher: str | None = None,
        feed_kind: str = "rss",
    ) -> UUID:
        row = await self._one(
            """
            INSERT INTO feed (url, domain, publisher, feed_kind)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (url) DO UPDATE SET domain = EXCLUDED.domain
            RETURNING id
            """,
            (url, domain, publisher, feed_kind),
        )
        assert row is not None
        return UUID(str(row["id"]))

    async def due(self, limit: int) -> list[Row]:
        """A bounded batch, not the whole registry."""
        return await self._all(
            """
            SELECT * FROM feed
             WHERE enabled AND next_fetch_at <= now()
             ORDER BY next_fetch_at
             LIMIT %s
            """,
            (limit,),
        )

    async def start_run(self, *, feed_id: UUID, window_start: datetime) -> UUID | None:
        """Claim a run window. None means this window is already claimed.

        This is the idempotency lock: a duplicated trigger for the same window is a
        provable no-op rather than a second ingestion.
        """
        row = await self._one(
            """
            INSERT INTO feed_run (feed_id, window_start)
            VALUES (%s, %s)
            ON CONFLICT (feed_id, window_start) DO NOTHING
            RETURNING id
            """,
            (feed_id, window_start),
        )
        return UUID(str(row["id"])) if row else None

    async def finish_run(
        self,
        *,
        run_id: UUID,
        status: str,
        item_count: int = 0,
        failure_reason: str | None = None,
        cursor: str | None = None,
    ) -> None:
        await self._execute(
            """
            UPDATE feed_run
               SET status = %s, item_count = %s, failure_reason = %s, cursor = %s
             WHERE id = %s
            """,
            (status, item_count, failure_reason, cursor, run_id),
        )

    async def reschedule(
        self, *, feed_id: UUID, next_fetch_at: datetime, backoff_seconds: int = 0
    ) -> None:
        await self._execute(
            "UPDATE feed SET next_fetch_at = %s, backoff_seconds = %s WHERE id = %s",
            (next_fetch_at, backoff_seconds, feed_id),
        )


class ReviewRepository(_Repository):
    """The queue for cases the system correctly refuses to decide (M43)."""

    async def enqueue(
        self, *, case_id: UUID, reason: str, machine_status: str | None = None
    ) -> UUID:
        row = await self._one(
            """
            INSERT INTO review_item (case_id, reason, machine_status)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (case_id, reason, machine_status),
        )
        assert row is not None
        return UUID(str(row["id"]))

    async def record_human_label(
        self, *, item_id: UUID, human_label: str, reviewer: str, notes: str | None = None
    ) -> None:
        """Record beside the machine verdict, never over it."""
        await self._execute(
            """
            UPDATE review_item
               SET human_label = %s, reviewer = %s, notes = %s, reviewed_at = now()
             WHERE id = %s
            """,
            (human_label, reviewer, notes, item_id),
        )

    async def pending(self, limit: int = 50) -> list[Row]:
        return await self._all(
            """
            SELECT * FROM review_item
             WHERE reviewed_at IS NULL
             ORDER BY created_at
             LIMIT %s
            """,
            (limit,),
        )


class AuditRepository(_Repository):
    """Append-only. There is deliberately no update or delete method."""

    async def record(
        self,
        *,
        actor: str,
        action: str,
        request_id: str | None = None,
        case_id: UUID | None = None,
        target: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        await self._execute(
            """
            INSERT INTO audit_log (request_id, case_id, actor, action, target, detail)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (request_id, case_id, actor, action, target, json.dumps(detail or {})),
        )

    async def for_case(self, case_id: UUID) -> list[Row]:
        return await self._all("SELECT * FROM audit_log WHERE case_id = %s ORDER BY at", (case_id,))
