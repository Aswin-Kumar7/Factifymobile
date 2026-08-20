# Architecture audit — 2026-08-20

Prompted by "the architecture feels low-performing." The feeling was correct, and
none of the causes was a slow function: every one was structure. This documents what
the audit found, what changed, what was measured, and what remains.

## Method

Every endpoint exercised; every function call on the hot path read; suspicions
verified against code or measurement before being called findings. Baseline numbers
came from the live server on this machine (DB round trip: 25ms median, measured).

## Findings and fixes (commit `8981535`)

| # | Finding | Consequence | Fix |
|---|---|---|---|
| 1 | `put_verdict` had **zero callers** | Cache permanently empty; every repeat paid full price | Write wired into the pipeline |
| 2 | Cache write failed even once wired: `case_id` FK points at a row the ledger writes *later* | Every write silently rejected — looked like "cache never hits" | Write with `case_id=None`; ordering documented |
| 3 | One pool connection held across the whole verification (fetches at 20s, model calls at 90s) | 10 concurrent requests pin the pool; the reasoner then starves and silently degrades to word overlap | `PoolGovernor` / `PoolCacheService` check connections out per query |
| 4 | Orchestrator, semaphore, and burst window rebuilt **per request** | `Semaphore(6)` capped nothing across requests; per-minute limiter always saw an empty window | One orchestrator per process; media gets a resolver view sharing the same semaphore |
| 5 | ONNX text embedding, CLIP, pHash DCT, provenance parsing ran **on the event loop** | Any one request stalled all others; first request paid ~6s of lazy model loads inline | `asyncio.to_thread` throughout; models prewarm at startup |
| 6 | `TARGET_SECONDS = 8.0` never enforced | Observed 17.9s, 29.6s, 48.1s, 90.3s — past the app's own 45s timeout | Per-resolver deadline; timeout is a named `SkippedCheck`, finished resolvers' evidence kept |
| 7 | Media matching selected up to 5,000 rows per request, embeddings re-parsed in Python; HNSW index unused | O(corpus) per upload, growing with ingestion | `sha256 exact UNION nearest-64 by phash <~>` in SQL; matcher decides over the shortlist |
| 8 | Video 202 pointed at a case that never came to exist | Client polls 15×, gets 404s, gives up on a promise the server never kept | The accepted case is recorded; the poll terminates in an honest "routed to review" |
| 9 | No readiness signal | Failed composition indistinguishable from health | `/readyz` reports what is missing |

## Measured

| Path | Before | After |
|---|---|---|
| Repeat submission (the common case: a viral forward) | 1.3s *(silent full verify)* | **0.18s over HTTP, `from_cache=true`** |
| Cold verify, corpus path | 1.8–2.3s | unchanged (fetch-bound; see plan) |
| 6 concurrent requests | untested before | wall 3.6s vs 21.1s serialised |
| First request after boot | +~6s model loading | prewarmed at startup |
| Worst request | 90.3s | bounded by the deadline |

## Endpoint inventory

| Endpoint | State |
|---|---|
| `POST /v1/verify` | working; cache round trip live |
| `POST /v1/verify/file` (image) | working; SQL shortlist |
| `POST /v1/verify/file` (video) | 202 + honest terminal case; **no real worker** |
| `GET /v1/cases/{id}`, `/evidence` | working (ledger-backed) |
| `GET /v1/receipts/{id}` | **503 always** — `receipt_reader` never assigned; needs `FACIFY_RECEIPT_SIGNING_KEY` and a reader |
| `GET/POST /v1/review*` | **503 always** — `ReviewQueue` is connection-scoped, never composed |
| `/healthz`, `/readyz` | working |

## Remaining plan, in priority order

1. ~~**Cache payload is action-only.**~~ **Fixed (`ad88d6b`).** The payload carries
   the original case id; a hit reads the full stored result through `CaseReader`.
   Verified live: hit = 341ms with identical claims, evidence and citations to the
   cold run; `retrieved_at` frozen at the original computation across repeated
   hits; the returned `case_id` resolves on `/v1/cases/{id}/evidence`.
2. **Snapshot cache.** The cold path is fetch-bound (~1–2s for six pages). Fetched
   pages are re-fetched for every claim and every request; a short-TTL cache keyed
   by URL would cut most of it and be honest (the snapshot records `fetched_at`).
3. **Review queue wiring** — pool adapter like the others; the endpoints and the
   mobile "Report" button already exist.
4. **Receipts** — needs `FACIFY_RECEIPT_SIGNING_KEY` minted, a `receipt_reader`,
   and the ledger's evidence digest passed through.
5. **Video worker** — frame extraction exists (`app/media/video.py`); a background
   task per accepted case could run frames through the media path and write the
   ledger. Until then the honest terminal case stands.
6. **Extraction latency** is the tail that remains (5–48s observed when quota
   exists): pin a faster model for extraction, or stream. Provider-bound.
7. **Cross-lingual retrieval** — a Devanagari claim against English articles still
   abstains (zero lexical overlap; dense model cross-lingual quality unmeasured).

## Non-findings, recorded to save the next audit

- DB round trips are 25ms median from this machine — the database was never the
  bottleneck.
- `normalise_text` is ~0ms per call (its 2.1s is import-time, paid once).
- Corroboration no longer re-runs retrieval; it reads rows for the citation URLs.
