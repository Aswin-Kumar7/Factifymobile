# Facify — Platform Architecture (Clean Slate)

**Positioning:** Facify is not a fact-check app. It is a **verification platform** — an API-first,
multi-tenant B2B SaaS whose consumer mobile app is one client among several. The hackathon build is
a thin vertical slice of this architecture, not a throwaway demo.

**The product family:**

| Surface | Who | Revenue |
|---|---|---|
| Consumer Android app | Public — the flywheel and the brand | Free |
| **Verification API** (metered) | Platforms, newsrooms, brand-safety, moderation pipelines | **Core revenue** |
| Newsroom dashboard | Editors verifying UGC before publishing | Seat + volume plans |
| **Signed trust badge** ("Verified by Facify") | Publishers/creators who want their content to carry provable verification | Subscription |
| Trend alerts | Emerging-misinformation early warning for comms/PR/civic bodies | Enterprise add-on |

**The moat is data, not models:** every verification enriches a content-addressed corpus — perceptual
hashes, claim embeddings, recurrence graphs, evidence citations. Misinformation is heavily repetitive,
so the corpus compounds: coverage improves and marginal cost falls as usage grows. That corpus is the
startup.

---

## 1. Ingestion — the share-intent truth, and the resolver architecture

### What the Android share sheet actually delivers

This is the fact that shapes the whole ingestion design:

| Shared from | What arrives | Media included? |
|---|---|---|
| WhatsApp (media forward) | `image/*` or `video/*` — actual bytes via `content://` URI | ✅ |
| Gallery / camera | Actual bytes | ✅ |
| **Instagram post/reel** | **`text/plain` — the post URL only** | ❌ |
| **X / Twitter** | URL only | ❌ |
| **YouTube** | URL only | ❌ |
| Facebook | URL only | ❌ |
| Browser | URL only | ❌ |
| Selected text | Text | — |

**Social apps never hand you the media.** They hand you a link. So ingestion is two planes:

```
                    ┌────────────────────────────────────────────┐
 ACTION_SEND ──────►│  INTAKE NORMALIZER (on device)             │
                    │  bytes?  → hash · EXIF · type-sniff        │
                    │  URL?    → send to Resolver Service        │
                    │  text?   → claim pipeline                  │
                    └────────────────────┬───────────────────────┘
                                         ▼
                    ┌────────────────────────────────────────────┐
                    │  RESOLVER SERVICE (server-side)            │
                    │  1 canonicalize: unwrap shorteners,        │
                    │    strip utm/fbclid, resolve redirects     │
                    │  2 route to PLATFORM ADAPTER               │
                    └────────────────────┬───────────────────────┘
                                         ▼
        ┌──────────────┬──────────────┬──────────────┬──────────────┐
        │ X adapter    │ YouTube      │ Instagram/FB │ Generic web  │
        │ oEmbed —     │ Data API v3  │ oEmbed (needs│ OpenGraph +  │
        │ public, free │ free 10k     │ Meta review) │ article      │
        │ text+author  │ units/day    │ → OG fetch   │ extraction   │
        │              │ title+thumb  │ → FALLBACK ▼ │              │
        └──────────────┴──────────────┴──────────────┴──────────────┘
                                         │
                     media URLs found → fetch → re-enter bytes plane
```

### The Instagram problem, answered honestly

Meta gates its oEmbed API behind app review, and increasingly login-walls public pages, so OpenGraph
fetch is best-effort. **Design the fallback as a first-class flow, not an apology:**

> "Instagram restricts automated access. Take a screenshot of the post and share that instead."

The screenshot path (OCR → text pipeline; image → visual pipeline) is the **universal adapter** — it
works for every platform, every privacy wall, forever. In practice most Indian users share
screenshots anyway. Build adapters for X/YouTube (open, free), attempt OG for Meta properties, and
let screenshots carry the rest.

### Video handling (bytes plane)

1. **On device:** extract keyframes at scene changes (capped ~12) + a 10 s audio fingerprint. Upload
   *those* first — kilobytes, not the video.
2. Server verifies keyframes against the corpus; most recycled videos resolve right here.
3. Full upload only if inconclusive **and** under a size cap (e.g. 100 MB), into object storage with
   a 24 h TTL; ASR on the audio track feeds the claim pipeline.

Mixed posts (image + video + caption) become one **Case** with multiple content objects; the verdict
is per-object plus a case-level summary.

---

## 2. Verification core — planner, providers, policy

Not a fixed pipeline. Three separated concerns, because tenants, plans and budgets differ:

### 2.1 Signal Providers (plugin architecture)

Every verification capability implements one interface and declares its contract:

```
SignalProvider {
  id, version
  accepts:   [image | video_keyframes | audio | text | url]
  cost_class:    FREE | CHEAP | METERED | EXPENSIVE
  latency_class: FAST (<300ms) | NORMAL (<2s) | SLOW (async)
  emits: Signal { type, finding, citation_url?, observed_at, confidence }
}
```

Launch set: corpus-match (pHash + embedding), provenance decode (C2PA / SynthID via Vertex / OpenAI
Verify), archive-history (first-seen dating), fact-check lookup, source-intelligence (domain age,
registry, credibility), web-corroboration (metered search), forensics (EXIF/ELA/re-encode), synthetic
detector (advisory only). New providers ship without touching the core — and enterprise tenants can
get tenant-specific providers (e.g. their own internal archive).

### 2.2 Budget-aware Planner — cost control as architecture

The planner receives `(content, tenant_plan, latency_budget, cost_budget)` and schedules providers in
waves, **stopping as soon as the policy engine can reach a verdict**:

```
Wave 0  FREE/FAST    cache · provenance decode · metadata          → ~60-70% of real
Wave 1  CHEAP        internal corpus · fact-check corpus · archive    traffic ends here
Wave 2  METERED      reverse-image search · web search · news APIs  → only if inconclusive
Wave 3  EXPENSIVE    LLM deep-dive · human review queue             → enterprise tier only
```

Metered calls are gated by per-tenant budgets enforced at the gateway. Cost is not an optimization
you do later — it is a scheduling input from day one.

### 2.3 Policy Engine → signed verdicts

- Deterministic rules over collected signals; **model scores are advisory inputs that can escalate
  suspicion but never establish authenticity**. No citation → `UNVERIFIABLE`.
- Rules are per-tenant configurable (a newsroom can demand two independent citations; a moderation
  pipeline can accept one).
- Output: verdict + machine-readable **evidence ledger** (every signal with its citation, snapshotted
  immutably at collection time — pages die, evidence must not).

### 2.4 Attestations — the B2B trust product ⭐

Every verdict is **signed** (Ed25519, keys in Cloud KMS) and appended to a public, hash-chained
**transparency log** (certificate-transparency style). This unlocks the "write news with
trustworthiness" business:

- A publisher runs a story through Facify → embeds a **badge** whose claim anyone can verify against
  the log — the badge is cryptographic, not decorative.
- An enterprise receiving a Facify verdict via API can prove later exactly what was attested and when.
- Tamper-evidence is a due-diligence feature enterprise buyers actually test.

---

## 3. Knowledge plane — how Facify stays current in real time

You do not search the whole web live per check. You maintain a **hot corpus, minutes fresh**, and pay
for live search only on the long tail.

| Feed | Cadence | Cost |
|---|---|---|
| ClaimReview / Google Fact Check Tools + Indian fact-checker RSS (Alt News, BOOM, Factly, Vishvas, PIB) | 15 min | Free |
| Credible-outlet corpus — RSS/sitemaps of ~150 Indian outlets across 10 languages | 15–30 min | Free |
| GDELT global news firehose (breadth) | 15 min | Free |
| Source registry — RDAP ages, IFCN signatories, hoax-site lists | Daily | Free |
| Archive snapshots of trending content | Continuous | Free |

Ingestion workers normalize everything into the evidence store (embeddings + citations). A clustering
job over incoming user checks detects **emerging misinformation waves** — which is simultaneously a
detection improvement and the **trend-alert product** for B2B.

---

## 4. Search & data APIs — 2026 reality

**Bing Search API retired 11 Aug 2025.** Any plan citing it — or SERP-scraper wrappers of it — is
already stale. Current strategy:

| Need | Choice | Price (verify at signup) | Note |
|---|---|---|---|
| Web search (primary) | **Brave Search API** | ~$5–9 / 1k | Independent index, licensed for AI use; free tier removed late 2025 |
| Web search (precision fallback) | Google Programmable Search JSON | $5 / 1k, 100/day free | 10k/day cap — fine early, plan around it |
| Semantic claim search (optional) | Exa (~$7/1k) or Tavily (~$8/1k) | pick **one**, later | AI-native retrieval |
| Reverse image | **Cloud Vision Web Detection** | $3.50 / 1k, first 1k/mo free | Primary; TinEye commercial later for enterprise SLA |
| First-seen dating | **Wayback CDX** | Free, no key | Core signal |
| Fact-checks | **Google Fact Check Tools API** (+ by-image) | Free | Core signal |
| Watermark decode | Vertex `imageverification@001` + OpenAI Verify | Credits / free | Deterministic AI-generation detection |
| Platform metadata | X oEmbed (free) · YouTube Data v3 (free quota) | Free | Resolver adapters |

**Explicitly avoided: SERP-scraping APIs (SerpAPI/Serper-class).** They violate search engines' ToS —
an acceptable hackathon shortcut, a red flag in enterprise due diligence. FactifyAI used one; Facify
must not.

LLM usage (extraction, OCR assist, phrasing, translation): current-generation Gemini Flash-class via
Vertex, with batch endpoints and context caching for corpus work. **Model IDs live in config, never
in code** — models rotate ~6-monthly, and stack currency is a process (Renovate + quarterly review),
not a snapshot.

---

## 5. Cost engineering & unit economics

Structural cost controls (not tweaks):

1. **Content-addressed cache first.** Misinformation is Zipfian — the same items are checked over and
   over. Cache hits cost ≈ ₹0, and the hit rate *rises* with user growth → **marginal cost falls as
   you scale**. That is the margin story for investors.
2. **Negative caching** — `UNVERIFIABLE` results carry a TTL so unresolvable content doesn't re-trigger
   metered waves.
3. **Dedup before spend** — pHash + embedding match precedes any metered call.
4. **Planner budgets** — metered waves run only past a suspicion threshold, within tenant budget.
5. **Batch everything offline** — corpus enrichment via batch APIs (~half price), never live rates.
6. **Meter per tenant** at the gateway; usage feeds billing directly.

Illustrative month at 100k checks (verify current prices before quoting): ~65% cache-resolved → ~35k
live; reverse-image ≈ $120; web search (only ~20% of live escalate) ≈ $50; LLM phrasing/extraction
≈ $30–80; free tiers cover the rest. **Blended ≈ $200–250 ≈ ₹0.17–0.21/check.** B2B pricing at
₹2–5/check → **~90% gross margin**, improving with scale.

---

## 6. Security, privacy, compliance — built in, not retrofitted

### Identity & tenancy
- OIDC everywhere. Consumer: Identity Platform/Firebase Auth. **B2B: SSO/SAML + SCIM via WorkOS-class
  broker** — enterprise deals die without it.
- API keys with HMAC request signing; mTLS for enterprise integrations.
- **Multi-tenant Postgres with Row-Level Security** on `tenant_id`; per-tenant envelope keys, CMEK for
  the enterprise tier.

### Encryption & data handling
- TLS 1.3 + certificate pinning in the app. AES-256-GCM at rest via cloud KMS. Signed URLs for media.
- **Hash-first ingestion is the privacy architecture:** a 64-bit perceptual hash leaves the device
  first; media uploads only on cache miss *with consent*. Data minimization by design, not by policy
  document.
- Raw media TTL 24 h. The durable record is the evidence ledger — public URLs and derived features
  only. **EXIF GPS is redacted before anything persists.**
- Data residency: `asia-south1/2` (Mumbai/Delhi) — a hard requirement for Indian gov/enterprise.

### DPDP Act (in force; phased enforcement through 2027)
Consent notices, purpose limitation, retention schedule, DSR endpoints (export/delete), records of
processing, breach runbook: **6 h CERT-In / 72 h Data Protection Board**. This is a *sales asset* in
India, not overhead.

### Device permissions (modern Android — the minimal-manifest story)
- Share-sheet intake needs **no storage permission** — `content://` URIs are scoped grants.
- Manual pick uses the **system Photo Picker** — again no `READ_MEDIA_*`.
- Net: `INTERNET` + optional notifications. **A two-permission manifest** is an enterprise talking
  point in itself.
- App integrity: Play Integrity API; local crypto in Android Keystore; **no secrets in the APK** —
  backend-issued short-lived tokens only.

### Engineering workflow (the "enterprise code quality" ask)
- Monorepo, trunk-based, mandatory PR review, conventional commits, **ADRs for every architectural
  decision** (`docs/adr/`).
- CI gates from commit #1: Semgrep (SAST) · Gitleaks (secrets) · osv-scanner + Renovate (deps) ·
  Trivy (containers) · SBOM (CycloneDX) · cosign image signing · SLSA provenance.
- IaC: Terraform/OpenTofu, dev → stage → prod promotion, no console changes.
- Observability: OpenTelemetry traces/metrics/logs, SLOs with error budgets, append-only audit log in
  a locked bucket (SOC 2 evidence from day one).
- Testing: unit + contract tests on the OpenAPI spec + golden-file tests on the policy engine
  (verdicts are deterministic — snapshot them).

### Certification roadmap
| When | What |
|---|---|
| Day 1 | DPDP hygiene, VDP + security.txt, audit logging |
| Mo 6–9 | **SOC 2 Type I** (compliance automation: Sprinto/Vanta-class — Sprinto is India-based) |
| Mo 12–15 | SOC 2 Type II (observation window) + first external pen test |
| Enterprise-driven | ISO 27001 when a contract demands it — not before |

---

## 7. Stack (2026-current, with the *why*)

| Layer | Choice | Currency note |
|---|---|---|
| Mobile | **Flutter 3.3x** (Dart 3) | Still the right one-codebase choice; Kotlin Multiplatform is the rising alternative — revisit at scale |
| Dashboard | **Next.js 15 / React 19** + shadcn/ui | Current B2B standard |
| API services | **Python 3.12+ / FastAPI**, Pydantic v2 | Current ecosystem standard for ML-adjacent APIs |
| Workflow engine | Cloud Tasks now → **Temporal** when verification workflows get long-running | Durable execution is the current pattern for multi-step pipelines |
| Events | Pub/Sub | — |
| Database | **Postgres 17** + pgvector | — |
| Cache | **Valkey** (the open-source Redis successor; Memorystore supports it) | Redis licensing changed 2024 — Valkey is the current OSS default |
| Objects | GCS, 24 h TTL buckets | — |
| AI | Current-gen Gemini Flash-class via Vertex · Vertex watermark verification · Chirp ASR · current multilingual embeddings | **Model IDs in config, not code**; quarterly model review |
| Infra | Cloud Run gen2 · Cloud Armor (WAF) · Cloud CDN · Terraform | Scales to zero; India regions |
| Billing | Razorpay (domestic) / Stripe (global) metered | — |
| Auth | Identity Platform + WorkOS-class SSO broker | SAML/SCIM for enterprise |

**Anti-staleness process** (the actual answer to "no 2–5 yr old tech"): Renovate auto-PRs weekly ·
model/config registry per environment · quarterly stack review with an ADR recording what was
evaluated and why it stayed or changed.

---

## 8. Monorepo skeleton

```
facify/
├── apps/
│   ├── mobile/            # Flutter — share intake, verdict UI, badge scanner
│   └── dashboard/         # Next.js — newsroom console, trend alerts, billing
├── services/
│   ├── gateway/           # authN/Z, tenancy, rate limits, usage metering
│   ├── resolver/          # URL canonicalizer + platform adapters
│   ├── pipeline/          # planner, signal providers, policy engine
│   ├── attestation/       # signing, transparency log, badge verification
│   └── knowledge/         # ingestion workers (fact-checks, news, sources)
├── packages/
│   ├── schemas/           # OpenAPI spec + generated clients (single source of truth)
│   └── evidence/          # shared evidence-ledger types
├── infra/                 # Terraform: envs, KMS, RLS migrations, buckets
├── docs/adr/              # architecture decision records
└── .github/workflows/     # CI: SAST, secrets, deps, SBOM, sign, deploy
```

---

## 9. Roadmap

| Phase | Window | Ship |
|---|---|---|
| **0 — Hackathon** | Now | Thin vertical slice *on this architecture*: share intake (bytes + X/YT URLs + screenshot fallback), Waves 0–1, signed verdict card, one dashboard page showing the transparency log. CI gates live from the first commit — the repo itself is part of the pitch. |
| **1 — Pilot** | 0–3 mo | 1–2 newsroom pilots · badge embed · API alpha (keys, metering) · SOC 2 program starts |
| **2 — GA** | 3–9 mo | Metered public API · dashboard GA · trend alerts · SOC 2 Type I |
| **3 — Enterprise** | 9–18 mo | SSO/SCIM · CMEK · human-review tier · Type II · ISO 27001 as deals demand |

---

## What's deliberately different from the old plan

| Old (app-first) | New (platform-first) |
|---|---|
| Android app with a backend | **API product; the app is one client** |
| Fixed five-collector pipeline | **Pluggable signal providers + budget-aware planner** |
| Verdict card in the UI | **Signed attestation + public transparency log** — the trust product |
| Live API calls per check | **Hot knowledge plane** (minutes-fresh corpus) + metered long-tail search |
| Cost as an afterthought | **Cost as a scheduling input**, metered per tenant, margin improves with scale |
| SerpAPI-class scrapers | Licensed indexes only (Brave/Google/Vision) — clean due diligence |
| Security "later" | RLS tenancy, KMS, DPDP, CI supply-chain gates **from commit #1** |

---

## Sources

[Bing Search API retirement & alternatives](https://www.firecrawl.dev/blog/bing-search-api-alternatives) ·
[Brave Search API positioning](https://brave.com/search/api/guides/what-sets-brave-search-api-apart/) ·
[Bing alternatives tested](https://apiserpent.com/blog/bing-search-api-alternatives) ·
[Tavily/Exa pricing comparison](https://www.firecrawl.dev/blog/tavily-alternatives) ·
[Android ACTION_SEND sharing](https://developer.android.com/training/sharing/send) ·
[Instagram oEmbed requirements](https://medium.com/geekculture/share-post-text-image-to-other-apps-on-android-e83d2aa5116c) ·
Cloud Vision pricing, Fact Check Tools API, Wayback CDX, DPDP timeline, Vertex watermark
verification — verified earlier in this project's research.

> Prices and quotas move. Re-verify Brave/Exa/Tavily/Vision numbers and current Gemini pricing at
> signup — and record the decision in an ADR.
