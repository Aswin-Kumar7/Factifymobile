# Factify

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

Factify ships a **scored explanation** rather than an explained score: strength is computed in Python
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

## What is in this repository

| Path | What it is |
|---|---|
| [app/](app/) | The API (FastAPI, Python 3.12): intake, claim extraction, retrieval, evidence verification, the verdict engine, media checks, accounts, organisations, plans and billing |
| [web/](web/) | The website (Next.js 15): landing page, the dashboard for checks, history, plans and organisations, and the admin panel |
| [apps/mobile/](apps/mobile/) | The Android app (Flutter): share anything into it and get a cited verdict |
| [migrations/](migrations/) | Forward-only Postgres migrations, applied in order by `app/db/migrate.py` |
| [tests/](tests/) | `unit` (pure), `db` (needs Postgres), `replay` (stored snapshots), `live` and `model` (opt-in) |
| [deploy/](deploy/) | Docker Compose and Caddy for the one-VM deployment |
| [scripts/](scripts/) | Local server, accuracy suite, model evaluation, APK publishing |
| [docs/](docs/) | Deployment, operations notes, the API contract changelog and design records |

## Stack

FastAPI / Python 3.12 · Supabase Postgres + pgvector · Azure OpenAI for reading and writing only ·
Tavily web search over a 727-host credibility allowlist · on-server models for pictures, faces,
voice, speech (Whisper) and text in images (RapidOCR) · CPU embeddings (fastembed) · ffmpeg ·
Next.js · Flutter · Razorpay · one Azure VM behind Caddy.

Every external provider is governed by a daily call budget and degrades to an honest
"capacity limited" state rather than a fabricated answer.

## Run it locally

```bash
cp .env.example .env
uv sync
uv run python scripts/serve_local.py
```

The API listens on `http://127.0.0.1:8000`. The website and the app talk only to it:

```bash
npm --prefix web install
npm --prefix web run dev
```

```bash
cd apps/mobile && flutter run
```

## Test it

```bash
uv run ruff check . && uv run mypy app && uv run pytest
```

```bash
npm --prefix web run lint && npm --prefix web run build
```

```bash
cd apps/mobile && flutter analyze && flutter test
```

Database tests skip unless `FACTIFY_DATABASE_URL` is set; `live` and `model` tests run only when
asked for (`-m live`, `-m model`).

## Deployment

One VM runs the API, the website and Caddy for HTTPS; see
[docs/deployment-azure.md](docs/deployment-azure.md).

## Documents

| File | What it is |
|---|---|
| [codexplan.md](codexplan.md) | The original 15-day plan: trust model, evidence contract, architecture, data model and evaluation gates |
| [agent-actionplan.md](agent-actionplan.md) | The module-by-module build order derived from it |
| [docs/evidence-architecture-plan.md](docs/evidence-architecture-plan.md) | How retrieval, verification and articulation fit together |
| [docs/contract-changelog.md](docs/contract-changelog.md) | Every change to the API contract the app and website read |

## Ground rules

- Public content only. No authenticated scraping, no paywall or login-wall bypass, no DRM.
- Fetched pages, OCR output and PDFs are hostile input: SSRF-guarded retrieval, prompt-injection
  sanitization, and an injection attempt recorded as evidence of deception.
- Source risk is never proof that a particular claim is false, and never on its own grounds to tell
  a user not to share something.
- No statistic without a citation — including in the pitch.
