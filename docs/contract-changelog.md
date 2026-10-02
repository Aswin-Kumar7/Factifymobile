# API contract changelog

The shape both clients read is defined in `app/api/schemas.py` and versioned by
`CONTRACT_VERSION`. Every change up to 1.3 is additive: a field is added, optional, and
nothing that was there changes name, type or meaning. A client built against an older
version keeps working and simply does not show the new fields. 1.4 adds a value to
`verdict`; see below for how an older client reads it.

## 1.8, as served (2026-10-02): links and posts read whole, and what that changes

Still 1.8 and still additive; what the server now does with the fields below, and
three small additions. The samples in `tests/fixtures/contract/` are updated to match.

- **Social posts are read whole.** A link to an X post, an Instagram post or reel, or
  a YouTube video is read through the platform's embed addresses: the post's words,
  a quoted post, each picture (words and what it shows), the video (what is said,
  the words on its frames, what it shows) and the article it links to. `input_read`
  has `kind: "social_post"`, `platform`, `author`, `handle` and `published_at`;
  `media_report` is the first picture's or video's checks and `media_reports` the
  rest; `image_reading` and `speech` are the first picture's and video's.
- **YouTube** is read from its title and channel, its description and captions, and
  its thumbnail (labelled "Text in the video's thumbnail" and "What the video's
  thumbnail shows (described by Factify)"). The video itself is not watched on this
  server: a `video_unread` gap with `blocking: false` says so, and `limits[]` says its
  voice and face checks did not run. The verdict is not held back for that, not even
  when no claim is found in it. The thumbnail's picture checks are in `media_report`,
  but never make the verdict "AI-made" FALSE: the thumbnail is not the video.
- **A post its platform would not show** (a login page or a refusal for the server, a
  reader that failed), and that the platform never said is gone, is read as a web
  page, as every post link was before 1.8: `input_read.kind` is `"link"`, with a
  `post_unavailable` gap, `blocking: false`, saying any picture or video in it was not
  read. A post the platform says does not exist, or a story, is withheld.
- **Descriptions are checked.** `picture_description` and `video_description` parts
  are now part of the text claims are found in, under a label ending "(described by
  Factify)", so they come with `checked: true` and `char_start`/`char_end`. A
  wordless photograph's description is the exception (`checked: false`): its own
  questions are asked instead. Show a description as Factify's words, never as the
  author's.
- **No more 422 for a link or post with nothing to check.** It used to answer 422
  "no checkable claims were found on the page … Try pasting the text". Now it is a
  200 with no claims, never charged:
  - when something that could decide it was not read (a blocking gap), or nothing
    checkable was read at all, the verdict is withheld
    (`input_read.verdict_withheld: true`, `summary` the fixed withheld sentence, and a
    `claim_extraction` skipped check with `kind: "reading"`, so an older app does not
    say "Nothing to fact-check");
  - when all of it was read, `input_read.complete` is true and `summary` says there
    is nothing in it to fact-check;
  - when only something that could not decide it was missed (gaps, none blocking:
    a YouTube video not watched, a long article's tail), `complete` is false, the gaps
    are listed, and `summary` says nothing in what was read could be fact-checked.
  - The withheld sentence no longer offers "check only what it could read": with
    blocking gaps checked past (below), `accept_partial` gives a withheld answer
    exactly the same answer again. Do not offer "Check what was read" on
    `verdict_withheld` for now; offer "Paste the text" and "Upload the picture or
    video".
- **`checked_partially` without asking.** For a link or a post, a blocking gap no
  longer holds the verdict back when claims were found in what was read: the answer
  is checked on what was read, `checked_partially` is true, and the verdict is never
  `TRUE`. `accept_partial` is still accepted. An upload (picture, PDF, video) with a
  blocking gap is checked as before 1.8: the gap is said and the answer is not
  cached, `checked_partially` stays false, and the verdict may still be `TRUE` -
  whether it should be is the owner's open decision.
- **Every gap is in `skipped[]`** with `kind: "reading"`, blocking or not.
- **New gap code `page_unread`** (blocking): a submitted link whose page could not be
  read at all, not even its headline.
- **A long article** is read to 12,000 characters (it was 6,000); past that an
  `article_truncated` gap says how much was read.
- **`GET /v1/cases/{id}`'s 202 body gains `phase`**: `reading_post`,
  `reading_pictures`, `reading_video`, `finding_claims` or `checking`, or `null`
  before the check says.

## 1.8 (2026-10-02): what Factify read, and answers held back when it could not

Additive: every 1.7 field is unchanged. Sample responses for building against are in
`tests/fixtures/contract/`.

- **`input_read`** on the result: what was read from the input, part by part, and
  what could not be. `kind` (`text`, `link`, `social_post`, `image`, `pdf`, `video`),
  and for a link or post `platform` (`x`, `instagram`, `youtube`, `facebook`), `url`,
  `author`, `handle` and `published_at`.
  - `parts[]`, in the order a person meets them: `kind` (`message`, `post_text`,
    `quoted_post`, `title`, `description`, `article`, `linked_article`,
    `picture_text`, `picture_description`, `transcript`, `on_screen_text`,
    `video_description`, `document_text`), `label` ("Post by … on X, 2 Oct 2026",
    "Text in picture 1 of 2", "Said in the video"), `text`, `checked`, `route` (how
    it was read), `complete`, `note`, `media_url` (the picture it was read from, on
    `/v1/media/thumbnails/{key}`, kept for an hour: hide it on a 404), `char_start`
    and `char_end` (where the part's text sits in the text claims were found in, the
    same offsets as `claims[].input_anchor`), and for speech `seconds_read` of
    `seconds_total` and the `language` heard.
  - `checked: false` marks a part that is not in the text claims were found in. (As
    first written, every description of what a picture or video shows was such a
    part; since the same day it is checked - see "1.8, as served" above.)
  - `gaps[]`: `part`, `code`, `detail` (one English sentence, the fallback for a code
    a client does not know) and `blocking`. Codes: `headline_only`,
    `text_truncated`, `post_unavailable`, `login_required`, `not_supported`,
    `picture_unread`, `video_unread`, `speech_unread`, `cut_off`, `pages_unread`,
    `too_large`, `needs_background`, `reader_unavailable`, `page_unread` (blocking),
    and `first_picture_only`, `article_truncated`, `description_unread`,
    `linked_page_unread` (not blocking). A reader may say a gap of a blocking kind
    does not block in its case: a capped album's later pictures, a YouTube video that
    was not watched.
  - `limits[]`: limits that are not about reading, as sentences ("YouTube does not
    let Factify download the video, so its AI, face-swap and voice checks did not
    run.").
  - `complete`: true exactly when there are no gaps.
  - `verdict_withheld`: something that could decide the answer was not read (or
    nothing checkable was), so no verdict was given. `verdict` is `UNCONFIRMED`,
    `claims` is empty, and `summary` says so in a fixed sentence. Offer "Paste the
    text", "Upload the picture or video" and "Check what was read".
  - `checked_partially`: checked from what could be read, as the person asked. The
    verdict is then never `TRUE`: a case that would be is `UNCONFIRMED`
    (`WAIT_AND_RECHECK`) under the new rule `rollup.partly_read`, "What could be read
    is supported; part of the input could not be read." A contradiction or a partial
    truth still stands.
  - `null` on cases stored before it was recorded.
- **`media_reports`**: for a post with more than one picture, the picture checks of
  pictures 2 to n, in order. `media_report` stays picture 1.
- **`skipped[].kind`**: `reading` (part of the input could not be read; `input_read`
  says what), `deadline` (the check ran out of time), `provider` (an outside service
  did not answer) or `other` (the default). Show the "ran out of time" sentence only
  for `deadline`.
- **`POST /v1/verify` `accept_partial`** (default false), and the same form field on
  `POST /v1/verify/file`: "Check what was read". Resubmit a withheld answer with it
  to check what could be read.
- `rule_version` is now `2026.10.02.1`: stored answers from earlier rules are not
  served again.

## 2026-10-02: endpoints behind the dashboard and app (contract still 1.7)

The result's shape is unchanged; these are endpoints and response fields the website
and app now use.

- `DELETE /v1/me` deletes the account: 204, or 409 `owns_organisations` while the
  person is the last owner of an open organisation.
- `DELETE /v1/cases/{id}` stops a running check its starter owns: 204 (also when
  already stopped), 404, or 409 once it has its answer. A stopped check costs nothing,
  and `GET /v1/cases/{id}` then answers 410.
- A video is charged when it has its answer, not when it is accepted.
- `POST /v1/cases/{id}/report` returns the waiting report's `item_id` when the case
  was already reported.
- A cached result's `case_id` is always the stored case it came from.
- `GET /v1/sources/summary` (public): `sites` and `fact_checkers` on the trusted list.
- `GET /v1/admin/counts`, `GET /v1/admin/reviews?status=pending|reviewed` (staff).
- Invoices for every payment: `GET /v1/me/billing/plans/{id}/invoice`,
  `/v1/me/billing/bills/{id}/invoice`, and the same under `/v1/orgs/{id}/billing/`.
  `FACTIFY_BILLING__GSTIN` prints Factify's GSTIN on them when set.
- `GET /v1/orgs` and `/v1/orgs/{id}` gain `month` (what the organisation can still
  check this month, from its plan, credits and extra usage) and `month_breakdown`;
  organisation "this month" is the calendar month in India time throughout.
- `GET /v1/me/plan` gains `enforced`; plan payments gain `paid`.
- `GET /v1/orgs/{id}/history` rows gain `name`, and `input_type` is filled in.
- A payment handoff expires 10 minutes after it was made if never opened, and 30
  minutes after it was opened if nothing finished it.

## 1.7 (2026-10-01): monthly plans

Additive. `/v1/me` gains `plan_usage`: the person's plan (`plan` free, plus or pro;
`name`, `interval`, `renews_at`, `cancel_at_end`), this month's `allowance` and `used`,
`resets_at` (midnight on the 1st, India time), `credits` held besides the plan, and
extra usage (`extra_enabled`, `extra_cap_paise`, `extra_used_paise`,
`extra_price_paise`, `extra_blocked`). `credits.balance` now means the checks the
person can still make this month - the plan's left plus their credits - so an older
app's "checks left" stays right. `plan` is the plan in force (a lapsed paid plan reads
`free`).

New endpoints: `GET /v1/plans` (the price list, public); `GET /v1/me/plan`,
`POST /v1/me/plan/subscribe|confirm|cancel`, `PUT /v1/me/plan/extra`; the same under
`/v1/orgs/{id}/plan` for Team (and `PUT .../plan/api` for pay-per-check); and
`POST /v1/admin/billing/close-month`. A 402 can now also mean the plan, credits and
extra usage are all spent.

## 1.6 (2026-10-01): what is known about a link's website

Additive. `source_profile`, on the result of a submitted link (or a forward carrying
one): `domain`, `trusted` (on Factify's trusted-source list), `trust` ("highly
credible", "credible", "listed"), `fact_checker`, `level` (the source-risk level from
its observations), `findings` (plain lines to show) and `warnings` (lines to show
raised: a name imitating a trusted outlet, a domain registered weeks ago, no contact
page or named author, hidden instructions aimed at automated checkers), and
`domain_age_days` when the public registry says. Never a finding about a claim: a
site with strong warnings can only hold an answer back from True. `source_risk`, which
was always UNKNOWN, now carries the same level. Absent for anything but a link.

A new case rule, `rollup.fabricated_unreported`: an AI-made picture or video
presented as news, whose main claim is a world event that no trusted outlet reports
after a full search, is FALSE at no more than 70% confidence. The verdict's
`action_reason` says why; its claims stay unconfirmed, as no source contradicts them.

## 1.5 (2026-09-29): why a picture check did not run

Additive. `media_report.detector.why` and `media_report.history.why` say why a check
shows `not_checked`, so the app can say it rather than a bare "Not checked":

- `detector.why`: `text_card` (the picture is mostly flat colour, a text card or a
  screenshot: the AI-picture models misread those, and the words in it are checked
  instead), `too_small`, `unreadable`, `off` (no detector on this server), `failed`.
- `history.why`: `off` (reverse image search is not set up here, or its provider
  refuses us, as Google Vision does until billing is enabled) or `failed`.

Both are absent when the check ran.

`speech` (on a video's result): what is said in it - `text`, the `language` it was
heard in, and `cut_off` when only the start of a long video was read. Read on our own
server, and checked exactly as a pasted message is, alongside the words on its frame.

`media_report.detector.machine_voice` says whether a video's voice is past the voice
model's own line (the app does not hold the threshold); absent when there was no voice.

## 1.4 (2026-09-28): one full check, and "partly true"

The first change that is not purely additive: `verdict` has a new value.

- **`verdict: "PARTLY_TRUE"`**: some of it is right and some of it is not - a claim
  that carries the piece is confirmed while another is contradicted, or sources
  confirm only a smaller version of a claim (one state's one-time payment for "every
  woman, every month"). Its `action` is `SHARE_WITH_CORRECTION`, which used to read
  `MISLEADING`; an app built before 1.4 that meets an unknown verdict falls back to
  the action, and shows it as it did before. `MISLEADING` is now only
  `SHARE_WITH_CONTEXT`: media shown out of context, or a wrong detail in a piece of
  which nothing else could be confirmed.
- A claim confirmed only in a smaller version is still `status: MISLEADING_CONTEXT`;
  its `rule_id` is `rule.narrower_scope`, which is how a client tells "partly true"
  from "out of context".
- **`POST /v1/verify` `mode: "background"`**: answered at once with `202` and a case
  id, and checked in the background - every claim searched and read, with up to five
  minutes to do it. Poll `GET /v1/cases/{id}` for `claims_done` / `claims_total` and
  then the answer; follow `/v1/cases/{id}/events` for each source. `mode: "deep"` is
  kept as another name for it. `mode: "fast"` (the default) still answers in one
  request, and now also checks every claim, inside what one request can hold.
- **`POST /v1/verify/file` `background=true`**: the same for a picture or a PDF. A
  video is always checked in the background, as before.
- **`claims[].in_full`**: a claim not made in English, as one self-contained English
  sentence - "NASA launched Chandrayaan-3" for a Bengali claim whose words say "NASA
  launched it". Optional; absent for English claims, which are shown self-contained.
- There is no quick or deep check any more: `claims[].search` is never
  `not_searched` from 1.4 on (an older stored answer may still carry it), and every
  check costs `check_cost`. `credits.deep_check_cost` is kept, equal to `check_cost`,
  for an app that reads it.

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
