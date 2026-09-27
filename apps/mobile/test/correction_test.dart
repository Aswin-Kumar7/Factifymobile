/// "Send this back to the chat" (v5, 2.6): the note that goes with the picture.
///
/// Held here: the server's note replaces the one built on the phone; the Hindi
/// note is asked for when Hindi is chosen; an edit is the person's and is never
/// overwritten, in either language; "Copy text only" copies the note with its links
/// and says "Copied"; and a server that cannot be reached leaves the phone's note.
library;

import 'dart:async';

import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/models/correction_message.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:factify_mobile/widgets/correction_sheet.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:share_plus/share_plus.dart';

const _url = 'https://pib.gov.in/factcheck/1';

Verdict _false() => Verdict.fromJson({
  'case_id': 'case-1',
  'action': 'DO_NOT_SHARE',
  'action_reason': 'r',
  'verdict': 'FALSE',
  'confidence': 91,
  'summary': 'No such scheme has been announced.',
  'rule_version': 'v',
  'claims': [
    {
      'id': 'cl_1',
      'text': 'Every woman gets Rs 5,000 a month.',
      'claim_type': 'EVENT',
      'status': 'CONTRADICTED',
      'severity': 'HIGH',
      'importance': 'HEADLINE',
      'reason': 'A published fact-check rated this false.',
      'rule_id': 'r',
      'rule_version': 'v',
      'strength': {'score': 0.9, 'band': 'STRONG', 'version': 'v'},
      'evidence': [
        {
          'id': 'ev_1',
          'tier': 'C',
          'kind': 'fact_check',
          'direction': 'contradicts',
          'method': 'claim_review',
          'finding': 'Rated false.',
          'citation_url': _url,
          'snapshot_id': 's',
          'source_excerpt': 'The claim is fake.',
          'source_anchor': <String, dynamic>{},
          'match_basis': {'metric': 'm', 'value': 0.9, 'threshold': 0.6},
          'match_quality': 'STRONG',
          'publisher': 'PIB Fact Check',
        },
      ],
    },
  ],
  'retrieved_at': '2026-09-26T10:00:00Z',
});

class _Clipboard {
  String? text;

  Future<Object?> handle(MethodCall call) async {
    if (call.method == 'Clipboard.setData') {
      text = (call.arguments as Map)['text'] as String?;
    }
    return null;
  }
}

Future<_Clipboard> _open(
  WidgetTester tester, {
  CorrectionLoader? load,
  Locale locale = const Locale('en'),
}) async {
  tester.view.physicalSize = const Size(1080, 2340);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
  final clipboard = _Clipboard();
  final messenger = tester.binding.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(SystemChannels.platform, clipboard.handle);
  addTearDown(() => messenger.setMockMethodCallHandler(SystemChannels.platform, null));

  await tester.pumpWidget(
    MaterialApp(
      locale: locale,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: CorrectionSheet(
        verdict: _false(),
        load: load,
        share: (_) async => ShareResultStatus.dismissed,
      ),
    ),
  );
  await tester.pumpAndSettle();
  return clipboard;
}

String _note(WidgetTester tester) =>
    tester.widget<TextField>(find.byType(TextField)).controller!.text;

void main() {
  testWidgets("the server's note replaces the phone's, and Hindi is asked for in Hindi", (
    tester,
  ) async {
    final asked = <String>[];
    await _open(
      tester,
      load: (language) async {
        asked.add(language);
        return CorrectionMessage(message: 'served in $language', links: const [_url]);
      },
    );

    expect(find.text('Send this back to the chat'), findsOneWidget);
    expect(_note(tester), 'served in en');

    await tester.tap(find.text('हिन्दी'));
    await tester.pumpAndSettle();
    expect(_note(tester), 'served in hi');
    expect(asked, ['en', 'hi']);

    // Back to English: already fetched, not asked for again.
    await tester.tap(find.text('English'));
    await tester.pumpAndSettle();
    expect(asked, ['en', 'hi']);
  });

  testWidgets('a Hindi phone starts on the Hindi note', (tester) async {
    await _open(tester, locale: const Locale('hi'));
    expect(_note(tester), startsWith('नमस्ते!'));
  });

  testWidgets('an edit is kept, and never overwritten by a late answer', (tester) async {
    final answer = Completer<CorrectionMessage>();
    await _open(tester, load: (_) => answer.future);

    expect(
      _note(tester),
      startsWith("Hi! I checked this before forwarding. Factify says it's false"),
    );
    await tester.enterText(find.byType(TextField), 'Mum, this one is fake: $_url');
    answer.complete(const CorrectionMessage(message: 'served', links: [_url]));
    await tester.pumpAndSettle();
    expect(_note(tester), 'Mum, this one is fake: $_url');

    // Switching languages and back brings the edit back too.
    await tester.tap(find.text('हिन्दी'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('English'));
    await tester.pumpAndSettle();
    expect(_note(tester), 'Mum, this one is fake: $_url');
  });

  testWidgets('"Copy text only" copies the note with its links, and says so', (tester) async {
    final clipboard = await _open(
      tester,
      load: (_) async => const CorrectionMessage(
        message: 'Hi! It is false. PIB: $_url',
        links: [_url, 'https://other.example/2'],
      ),
    );

    await tester.tap(find.text('Copy text only'));
    await tester.pumpAndSettle();
    expect(clipboard.text, 'Hi! It is false. PIB: $_url\nhttps://other.example/2');
    expect(find.text('Copied'), findsOneWidget);

    // Changing the note makes the copy stale, and the button says so.
    await tester.enterText(find.byType(TextField), 'Changed');
    await tester.pump();
    expect(find.text('Copy text only'), findsOneWidget);
  });

  testWidgets("a server that can't be reached leaves the phone's note", (tester) async {
    await _open(tester, load: (_) async => throw Exception('offline'));
    expect(_note(tester), endsWith('PIB Fact Check: $_url'));
  });
}
