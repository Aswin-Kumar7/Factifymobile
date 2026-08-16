# Facify

**Proof, not opinion.** Evidence-based content verification for India's information ecosystem.

Share any post, link, image, PDF or short video from any app → get a cited, claim-level verdict in
your language. Verdicts are computed from **citable evidence** — provenance, dated sources,
published fact-checks, corroboration — never from a model's confidence score. AI reads and writes;
it does not decide.

Built for the **ZeAI #MadeInIndia Hackathon 2026** · Problem statement **ZAIML-005** (Fake News &
Deepfake Detection Platform) · designed as the seed of a B2B verification platform.

---

## The design law

> **Verdicts come only from citable evidence (Tiers A–D). Model scores are advisory (Tier E): they
> may raise suspicion, never establish authenticity, never decide alone. No citation → no verdict →
> `UNVERIFIED`.**

Enforced in three places, not by review discipline:

- **Type level** — `decide()` accepts validated evidence objects only; advisory signals are a
  different type and are not in the signature.
- **CI** — a test asserts that disabling every Tier E provider leaves verdicts byte-identical.
- **CI** — no verdict may serialize as anything other than `UNVERIFIED` with empty `evidence[]`.

## Why not a probability score

The brief invites a classifier: upload media, receive a fake percentage. Five prior open-source
builds in this space each document why that fails — text classifiers learn writing style, video CNNs
learn their training generators, LLMs emit fluent unfalsifiable confidence. None learns truth.

And the dominant Indian format is not a deepfake at all: it is real footage under a false caption, a
2019 photograph presented as today, a genuine article with names swapped, a forged circular as a
PDF. A perfect deepfake detector scores zero on all of it.

Facify ships a **scored explanation** rather than an explained score: strength is computed in Python
from tier composition, independent-origin count, source credibility and temporal confidence, with
every term linked to the citation that produced it, and the forensic panel displayed **greyed and
labelled "not used in this verdict."**

## What it does and does not answer

| Question | Answerable? | By |
|---|---|---|
| Is this recycled or misattributed? | ✅ | Fingerprint + reverse-image discovery → dated source |
| Has this claim already been fact-checked? | ✅ | ClaimReview / Fact Check Tools match |
| Was this fabricated at national scale? | ✅ | Significance-weighted silence + source risk |
| Is the cited source real, and does it say this? | ✅ | Attribution and quote checks |
| Is this AI-generated with a valid manifest? | ✅ | C2PA — provenance only, never factual truth |
| Is this AI-generated without one? | ⚠️ Suspicion only | Advisory; may escalate, never establish |
| Is this novel local claim true? | ❌ **Honestly no** | `UNVERIFIED` → human review. The failure mode is designed, not hidden |

---

## Documents

| File | What it is |
|---|---|
| **[codexplan.md](codexplan.md)** | ⭐ **Start here.** The 15-day execution plan: trust model, evidence contract, architecture, data model, day-by-day build, evaluation gates, and the startup case |
| [technical_plan.md](technical_plan.md) | The full platform architecture beyond the hackathon — signal providers, budget planner, attestations, transparency log, and the metered B2B API (keys, scopes, metering, webhooks, BYOK, tenancy) |
| [dump/](dump/) | Superseded planning documents, kept for provenance |

`codexplan.md` is the operational source of truth. Where the two disagree on scope, `codexplan.md`
wins for the 15-day build and `technical_plan.md` describes where it grows.

## Status

Planning. Committed code from earlier iterations (verdict engine, URL resolvers, quota governor,
language detection, corroboration) is in git history at `1fbb6a0` and earlier; the working tree is
being restructured around the plan above.

## Stack

FastAPI / Python 3.12 · Supabase Postgres + pgvector · Cloud Run · Android share target ·
local CPU embeddings (ONNX) · ffmpeg · free-tier LLM for bounded extraction only.

Every external provider is governed by a daily call budget and degrades to an honest
"capacity limited" state rather than a fabricated answer.

## Ground rules

- Public content only. No authenticated scraping, no paywall or login-wall bypass, no DRM.
- Fetched pages, OCR output and PDFs are hostile input: SSRF-guarded retrieval, prompt-injection
  sanitization, and an injection attempt recorded as evidence of deception.
- Source risk is never proof that a particular claim is false, and never on its own grounds to tell
  a user not to share something.
- No statistic without a citation — including in the pitch.
