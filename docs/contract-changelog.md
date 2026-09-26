# API contract changelog

The shape both clients read is defined in `app/api/schemas.py` and versioned by
`CONTRACT_VERSION`. Every change so far is additive: a field is added, optional, and
nothing that was there changes name, type or meaning. A client built against an older
version keeps working and simply does not show the new fields.

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

## 1.2

- **`image_reading`** `{text, description, kind, publisher, language}`: what was
  read from an uploaded picture.

## 1.1

- **`verdict`**, **`confidence`**, **`summary`** on the result; per-claim
  **`confidence`** and **`explanation`**; per-source **`credibility`**.
