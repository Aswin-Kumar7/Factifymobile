# Operations notes

Running record of measured numbers and deployment decisions. Everything here is
either measured or an explicitly-labelled estimate awaiting measurement — the plan
forbids publishing figures we have not measured, and that rule applies internally
too.

---

## Target database (measured 2026-08-16)

| Property | Value |
|---|---|
| PostgreSQL | 17.6 |
| pgvector | **0.8.2** — clears the ≥0.7 requirement for `bit_hamming_ops` and `halfvec` |
| `gen_random_uuid()` | Core in PG13+; no extension dependency |
| Extension schema | `extensions` (platform convention) |
| Region | ap-south-1 |

**Connection choice.** Use the **session pooler** (port 5432 on the pooler host).
The direct host is IPv6-first and not reachable from every network; the transaction
pooler (6543) does not support prepared statements, which psycopg3 uses by default —
it would need `prepare_threshold=None` and buys nothing at this scale.

**Windows development note.** psycopg's async mode cannot run on the default
`ProactorEventLoop`. `tests/conftest.py` selects the selector policy on `win32`;
production is Linux, where this is a no-op.

---

## Schema isolation (M03)

All 25 tables live in a dedicated **`facify`** schema, verified as **0 tables in
`public`**.

This is a security decision, not tidiness. The platform auto-generates a REST API
over `public`, can auto-expose new tables in it, and runs an event trigger enabling
RLS on new `public` tables. This schema holds evidence, verdicts and an append-only
audit log reached only by this service over a direct connection. A dedicated schema
keeps all three mechanisms off our tables **by construction**, rather than by
remembering to toggle a dashboard setting — and it survives someone re-enabling
those settings later.

Connections set `search_path=facify,extensions,public`, so repositories carry no
schema prefix and cannot accidentally read or write a platform-managed table.

**Re-check after any platform change:** `public` must still contain zero Facify
tables.

---

## Storage sizing (M03)

Free-tier ceiling: **500 MB database**, 1 GB file storage, 50 MB maximum upload,
5 GB cached plus 5 GB uncached egress.

**Measured baseline:** the empty migrated schema, 25 tables and 6 HNSW indexes,
occupies **2,360 kB**. That is the fixed cost before a single row exists.

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

| Item | Status | Note |
|---|---|---|
| Migration runs clean on an empty database | ✅ **Closed** 2026-08-16 | 25 tables, 6 HNSW indexes, `bit_hamming_ops` accepted |
| Migration is idempotent under re-run | ✅ **Closed** | Second run found `0001` applied with a matching checksum and applied nothing |
| Round-trip through every repository | ✅ **Closed** | 22 database tests pass against the live instance |
| Container image builds and boots | ⏳ Open | Docker unavailable locally; the CI `image` job builds and probes `/healthz` |
| Measured storage per corpus item | ⏳ Open | Needs ingestion to have run — Day 6 |
| Measured model quota in the team account | ⏳ Open | Needs provider credentials — Day 0 |

---

## Local embedding models (M22, M23) — measured 2026-08-16

| | Text | Image |
|---|---|---|
| Model | `paraphrase-multilingual-MiniLM-L12-v2` | `clip-ViT-B-32-vision` |
| Runtime | ONNX, CPU, loaded once per container | same |
| Dimensions | **384** — fixed at the migration | **512** — fixed at the migration |
| First load (incl. download) | ~21 s | ~15 s |
| Encoding | 4 texts in 76 ms | — |
| External calls | **zero** | **zero** |

### Text: cross-script matching works, romanised Hindi does not

| Pair | Cosine |
|---|---|
| English ↔ Hindi, same claim | **0.927** |
| English ↔ Hinglish, same claim | 0.078 |
| Hindi ↔ Hinglish, *identical* sentence | 0.044 |
| Hinglish ↔ Hinglish, same topic | 0.494 |
| Hinglish ↔ Hinglish, **unrelated** topic | **0.630** |

The last two rows are the finding: unrelated romanised Hindi scores *higher* than
related romanised Hindi. That is not weak signal, it is noise, and noise in retrieval
produces confident cited wrong matches.

**Consequence:** the service refuses to embed Hinglish rather than embedding it badly,
and retrieval falls back to lexical matching for that language. Since English↔Hindi
is 0.927, transliterating Hinglish to Devanagari before embedding would fix this
properly. That needs a real transliterator rather than a scheme mapping, and is
recorded as roadmap rather than faked.

**This matters more than it looks:** Hinglish is the default register of Indian
WhatsApp, so the dominant input format currently gets lexical-only retrieval.

### Image: CLIP measures semantic similarity, not identity

| Pair | Cosine |
|---|---|
| Image ↔ itself, cropped + resized + JPEG q40 | **0.975** |
| Image ↔ genuinely different content | 0.78 – 0.84 |
| Image ↔ **different content of the same kind** | **0.956** |

The 0.956 is why embedding similarity can never be primary retrieval or decisive on
its own. Two different photographs of the same sort of scene — two crowds, two
floods, two ministers at two podiums — score almost as high as a true match.

**Default threshold is 0.96**, set *above* the same-kind figure rather than between it
and a true match: a false match is a cited wrong answer, a miss is an honest
abstention. Every comparison reports its margin, and near-misses are logged, so the
threshold can be calibrated on real pairs rather than assumed. **It has not been
calibrated on real images yet** — that is a Day 8 task.

### Running the model tests

```
FACIFY_MODEL_TESTS=1 uv run pytest -m model
```

Excluded from the default run and from CI: nothing should silently pull hundreds of
megabytes on an ordinary test run. Weights should be baked into the container image
at build time rather than downloaded on first request, or the first verification
after a cold start pays ~20 s.

---

## Credential hygiene

The database password was shared in a chat transcript during setup and is therefore
**considered compromised**. Rotate it in the platform dashboard, and from then on
supply it only through the server environment.

Nothing in this repository contains a connection string: `.env` is ignored, and
`.env.example` carries commented placeholders only.
