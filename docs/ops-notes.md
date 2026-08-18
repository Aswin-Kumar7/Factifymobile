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

## Origin clustering: the M26 gate is MET (closed 2026-08-16)

**Status: closed.** It took two changes, and the second was not the one the options
below anticipated. The original failure analysis is kept underneath because it is
still correct about national outlets and it is why the feed mix changed.

### What actually closed it

**1. Feeds that genuinely syndicate.** Option 1 below, chosen and implemented. The
registry went from 30 declared feeds to 42, of which 22 are marked `carries_wire`:
regional papers and aggregators that republish PTI/ANI copy substantially unedited.
`load_registry` now refuses to load a registry with no wire-carrying outlet, because
that configuration cannot satisfy this gate however long ingestion runs.

Along the way, **13 of the original 30 feeds turned out to be dead** — HTTP 404, 403
or zero items — including *two of the six fact-checkers* (BOOM and Newschecker),
which had been quietly weakening the cheapest evidence class. Every URL in the
registry has now been fetched and parsed; a feed that cannot be verified is removed
rather than left to fail against backoff.

**2. Clustering on the article, not the feed excerpt.** This was the larger effect
and it was not in the options below.

Every CMS truncates its RSS excerpt at a different length. The Jaccard between two
outlets' excerpts of one wire story is therefore bounded by *where the two feeds
happened to cut*, not by how similar the articles are. Same three PTI stories:

| Pair | On excerpts | On article bodies |
|---|---|---|
| Business Standard ↔ Orissa Post (FPI flows) | 0.301 | **0.787** |
| Business Standard ↔ Orissa Post (m-cap erosion) | 0.265 | **0.792** |
| Business Standard ↔ Orissa Post (markets outlook) | 0.205 | **0.770** |

The threshold sits at 0.5, between the two columns. Ingestion now fetches each new
item's article and clusters on the extracted body, falling back to the excerpt when a
page will not load. Only the MinHash signature and a 500-character excerpt are
persisted — a signature is 128 integers, not article text — so this stays inside
M25's rule against republishing full articles.

Body clustering is also *more specific*, not merely more sensitive: one pair scoring
0.393 on excerpts turned out to be two different FPI stories sharing boilerplate, and
fell to 0.152 on bodies. Shared phrasing in a truncated lede is a weaker signal than
a whole article.

### The gate, end to end

50 feeds, all reachable, 557 items, 510 hydrated, shipped threshold 0.5 unchanged:

| Clustering text | Clusters | Multi-outlet |
|---|---|---|
| Feed excerpts (the old behaviour) | 545 | **0** |
| Article bodies | 541 | **6** |

The six are regional outlets pairing with each other and with The New Indian Express
and Hindustan Times — Orissa Post, Sambad English, The Assam Tribune, Telangana
Today, The Shillong Times. Real wire syndication, correctly collapsed to one origin
each.

Both changes were necessary and neither is sufficient. Syndicating feeds clustered on
excerpts still produced zero multi-outlet clusters across 828 items; national outlets
clustered on bodies score 0.00–0.04 because they genuinely write their own copy.

Regression is guarded without a network by
`TestClusteringTextIsTheArticleNotTheExcerpt` in `tests/unit/test_clustering.py`,
which asserts that differing truncations of one article fall below threshold while
the bodies cluster, and that independent reporting still does *not* cluster.

---

## The original M26 failure analysis (measured 2026-08-16)

Kept because it remains accurate about national mastheads, and because it is the
evidence that the feed mix — not the threshold — had to change.

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

### Options that were on the table — **option 1 was chosen**

1. ✅ **Add feeds that genuinely syndicate** — regional and aggregator outlets that run
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

## Google News as a source: measured and rejected (2026-08-16)

Recorded because it is the obvious idea, it was raised twice, and the reason it fails
is not obvious until measured.

### There is no API

The Google News API was deprecated in 2011 and turned down in February 2016. What
remains is the unofficial `news.google.com/rss`, a SERP scraper, or an aggregator
such as NewsAPI.org — whose free tier carries a **24-hour delay**, restricts CORS to
localhost, forbids commercial use, and costs $449/month to run in production. A
24-hour delay is disqualifying on its own against a 30-minute developing-story TTL.

### The RSS endpoints work, and give us the wrong thing

Measured against `hl=en-IN&gl=IN&ceid=IN:en`:

| Endpoint | Entries | Distinct outlets | **Repeated headlines** |
|---|---|---|---|
| Top stories | 38 | 25 | **0** |
| Search `PTI` | 100 | 36 | **0** |
| Search `farmers relief scheme` | 100 | 70 | **2** |

The last column is the whole point. Google clusters and deduplicates at ingestion
and serves one representative article per story — that is a feature of a reader
product and the exact destruction of the signal M26 needs. The two repeats in the
third row were *US* stories (Utah, Nebraska) returned despite India geo-targeting,
which is a separate relevance problem.

Sourcing the corpus from Google News would guarantee the origin-clustering gate can
never pass, and worse: syndicated coverage would arrive pre-collapsed and unlabelled,
so twenty mastheads carrying one wire story would look like one independent report
rather than being counted as one. That is the failure that makes corroboration
theatre.

### The links are not citable

Every item link is a `news.google.com/rss/articles/CBMi…` stub. Fetched, all three
sampled stubs returned HTTP 200 **from `news.google.com` itself** — ~600 KB of
JavaScript, no redirect to the publisher. Recovering a real URL needs either decoding
Google's payload format or driving a headless browser. Both are undocumented,
change without notice, and would sit on the evidence path where a citation must
resolve to the publisher.

### Scraping the HTML surface

`news.google.com/home` returns 1.7 MB containing **zero `<article>` elements** and is
JS-rendered, so it needs a headless browser to read at all. It is also against
Google's terms of service. Not pursued on either ground.

### What Google News would legitimately be good for

Query-time *discovery* of coverage for a claim the corpus does not hold — the shape
of M27/M31/M34, which are already governed and capped. It is not a corpus source and
it cannot supply a citation. That distinction is the whole of the argument: discovery
finds candidates, and evidence requires a fetched, dated, anchored page.

---

## Non-Indian sources: eight added (2026-08-16)

The allowlist is a fetch-security and trust boundary, not a geography rule. It is
mostly Indian because the claim distribution is, but two categories of non-Indian
source do work nothing in the Indian list can:

- **International fact-checkers** — Snopes and Full Fact adjudicate claims that
  circulate in India too, and their output is Tier C like any other adjudication.
- **International desks** — BBC (India and World), Al Jazeera, The Guardian,
  Deutsche Welle, France 24. Recycled foreign imagery is among the largest categories
  of Indian visual misinformation, and a Gaza or Syria photograph recaptioned as
  Kashmir can only be dated if the original coverage is in the corpus for M33/M34 to
  match against.

None are marked `carries_wire`: they write their own copy and must not be counted as
syndication.

**Reuters, AP and AFP are absent because their public RSS is retired** — measured
404, 401 and 403 respectively on 2026-08-16 — and their wire content is now sold
through paid APIs. Their copy still reaches the corpus second-hand through the Indian
outlets that carry it, which is exactly what the `carries_wire` feeds provide.

Registry is now 50 feeds: 8 fact-checkers, 40 news (22 wire-carrying), 2 official.

---

## Google Fact Check Tools API: live, needs a key (2026-08-16)

`GET https://factchecktools.googleapis.com/v1alpha1/claims:search`

Without a key it returns **HTTP 403 `PERMISSION_DENIED`** — *"Method doesn't allow
unregistered callers"*. So the service is up and the endpoint is correct; it is
gated on a key, not broken. The key is free and the wiring in `FactCheckResolver`
is already in place behind `FACIFY_FACTCHECK__ENABLED` plus a cap.

### ClaimReview markup is absent from Indian fact-checkers

Checked separately, because the API is not the only way to reach an adjudication —
publishers can embed `ClaimReview` JSON-LD in their own pages, which needs no key.
They do not:

| Page | `ClaimReview` present |
|---|---|
| altnews.in (index) | no |
| factly.in (index) | no |
| vishvasnews.com (index) | no |
| Three individual Factly article pages | **no** |

This is the measurement that justifies `parse_rating_from_title`. Indian
fact-checkers write the verdict into the headline — "Fact Check: this video is NOT
from Delhi", "फैक्ट चेक: यह दावा फर्जी है" — and publish no structured rating
anywhere. Reading the headline is not a shortcut around missing markup; it is the
only place the rating exists.

The M27 gate — a fact-checked case resolving with the external API disabled — passes
on this path, which is why it was written that way.

---

## Gemini billing: the $300 Cloud credit does not apply (2026-08-16)

Recorded because it looks exactly like a broken account and is not one.

A new Google Cloud account with the $300 free trial credit still gets **HTTP 429
"Your prepayment credits are depleted"** on every Gemini `generateContent` call. The
credit is real and works — Vision and Fact Check Tools both returned 200 on the same
project — but Google excludes this one API from it:

> the Google Cloud Welcome credit or free trial credit can't be used towards the
> Gemini API or AI Studio

Effective March 2026. Prepay and Postpay plans started 23 March 2026, new users
default to Prepay, and the minimum initial purchase is $10.

So the split on one project is:

| Service | Billed against | Status on the trial credit |
|---|---|---|
| Cloud Run, Cloud Vision, Fact Check Tools | Google Cloud billing | Covered by the $300 |
| Gemini API | Separate Gemini prepay balance | **Not covered** — needs its own $10+ |

### ListModels advertises models that cannot be called

Separate trap found at the same time. `gemini-2.5-flash` appears in ListModels with
`generateContent` in its supported methods, then returns **404 "no longer available
to new users"** on an actual call. `gemini-3.5-flash`, `gemini-3.6-flash` and
`gemini-3.7-flash` resolve.

Never pick a model id from the list alone — probe it with a real `generateContent`
call. The list is a catalogue, not an entitlement.

### There is no extraction path without a model

`app/extraction/` contains exactly two implementations of the `Extractor` protocol:
`LLMExtractor` and `UnavailableExtractor`, which returns nothing by design. There is
no rule-based fallback, and adding one would mean hand-written heuristics deciding
what counts as a claim — a judgement with no author, which is the thing the
architecture refuses everywhere else.

Without a funded Gemini balance, `/v1/verify` extracts no claims and abstains with
`claim_extraction was not checked`. That is honest and it is also the whole text
path, so the media path (Vision, funded by the Cloud credit) is what still
demonstrates end to end.

---

## Live end-to-end testing with real providers (2026-08-18)

All three Google services live, a real ingested corpus, and real claims. Two
defects found, both fixed; one earlier measurement corrected.

### The first real cited verdict

Corpus: 2,064 items from 39 sources, including 76 fact-check adjudications of which
8 carried a rating readable from the headline.

    claim   "A digitally altered video of Sara Tendulkar has gone viral"
    action  DO_NOT_SHARE
    status  CONTRADICTED
    tier    C, Alt News, altnews.in/digitally-altered-video-of-sara-t...
    excerpt "Alt News rated this altered: Digitally altered video of Sara Tendulkar"

A decisive status carrying a citation the system ingested itself, with no
fact-check API key involved — the M27 fallback path working on live data.

### Defect: the extraction prompt referenced a schema it never sent

`_SYSTEM_INSTRUCTION` said "Return only the JSON described by the schema" and no
`responseSchema` was ever transmitted. The model was matching a shape it had never
seen, answering plausibly and differently each run, and failing validation
downstream. The schema is now sent, derived from the enums so a new `ClaimType`
cannot be offered to the model without `ProposedClaim` also accepting it.

### Defect: false factual claims were classified OPINION

Worse than it sounds, because opinion is never fact-checked — so the claims this
product exists to catch were being routed away from checking:

| Claim | Before | After |
|---|---|---|
| "Drinking hot water cures coronavirus infection." | OPINION | EVENT |
| "EVMs used in Indian elections can be hacked remotely." | OPINION | EVENT |

The instruction said only "Label opinion as OPINION" and the model read
"implausible or debunked" as "opinion". It now defines OPINION as a value judgement
no evidence could settle, names both examples above as factual-but-false, and states
that misfiling one removes it from checking entirely.

`EXTRACTOR_VERSION` 2026.08.1 → 2026.08.3 across both fixes, because each changes
what the same document extracts to and the extraction cache is keyed on it.

### Correction: the "graphics fail to match" alarm was a test artifact

A byte-identical share card measured 0.8681 against the 0.93 threshold, which looked
like the threshold being mis-calibrated for graphics — a serious problem, since
screenshotted text cards are a large share of what circulates on WhatsApp.

It was not. The test's recycling transform used `resize((480, 360))`, which squashes
a 1200x667 image; the aspect distortion destroyed the similarity, not the
recompression. A messaging app rescales, it does not restretch. With `thumbnail`
preserving aspect:

| Content type | n | min | median | below 0.93 |
|---|---|---|---|---|
| Real news photographs | 20 | 0.8049 | 0.9734 | 5/20 |
| Real branded share cards | 12 | 0.8452 | 0.9686 | 2/12 |

Graphics are fine. A first attempt at this used *synthetic* text cards and reported
different cards scoring 1.0000 — that measured the fixture, not the model: one
layout with only the words changed is pixel-near-identical, and CLIP at 224px cannot
read the text that differs. Replaced with real `og:image` cards, one per masthead.

### The 0.93 threshold is confirmed, not changed

Across 16 real images the hash gate rejected **every** cross-image pair, so this run
produced no impostor data. Combined with the earlier 22-wallpaper calibration:

    genuine recycles, minimum      0.8049  (this run)
    impostors past the gate, max   0.9188  (earlier run)

The populations overlap: no threshold catches every genuine recycle and rejects
every impostor. 0.93 sits above the impostor ceiling and misses roughly 22% of
genuine recycles. That is the correct trade for this product — a miss is recoverable
through reverse-image discovery, a false match is a cited wrong answer.

---

## Credential hygiene

The database password was shared in a chat transcript during setup and is therefore
**considered compromised**. Rotate it in the platform dashboard, and from then on
supply it only through the server environment.

Nothing in this repository contains a connection string: `.env` is ignored, and
`.env.example` carries commented placeholders only.
