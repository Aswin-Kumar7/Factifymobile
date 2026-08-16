# Facify — Master Execution Plan

**Stack locked:** Flutter 3.x · Android-only (ADR-0001) · FastAPI/Python 3.12 · Neon Postgres +
pgvector · Cloud Run free tier · Gemini AI Studio free key · ₹0/month at demo scale.

---

## The problem statement we are answering

### ZAIML-005 — Fake News & Deepfake Detection Platform

**Background.** The rapid growth of generative AI and social media has increased the spread of
misinformation, manipulated media, and deepfake content, creating societal and security challenges.

**Problem statement.** Build an AI-powered platform that detects fake news, manipulated content,
synthetic media, and deepfake videos to help users verify information authenticity.

**Impact**
- Reduce misinformation spread.
- Improve public trust in digital information.
- Strengthen media literacy.
- Support information integrity.

**Key deliverables**
- Detect AI-generated and manipulated media.
- Analyze news credibility and source reliability.
- Provide explainable authenticity scores.
- Identify misinformation patterns.
- Generate fact-checking recommendations.

### How Facify answers each deliverable

| Deliverable | Facify's answer | Tasks | Phase |
|---|---|---|---|
| Detect AI-generated media | C2PA manifest decode · SynthID/Vertex · OpenAI Verify — **Tier A cryptographic**, not classifier guesswork | 1.5.3 | 1 |
| Detect manipulated media | pHash recycling · EXIF anomalies · temporal chain (oldest-instance dating) · MinHash near-dup · backdating triple-check | 1.5.1, 1.5.2, 2.4, 2.5 | 1–2 |
| Detect deepfake videos | Keyframe→dated-source matching (**Tier B, citable**) as the primary path; neural detector shipped **quarantined as Tier E advisory**; audio fingerprint + AV-sync later | 1.5.4, 1.8.5, 4.2, 4.5 | 1, 4 |
| Analyze news credibility | Claim pipeline: decomposition → known-claim match → corroboration with independent-origin dedup → significance-weighted silence | 1.4 | 1 |
| Source reliability | MBFC-seeded credibility registry · RDAP domain age · typosquat · infra clustering · cloaking diff · archive footprint | 1.3.3, 1.3.5, 2.3 | 1–2 |
| **Explainable authenticity scores** | **Evidence-strength summary computed in Python** from tier composition, independent-origin count and source credibility — never model-supplied. Every component tappable to its citation. See the note below. | 1.2.3, 1.7.7 | 1 |
| Identify misinformation patterns | Recurrence timeline ("seen N times, first on X") · caption-variant view · hoax-site graph via infra clustering · claim-cluster velocity alerts | 2.3, 2.4, 2.6, 5.3 | 2, 5 |
| Fact-checking recommendations | Teaching-mode line naming the manipulation technique · human review queue · prefilled submit-to-fact-checker flow with the evidence ledger attached | 1.7.4, 1.9.4, 3.4 | 1, 3 |

### On "explainable authenticity scores" — the deliberate reading

The deliverable asks for a score that is explainable. A softmax output from a detector is a **number
without an explanation**; appending a saliency map does not make it evidence. Facify therefore ships
a **scored explanation** rather than an explained score:

> The score is computed in Python from the evidence ledger — tier composition, count of
> **independent** corroborating origins, and source credibility. No model output is an input.
> Every term in the score links to the citation that produced it, and the Tier E advisory strip is
> displayed **greyed and labelled "not used in verdict."**

This is strictly more explainable than a model confidence, and it is the only form of score
compatible with the design law below. Five prior open-source builds (see Appendix A) independently
demonstrate why the model-supplied alternative fails.

---

## How to use this plan (agents & humans)

- **One phase at a time.** A phase does not begin until the previous phase's **Done-when** gate
  passes. Within a phase, tasks are ordered by dependency; tasks marked ∥ can run in parallel.
- **Every task is agent-sized:** one sitting, one reviewable diff, conventional commit
  (`feat:`, `fix:`, `chore:`, `docs:`), tests where the task says so.
- **Architectural choices get an ADR** in `docs/adr/` — one page, decision + consequences.
- **The design law is enforced in code review:** no model output may flow into
  `verdict_engine`. Tier E signals live in `advisory[]`, never in `evidence[]`.
- Secrets only in `.env` (gitignored) locally / Secret Manager in cloud. CI runs gitleaks.

## The evidence-tier contract (referenced by every phase)

| Tier | Class | Examples | May decide verdict? |
|---|---|---|---|
| A | Cryptographic | C2PA manifest, SynthID decode, OpenAI Verify | ✅ |
| B | Temporal | page publish dates, Wayback snapshot, fingerprint match to dated source | ✅ |
| C | Adjudicated | ClaimReview fact-check with rating + URL | ✅ |
| D | Corroboration / source intel | independent-origin counts, domain age, typosquat, infra clusters | ✅ |
| E | Model scores | synthetic detectors, antispoof, sync | ❌ advisory only — may escalate to DISPUTED, never VERIFIED, never alone |

Verdicts: `VERIFIED` · `DISPUTED` · `UNVERIFIABLE` (+ `UNVERIFIABLE (developing)` inside the
breaking-news window).

---

# PHASE 1 — Core spine (hackathon MVP)

**Goal:** a judge shares a WhatsApp forward → cited verdict in their language in <6 s, twice in a
row, on venue wifi. Everything else exists to make that moment happen.

### Features delivered
1. Android share-target app (text / image / URL intake) + clipboard fallback
2. On-device pre-processing: dHash/pHash, EXIF read, local C2PA check
3. Hash-first API: verdict from cache without media upload (privacy + speed)
4. Resolvers: X (syndication → oEmbed), YouTube (oEmbed + thumbnails + Gemini-native), generic
   web (JSON-LD → trafilatura → AMP)
5. Knowledge plane v0: ClaimReview ingest + ~150-outlet RSS corpus, 15–30 min fresh
6. Claim pipeline v0: decomposition (Gemini) → embedding match vs fact-check corpus →
   corroboration with **independent-origin dedup** (MinHash) + **significance-weighted silence** +
   **breaking-news window**
7. Dating v2: matched-page publish dates (primary) · date-restricted PSE · selective Wayback
   confirm · Save-Page-Now on cited URLs
8. Wave-2 quota governor: Vision Web Detection ≤33/day, PSE ≤100/day, hard-capped
9. Deterministic verdict engine (Tiers A–D) + evidence cards with tappable citations
10. Multilingual output (10 languages, romanized-Indic detection) — Gemini phrases, never decides
11. Reply-card image share-out (correction returns to the group)
12. OCR path for screenshots/text-on-image (the dominant Indian format)
13. **Evidence-strength summary** — the explainable authenticity score, computed in Python from the
    ledger, with the Tier E advisory strip shown greyed and labelled excluded
14. **Quarantined deepfake video detector** (Tier E advisory) — demonstrates the deletion test live
15. **Hostile-input hardening** (SSRF guard, prompt-injection sanitization, rate limits) and an
    **evaluation harness** — the two things every prior build in this space skipped

### Tasks

**1.1 Backend spine**
- [x] 1.1.1 Scaffold `services/api`: FastAPI + Pydantic v2, `/healthz`, Dockerfile, deploy to
      Cloud Run (free tier). *Test: deployed URL returns 200.*
- [ ] 1.1.2 Provision Neon Postgres + pgvector; migrations (alembic): `case`, `content_object`,
      `evidence`, `verdict_ledger`, `media_fingerprint(phash, times_seen, first_verified_at)`,
      `claim(embedding vector)`, `source_credibility`, `api_budget(provider, day, used)`.
- [x] 1.1.3 `POST /v1/verify` two-phase contract: accepts `{phash, exif?, c2pa?, lang}` → cache
      hit returns ledger; miss returns `202 need_media` → `POST /v1/verify/full`.
      *Test: golden-file JSON contract tests.*
- [x] 1.1.4 Quota governor middleware: per-provider daily counters in `api_budget`; exceeding →
      provider skipped + ledger notes "capacity reached". *Test: unit.*
- [ ] 1.1.5 **SSRF guard on the resolver** — the API fetches attacker-chosen URLs from Cloud Run.
      Allowlist schemes (http/https only), resolve DNS then block private/loopback/link-local/
      metadata ranges (incl. `169.254.169.254`), re-check after **every** redirect, cap depth at 5,
      hard timeout, cap response size. *Test: fixture URLs for each blocked range + a redirect that
      pivots to internal on hop 2.*
- [ ] 1.1.6 **Prompt-injection sanitization** — fetched page text and OCR output are adversary-
      controlled and flow into Gemini (1.4.2). Strip/neutralize instruction-shaped content, fence
      untrusted text in the prompt, and **detect injection markers**. A page attempting to instruct
      the verifier is itself deception → record as **Tier D evidence** (same logic as cloaking
      diff), never silently dropped. *Test: 8 injection fixtures incl. hidden-text and
      unicode-obfuscated variants.*
- [ ] 1.1.7 Rate limiting (per device/day) + three-layer TTL cache (resolved URL text, verdict,
      provider results) incl. **negative caching** of `UNVERIFIABLE`.

**1.2 Verdict engine** (pure Python module, no I/O)
- [x] 1.2.1 `verdict_engine.decide(evidence[]) -> Verdict` — ~20 lines implementing the tier
      contract incl. developing-window rule. *Test: table-driven cases for every rule branch —
      this module gets the most tests in the repo.*
- [x] 1.2.2 Evidence ledger serializer: every item carries `tier, type, finding, citation_url,
      observed_at, weight`; advisory list separate. Snapshot citation text at collection time.
- [ ] 1.2.3 **`evidence_strength(ledger) -> Strength`** — the explainable authenticity score, pure
      Python, **no model input**. Emits `{score, band, components[]}` where components are
      `tier_composition` (count+weight per tier A–D), `independent_origins` (post-MinHash distinct
      count, not article count), `source_credibility` (registry-backed), and `temporal_confidence`.
      Every component carries the `citation_url`s that produced it. `advisory[]` is reported
      **alongside and explicitly excluded** from the arithmetic. *Test: table-driven — the score is
      deterministic, so snapshot it; incl. a case proving Tier E changes the number by zero.*

**1.3 Knowledge plane v0** (`services/knowledge`)
- [ ] 1.3.1 ClaimReview ingester: Fact Check Tools API + RSS of Alt News/BOOM/Factly/Vishvas/PIB →
      normalize → embed (Gemini embeddings) → pgvector. Cloud Scheduler every 15 min.
- [ ] 1.3.2 News corpus ingester: ~150 credible Indian outlets (seed list = FactifyAI source DB),
      RSS/sitemaps → store title/lead/URL/date + embedding + MinHash shingles.
- [ ] 1.3.3 Source registry loader: credibility DB port + IFCN list + RDAP age cache.
- [ ] 1.3.4 **Move knowledge-plane crons to GitHub Actions.** Cloud Scheduler free tier is **3 jobs
      total** and 1.3.1–1.3.3 already consume all three. GH Actions `schedule:` is free and
      unmetered for public repos → ingesters can run at independent cadences and the cap
      disappears. Cloud Scheduler stays reserved for latency-sensitive jobs. *ADR required.*
- [ ] 1.3.5 Seed `source_credibility` from the **MBFC-derived corpus (~859 scored domains)** in
      addition to the FactifyAI port; record provenance + license per row.
- [ ] 1.3.6 Extra corpus ingesters (unblocked by 1.3.4): **Reddit** (r/india + topic subs — claims
      surface here before news covers them), **YouTube transcripts**, **RSSHub** for X accounts,
      GDELT. Same normalize→embed→MinHash path as 1.3.2.

**1.4 Claim pipeline v0**
- [x] 1.4.1 Language detect (Unicode ranges + romanized-Indic heuristic → Gemini fallback).
- [ ] 1.4.2 Claim decomposition prompt (Gemini, structured JSON out, ≤7 claims) + coverage-
      expectation estimate (high/medium/local). *Test: golden prompts on 10 fixture messages.*
- [ ] 1.4.3 Known-claim match: embed → pgvector cosine ≥ threshold → Tier C evidence.
- [x] 1.4.4 Corroboration: corpus search → MinHash cluster → **count distinct origins** → Tier D
      (positive or significance-weighted negative, honoring the developing window).
- [ ] 1.4.5 Attribution check: cited-source extraction → site-restricted PSE query → Tier D.

**1.5 Media path**
- [ ] 1.5.1 Image intake: server pHash verify, OCR (Vision text detection) → extracted text joins
      claim pipeline; EXIF anomalies → forensic notes.
- [ ] 1.5.2 Temporal chain: Vision Web Detection (quota-gated) → fetch matched pages → publish
      dates (JSON-LD/trafilatura) → oldest vs asserted date → Tier B; selective Wayback confirm;
      Save-Page-Now async on cited URLs.
- [ ] 1.5.3 C2PA server-side verification (`c2pa` lib) → Tier A. (Vertex SynthID decode: attempt
      on trial credits; if billing-gated, C2PA-only for demo + roadmap note.)
- [ ] 1.5.4 **Video path v0 + quarantined Tier E detector.** (a) Keyframe extraction (scene-change,
      ≤12) → pHash → corpus/temporal match → **Tier B citation** — this is the load-bearing video
      answer. (b) Ship a **pretrained** ResNext+LSTM frame detector (no training, no GPU, CPU
      inference on ≤24 frames) wired **only** into `advisory[]`. It is architecturally incapable of
      reaching `verdict_engine`. *Test: a case asserting that toggling the detector off leaves the
      verdict byte-identical — **the deletion test, executable in CI**.*
- [ ] 1.5.5 PDF intake (PyMuPDF) → text → claim pipeline. Forged "government circulars" and fake
      job/scheme notices circulate as PDFs on WhatsApp; cheap to support, high Indian relevance.

**1.6 Resolvers**
- [x] 1.6.1 URL canonicalizer: shortener unwrap, tracking-param strip, redirect follow (httpx).
- [x] 1.6.2 X adapter: syndication JSON → text/author/media; oEmbed fallback. *Test: 3 fixture
      tweets incl. one video.*
- [x] 1.6.3 YouTube adapter: oEmbed + `i.ytimg` thumbnails → pHash; Gemini-native URL ingestion
      for transcript/claims.
- [x] 1.6.4 Generic web adapter: JSON-LD → trafilatura → AMP variant; emits article + hero image.

**1.7 Flutter app** (`apps/mobile`) ∥ with 1.3–1.6 once 1.1 contract is fixed
- [ ] 1.7.1 Scaffold: Flutter 3.x, Riverpod, dio, drift; CI analyze+test green.
- [ ] 1.7.2 Share intake: `receive_sharing_intent` (text/image/video), clipboard-on-open prompt.
- [ ] 1.7.3 On-device pre-process: dHash (9×8 grayscale), EXIF strip-read; local drift cache
      phash→verdict.
- [ ] 1.7.4 Verify flow UI: progress → verdict card (3 states) → evidence cards (tap = open
      citation) → advisory strip (greyed) → teaching-mode line.
- [ ] 1.7.5 Reply card: rendered verdict image via `screenshot` + `share_plus`.
- [ ] 1.7.6 Language: device locale → `lang` param; RTL-safe layouts.
- [ ] 1.7.7 **Authenticity-strength panel** rendering 1.2.3: the score with its component breakdown
      (tier composition · independent origins · source credibility · temporal confidence), each row
      tappable through to its citations. Below it, the **advisory strip greyed out with an explicit
      "not used in this verdict" label** — the refusal must be visible, not implied.

**1.8 Demo hardening**
- [ ] 1.8.1 Pre-warm corpus: run demo set (recycled-video keyframes, fake-scheme article,
      typosquat URL, genuine article) end-to-end; verify cache hits.
- [ ] 1.8.2 Kill-switch rehearsal: Gemini key revoked → verdict unchanged, template phrasing.
- [ ] 1.8.3 Offline insurance: local cache serves pre-warmed verdicts with wifi off.
- [ ] 1.8.4 60-second backup screen recording.
- [ ] 1.8.5 **Video demo case** in the pre-warm set: a recycled video (new caption, old footage) →
      keyframe pHash → dated source → **Tier B citation**, with the Tier E detector visible and
      greyed beside it. This is the shot that answers "does it do deepfakes" on stage.

**1.9 Evaluation & trust** — *the two gaps every prior build in this space left open (Appendix A)*
- [ ] 1.9.1 Evaluation harness: **LIAR** (baseline comparability with prior work) + a hand-built
      **Indian fixture set** (~50 cases: PIB-debunked scheme hoaxes, recycled communal videos,
      typosquat portals, fabricated attributions, and — critically — **genuine** content that must
      not be flagged). Report precision/recall per verdict class **and false-positive rate on
      genuine content separately**; a system that flags real news is worse than useless.
- [ ] 1.9.2 Publish the eval as `docs/EVALUATION.md`, regenerated in CI. "How do you know it works"
      must have an answer that is not the demo.
- [ ] 1.9.3 Ledger-completeness assertion in CI: no verdict may serialize with an empty
      `evidence[]` while claiming anything other than `UNVERIFIABLE`. The design law, enforced by a
      test rather than by review discipline.
- [ ] 1.9.4 Human-in-the-loop review queue: low-strength and `UNVERIFIABLE (developing)` cases land
      in a queue; human verdicts recorded **beside** machine output, never overwriting it. Doubles
      as the on-ramp to the Phase 3 fact-checker submission flow.
- [ ] 1.9.5 APK build + attach on tag via GitHub Actions (demo-day insurance).

**Done-when:** live run passes twice consecutively: (a) WhatsApp image forward → DISPUTED with
≥2 citations <6 s; (b) X/YouTube link → resolved + verdict; (c) fake-scheme text → PIB citation +
zero-corroboration evidence; (d) Gemini-down drill passes; (e) `verdict_engine` coverage 100%;
(f) **video share → Tier B dated citation, with the Tier E detector shown and excluded**;
(g) **the deletion test runs green in CI** (1.5.4); (h) **injection and SSRF fixture suites pass**;
(i) **`docs/EVALUATION.md` is generated and non-empty**.

**Out of scope:** Instagram ladder, Playwright, site clustering, attestations, dashboard, auth
beyond device ID, iOS. Media *acquisition* and forensics remain Phase 4 — the Phase 1 exception is
1.5.4, which adds keyframe dating plus a **pretrained, advisory-only** detector and trains nothing.

---

# PHASE 2 — Extraction depth & site forensics (weeks 1–6)

**Goal:** the long-tail web: any URL either resolves or fails into a screenshot flow; hoax sites
are profiled, not just their claims.

### Features delivered
1. Instagram/FB ladder: `/embed/captioned` → preview-bot UA OG fetch → Gemini `url_context` →
   guided screenshot fallback
2. Playwright renderer service: rendered DOM + server-side screenshot → visual pipeline
3. Site forensics: RDAP age · typosquat (rapidfuzz vs credible list) · **infra clustering**
   (analytics/AdSense IDs, crt.sh cert SANs, favicon hashes) · cloaking diff (dual-UA SimHash) ·
   archive footprint · credibility-structure heuristics
4. Site-profile cache → the hoax-site graph begins accumulating
5. Near-dup article detection (MinHash vs corpus) with diff evidence card
6. Backdating triple-check (stated vs snapshot vs sitemap lastmod)
7. Recurrence surfacing: "seen N times, first on date X" + same-image-different-captions view
8. Firebase Auth (anonymous → account), per-device rate limits

### Tasks
- [ ] 2.1 Playwright service on Cloud Run (own container): `/render {url} → {dom, screenshot}`,
      stealth context, mobile viewport, 15 s cap. ∥
- [ ] 2.2 Instagram adapter ladder with per-step outcome logging; guided-screenshot UX in app. 
- [ ] 2.3 `site_profile` table + forensics collectors (each a SignalProvider): rdap_age,
      typosquat, ga_adsense_cluster, cert_cluster (crt.sh), favicon_hash, cloaking_diff,
      archive_footprint, structure_score. *Test: fixtures incl. one known hoax domain.* ∥
- [ ] 2.4 MinHash near-dup provider + diff renderer (old vs new article). 
- [ ] 2.5 Backdating provider. 
- [ ] 2.6 Patterns UI: recurrence timeline + caption-variants list (query over `media_fingerprint`
      + `claim` joins).
- [ ] 2.7 Auth + rate limiting middleware; abuse guard (max checks/device/day).
- [ ] 2.8 Play Store internal-testing track release.

**Done-when:** an unknown hoax-site URL produces: site profile card (age, cluster, cloaking) +
content verdict with citations; Instagram public post resolves via ladder ≥60% of test set, with
clean screenshot fallback for the rest; internal-track build installed by 5 testers.

---

# PHASE 3 — Trust layer (weeks 6–10)

**Goal:** verdicts become portable, provable objects — the B2B seed.

### Features delivered
1. **Signed attestations:** Ed25519 (Cloud KMS) over `{content_hashes, verdict, evidence_digest,
   timestamp}` — every verdict card carries a verification QR/ID
2. **Transparency log:** append-only, hash-chained; public `/verify/{attestation_id}` page
3. Submit-to-fact-checker flow: prefilled tip (Alt News/BOOM) with evidence ledger attached
4. Public "developing" re-check jobs: +1 h/+6 h verdict maturation (Cloud Tasks)
5. Basic web verify page (server-rendered — no dashboard yet)

### Tasks
- [ ] 3.1 KMS key + signing service; attestation schema; ledger digest (merkle over evidence). 
- [ ] 3.2 `transparency_log` table (prev_hash chain) + public lookup endpoint + verify page. 
- [ ] 3.3 QR on reply card → verify page. 
- [ ] 3.4 Fact-checker submission templates + flow UI. 
- [ ] 3.5 Re-check scheduler + verdict-update push (FCM) to users who checked that content.

**Done-when:** scan the QR on any reply card → public page proves what was attested, when, on
what evidence; tampering with a stored ledger row breaks chain verification in tests.

---

# PHASE 4 — Media acquisition & forensics (weeks 10–16)

**Goal:** audio/video claims get real forensic treatment, with chain of custody.

### Features delivered
1. Evidence Acquisition Service: direct-CDN fetch + yt-dlp (per-platform policy table; DRM never)
2. Chain of custody: sha256 at acquisition, route, timestamps, ffprobe snapshot — referenced in
   attestations
3. Audio fingerprinting (audfprint-style) vs seeded corpus → recycled audio = Tier B citations
4. ASR transcript (Gemini / faster-whisper) → claims pipeline for video/voice notes
5. Progressive verdicts: fast Wave 0–1 answer, forensic addendum lands async
6. Advisory detectors (clearly Tier E): AV-sync on curated cases; antispoof behind a flag
7. Compute caps: first 90 s, ≤480p, mono 16 kHz, ≤24 frames

### Tasks
- [ ] 4.1 Acquisition worker (Cloud Run job): policy table config, route ladder, custody record. 
- [ ] 4.2 Fingerprint index + matcher; corpus seeding tool (ingest known speeches/broadcasts). 
- [ ] 4.3 ASR provider + voice-note intake in app. 
- [ ] 4.4 Async verdict updates end-to-end (202 → poll/push → card refresh). 
- [ ] 4.5 AV-sync provider (pretrained SyncNet-class) marked advisory; eval on 20-clip fixture
      set; ship only if precision acceptable — else keep behind flag.

**Done-when:** a recycled-audio video (new visuals, 2019 speech) → Tier B fingerprint citation;
dubbed-audio fixture → advisory escalation to DISPUTED; every acquisition has a custody record.

---

# PHASE 5 — B2B API & pilot (months 4–6)

**Goal:** first external consumers of the same engine.

### Features delivered
1. API productization: keys, OpenAPI spec, versioned `/v1`, idempotency, webhooks, per-tenant
   metering + budgets (the planner's budget input becomes plan tiers)
2. Newsroom dashboard v1 (Next.js 15): case queue, evidence view, batch URL check, CSV/JSON export
3. Trend alerts: claim-cluster velocity detection → email/webhook
4. DPDP hygiene: consent records, retention jobs (24 h media TTL enforced), DSR export/delete
5. Tenant onboarding for 1–2 newsroom pilots; feedback loop instrumented
6. Postgres RLS multi-tenancy; append-only audit log

### Tasks
- [ ] 5.1 Tenant + API-key model, HMAC signing, metering counters → usage endpoint. 
- [ ] 5.2 OpenAPI spec as source of truth; generate Dart + TS clients (ADR-0001 mitigation). 
- [ ] 5.3 Dashboard scaffold + case queue + evidence viewer. ∥
- [ ] 5.4 Webhooks (signed) + trend-alert job. 
- [ ] 5.5 RLS migration + audit log + DSR endpoints. 
- [ ] 5.6 Pilot onboarding runbook + SLA doc.

**Done-when:** a pilot newsroom verifies content via dashboard AND via API key with metered usage
visible; RLS tests prove tenant isolation; DSR delete verifiably purges a user.

---

# PHASE 6 — SaaS GA (months 6–9)

**Goal:** revenue-ready, compliance-credible.

### Features delivered
1. Billing: Razorpay/Stripe metered plans; overage handling
2. Infra upshift: Neon → Cloud SQL (asia-south1) · Upstash → Memorystore Valkey · PSE quota →
   Brave Search contract · GPU worker pool for forensics
3. Badge embed for publishers (attestation-backed) + public verification pages
4. SOC 2 Type I program (compliance automation tooling); pen test; VDP + security.txt
5. SSO groundwork (WorkOS-class broker) for enterprise pipeline

**Done-when:** first paying tenant invoiced; Type I audit window opened; migration executed with
zero API contract changes (the re-configuration-not-re-architecture proof).

---

# Feature → phase matrix (quick reference)

| Feature | Phase |
|---|---|
| Share-target intake, hash-first API, verdict engine, evidence cards | 1 |
| X/YouTube/web resolvers, OCR, temporal chain, corroboration, 10 languages, reply card | 1 |
| Instagram ladder, Playwright, site forensics, hoax-site graph, recurrence UI | 2 |
| Signed attestations, transparency log, QR verify, fact-checker submissions, re-checks | 3 |
| Media acquisition, custody, audio fingerprint, ASR, progressive verdicts, advisory detectors | 4 |
| B2B API, dashboard, trend alerts, DPDP endpoints, RLS, pilots | 5 |
| Billing, infra upshift, badge embed, SOC 2, SSO | 6 |

*Superseded planning docs live in `docs/archive/`. Architecture detail: `docs/architecture/`.*

---

# Appendix A — Prior art review (why the design law is the conclusion, not the hedge)

Five open-source builds in this problem space were reviewed. **Every one of them fails at the model
layer, and every one documents it.**

| Build | Model layer | What its own authors say about it |
|---|---|---|
| [dessa-oss/DeepFake-Detection](https://github.com/dessa-oss/DeepFake-Detection) | ResNet18 / FaceForensics++ | "does not generalize to real-life videos randomly collected from Youtube"; academic-trained models failed in the wild, YouTube-trained models missed academic manipulations, **no single dataset covered both** |
| [abhijithjadhav/Deepfake_detection_using_deep_learning](https://github.com/abhijithjadhav/Deepfake_detection_using_deep_learning) | ResNext + LSTM, 6k videos | 84.2%→93.6% by frame count — **on its own test set**; exactly the number the row above shows collapsing in the wild |
| [Md-Emon-Hasan/InformaTruth](https://github.com/Md-Emon-Hasan/InformaTruth) | RoBERTa-base / LIAR | "**The classifier is stylistic, not evidence-based**"; ~70% acc / 0.67 F1 |
| [vaibhav-gupta16/Factora](https://github.com/vaibhav-gupta16/Factora-AI-based-Fact-checker) | Groq LLM | Deliberately moved confidence **out of the model** into Python — credibility × relevance × corroboration |
| [begoneeraj/Newsup](https://github.com/begoneeraj/Newsup) (TruthLens India) | Llama 3.1/3.3 | Model-supplied confidence, unvalidated |

**The conclusion.** Five independent teams, five architectures, one shared failure: text classifiers
learn *writing style*, video CNNs learn *their training generators*, LLMs emit *fluent unfalsifiable
confidence*. None of the three learns truth. The evidence-tier contract is therefore not caution —
it is the only design consistent with what this field has already demonstrated about itself.

**Factora is convergent evidence for the opposite bet:** an independent team hit the same wall and
independently arrived at *compute the confidence in Python, not in the model*. That is Facify's
Tier A–D engine, reinvented at smaller scale. 1.2.3 generalizes it over the tier contract.

**What none of the five has:** provenance decoding (C2PA/SynthID) · temporal dating (Wayback,
publish-date chains) · independent-origin dedup · site forensics · signed attestations ·
hash-first on-device privacy · share-target intake · Indic multilingual. The entire evidence layer
is unoccupied territory.

### What was adopted from each

| Source | Adopted as |
|---|---|
| Factora — Python-computed confidence from credibility/relevance/corroboration | **1.2.3 / 1.7.7** — the explainable authenticity score |
| Factora — MBFC 859-domain credibility corpus; LIAR eval | **1.3.5**, **1.9.1** |
| InformaTruth — SSRF guard, prompt-injection sanitization, TTL caching, rate limits, human review queue, PDF intake, high test discipline | **1.1.5–1.1.7**, **1.5.5**, **1.9.4** |
| Newsup — GitHub Actions cron (escapes the 3-job Scheduler cap), Reddit / YouTube-transcript / RSSHub ingesters, APK build in CI, push-updated verdicts | **1.3.4**, **1.3.6**, **1.9.5** |
| abhijithjadhav — pretrained ResNext+LSTM weights | **1.5.4(b)** — shipped **quarantined in `advisory[]`**, CPU-only, no training |
| dessa-oss — the generalization-failure finding | The **"why not a score"** slide, and the citation behind Tier E |

### Deck note

The "why not a score" slide quotes rows 1 and 3 of the table above **verbatim**. A refusal to score
is far more persuasive in the words of the teams that built the scorers than in ours — and the
deletion test (1.5.4) turns the argument into something the judges watch execute rather than hear
asserted.
