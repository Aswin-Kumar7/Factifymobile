# Facify for Android

The judged surface of Facify (M44). Share a forward, a link or a picture into the app
and get a verdict that rests only on cited sources — with the evidence, what could
not be checked, and what Facify cannot establish. The app holds no provider
credential: every key lives in the API.

## Run it

The app talks only to the Facify API. Built without a flag it points at
`http://10.0.2.2:8000`, the host machine as seen from the Android emulator, so a local
API started from the repository root with `uv run python scripts/serve_local.py` is
reachable from the emulator as-is.

```bash
flutter run
```

A build for a real phone needs the deployed API's address. A release build made
without one says so on screen rather than simply looking offline.

```bash
flutter build apk --release --dart-define=FACIFY_API=https://your-api.example
```

## Test it

```bash
flutter analyze
```

```bash
flutter test test/widget_test.dart test/l10n_test.dart
```

The widget tests check the design law in both languages, the language toggle end to
end, and that the result and evidence screens lay out at phone width, left to right
and right to left. `test/integration/live_api_test.dart` runs against a live API on
`127.0.0.1:8000`.

## Languages

English and Hindi (PLAN 1.7.6).

- Strings live in `lib/l10n/app_en.arb`, the template, and `lib/l10n/app_hi.arb`.
  `AppLocalizations` is generated from them on `flutter pub get`; the generated files
  are committed, so a fresh clone analyzes cleanly.
- `test/l10n_test.dart` fails when the Hindi file is missing a key, drops a
  placeholder, changes a select case, or leaves a message identical to the English.
- The interface follows the phone's language, falling back to English, unless the
  reader picks one from the language menu on the home or evidence screen. That choice
  is the only thing the app stores on the device; what was checked is never written.
- Every check sends the interface language to the API as `language`. The server does
  not phrase verdicts in Hindi yet (B5 in `docs/hackathon-workflow.md`), so reasons
  still arrive in English, and the Hindi interface says so.

To add a language, add `lib/l10n/app_<code>.arb` with every key, give it a name in
`lib/widgets/language_menu.dart`, and add its code to `_translations` in
`test/l10n_test.dart`.
