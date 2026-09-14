# Hackathon workflow — from 2026-09-14

Built from a verified audit on 2026-09-14: every defect below was reproduced on the
emulator, in the database or against the live API.

**Ground rules set by the user:** nothing from the original plan is dropped — items
are sequenced, and the user decides later what to skip. The Flutter app comes first.
Day 6 (demo video / pitch / submission) is not part of this workflow.

## The app: fix it, don't rebuild it

It builds (debug and release), analyzes clean, all 51 imports resolve, the Dart↔Kotlin
share channel matches, and on the emulator it launches, shows *Online*, verifies
text, and accepts shared text both cold and warm. What makes it feel broken is a
specific list of defects and unbuilt plan items, below.

## Phase A — Flutter app (M44 + PLAN §1.7), first

Governing spec: **M44** in `agent-actionplan.md`. Done when: *content shared from a
messaging app, a browser and the gallery all reach a rendered verdict, in both
supported languages.* Also carries the original **PLAN.md §1.7** app tasks.

### FL-1 · Broken fundamentals (verified defects) — ✅ done 2026-09-14
Verified after the fix: `flutter analyze` clean, widget tests 13/13, live integration
4/4, release APK has `INTERNET` in its merged manifest and shows *Online* on the
emulator, and a failed image share now shows a visible message. Still open: the
shared image's `SecurityException` may be an adb-granted-URI artifact — verify on a
real phone (FL-5).

| ID | Defect | Where |
|---|---|---|
| F1 | Release APK has no `INTERNET` permission — cannot reach the network | `android/app/src/main/AndroidManifest.xml` |
| F2 | Timeouts surface as raw `TimeoutException after 0:00:45` text | `lib/api/client.dart` |
| F3 | Image upload and case polling bypass the error wrapper; failures go uncaught | `client.dart:77`, `:90`; `home_screen.dart` |
| F4 | A failed image share does nothing visible and clears the previous result | `MainActivity.kt:129–136`, share handling |
| F5 | Redesign removed the "Evidence retrieved" label (test fails) | `verdict_card.dart`; `widget_test.dart:246` |
| F6 | Integration test asserts extraction is unconfigured | `live_api_test.dart:30` |
| F7 | App ships pointing at `http://10.0.2.2:8000` (emulator-only) | `client.dart:22`, build flag |

### FL-2 · Languages (M44 done-when · §1.7.6) — ✅ done 2026-09-14
Every interface string lives in `lib/l10n/app_en.arb` and `app_hi.arb` (gen-l10n),
reusing the approved Hindi wording in `app/extraction/phrasing.py` where it exists. The
interface follows the phone's language with an English fallback; a language menu on the
home and evidence screens overrides it and is remembered; every check sends the
interface language as `language`; layouts are direction-aware.

Verified: `flutter analyze` clean; widget and ARB tests 24/24 (the design law in Hindi,
the toggle end to end including the `language` sent, the phone-locale fallback, layout
at phone width in both languages and both text directions, ARB key/placeholder/case
parity); live integration 4/4 sending `language: "hi"`; the file endpoint accepts a
`language` form field (HTTP 200); the release APK builds with the new
`shared_preferences` plugin. On the emulator: English → हिन्दी from the menu, a Hindi
verdict card and evidence screen against the live API, the choice surviving a
force-stop, and "phone language" returning to English on the en-US device.

Found and fixed on the way: the verdict meta chip and the app-bar title could neither
wrap nor shrink, so a Hindi label or a large system font ran past the card and the app
bar.

Still open, owned by **B5**: verdict reasons, summaries and notes arrive in English;
the Hindi screens say so in a one-line note until the server phrases them.

### FL-3 · Correction share-out (M44 · §1.7.5) — ✅ built 2026-09-14 · device share pending
"Share correction" used to copy text to the clipboard and nothing more. It now opens a
preview of the correction card — the verdict's own wording, the decided claims, who
said so and when, the retrieval time, never an advisory — captured as a 1080-px PNG and
handed to the system share sheet (`share_plus`) with the source links as text beside
it. "Copy text only" remains. The card is also offered for `SHARE_WITH_CONTEXT`, whose
own advice is to share the context; an abstention still gets no button.

Verified: `flutter analyze` clean; widget and ARB tests 29/29, including a real PNG
captured and handed to the share call with the links, the card in Hindi without truth
words, and the sheet at phone width in both languages and both text directions; the
release APK builds (52 MB) with `share_plus` and its `path_provider`/`jni` native
library.

**Not yet exercised on a device: the share sheet itself.** No live check currently
produces a verdict that shows the button. The ledger holds only `SEND_TO_REVIEW` (61)
and `SHARE_WITH_CONTEXT` (7), and all 7 came from the one registered image
(`commons.wikimedia.org/wiki/File:Glimpses_of_the_new_Parliament_Building.jpg`), which is
not on this machine. Needs that image (a download to approve) or corpus content that
yields a correction.

### FL-4 · Evidence screen completeness (M44 · §1.7.4 · §1.7.7)
- Timeline of dates and instances (absent)
- Media match preview (absent)
- Claim anchor shown with the claim
- Strength rows tappable through to their citations — **needs the components from the
  server first**: on 2026-09-14 a cached text verdict arrived with
  `strength.components: []` (band `none`), while a live media verdict carried all
  five. Find which path drops them — the cache hit or the text abstention.
- Teaching-mode line

### FL-5 · Intake completeness (M44 · §1.7.2)
- Upload progress for files (indeterminate spinner only today)
- Clipboard-on-open prompt
- URL share verified end to end; gallery share verified on a real phone

### FL-6 · On-device pre-processing (§1.7.3)
- dHash + EXIF read on device; local phash → verdict cache

## Phase B — Backend blockers (verified)
| ID | Defect | Where |
|---|---|---|
| B1 | Extraction cache never renews `expires_at` — 17 of 19 rows permanently dead | `app/db/repositories.py` → `put_extraction` |
| B2 | Extraction runs before the verdict-cache probe (cached repeat: 83ms inside, 19.2s wall) | `app/api/verify.py:238` vs `:240` |
| B3 | Extraction still on Gemini default thinking (25s alone) | `app/extraction/llm.py` |
| B4 | Ingestion trigger never runs a tick; no worker composed; no CLI — corpus stuck at 2026-08-18 | `app/api/verify.py:509` |
| B5 | Request `language` is ignored and the Hindi phrasing templates (M21) are never called; the file endpoint does not declare a `language` form field (the app already sends one) | `app/api/verify.py`; `app/extraction/phrasing.py` |
| R1 | `gemini-3-flash-preview` slow and capacity-limited (13–17s for "say ok") | provider |
| G1 | 42 commits exist only locally; GitHub has an unrelated history | git |

## Phase C — Capability, deployment, evaluation
- M29 attribution/quote · M31 temporal · M32 source risk — compose into the pipeline
- M18 OCR for screenshots
- M49 deploy (Cloud Run from Cloud Shell) · M24 Cloud Scheduler
- M46 clean audit run · M48 pre-warm + offline rehearsal — **the demo set must include
  content that yields `DO_NOT_SHARE` or `SHARE_WITH_CORRECTION`**: as of 2026-09-14 the
  ledger has never produced either, so the red and orange verdicts and the correction
  card cannot be shown with live data. The one registered media fingerprint is also the
  only source of `SHARE_WITH_CONTEXT`, and its image is not on this machine.

## Phase D — Remaining original-plan modules (sequenced, not dropped)
- M45 web evidence console
- M42 result receipts
- M27 Google Fact Check API
- M34 reverse-image discovery
- M35 video worker
- Async reasoning upgrade (fast lexical answer, background read)
- Android Gradle Plugin / Kotlin upgrades — the 2026-09-14 release build warns that
  Flutter will soon drop Gradle 8.14, AGP 8.11.1 and Kotlin 2.2.20

## Decisions for the user
- GitHub: push to a new branch, or overwrite `main` (discards only the two remote planning commits).
- Rotate keys before deploying.
- A physical Android phone for real share grants and the camera.
- Wording: the `SHARE_WITH_CONTEXT` headline reads "True, but missing context" — the one
  headline that speaks about truth rather than evidence (the Hindi mirrors it). Keep, or
  align with the server's "Real content, misleading context"?
- Download the registered Wikimedia image (see FL-3), so the recycled-image verdict and
  the correction card can be exercised on a device?
