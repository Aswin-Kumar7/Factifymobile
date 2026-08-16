# Facify — Advanced URL Extraction + Zero-Cost Deployment Plan

Supersedes the resolver section of [Facify-platform-architecture.md](./Facify-platform-architecture.md)
and re-plans the infrastructure for **₹0/month actual spend** on Google Cloud free tier.

---

# Part 1 — Extracting content from URL-only shares

## The principle

Platforms wall their pages against browsers, but they **must** serve content to three consumers:
**link-preview bots** (WhatsApp/Telegram previews would break otherwise), **their own embed
surfaces** (embedded tweets/posts must render), and **search crawlers**. Those three doors are
public by design. The resolver walks through them in order of reliability, and every route emits the
same normalized object:

```
PostContent { platform, author, text, media[], published_at, canonical_url, extraction_route }
```

`extraction_route` is recorded in the evidence ledger — *how* we got the content is part of the
chain of custody.

---

## Per-platform strategy chains

### X / Twitter — the syndication CDN ⭐

The JSON that powers every embedded tweet on the web is publicly fetchable:

```
GET https://cdn.syndication.twimg.com/tweet-result?id=<tweet_id>&token=<computed>
→ full text · author · created_at · photo URLs · video variants (mp4) · quote-tweet chain
```

No auth, no API key, richer than oEmbed (which is the documented fallback:
`https://publish.twitter.com/oembed?url=...`). Media URLs feed straight into the bytes plane.

**Chain:** syndication JSON → oEmbed → headless render.

### YouTube — never download the video ⭐

Two techniques make yt-dlp and video downloads unnecessary:

1. **Gemini ingests YouTube URLs natively.** Pass the URL as `file_data` in a generateContent call —
   the model watches/transcribes the public video server-side. Free-tier API supports it. Claim
   extraction from a video becomes one API call with zero bandwidth.
2. **Thumbnail keyframes without the video:** `i.ytimg.com/vi/<id>/maxresdefault.jpg`, plus
   `0.jpg…3.jpg` (auto-generated scene frames). Those are your pHash inputs for recycled-video
   detection — four frames, a few hundred KB.

Metadata: `youtube.com/oembed` (no key) or Data API v3 (free 10k units/day).

**Chain:** oEmbed (title/channel) + thumbnails (visual pipeline) + Gemini URL ingestion (content).

### Instagram — three doors before giving up ⭐

1. **The embed surface:** `instagram.com/p/<shortcode>/embed/captioned/` — server-rendered HTML
   built for embedding; for public posts it typically returns the image and caption without login.
2. **The link-preview door:** fetch the post URL with a preview-bot User-Agent
   (`facebookexternalhit/1.1` or `WhatsApp/2.x`). Meta serves OG tags (`og:image`,
   `og:description`) to these UAs *by design* — it is exactly how WhatsApp renders link previews.
   You are using the mechanism the platform publishes for previews, on public content only.
3. **Gemini URL-context tool:** hand the URL to Gemini with the `url_context` tool enabled — the API
   retrieves the page from Google's infrastructure (which gets served far better than your Cloud
   Run egress IP) and you extract structured fields from what it read.
4. **Fallback, first-class UX:** "Instagram restricts automated access — screenshot the post and
   share that." OCR + vision take it from there. Most Indian users share screenshots anyway.

**Never:** authenticated scraping, login-wall bypass, private content. The enterprise tier does this
properly — Meta oEmbed via app review, per-tenant.

### Facebook

Same ladder as Instagram (preview-bot UA → Gemini URL context → screenshot), with lower expectations
— Facebook walls hardest. The screenshot path carries most Facebook traffic, and that's fine.

### Generic web / news links

1. `trafilatura` extraction — title, byline, publish date, body.
2. **JSON-LD first:** news sites embed `schema.org/NewsArticle` (headline, datePublished, author,
   image) — structured, no parsing heuristics.
3. **AMP variant check:** `<link rel="amphtml">` — AMP pages are static, light, and rarely walled;
   fetching the AMP version dodges most paywalls' JS.
4. Stated publish date vs **Wayback first snapshot** → the backdating check (Tier B evidence).

### The universal normalizer — server-side render + screenshot ⭐

A **Playwright service on Cloud Run** (mobile viewport, stealth context) for anything the structured
routes can't parse:

- Render the page → **full-page screenshot** → the screenshot enters the *visual* pipeline exactly
  like a user-shared image (OCR, pHash, reverse search).
- This inverts the failure mode: **if a page renders at all, Facify can verify it** — parsing
  failure no longer means verification failure.
- Also yields the rendered DOM for extraction when JS built the page.

```
URL → canonicalize (unwrap shorteners · strip utm/fbclid · resolve redirects)
    → platform router
        X:        syndication JSON → oEmbed ────────────┐
        YouTube:  oEmbed + thumbnails + Gemini native ──┤
        IG:       /embed/captioned → bot-UA OG →        │→ PostContent
                  Gemini url_context ───────────────────┤     ↓
        FB:       bot-UA OG → Gemini url_context ───────┤  bytes plane +
        Web:      JSON-LD → trafilatura → AMP ──────────┘  claim pipeline
    → [any failure] → Playwright render + screenshot → visual pipeline
    → [still nothing] → user screenshot prompt
```

---

# Part 2 — Restructured for Google Cloud free tier (₹0/month)

## The two services that silently cost money — and their free replacements

Cloud SQL and Memorystore have **no free tier**. They're out. That forces a leaner shape that's
actually better for a demo:

| Original plan | Free-tier replacement | Free allowance |
|---|---|---|
| Cloud SQL Postgres + pgvector | **Neon or Supabase free Postgres** (pgvector included) | 0.5 GB — thousands of cases + embeddings |
| Memorystore Redis/Valkey | **Upstash Redis free** — or just a Postgres `cache` table | 10k commands/day |
| Vertex AI (billed) Gemini | **Gemini API via AI Studio key** — free tier | ~1.5k req/day Flash-class, incl. vision, URL context, YouTube ingestion |
| Cloud Armor / CDN | Skip for demo — Cloud Run's HTTPS is enough | — |
| Brave Search ($5/1k, no free tier since late 2025) | **Google Programmable Search** | **100 queries/day free** |

## What stays, because it's already free

| Service | Free allowance | Role |
|---|---|---|
| **Cloud Run** | 180k vCPU-sec + 2M req/month | API, resolver, **and the Playwright renderer** |
| **GCS** | 5 GB (us region) | media staging, 24 h TTL |
| **Cloud Scheduler** | 3 jobs | knowledge-plane crons (fact-check RSS, news feeds) |
| **Pub/Sub** | 10 GB/month | async pipeline events |
| **Secret Manager** | 6 secrets | keys |
| **Cloud Vision Web Detection** | **1,000 units/month** | reverse image — the scarcest quota |
| Fact Check Tools API · Wayback CDX · X syndication/oEmbed · YouTube oEmbed · RSS/GDELT | Free, unlimited-ish | evidence sources |
| Firebase Auth | Free tier | consumer identity |

## Quota-as-budget: the planner gets real numbers

The budget-aware planner from the platform doc now has hard daily budgets — the free quotas:

| Wave | Provider | Daily budget | Planner rule |
|---|---|---|---|
| 0 | pHash/embedding cache, C2PA local decode | ∞ | always |
| 1 | Fact-check corpus, Wayback, X/YT adapters | ∞ (be polite) | always |
| 2 | **Vision Web Detection** | **~33/day** (1k/mo) | only if Waves 0–1 inconclusive AND image is novel (cache miss) |
| 2 | **Programmable Search** | **100/day** | only above suspicion threshold |
| 0–3 | **Gemini free tier** | ~1.5k req/day | extraction/OCR/phrasing; batch where possible |

Three design consequences:

1. **Cache-first stops being an optimization and becomes survival** — every Vision call must be
   earned. This is the same governor the paid SaaS needs; you're just tuning it at quota scale.
   *"We built the cost governor because our budget was zero"* is a genuinely good pitch line.
2. **Pre-warm the demo corpus:** run your demo media set (Gaza clip keyframes, test screenshots)
   through the pipeline days before, so demo-day requests hit cache and cost zero quota.
3. **Degradation is explicit:** quota exhausted → the verdict falls back to `UNVERIFIABLE` with
   "daily verification capacity reached" — honest, and it demonstrates the budget system live.

## Free-tier deployment map

```
┌─ Cloud Run (always-free) ───────────────────────────────┐
│  gateway+API (FastAPI) · resolver · Playwright renderer │
│  scale-to-zero · asia-south1 for demo latency*          │
└──────────────┬──────────────────────────────────────────┘
               │
   Neon/Supabase Postgres+pgvector (free)  ← cases, evidence, embeddings, cache table
   Upstash Redis (free)                    ← hot cache + rate limits (optional)
   GCS 5GB                                 ← media TTL bucket
   Cloud Scheduler ×3                      ← fact-check RSS · news corpus · source registry
   Gemini API (AI Studio key, free)        ← URL context · YouTube native · OCR · phrasing
   Vision (1k/mo) · PSE (100/day)          ← metered waves
   Fact Check API · Wayback · oEmbeds      ← free evidence
```

\* GCS always-free is US-region; Cloud Run free tier applies in most regions — check current terms.
For a hackathon demo, region hardly matters; for the SaaS, move to asia-south1 with billing.

**Held in reserve:** the $300/90-day trial credits. Don't budget them into the architecture — keep
them for demo-day burst headroom and for testing Vertex `imageverification@001` (SynthID decode),
which may need a billed project. If it does: cite it as the enterprise-tier technique, demo C2PA
decode (free, local `c2pa` library) instead.

## What this changes in the pitch — nothing

The architecture story is identical: waves, budgets, cache-as-moat, signed verdicts. Free tier just
sets the budget knobs to zero-cost values. When revenue exists, the knobs turn up — Neon → Cloud
SQL/AlloyDB, Upstash → Memorystore Valkey, PSE → Brave, quotas → contracts. **No re-architecture,
only re-configuration.** That is the definition of having built it right.

---

## Build order for the vertical slice

| # | Step | Free resources used |
|---|---|---|
| 1 | Monorepo + CI gates (Semgrep, Gitleaks, osv-scanner) | GitHub free |
| 2 | FastAPI on Cloud Run + Neon Postgres + schema | Cloud Run, Neon |
| 3 | Flutter share intake: bytes plane (pHash/EXIF on device) | — |
| 4 | **X syndication + YouTube adapters** (highest yield, zero cost) | free endpoints |
| 5 | Wave 0–1: cache, fact-check corpus ingest (Scheduler cron), Wayback | free |
| 6 | Instagram ladder: /embed/captioned → bot-UA OG → Gemini url_context | Gemini free |
| 7 | Playwright renderer service (universal fallback) | Cloud Run |
| 8 | Wave 2 with quota governor (Vision 33/day, PSE 100/day) | free quotas |
| 9 | Verdict card + evidence ledger UI + reply card | — |
| 10 | Pre-warm demo corpus · rehearse | — |

> Verify at build time: Gemini free-tier RPD limits (they shift), Vision free-unit terms, Neon/
> Supabase/Upstash current free plans, and whether `url_context` + YouTube ingestion are enabled on
> the free key. Record each in an ADR.

---

# Part 3 — Evidence Acquisition Service: getting the actual media bytes

> ## ⚠️ Reliability grading — read before scoping
> Everything below is a real technique; they are **not equally reliable**, and the weekend build
> must respect the grades:
>
> | Grade | Pieces | Treatment |
> |---|---|---|
> | **A — proven** | yt-dlp acquisition · ASR transcript · hashes | Build on these |
> | **B — solid with caveats** | Direct CDN URLs (fragile to platform changes) · audio fingerprint (**only matches a corpus you've seeded** — use landmark-style/audfprint for speech, not music-tuned chromaprint) | Build with fallbacks |
> | **C — research-grade, noisy in the wild** | Playwright network capture (Meta detects headless) · AV-sync · antispoof · frame forensics | Advisory-only by architecture; curated demo clips only; **never load-bearing, never on a metrics slide** |
>
> **Weekend cut:** yt-dlp + direct URLs for acquisition; transcript + seeded fingerprint for
> forensics; one curated AV-sync example as stretch. Network capture is enterprise-roadmap
> material — skip it.
>
> **The deletion test (why the product survives detector distrust):** remove every C-grade
> provider and the verdict engine is untouched — hashes, archive dates, citations and signatures
> carry it. Detectors can only escalate suspicion; they are architecturally barred from
> establishing anything.

Thumbnails, embeds and screenshots answer *"is this recycled?"* and *"what does it claim?"* — but
they cannot answer *"is this voice cloned?"* or *"is this face swapped?"* **Audio forensics needs
the audio track; frame forensics needs real frames, not re-rendered pixels.** That requires a
dedicated acquisition layer — the "bots" — built as a controlled service with a chain of custody,
not ad-hoc downloading.

## 3.1 The acquisition ladder (cheapest, cleanest first)

```
MediaRef (from resolver)
  │
  ├─ 1. DIRECT CDN URL — already exposed by the extraction routes
  │     X syndication → video_info.variants[] (progressive mp4)
  │     og:video / og:video:secure_url · JSON-LD contentUrl · <video src> in rendered DOM
  │     → plain HTTP GET. The same URL every viewer's player fetches.
  │
  ├─ 2. RENDERER NETWORK CAPTURE ⭐ — the advanced route
  │     The Playwright renderer already loads the page. Attach request interception,
  │     let the player start, and record what it fetches:
  │       · progressive mp4  → save stream
  │       · HLS (.m3u8)      → fetch manifest → download segments → ffmpeg remux -c copy
  │       · DASH (.mpd)      → same pattern
  │     `-c copy` remuxes WITHOUT re-encoding — the captured stream is bit-identical to
  │     what the platform serves, which is exactly what forensics needs.
  │     You are recording the bytes any viewer receives; no auth, no bypass.
  │
  ├─ 3. DEDICATED EXTRACTOR (yt-dlp) — policy-gated per platform
  │     Covers 1000+ sites, handles manifest/signature complexity. The tool journalists,
  │     archivists and fact-checkers actually use. ToS-gray on some platforms (YouTube
  │     prohibits downloading) → gated by a per-platform policy table, and for YouTube
  │     prefer Gemini native ingestion (content) + thumbnails (frames); invoke yt-dlp only
  │     when audio forensics is genuinely required and policy allows.
  │
  └─ 4. USER-SIDE CAPTURE — screen recording shared by the user
        Arrives as bytes through the normal share intake. Weakest forensically
        (re-encoded twice) but always available; flagged as such in the ledger.
```

**Hard lines:** public content only · never authenticated sessions · **never DRM** (no exception) ·
analyze, don't republish · raw media TTL 24 h, only hashes + derived features persist.

## 3.2 Chain of custody — what makes it evidence

Every acquisition produces:

```
MediaAsset {
  sha256,                  # of the exact acquired bytes, computed at acquisition
  phash[], audio_fp,       # perceptual + acoustic fingerprints
  acquisition_route,       # cdn_direct | network_capture | extractor | user_capture
  source_url, fetched_at,  # where and when
  probe: {codec, container, duration, resolution}   # ffprobe snapshot
}
```

The signed attestation references the `sha256` and `acquisition_route` — a verdict states not just
*what* was analyzed but *how the evidence was obtained and that it hasn't changed since*. That is
the difference between "we downloaded a video" and an evidence pipeline a newsroom can defend.

## 3.3 Forensic providers that run on acquired media

| Provider | Technique | Catches | Evidence tier |
|---|---|---|---|
| **audio_fingerprint** ⭐ | Chromaprint-class acoustic match vs ingested corpus (speeches, old broadcasts) | **Recycled audio** — old speech under a new caption | **Tier B — citable**: match to a dated source is temporal evidence, not a model opinion |
| **av_sync** ⭐ | SyncNet-class lip-audio consistency | **Real video + substituted audio** — the dominant Indian pattern (politician's face, fake voiceover) | Advisory → can escalate to `DISPUTED` |
| **audio_antispoof** | AASIST / wav2vec2-AASIST (ASVspoof-baseline class, CPU-sized) | Vocoder artifacts of cloned/synthetic voices | Advisory → escalate only |
| **frame_forensics** | Face-crop detector on scene-sampled frames + temporal consistency | Face-swap / reenactment artifacts | Advisory → escalate only |
| **transcript** | ASR (Gemini free tier; faster-whisper local as fallback) | Feeds the claim pipeline — what the audio *says* gets fact-checked | → Tiers C/D via claims |

Note the two ⭐ rows: **the highest-value media forensics here aren't deepfake classifiers at all.**
Fingerprint-matching recycled audio gives you a *citable, dated* source; sync analysis catches the
cheap fake that actually circulates (dubbed audio over real footage). Both are far more robust than
GAN detection — and both only exist because the acquisition layer exists.

## 3.4 The honest physics — and the answer to "how is authenticity proven"

Two things must be said plainly, on a slide and in Q&A:

1. **Platforms re-encode everything on upload.** Container metadata, encoder traces and much
   codec-level signal are destroyed before you ever see the file — for *every* video, real or fake.
   This is why history + provenance lead the architecture and pixel/waveform forensics stay
   advisory: the strongest signals survive re-encoding (perceptual hashes, acoustic fingerprints,
   sync geometry); the fragile ones don't.

2. **Extraction lets you catch fakes. It cannot prove something real.** The verdict asymmetry is
   architectural, and it answers the question directly:

   | Question | Provable? | By |
   |---|---|---|
   | "Is this content recycled/misattributed?" | ✅ Yes | Fingerprint/hash match to a dated source — citation |
   | "Is this AI-generated (major generators)?" | ✅ Yes | C2PA / SynthID / OpenAI Verify — cryptographic |
   | "Is this audio cloned / face swapped?" | ⚠️ **Suspicion only** | Detectors — advisory, can escalate to `DISPUTED`, never establish `VERIFIED` |
   | "Is this authentic?" | Only via provenance + corroboration | Signed capture credentials + independent sources |

   "No fake detected" is **not** evidence of authenticity — a detector that has never seen the
   generator returns exactly the same silence. The system never converts that silence into a
   `VERIFIED`.

## 3.5 Free-tier compute reality

Media work is the vCPU hog; the free 180k vCPU-seconds (~50 vCPU-hours/month) forces caps that are
good practice anyway:

- **Analyze the first 90 s, at ≤480p, mono 16 kHz audio** — forensic signals don't need more
- Scene-sampled frames capped at ~24 per asset; face crops only where faces exist
- Acquisition + forensics run as a **background job**: the user gets the Wave 0–1 verdict in
  seconds, and the card **updates asynchronously** — "deep media analysis running…" → forensic
  addendum lands a minute later. Progressive verdicts are better UX *and* better economics.
- Fingerprint/hashes cached forever — a re-shared clip never re-acquires

Demo-scale (a few hundred short clips/month) fits. At SaaS scale this becomes a GPU worker pool —
again re-configuration, not re-architecture.

## 3.6 The policy table (per-platform, config not code)

| Platform | Route allowed | Note |
|---|---|---|
| X | cdn_direct (syndication variants) | Clean — public CDN URLs |
| Instagram/FB | network_capture on public posts | Preview-mechanism bytes; screenshot fallback |
| YouTube | **Gemini native + thumbnails only** by default | ToS prohibits download; extractor only under research/enterprise flag |
| News sites / generic | cdn_direct → network_capture | Respect robots for bulk crawl |
| Any DRM | ❌ never | Hard legal line |

Enterprise tier replaces gray routes with official APIs and per-tenant platform agreements — the
policy table is where "hackathon pragmatism" and "enterprise due diligence" are kept separate,
visibly.

---

# Part 4 — The long-tail web: unknown sites, hoax portals, everything else

For X/Instagram/YouTube, the platform is trusted transport and the *content* is the question. For an
unknown domain — a "news portal" registered last month, a WordPress hoax farm, a typosquat of a real
outlet — **the site itself is a first-class subject of verification.** Two parallel tracks per URL:

```
unknown URL ──┬── CONTENT track:  what does the page claim?   → claim pipeline
              └── SITE track:     what IS this site?          → source forensics (Tier D)
```

## 4.1 Content extraction ladder (generic sites)

1. **Static fetch → structured data first.** Parse in priority order: **JSON-LD**
   (`schema.org/NewsArticle`, `Article`, `VideoObject` — and `ClaimReview`, which some sites embed),
   then OpenGraph/Twitter Cards, then `<time>` elements and byline patterns. Legit news CMSes emit
   JSON-LD automatically; hoax sites rarely bother — **the absence is itself a weak signal.**
2. **`trafilatura`** for main-content extraction (current SOTA open extractor — title, author, date,
   body, boilerplate stripped). Language-detect → route Indic content correctly.
3. **AMP variant** (`<link rel="amphtml">`) when the main page is JS-walled — publisher-published,
   static, light. (Reading the AMP page a publisher ships is fine; **bypassing metered paywalls is
   not** — hard line.)
4. **Playwright render** when static returns a JS shell (detect: low text-to-HTML ratio, empty
   article node) → rendered DOM + **screenshot into the visual pipeline** (universal normalizer,
   as in Part 1).

## 4.2 Site forensics — the layer that catches hoax networks ⭐

All deterministic, all citable, almost all free:

| Signal | Technique | What it catches |
|---|---|---|
| **Domain age** | RDAP (free) | "News site" registered 3 weeks ago covering a 10-year beat |
| **Typosquatting** | Levenshtein + homoglyph distance vs credible-domain list | `thehindu.co.in` vs `thehindu.com` |
| **Archive footprint** | Wayback CDX on the *domain* | Site claims "since 2005", first snapshot 2024 — citable contradiction |
| **Infrastructure clustering** ⭐⭐ | Shared Google Analytics/AdSense IDs in page source · shared TLS cert SANs via **crt.sh** (free) · **favicon hash** matching · same IP/ASN | *"This site shares an AdSense ID with 14 known hoax domains"* — hoax farms reuse infrastructure; one operator, forty mastheads. Deterministic, devastating, citable |
| **Cloaking diff** ⭐ | Fetch the same URL as crawler-UA and as mobile-browser-UA; SimHash the two bodies; large diff = different content for bots vs humans | Scam/hoax sites cloak. **Cloaking is itself evidence of deception**, and it costs two fetches |
| **Credibility structure** | Contact page, about page, real author pages, editorial policy, `ads.txt`, DMARC/SPF | The heuristic feature-set NewsGuard-style analysts check by hand — computed |

Every profiled domain is cached as a **site profile**. This compounds: user-triggered checks
crowdsource the crawl frontier, and the result is a proprietary, continuously-updated **Indian
hoax-site graph** — analyst-built databases of this kind are maintained manually; Facify builds it
computationally as a side effect of usage. That's moat, not plumbing.

## 4.3 Content provenance for long-tail pages

- **Near-duplicate text detection** ⭐ — MinHash/SimHash shingles vs the news corpus:
  *"this 'exclusive' is a 2019 article, verbatim, with names and dates changed"* — a classic hoax
  pattern, and the diff itself is the evidence card.
- **Backdating triple-check:** stated publish date vs Wayback first snapshot vs sitemap
  `lastmod`/HTTP `Last-Modified`. Disagreement = citable.
- **Hero image** → temporal chain (Vision, budget-gated) — recycled imagery on a fresh article.
- **Snapshot on sight:** trigger Wayback Save-Page-Now on first check, so the evidence URL is
  archived *before* the page can change or vanish. (Google's public page cache is retired —
  Wayback and archive.today are the remaining time machines; preserve proactively.)

### Dating hierarchy v2 — Google is the detective, Wayback is the notary

Roles, not rivals. Google has **no first-indexed-date API** (cache retired 2024), and a page's own
timestamp is editable by the adversary — so discovery and dating are split:

| Step | Tool | Cost | Role |
|---|---|---|---|
| Discover | Vision Web Detection (images) · PSE + news corpus (text) | quota | *Where else does this exist?* |
| **Date — primary** | **Matched pages' own publish dates** (JSON-LD/trafilatura at fetch) | free, ms | The common case |
| Date — older instances | Date-restricted PSE (`before:` / `dateRestrict`) | quota | Targeted |
| **Date — confirm** | **Wayback CDX, only when the verdict hinges on the date** — confirms stated dates and catches backdating (stated ≠ snapshot is itself citable) | free, slow | The only third-party tamper-proof timestamp |
| Preserve | Save-Page-Now + archive.today fallback | free, async | Citations must not rot under a signed attestation |

Wayback is deliberately **not** in the per-match fan-out anymore — it runs selectively. Its
irreplaceable jobs are the backdating check and evidence permanence; everything else moved to
faster, free page-level dates. Known caveats: Archive outages happen and Indian regional coverage
is thin — archive.today is the fallback notary, and page-level dates carry the load.

## 4.4 Politeness and legality

- **User-triggered resolution ≠ crawling.** One fetch of a URL a user shared is the same fetch any
  preview bot makes. Bulk corpus ingestion is crawling: honest bot UA (`FacifyBot/1.0 +url`),
  robots.txt respected, per-domain rate limits and backoff.
- No paywall circumvention, no auth walls, DRM never. Cache aggressively so a viral URL is fetched
  once, not ten thousand times.

## 4.5 Free-tier fit

RDAP, crt.sh, Wayback (read *and* save), favicon/SimHash/MinHash computation, trafilatura — all free
or compute-only. The only metered touches remain Vision (hero image) and PSE (corroboration),
already governed by the Wave-2 quota budget. **The entire site-forensics layer costs ₹0.**

---

# Part 5 — Verifying the content itself: article text → verdict

The site track says *who is talking*. This part is *whether what they say is true*. Pipeline, then a
worked example, then the honest scope.

## 5.1 The claim pipeline

```
article text
  1 ─ CLAIM DECOMPOSITION      Gemini extracts the 3–7 check-worthy factual assertions
  │                            (who/what/when/where/numbers) — not every sentence, only
  │                            claims that are verifiable and consequential
  2 ─ CANONICALIZATION         entity resolution ("PM", "Modi ji" → same entity),
  │                            date/place anchoring, normalize across 10 languages
  3 ─ KNOWN-CLAIM MATCH        embedding search (pgvector) over the ClaimReview corpus
  │                            + Fact Check Tools API      → Tier C citation if ruled
  4 ─ CORROBORATION            internal news corpus (free, minutes-fresh) → PSE long tail
  │                            → significance-weighted presence/absence      → Tier D
  5 ─ ATTRIBUTION CHECK ⭐      "according to Reuters/NASA/RBI…" → site-restricted
  │                            search on the cited source → did they actually say it?
  6 ─ QUOTE CHECK ⭐            exact/fuzzy phrase search for quotes → who else carries
  │                            this quote, and since when?
  7 ─ PER-CLAIM VERDICTS       each claim gets its own verdict + citations;
                               article rolls up: claims × site track × provenance track
```

Steps 1–2 are the only LLM steps — **reading, not judging**, as everywhere else. Steps 3–6 produce
citations or nothing.

## 5.2 The two deterministic killers ⭐

**Fabricated attribution.** Fake articles borrow authority: *"as reported by BBC," "according to a
NASA study," "RBI circular states."* The check is one site-restricted query
(`site:bbc.com <claim keywords>`) against the cited source. **Cited source doesn't carry it →
citable negative evidence.** Costs one PSE query, quota-gated, and it dismantles a large fraction
of fabricated news on its own.

**Fabricated quotes.** *"Ambedkar said…" / "APJ Kalam said…"* — a signature Indian pattern. Exact-
phrase search across the corpus: famous fake quotes are almost always already fact-checked
(→ Tier C hit); novel ones that appear *only* on low-credibility sites inherit that as evidence.

## 5.3 Significance-weighted silence — using absence correctly

A claim that would be front-page news if true — a minister resigning, a new welfare scheme, a
vaccine death wave — **cannot be exclusively reported by an unknown WordPress site.** So:

1. Gemini estimates coverage-expectation: *"if true, how widely would this be reported?"* (high /
   medium / local)
2. **High-expectation claim + zero hits in the 150-outlet corpus → strong negative evidence.**
3. **Local/minor claim + zero hits → means nothing.** A village-level story won't be in national
   feeds; silence is only evidence when coverage was expected.

This asymmetry keeps the "no one else reports it" heuristic honest — it's powerful against
fabricated national news and correctly mute on genuine local reporting.

## 5.4 Worked example

Unknown site posts: *"Govt announces ₹5,000 monthly allowance for all farmers — applications close
tomorrow. Forward to every farmer!"*

| Step | Finding | Tier |
|---|---|---|
| Decompose | Claim 1: govt announced ₹5,000/mo farmer scheme · Claim 2: deadline tomorrow | — |
| Known-claim match | PIB Fact Check has debunked near-identical scheme hoaxes; embedding match ≥ threshold | **C** |
| Corroboration | Coverage-expectation HIGH; **0 of 150 corpus outlets** carry it | **D (negative)** |
| Attribution | No named source at all — flagged | display |
| Site track (Part 4) | Domain registered 6 weeks ago; AdSense ID shared with 3 known hoax domains | **D** |
| Manipulation markers | "closes tomorrow", "forward to every farmer" — urgency + share pressure | display-only |

**Verdict: `DISPUTED`** — with a PIB citation, a corroboration count, and a domain profile. The
urgency markers are shown as named techniques (teaching mode) but never scored.

## 5.5 The honest scope — what machines can and cannot check

| Claim type | Can Facify verify? | How |
|---|---|---|
| Already fact-checked (even paraphrased/translated) | ✅ Strong | Embedding match → citation |
| Fabricated national-scale news | ✅ Strong | Significance-weighted silence + site track |
| Fabricated attribution / famous fake quotes | ✅ Strong | Deterministic search |
| Recycled story with names/dates swapped | ✅ Strong | MinHash near-dup (Part 4) |
| **Genuinely novel local claim** ("bridge collapsed in X village an hour ago") | ❌ **Honestly no** | `UNVERIFIABLE` + route to the submit-to-fact-checker flow — a human lead, not a machine guess |

Automated verification of novel real-world events is unsolved — for everyone. The system's
credibility rests on refusing to fake it: the last row returns `UNVERIFIABLE`, states why, and
turns the claim into a lead for Alt News/BOOM. **The failure mode is designed, not hidden.**

## 5.6 Two correctness rules that make cross-site checking real

**Rule 1 — Count independent origins, not websites.** Twenty Indian outlets carrying the same story
are often **one PTI/ANI wire copy reprinted twenty times** — that is one source wearing twenty
mastheads, not twenty confirmations. Corroboration must cluster near-duplicate articles (MinHash —
the same machinery as the recycled-story check) and count **distinct originating sources**:
independent reporting uses different words, different details, different bylines. A claim carried
by 3 genuinely independent origins outweighs one carried by 20 syndicated reprints. Without this
rule, corroboration counts are theater.

**Rule 2 — Respect the breaking-news window.** For the first ~1–2 hours of a *real* event, credible
coverage may not exist yet — silence is ambiguous early. So verdicts are **time-aware**:

- Claim's asserted event time is recent + coverage-expectation high + corpus silent →
  **`UNVERIFIABLE (developing)`** — *"too recent to corroborate; we'll re-check"* — never
  `DISPUTED` on silence alone inside the window.
- A scheduled re-check (Cloud Tasks, free) re-runs corroboration at +1 h and +6 h and **updates the
  cached verdict** — everyone who checks the same content later gets the matured answer.
- Silence only converts to negative evidence once the window has passed and coverage was expected.

These two rules encode how human fact-checkers actually reason about corroboration; skipping them
is how naive "check other sites" systems embarrass themselves on day one.
