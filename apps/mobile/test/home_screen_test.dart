/// The home screen's clipboard-on-open prompt (PLAN 1.7.2).
///
/// The rule under test is the privacy half as much as the feature half: the
/// prompt may say that text is waiting, but the text itself is read only when the
/// person asks.
library;

import 'dart:convert';

import 'package:facify_mobile/api/client.dart';
import 'package:facify_mobile/l10n/language_preference.dart';
import 'package:facify_mobile/main.dart';
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
  final client = FacifyClient(
    baseUrl: 'http://facify.test',
    httpClient: MockClient((request) async {
      if (request.url.path == '/readyz') {
        return http.Response('{"ready": true, "missing": []}', 200);
      }
      sent.add(jsonDecode(request.body) as Map<String, dynamic>);
      return http.Response(jsonEncode(_verdictJson()), 200);
    }),
  );

  await tester.pumpWidget(FacifyApp(language: LanguagePreference.inMemory(), client: client));
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
}
