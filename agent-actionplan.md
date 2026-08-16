# Facify — Agent Action Plan

**Derived from:** [codexplan.md](codexplan.md) — that document is the specification; this one is the
build order. Where they disagree, `codexplan.md` wins and this file is wrong.

**Purpose:** a module-by-module description of what to build, in what order, with what boundaries,
and how each module proves it is finished. No code, no schema definitions — those are decided inside
each module against the contracts in `codexplan.md` §3, §9, §10 and §12.

---

## How an agent uses this document

1. **Take one module at a time.** A module is one reviewable change with a conventional commit.
2. **Do not start a module until its dependencies are green.** Dependencies are listed per module
   and the graph is acyclic; if you find yourself needing a downstream module, you have mis-scoped
   the work.
3. **"Done when" is the contract.** A module is not finished because the code exists. It is finished
   when its stated conditions are demonstrably true.
4. **"Must not" is not advice.** Every boundary listed exists because violating it breaks the design
   law, the cost model, or a live gate. If a boundary blocks you, stop and escalate rather than
   working around it.
5. **Never invent evidence.** No hand-authored verdicts, no fabricated sources, no synthetic
   corpus rows, no "temporary" stub that returns a plausible answer. A stub returns *nothing* and
   the pipeline abstains.

---

## The eight invariants every module obeys

These are checked in CI and hold across the whole codebase.

| # | Invariant | Enforced by |
|---|---|---|
| 1 | The verdict engine receives validated evidence objects only — never model output, detector scores, or search snippets | Type signature; M08 |
| 2 | Removing every advisory (Tier E) signal leaves verdicts byte-identical | M08 deletion test |
| 3 | No decisive status ships with empty evidence | M08 ledger-completeness test |
| 4 | Every evidence object carries a citation URL, a source snapshot, an excerpt and an anchor | M28, M40 |
| 5 | Every numeric or ordinal field on an evidence object is reproducible from a recorded metric | M05, M28 |
| 6 | Source-risk signals alone can never reach `DO_NOT_SHARE` | M06 |
| 7 | External text — fetched pages, OCR, PDF, captions — is data, never instructions | M11 |
| 8 | Every external call passes the governor and degrades to "capacity limited", never to a fabricated answer | M14 |

---

## Track map

```
A. Foundation        M01 M02 M03 M04
B. Pure core         M05 M06 M07 M08          ← no I/O; build first, in parallel with A
C. Safety            M09 M10 M11 M12
D. Cost control      M13 M14
E. Extraction        M15 M16 M17 M18 M19 M20 M21
F. Local models      M22 M23
G. Knowledge plane   M24 M25 M26
H. Evidence          M27 M28 M29 M30 M31 M32
I. Media             M33 M34 M35 M36 M37
J. Graph             M38 M39
K. Orchestration     M40 M41 M42 M43
L. Clients           M44 M45
M. Evaluation & ops  M46 M47 M48 M49
```

**The critical path is A → D → G → H → K.** Track B has no dependencies at all and should start on
day one alongside Track A. Track L needs only the frozen API contract, not the pipeline.

---

# Track A — Foundation

## M01 · Repository, CI and quality gates

**Purpose.** A single deployable service skeleton with the test and lint harness that every later
module reports into.

**Depends on:** nothing.

**Responsibilities**
- One FastAPI application with the internal module layout from `codexplan.md` §4 — `api`, `intake`,
  `extraction`, `knowledge`, `evidence`, `sources`, `verdict`, `media`, `cache`, `governor`,
  `corpus`, `security`, `db`; plus top-level `web`, `mobile`, `data`, `docs`.
- Dependency management, lockfile, reproducible build, container image.
- CI that runs lint, type-check and the full test suite on every change.
- Secret scanning and dependency vulnerability scanning in CI.
- Conventional commits enforced.
- A test-layout convention: pure-core tests that need no fixtures, snapshot-replay tests, and live
  tests that are excluded from CI by default.

**Must not**
- Run scheduled jobs in CI. CI runs tests only.
- Place any provider credential in the repository or in CI configuration.

**Failure behaviour.** A red CI blocks merge. No exceptions for "demo week".

**Done when**
- A clean checkout builds, boots, serves a health endpoint, and passes an empty-but-real test suite.
- The container image builds in CI and is the same artifact deployed.

---

## M02 · Configuration and secret handling

**Purpose.** Every environment-specific and provider-specific value lives in configuration, never in
code.

**Depends on:** M01.

**Responsibilities**
- Typed, validated settings loaded at startup; the process refuses to boot on invalid configuration
  rather than failing at first use.
- **Model identifiers are configuration.** No model name appears in application code.
- Per-provider settings: enabled flag, credential reference, daily cap, timeout, retry policy.
- A feature flag per optional provider so any of them can be disabled without a code change —
  required by the Day 13 fallback test.
- Environment separation so a local run cannot touch production data or spend production quota.

**Must not**
- Read credentials from anywhere but the server environment.
- Ship a default that enables a paid or metered provider.

**Done when**
- Every provider can be disabled by configuration alone, and the service boots and serves with all
  optional providers off.

---

## M03 · Persistence layer

**Purpose.** Migrations and repositories for the entity set defined in `codexplan.md` §10.

**Depends on:** M01, M02.

**Responsibilities**
- Forward-only migrations creating the full entity set in one pass: cases, content objects, claims,
  claim anchors, evidence, sources, source snapshots, media matches, source relations, observations,
  verdicts; the write-back set (media fingerprints, claim occurrences, origin clusters); the
  cache and budget set (verdict cache, call budget, feed and feed-run).
- Repository interfaces per aggregate — the rest of the codebase never issues ad-hoc queries.
- Vector columns and their indexes: image vectors, text vectors, and the perceptual-hash column with
  its Hamming index. Dimensions come from M22 and M23 and are fixed at migration time.
- The uniqueness constraint that makes ingestion idempotent (feed identifier plus window start).
- `tenant_id` and `provider_version` columns present but unused, so later evolution needs no
  migration surgery.

**Must not**
- Store raw media bytes in the database. Media is short-TTL object storage; the durable record is
  hashes, derived features and citations.
- Create the write-back tables later. They must exist from the first request or the compounding-loop
  claim is a future migration rather than a property of the system.

**Failure behaviour.** Migration failure is a boot failure.

**Done when**
- A migration runs clean on an empty database, and a round-trip write and read succeeds through a
  repository for every aggregate.
- Storage sizing is recorded: measured bytes per corpus item, extrapolated against the free-tier
  ceiling, written into the ops notes.

---

## M04 · Observability and audit

**Purpose.** Make every verdict explainable after the fact without opening a debugger.

**Depends on:** M01, M03.

**Responsibilities**
- Request identifier generated at intake, attached to every log line, returned on every response,
  and stored on the case.
- Structured logging with a fixed field set: request id, case id, module, provider, model id,
  latency, outcome, failure reason.
- An audit event for every verdict produced and every piece of evidence retrieved — append-only.
- Per-provider counters: calls, successes, failures, latency percentiles. These feed the Day 13
  provider-failure-rate report and the governor's dashboards.
- A recorded reason string on every skipped provider ("capacity limited", "disabled", "timeout").

**Must not**
- Log full article bodies, raw media, or credentials.
- Log personal data from EXIF; GPS is stripped upstream and must never reach a log.

**Done when**
- A single verdict can be reconstructed from logs alone: what was fetched, what was skipped and why,
  which model served each call, and which rule fired.

---

# Track B — Pure core (no I/O)

Start this on day one. It has no dependencies, needs no database, network or model, and it is the
part of the system that must be most heavily tested.

## M05 · Domain types and enumerations

**Purpose.** One authoritative definition of every value the system can produce.

**Depends on:** nothing.

**Responsibilities**
- The four claim statuses, the three provenance states, the three synthetic-signal states, the four
  source-risk levels, and the six actions — exactly as enumerated in `codexplan.md` §2.
- The eight claim types from §5A, the severity and importance scales from §9.
- The evidence object type, the advisory object type, and the relation labels from §5A step 8.
- The match-quality scale and the requirement that it is derived from a recorded metric and
  threshold.
- **Evidence and advisory are separate types.** This is the structural enforcement of invariant 1 —
  the verdict engine's signature accepts only the former, so passing an advisory signal is a
  compile-time or validation-time error, not a policy violation to be caught in review.

**Must not**
- Allow a free-text confidence field on an evidence object.
- Allow an evidence object to be constructed without a citation URL, snapshot reference, excerpt and
  anchor.

**Done when**
- Constructing an evidence object without a citation fails validation.
- There is no code path by which an advisory object can be passed where evidence is expected.

---

## M06 · Verdict engine

**Purpose.** Turn a claim plus its validated evidence into a status, and a set of claim statuses into
one case action. Pure function, no I/O.

**Depends on:** M05.

**Responsibilities**
- The eight ordered rules in `codexplan.md` §9, evaluated deterministically.
- The `CONTRADICTED` versus `MISLEADING_CONTEXT` boundary: the former when the asserted proposition
  itself is false, the latter when the proposition is true but its framing — date, place, actor,
  causal link — is not.
- The case rollup precedence table, evaluated top to bottom, first match wins, with "material"
  resolved to its enum definition rather than left to judgement.
- Conflict handling: when evidence points both ways, surface the conflict and abstain rather than
  averaging.
- A rule version stamped onto every verdict, so a cached verdict produced under older rules is
  identifiable.
- Every decisive result carries the identifier of the rule that fired and the evidence that
  satisfied it.

**Must not**
- Perform any network, database, model or filesystem access.
- Accept advisory input in any form.
- Produce `DO_NOT_SHARE` from source-risk evidence alone.
- Produce a decisive status from search silence alone.

**Failure behaviour.** Unrecognised or malformed evidence is a programming error and raises; it is
never silently ignored.

**Done when**
- Table-driven tests cover every rule branch, both boundary cases, and every row of the rollup table.
- The worked example in `codexplan.md` §5A reproduces exactly, including the case action.
- The engine runs with no database, no network and no model available.

---

## M07 · Evidence strength

**Purpose.** The explainable authenticity score — a deterministic explanation index, not a
probability.

**Depends on:** M05.

**Responsibilities**
- Compute a score from the components named in `codexplan.md` §9: evidence quality, relevance to the
  exact claim, independent-origin count, temporal confidence, source transparency, conflict penalty.
- Return the component breakdown alongside the number, with the citations that produced each
  component.
- Report advisory signals **beside** the calculation, explicitly labelled as excluded from it.

**Must not**
- Take any advisory or model-produced value as an input.
- Emit a bare number without its components.
- Present itself as a probability that the claim is true, or as a global authenticity score that
  conflates provenance with truth.

**Done when**
- A test proves that adding, removing or maximising every advisory signal changes the score by
  exactly zero.
- Every component in a sample output resolves to at least one citation.

---

## M08 · Design-law CI assertions

**Purpose.** Convert the three architectural promises into failing tests.

**Depends on:** M06, M07.

**Responsibilities**
- **Deletion test:** run a representative case set with all advisory providers enabled, then with all
  disabled, and assert the verdicts and strengths are byte-identical.
- **Ledger-completeness test:** assert no verdict serialises with a decisive status and an empty
  evidence list.
- **No-model-score test:** assert every numeric or ordinal field on every evidence object in the
  fixtures traces to a recorded metric and threshold.
- These run on every commit, not on demand.

**Must not**
- Be marked skippable, xfail, or "known issue" at any point in the build.

**Done when**
- All three fail loudly when the invariant is deliberately broken in a scratch branch, and pass on
  main.

---

# Track C — Safety

## M09 · Secure outbound fetcher

**Purpose.** One chokepoint through which every outbound HTTP request passes.

**Depends on:** M02, M04.

**Responsibilities**
- Scheme allowlist: HTTP and HTTPS only.
- Resolve DNS before connecting and reject loopback, private, link-local, multicast, and cloud
  metadata address ranges.
- **Re-check the destination after every redirect**, not only on the initial URL.
- Caps on redirect depth, response bytes, content type, and total time.
- Never send cookies, credentials or authenticated sessions.
- Record for every fetch: final URL, HTTP status, content type, byte count, fetch timestamp,
  extraction route — this is the chain-of-custody record other modules cite.
- A politeness layer for bulk ingestion: honest user agent, robots respected, per-domain rate limit
  and backoff. User-triggered single fetches are not crawling and are not rate-limited per domain.

**Must not**
- Bypass a paywall, login wall, DRM, or any platform access control.
- Be bypassed by another module issuing its own HTTP client.

**Failure behaviour.** A blocked or failed fetch is a recorded outcome that produces `INSUFFICIENT`,
never an exception that surfaces to the user as a verdict.

**Done when**
- A fixture suite of SSRF payloads is rejected, including a redirect that pivots to an internal
  address on the second hop.
- No other module in the codebase constructs an HTTP client.

---

## M10 · Upload validation and resource limits

**Purpose.** Stop hostile files before they reach a parser.

**Depends on:** M02.

**Responsibilities**
- Size, MIME, and — for video — duration and resolution limits, enforced before any decode.
- Content-type sniffing rather than trusting the declared type or extension.
- Decompression-bomb protection for archives, images and PDFs.
- Sandbox the PDF and image parsers; treat every parse as untrusted input.
- Strip EXIF GPS before anything is persisted or logged.
- Enforce short retention on raw media, with explicit user consent captured at intake.

**Must not**
- Make a private user upload publicly accessible for any reason — including to satisfy a third-party
  image-search API that requires a public URL. Providers that accept raw bytes are used instead.

**Done when**
- Malformed, oversized and bomb fixtures are all rejected without crashing the process.
- A test confirms GPS never reaches storage or logs.

---

## M11 · Prompt-injection boundary

**Purpose.** Everything fetched from the network is adversary-controlled text; keep it as data.

**Depends on:** M02, M04.

**Responsibilities**
- All external text — fetched pages, OCR output, PDF text, captions, transcripts — is passed to the
  model only inside a clearly delimited untrusted region, never in a system or developer position.
- Model output is schema-validated and treated as an untrusted proposal until deterministic checks
  pass.
- **Detect instruction-shaped content in fetched material and record it.** A page attempting to
  instruct the verifier is practising deception; that is a finding routed to the source-risk track,
  not noise to be dropped silently.
- Maintain a growing fixture set of real injection attempts encountered in live fetching.

**Must not**
- Concatenate fetched text into an instruction.
- Discard a detected injection attempt without recording it.

**Done when**
- The injection fixture suite passes, and at least one fixture demonstrates a detected attempt
  appearing in the output as a recorded signal.

---

## M12 · Rate limiting

**Purpose.** Protect the service and the free-tier quotas from a single caller.

**Depends on:** M02, M03.

**Responsibilities**
- Per-device and per-key request limits with clear response headers.
- Separate, stricter limits for the file-upload endpoint.
- Request identifiers on every response for support correlation.

**Done when**
- Limits are enforced, observable, and configurable without redeploy.

---

# Track D — Cost control

## M13 · Cache layer

**Purpose.** Make repeat content free. This is the mechanism behind both the cost model and the
compounding-moat claim.

**Depends on:** M03.

**Responsibilities**
- Three cache surfaces: resolved-URL text, extraction results keyed by content hash, and complete
  verdicts.
- Verdict cache keys incorporate the inputs that would change the answer: rule version, extractor
  version, corpus version, policy profile and language. A rule change must not serve a stale verdict.
- **Negative caching:** `UNVERIFIED` results carry a time-to-live so unresolvable content does not
  re-trigger metered work on every share.
- Cache probe runs **before** any external call, immediately after hashing.
- Cache hit rate is a recorded metric — it is a stated day-one investor metric and must be
  measurable from the start.

**Must not**
- Serve a cached verdict without its retrieval timestamp available to the UI.
- Cache across a rule-version boundary.

**Done when**
- Re-submitting identical content performs zero external calls, and this is asserted by a test.
- Re-running the audit manifest after a code change costs zero model calls while snapshots remain
  valid.

---

## M14 · Call governor

**Purpose.** No external provider can be called more times per day than its budget allows, and
exhaustion is honest.

**Depends on:** M02, M03, M04.

**Responsibilities**
- Per-provider daily counters against configured caps, set **below** the provider's own limit so the
  system degrades before the provider does.
- Every external call in the codebase acquires from the governor first. There is no direct path.
- On exhaustion: skip the provider, record the reason, and let the pipeline continue with whatever
  evidence it has — which usually means abstaining.
- Surface "capacity limited" as a first-class state in the response, not an error.
- Also guard concurrency, not only volume: a per-minute ceiling matters more than a daily one when
  three items are shared in quick succession during judging.

**Must not**
- Retry past the cap.
- Allow a caller to bypass it "just for the demo".

**Failure behaviour.** Governor unavailability fails closed — no external call proceeds.

**Done when**
- Setting every cap to zero produces a complete, honest run with all verdicts abstaining and every
  skip reason recorded.

---

# Track E — Extraction

## M15 · Intake normalizer

**Purpose.** Turn any accepted input into a case with one or more content objects.

**Depends on:** M03, M10.

**Responsibilities**
- Accept URL, pasted text, image, PDF and short video.
- Compute identity immediately: cryptographic hash for every object, perceptual hash for images and
  extracted frames.
- Detect the true input type by sniffing, not by the client's claim.
- Create the case, the content objects, and the initial observation record before any work is done,
  so that even a failed verification is auditable.
- Capture the consent flag for media processing and the requested language.
- Route to the correct downstream path and record the extraction route on the case.

**Must not**
- Begin any external work before the cache probe.

**Done when**
- Every input type creates a well-formed case, and an input that fails validation still leaves an
  auditable record of the attempt.

---

## M16 · Web article extraction

**Purpose.** Turn a fetched public page into structured content with anchors.

**Depends on:** M09.

**Responsibilities**
- Priority order: structured metadata first, then a main-content extractor, then a lighter published
  variant if the main page is script-walled.
- Extract canonical URL and redirect chain, title and subtitle, article body, author and publisher,
  published and updated dates, structured article metadata, quotations, images with captions, and
  outbound cited links.
- Compute and store a hash of the extracted page so a later change is detectable.
- Store short excerpts and metadata, never a full copy of the article body.
- Record extraction limits when the page is only partially parseable, rather than silently returning
  less.
- Note that the absence of structured metadata is a weak signal in its own right — real publishing
  systems emit it, hoax sites frequently do not.

**Must not**
- Bypass a paywall or login wall to obtain more content.
- Treat a partially-extracted page as fully extracted.

**Done when**
- A representative set of real Indian news pages extracts title, date, publisher, body and outbound
  links; a script-only page falls back cleanly and records the limitation.

---

## M17 · PDF extraction

**Purpose.** Forged government circulars and scheme notices circulate as PDFs; treat them as
documents, not images.

**Depends on:** M10.

**Responsibilities**
- Text extraction with page and character positions preserved for anchoring.
- Page rendering when the PDF is image-only, feeding the OCR path.
- Document metadata capture where present.
- Hard limits on page count and file size.

**Must not**
- Execute embedded content of any kind.

**Done when**
- A real public official PDF and a real published forged-circular case both produce anchored text.

---

## M18 · OCR

**Purpose.** Screenshots are the dominant Indian format; the text inside an image is usually the
claim.

**Depends on:** M14 (if model-served), M15.

**Responsibilities**
- Extract text from images, rendered PDF pages and video keyframes.
- Preserve the raw extraction and the detected language before any normalisation.
- Attach spatial anchors so a claim can point back to a region of the image or a frame timestamp.
- Route output into the claim pipeline as untrusted text (M11 applies).

**Must not**
- Silently translate. Language detection is a separate, recorded step.

**Done when**
- A Hindi screenshot and an English screenshot both yield anchored text that reaches the claim
  pipeline.

---

## M19 · Language and script detection

**Purpose.** Route Indian-language content correctly and choose the output language.

**Depends on:** M05.

**Responsibilities**
- Deterministic detection first — script ranges and a romanised-Indic heuristic, since Hinglish is
  the default register of Indian forwards.
- Model fallback only when deterministic detection is inconclusive.
- Record the detected language on the case; it is a cache key component.

**Must not**
- Claim quality in languages that have no evaluation coverage. Scope is English, Hindi and Hinglish.

**Done when**
- A Devanagari sample, a romanised-Hindi sample and an English sample each route correctly without a
  model call.

---

## M20 · Claim extraction

**Purpose.** Convert a document into atomic, anchored, checkable claims. This is the only place the
model does substantive work, and it does not judge.

**Depends on:** M11, M13, M14, M19.

**Responsibilities**
- **One model call per document.** Claim segmentation, entity and date normalisation, severity,
  importance, coverage expectation and search phrases return in a single structured response.
- Every claim carries its claim type from the fixed enumeration, its entities, dates and location,
  its severity and importance, and a source anchor pointing at the exact paragraph, character range,
  frame or timestamp it came from.
- A claim without an anchor fails schema validation and is not stored.
- Opinion is labelled as opinion and excluded from factual checking.
- Coverage expectation — how widely this would be reported if true — is captured here because the
  corroboration module needs it to interpret silence correctly.
- Cache extraction results by content hash so a re-run costs nothing.
- Record the model identifier that served each call.
- Escalate to a higher-capability model only when schema validation fails or the input is unusable,
  and cap that escalation separately.

**Must not**
- Ask the model whether the document is true, or accept any status from it.
- Make more than one call per document in the normal path.
- Store a claim whose anchor cannot be resolved back to the source text.

**Failure behaviour.** Schema validation failure retries once against the escalation model, then
abandons extraction; the case proceeds with whatever media evidence exists, or abstains.

**Done when**
- Pasted text produces stable, anchored, schema-valid claims across repeated runs.
- A test asserts exactly one model call per document.

---

## M21 · Template phrasing

**Purpose.** The user-facing wording is assembled, not generated, so the response path costs no quota
and the verdict is unchanged if the model is unavailable.

**Depends on:** M05, M19.

**Responsibilities**
- Templates per status, per action and per evidence kind, in English and Hindi.
- Slots filled from the verdict, the evidence and the citations — publisher, date, count of
  independent origins.
- A "what Facify cannot establish" block, composed from what was checked and came back empty.

**Must not**
- Call a model on the response path.
- Produce wording that asserts more than the evidence supports.

**Done when**
- With every model provider disabled, a full verdict still renders complete, correct bilingual text.

---

# Track F — Local models

## M22 · Text embedding service

**Purpose.** Semantic retrieval over claims and corpus items, at zero quota cost.

**Depends on:** M02.

**Responsibilities**
- A small multilingual sentence-embedding model running **locally on CPU** via ONNX, loaded once per
  container.
- Used for claim-to-fact-check matching, claim-to-corpus retrieval, and corpus deduplication.
- Fixed dimensionality agreed with M03 before migrations are written.
- Batch encoding for ingestion; single encoding for request-path use.

**Must not**
- Call a hosted embedding API. Ingestion embeds hundreds to thousands of items per day, against a
  daily model allowance in the low hundreds that is already committed to claim extraction. A hosted
  embedding call would exhaust the quota on ingestion alone, before any user request, and it would
  fail quietly — correct at test volume, starved in production.

**Done when**
- Ingestion of a full feed batch completes with zero external model calls.
- Encoding latency and container memory are measured and recorded against the deployment sizing.

---

## M23 · Image embedding service

**Purpose.** Verify perceptual-hash candidates robustly against crop, resize, recolour and
re-encoding.

**Depends on:** M02.

**Responsibilities**
- A CLIP-class image embedding model running locally on CPU via ONNX, loaded once per container.
- Used only to *verify* candidates produced by hash search — never as the primary retrieval step on
  its own.
- Fixed dimensionality agreed with M03 before migrations.

**Must not**
- Be treated as decisive by itself. Embedding similarity alone is candidate generation; a decisive
  media match additionally requires visual or contextual confirmation and a source date.

**Done when**
- A cropped, resized and recompressed variant of a known image verifies against the original, and a
  visually similar but different image does not.

---

# Track G — Knowledge plane

## M24 · Feed registry and scheduler trigger

**Purpose.** Own the list of allowlisted sources and the single trigger that drives ingestion.

**Depends on:** M02, M03.

**Responsibilities**
- A registry of 20–30 allowlisted Indian news and fact-check feeds, each with its fetch cadence,
  next-fetch time, conditional-request state and backoff.
- **Deliberately include outlets that carry the same wire services**, so origin clustering has real
  duplicates to collapse. Choosing which real feeds to subscribe to is a selection decision, not
  synthetic data.
- Exactly one scheduler owner per environment, invoking one authenticated internal endpoint or job.
- An idempotency lock in the database so a duplicated trigger cannot double-ingest.

**Must not**
- Run the scheduler inside the web process — instances scale to zero or multiply, and both break
  scheduling.
- Use CI-hosted scheduling: public-repository schedules are disabled automatically after a period of
  inactivity, and credentials do not belong in a public repository.

**Done when**
- A single tick fires on schedule, is authenticated, and a duplicate trigger is provably a no-op.

---

## M25 · Ingestion worker

**Purpose.** Keep the corpus minutes-fresh from live public sources, without blocking any user
request.

**Depends on:** M09, M16, M22, M24, M26.

**Responsibilities**
- Per tick, select a bounded number of due feeds — a small batch, not the whole registry.
- Conditional fetching using entity tags and modification times; skip unchanged feeds.
- Canonicalise URLs, discard already-seen content hashes.
- Extract title, date, publisher, links, images and body excerpt for each new item.
- Create claims with source anchors, compute lexical, similarity-hash and embedding representations.
- Assign origin clusters and record discovered fact-check or source links.
- Write source snapshots, claims, observations and a feed-run record with status and cursor.
- Set the next fetch time with per-domain backoff, and record every failure with its reason.

**Must not**
- Block a user verification. Ingestion is for freshness and breadth; a user-supplied URL is fetched
  immediately on the request path regardless of corpus state.
- Create trusted evidence directly. An ingested item becomes usable evidence only when the same
  validators that judge a user request accept it.
- Republish full article text.

**Failure behaviour.** A feed failure is recorded and retried with backoff; it never fails the tick.

**Done when**
- A tick is idempotent under retry, resumes from its cursor, and the corpus can be rebuilt
  deterministically from recorded feed snapshots.

---

## M26 · Origin clustering

**Purpose.** Count independent sources, not articles. Without this, corroboration is theatre.

**Depends on:** M22, M25.

**Responsibilities**
- Similarity-hash shingles over normalised text to detect near-duplicate coverage.
- Cluster assignment with a canonical publisher and first-seen time per cluster.
- Store the signals that make independence judgeable: normalised shingles, named entities and dates,
  quoted-source relationships, canonical URL and publisher.
- Expose a count of distinct origins, not a count of matching documents.
- Threshold calibration against real observed duplicates and real distinct reporting.

**Must not**
- Report an article count where an origin count is required.

**Done when**
- **At least one multi-outlet cluster exists in the live corpus** — a real wire story carried by two
  or more allowlisted outlets, correctly collapsed to one origin. This is a hard gate; if it has not
  fired, the threshold is mistuned or the feed mix is too narrow, and both are cheap to fix now and
  expensive to discover during evaluation.

---

# Track H — Evidence retrieval

## M27 · Fact-check retrieval

**Purpose.** The strongest and cheapest evidence class — someone has already adjudicated this claim.

**Depends on:** M13, M14, M22, M28.

**Responsibilities**
- Query the external fact-check API by claim text and, where a public source image URL already
  exists, by image.
- Query the local corpus of previously-retrieved fact-check records in parallel.
- Persist every live response with its retrieval timestamp; those persisted live responses are the
  fallback when the external API is unavailable.
- Require claim similarity, publisher, rating, URL and a source snapshot before a result becomes
  decisive evidence.

**Must not**
- Use image search in a way that requires making a private user upload public.
- Treat a low-similarity match as decisive.

**Failure behaviour.** External unavailability falls back to persisted live responses; if neither
resolves, the claim continues to other checks.

**Done when**
- A known fact-checked claim resolves with a citation, publisher and rating **while the external API
  is disabled**, using only previously-retrieved live records.

---

## M28 · Source resolver framework

**Purpose.** The single mechanism by which "check the official source" happens. Every evidence
producer implements this shape.

**Depends on:** M09, M11, M13, M14.

**Responsibilities**
- Three stages per resolver: propose candidates for a claim, snapshot a candidate, and relate the
  snapshot to the claim.
- Each resolver declares its allowed domains, retrieval method, rate limit and validator version.
- The relate stage may use structured extraction or a bounded model proposal, but **must return the
  exact source excerpt and its anchor**. A model statement that a page supports a claim is not
  evidence.
- Every relation is labelled with one of the fixed relation values.
- The launch set of resolvers: fact-check search, the live corpus, user-supplied cited URLs, and a
  small allowlist of official domains.

**Must not**
- Crawl the open web unrestricted.
- Emit an evidence object without excerpt, anchor and snapshot.
- Let a general web search be the sole basis for a verdict — search is candidate generation only.

**Failure behaviour.** If a source cannot be located, fetched, anchored and cited, the relation is
`INSUFFICIENT` and the claim remains `UNVERIFIED`. That is a correct outcome, not a failure to fix.

**Done when**
- A claim naming an official body resolves to that body's own page with an anchored excerpt, and a
  claim naming a body with no matching statement produces `INSUFFICIENT` rather than a guess.

---

## M29 · Attribution and quote checks

**Purpose.** The two deterministic killers. Fabricated articles borrow authority they do not have.

**Depends on:** M28.

**Responsibilities**
- **Attribution:** when a claim cites a source — an agency, a regulator, a ministry, a scientific
  body — fetch that source and check whether it carries the claimed announcement, number, quote or
  date. A citation is not accepted merely because it was asserted.
- **Quote:** search exact and normalised variants of a quoted statement; compare speaker, date,
  language and context. Famous fabricated quotes are usually already fact-checked; novel ones
  appearing only on low-credibility sites inherit that as context.
- Both produce citable negative evidence when the cited source does not carry the claim — which is
  often the single most decisive finding available.

**Must not**
- Treat absence of a claim on a cited source as proof the claim is false in general — it is proof
  the *attribution* is false, which is a different and narrower finding.

**Done when**
- A real published case of fabricated attribution produces a citable negative finding against the
  named source.

---

## M30 · Corroboration

**Purpose.** How many genuinely independent sources carry this, and what does silence mean here.

**Depends on:** M22, M26, M28.

**Responsibilities**
- Retrieve related coverage from the live corpus using hybrid lexical and embedding search.
- Cluster results and count **distinct origins**.
- Interpret silence using the coverage expectation captured at extraction: a claim that would be
  national news if true, absent from the whole corpus, is meaningful negative evidence; a local or
  minor claim absent from national feeds means nothing at all.
- Respect the developing-news window: for a recently-asserted event, corpus silence is ambiguous and
  must produce abstention with a re-check recommendation, never a contradiction.
- Surface both numbers to the interface — documents and origins — so the distinction is visible.

**Must not**
- Produce a contradiction from silence alone under any circumstances.
- Count syndicated reprints as independent confirmations.

**Done when**
- A high-expectation fabricated claim yields negative corroboration evidence with an origin count,
  and a genuinely local claim with no coverage yields nothing rather than a negative.

---

## M31 · Temporal and dating

**Purpose.** Establish when something first existed. This is what catches recycling and backdating.

**Depends on:** M09, M16, M28.

**Responsibilities**
- Primary dating: the publish dates of matched pages themselves, extracted at fetch time from
  structured metadata and byline patterns. This is free, fast and carries the common case.
- Compare the asserted date against the oldest credible instance found.
- Compare the page's stated date against its own structural signals for backdating.
- Archive capture lookup is **additive confirmation only**, used when a verdict genuinely hinges on a
  contested date. It is optional, timeout-bounded, and no gate depends on it.
- Produce the context-mismatch finding that drives `MISLEADING_CONTEXT`.

**Must not**
- Make the flagship path depend on the archive service.
- Treat a page's own timestamp as authoritative — it is editable by the adversary.

**Done when**
- The "real image, wrong context" case resolves **from matched-page publish dates alone**, with the
  archive lookup disabled.

---

## M32 · Source risk track

**Purpose.** Say what is known about the publisher — running in parallel with, and strictly separate
from, the claim track.

**Depends on:** M09, M16.

**Responsibilities**
- Domain registration age where available.
- Transparency structure: contact and about pages, named authors, editorial policy, mail
  authentication records.
- Typosquat candidacy against the allowlisted credible-domain list.
- Recorded injection attempts from M11 as a deception signal.
- Produce a source-risk level with the specific signals that produced it, each independently
  displayable.

**Must not**
- Contribute to a claim status. Source risk is context; it never makes a claim false.
- Produce `DO_NOT_SHARE` on its own — its ceiling is abstention plus review.

**Done when**
- A newly-registered opaque domain produces `HIGH` risk with itemised signals, and that alone changes
  no claim status anywhere in the output.

---

# Track I — Media

## M33 · Media hashing and local matching

**Purpose.** Stage one of media verification — free, fast, and correct for repeat content.

**Depends on:** M03, M23.

**Responsibilities**
- Exact identity by cryptographic hash.
- Perceptual hash search over the fingerprint store for near-duplicate candidates.
- **Every candidate is verified by image embedding before it can become evidence.** A 64-bit
  perceptual hash is a candidate generator; it collides, and a false media match is the worst
  possible failure because it produces a confident, cited, wrong answer.
- A conservative threshold, calibrated against real matches and logged near-misses, owned by this
  module.
- Record every match attempt as an observation, including misses — the near-miss log is what makes
  threshold calibration possible.

**Must not**
- Emit a match on hash distance alone.
- Loosen the threshold to make a demo case work.

**Done when**
- A known recycled image matches its stored original, and a visually similar but distinct image
  produces **no** match. Both are asserted by tests.

---

## M34 · Reverse-image discovery

**Purpose.** Stage two — the only path to media older than the corpus. Without it the flagship case
cannot resolve, because a corpus built over fifteen days contains no imagery from years earlier.

**Depends on:** M09, M14, M31, M33.

**Responsibilities**
- Runs **only on local miss**, and only within its daily budget under the governor.
- Submit the image as raw bytes to the web-detection provider and receive matching page URLs.
- **Discovery and dating are separate steps.** The provider returns URLs, titles and scores — not
  publication dates. Every matched page is then fetched through the secure fetcher, and its own
  publish date, publisher and anchored excerpt are extracted. The matched page is the citation.
- Rank and select which matched pages are worth fetching, since the fetch budget is also finite.
- Write every resolved match back to the fingerprint store, so the second person to share the same
  image resolves for free.

**Must not**
- Be called before the local stage, on cached content, or past its budget.
- Require making a user's private upload publicly accessible.
- Treat a provider result as evidence without fetching and anchoring the underlying page.

**Failure behaviour.** Budget exhaustion or provider failure records "capacity limited" and the case
abstains on the media question.

**Done when**
- A genuinely old image, absent from the local corpus, resolves to a dated original with a citation
  and an anchored excerpt — and the same image submitted again performs zero external calls.

---

## M35 · Video keyframe path

**Purpose.** Verify video context without downloading, storing or analysing whole videos.

**Depends on:** M10, M18, M33, M34.

**Responsibilities**
- Validate and cap the upload by duration, size and resolution before any decode.
- Extract a small bounded set of scene-change keyframes.
- Run each keyframe through the full image path — hash, embedding verification, then reverse-image
  discovery on miss.
- OCR the frames and route the text into the claim pipeline.
- Carry frame timestamps into claim and evidence anchors so a finding points at a moment in the clip.
- Return context and provenance results first; forensic advisory last.
- Long jobs return an accepted-with-progress response and complete asynchronously.
- Transcription is added only after the core path is green, and only when audio is needed for a
  claim.

**Must not**
- Promise resolution of arbitrary platform video URLs.
- Retain raw video beyond its short retention window.

**Done when**
- One real recycled-video case resolves to a dated source through keyframes, and one genuinely
  inconclusive case abstains.

---

## M36 · Provenance verification *(P1)*

**Purpose.** Read content credentials where they exist, and say honestly that they usually do not.

**Depends on:** M10.

**Responsibilities**
- Parse and validate content credentials locally; report manifest presence, validation result, signer
  identity, creation and edit assertions, and the ingredient chain.
- Report absence as unknown and continue with source and context analysis.

**Must not**
- Treat a missing manifest as evidence of fakery.
- Treat a valid manifest as evidence that the depicted event is true — it binds an assertion to an
  asset, nothing more.
- Occupy build time on the critical path. Platforms strip these credentials during reprocessing and a
  screenshot severs the binding entirely, so on the dominant demo inputs this returns unknown.

**Done when**
- A real credentialed asset validates and displays; every other input reports unknown without
  affecting the verdict.

---

## M37 · Forensic advisory panel

**Purpose.** The visible forensic surface the problem statement expects, wired so it cannot decide
anything.

**Depends on:** M05, M23, M35.

**Responsibilities**
- Noise-inconsistency analysis over the image or keyframes, with a renderable map.
- A frequency-domain view of the power spectrum, renderable.
- Optionally, one pretrained open-weight detector running on CPU.
- All three emit **advisory objects only**, and all three render under a permanently visible header
  stating they are not used in the verdict.
- Record the detector's dataset, threshold and known out-of-distribution behaviour separately from
  any product metric.

**Must not**
- Emit an evidence object. Ever.
- Use error-level analysis. It false-positives on recolouring, brightness adjustment, in-camera
  processing, resampling and **screenshots** — which is precisely the input distribution here — and
  it cannot distinguish an edit from naturally high-frequency content such as text and sharp edges.
  A persuasive-looking heatmap that is not diagnostic reintroduces the confident-wrong-answer
  failure through the interface after the architecture excluded it from the engine.
- Have its output quoted as a product accuracy figure anywhere.

**Done when**
- The panel renders on a real video case, the deletion test still passes, and disabling the whole
  module changes no verdict and no strength score.

---

# Track J — Evidence graph

## M38 · Observation recording and promotion

**Purpose.** Grow the corpus from usage without letting usage poison it.

**Depends on:** M03, M06.

**Responsibilities**
- Every request writes an observation, regardless of outcome.
- Observations carry a trust state and are **not** evidence.
- Only a validated match or a reviewed finding is promoted into the trusted fingerprint, occurrence
  and cluster stores.
- Promotion updates the times-seen counter, the first- and last-verified timestamps, and the last
  verdict for that fingerprint.

**Must not**
- Promote on repetition alone. A raw user submission does not become trusted evidence because it was
  submitted many times — that is the obvious attack on a recurrence counter.

**Done when**
- Repeatedly submitting the same unverified content increments observations and **does not** move any
  trusted counter.

---

## M39 · Recurrence and caption variants

**Purpose.** The "identify misinformation patterns" deliverable, and one of the strongest demo beats.

**Depends on:** M38.

**Responsibilities**
- Given a fingerprint, report how many times it has been verified and when it was first seen.
- Given a fingerprint, list the distinct captions and claims attached to it over time, with their
  dates and source domains — one image, several contradictory narratives, across languages.
- Both are queries over the write-back stores, not new pipelines.

**Must not**
- Count unpromoted observations in a user-facing recurrence figure.

**Done when**
- A repeatedly-verified image shows a truthful times-seen and first-seen line, and an image with
  multiple recorded captions renders the contradictory-caption view.

---

# Track K — Orchestration and API

## M40 · Verification orchestrator

**Purpose.** The request pipeline that sequences everything, enforces order, and assembles the
ledger.

**Depends on:** every retrieval and media module, M06, M07, M13, M14.

**Responsibilities**
- Enforce the fixed order: validate → create case → hash → **cache probe** → **governor** → extract
  claims and media candidates → retrieve evidence → decide → persist ledger → write back → respond.
- Run independent evidence producers concurrently, bounded by the governor's concurrency ceiling.
- Assemble the evidence ledger and the separate advisory list.
- Call the verdict engine and the strength calculation, never bypassing either.
- Persist verdicts with their rule version, then write back through M38.
- Return within the synchronous latency target for text, URL, image and PDF; return accepted-with-
  progress for video.
- Attach the provider-skip reasons so the response can honestly say what was not checked.

**Must not**
- Call an external provider before the cache probe or outside the governor.
- Assemble a response from partial results without recording what was missing.

**Done when**
- A full verification runs end to end within the latency target, and a run with every optional
  provider disabled still produces a complete, honest, abstaining response.

---

## M41 · Public API

**Purpose.** The contract both clients consume, frozen early so client work can proceed in parallel.

**Depends on:** M40.

**Responsibilities**
- The endpoint set from `codexplan.md` §12: verify, verify-file, case retrieval, case evidence
  retrieval, receipt retrieval, the scheduler-authenticated internal ingestion trigger, and health.
- Response carries: case identifier, overall action, per-claim entries with status, severity,
  importance, reason, strength with components, and evidence with citation, snapshot reference,
  excerpt, source anchor and input anchor; plus media provenance, source risk, the advisory list, and
  the receipt link.
- Generated interface documentation published from the contract, not written by hand.
- The internal ingestion endpoint is authenticated and never publicly routable.

**Must not**
- Return an advisory value inside the evidence list.
- Return a decisive status without evidence.
- Change shape after Day 1 without a versioned contract change, because the mobile client is being
  built against it in parallel.

**Done when**
- The contract is frozen, published, and a client can be built against it before the pipeline is
  complete.

---

## M42 · Result receipt

**Purpose.** Tamper-evidence — a verifiable record of what was attested, on what evidence, when.

**Depends on:** M40.

**Responsibilities**
- Canonicalise the evidence digest for a case and sign it with a development key.
- A public verification view that shows what was attested and when.
- Content-addressed identifiers so a receipt cannot silently point at different content.

**Must not**
- Be described as a legal certificate, a compliance artifact, or a tamper-proof archive. It is a
  tamper-evident result receipt.

**Done when**
- A receipt verifies, and altering any stored evidence row makes verification fail.

---

## M43 · Human review queue

**Purpose.** The designed destination for the cases the system correctly refuses to decide.

**Depends on:** M03, M40.

**Responsibilities**
- Cases routed to review land in a queue with their reason.
- A reviewer records a human label **beside** the machine output.
- Reviewed findings become eligible for promotion into the trusted graph (M38).

**Must not**
- Overwrite the machine verdict with the human one. Both are recorded.

**Done when**
- An abstaining case appears in the queue with its reason, and a recorded human label is visible
  alongside the original output.

---

# Track L — Clients

## M44 · Android application

**Purpose.** The judged surface. Start it early — it needs only the frozen contract, not the
pipeline.

**Depends on:** M41 (contract only).

**Responsibilities — phase one, early**
- Project scaffold, share-target intake for text, URL and file, and a screen that submits and renders
  the raw response. No design work.

**Responsibilities — phase two, later**
- Minimal permissions — share-sheet intake needs no storage permission and manual selection uses the
  system picker.
- Upload progress and result polling for asynchronous cases.
- The result card: status, one-line explanation, the reasons, and three actions — see evidence, share
  correction, report for review.
- The evidence screen: extracted claim with its anchor, timeline, source cards with publisher, date
  and URL, media match preview, the recurrence line, the "what Facify cannot establish" block, and a
  language toggle.
- The advisory panel, greyed, under its permanent exclusion header.
- A shareable correction card that returns to the group the content came from.

**Must not**
- Contain any secret or provider credential.
- Show an advisory signal in a way that reads as part of the verdict.

**Done when**
- Content shared from a messaging app, a browser and the gallery all reach a rendered verdict, in
  both supported languages.

---

## M45 · Web evidence console

**Purpose.** The reviewer and newsroom surface, and the proof that the same engine serves more than
one client.

**Depends on:** M41.

**Responsibilities**
- Claim list with per-claim status and anchors.
- Evidence cards with publisher, date, excerpt and link.
- Timeline view of dates and instances.
- Source-risk panel with itemised signals.
- Recurrence card and contradictory-caption list.
- Advisory panel, visibly excluded.
- A simple queue view over cases routed to review.

**Must not**
- Query the database directly. It is an API consumer — that is what proves the API is complete.

**Done when**
- A complete explanation for any case is readable without opening logs or the database.

---

# Track M — Evaluation and operations

## M46 · Live audit manifest and harness

**Purpose.** The answer to "how do you know it works" that is not the demo.

**Depends on:** M40.

**Responsibilities**
- A manifest of real public URLs, real public media and real fact-check pages, collected during
  operation, each with its retrieval timestamp, snapshot hash, expected relationship and reviewer
  label.
- Category coverage across genuine content, fact-checked matches, recycled media, fabricated
  attribution, official-document claims, developing claims, provenance examples and adversarial
  input.
- **A hard floor of at least 35 genuine-content items.** Below that the false-positive rate is not
  reportable: with a handful of items the only observable rates are far apart, a single failure
  already exceeds the target, and the measurement cannot distinguish a safe system from an unsafe
  one. Genuine articles are the cheapest items to collect, so this costs collection time, not build
  time.
- Report precision on the two decisive statuses, false-positive rate on genuine content **with its
  sample size shown**, citation coverage across all decisive results, abstention rate, latency by
  input type, provider failure rate, and a human review of bilingual explanation quality.
- Report over the whole manifest, never a demo subset.
- Every run is stamped with a timestamp and pinned to a snapshot set, so successive runs are
  comparable and a judge can be shown exactly what was retrieved and when.
- Publish the report as a document regenerated by the harness.

**Must not**
- Substitute hand-authored evidence when a live source changes, disappears or rate-limits. That is
  recorded as a failure and the item abstains.
- Minimise the abstention rate. It is reported, not optimised — a falling abstention rate means the
  system has stopped refusing, which is the opposite of the design intent.

**Done when**
- The full manifest runs, the report generates, and the genuine-content floor is met.

---

## M47 · Snapshot-replay test infrastructure

**Purpose.** Deterministic CI over live-sourced data.

**Depends on:** M03, M09.

**Responsibilities**
- Tests execute against stored source snapshots — real bytes fetched from real URLs at a recorded
  time — rather than re-fetching.
- Recording mode captures new snapshots; replay mode is the default and the only mode CI uses.
- Live retrieval is exercised by the ingestion worker and the audit run, not by unit tests.

**Must not**
- Fetch live URLs in CI. A publisher editing a page is a flake, not a finding.

**Done when**
- The full suite passes with networking disabled.

---

## M48 · Pre-warm and offline demo path

**Purpose.** Demo survival. A system that can only answer while every provider is reachable fails on
venue wifi.

**Depends on:** M13, M40.

**Responsibilities**
- Execute the demo set through the **live** pipeline against **live** sources ahead of time, so the
  cache holds real verdicts computed from real evidence.
- Serve from cache when providers are unreachable, with the retrieval timestamp visible in the
  interface.
- A rehearsal procedure that runs the full demo with outbound network disabled.

**Must not**
- Hand-author a cached result. Pre-warming means running the real pipeline early, not writing an
  answer.
- Hide that a result came from cache. The timestamp is shown.

**Done when**
- The complete demo sequence runs end to end with outbound network disabled, and every served result
  displays its retrieval time.

---

## M49 · Deployment and runtime sizing

**Purpose.** Run the thing, at the right size, in the right place.

**Depends on:** M01, M02.

**Responsibilities**
- One container serving the API and the console, sized for the real workload: the default small
  memory allocation will exhaust memory once image processing and two local models are loaded.
- A minimum warm instance during judging, because loading local models on a scale-to-zero container
  makes the first request slow — which collides directly with the synchronous latency target.
- Ingestion runs as a separate short-lived job that exits after each batch, never inside the web
  process.
- Region choice recorded as a deliberate decision with its cost consequence, rather than assumed.
- Dependency and model identifiers frozen before demo day.

**Done when**
- A cold deployment serves a real verification within the latency target, and ingestion runs on
  schedule as a separate job.

---

# Build order

**Week one — foundation and core**

| Sequence | Modules | Notes |
|---|---|---|
| Before the sprint | M24 registry population, credential and quota verification, manifest collection start | External, parallelisable, blocks nothing but gates everything later |
| 1 | M01 · M02 · M05 | M05 needs nothing; start it immediately |
| 2 | M03 · M06 · M07 | Core and persistence in parallel — different people, no coupling |
| 3 | M04 · M08 · M44 phase one | The Android shell needs only the frozen contract |
| 4 | M09 · M10 · M11 · M13 · M14 | Safety and cost control before any provider is wired |
| 5 | M19 · M20 · M21 · M22 | The text path becomes real |
| 6 | M27 · M28 · M25 · M26 | Knowledge plane and first evidence class |

**Week two — evidence, media, clients**

| Sequence | Modules | Notes |
|---|---|---|
| 7 | M16 · M29 · M32 | The URL path and the two deterministic killers |
| 8 | M17 · M18 · M23 · M33 · M38 | Image and document paths; write-back live from the first match |
| 9 | M31 · M34 · M39 | The flagship case becomes resolvable |
| 10 | M35 | Video, bounded |
| 11 | M44 phase two | Result experience, on a shell that already exists |
| 12 | M45 · M42 | Console and receipt |
| 13 | M46 · M47 · M12 · M43 | Evaluation, red team, review queue |
| 14 | M41 documentation · M39 views · M37 | Platform surface and the forensic panel |
| 15 | M48 · M49 freeze | Pre-warm, rehearse, freeze |

**P1, only after the above is reliable:** M36 provenance, transcription within M35, archive
confirmation within M31, the open-weight detector within M37, receipt signing hardening, API key
authentication.

---

# The gates that actually block

These are the checks that stop the build if unmet. Everything else is progress; these are pass/fail.

| Gate | Module | Why it blocks |
|---|---|---|
| Verdicts compute with no model, network or database | M06 | If the core is not pure, nothing downstream is trustworthy |
| Deletion test green in CI | M08 | The single differentiating claim of the product |
| No decisive verdict with empty evidence | M08 | The design law, mechanically enforced |
| SSRF fixture suite passes, including mid-redirect pivot | M09 | The service fetches attacker-chosen URLs from inside the network |
| Every cap at zero produces a complete honest run | M14 | Proves graceful degradation before it is needed live |
| At least one multi-outlet origin cluster in the live corpus | M26 | The flagship correctness rule needs something real to demonstrate |
| Fact-checked case resolves with the external API disabled | M27 | Proves the fallback, which will be needed |
| Near-miss image produces no match | M33 | A false media match is a confident, cited, wrong answer |
| Flagship case resolves from matched-page dates with archive disabled | M31 · M34 | Removes an external single point of failure from the demo |
| Repeated unverified submission moves no trusted counter | M38 | The obvious attack on the recurrence counter |
| ≥ 35 genuine-content items before the false-positive figure is reported | M46 | Below this the safety metric is unmeasurable |
| Full demo runs with outbound network disabled | M48 | Venue wifi is a when, not an if |

---

# Failure modes to watch for during the build

| Symptom | What it actually means | Correct response |
|---|---|---|
| A module needs "just one" direct external call | The governor is being bypassed | Route it through M14 |
| A stub returns a plausible answer during development | Fabricated evidence has entered the system | Stubs return nothing; the pipeline abstains |
| A threshold is loosened to make a demo case pass | The matcher is being tuned to the demo, not to reality | Revert; log the near-miss; fix the candidate stage |
| An evidence object appears without an excerpt | A search result is being treated as evidence | Fetch and anchor the page, or return `INSUFFICIENT` |
| Model latency dominates the request | More than one extraction call per document | Batch into the single structured call |
| Ingestion starts consuming model quota | An embedding API crept in | Local ONNX only |
| CI goes red on an unrelated publisher change | Tests are fetching live | Move to snapshot replay |
| The advisory panel starts influencing a status | The two types have been merged somewhere | The deletion test will catch it; treat as a build break |

---

# Definition of done for the whole build

A person can share, from a messaging app, a browser or the gallery:

- a real but miscaptioned image,
- a misleading or forged PDF with a verifiable cited contradiction,
- a public article link containing several mixed claims,
- a known fact-checked claim,
- a genuine article,
- a genuinely novel claim,

and receive fast, cited, claim-level, bilingual results with anchors back to the exact paragraph or
frame — abstaining correctly on the last one. At least one live feed item has entered the corpus
through scheduled ingestion and later contributed to a user verification. The evaluation report is
published with its sample sizes shown. And the whole sequence runs with the network disabled.
