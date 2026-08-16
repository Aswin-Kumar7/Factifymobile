# Operations notes

Running record of measured numbers and deployment decisions. Everything here is
either measured or an explicitly-labelled estimate awaiting measurement — the plan
forbids publishing figures we have not measured, and that rule applies internally
too.

---

## Storage sizing (M03)

Free-tier ceiling: **500 MB database**, 1 GB file storage, 50 MB maximum upload,
5 GB cached plus 5 GB uncached egress.

### Per-row cost of the vector columns

| Column | Type | Bytes per row |
|---|---|---|
| `content_object.embedding`, `media_fingerprint.embedding` | `vector(512)` | ~2,052 |
| `claim.embedding`, `corpus_item.embedding`, `factcheck_record.embedding` | `vector(384)` | ~1,540 |
| `content_object.phash`, `media_fingerprint.phash` | `bit(64)` | ~16 |

`vector` stores 4 bytes per dimension plus a small header. `halfvec` stores 2 and
would halve these figures; it is the right optimisation **once retrieval quality is
measured**, and it is a column-type and index change rather than a schema change.
Not taken yet, because an unmeasured storage saving that costs recall is a bad trade.

### Estimated corpus growth

Ingestion is bounded: 20–30 feeds, a small batch per tick. Assume the pessimistic
end of the plan's range — 2,000 new corpus items per day.

| Horizon | Corpus items | Vectors | Row data + indexes (≈2×) |
|---|---:|---:|---:|
| 15 days (demo) | 30,000 | ~46 MB | ~140 MB |
| 30 days | 60,000 | ~92 MB | ~280 MB |
| 60 days | 120,000 | ~185 MB | ~550 MB — **over the ceiling** |

HNSW indexes roughly double the storage of the column they cover, which is why the
third column is not the second column.

**Conclusion.** The demo horizon fits comfortably. Beyond roughly six weeks of
continuous ingestion the free tier runs out, and the first lever is retention on
`corpus_item` (drop the body excerpt and the vector for items older than the
corroboration window, keep the citation), not a bigger plan. Second lever is
`halfvec`. Recorded here so the ceiling is a known date rather than a surprise.

**Status:** estimated from type widths, not yet measured against a live database.
Replace with measured `pg_total_relation_size` figures once ingestion has run —
this is a Day 6 task.

### What is deliberately not in the database

Raw media. The durable record is hashes, derived features and citations; bytes live
in short-TTL object storage and expire. A 50 MB upload limit against a 500 MB
database makes this non-negotiable rather than a preference.

---

## Runtime sizing (M49, recorded early)

The default small container memory allocation will not survive image processing plus
two local ONNX models loaded in the same process. Sizing and a warm instance during
judging are M49's responsibility; the constraint is recorded here because it
influences whether the embedding services share a process or split.

**Status:** not yet measured. Blocked on M22/M23 having real model weights.

---

## Verification still owed

| Item | Blocked on | How to close it |
|---|---|---|
| Migration runs clean on an empty database | A Postgres with pgvector ≥ 0.7 | `FACIFY_TEST_DATABASE_URL=… uv run pytest -m db` |
| Round-trip through every repository | Same | Same command; 22 tests are written and skipping |
| Container image builds and boots | Docker, unavailable locally | CI `image` job builds it and probes `/healthz` |
| Measured storage per corpus item | Ingestion having run | Day 6 |
| Measured model quota in the team account | Provider credentials | Day 0 |
