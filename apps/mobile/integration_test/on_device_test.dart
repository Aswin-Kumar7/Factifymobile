/// The shipped app, on a real device, against a real service.
///
/// Everything under `test/` runs on the host VM: the widget tests drive the UI with
/// hand-written payloads, and `test/integration/` drives the HTTP client directly.
/// Neither runs the app. This does — it boots the APK on the emulator and types into
/// the same field a person types into, so it covers the three things only a device
/// can show:
///
///   - the app reaches the service over the network a phone actually has
///     (`10.0.2.2` is the host as the emulator sees it, and a build that got that
///     wrong would pass every test under `test/` and fail on every phone),
///   - a verdict renders rather than merely parses,
///   - Devanagari survives the keyboard, the request and the result.
///
///   flutter test integration_test/on_device_test.dart -d emulator-5554
///
/// Verifications take tens of seconds, so each wait is bounded explicitly rather
/// than by `pumpAndSettle`, which gives up on a screen that is legitimately busy.
library;

import 'package:factify_mobile/main.dart' as app;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

/// Pump until [found] is true or the budget runs out.
///
/// `pumpAndSettle` is wrong here: a spinner is a running animation, so settling
/// never happens while the service is thinking, and the test fails with a timeout
/// that says nothing about the product.
Future<bool> _waitFor(
  WidgetTester tester,
  bool Function() found, {
  Duration budget = const Duration(seconds: 90),
}) async {
  final deadline = DateTime.now().add(budget);
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 500));
    if (found()) return true;
  }
  return false;
}

// The four verdicts a card can carry since the redesign. The old evidence-only
// headlines ("Nothing contradicts this", "Not enough evidence to decide") are gone,
// and waiting for them timed out on a card that had drawn perfectly well.
bool _anyVerdictShown() => const [
  'True',
  'False',
  'Misleading',
  'Unconfirmed',
].any((headline) => find.text(headline).evaluate().isNotEmpty);

/// Launch the app and get to Home: past the splash, and through the welcome by
/// creating a throwaway account the first time (an account is compulsory; the
/// session is remembered after that).
Future<void> _start(WidgetTester tester) async {
  app.main();
  final home = find.text('What would you like to check?');
  final welcome = find.text('Create your account');
  expect(
    await _waitFor(
      tester,
      () => home.evaluate().isNotEmpty || welcome.evaluate().isNotEmpty,
      budget: const Duration(seconds: 20),
    ),
    isTrue,
    reason: 'the app never got past its splash',
  );
  if (welcome.evaluate().isNotEmpty) {
    final stamp = DateTime.now().microsecondsSinceEpoch;
    await tester.enterText(find.widgetWithText(TextField, 'Email'), 'device-$stamp@factify.test');
    await tester.enterText(find.widgetWithText(TextField, 'Password'), 'device-test-$stamp');
    await tester.enterText(
      find.widgetWithText(TextField, 'Confirm password'),
      'device-test-$stamp',
    );
    await tester.pump();
    final create = find.widgetWithText(FilledButton, 'Create account');
    await tester.ensureVisible(create);
    await tester.pumpAndSettle();
    await tester.tap(create);
    expect(
      await _waitFor(tester, () => home.evaluate().isNotEmpty),
      isTrue,
      reason: 'creating an account did not open the app',
    );
  }
  expect(home, findsOneWidget);
}

Future<void> _submit(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField).first, text);
  await tester.pump();

  final check = find.text('Check now');
  expect(check, findsOneWidget, reason: 'the check button is the only way in');
  await tester.tap(check);
  await tester.pump();
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('the app starts and offers somewhere to paste a claim', (tester) async {
    await _start(tester);

    expect(find.byType(TextField), findsWidgets);
    expect(find.text('Check now'), findsOneWidget);
  });

  testWidgets('an English claim is checked and a verdict is rendered', (tester) async {
    await _start(tester);

    await _submit(tester, '5G mobile towers spread the coronavirus.');

    final shown = await _waitFor(tester, _anyVerdictShown);
    expect(
      shown,
      isTrue,
      reason: 'no verdict rendered — the app could not reach the service, or the '
          'result did not draw',
    );

    // A known falsehood must never read True, whatever else the sources say.
    expect(find.text('True'), findsNothing, reason: '5G does not spread the coronavirus');
  });

  testWidgets('a Hindi claim survives the keyboard, the request and the result', (tester) async {
    await _start(tester);

    await _submit(tester, 'गाय का मूत्र पीने से कोरोना वायरस का संक्रमण पूरी तरह ठीक हो जाता है।');

    expect(
      await _waitFor(tester, _anyVerdictShown),
      isTrue,
      reason: 'Devanagari did not survive the round trip',
    );
  });

  testWidgets('a shared link is accepted in the same field as text', (tester) async {
    await _start(tester);

    await _submit(tester, 'https://en.wikipedia.org/wiki/Chandrayaan-3');

    expect(
      await _waitFor(tester, _anyVerdictShown, budget: const Duration(seconds: 120)),
      isTrue,
      reason: 'a link is the commonest thing a person forwards; it must be read',
    );
  });

  testWidgets('the check button refuses an empty submission', (tester) async {
    await _start(tester);

    final check = tester.widget<ButtonStyleButton>(
      find.ancestor(of: find.text('Check now'), matching: find.bySubtype<ButtonStyleButton>()),
    );

    // Disabled rather than accepted-and-rejected: an empty submission has no honest
    // answer, and a 422 explaining that is a worse experience than a button that
    // plainly is not ready.
    expect(check.onPressed, isNull);
  });
}
