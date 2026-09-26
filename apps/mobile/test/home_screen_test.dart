/// Home, the check in progress, the result, and history (the app's main path).
///
/// The rules under test: one kind of input at a time, removed with its X to switch;
/// the clipboard is read only when the person asks; a check runs on its own page and
/// its answer opens on another; and every finished check is kept in history, from
/// which it opens again exactly as it was shown.
library;

import 'dart:convert';

import 'package:factify_mobile/api/client.dart';
import 'package:factify_mobile/l10n/language_preference.dart';
import 'package:factify_mobile/main.dart';
import 'package:factify_mobile/widgets/ui/ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Map<String, dynamic> _verdictJson() => {
  'case_id': 'case-1',
  'contract_version': '1.2',
  'action': 'SEND_TO_REVIEW',
  'action_reason': 'Not enough citable evidence to decide.',
  'rule_version': '2026.08.1',
  // One claim no source settled: an answer with no claim at all is "nothing to
  // fact-check", a different card.
  'claims': <Map<String, dynamic>>[
    {
      'id': 'cl_1',
      'text': 'RBI is withdrawing Rs 500 notes.',
      'claim_type': 'EVENT',
      'status': 'UNVERIFIED',
      'severity': 'HIGH',
      'importance': 'HEADLINE',
      'reason': 'Not enough citable evidence.',
      'strength': {'score': 0.0, 'band': 'WEAK', 'components': <Object>[], 'version': 'v'},
      'evidence': <Object>[],
    },
  ],
  'advisories': <Map<String, dynamic>>[],
  'skipped': <Map<String, dynamic>>[],
  'completeness_note': null,
  'retrieved_at': '2026-09-14T10:00:00Z',
  'from_cache': false,
  'elapsed_ms': 700,
};

/// Stands in for the platform clipboard, and records whether it was ever read.
class _FakeClipboard {
  _FakeClipboard({required this.hasText, this.text = ''});

  final bool hasText;
  final String text;
  bool read = false;

  Future<Object?> handle(MethodCall call) async {
    if (call.method == 'Clipboard.hasStrings') return {'value': hasText};
    if (call.method == 'Clipboard.getData') {
      read = true;
      return {'text': text};
    }
    return null;
  }
}

void _phone(WidgetTester tester, _FakeClipboard clipboard) {
  tester.view.physicalSize = const Size(1080, 2340);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
  final messenger = tester.binding.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(SystemChannels.platform, clipboard.handle);
  addTearDown(() => messenger.setMockMethodCallHandler(SystemChannels.platform, null));
}

/// Pumps the whole app against a stand-in server and clipboard, and returns the
/// bodies of the checks it sends.
Future<List<Map<String, dynamic>>> _pumpApp(
  WidgetTester tester,
  _FakeClipboard clipboard, {
  http.Response Function(http.Request request)? answer,
}) async {
  _phone(tester, clipboard);
  final sent = <Map<String, dynamic>>[];
  final client = FactifyClient(
    baseUrl: 'http://factify.test',
    httpClient: MockClient((request) async {
      if (request.url.path == '/readyz') {
        return http.Response('{"ready": true, "missing": []}', 200);
      }
      if (request.url.path == '/v1/auth/config') return http.Response('{"enabled": false}', 200);
      sent.add(jsonDecode(request.body) as Map<String, dynamic>);
      return answer?.call(request) ?? http.Response(jsonEncode(_verdictJson()), 200);
    }),
  );

  await tester.pumpWidget(FactifyApp(language: LanguagePreference.inMemory(), client: client));
  await tester.pumpAndSettle();
  return sent;
}

Future<void> _check(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField), text);
  await tester.pump();
  await tester.tap(find.text('Check now'));
  await tester.pumpAndSettle();
}

void main() {
  const offer = 'Paste copied text';
  const claim = 'The minister said the scheme was cancelled.';

  group('the clipboard', () {
    testWidgets('is offered, and read only when asked', (tester) async {
      final clipboard = _FakeClipboard(hasText: true, text: claim);
      final sent = await _pumpApp(tester, clipboard);

      expect(find.text(offer), findsOneWidget);
      // Offering is not reading: the content stays unread until the tap.
      expect(clipboard.read, isFalse);

      await tester.tap(find.text(offer));
      await tester.pumpAndSettle();

      // Pasted into the box, to be looked at before it is checked.
      expect(clipboard.read, isTrue);
      expect(find.text(claim), findsOneWidget);
      expect(sent, isEmpty);

      await tester.tap(find.text('Check now'));
      await tester.pumpAndSettle();
      expect(sent.single['text'], claim);
      expect(find.text('Result'), findsOneWidget);
    });

    testWidgets('says nothing when nothing is copied', (tester) async {
      await _pumpApp(tester, _FakeClipboard(hasText: false));

      expect(find.text(offer), findsNothing);
    });

    testWidgets('goes once something is typed, still unread', (tester) async {
      final clipboard = _FakeClipboard(hasText: true, text: 'Anything');
      await _pumpApp(tester, clipboard);

      await tester.enterText(find.byType(TextField), claim);
      await tester.pumpAndSettle();

      expect(find.text(offer), findsNothing);
      expect(clipboard.read, isFalse);
    });
  });

  group('one kind of input at a time', () {
    testWidgets('once text is added the other kinds are locked, and X unlocks them', (
      tester,
    ) async {
      await _pumpApp(tester, _FakeClipboard(hasText: false));

      await tester.enterText(find.byType(TextField), claim);
      await tester.pump();
      await tester.tap(find.text('Image'));
      await tester.pumpAndSettle();

      // Still on text, and told why.
      expect(find.byType(TextField), findsOneWidget);
      expect(find.text("Remove what you've added to switch to another type."), findsOneWidget);
      expect(find.text('Add a picture'), findsNothing);

      await tester.tap(find.text('Remove'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Image'));
      await tester.pumpAndSettle();

      expect(find.text('Add a picture'), findsOneWidget);
      expect(find.text('Gallery'), findsOneWidget);
      expect(find.byType(TextField), findsNothing);
    });

    testWidgets('nothing can be checked until something is added', (tester) async {
      await _pumpApp(tester, _FakeClipboard(hasText: false));

      final button = tester.widget<FxButton>(
        find.ancestor(of: find.text('Check now'), matching: find.byType(FxButton)),
      );
      expect(button.onPressed, isNull);
    });

    testWidgets('a link is recognised as a link', (tester) async {
      await _pumpApp(tester, _FakeClipboard(hasText: false));

      await tester.enterText(find.byType(TextField), 'https://www.reuters.com/world/x');
      await tester.pump();

      expect(find.text("Link found. We'll read the page and check it."), findsOneWidget);
    });
  });

  group('the check and its result', () {
    testWidgets('a text check opens the result on its own page', (tester) async {
      final sent = await _pumpApp(tester, _FakeClipboard(hasText: false));

      await _check(tester, claim);

      expect(sent.single['text'], claim);
      expect(find.text('Result'), findsOneWidget);
      expect(find.text('Unconfirmed'), findsOneWidget);
      expect(find.text(claim), findsOneWidget); // what was checked, above the answer
    });

    testWidgets('a link the server could not check says so, not "Unconfirmed"', (tester) async {
      await _pumpApp(
        tester,
        _FakeClipboard(hasText: false),
        answer: (_) => http.Response(
          '{"detail": "no checkable claims were found on the page. Nothing was checked."}',
          422,
        ),
      );

      await _check(tester, 'https://www.reuters.com/world/x');

      expect(find.text("The check didn't finish"), findsOneWidget);
      expect(find.textContaining("couldn't find anything to check on that page"), findsOneWidget);
      expect(find.text('Unconfirmed'), findsNothing);

      await tester.tap(find.text('Back to home'));
      await tester.pumpAndSettle();
      // The link is still there to try another way.
      expect(find.text('https://www.reuters.com/world/x'), findsOneWidget);
    });

    testWidgets('"Check again" re-runs the same check fresh', (tester) async {
      final sent = await _pumpApp(tester, _FakeClipboard(hasText: false));

      await _check(tester, claim);
      expect(sent.single.containsKey('recheck'), isFalse);

      await tester.tap(find.text('Check again'));
      await tester.pumpAndSettle();

      expect(sent, hasLength(2));
      expect(sent.last['text'], claim);
      expect(sent.last['recheck'], isTrue);
      expect(find.text('Result'), findsOneWidget);
    });

    testWidgets('"New check" returns to an empty Home', (tester) async {
      await _pumpApp(tester, _FakeClipboard(hasText: false));

      await _check(tester, claim);
      await tester.tap(find.text('New check'));
      await tester.pumpAndSettle();

      expect(find.text('What would you like to check?'), findsOneWidget);
      // The box is empty again; the check is listed under Recent.
      expect(tester.widget<TextField>(find.byType(TextField)).controller?.text, isEmpty);
      expect(find.text('Recent'), findsOneWidget);
    });

    testWidgets('a deep check shows the progress the server reports, then the verdict', (
      tester,
    ) async {
      _phone(tester, _FakeClipboard(hasText: false));
      final sent = <Map<String, dynamic>>[];
      var polls = 0;
      final client = FactifyClient(
        baseUrl: 'http://factify.test',
        httpClient: MockClient((request) async {
          if (request.url.path == '/readyz') {
            return http.Response('{"ready": true, "missing": []}', 200);
          }
          if (request.method == 'POST' && request.url.path == '/v1/verify') {
            sent.add(jsonDecode(request.body) as Map<String, dynamic>);
            return http.Response('{"case_id": "deep-1", "poll_url": "/v1/cases/deep-1"}', 202);
          }
          if (request.url.path == '/v1/cases/deep-1') {
            polls += 1;
            return polls == 1
                ? http.Response(
                    '{"status": "processing", "claims_done": 1, "claims_total": 3}',
                    202,
                  )
                : http.Response(jsonEncode(_verdictJson()), 200);
          }
          return http.Response('{}', 404);
        }),
      );
      await tester.pumpWidget(FactifyApp(language: LanguagePreference.inMemory(), client: client));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Deep'));
      await tester.pump();
      await tester.enterText(find.byType(TextField), claim);
      await tester.pump();
      await tester.tap(find.text('Check now'));
      await tester.pump();
      await tester.pump(const Duration(seconds: 3));
      await tester.pump();

      expect(sent.single['mode'], 'deep');
      expect(find.text('1 of 3 claims checked'), findsOneWidget);
      expect(find.text('Deep check…'), findsOneWidget);

      await tester.pump(const Duration(seconds: 3));
      await tester.pumpAndSettle();

      expect(find.text('Result'), findsOneWidget);
      expect(find.text('Unconfirmed'), findsOneWidget);
    });
  });

  group('history', () {
    testWidgets('a finished check is kept, and opens again as it was shown', (tester) async {
      await _pumpApp(tester, _FakeClipboard(hasText: false));

      await _check(tester, claim);
      await tester.tap(find.text('New check'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('History'));
      await tester.pumpAndSettle();

      expect(find.text('Today'), findsOneWidget);
      expect(find.text(claim), findsOneWidget);
      expect(find.textContaining('No sources'), findsOneWidget);

      await tester.tap(find.text(claim));
      await tester.pumpAndSettle();

      expect(find.text('Result'), findsOneWidget);
      expect(find.text('Unconfirmed'), findsOneWidget);
    });

    testWidgets('is empty, and says what it is for, before anything is checked', (tester) async {
      await _pumpApp(tester, _FakeClipboard(hasText: false));

      await tester.tap(find.text('History'));
      await tester.pumpAndSettle();

      expect(find.text('No checks yet'), findsOneWidget);
    });
  });

  group('the way in', () {
    testWidgets('splash, then an account is required, then the app', (tester) async {
      _phone(tester, _FakeClipboard(hasText: false));
      final client = FactifyClient(
        baseUrl: 'http://factify.test',
        httpClient: MockClient((request) async {
          switch (request.url.path) {
            case '/v1/auth/config':
              return http.Response(
                '{"enabled": true, "required": true, "providers": ["password"]}',
                200,
              );
            case '/v1/auth/register':
              return http.Response(
                jsonEncode({
                  'access_token': 'fs_session-1',
                  'expires_at': DateTime.now().add(const Duration(days: 30)).toIso8601String(),
                  'method': 'password',
                  'email': 'asha@example.org',
                }),
                201,
              );
            case '/v1/me':
              return http.Response(
                jsonEncode({
                  'id': 'u-1',
                  'email': 'asha@example.org',
                  'name': 'Asha',
                  'plan': 'free',
                  'joined_at': '2026-09-26T10:00:00Z',
                  'credits': {
                    'balance': 100,
                    'used': 0,
                    'checks': 0,
                    'check_cost': 1,
                    'deep_check_cost': 3,
                    'limited': false,
                  },
                }),
                200,
              );
          }
          return http.Response('{"ready": true, "missing": []}', 200);
        }),
      );

      await tester.pumpWidget(
        FactifyApp(language: LanguagePreference.inMemory(), client: client, showIntro: true),
      );
      await tester.pump();
      expect(find.text('Check before you share'), findsOneWidget);

      await tester.pump(const Duration(seconds: 2));
      await tester.pumpAndSettle();

      // No way past without an account.
      expect(find.text('Create your account'), findsOneWidget);
      expect(find.textContaining('without an account'), findsNothing);

      await tester.enterText(find.widgetWithText(TextField, 'Email'), 'asha@example.org');
      await tester.enterText(find.widgetWithText(TextField, 'Password'), 'long enough');
      await tester.enterText(find.widgetWithText(TextField, 'Confirm password'), 'long enough');
      await tester.pump();
      final create = find.widgetWithText(FilledButton, 'Create account');
      await tester.ensureVisible(create);
      await tester.pumpAndSettle();
      await tester.tap(create);
      await tester.pumpAndSettle();

      expect(find.text('Hi, Asha'), findsOneWidget);
      expect(find.text('What would you like to check?'), findsOneWidget);

      await tester.tap(find.text('Profile'));
      await tester.pumpAndSettle();
      expect(find.text('Signed in with email'), findsOneWidget);
      expect(find.text('100 credits left'), findsOneWidget);
    });
  });
}
