/// The home screen's clipboard-on-open prompt (PLAN 1.7.2).
///
/// The rule under test is the privacy half as much as the feature half: the
/// prompt may say that text is waiting, but the text itself is read only when the
/// person asks.
library;

import 'dart:convert';

import 'package:factify_mobile/api/client.dart';
import 'package:factify_mobile/l10n/language_preference.dart';
import 'package:factify_mobile/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Map<String, dynamic> _verdictJson() => {
  'case_id': 'case-1',
  'contract_version': '1.0',
  'action': 'SEND_TO_REVIEW',
  'action_reason': 'Not enough citable evidence to decide.',
  'rule_version': '2026.08.1',
  'claims': <Map<String, dynamic>>[],
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

/// Pumps the whole app against a stand-in server and clipboard, and returns the
/// bodies of the checks it sends.
Future<List<Map<String, dynamic>>> _pumpApp(WidgetTester tester, _FakeClipboard clipboard) async {
  tester.view.physicalSize = const Size(1080, 2340);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);

  final messenger = tester.binding.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(SystemChannels.platform, clipboard.handle);
  addTearDown(() => messenger.setMockMethodCallHandler(SystemChannels.platform, null));

  final sent = <Map<String, dynamic>>[];
  final client = FactifyClient(
    baseUrl: 'http://factify.test',
    httpClient: MockClient((request) async {
      if (request.url.path == '/readyz') {
        return http.Response('{"ready": true, "missing": []}', 200);
      }
      sent.add(jsonDecode(request.body) as Map<String, dynamic>);
      return http.Response(jsonEncode(_verdictJson()), 200);
    }),
  );

  await tester.pumpWidget(FactifyApp(language: LanguagePreference.inMemory(), client: client));
  await tester.pumpAndSettle();
  return sent;
}

void main() {
  const offer = 'You have text copied. Check it?';

  testWidgets('offers to check copied text, and reads it only when asked', (tester) async {
    final clipboard = _FakeClipboard(
      hasText: true,
      text: 'The minister said the scheme was cancelled.',
    );
    final sent = await _pumpApp(tester, clipboard);

    expect(find.text(offer), findsOneWidget);
    // Offering is not reading: the content stays unread until the tap.
    expect(clipboard.read, isFalse);

    await tester.tap(find.text('Paste and check'));
    await tester.pumpAndSettle();

    expect(clipboard.read, isTrue);
    expect(sent.single['text'], 'The minister said the scheme was cancelled.');
    expect(find.text(offer), findsNothing);
  });

  testWidgets('says nothing when nothing is copied', (tester) async {
    await _pumpApp(tester, _FakeClipboard(hasText: false));

    expect(find.text(offer), findsNothing);
  });

  testWidgets('can be dismissed without the clipboard being read', (tester) async {
    final clipboard = _FakeClipboard(hasText: true, text: 'Anything');
    await _pumpApp(tester, clipboard);

    await tester.tap(find.byTooltip('Not now'));
    await tester.pumpAndSettle();

    expect(find.text(offer), findsNothing);
    expect(clipboard.read, isFalse);
  });

  testWidgets('a link the server could not check says so, not "Unconfirmed"', (tester) async {
    tester.view.physicalSize = const Size(1080, 2340);
    tester.view.devicePixelRatio = 2.625;
    addTearDown(tester.view.reset);
    final messenger = tester.binding.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(
      SystemChannels.platform,
      _FakeClipboard(hasText: false).handle,
    );
    addTearDown(() => messenger.setMockMethodCallHandler(SystemChannels.platform, null));

    final client = FactifyClient(
      baseUrl: 'http://factify.test',
      httpClient: MockClient((request) async {
        if (request.url.path == '/readyz') {
          return http.Response('{"ready": true, "missing": []}', 200);
        }
        return http.Response(
          '{"detail": "no checkable claims were found on the page. Nothing was checked."}',
          422,
        );
      }),
    );
    await tester.pumpWidget(FactifyApp(language: LanguagePreference.inMemory(), client: client));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'https://www.reuters.com/world/x');
    await tester.pump();
    await tester.tap(find.text('Check this'));
    await tester.pumpAndSettle();

    expect(find.textContaining("couldn't find anything to check on that page"), findsOneWidget);
    expect(find.text('Unconfirmed'), findsNothing);
  });

  testWidgets('"Check again" re-runs the same check fresh', (tester) async {
    final sent = await _pumpApp(tester, _FakeClipboard(hasText: false));

    await tester.enterText(find.byType(TextField), 'The minister said the scheme was cancelled.');
    await tester.pump();
    await tester.tap(find.text('Check this'));
    await tester.pumpAndSettle();

    expect(find.text('Check again'), findsOneWidget);
    expect(sent.single.containsKey('recheck'), isFalse);
    // The message is in the box already; it is not shown a second time below.
    expect(find.text('Checking this message'), findsNothing);

    await tester.tap(find.text('Check again'));
    await tester.pumpAndSettle();

    expect(sent, hasLength(2));
    expect(sent.last['text'], 'The minister said the scheme was cancelled.');
    expect(sent.last['recheck'], isTrue);
  });

  testWidgets('editing the box turns "Check again" back into "Check this"', (tester) async {
    await _pumpApp(tester, _FakeClipboard(hasText: false));

    await tester.enterText(find.byType(TextField), 'The minister said the scheme was cancelled.');
    await tester.pump();
    await tester.tap(find.text('Check this'));
    await tester.pumpAndSettle();
    expect(find.text('Check again'), findsOneWidget);

    await tester.enterText(find.byType(TextField), 'Something else entirely.');
    await tester.pump();

    expect(find.text('Check again'), findsNothing);
    expect(find.text('Check this'), findsOneWidget);
  });

  testWidgets('a deep check shows the progress the server reports, then the verdict', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1080, 2340);
    tester.view.devicePixelRatio = 2.625;
    addTearDown(tester.view.reset);
    final messenger = tester.binding.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(
      SystemChannels.platform,
      _FakeClipboard(hasText: false).handle,
    );
    addTearDown(() => messenger.setMockMethodCallHandler(SystemChannels.platform, null));

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
              ? http.Response('{"status": "processing", "claims_done": 1, "claims_total": 3}', 202)
              : http.Response(jsonEncode(_verdictJson()), 200);
        }
        return http.Response('{}', 404);
      }),
    );
    await tester.pumpWidget(FactifyApp(language: LanguagePreference.inMemory(), client: client));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Deep check'));
    await tester.pump();
    await tester.enterText(find.byType(TextField), 'The minister said the scheme was cancelled.');
    await tester.pump();
    await tester.tap(find.text('Check this'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();

    expect(sent.single['mode'], 'deep');
    expect(find.text('1 of 3 claims checked'), findsOneWidget);
    expect(find.text('Deep check…'), findsOneWidget);

    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();

    expect(find.text('Check again'), findsOneWidget);
    expect(find.text('Unconfirmed'), findsOneWidget);
  });
}

