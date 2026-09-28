# API contract changelog

The shape both clients read is defined in `app/api/schemas.py` and versioned by
`CONTRACT_VERSION`. Every change so far is additive: a field is added, optional, and
nothing that was there changes name, type or meaning. A client built against an older
version keeps working and simply does not show the new fields.

## 1.3, addition (2026-09-28): languages

- **`claims[].language`**: the language the claim was made in - `en`, `hi`, or one of
  `bn mr te ta gu ur kn or ml pa`. Its `explanation` is written in that language.
- **`POST /v1/cases/{id}/correction-text`** accepts the same twelve codes.

## 1.3, addition (2026-09-28)

Our own detectors replace the hosted one. All new fields are optional.

- **`media_report.detector.second_opinion`**: a second AI-picture model's likelihood
  (DDA), 0-1. Off by default, so usually absent.
- **`media_report.detector.agreement`**: `likely_ai` when every AI-picture model
  agrees, `unclear` when they disagree, `no_sign` when none is raised. Never "real".
- **`media_report.detector.faces`**: how many faces the face-swap model judged;
  absent when the face check did not run. `face_swap` is its highest likelihood.
- **`media_report.detector.voice`**: for a video, the likelihood that the speech was
  made by a speech generator. Experimental.
- **`media_report.detector.on_server`**: `true` when these detectors ran on our own
  server. It says nothing about other checks: the hosted reader may still read the
  picture's text, and reverse image search sends it to its provider.

## 1.3 (2026-09-27)

Added for the v5 app.

- **`claims[].input_anchor`** `{char_start, char_end, page_number, frame_start_ms}`:
  where the claim sits in what was submitted, so the app underlines the words
  themselves. For text, the offsets are into the text exactly as sent - line breaks,
  double spaces and curly quotes included. For a link, a picture or a PDF they are
  into the text read from it. `null` when the claim was never located to a character
  range. The per-evidence `input_anchor` is unchanged.
- **`claims[].technique`**: one of `RECYCLED_MEDIA`, `MISSING_CONTEXT`,
  `MISATTRIBUTED_QUOTE`, `TWISTED_NUMBER`, `WRONG_IDENTITY`, or `null`. How a false or
  misleading claim misleads, for the lesson the app shows beside it. Only ever set on
  a `CONTRADICTED` or `MISLEADING_CONTEXT` claim; the contract refuses it on any other.
  Derived from the decision already made (status, claim type, evidence kind -
  `app/verdict/technique.py`); it never changes a status or a confidence.
- **`receipt`** `{receipt_id, verified, issued_at}`: the result's receipt, checked
  against the stored evidence as the result was sent, so the seal shows without a
  second call. `null` when no receipt was issued. `receipt_url` and
  `GET /v1/receipts/{id}` are unchanged.
- **Progress events.** `GET /v1/cases/{key}/events` (Server-Sent Events) and
  `GET /v1/cases/{key}/progress?after=n` (polling) report a check as it runs:
  `step {step: read|search|compare}`, `source_started {publisher, domain, initials}`,
  `source_done {publisher, domain, outcome: evidence|not_relevant}`,
  `evidence_count {n}`, then `done {case_id}` or `error {code}`. Every event has a
  `seq`; a reconnect with `Last-Event-ID` resumes after it. `key` is the
  `X-Request-ID` (a UUID) the app sent with `/v1/verify` or `/v1/verify/file`, so it
  can listen before the answer returns, or a deep check's case id from its 202.
  A source counted as evidence and then thrown out by the source check is sent again
  as `not_relevant`, so the final count is the count of cited sources. Events carry
  no submitted content, claim or page address, and are forgotten ten minutes after
  the check ends. Setting `FACTIFY_PROGRESS_REDIS_URL` carries them between
  instances (needs the optional `redis` package).
- **`request_id`** on the result: the `X-Request-ID` the app sent, echoed.
- **`media_report`** for an uploaded picture or video: the checks of the upload
  itself, beside the verdict and never inside it. `credentials` (C2PA: `valid`,
  `untrusted`, `invalid`, `none`, `unavailable`, plus `declares_ai` when the file
  itself says an AI tool made it), `history` (reverse image search: `found` with
  the earliest dated appearance and `days_before`, `none`, `not_checked`; the
  earlier copy's `thumbnail_url` is served from `GET /v1/media/thumbnails/{key}`,
  never the third party), `detector` (an AI-image and face-swap detector's
  likelihoods, 0-1, advisory), `editing` (noise and spectrum signals, advisory), and
  for a video the number of still `frames` checked. The detector and editing
  signals also arrive as `advisories`. A video upload is now checked (202, then
  `/v1/cases/{id}`) instead of being recorded as unprocessed.
- **`GET /v1/cases/{case_id}/sources/{evidence_id}`** (the source reader): a cited
  passage in its article - the quoted paragraph and one either side, never the
  whole article - with `headline`, `published_at`, `read_minutes`, `image_url`
  (served from our own address), `quote` (its paragraph and characters), and the
  citation's `tier`, `direction`, `credibility` and `match_basis`. The server
  fetches the page through the SSRF-guarded client and cleans its text; `complete`
  is false, with `limitations` saying why, when the page will not open or no longer
  carries the quote. A fresh result's evidence ids differ from the stored ones, so
  `?url=` finds the citation by its page.
- **`claims[].evidence[].published_on`** and **`title`**: the cited page's own
  publication date and headline, when known. `observed_at` is when we fetched the
  page and was being shown as if it were the article's date. Cases stored before
  this carry no `published_on`.
- **`claims[].evidence[].earlier_media`** `{thumbnail_url, published_at, publisher,
  similarity}` on a `media_match` citation: the earlier copy of the picture, for the
  side-by-side on a Misleading answer. `similarity` is the match value (0-1).
  `thumbnail_url` is on our own address, and only on a fresh result whose picture
  checks fetched the same page; the upload is never kept, so a stored case has none.
- **`POST /v1/cases/{case_id}/correction-text`** `{"language": "en" | "hi"}` →
  `{"message", "links"}`: a short, polite message to send back to the chat, built
  from the stored answer by template (no model). A decided verdict always names its
  deciding source with the link; Unconfirmed never says false and names none. The
  Hindi message leaves out the English summary. The app lets the person edit it.

## 1.2

- **`image_reading`** `{text, description, kind, publisher, language}`: what was
  read from an uploaded picture.

## 1.1

- **`verdict`**, **`confidence`**, **`summary`** on the result; per-claim
  **`confidence`** and **`explanation`**; per-source **`credibility`**.
