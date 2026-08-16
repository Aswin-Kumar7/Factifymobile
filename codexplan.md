# Facify — 15-Day Hackathon and Startup Plan

**Competition:** ZeAI National Hackathon, ZAIML-005 — Fake News & Deepfake Detection Platform  
**Product:** Facify  
**Horizon:** 15 days to a judged MVP; incubator-ready architecture beyond the demo  
**Planning principle:** Build one complete evidence-backed product experience, then expose the same engine as a startup platform.

**Data principle:** The product runs on live public evidence. No synthetic evidence, hand-authored
verdicts, synthetic duplicate stories, or artificial-only demo path is used to claim verification quality.
Tests may replay real public URLs and real source snapshots, but those records remain observations or
source snapshots—not trusted evidence unless the live evidence validators accept them.

**What this principle does *not* forbid.** Two practices are compatible with it and are required:

1. **Pre-warming.** Executing real inputs through the live pipeline against live sources *before*
   demo day, and later serving the resulting real verdict from `verdict_cache` with its retrieval
   timestamp displayed. Nothing is hand-authored; this is the cache the architecture already
   specifies, populated early. A demo that can only answer while every provider is reachable is a
   demo that fails on venue wifi.
2. **Snapshot replay in CI.** Tests run against stored `source_snapshot` rows — real bytes fetched
   from real URLs at a recorded time — rather than re-fetching live. Live fetching in CI makes the
   suite fail whenever a publisher edits a page, which is a flake, not a finding. Live retrieval is
   exercised by the scheduled ingestion job and the Day 13 audit, not by unit tests.

> **Why this was added:** the purity principle is correct about evidence provenance and was being
> over-applied to *execution*. Caching a real verdict computed from real evidence is not synthetic
> data, and replaying a stored real snapshot is not fabrication. Without these two carve-outs the
> plan has no answer for a provider outage during judging, and no way to keep CI deterministic.

> Facify does not ask, “Does this file look fake?”  
> It asks, “What exactly is being claimed, what evidence exists, what conflicts with it, and what should a person do next?”

## Executive decision

The original architecture is a strong long-term company design, but it contains too many production and enterprise surfaces for a 15-day build. This plan keeps its most defensible ideas and removes dependencies that are fragile, paid, policy-sensitive, or difficult to evaluate.

### The 15-day product

An Android share-to-verify application and a small web evidence console that accept:

- a URL;
- an image or PDF;
- a short video;
- pasted text.

Text and links are first-class inputs, not a secondary feature. A submitted link is treated as a document to inspect: Facify safely fetches the public page, extracts its article body, title, author, dates, quoted material, images, captions, and structured metadata, and verifies the individual claims rather than trusting the page's own label.

Facify returns, in English or Hindi:

1. the claim or claims extracted from the input, including the exact paragraph, title, frame, or timestamp where each claim appeared;
2. a status for each claim: `SUPPORTED`, `CONTRADICTED`, `MISLEADING_CONTEXT`, or `UNVERIFIED`;
3. a separate media-provenance status: `PROVENANCE_FOUND`, `RECYCLED_OR_MISATTRIBUTED`, or `UNKNOWN`;
4. a separate source-risk status;
5. two or more clickable evidence items where available;
6. a plain-language explanation and a safe sharing recommendation;
7. an evidence-strength score that is explicitly **not** a probability of truth.

### The investor story

The consumer app is the acquisition surface. The business is an evidence API for newsrooms, platforms, moderation teams, civic-information organizations, and brand-safety workflows.

The long-term moat is not a proprietary “fake detector.” It is a continuously improving, content-addressed evidence graph containing:

- normalized claims;
- fact-check references;
- dated source references;
- media fingerprints;
- source-risk profiles;
- recurrence and caption-variant relationships;
- human corrections.

Every **validated** verification improves the next one. This is the startup compounding loop.

### ZAIML-005 requirement coverage

| Required deliverable | Facify mechanism | Judge-proof output |
|---|---|---|
| Detect manipulated / AI-generated media | Dated-source matching, media fingerprints, C2PA when present, optional forensic advisory | Provenance status, dated citation, and an explicit `UNKNOWN` when evidence is absent |
| Analyze news credibility and source reliability | Claim-level source retrieval, ClaimReview, source-risk signals | Anchored claim cards and evidence links; source risk never decides a claim alone |
| Explain authenticity score | Deterministic evidence-strength calculation | A component breakdown linked to evidence, never a model probability |
| Identify misinformation patterns | Validated fingerprint write-back, recurrence and caption variants | “Seen N times / first verified on X” and contradictory-caption view |
| Generate fact-checking recommendations | Deterministic action rules and correction cards | `SAFE_TO_SHARE`, `WAIT_AND_RECHECK`, `SEND_TO_REVIEW`, or `DO_NOT_SHARE` with reasons |

## 1. Problem and sharp point of view

The brief is commonly interpreted as “upload media, receive a fake probability.” That framing is unsafe in production. Generic detectors can fail on unseen generators, social-platform transformations, compression, language shift, and adversarial edits. A detector also cannot tell whether a real 2019 image is being falsely presented as a 2026 event.

Facify addresses the higher-volume problem: **false context around real media, fabricated claims, recycled content, fake attributions, and unverifiable breaking news.** Deepfake models are retained as optional forensic signals, never as the sole source of truth.

### Product promise

> Share any public post, link, image, PDF, video, or text and receive a cited, multilingual explanation of what is supported, contradicted, recycled, suspicious, or still unknown.

### Why this can stand out among 10,000 teams

Most demos will show a model score. Facify shows a defensible decision trail:

```text
Input → claim extraction → evidence retrieval → source/media analysis
      → deterministic status → citations → recommended action
```

The memorable moment is not “our model says 93% fake.” It is:

> “This is a real image, but it was published five years earlier. Here is the original dated source, here is the current false caption, and here is why Facify refuses to call a novel claim true.”

## 2. Trust model: do not collapse different questions

“Authenticity” is multidimensional. The API and UI must not return one misleading label for all of these questions.

| Dimension | Values | What it means |
|---|---|---|
| Claim status | `SUPPORTED`, `CONTRADICTED`, `MISLEADING_CONTEXT`, `UNVERIFIED` | What the cited evidence says about the assertion |
| Media provenance | `PROVENANCE_FOUND`, `RECYCLED_OR_MISATTRIBUTED`, `UNKNOWN` | What is known about origin/history, not whether the claim is true |
| Synthetic-media signal | `CONFIRMED_BY_PROVENANCE`, `ADVISORY_SUSPICION`, `NO_SIGNAL` | Positive provenance or a non-decisive forensic signal |
| Source risk | `LOW`, `MEDIUM`, `HIGH`, `UNKNOWN` | Risk indicators about the publisher/domain, not proof that every claim is false |
| Action | `SAFE_TO_SHARE`, `SHARE_WITH_CONTEXT`, `SHARE_WITH_CORRECTION`, `DO_NOT_SHARE`, `WAIT_AND_RECHECK`, `SEND_TO_REVIEW` | The user-facing decision |

`SUPPORTED` means the available evidence supports the specific claim. It does not mean the media is original, the source is trustworthy in every situation, or the event is metaphysically proven.

## 3. Evidence contract

Every finding is an evidence object. The verdict engine receives only validated evidence objects. It never receives raw LLM confidence or detector scores.

```json
{
  "id": "ev_01",
  "kind": "fact_check | dated_source | media_match | provenance | source_risk | corroboration",
  "direction": "supports | contradicts | contextualizes | risk_signal",
  "claim_id": "cl_01",
  "finding": "The same image appeared in a Reuters article dated 2019-03-14.",
  "citation_url": "https://example.org/source",
  "publisher": "Reuters",
  "observed_at": "2026-08-16T09:14:22Z",
  "method": "live_source_snapshot_match",
  "source_snapshot_id": "ss_01",
  "source_excerpt": "The same image appeared in a Reuters article dated 2019-03-14.",
  "source_anchor": { "paragraph": 3, "char_start": 84, "char_end": 151 },
  "input_anchor": { "kind": "image", "frame_start_ms": null, "frame_end_ms": null },
  "match_quality": "STRONG",
  "match_basis": { "metric": "clip_cosine", "value": 0.94, "threshold": 0.90 }
}
```

`match_quality` is one of `STRONG | MODERATE | WEAK`, and it is **derived deterministically from
`match_basis`** — an embedding distance, a fact-check rating string, an exact-hash equality, a
redirect-confirmed URL. It is never written by a model.

> **Why this changed (was `"confidence": "high"`):** a free-text confidence field on an evidence
> object has no defined author. If the LLM populates it, model confidence has entered the evidence
> contract through a side door, contradicting this plan's own rule that the verdict engine never
> receives model scores. Deriving the value from a recorded metric and threshold keeps the field
> auditable — a reviewer can recompute it — and makes threshold calibration a testable artifact
> rather than a prompt.

### Evidence hierarchy

| Level | Evidence | Role | Decides? |
|---|---|---|---|
| A | Validated C2PA/content credential | Tamper-evident provenance assertions | Yes, for provenance only |
| B | Dated source, archive capture, exact/near media match | Context and chronology | Yes, when the match is strong |
| C | Published ClaimReview/fact-check | Adjudicated claim evidence | Yes, with publisher and rating shown |
| D | Corroboration clusters, attribution check, source-risk signals | Support, contradiction, or caution | Yes for limited status rules; not proof by itself |
| E | Deepfake classifier, lip-sync model, stylistic detector | Investigation lead | No; display as advisory only |

### Evidence validators

`match_quality` is method-specific, not a universal model score:

| Method | Can become decisive? | Required validation |
|---|---:|---|
| Exact SHA-256 match | Yes | Same bytes and source snapshot |
| Near-duplicate image/video match | Yes | Candidate metric plus visual/context confirmation and source date |
| Embedding similarity alone | No | Candidate generation only |
| ClaimReview result | Yes | Claim similarity, publisher, rating, URL, and source snapshot |
| Official-source relation | Yes | Allowlisted domain, exact excerpt, claim anchor, validator version |
| Search-result snippet | No | Must fetch and anchor the underlying page |
| Domain-age/source-risk signal | No | Source-risk/review signal only |
| C2PA validation | Yes for provenance | Valid manifest and signer/trust details; not factual truth |

### Hard design rules

1. No citation means no `SUPPORTED` or `CONTRADICTED`; return `UNVERIFIED`.
2. C2PA proves a signed provenance assertion is bound to an asset; it does not prove that the depicted event is true. This is consistent with the C2PA specification and explainer.
3. A missing C2PA manifest is not evidence that media is fake.
4. Domain age, typosquatting, shared infrastructure, and cloaking are source-risk evidence, not proof that a particular claim is false.
5. Search silence alone never produces `CONTRADICTED`.
6. Tier E signals never change the verdict or evidence-strength score in the hackathon build.
7. If evidence conflicts, show the conflict and return `UNVERIFIED` or `SEND_TO_REVIEW` rather than silently averaging it away.
8. **Source-risk evidence alone can never produce `DO_NOT_SHARE`.** Its ceiling is `UNVERIFIED` +
  `SEND_TO_REVIEW`. A `DO_NOT_SHARE` requires at least one claim-level `CONTRADICTED` or
  `MISLEADING_CONTEXT`.
9. **No evidence object may carry a model-authored score.** Every numeric or ordinal field on an
  evidence object must be reproducible from a recorded metric (see `match_basis` above).

> **Why rule 8 was added:** the verdict rules in §9 previously allowed source-risk evidence alone to
> reach `DO_NOT_SHARE`. That publishes an actionable negative assertion about a *named publisher*
> without any finding about the content itself — the shape of a defamation complaint, and directly
> contradicting rule 4 of this same list. Domain age and shared infrastructure are reasons to look
> harder, not reasons to tell users a specific article is unsafe. Capping the outcome at review
> keeps the signal useful and the claim defensible.

## 4. The buildable system architecture

```text
Android share target / Web console / API request
                    │
                    ▼
              FastAPI intake
      validate → normalize → hash → case
                    │
                    ▼
        ┌───────────────────────────┐
        │ CACHE PROBE               │  content hash · canonical URL · claim hash
        │ hit → serve stored verdict│  (negative cache: UNVERIFIED carries a TTL)
        └───────────┬───────────────┘
                    │ miss
                    ▼
        ┌───────────────────────────┐
        │ CALL GOVERNOR             │  per-provider daily counters, hard-capped
        │ over budget → skip provider, record "capacity limited"
        └───────────┬───────────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
  Content analysis        Evidence retrieval
  OCR / optional ASR / claims  fact-check API
  keyframes / C2PA        live RSS/source corpus
  local hash + embedding  ── local miss ─► reverse-image discovery (governed)
                            └─► fetch matched pages → dates + anchored excerpt
                            source-risk checks
        └───────────┬───────────┘
                    ▼
      Evidence ledger + claim graph
                    │
                    ▼
      Pure deterministic verdict engine
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
  Evidence card /          ┌──────────────────────────────┐
  share card /             │ CORPUS WRITE-BACK            │
  API JSON /               │ media_fingerprint (times_seen)│
  review queue             │ claim_occurrence              │
                          │ verdict cache entry           │
                          └──────────────────────────────┘
                                        │
                                        └──► feeds the next verification
```

Three components were added to the original flow: a **cache probe** before any work, a **call
governor** before any external call, and a **corpus write-back** after validated findings. Every
request is recorded as an observation; raw requests never become trusted corpus evidence.

> **Why the cache and governor were added:** the free-tier model budget is far smaller than a
> vague "rate-limited" note implies (see §11 for measured numbers). Without a probe, repeated demo
> content re-spends quota on every share; without a governor, a burst of judge activity returns
> provider errors mid-demo instead of the honest "capacity limited" state this plan already
> promises in §16. Both were listed as cost-control bullets but owned by no component, which meant
> nobody would build them.
>
> **Why write-back was added:** the executive summary stakes the company on "every validated
> verification
> improves the next one", and §19 lists repeat-content cache-hit rate and recurrence rate as
> day-one investor metrics. The original flow terminated at the output card — no path wrote results
> back into the retrieval corpus, so the corpus could only grow from the RSS feeds. That makes it a
> *content* corpus any team can clone in a weekend, not an evidence graph. Write-back is what makes
> the moat claim true rather than asserted, and it is two inserts.

### Services for the hackathon

Use one deployable FastAPI service with internal modules, not seven microservices.

```text
app/
  api/              request and response routes
  intake/           URL, text, image, PDF, short-video normalization
  extraction/       HTML, JSON-LD, OCR, structured LLM extraction
  knowledge/        fact-check and RSS corpus ingestion
  evidence/         fingerprints, retrieval, evidence ledger
  sources/          source resolver, snapshots, allowlists, attribution checks
  verdict/          deterministic status and strength functions
  media/            C2PA, ffmpeg keyframes, optional advisory models
  cache/            content-hash and URL cache, negative-cache TTLs
  governor/         per-provider daily counters and call budgets
  corpus/           write-back: fingerprints, claim occurrences, recurrence
  security/         SSRF, upload limits, prompt-injection boundaries
  db/               migrations and repositories
web/                evidence console
mobile/             Android share target
data/               schemas, live-case manifests, and local test artifacts; no preloaded trusted evidence
docs/               evaluation, ADRs, source register
```

After the hackathon, the internal modules can become independently scalable workers. The 15-day architecture should preserve interfaces, not prematurely deploy infrastructure.

## 5. Intake and URL handling

### Supported in the judged MVP

| Input | Treatment | Demo priority |
|---|---|---:|
| Text | Extract claims; match fact-check and news corpus | P0 |
| URL | Fetch public HTML; parse JSON-LD, OpenGraph, article text and media URLs | P0 |
| Image | OCR → claim pipeline; hash + embedding corpus match, then governed reverse-image discovery on miss (§8B); C2PA probe if a manifest survived | P0 |
| PDF | Text extraction, page rendering when needed, OCR, claim pipeline | P0 |
| Short video | 6–12 keyframes, OCR, claim and media/context matching; audio optional | P0 bounded |
| Generic public article link | Fetch and extract article HTML/JSON-LD/OpenGraph | P0 |
| Public X / YouTube link | Read public metadata/thumbnail when the platform permits; otherwise ask for screenshot or exported media | Best effort, not a decisive path |
| Authenticated/private social post | Ask the user for a screenshot or exported media | Explicitly unsupported |

> **Platform boundary:** the generic-web resolver is P0 and must be built. X and YouTube adapters are
> **best effort only** — both platforms frequently restrict automated retrieval, so no verdict may
> depend on either. Read public metadata or thumbnails when available, then ask for a screenshot or
> exported media. The reliable P0 demonstration is a public web article, image, PDF, or upload, and
> the platform adapters must never sit on the critical path of a gate.

### Model-side URL retrieval — what it cannot do

If the LLM's URL-context tool is used for retrieval, three limits are contractual, not incidental:
**YouTube URLs are unsupported**, paywalled pages are unsupported, and login-required pages are
unsupported. Video therefore never has a model-side retrieval path.

> **Why this is stated explicitly:** the plan previously treated "fetch the page" and "let the model
> read the page" as interchangeable routes. They are not — YouTube is excluded from the model-side
> tool entirely, so any video capability must come from the local keyframe path (§8C) and the
> YouTube thumbnail adapter. Writing it down prevents a late discovery that the video demo has no
> retrieval route.

### URL policy

Use a strict fetcher:

- only `http` and `https`;
- resolve DNS and reject loopback, private, link-local, multicast, and cloud metadata ranges;
- re-check the destination after every redirect;
- cap redirect count, response bytes, content type, and timeout;
- never send cookies or authenticated sessions;
- never bypass paywalls, DRM, login walls, or platform controls;
- store the final URL, HTTP metadata, extraction route, and fetch time;
- treat fetched text as untrusted data, never as instructions.

For blocked social pages, do not promise a scraping ladder. Use public metadata where available and fall back to a user-provided screenshot/media file. This is more reliable and easier to defend with platform policies.

## 5A. Text and link verification — the Claim–Evidence Graph

Facify does not ask an LLM whether an entire article “feels true.” It converts a page into atomic, traceable claims and checks each claim against evidence.

### Link verification lifecycle

```text
user URL
  ↓
SSRF-safe one-time fetch
  ↓
canonical URL + response hash + extraction timestamp
  ↓
title · body · author · dates · quotes · images · JSON-LD
  ↓
claim segmentation with paragraph/span anchors
  ↓
fact-check + primary-source + corroboration + attribution checks
  ↓
claim–evidence graph
  ↓
per-claim status + citations + source-risk context
```

### What the crawler extracts

Store structured metadata and short evidence excerpts rather than copying entire articles into the product:

| Page element | Use |
|---|---|
| Canonical URL and redirects | Identify the page and preserve the acquisition route |
| Title and subtitle | Extract headline claims and detect sensational changes |
| Article body | Segment checkable factual claims |
| Author and publisher | Attribution and source context |
| Published/updated dates | Temporal checks and backdating detection |
| JSON-LD/NewsArticle metadata | Structured date, author, image, and publisher fields |
| Quotations | Exact and fuzzy quote attribution |
| Images and captions | Send images through the media pipeline |
| Links and cited sources | Check whether the cited source actually supports the statement |
| HTTP/fetch metadata | Chain of custody and reproducibility |

### Atomic claim types

```text
EVENT        “An eruption happened in China on 14 August.”
STATISTIC    “The scheme helped 10 million people.”
ATTRIBUTION  “The RBI announced this policy.”
QUOTE        “The minister said …”
IDENTITY     “This person is the chief minister.”
MEDIA        “This image shows the current eruption.”
PREDICTION   “The government will announce …”
OPINION      Label as opinion; do not automatically fact-check it.
```

Each claim must retain its location in the input:

```json
{
  "claim_id": "cl_17",
  "text": "The eruption happened in China on 14 August.",
  "claim_type": "EVENT",
  "source_anchor": {
    "url": "https://example.org/article",
    "section": "article_body",
    "paragraph_index": 3,
    "char_start": 412,
    "char_end": 458,
    "content_hash": "sha256:..."
  },
  "entities": ["China"],
  "date": "2026-08-14",
  "location": "China"
}
```

### How a link is checked

1. **Known fact-check:** search the extracted claim and relevant image through the Fact Check Tools API and the local ClaimReview corpus.
2. **Primary-source check:** when the page names a government department, court, university, scientific body, company, or event, look for the original statement or record from that entity.
3. **Attribution check:** fetch the cited source and check whether it contains the claimed announcement, number, quote, or date. “According to Reuters” is not accepted unless the cited source supports the statement.
4. **Quote check:** search exact and normalized quote variants; compare speaker, date, language, and context.
5. **Temporal check:** compare the page's stated date with source publication dates, archive captures, sitemap metadata, and the earliest matching media occurrence.
6. **Corroboration:** cluster near-duplicate coverage so ten copies of one wire story do not count as ten independent sources.
7. **Source-risk track:** calculate transparency and risk signals for the domain, but never treat a suspicious domain alone as proof that a claim is false.
8. **Evidence relation:** label every retrieved item `SUPPORTS`, `CONTRADICTS`, `CONTEXTUALIZES`, `NOT_RELEVANT`, or `INSUFFICIENT`.

Search is candidate generation. The page, official record, archive capture, or fact-check that contains the relevant fact is the evidence. Search snippets, LLM memory, and publisher reputation alone cannot establish a verdict.

### SourceResolver contract

“Check the official source” is implemented only through an allowlisted resolver, never through
unrestricted crawling:

```python
class SourceResolver(Protocol):
    def candidates(self, claim: Claim) -> list[SourceCandidate]: ...
    def snapshot(self, candidate: SourceCandidate) -> SourceSnapshot: ...
    def relate(self, claim: Claim, snapshot: SourceSnapshot) -> list[SourceRelation]: ...
```

A resolver must declare its allowed domains, retrieval method, rate limit, and validator version.
`relate()` may use structured extraction or a bounded model proposal, but it must return the exact
source excerpt and anchor. A model-only statement such as “this page supports the claim” is not an
evidence object. If the source cannot be located, fetched, anchored, and cited, the result is
`INSUFFICIENT` and the claim remains `UNVERIFIED`.

P0 resolvers are: Fact Check Tools search, the live RSS/sitemap corpus, user-supplied cited URLs,
and a small allowlist of official domains. General web search is an optional discovery adapter and
cannot be the sole basis for a verdict.

### Example: false volcano article

```text
Article title: “China volcano erupts today”
Article image: video frame of an eruption
Article body: “Officials confirmed the event …”

Facify extracts:
  Claim A: a volcanic eruption occurred
  Claim B: it occurred in China
  Claim C: it occurred today
  Claim D: officials confirmed it

Evidence:
  frame match → older source associated with Indonesia
  official volcanology record → location/date conflict
  cited officials’ page → no matching announcement
  fact-check corpus → related recycled-footage debunk

Result:
  Claim A: SUPPORTED as an event shown by the footage
  Claim B: CONTRADICTED
  Claim C: CONTRADICTED          (the asserted date is false — see the §9 boundary rule)
  Claim D: UNVERIFIED unless the official statement is found

Rollup: Claim B is MAIN_THESIS + CONTRADICTED → first precedence row fires.
  Overall action: DO_NOT_SHARE
```

The system is not deciding whether a volcano can exist. It is checking whether each assertion in this specific document is supported by an identifiable source.

### Text-only input

Pasted text follows the same claim pipeline without a crawl. Preserve the original text, language, and user-provided context. If the text is a forwarded message with no source, return `UNVERIFIED` unless it matches a fact-check or reliable evidence record.

### Link failure modes

| Situation | Correct behaviour |
|---|---|
| Login wall/paywall/private page | Ask for a screenshot or pasted text; never bypass |
| JavaScript-only page | Try structured metadata, then a screenshot fallback; record extraction limits |
| Page changes during analysis | Keep response hash, timestamp, and extracted evidence snapshot |
| Article contains prompt injection | Treat it as quoted hostile text and record the attempted instruction |
| No corroborating coverage | `UNVERIFIED`, never automatically false |
| Article is opinion/satire | Label genre and avoid factual verdicts on opinions |

## 6. News and fact-check evidence strategy

The original “crawl 150 outlets plus Reddit, RSSHub, GDELT, transcripts, archives, and live search” plan is a good later knowledge-plane roadmap, but it is too broad and operationally fragile for 15 days.

### P0: controlled, free or predictable sources

1. **Google Fact Check Tools API** for fact-checked claim search and image search. It provides programmatic access to Fact Check Explorer-style searches and ClaimReview data.
2. **Allowlisted RSS/Atom feeds and sitemaps** from 20–30 Indian sources and fact-check publishers. Store metadata and links; do not bulk-republish copyrighted article text.
3. **Live evidence corpus:** each scheduled run fetches currently available feed items, extracts metadata and claims, deduplicates them, and stores source snapshots or links. There is no trusted pre-seeded corpus. A source becomes evidence only after the same validators used for a user request accept it.
4. **Direct source-page retrieval** only for URLs supplied by the user or discovered from an evidence result.
5. **Reverse-image discovery.** Cloud Vision `WEB_DETECTION` is free for the first
   **1,000 units/month** (~33/day), then $3.50/1k. Gated by `call_budget` like any metered provider.

*(Internet Archive CDX is **P1** — additive date confirmation, listed under P1 below, never a gate.)*

> **Why this is P0 and not deferred: the corpus cold-start problem.** The flagship demo asserts that
> a 2019 photograph is being recaptioned as a 2026 event. A live RSS corpus built over 15 days
> contains **no 2019 imagery** — an RSS feed carries days of history, not years. With local matching
> as the only discovery path, the flagship case cannot resolve, no matter how good the matcher is.
> Reverse-image discovery is what supplies the historical URLs the local corpus structurally cannot
> hold. The local corpus remains primary for *repeat* content (cache, zero cost); Vision is the
> cold-start path for content the corpus has never seen.

**Discovery and dating are separate steps.** `WEB_DETECTION` returns `pagesWithMatchingImages`
(URL, page title, score), `fullMatchingImages`, `partialMatchingImages` and `webEntities` — it
returns **no publication dates**. The date comes from fetching those matched pages through the
existing SSRF-safe fetcher and extracting JSON-LD `datePublished` / `<time>` / byline dates, which
also yields the anchored excerpt the evidence contract requires. Reverse image search is the
detective; the matched page is the citation; the archive is the notary when a date is contested.

**Privacy:** Vision accepts raw bytes via `image.content`, so a user's private upload is **never
made publicly accessible** to run this check — the §15 rule holds. Sending user media to a third
party still requires an explicit consent line at intake.

### What cron actually does

Cron is the live knowledge-plane trigger. It does not verify a user claim and it does not create a
verdict by itself. Every 15 minutes it invokes one authenticated `ingest_tick` job:

```text
scheduler
  → select feeds where next_fetch_at <= now(), maximum 5 per tick
  → fetch RSS/Atom/sitemap with ETag/Last-Modified and timeout
  → canonicalize URLs and discard already-seen content hashes
  → extract title, date, publisher, links, images, and article text/excerpts
  → create claims with source anchors
  → compute lexical/MinHash/embedding representations
  → assign origin clusters and discover related fact-check/source links
  → write live source snapshots, claims, observations, and feed_run status
  → set next_fetch_at with per-domain backoff
```

The next user request searches this live corpus before spending external search or model quota. A
user-provided URL is still fetched immediately through the request path; cron is for freshness and
breadth, not for blocking an individual verification.

**Scheduler implementation:** use Cloud Scheduler → authenticated Cloud Run Job only if the team has
an enabled Google Cloud billing account; one Scheduler job is within its three-job monthly free
allowance. Otherwise use Supabase Cron → a short authenticated ingestion endpoint. Do not run
cron inside a Cloud Run web process: instances can scale to zero or multiply. Exactly one scheduler
is enabled per environment, with one idempotency lock in the database.

**Idempotency:** `feed_run(feed_id, window_start)` is unique; a retry resumes from the last cursor.
Conditional HTTP requests, canonical URL hashes, and exponential backoff prevent repeated downloads
and duplicate claims.

### P1: useful but non-authoritative discovery

- **Internet Archive CDX lookup** for historical captures when chronology matters. Treat a capture as a dated archive observation, not as an infallible statement of truth. Additive only — no gate depends on it.
- GDELT can help discover related stories and event coverage, but its automated event extraction is not ground truth.
- Media Cloud can be useful for coverage discovery and source collections, but it does not provide unrestricted article text and requires an API key for programmatic use.
- Common Crawl is valuable for historical research, but its scale and latency make it a post-hackathon batch source, not a live request dependency.

### Defer

- Reddit ingestion
- RSSHub X-account feeds
- 150-source freshness guarantees
- Google News scraping
- SERP scraping services
- authenticated social scraping
- paid/commercial reverse-image services (TinEye-class) — the free Vision allowance covers demo
  scale; a paid tier is a post-hackathon adapter

### Why this approach is correct

Evidence retrieval must be reproducible. The system should be able to show exactly which source, capture, feed item, or ClaimReview record generated each result. A smaller, allowlisted live corpus with provenance is more credible in front of judges than a large scraper that fails live.

## 7. Claim extraction and multilingual processing

### Pipeline

```text
input text / OCR / article / transcript
        ↓
language + script detection
        ↓
structured claim extraction
        ↓
entity/date/place normalization
        ↓
fact-check and corpus retrieval
        ↓
per-claim evidence ledger
```

The LLM may propose claims, translations, entities, and search queries. It may not assign the final status.

One call per document returns every claim. Structured output, schema-validated:

```json
{
  "claims": [
    {
      "text": "The image shows an event that happened in Delhi in 2026.",
      "claim_type": "MEDIA",
      "entities": ["Delhi"],
      "dates": ["2026"],
      "location": "Delhi",
      "severity": "HIGH",
      "importance": "MAIN_THESIS",
      "coverage_expectation": "HIGH",
      "source_anchor": {
        "section": "article_body",
        "paragraph_index": 3,
        "char_start": 412,
        "char_end": 458,
        "content_hash": "sha256:..."
      },
      "search_phrases": ["..."],
      "needs_human_review": false
    }
  ]
}
```

`claim_type` uses the §5A enum exactly: `EVENT | STATISTIC | ATTRIBUTION | QUOTE | IDENTITY |
MEDIA | PREDICTION | OPINION`. `severity` and `importance` use the §9 rollup enums. Every claim
carries a `source_anchor`; a claim without one is rejected by schema validation, not stored.

> **Why the schema is pinned here:** the earlier example used `"claim_type": "event_context"`, which
> is not in the §5A enum, and omitted the anchor that §5A declares mandatory and §9 rollup depends
> on. An implementing agent would have written a claim record the verdict engine cannot roll up.

### Embeddings run locally — this is forced, not preferred

| Vector | Model class | Where | Dim |
|---|---|---|---|
| Text (claims, corpus items) | Small multilingual sentence embedding, ONNX | **Local CPU** | 384 |
| Image (frames, uploads) | CLIP/SigLIP, ONNX | **Local CPU** | 512 |

> **Why an embedding API is not an option.** 20–30 Indian outlets produce roughly 500–2,000 new
> items per day, and `ingest_tick` embeds every one at ingestion. The entire free LLM allowance is
> in the low hundreds to ~1,000 requests/day and is already committed to claim extraction and OCR.
> **An embedding API would exhaust the daily quota on ingestion alone, before a single user
> request** — and it would fail quietly, because it looks fine at test volume and starves the
> pipeline only once the corpus is running. Local ONNX inference makes ingestion entirely
> quota-free, which is what allows the knowledge plane to run every 15 minutes without touching the
> governor. Model weights load once per container; the §16 memory sizing already accounts for both
> models.

### Language scope

For 15 days, support English, Hindi, and Hinglish well. Architect the schema for more languages, but do not claim ten-language quality without evaluation data. Use templates for final phrasing so the verdict remains unchanged if the LLM is unavailable.

### Prompt-injection boundary

Fetched pages, OCR, PDFs, captions, and transcripts are hostile content. Delimit them as quoted evidence. Never place external text in a system/developer instruction position. The model output is schema-validated, source-linked, and treated as an untrusted proposal until deterministic checks pass.

## 8. Media and deepfake strategy

### What to build

#### A. Provenance verification — P1, optional live provider

Use an open C2PA implementation to parse and validate Content Credentials where present. Report:

- manifest present or absent;
- signature/validation result;
- signer identity if available;
- creation/edit assertions;
- ingredient/provenance chain;
- limitations and trust context.

Do not label “no manifest” as fake. Do not label “manifest present” as factual truth.

> **Operational limit:** platforms strip C2PA metadata during reprocessing, and a
> screenshot or a re-photographed screen produces a new file with no link to the original manifest.
> The core demo inputs — a WhatsApp forward, a screenshot — are precisely the cases where a manifest
> cannot survive, so a P0 investment would return "no manifest" on essentially every real input
> while occupying the most crowded day of the build. It remains an optional live provider: when a
> real submitted asset contains valid Content Credentials, Facify validates and displays them; when
> it does not, Facify reports `UNKNOWN` and continues with source/context analysis. No prepared asset
> is required for the product to claim this limitation honestly.

#### B. Recycled/misattributed media — P0

This is the strongest practical media path for the hackathon, and it runs in **two stages** because
one stage cannot cover both repeat and cold-start content:

**Stage 1 — local corpus (free, always runs).**
- SHA-256 for exact identity;
- pHash/dHash `bit(64)` Hamming search for near-duplicate candidates;
- CLIP/SigLIP embedding (ONNX on CPU) verifying every candidate — crop/resize/recolour robustness;
- a live image/video-keyframe corpus with dated source URLs collected by the knowledge plane;
- a conservative threshold calibrated from live matches and logged near-misses.

**Stage 2 — reverse-image discovery (governed, only on local miss).**
- Cloud Vision `WEB_DETECTION` on the raw bytes → matching page URLs;
- fetch those pages through the SSRF-safe fetcher → publish date, title, publisher, anchored excerpt;
- oldest credible instance vs the asserted date → the `MISLEADING_CONTEXT` rule;
- write the resolved match back to `media_fingerprint`, so the *second* person to share it costs zero.

Then: human-visible “matched source” and “difference/context” cards.

Do not claim that a 64-bit perceptual hash alone identifies media. Use it as a fast candidate generator, then verify candidates with an embedding or visual comparison.

> **Why two stages:** local-only matching cannot resolve media older than the corpus (§6). Vision-only
> matching burns a 33/day quota on content already verified. Local-then-Vision resolves repeats for
> free and cold-starts for one unit — and every cold-start resolution permanently enriches the
> corpus, which is the compounding loop stated in the executive summary, made concrete.

#### C. Short-video context verification — live P0 path with bounded scope

For a capped upload:

- validate the file and limit duration/size;
- extract six to twelve scene-change keyframes with ffmpeg;
- run OCR and visual embedding on frames;
- add transcription only after the core P0 flow is green and only when audio is needed for a claim;
- search the resulting claims and keyframe candidates;
- return the context/provenance result first.

This catches recycled footage, old footage with a new caption, and contradictory claims without pretending that a classifier can solve every face swap.

> **Scope boundary:** the live P0 path is a user-supplied public video or upload capped by duration,
> size, and keyframe count. It is not a promise to resolve every platform URL or every face swap. A
> real video that cannot be matched or corroborated returns `UNVERIFIED`; there is no artificial-only
> success path.

#### D. Deepfake models — P1 advisory only

Do not train a detector in 15 days. Do not put a generic pretrained face detector in the main verdict path. If time permits, add one open-source detector behind an `ADVISORY_SUSPICION` interface and evaluate it on compressed, unseen examples.

The UI should say:

> “A forensic model detected visual irregularities. This signal is not used to declare the content fake. Verify the cited context and provenance.”

The product answer to deepfakes is a layered pipeline:

```text
C2PA/provenance → known-source matching → claim/context checks
                → optional forensic advisory → human review
```

This is technically stronger than a single black-box number because the latest evaluation literature and NIST testing continue to emphasize operational performance, distribution shift, and evaluation outside a narrow benchmark.

##### The forensic advisory panel — visible depth without a decisive score

ZAIML-005 names deepfakes in its title, so the system needs a **visible** forensic surface. It gets
one, rendered prominently and wired **only** to `advisory[]`:

| Signal | Basis | Status |
|---|---|---|
| Noise-inconsistency map (Laplacian variance / wavelet SNR) | Sensor-noise discontinuity across a pasted region | Advisory, displayed |
| Frequency-domain view (DCT/FFT power spectrum) | Generator grid artifacts | Advisory, displayed |
| Open-weight detector (MIT-licensed, pretrained, CPU) | Learned features | Advisory, displayed |

Panel header, always visible: **“Forensic signals — not used in this verdict.”**

> **Why Error Level Analysis is deliberately excluded.** ELA is the obvious choice and it is the
> wrong one. It produces false positives from recolouring, brightness adjustment, in-camera HDR,
> portrait mode, resampling and **screenshots**, and it cannot distinguish an edit from naturally
> high-frequency content such as text and sharp edges; standard guidance is that it must never be a
> standalone finding. Our dominant inputs are WhatsApp forwards and screenshots — every named
> false-positive generator. ELA would light up on essentially every genuine demo image.
>
> That failure is worse here than elsewhere: a glowing heatmap beside a verdict **reads as evidence
> to every viewer**, whatever the caption says. It would reintroduce the confident-wrong-answer
> failure mode through the interface after the architecture spent a whole document excluding it from
> the engine. Noise inconsistency has an actual physical basis and does not fire on a plain
> screenshot; it still degrades under recompression, which is exactly why it stays advisory.
>
> **The strongest demo beat remains the one in §13:** the forensic panel returns *inconclusive*, and
> the dated source catches the lie anyway. That only lands if the panel is visibly excluded from the
> verdict.

#### E. Watermark and hosted verification adapters — optional

SynthID and other provider-specific watermark checks are useful when the media was generated by a supported ecosystem, but they are not universal detectors. Keep them behind a provider interface and only enable them if the exact account, model, quota, billing, and input-type access is confirmed during implementation.

Do not include an unverified “OpenAI Verify” dependency in the critical path. If a provider does not have a currently callable, documented API available to the team, it is a roadmap adapter, not an implemented capability.

## 9. Deterministic verdict engine

```python
def decide(claim, evidence, policy) -> Verdict:
    """Pure function. No network, model, or detector calls."""
```

Rules:

1. A strong ClaimReview contradiction → `CONTRADICTED`.
2. A strong dated media match that conflicts with the asserted date/location → `MISLEADING_CONTEXT`.
3. A validated attribution contradiction → `CONTRADICTED`.
4. Multiple genuinely independent, relevant sources → `SUPPORTED`.
5. Recent claim with insufficient expected coverage → `UNVERIFIED` plus `WAIT_AND_RECHECK`.
6. Source-risk evidence alone → `UNVERIFIED` plus `SEND_TO_REVIEW`. **Never `DO_NOT_SHARE`** (§3, rule 8).
7. No qualifying evidence → `UNVERIFIED`.
8. Tier E never changes the result.

### `CONTRADICTED` vs `MISLEADING_CONTEXT` — the boundary rule

The two statuses drive different actions, so the boundary must be deterministic:

| Status | Test | Example |
|---|---|---|
| `CONTRADICTED` | The **asserted proposition itself** is false | "The eruption occurred in China" — it did not |
| `MISLEADING_CONTEXT` | The proposition is **true**, but its framing — date, place, actor, or causal link — is not | Real eruption footage, presented as today's event |

Applied to the §5A volcano example: Claim B (`in China`) and Claim C (`today`) are each
`CONTRADICTED`, because each asserted fact is false. The **document as a whole** is
`MISLEADING_CONTEXT`, because it uses genuine footage under a false frame.

> **Why this rule was added:** the worked example previously resolved Claim C as "`CONTRADICTED` or
> `MISLEADING_CONTEXT`". If the plan cannot decide, the engine cannot either — and for a system
> whose entire pitch is determinism, an undefined boundary between two of four statuses is a hole a
> judge can open with one question. The two statuses also map to different user actions
> (`DO_NOT_SHARE` vs `SHARE_WITH_CONTEXT`), so the ambiguity reaches the user.

### Case rollup — N claim statuses to one action

Claim statuses are per-claim; `overall_action` is per-case. Each claim also carries `severity`
(`LOW | MEDIUM | HIGH | CRITICAL`) and `importance` (`HEADLINE | MAIN_THESIS | SUPPORTING_DETAIL |
BACKGROUND`). Precedence is evaluated in order:

| Condition | `overall_action` |
|---|---|
| Any `CONTRADICTED` claim with `importance ∈ {HEADLINE, MAIN_THESIS}` **or** `severity = CRITICAL` | `DO_NOT_SHARE` |
| Any `CONTRADICTED` claim with `severity = HIGH` | `DO_NOT_SHARE` |
| Any `MISLEADING_CONTEXT` claim with `importance ∈ {HEADLINE, MAIN_THESIS}` **or** `severity ∈ {HIGH, CRITICAL}` | `SHARE_WITH_CONTEXT` |
| Any remaining `CONTRADICTED` or `MISLEADING_CONTEXT` (i.e. `SUPPORTING_DETAIL`/`BACKGROUND` at `LOW`/`MEDIUM`) | `SHARE_WITH_CORRECTION` |
| Else any claim `UNVERIFIED` **and** inside the developing window | `WAIT_AND_RECHECK` |
| Else any claim `UNVERIFIED` **and** source risk is `HIGH` | `SEND_TO_REVIEW` |
| Else all claims `SUPPORTED` | `SAFE_TO_SHARE` |
| Else | `SEND_TO_REVIEW` |

A `SUPPORTED` claim never raises the action; only contradiction and uncertainty move it. Rollup is
part of the pure engine and is snapshot-tested with the rest of `decide()`.

“Material” is not a judgement call: it is `importance ∈ {HEADLINE, MAIN_THESIS}` or
`severity ∈ {HIGH, CRITICAL}`, both assigned at extraction (§7) and stored on `claim`. Rows are
evaluated top to bottom and the first match wins.

> **Why this was added:** the API response carried per-claim statuses and a single
> `overall_action`, but no rule combined them — leaving the field the user actually reads
> undefined whenever a document mixes supported and contradicted claims, which is the normal case
> for a real article. Precedence had to be *stated* rather than left to whoever writes the endpoint,
> or the same input would produce different actions across code paths.

### Evidence strength

The score is a deterministic explanation index, not a probability:

```text
strength = f(
  evidence quality,
  relevance to the exact claim,
  independent-origin count,
  temporal confidence,
  source transparency,
  conflict penalty
)
```

It must show its components and citations. Never show `0.82` without explaining what produced it. Avoid a global “authenticity score” that conflates provenance and truth.

### “Independent” means origin-cluster independent

Ten outlets repeating one wire story count as one origin cluster. Store:

- normalized text shingles;
- named entities and dates;
- quoted-source relationships;
- canonical URL and publisher;
- origin cluster.

Corroboration is support, not proof. The UI should explicitly show “3 articles, 2 origin clusters.”

## 10. Evidence graph and data model

Use Supabase Postgres with pgvector for the judged MVP. The free plan currently provides a 500 MB database, 1 GB file storage, 5 GB uncached plus 5 GB cached egress, and a 50 MB maximum file upload; keep raw media out of the durable store and enforce tight limits.

```text
case                 id, input_type, language, created_at, status
content_object       id, case_id, sha256, phash bit(64), embedding, source_url
claim                id, case_id, text, normalized_text, language, entities,
                     severity, importance, source_anchor
evidence             id, claim_id, kind, direction, finding, citation_url,
                    publisher, observed_at, method, match_quality, match_basis
source                id, domain, publisher, feed_url, source_class,
                     allowed_for_primary_check, last_seen_at, risk_signals
source_snapshot       id, source_id, url, final_url, fetched_at, content_hash,
                     excerpt, archive_url, extraction_method, http_status
claim_anchor          id, claim_id, input_kind, paragraph_index, char_start,
                     char_end, frame_start_ms, frame_end_ms, audio_start_ms,
                     audio_end_ms, content_hash
media_match           id, content_object_id, source_object_id, distance,
                     metric, threshold, source_date, citation_url
source_relation       id, claim_id, snapshot_id, relation, excerpt,
                     source_anchor, validator, validator_version
observation           id, case_id, content_object_id, claim_id, observed_at,
                     raw_claim, trust_state(raw|validated|promoted)
verdict               id, claim_id, status, action, reason, strength_json,
                      rule_version, created_at

-- corpus write-back: the compounding loop
media_fingerprint     hash, phash, embedding, times_seen, first_verified_at,
                      last_verified_at, last_verdict
claim_occurrence      claim_id, case_id, content_object_id, observed_at,
                      caption_text, source_domain
origin_cluster        id, minhash_signature, canonical_publisher, first_seen_at

-- cache and budget
verdict_cache         cache_key, case_id, status_json, rule_version,
                     extractor_version, corpus_version, policy_profile,
                     language, created_at, expires_at
call_budget           provider, day, used, cap      -- governor counters
feed_run              id, feed_id, window_start, ran_at, item_count, failure_reason,
                      cursor                        -- UNIQUE (feed_id, window_start)
feed                  id, url, domain, next_fetch_at, etag, last_modified,
                      backoff_seconds, enabled
```

**Embedding columns are explicit, because the migration needs them:**
`content_object.embedding` and `media_fingerprint.embedding` are **image** embeddings
(`vector(512)`, CLIP/SigLIP class). `claim.embedding` and `corpus_item.embedding` are **text**
embeddings (`vector(384)`, small local model). Store as `halfvec` where retrieval quality allows —
a 512-dim `halfvec` is ~1 KB/row, so 100k rows is ~100 MB of vectors before indexes, against a
500 MB cap. Index `bit(64)` pHash with HNSW/Hamming and vectors with HNSW/cosine.

Every request writes an `observation`; only a validated match or reviewed finding is promoted into
`media_fingerprint`, `claim_occurrence`, or `origin_cluster`. Raw user submissions never become
trusted evidence merely because they were repeated.

> **Why these tables were added:** the original schema had no write-back path, which left three
> stated product claims unimplemented. (1) "Every validated verification improves the next one" —
> nothing wrote verification results anywhere retrievable, so the corpus could only grow from RSS feeds.
> (2) The recurrence and caption-variant views promised in §13 and §18 had no backing tables.
> (3) "Repeat-content cache hit rate" and "source/case recurrence rate" are listed in §19 as
> day-one investor metrics but were not measurable from the schema. Observations are cheap to store;
> only validated relations are promoted into the trusted graph.
>
> `verdict_cache` and `call_budget` exist because §16's cost controls were specified as behaviour
> with no owning component; a bullet list does not enforce a quota.

### Recurrence and caption variants — P0, not P1

```sql
-- "seen 47 times, first on 12 Mar 2024"
SELECT times_seen, first_verified_at FROM media_fingerprint WHERE phash <~> :p < :threshold;

-- "one image, six contradictory captions"
SELECT caption_text, source_domain, observed_at FROM claim_occurrence
WHERE content_object_id IN (...) ORDER BY observed_at;
```

`phash` is a `bit(64)` column, and `<~>` is pgvector's Hamming-distance operator for the `bit` type
(added in pgvector 0.7.0; HNSW and IVFFlat both index it). The adapter owns threshold units and
rejects a candidate unless the subsequent embedding comparison also passes.

> **Why promoted to P0:** "Identify misinformation patterns" is a **named ZAIML-005 deliverable**.
> Leaving it at P1 risks shipping a plan that omits one of the five things the brief explicitly
> asks for. Once the write-back tables exist these are two queries and one card — among the
> cheapest deliverable-coverage available, and the recurrence line is a strong demo beat in its own
> right.

Do not add multi-tenant billing, BYOK, SSO, mTLS, or a complex transparency log before the core flow works. Keep `tenant_id` and `provider_version` in the schema so the product can evolve without migration pain.

### Optional trust artifact

For the hackathon, sign the canonical JSON evidence digest with an Ed25519 development key and expose a public verification page. Call it a **tamper-evident result receipt**, not a legal certificate or universal truth stamp. A full public transparency log is a post-hackathon hardening step.

## 11. AI and backend process

### Model responsibilities

| Task | AI allowed? | Required control |
|---|---:|---|
| OCR/transcription | Yes | Preserve raw extraction and language |
| Claim decomposition | Yes | JSON schema, original text retained |
| Translation/phrasing | Yes | Templates and citation links |
| Search query generation | Yes | Query is logged and bounded |
| Source ranking | Limited | Deterministic relevance and source policy |
| Verdict | No | Pure evidence engine |
| Evidence strength | No | Deterministic arithmetic |
| Deepfake suspicion | Optional | Advisory, calibrated, never decisive |

Use a current low-cost/ free-tier multimodal model only for bounded extraction. Do not use live web grounding as the only evidence store. URL-context and Google Search grounding are useful capabilities, but their availability, model support, rate limits, and pricing change; the core product must continue to work using the owned corpus and explicit citations.

### The model call budget is the binding constraint — design to it

Provider allowances are account- and model-specific, and both daily and per-minute ceilings can
change. Measure them in the team account before Day 1. The product must be safe if the usable
allowance is much smaller than expected.

| Conservative implementation cap | Implication |
|---|---|
| Default lightweight model | Start at 50 completed verifications/day and five concurrent extractions; adjust only after measuring the team account |
| Higher-capability model | Escalation only for schema failure or unusable multimodal extraction; cap it separately |
| Premium/preview model | Assume unavailable until the team account proves otherwise |

Four rules follow, and they are implementation requirements, not advice:

1. **One extraction call per document.** Claim segmentation, entity/date normalization, and
  `search_phrases` come back in a **single** structured response, not three calls.
2. **The lowest-cost model that meets the schema by default.** Escalate only when schema validation
  fails or the input is unusable. Record the model ID that served each call.
3. **Cache extraction by content hash.** Re-sharing the same article, or re-running a live audit URL
after a code change, must cost zero model calls while the source snapshot remains valid.
4. **Template phrasing, never a model call.** The final wording is assembled from templates plus
  citations, so the response path is quota-independent.

The governor enforces a per-day cap below the provider's own limit and surfaces `capacity limited`
rather than a provider error.

> **Why this was added:** the plan previously described model usage as "bounded" and
> "rate-limited" without an implementation budget. A single Day 13 evaluation pass can consume the
> usable daily allowance, and a rerun after a fix can exhaust it — so the evaluation gate could
> fail for quota reasons rather than quality reasons.
> The per-minute ceiling is worse in front of judges: three items shared in quick succession can
> trip it live. Batching, cheap-model routing, and extraction caching turn a hard external limit
> into a design parameter.

### Backend request lifecycle

```text
POST /v1/verify
  → validate input and policy
  → create case
  → local hash/probe
  → cache/corpus probe
  → extract claims and media candidates
  → retrieve evidence
  → run deterministic verdicts
  → persist ledger and receipt
  → return response or async case id
```

For the demo, synchronous processing should target 3–8 seconds for text, URLs, images, and PDFs. Video can return `202 Accepted` with a progress state and complete within 30 seconds.

## 12. API contract

### Endpoints

```text
POST /v1/verify
POST /v1/verify/file
GET  /v1/cases/{case_id}
GET  /v1/cases/{case_id}/evidence
GET  /v1/receipts/{receipt_id}
POST /internal/ingest-tick   (scheduler-authenticated, not public)
GET  /healthz
```

### Request

```json
{
  "url": "https://example.org/story",
  "text": null,
  "language": "hi",
  "mode": "fast | deep",
  "consent_to_process_media": false
}
```

### Response shape

```json
{
  "case_id": "case_123",
  "overall_action": "SHARE_WITH_CONTEXT",
  "claims": [
    {
      "claim_id": "cl_1",
      "text": "The image shows a 2026 event in Delhi.",
      "severity": "HIGH",
      "importance": "MAIN_THESIS",
      "status": "MISLEADING_CONTEXT",
      "reason": "The same image is cited in a dated 2019 source.",
      "strength": {
        "score": 0.91,
        "components": ["dated_media_match", "source_citation"]
      },
      "evidence": [
        {
          "kind": "dated_source",
          "publisher": "Example Publisher",
          "citation_url": "https://example.org/original",
          "source_snapshot_id": "snap_456",
          "source_excerpt": "The same image was published on 14 March 2019.",
          "source_anchor": { "paragraph_index": 2, "char_start": 88, "char_end": 142 },
          "input_anchor": { "frame_start_ms": 4200, "frame_end_ms": 8700 }
        }
      ]
    }
  ],
  "media_provenance": "UNKNOWN",
  "source_risk": "MEDIUM",
  "advisory": [],
  "receipt_url": "https://facify.example/receipts/receipt_123"
}
```

## 13. User experience that sells the product

### Mobile result card

The first screen must communicate the decision in under three seconds:

```text
MISLEADING CONTEXT
Real image. Wrong date/caption.

Why?
✓ Same image found in a dated 2019 source
✓ Current post claims 2026
⚠ No cryptographic provenance found

[See evidence] [Share correction] [Report for review]
```

The evidence screen then shows:

- extracted claim;
- timeline;
- source cards with publisher, date, and URL;
- media match preview;
- “what Facify cannot establish”;
- English/Hindi toggle;
- safe shareable correction card.

### Investor demo sequence

**Open on the strongest path, close on the forensics beat.**

1. Share a viral image or fake circular from Android — the most complete path, and the most
   memorable claim.
2. Show the extracted claim, its paragraph/frame anchor, and the language.
3. Show the dated source or ClaimReview result: *genuine media, fabricated context.*
4. Show the evidence graph/timeline.
5. Recurrence: same frame, several dates, contradictory captions across languages.
6. Submit a genuinely novel claim → `UNVERIFIED` + `SEND_TO_REVIEW`, with what was checked listed.
7. Open the API response and receipt to prove this is a platform, not only a UI.
8. **Close with video:** share a suspected deepfake clip. The forensic panel returns *inconclusive*,
   greyed and labelled excluded — and the keyframe still resolves to a dated source.

> **Why this order:** the earlier draft opened with video and audio forensics, which is the
> **least-built path** in this plan (video is bounded P0, ASR is P1). If anything slips, that
> ordering opens the demo on the weakest thing you own. Leading with false context leads with the
> most complete path, and moving the forensic beat to the close turns "the detector could not tell"
> from an apology into the punchline.
>
> **Step 6 must show `SEND_TO_REVIEW`, not `DO_NOT_SHARE`.** A novel claim with no citations has no
> `CONTRADICTED` or `MISLEADING_CONTEXT` finding, so §9 rollup and §3 rule 8 both forbid
> `DO_NOT_SHARE`. Demoing an accusation built on absence of evidence would contradict the engine on
> stage — and "we abstain rather than accuse" is the stronger claim anyway.

### The “trust moment”

Demonstrate a detector result that is inconclusive, then show that Facify still catches the false context through a dated source. This explains why the company is not competing in the weakest part of the market.

## 14. Live evaluation and red-team audit

The evaluation set is a manifest of real public URLs, real public media, and real fact-check/source
pages collected during operation. It is not preloaded evidence and is never inserted into the trusted
corpus by hand. Each item stores its retrieval timestamp, source snapshot hash, expected evidence
relationship, and reviewer label. The live pipeline must resolve the item from the public source or
abstain.

Build the manifest continuously from real cases across these categories:

| Live category | Required coverage |
|---|---|
| **Credible genuine articles and announcements** | **≥ 35 items — a hard floor, see below** |
| Published fact-check matches | Text and image ClaimReview results |
| Real recycled media with changed context | Public debunk/source pairs |
| Fake quote or fabricated attribution | Published fact-check/source pairs |
| Government notice/PDF claims | Public official pages and published debunks |
| Recent/developing claims | Live items where the correct answer is abstention |
| Public AI/provenance examples | Only when a real manifest or provider signal exists |
| Ambiguous/adversarial input | Real hostile pages, malformed inputs, and prompt-injection samples |

Report **over the whole live audit manifest, not a demo subset**:

- precision for `CONTRADICTED` and `MISLEADING_CONTEXT`;
- **false-positive rate on genuine content, with the case count shown alongside**;
- citation coverage across all decisive results;
- **abstention rate** — the share of cases correctly returning `UNVERIFIED`;
- median and p95 latency by input type;
- provider failure rate and fallback behavior;
- bilingual explanation quality reviewed by a human.

Success targets for the live run:

```text
≥ 90% citation coverage across ALL decisive live results
≥ 35 genuine-content items in the manifest — below this the gate does not pass
≤ 10% false-positive rate on that sample, with sample size shown
abstention rate reported, not minimized
100% of decisive results expose the rule and citation that caused them
0 Tier E-only verdicts
0 verdicts with empty evidence
```

> **Live-data rule:** if a public source changes, disappears, rate-limits, or cannot be cited, the
> run records that failure and returns `UNVERIFIED`; it does not substitute hand-authored evidence.

> **Why the genuine-content floor is a hard number:** false-positive rate on genuine content is the
> metric that decides whether this system is safe to put in front of the public, and it is the one
> metric a sample size can silently invalidate. With 8 genuine items the only observable rates are
> 0%, 12.5% and 25% — a single failure already exceeds the 10% target, and 0/8 has a confidence
> interval reaching past 30%. Showing the sample size makes that visible but not valid. At 35 items
> each failure moves the rate about 2.9%, giving the target real resolution. Genuine articles are
> also the cheapest items to collect from allowlisted sources, so this costs collection time, not
> build time.

> **Reproducibility:** every audit run is reported **"as of" a timestamp, against a pinned
> `source_snapshot` set**, so Day 13 and Day 15 runs are comparable and a judge can be shown what
> was retrieved and when. Live drift is expected; unrecorded drift makes the numbers indefensible.

Do not report benchmark accuracy from a public deepfake dataset as if it measured production truth verification. If an advisory detector is included, report its dataset, compression level, threshold, and out-of-distribution behavior separately.

**The benchmark literature cited in §22 is evidence for distrusting detectors, never a performance
claim.** NIST OMFC and DeepfakeBench appear in this plan to justify why Tier E is advisory — they
must never be quoted in the deck as a number Facify achieves or inherits.

> **Why this needed saying:** §14 forbids reporting public-dataset accuracy, and §22 then cites two
> deepfake benchmarks as sources. That is a coherent position — the benchmarks show detectors
> degrade under distribution shift — but the two statements sit far apart in the document, and the
> easiest slide to accidentally build is one that pairs a benchmark logo with an implied accuracy.
> Stating the intended use next to the prohibition closes the gap.

## 15. Security, privacy, and responsible claims

### Build now

- SSRF protection and redirect re-checks;
- file size, duration, MIME, and decompression limits;
- malware-safe PDF/image processing;
- no secrets in the mobile application;
- API key in server environment only;
- EXIF GPS removed before persistence;
- raw media short TTL and explicit consent;
- never make a private user upload publicly accessible solely to call a third-party image-search API;
- prompt-injection cases from real fetched pages, OCR, and PDFs;
- rate limit and request IDs;
- audit event for every verdict and evidence retrieval;
- clear “not a legal or final fact-check” language.

### Do not claim during the hackathon

- universal deepfake detection;
- legal certification;
- guaranteed truth;
- complete coverage of social platforms;
- compliance certification;
- “tamper-proof” archives;
- a universal credibility score for publishers;
- **any statistic without a citation** — no market percentages, no "detectors degrade by X%", no
  "N% of Indian misinformation is …", no latency or cost-reduction figures we have not measured;
- **elimination of legal liability.** The defensible claim is an auditable evidence trail and
  calibrated abstention, which *reduce* exposure. Nothing eliminates it.

> **Why the statistics rule is explicit:** three separate strategy reviews of this plan supplied
> confident round numbers — "over 80% of Indian misinformation is real media with false captions",
> "classifiers degrade 40–60% on unseen generators, as proven by NIST", "90% of misinformation
> circulates on WhatsApp", "reduces moderation cost by 95%" — and none was sourceable. Each is
> directionally plausible, which is what makes them dangerous: a judge who checks one and finds
> nothing discounts every other number in the deck. This plan already refuses to publish its own
> unvalidated unit economics (§16); the same rule applies to borrowed figures.

The DPDP and security roadmap should be reviewed with counsel before making legal deadline or compliance claims. Implement privacy-by-design controls now; do not present future SOC 2/ISO work as present capability.

## 16. Free-tier and buildability assessment

### Recommended demo topology

```text
Cloud Run (India region)  FastAPI + web frontend container
                          1 vCPU / 1.5 GB RAM — the 512 MB default OOMs on OpenCV + ONNX
                          min-instance=1 during judging; CLIP/ONNX load makes cold start seconds
Supabase                  Postgres + pgvector + small evidence store
Supabase Cron / Cloud Scheduler  authenticated `ingest_tick` trigger
Cloud Run Job              live feed ingestion worker; exits after each batch
CI                        tests only — no scheduled jobs, no provider credentials
Live evidence corpus       real source snapshots, claims, observations, validated relations
Google Fact Check API     claim/image fact-check lookup where quota is available
Cloud Vision WEB_DETECTION  reverse-image discovery on local miss; 1,000 units/mo, governed
C2PA open-source library  local provenance validation (P1)
ffmpeg                    local keyframe extraction
Local ONNX models         image embedding (CLIP/SigLIP) + text embedding — CPU, no quota
LLM free tier             bounded extraction/OCR, governed — see §11 budget
Internet Archive CDX      occasional historical capture lookup (P1)
Pre-warmed verdict cache  real verdicts from real sources, served if providers are unreachable
```

> **Why a pre-warmed cache is listed infrastructure:** Day 15 rehearses a failure mode that nothing
> in the topology could previously support — with live providers as the only path, a rate limit or a
> 503 during judging ends the demo. Pre-warming runs real inputs through the live pipeline ahead of
> time; what is served later is a real verdict with its retrieval timestamp shown (see the data
> principle carve-outs at the top of this document).

> **Why ingestion is a job:** the scheduler only triggers work. The Cloud Run Job fetches a bounded
> batch of real feeds, writes live source snapshots and claims, records failures, then exits. This
> avoids duplicate in-process schedulers and makes retries observable.

Cloud Run has an always-free request/compute allowance and new accounts may have credits, but network egress, build systems, artifact storage, and other services can still incur cost. Note that the always-free compute allowance applies only in selected US regions — deploying in the India region is a deliberate latency choice with a cost consequence, and should be budgeted rather than assumed free. Supabase free is sufficient for a small demo, not for storing many raw videos. CI runs tests only; scheduled ingestion runs server-side, and provider credentials never enter a public repository.

### Cost controls

- cache by content hash and canonical URL;
- cap each request to one extraction call and one retrieval pass;
- use local deterministic checks before model calls;
- store metadata and evidence URLs, not full article bodies;
- cap video at 30–60 seconds and 480p;
- use a feature flag for every paid provider;
- record provider, model, latency, tokens, and failure reason;
- show “capacity limited” rather than silently degrading to fabricated certainty.

Do not publish the original plan’s 100,000-check unit economics yet. It is not validated against actual provider quotas, platform restrictions, storage, egress, and cache hit rate. Instrument the MVP first; produce the investor model from measured numbers.

## 17. Fifteen-day execution plan

### Day 0 (before the sprint) — Connect real sources

- obtain API credentials and verify live quotas in the team accounts;
- configure 20–30 allowlisted RSS/Atom/sitemap sources and official domains;
- configure Supabase Cron or Cloud Scheduler with one `ingest_tick` owner;
- run the first real ingestion batch and inspect source snapshots, claims, and failures;
- record a live-case manifest of public URLs for audit, without promoting them into trusted evidence.

### Day 1 — Freeze the product and evidence contract

- finalize the four claim statuses and three dimensions;
- define the live audit manifest format and source-snapshot retention policy;
- define the JSON schemas and golden responses;
- create the source register and provider risk table;
- record ADR-001: evidence-first, abstention by default.

**Gate:** every judge-facing result can be described as a claim plus evidence.

### Day 2 — Backend skeleton and database

- FastAPI, Supabase schema, migrations, health endpoint;
- case/content/claim/evidence/verdict repositories;
- **write-back tables** (`media_fingerprint`, `claim_occurrence`, `origin_cluster`);
- **cache and governor tables** (`verdict_cache`, `call_budget`, `feed_run`);
- request IDs, structured logs, environment configuration;
- implement the first live `ingest_tick` and verify idempotent feed runs;
- **scaffold the Android app in parallel**: project, `ACTION_SEND` intake, and a screen that posts
  to `/v1/verify` and renders raw JSON. No design work.

> **Why the Android shell starts on Day 2:** the app needs only the API contract, which Day 1
> freezes — it does not need the pipeline. Leaving the entire mobile client on Day 11 puts the
> **judged surface** in the last third of the schedule, where every upstream slip lands on it, and
> Day 11 currently carries intake, upload, polling, a bilingual result card and a share card in one
> day. Splitting it costs nothing on Day 2 and converts Day 11 from "build the app" into "finish the
> result card", which is achievable.

**Gate:** a real public feed item can be ingested, anchored, searched, and retrieved through the API.

> **Why the extra tables land on Day 2:** live observations, source snapshots, claim anchors, and
> validated relations must exist from the first real request. Otherwise the live-data claim is only
> a future migration.

### Day 3 — Pure verdict engine

- implement `decide()`;
- implement deterministic evidence strength;
- add conflict handling and abstention;
- **implement the `CONTRADICTED`/`MISLEADING_CONTEXT` boundary rule and the case rollup rule (§9)**;
- add golden tests and the Tier E non-interference test.

**Gate:** verdicts work without a model, network, or database; rollup is snapshot-tested.

> **Note on scope:** this is built from nothing — the repository starts at a planning baseline with
> no prior implementation. Day 3 is the highest-leverage day in the schedule: the engine is pure,
> has no dependencies on the database, network or any model, and every invariant the rest of the
> system relies on is enforced here. Give it the time, and write the tests first.

### Day 4 — Text and claim pipeline

- English/Hindi/Hinglish detection;
- structured claim extraction;
- deterministic normalization;
- template phrasing;
- prompt-injection cases collected from real fetched pages and OCR/PDF inputs.

**Gate:** pasted text produces claims with stable JSON.

### Day 5 — Fact-check and corpus retrieval

- integrate Google Fact Check Tools API if credentials/quota are available;
- persist live ClaimReview responses with retrieval timestamps; use only those prior live responses as a fallback;
- load local ONNX text-embedding model; implement hybrid lexical + embedding retrieval;
- attach citations and publisher/date fields.

**Gate:** known fact-checked cases resolve with citations even if the external API is unavailable.

### Day 6 — RSS/sitemap knowledge ingester

- add 20–30 allowlisted sources;
- parse RSS/Atom/JSON-LD;
- normalize titles, dates, URLs, publishers;
- deduplicate by canonical URL and MinHash;
- record fetch failures and freshness;
- **verify origin clustering has actually fired on live data.**

**Gate:** the corpus can be rebuilt deterministically from feed snapshots, **and at least one
multi-outlet origin cluster exists** — a real wire story carried by two or more allowlisted outlets,
correctly collapsed to a single origin.

> **Why this gate exists:** origin-cluster independence is a flagship correctness rule and the UI
> promises "3 articles, 2 origin clusters". Indian syndication is pervasive enough that duplicates
> should appear naturally across 20–30 feeds, but "should" is not a check. If no cluster has formed
> by Day 6, the MinHash threshold is mistuned or the feed mix is too narrow — both are cheap to fix
> on Day 6 and expensive to discover on Day 13 with nothing to demonstrate. Subscribing to outlets
> that carry the same wire service is a feed-selection decision, not synthetic data.

### Day 7 — URL resolver and source-risk track

- SSRF-safe fetcher;
- JSON-LD/OpenGraph/article extraction;
- paragraph-level claim anchors and extracted-page hash;
- attribution and quote checks against cited source pages;
- source profile: domain age when available, transparency fields, typosquat candidates;
- direct attribution check against cited publisher pages.

**Gate:** public URLs work; blocked/private pages fail honestly.

### Day 8 — Image and PDF path

- pHash/dHash **candidate retrieval, then embedding verification of every candidate**;
- threshold calibration on real and altered examples;
- OCR;
- PDF text extraction and page preview;
- evidence/timeline UI data;
- write every attempt to `observation`; promote only validated matches to `media_fingerprint`.

**Gate:** real public recycled-image and misleading-PDF cases work end-to-end; a near-miss image does
**not** produce a match.

> **Why C2PA moved off this day:** it was the fifth capability on the single most crowded day, and
> it returns "no manifest" on many realistic inputs (see §8A). It remains an optional live provider.
> The freed time goes to embedding verification and threshold
> calibration, because an uncalibrated media matcher produces the worst possible failure — a
> confident, cited, wrong answer — and a 64-bit perceptual hash alone cannot carry that decision.

### Day 9 — Dated-source and archive path

- collect dated-media records from live public sources as they are encountered;
- source-date extraction;
- **reverse-image discovery on local miss** (Vision `WEB_DETECTION`, governed) → matched page URLs;
- fetch matched pages → publish dates, publisher, anchored excerpt;
- context mismatch rule;
- evidence timeline;
- write resolved matches back to `media_fingerprint` so repeats cost zero;
- **(P1, optional)** Internet Archive CDX lookup with timeout/fallback — additive confirmation only.

**Gate:** “real image, wrong context” is the flagship demo, **resolved from matched-page publish
dates alone**, with CDX disabled.

> **Why CDX is explicitly excluded from the gate:** §6 lists Internet Archive lookup as P1, but it
> was scheduled inside the day whose gate is the flagship demo — so the demo appeared to depend on a
> deferred, slow, externally-owned service. Page-level publish dates carry the common case; the
> archive is a notary for the cases where the verdict hinges on a contested date. Proving the gate
> with CDX off means an archive outage on demo day costs a confirmation, not the flagship.

### Day 10 — Short-video path

- upload limits;
- ffmpeg keyframes;
- OCR; transcription only if the P0 gates are already green;
- frame-to-corpus matching;
- asynchronous status for longer processing.

**Gate:** one recycled-video case works and one inconclusive case abstains.

### Day 11 — Android result experience

*(Intake shell and raw-JSON screen already exist from Day 2.)*

- minimal permissions;
- upload progress and result polling;
- Hindi/English result card;
- shareable correction card.

**Gate:** a judge can share content from WhatsApp/browser/gallery into Facify.

### Day 12 — Evidence console and receipt

- claim list;
- evidence cards;
- timeline;
- source-risk panel;
- **recurrence card ("seen N times, first on X") and caption-variant list**;
- advisory panel visibly excluded;
- content-addressed result receipt and local verification view.

**Gate:** the complete explanation is visible without opening logs.

### Day 13 — Evaluation, reliability, and red team

- run the live audit manifest against current public sources, pinned and timestamped;
- measure precision, false positives, citation coverage, latency;
- test malformed files, SSRF payloads, prompt injection, duplicate requests;
- disable each optional provider and confirm deterministic fallback.

**Gate:** no empty-evidence decisive verdicts, no Tier E-only decisions, **and ≥35 genuine-content
items in the manifest** — the false-positive figure is not reportable below that.

### Day 14 — Investor polish and startup surface

- API example and OpenAPI page;
- simple newsroom queue;
- recurrence/caption-variant view;
- product metrics dashboard;
- architecture and moat slide;
- pricing hypothesis and pilot workflow.

**Gate:** the same engine is visibly usable by a consumer and a newsroom.

### Day 15 — Freeze, rehearse, and package

- freeze dependencies and model IDs;
- verify live ingestion and provider failure modes;
- **pre-warm the demo set through the live pipeline and rehearse with providers unreachable**
  (cached real verdicts, retrieval timestamps visible);
- record a backup demo video;
- prepare judge Q&A;
- publish evaluation report and limitation register.

**Gate:** every claim in the pitch can be demonstrated or is clearly labelled roadmap.

## 18. Scope control: P0, P1, and roadmap

### P0 — must ship

- evidence ledger;
- deterministic verdict engine **including the boundary and rollup rules**;
- public-link crawler with SSRF protection, article extraction, claim-span anchors, and citation snapshots;
- generic-public-web resolver; X/YouTube metadata support only when available, with screenshot/upload fallback;
- English/Hindi claim extraction;
- fact-check lookup plus a timestamped cache of prior live ClaimReview responses;
- RSS/sitemap live corpus with natural origin clustering;
- URL/PDF/image flow;
- bounded live short-video flow: keyframes, OCR, and media/context matching;
- pHash candidate retrieval **plus embedding verification**;
- **governed reverse-image discovery on local miss, with matched-page date extraction**;
- **corpus write-back and recurrence/caption-variant views**;
- **verdict cache, negative caching, and the call governor**;
- **forensic advisory panel** (noise-inconsistency + frequency view), visibly excluded from verdicts;
- source-risk panel;
- Android share target;
- web evidence console;
- live audit report with genuine-content sample size shown;
- SSRF and prompt-injection protections;
- live failure states and provider-capacity reporting;
- **pre-warmed verdict cache and an offline-capable demo path**;
- **snapshot-replay test suite** (deterministic CI against stored `source_snapshot` rows).

### P1 — ship only after P0 is reliable

- C2PA validation when a real submitted asset contains credentials;
- ASR;
- Internet Archive lookup;
- advisory deepfake model;
- signed receipt;
- API key authentication.

> **Why P0 changed:** four items moved in and one moved out, each for a stated reason above —
> recurrence because it is a named ZAIML-005 deliverable (§10), cache and governor because the
> free-tier model budget makes them survival rather than optimization (§11), the generic-web
> resolver because links are the most likely judge input (§5), live failure reporting because the demo must
> remain honest when a real provider fails (§16), and C2PA remains optional because it cannot be
> guaranteed on reprocessed public inputs (§8A).

### Post-hackathon roadmap

- newsroom and platform pilots;
- metered API and batch verification;
- larger source registry and multilingual expansion;
- temporal re-check jobs;
- human fact-checker network;
- trend alerts and early-warning graph;
- provider plugins for watermarks and commercial visual search;
- full transparency log;
- tenant isolation, BYOK, SSO, mTLS, regional deployment;
- enterprise retention, deletion, audit, and compliance programs.

## 19. Startup model after the hackathon

### Competitive landscape and the wedge

| Player | What they do | Where they stop | Facify's wedge |
|---|---|---|---|
| **Reality Defender** | Enterprise multi-model synthetic-media ensemble (spatial, temporal, frequency, audio antispoof) | Synthetic detection only — blind to real media under a false caption | Context + provenance + forensics, not forensics alone |
| **TrueMedia.org** | Open-sourced detector ensemble (MIT), human-in-the-loop | Ceased operating as a service; hosting an ensemble was the stated cost problem | Cache-first, CPU-only, governed quota — the economics that shut them down are the constraint we designed to |
| **Factiverse** | Claim extraction + stance detection against ClaimReview and live search, newsroom CMS integration | Text-heavy; weak on recycled media and video | Claim-to-frame anchoring across image, video and PDF |
| **NewsGuard** | Human-curated domain credibility labels and false-narrative fingerprints, licensed B2B | Analyst-paced; does not resolve an individual viral item in real time | Automated source-risk plus per-claim resolution, India-first |
| **InVID / WeVerify** | The OSINT forensic workbench — keyframes, reverse search, forensic filters | Manual; requires a trained analyst to interpret | Automated synthesis into a cited, deterministic verdict |
| **Typical hackathon entry** | Upload → "87% fake" | No citation, no provenance, no audit trail | An evidence trail a reviewer can independently check |

> **One case to know before Q&A: Logically.ai.** Frequently cited as the model for this category
> (£/$ tens of millions raised, government and platform contracts). It **entered administration in
> July 2025** after Meta and TikTok wound down fact-checking programmes, and its assets were sold in
> a pre-pack deal. The lesson is not that the technology failed — it is that **revenue concentrated
> in a few platform trust-and-safety contracts is politically fragile.** Our answer is the ladder
> below: consumer distribution, newsroom seats, and metered API across several buyer types, so no
> single policy reversal removes the business. Expect this question; do not cite Logically as an
> aspiration.

### WhatsApp tipline — roadmap, with its real cost stated

WhatsApp is where Indian misinformation actually circulates, and a tipline is the natural consumer
surface. It is **not** a 15-day zero-cost item: the Business API cannot be accessed directly — it
requires a Business Solution Provider (markup and/or monthly fee), business verification,
display-name approval and template pre-approval, and from **1 October 2026 Meta bills per business
message, including service replies inside the 24-hour window.**

The Android `ACTION_SEND` share target reaches the same content with **no Meta relationship at
all**, which is why it is P0. Present the tipline as a costed roadmap item with a named path, never
as a demo artifact.

### Pricing hypothesis (unvalidated — label it as such)

| Tier | Who | Hypothesis |
|---|---|---|
| Free | Consumer app | Distribution and corpus discovery — the ingestion frontier |
| Pro | Newsrooms, fact-checkers | Per-seat, with batch verification and export |
| API | Platforms, brand safety, moderation | Metered per completed evidence workflow, not per raw request |

Figures are hypotheses until the MVP is instrumented (§16). Say "hypothesis" out loud.

### Beachhead customer

Start with digital newsrooms and moderation teams. They have a repeated verification workflow, measurable cost of delay, and a willingness to pay for evidence, auditability, and API integration.

### Initial product ladder

1. Free consumer verifier for distribution and corpus discovery.
2. Newsroom workspace with evidence review and export.
3. Verification API priced by completed evidence workflow, not by raw request count.
4. Trend and recurrence intelligence for enterprise customers.
5. Trust receipts and provenance workflows for publishers.

### Investor metrics to instrument from day one

- verification completion rate;
- citation coverage;
- repeat-content cache hit rate;
- cost per completed verification;
- time to first useful evidence;
- abstention rate;
- human correction rate;
- source/case recurrence rate;
- newsroom review time saved;
- false-positive rate on genuine content.

The most important early metric is not “number of models.” It is **percentage of decisive answers that a reviewer can independently audit.**

## 20. Judge questions and strong answers

### “Is this just an LLM wrapper?”

No. The model extracts candidate claims and phrases results. The verdict engine is deterministic, citations are stored as evidence objects, and a test proves that removing model advisory signals does not change verdicts.

### “Can you detect every deepfake?”

No—and claiming that would be irresponsible. Facify detects provenance, recycled media, false context, and cited claim contradictions reliably where evidence exists. Generic deepfake models are advisory because their performance can shift under new generators and platform transformations.

### “What happens when there is no evidence?”

Facify returns `UNVERIFIED`, explains what it checked, offers a user-triggered re-check, and can route the case to human review. Refusing to hallucinate certainty is a product feature.

### “Why will this become a company?”

Each check builds a reusable evidence graph. Repeated misinformation becomes cheaper and faster to verify, while the API turns the same engine into infrastructure for organizations that cannot manually review every post.

### “What is defensible?”

The compounding evidence graph, origin clustering, reviewer corrections, source profiles, multilingual normalization, and the trust/audit layer—not an easily copied model endpoint.

## 21. Technology decision register

| Decision | Use now | Reason |
|---|---|---|
| FastAPI | Yes | Fast typed API and ML-adjacent ecosystem |
| Supabase Postgres/pgvector | Yes | Free-tier database, auth/storage optional, fast iteration |
| Cloud Run | Yes | Container deployment and scale-to-zero; monitor egress/build charges |
| CI (tests only) | Yes | Scheduled jobs excluded: public-repo schedules auto-disable after 60 days of inactivity, and credentials do not belong in a public repository |
| Supabase Cron or Cloud Scheduler → Cloud Run Job | Yes | One authenticated live ingestion trigger; Cloud Scheduler path requires enabled GCP billing |
| Verdict cache + call governor | Yes, P0 | Free-tier model quota is the binding constraint (§11); cost controls need an owning component, not a bullet list |
| Corpus write-back | Yes, P0 | The compounding-evidence claim is the moat; without write-back it is unimplemented (§10) |
| Google Fact Check Tools API | Yes with timestamped live-response cache | Official ClaimReview and image-search surface |
| RSS/Atom/sitemaps | Yes | Transparent, controllable, reproducible ingestion |
| GDELT | Discovery/P1 | Useful breadth, not ground truth |
| Media Cloud | P1 | Good research/discovery layer; API/access constraints |
| Common Crawl | Roadmap batch source | Free but too large for live MVP retrieval |
| C2PA parser | Optional live provider | Validate real credentials when present; report unknown when platform reprocessing strips them |
| Generic web resolver | Yes, P0 | Reliable public-page retrieval with anchored evidence |
| X / YouTube metadata adapters | Best effort | Never decisive; screenshot or upload fallback when retrieval is blocked |
| SynthID/provider watermark APIs | Optional adapter | Ecosystem-specific and access/quota dependent |
| Generic deepfake classifier | Advisory/P1 | Evaluation and distribution-shift risk |
| Playwright/social scraping | Fallback only | Fragile, resource-heavy, policy-sensitive |
| Cloud Vision `WEB_DETECTION` | **Yes, P0, governed** | 1,000 free units/month (~33/day) under `call_budget`; the only path to media older than the live corpus (§6). Accepts raw bytes, so no upload is made public |
| Paid reverse-image services | Roadmap adapter | TinEye-class APIs have no free tier; the free Vision allowance covers demo scale |
| Error Level Analysis (ELA) | **No** | False-positives on screenshots, HDR, portrait mode and resampling — our exact input distribution; a persuasive-looking heatmap that is not diagnostic (§8D) |
| Noise-inconsistency / frequency panel | Advisory, displayed | Physical basis, CPU-cheap, gives the visible forensic surface ZAIML-005 expects without touching the verdict |
| WhatsApp Business API tipline | Roadmap, costed | BSP required, verification and template approval, per-message billing from Oct 2026 (§19) |
| Hosted multimodal LLM | Bounded extraction only | One call per document; model ID in config, never in code; availability and quotas measured in the team account on Day 0 |
| Local ONNX embeddings (text 384-d, image 512-d) | **Yes, P0** | Ingestion embeds 500–2,000 items/day — an embedding API would exhaust the free LLM quota before any user request (§7) |
| Temporal/queues/microservices | Roadmap | Not required to prove product value in 15 days |

## 22. Verified source register

The following primary sources were checked while revising this plan. Re-check quotas and pricing immediately before implementation because provider terms and model availability change.

- [C2PA Specifications](https://spec.c2pa.org/specifications/)
- [C2PA Explainer — provenance cannot alone establish factual truth](https://spec.c2pa.org/specifications/specifications/2.2/explainer/Explainer.html)
- [Google Fact Check Tools API](https://developers.google.com/fact-check/tools/api/reference/rpc/google.factchecking.factchecktools.v1alpha1)
- [Gemini URL Context](https://ai.google.dev/gemini-api/docs/url-context)
- [Gemini API pricing and grounding limits](https://ai.google.dev/gemini-api/docs/pricing)
- [Gemini API rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- [YouTube Data API quota and compliance](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits)
- [Internet Archive CDX server](https://github.com/internetarchive/wayback-cdx-server)
- [GDELT Cloud API reference](https://docs.gdeltcloud.com/api-reference/v2)
- [Media Cloud documentation and collection limits](https://www.mediacloud.org/documentation/faqs)
- [Common Crawl index and access](https://commoncrawl.org/get-started)
- [Cloud Run pricing/free allowance](https://cloud.google.com/run/pricing)
- [Cloud Scheduler → Cloud Run Jobs](https://docs.cloud.google.com/run/docs/execute/jobs-on-schedule)
- [Supabase Cron and pg_cron](https://supabase.com/docs/guides/cron)
- [Supabase pricing/free-plan limits](https://supabase.com/pricing)
- [GitHub Actions billing for public repositories](https://docs.github.com/en/actions/concepts/billing-and-usage)
- [NIST Open Media Forensics Challenge](https://www.nist.gov/itl/iad/mltg/open-media-forensics-challenge)
- [DeepfakeBench benchmark](https://arxiv.org/abs/2307.01426)

### Verified during this revision

| Finding | Effect on the plan | Source |
|---|---|---|
| URL-context tool: 20 URLs/request, 34 MB/URL; **YouTube, paywalled and login-required pages unsupported** | §5 model-side retrieval limits; video has no model-side route | [URL Context docs](https://ai.google.dev/gemini-api/docs/url-context) |
| Provider model quotas and pricing change by account/model | §11 call budget is configurable and measured in the team account before implementation | [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) — record the team-account snapshot |
| Public-repo scheduled workflows auto-disable after 60 days of inactivity | §6/§16 scheduling moved server-side | [GitHub Docs](https://docs.github.com/actions/managing-workflow-runs/disabling-and-enabling-a-workflow) |
| C2PA provenance may be incomplete or absent after later processing; it cannot establish factual truth | §8A is optional on real inputs; absence is reported as unknown | [C2PA Explainer](https://spec.c2pa.org/specifications/specifications/2.4/explainer/Explainer.html) |
| C2PA verifies that provenance claims are untampered, not that they are true | §3 hierarchy — already correct, now sourced | [C2PA Explainer 2.4](https://spec.c2pa.org/specifications/specifications/2.4/explainer/Explainer.html) |
| Fact Check Tools exposes `claims.search` and `claims.imageSearch`; image search requires a publicly accessible image URL and can fail when the host throttles it | Image search is optional and only used for already-public source images; local corpus matching remains primary | [claims.imageSearch](https://developers.google.com/fact-check/tools/api/reference/rest/v1alpha1/claims/imageSearch) |
| Supabase free: 500 MB DB, 1 GB storage, 50 MB max upload, 5 GB cached and 5 GB uncached egress | §10 sizing confirmed as stated | [Supabase pricing](https://supabase.com/pricing) |
| Cloud Vision: first **1,000 units/month free** across features incl. `WEB_DETECTION`, then $3.50/1k | §6/§8B reverse-image discovery is P0 under `call_budget` at ~33/day | [Cloud Vision pricing](https://cloud.google.com/vision/pricing) |
| `WEB_DETECTION` returns page URLs, titles and scores — **no publication dates** | Dating is a separate fetch of the matched pages (§8B), which also yields the anchored excerpt | [Detect web entities and pages](https://docs.cloud.google.com/vision/docs/detecting-web) |
| ELA false-positives on recolouring, HDR, portrait mode, resampling and screenshots; not a standalone finding | ELA excluded (§8D); noise-inconsistency used instead | [ELA limitations](https://forensicspot.com/topics/multimedia-forensics/error-level-analysis) |
| WhatsApp Business API requires a BSP, business/display-name approval and template pre-approval; per-message billing from 1 Oct 2026 | Tipline is costed roadmap, not a demo item (§19) | [WhatsApp API pricing](https://respond.io/blog/whatsapp-business-api-pricing) |
| Logically.ai entered administration July 2025 after losing Meta and TikTok contracts | §19 competitive note and the revenue-concentration answer | [Sifted](https://sifted.eu/articles/logically-ai-fact-check-misinformation-trump-tiktok-meta) |
| Cloud Scheduler charges by job, with three jobs free per billing account each month | §6 uses one job and requires a billing-account check; Supabase Cron remains the no-GCP fallback | [Cloud Scheduler pricing](https://cloud.google.com/scheduler/pricing) |

## Final definition of done

Facify is ready for judging when a person can share a real but miscaptioned image, a misleading or forged PDF with a verifiable cited contradiction, a public article link containing several mixed claims, a known fact-checked claim, a genuine article, and a novel claim—and the product produces fast, understandable, cited, multilingual, claim-level results with the correct willingness to abstain. At least one live feed item must enter the corpus through `ingest_tick` and later contribute to a user verification.

The winning claim is not:

> “We built the most accurate deepfake detector.”

It is:

> “We built an auditable evidence engine for the real misinformation workflow, and we can prove exactly what it knows, what it does not know, and how this becomes verification infrastructure for every newsroom and platform.”
