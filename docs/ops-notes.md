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
threshold can be calibrated on real pairs rather than assumed.

This 0.96 remains the embedder's default for any caller comparing two images in
isolation. **The media matcher does not use it** — it verifies candidates that already
survived a perceptual-hash gate, which is a different population, and 0.96 is wrong
for it by a wide margin. See the calibration below.

### Running the model tests

```
FACIFY_MODEL_TESTS=1 uv run pytest -m model
```

Excluded from the default run and from CI: nothing should silently pull hundreds of
megabytes on an ordinary test run. Weights should be baked into the container image
at build time rather than downloaded on first request, or the first verification
after a cold start pays ~20 s.

---

## Origin clustering: the M26 gate is NOT met (measured 2026-08-16)

**Status: open.** Recorded rather than worked around, because the fix is a
feed-selection decision that needs a human.

### What the plan assumed

codexplan.md §9 states the rule this way: *"Twenty Indian outlets carrying the same
story are often one PTI/ANI wire copy reprinted twenty times."* Near-duplicate
MinHash was chosen to collapse exactly that.

### What was measured

Live ingestion of **638 items from 12 major English-language national outlets**
(Times of India, Hindustan Times, Indian Express, NDTV, Mint, News18 and others)
produced **630 clusters and zero multi-outlet clusters**.

Three diagnostics, in order:

| Question | Finding |
|---|---|
| Is RSS text long enough to shingle? | **No.** 246 of 402 items had excerpts under 100 characters; the median was **0**. RSS carries headlines, not bodies. |
| Would article bodies fix it? | **No.** Fetched 22 real article bodies for hand-labelled same-story pairs. Same-story Jaccard: **0.0 – 0.04**. Different-story: 0.0. The populations do not separate. |
| Is there explicit wire attribution? | **No.** Zero of 402 items carried a PTI/ANI/Reuters credit in RSS metadata. |

Shingle size was swept from 2 to 5 words. At every size, the tenth percentile of
same-story pairs sat *below* the maximum of different-story pairs. **No threshold
separates them**, so this is not a tuning problem.

### What it actually means

These outlets **cover** the same events; they do not **reprint** each other. Each
writes its own headline and its own prose. Near-duplicate detection finds nothing
because there are no near-duplicates.

That is not entirely bad news. On this population, multiple outlets covering one
story really are multiple independent origins, so corroboration counts here are more
meaningful than the plan feared, not less. The feared failure — twenty mastheads over
one origin — does not appear in this feed mix.

Near-duplicate MinHash remains the right tool for the population it was chosen for:
content farms, regional aggregators that do run wire copy verbatim, and the recycled
-article pattern the plan describes elsewhere. Those sources are simply not in the
current registry.

### Options, for a human to choose

1. **Add feeds that genuinely syndicate** — regional and aggregator outlets that run
   PTI/ANI copy unedited. This makes the gate meetable and also broadens the corpus
   toward the sources where recycling actually happens. Most aligned with the plan.
2. **Add a second independence signal** — shared quoted-source relationships, which
   §9 already lists among the signals to store and which is not implemented. Three
   articles quoting one identical official statement share an origin even when the
   prose differs.
3. **Restate the gate** to "clustering demonstrably collapses verbatim reprints",
   which the 25 unit tests already prove against realistic wire-reprint fixtures, and
   accept that the current national-outlet mix does not exercise it live.

**Not done: lowering the threshold until something clusters.** The populations
overlap, so any threshold that produced a multi-outlet cluster here would be merging
genuinely independent reporting — overstating corroboration, which is the failure
mode that produces a confident wrong `SUPPORTED`.

---

## Media matching calibrated (M33, measured 2026-08-16)

The Day 8 task named above, done. 22 distinct real photographs, deduplicated by
content hash *and* perceptual hash — Windows ships the same wallpaper under several
filenames, and counting those as different pictures scores a correct match as a false
positive, which is how the first run of this measurement fooled itself.

Four transformations per photograph (88 same-picture variants) and all 231
cross-photograph pairs:

| Variant | What it models |
|---|---|
| Downscale to 480×360 + JPEG q55 | A photo on its third forward |
| Re-encode at 720×540 + q70 | A screenshot of a post |
| 8% crop + q80 | The common trim |
| 15% crop + q80 | An aggressive trim |

### The hash gate, not the embedding, is what rejects unrelated images

At the shipped gate of Hamming ≤ 12, **229 of 231 different-photograph pairs never
reach the verifier at all**. Only two survive it, scoring 0.8649 and 0.9188. Meanwhile
same-picture variants that pass the gate score 0.8829 – 1.0000, median 0.9642.

This inverts the assumption the 0.96 threshold was built on. M23 set it above 0.956 to
reject "different content of the same kind" — but that population is eliminated by the
hash gate before the embedding is ever consulted. The threshold was calibrated against
pairs the verifier never sees.

### Gate and threshold swept together

Recall is over all 88 variants; a false match is any different-photograph pair passing
both stages.

| Gate | 0.96 | 0.94 | 0.93 | 0.92 | 0.90 | Worst impostor past gate |
|---|---|---|---|---|---|---|
| 10 | 29 / 0 | 42 / 0 | 49 / 0 | 50 / 0 | 51 / **1** | 0.9188 |
| **12** | 31 / 0 | 44 / 0 | **51 / 0** | 52 / 0 | 54 / **1** | 0.9188 |
| 16 | 35 / **1** | 49 / **1** | 57 / **1** | 58 / **2** | 61 / **3** | 0.9697 |
| 20 | 40 / **1** | 54 / **1** | 62 / **1** | 63 / **2** | 66 / **4** | 0.9697 |
| 24 | 41 / **1** | 59 / **1** | 67 / **1** | 68 / **2** | 72 / **6** | 0.9697 |

*(cells are `recall / false matches`)*

**Gate 12 is the last value that is clean at every threshold.** At 16 and above a false
match appears even at 0.96, because an impostor pair sits at 0.9697 — higher than most
genuine re-shares. Widening the gate to recover cropped images buys recall by
introducing exactly the failure the module exists to prevent, so it stays at 12.

### Changed: verification threshold 0.96 → 0.93, media matcher only

`app/media/matching.py::VERIFICATION_THRESHOLD`. At gate 12 this takes recall from
31/88 to 51/88 — it roughly doubles the number of recycled images found — with zero
false matches and 0.0112 of margin over the highest surviving impostor. 0.92 would add
one more match and cut the margin to 0.0012, which is not a margin.

`ImageEmbedder`'s own default stays at 0.96 for callers comparing images in isolation.

**Provisional.** The negative population past the gate is two pairs. Two samples do not
justify a threshold, and this is re-measured against the real corpus once it carries
volume. It is recorded here rather than left as a bare constant for that reason.

### Known limitation: crops beyond ~10% are not found locally

Measured pHash distances for an 8% crop across 8 photographs: `8, 10, 12, 16, 18, 20,
20, 24` against a gate of 12 — so **3 of 8 cropped re-shares are recovered locally**.
This is not tuned away, because the sweep above shows the only way to recover the rest
is a gate that admits false matches.

Cropped media is stage two's job. This is precisely why M34 reverse-image discovery
exists, and it is the strongest argument against treating local matching as sufficient
on its own.

### CLIP is not testable on synthetic images

Recorded because it cost a debugging cycle. The synthetic fixtures in
`tests/unit/images.py` are right for testing the matcher and hashing, and useless for
testing CLIP: with real weights a recompressed copy of one synthetic scene scored
**0.9248 against itself**, while two unrelated synthetic scenes scored **0.9491**. The
same picture ranked *below* a different one.

CLIP embeds semantic content, and every abstract pattern is semantically "an abstract
picture with coloured shapes." The model tests therefore source real photographs from
the machine and **skip with a named reason** when none are found, rather than passing
over data that means nothing.

---

## Video: asyncio subprocesses do not work under the selector event loop

`asyncio.create_subprocess_exec` raises `NotImplementedError` on Windows under
`WindowsSelectorEventLoopPolicy` — which is the policy psycopg's async support
requires, so the two cannot coexist in one process. ffmpeg is invoked through
`asyncio.to_thread(subprocess.run, ...)` instead, which works under every loop on
every platform and still kills the child on timeout.

Not a Windows-only concern: it would have surfaced as "video silently never works" on
any deployment that sets a non-default loop policy.

---

## Credential hygiene

The database password was shared in a chat transcript during setup and is therefore
**considered compromised**. Rotate it in the platform dashboard, and from then on
supply it only through the server environment.

Nothing in this repository contains a connection string: `.env` is ignored, and
`.env.example` carries commented placeholders only.
