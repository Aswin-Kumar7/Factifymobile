-- Facify initial schema (M03).
--
-- Entity set from codexplan.md §10. Created in one pass, forward-only.
--
-- Two structural commitments are load-bearing and must not be deferred:
--
--   1. The write-back tables (media_fingerprint, claim_occurrence, origin_cluster)
--      exist from the first request. If they arrive later, the compounding-loop
--      claim is a future migration rather than a property of the system.
--   2. observation is separate from evidence and carries a trust_state. Usage grows
--      the corpus; usage must not poison it. Nothing is promoted on repetition alone.
--
-- Enumerated values are text with CHECK constraints rather than native enum types:
-- the value set is the contract (app/domain), and CHECK keeps it visible in the
-- schema without ALTER TYPE surgery on every evolution.
--
-- Vector width: image embeddings are 512-d, text embeddings 384-d, perceptual hash
-- is bit(64) with a Hamming index. `vector` is used rather than `halfvec`; halfvec
-- halves storage and is the right optimisation once retrieval quality is measured,
-- which is a change of column type and index, not of schema shape.

-- Schema placement is a security decision, not a preference.
--
-- The hosting platform auto-generates a REST API over `public`, can auto-expose new
-- tables in it, and runs an event trigger that enables RLS on new `public` tables.
-- None of that is wanted here: this schema holds evidence, verdicts and an
-- append-only audit log, reached only by this service over a direct connection.
-- A dedicated schema keeps all three mechanisms off our tables by construction,
-- rather than by remembering to toggle a setting in a dashboard.
--
-- The runner wraps each migration in its own transaction, so this file does not
-- open one.

CREATE SCHEMA IF NOT EXISTS facify;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

SET LOCAL search_path TO facify, extensions, public;

-- gen_random_uuid() is core in PostgreSQL 13+, so no extension is needed for it.

-- ---------------------------------------------------------------------------
-- Request-scoped entities
-- ---------------------------------------------------------------------------

CREATE TABLE verification_case (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID,
    request_id        TEXT        NOT NULL,
    input_type        TEXT        NOT NULL
        CHECK (input_type IN ('text', 'url', 'image', 'pdf', 'video')),
    language          TEXT,
    status            TEXT        NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'complete', 'failed')),
    overall_action    TEXT
        CHECK (overall_action IN ('SAFE_TO_SHARE', 'SHARE_WITH_CONTEXT',
                                  'SHARE_WITH_CORRECTION', 'DO_NOT_SHARE',
                                  'WAIT_AND_RECHECK', 'SEND_TO_REVIEW')),
    media_provenance  TEXT
        CHECK (media_provenance IN ('PROVENANCE_FOUND', 'RECYCLED_OR_MISATTRIBUTED',
                                    'UNKNOWN')),
    source_risk       TEXT
        CHECK (source_risk IN ('LOW', 'MEDIUM', 'HIGH', 'UNKNOWN')),
    extraction_route  TEXT,
    consent_to_process_media BOOLEAN NOT NULL DEFAULT FALSE,
    latency_ms        INTEGER,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at      TIMESTAMPTZ
);

CREATE INDEX idx_case_created_at ON verification_case (created_at DESC);
CREATE INDEX idx_case_request_id ON verification_case (request_id);

CREATE TABLE content_object (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id      UUID        NOT NULL REFERENCES verification_case (id) ON DELETE CASCADE,
    kind         TEXT        NOT NULL
        CHECK (kind IN ('text', 'url', 'image', 'pdf', 'video', 'audio', 'frame')),
    sha256       TEXT        NOT NULL,
    phash        BIT(64),
    embedding    VECTOR(512),          -- image embedding; NULL for non-visual objects
    source_url   TEXT,
    byte_size    BIGINT,
    mime_type    TEXT,
    frame_index  INTEGER,              -- set for keyframes extracted from a video
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_content_object_case ON content_object (case_id);
CREATE INDEX idx_content_object_sha256 ON content_object (sha256);

CREATE TABLE claim (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id          UUID        NOT NULL REFERENCES verification_case (id) ON DELETE CASCADE,
    content_object_id UUID       REFERENCES content_object (id) ON DELETE SET NULL,
    text             TEXT        NOT NULL,
    normalized_text  TEXT        NOT NULL,
    language         TEXT,
    claim_type       TEXT        NOT NULL
        CHECK (claim_type IN ('EVENT', 'STATISTIC', 'ATTRIBUTION', 'QUOTE',
                              'IDENTITY', 'MEDIA', 'PREDICTION', 'OPINION')),
    severity         TEXT        NOT NULL
        CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    importance       TEXT        NOT NULL
        CHECK (importance IN ('HEADLINE', 'MAIN_THESIS', 'SUPPORTING_DETAIL',
                              'BACKGROUND')),
    coverage_expectation TEXT
        CHECK (coverage_expectation IN ('HIGH', 'MEDIUM', 'LOCAL')),
    entities         JSONB       NOT NULL DEFAULT '[]'::jsonb,
    dates            JSONB       NOT NULL DEFAULT '[]'::jsonb,
    location         TEXT,
    embedding        VECTOR(384),       -- text embedding
    extractor_model  TEXT,              -- which model served the extraction call
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_claim_case ON claim (case_id);

-- A claim without an anchor is not storable: the anchor is what makes a finding
-- auditable back to the exact paragraph, character range, frame or timestamp.
CREATE TABLE claim_anchor (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id        UUID        NOT NULL REFERENCES claim (id) ON DELETE CASCADE,
    input_kind      TEXT        NOT NULL
        CHECK (input_kind IN ('text', 'url', 'image', 'pdf', 'video', 'audio')),
    section         TEXT,
    paragraph_index INTEGER,
    char_start      INTEGER,
    char_end        INTEGER,
    page_number     INTEGER,
    frame_start_ms  INTEGER,
    frame_end_ms    INTEGER,
    audio_start_ms  INTEGER,
    audio_end_ms    INTEGER,
    bbox            JSONB,
    content_hash    TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT anchor_char_range_ordered
        CHECK (char_start IS NULL OR char_end IS NULL OR char_end >= char_start),
    CONSTRAINT anchor_frame_range_ordered
        CHECK (frame_start_ms IS NULL OR frame_end_ms IS NULL
               OR frame_end_ms >= frame_start_ms)
);

CREATE INDEX idx_claim_anchor_claim ON claim_anchor (claim_id);

-- ---------------------------------------------------------------------------
-- Sources and snapshots — the chain of custody behind every citation
-- ---------------------------------------------------------------------------

CREATE TABLE source (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain                   TEXT        NOT NULL UNIQUE,
    publisher                TEXT,
    feed_url                 TEXT,
    source_class             TEXT        NOT NULL DEFAULT 'unknown'
        CHECK (source_class IN ('official', 'factchecker', 'news', 'unknown')),
    allowed_for_primary_check BOOLEAN    NOT NULL DEFAULT FALSE,
    risk_signals             JSONB       NOT NULL DEFAULT '{}'::jsonb,
    risk_level               TEXT        NOT NULL DEFAULT 'UNKNOWN'
        CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'UNKNOWN')),
    last_seen_at             TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE source_snapshot (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id         UUID        REFERENCES source (id) ON DELETE SET NULL,
    url               TEXT        NOT NULL,
    final_url         TEXT        NOT NULL,
    http_status       INTEGER,
    content_type      TEXT,
    byte_count        BIGINT,
    content_hash      TEXT        NOT NULL,
    excerpt           TEXT,
    title             TEXT,
    published_at      TIMESTAMPTZ,
    archive_url       TEXT,
    extraction_method TEXT,
    extraction_route  TEXT,
    redirect_chain    JSONB       NOT NULL DEFAULT '[]'::jsonb,
    fetched_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_source_snapshot_content_hash ON source_snapshot (content_hash);
CREATE INDEX idx_source_snapshot_final_url ON source_snapshot (final_url);

-- ---------------------------------------------------------------------------
-- Evidence and advisory — separate tables, because they are separate types
-- ---------------------------------------------------------------------------

-- Every row here can reach the verdict engine. Every row therefore carries a
-- citation, a snapshot, an excerpt and an anchor, and its match_quality is
-- reproducible from the recorded match_basis. No model writes to this table.
CREATE TABLE evidence (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id       UUID        NOT NULL REFERENCES claim (id) ON DELETE CASCADE,
    tier           TEXT        NOT NULL CHECK (tier IN ('A', 'B', 'C', 'D')),
    kind           TEXT        NOT NULL
        CHECK (kind IN ('fact_check', 'dated_source', 'media_match', 'provenance',
                        'source_risk', 'corroboration', 'attribution', 'quote')),
    direction      TEXT        NOT NULL
        CHECK (direction IN ('supports', 'contradicts', 'contextualizes',
                             'risk_signal')),
    finding        TEXT        NOT NULL,
    citation_url   TEXT        NOT NULL,
    publisher      TEXT,
    snapshot_id    UUID        NOT NULL REFERENCES source_snapshot (id),
    source_excerpt TEXT        NOT NULL,
    source_anchor  JSONB       NOT NULL,
    input_anchor   JSONB,
    method         TEXT        NOT NULL,
    match_quality  TEXT        NOT NULL
        CHECK (match_quality IN ('STRONG', 'MODERATE', 'WEAK')),
    match_basis    JSONB       NOT NULL,
    provider       TEXT,
    provider_version TEXT,
    observed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_evidence_claim ON evidence (claim_id);

-- Tier E lives here and only here. Nothing in this table is an input to decide()
-- or to the strength calculation; the deletion test asserts that emptying it
-- changes no verdict and no score.
CREATE TABLE advisory (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id       UUID        NOT NULL REFERENCES verification_case (id) ON DELETE CASCADE,
    content_object_id UUID    REFERENCES content_object (id) ON DELETE CASCADE,
    provider      TEXT        NOT NULL,
    provider_version TEXT,
    signal        TEXT        NOT NULL
        CHECK (signal IN ('CONFIRMED_BY_PROVENANCE', 'ADVISORY_SUSPICION',
                          'NO_SIGNAL')),
    score         DOUBLE PRECISION,
    note          TEXT        NOT NULL,
    artifact_ref  TEXT,                 -- renderable map, stored outside the database
    observed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_advisory_case ON advisory (case_id);

CREATE TABLE source_relation (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id          UUID        NOT NULL REFERENCES claim (id) ON DELETE CASCADE,
    snapshot_id       UUID        NOT NULL REFERENCES source_snapshot (id),
    relation          TEXT        NOT NULL
        CHECK (relation IN ('SUPPORTS', 'CONTRADICTS', 'CONTEXTUALIZES',
                            'NOT_RELEVANT', 'INSUFFICIENT')),
    excerpt           TEXT,
    source_anchor     JSONB,
    validator         TEXT        NOT NULL,
    validator_version TEXT        NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_source_relation_claim ON source_relation (claim_id);

CREATE TABLE media_match (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content_object_id UUID        NOT NULL REFERENCES content_object (id) ON DELETE CASCADE,
    source_object_id  UUID        REFERENCES content_object (id) ON DELETE SET NULL,
    fingerprint_hash  TEXT,
    metric            TEXT        NOT NULL,
    distance          DOUBLE PRECISION NOT NULL,
    threshold         DOUBLE PRECISION NOT NULL,
    verified          BOOLEAN     NOT NULL DEFAULT FALSE,
    source_date       TIMESTAMPTZ,
    citation_url      TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_media_match_content_object ON media_match (content_object_id);

CREATE TABLE verdict (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id      UUID        NOT NULL REFERENCES claim (id) ON DELETE CASCADE,
    status        TEXT        NOT NULL
        CHECK (status IN ('SUPPORTED', 'CONTRADICTED', 'MISLEADING_CONTEXT',
                          'UNVERIFIED')),
    action        TEXT        NOT NULL
        CHECK (action IN ('SAFE_TO_SHARE', 'SHARE_WITH_CONTEXT',
                          'SHARE_WITH_CORRECTION', 'DO_NOT_SHARE',
                          'WAIT_AND_RECHECK', 'SEND_TO_REVIEW')),
    reason        TEXT        NOT NULL,
    rule_id       TEXT        NOT NULL,   -- which rule fired
    rule_version  TEXT        NOT NULL,
    strength_json JSONB       NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_verdict_claim ON verdict (claim_id);

-- ---------------------------------------------------------------------------
-- Observations — every request, regardless of outcome. Not evidence.
-- ---------------------------------------------------------------------------

CREATE TABLE observation (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id           UUID        REFERENCES verification_case (id) ON DELETE CASCADE,
    content_object_id UUID        REFERENCES content_object (id) ON DELETE CASCADE,
    claim_id          UUID        REFERENCES claim (id) ON DELETE CASCADE,
    kind              TEXT        NOT NULL,
    raw_claim         TEXT,
    detail            JSONB       NOT NULL DEFAULT '{}'::jsonb,
    trust_state       TEXT        NOT NULL DEFAULT 'raw'
        CHECK (trust_state IN ('raw', 'validated', 'promoted')),
    observed_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_observation_case ON observation (case_id);
CREATE INDEX idx_observation_trust_state ON observation (trust_state);

-- ---------------------------------------------------------------------------
-- Corpus write-back — the compounding loop
-- ---------------------------------------------------------------------------

CREATE TABLE media_fingerprint (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sha256            TEXT        NOT NULL UNIQUE,
    phash             BIT(64),
    embedding         VECTOR(512),
    times_seen        INTEGER     NOT NULL DEFAULT 0,
    first_verified_at TIMESTAMPTZ,
    last_verified_at  TIMESTAMPTZ,
    last_verdict      TEXT
        CHECK (last_verdict IN ('SUPPORTED', 'CONTRADICTED', 'MISLEADING_CONTEXT',
                                'UNVERIFIED')),
    source_date       TIMESTAMPTZ,
    citation_url      TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE origin_cluster (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    minhash_signature  BYTEA       NOT NULL,
    canonical_publisher TEXT,
    canonical_url      TEXT,
    member_count       INTEGER     NOT NULL DEFAULT 1,
    first_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE claim_occurrence (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fingerprint_id    UUID        REFERENCES media_fingerprint (id) ON DELETE CASCADE,
    claim_id          UUID        REFERENCES claim (id) ON DELETE SET NULL,
    case_id           UUID        REFERENCES verification_case (id) ON DELETE SET NULL,
    content_object_id UUID        REFERENCES content_object (id) ON DELETE SET NULL,
    caption_text      TEXT,
    language          TEXT,
    source_domain     TEXT,
    observed_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_claim_occurrence_fingerprint ON claim_occurrence (fingerprint_id);

-- ---------------------------------------------------------------------------
-- Live corpus — what ingestion writes and corroboration searches
-- ---------------------------------------------------------------------------

CREATE TABLE corpus_item (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id         UUID        REFERENCES source (id) ON DELETE SET NULL,
    snapshot_id       UUID        REFERENCES source_snapshot (id) ON DELETE SET NULL,
    origin_cluster_id UUID        REFERENCES origin_cluster (id) ON DELETE SET NULL,
    canonical_url     TEXT        NOT NULL UNIQUE,
    content_hash      TEXT        NOT NULL,
    title             TEXT,
    excerpt           TEXT,
    publisher         TEXT,
    published_at      TIMESTAMPTZ,
    language          TEXT,
    embedding         VECTOR(384),
    minhash_signature BYTEA,
    ingested_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_corpus_item_published_at ON corpus_item (published_at DESC);
CREATE INDEX idx_corpus_item_cluster ON corpus_item (origin_cluster_id);
CREATE INDEX idx_corpus_item_content_hash ON corpus_item (content_hash);

-- Persisted live fact-check responses. These are the fallback when the external
-- API is unavailable — real records retrieved live, with their retrieval time.
CREATE TABLE factcheck_record (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_text     TEXT        NOT NULL,
    normalized_text TEXT       NOT NULL,
    rating         TEXT,
    publisher      TEXT,
    url            TEXT        NOT NULL,
    snapshot_id    UUID        REFERENCES source_snapshot (id) ON DELETE SET NULL,
    language       TEXT,
    embedding      VECTOR(384),
    published_at   TIMESTAMPTZ,
    retrieved_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (url, normalized_text)
);

-- ---------------------------------------------------------------------------
-- Ingestion scheduling
-- ---------------------------------------------------------------------------

CREATE TABLE feed (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url             TEXT        NOT NULL UNIQUE,
    domain          TEXT        NOT NULL,
    publisher       TEXT,
    feed_kind       TEXT        NOT NULL DEFAULT 'rss'
        CHECK (feed_kind IN ('rss', 'atom', 'sitemap')),
    enabled         BOOLEAN     NOT NULL DEFAULT TRUE,
    next_fetch_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    etag            TEXT,
    last_modified   TEXT,
    backoff_seconds INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_feed_due ON feed (next_fetch_at) WHERE enabled;

-- The uniqueness constraint that makes ingestion idempotent: a duplicated trigger
-- for the same window is a no-op, and a retry resumes from the recorded cursor.
CREATE TABLE feed_run (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feed_id        UUID        NOT NULL REFERENCES feed (id) ON DELETE CASCADE,
    window_start   TIMESTAMPTZ NOT NULL,
    ran_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    item_count     INTEGER     NOT NULL DEFAULT 0,
    status         TEXT        NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'complete', 'failed', 'skipped')),
    failure_reason TEXT,
    cursor         TEXT,
    UNIQUE (feed_id, window_start)
);

-- ---------------------------------------------------------------------------
-- Cache and budget
-- ---------------------------------------------------------------------------

-- The key incorporates everything that would change the answer, so a rule change
-- can never serve a stale verdict.
CREATE TABLE verdict_cache (
    cache_key         TEXT PRIMARY KEY,
    case_id           UUID        REFERENCES verification_case (id) ON DELETE SET NULL,
    status_json       JSONB       NOT NULL,
    rule_version      TEXT        NOT NULL,
    extractor_version TEXT        NOT NULL,
    corpus_version    TEXT        NOT NULL,
    policy_profile    TEXT        NOT NULL,
    language          TEXT,
    is_negative       BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at        TIMESTAMPTZ
);

CREATE INDEX idx_verdict_cache_expires_at ON verdict_cache (expires_at);

CREATE TABLE extraction_cache (
    content_hash      TEXT        NOT NULL,
    extractor_version TEXT        NOT NULL,
    payload           JSONB       NOT NULL,
    model_id          TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at        TIMESTAMPTZ,
    PRIMARY KEY (content_hash, extractor_version)
);

CREATE TABLE call_budget (
    provider TEXT        NOT NULL,
    day      DATE        NOT NULL,
    used     INTEGER     NOT NULL DEFAULT 0,
    cap      INTEGER     NOT NULL,
    PRIMARY KEY (provider, day),
    CONSTRAINT budget_never_exceeds_cap CHECK (used <= cap)
);

-- ---------------------------------------------------------------------------
-- Review queue and audit
-- ---------------------------------------------------------------------------

CREATE TABLE review_item (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id        UUID        NOT NULL REFERENCES verification_case (id) ON DELETE CASCADE,
    reason         TEXT        NOT NULL,
    machine_status TEXT,
    human_label    TEXT,        -- recorded beside the machine verdict, never over it
    reviewer       TEXT,
    notes          TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at    TIMESTAMPTZ
);

CREATE INDEX idx_review_item_pending ON review_item (created_at) WHERE reviewed_at IS NULL;

-- Append-only. No update or delete path exists in any repository.
CREATE TABLE audit_log (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id  UUID,
    request_id TEXT,
    case_id    UUID,
    actor      TEXT        NOT NULL,
    action     TEXT        NOT NULL,
    target     TEXT,
    detail     JSONB       NOT NULL DEFAULT '{}'::jsonb,
    at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_log_case ON audit_log (case_id);
CREATE INDEX idx_audit_log_at ON audit_log (at DESC);

-- ---------------------------------------------------------------------------
-- Vector and hash indexes
--
-- Hamming distance on bit(64) is the perceptual-hash candidate search; it is a
-- candidate generator only, and a match is not evidence until the embedding
-- comparison also passes (M33).
-- ---------------------------------------------------------------------------

CREATE INDEX idx_media_fingerprint_phash
    ON media_fingerprint USING hnsw (phash bit_hamming_ops);

CREATE INDEX idx_media_fingerprint_embedding
    ON media_fingerprint USING hnsw (embedding vector_cosine_ops);

CREATE INDEX idx_content_object_phash
    ON content_object USING hnsw (phash bit_hamming_ops);

CREATE INDEX idx_corpus_item_embedding
    ON corpus_item USING hnsw (embedding vector_cosine_ops);

CREATE INDEX idx_claim_embedding
    ON claim USING hnsw (embedding vector_cosine_ops);

CREATE INDEX idx_factcheck_record_embedding
    ON factcheck_record USING hnsw (embedding vector_cosine_ops);


