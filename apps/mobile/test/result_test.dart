/// The v5 result: claims underlined where they sit, the Why sheet, the receipt id,
/// and the one action the bottom bar offers for each verdict.
library;

import 'package:factify_mobile/api/client.dart';
import 'package:factify_mobile/app_services.dart';
import 'package:factify_mobile/auth/auth_service.dart';
import 'package:factify_mobile/history/history_store.dart';
import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/l10n/language_preference.dart';
import 'package:factify_mobile/models/submission.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:factify_mobile/screens/result_screen.dart';
import 'package:factify_mobile/theme/theme.dart';
import 'package:factify_mobile/widgets/action_style.dart';
import 'package:factify_mobile/widgets/claim_spans.dart';
import 'package:factify_mobile/widgets/why_sheet.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> _claim(
  String text, {
  String status = 'CONTRADICTED',
  int? confidence,
  Map<String, dynamic>? anchor,
}) => {
  'id': 'cl_${text.hashCode}',
  'text': text,
  'claim_type': 'EVENT',
  'status': status,
  'severity': 'HIGH',
  'importance': 'HEADLINE',
  'reason': 'A published fact-check rated this false.',
  'confidence': confidence,
  'input_anchor': anchor,
  'strength': {
    'score': 0.9,
    'band': 'STRONG',
    'components': [
      {'name': 'tier_composition', 'value': 0.92, 'explanation': '2×C, 1×D'},
      {
        'name': 'independent_origins',
        'value': 0.86,
        'explanation': '3 distinct origin(s) across 3 document(s)',
      },
    ],
    'version': 'v',
  },
  'evidence': [
    if (status != 'UNVERIFIED')
      {
        'id': 'ev_1',
        'tier': 'C',
        'kind': 'fact_check',
        'direction': status == 'SUPPORTED' ? 'supports' : 'contradicts',
        'method': 'claim_review',
        'finding': 'Rated false.',
        'citation_url': 'https://pib.gov.in/factcheck/1',
        'source_excerpt': 'No such scheme has been announced.',
        'publisher': 'PIB Fact Check',
        'credibility': 'HIGH',
      },
  ],
};

Verdict _verdict(
  String action,
  List<Map<String, dynamic>> claims, {
  int? confidence,
  Map<String, dynamic>? receipt,
}) => Verdict.fromJson({
  'case_id': 'case-1',
  'contract_version': '1.3',
  'action': action,
  'action_reason': 'r',
  'rule_version': 'v',
  'claims': claims,
  'advisories': <Object>[],
  'skipped': <Object>[],
  'retrieved_at': '2026-09-26T10:42:00Z',
  'from_cache': false,
  'elapsed_ms': 10,
  'confidence': ?confidence,
  'receipt_url': ?(receipt == null ? null : '/v1/receipts/${receipt['receipt_id']}'),
  'receipt': ?receipt,
});

Future<void> _show(WidgetTester tester, Widget child) async {
  tester.view.physicalSize = const Size(1080, 2340);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: buildFactifyTheme(Brightness.light),
      supportedLocales: AppLocalizations.supportedLocales,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      home: child,
    ),
  );
  await tester.pumpAndSettle();
}

AppServices _services() {
  final client = FactifyClient(baseUrl: 'http://factify.test');
  return AppServices(
    client: client,
    auth: AuthService(client: client, persist: false),
    language: LanguagePreference.inMemory(),
    history: HistoryStore(),
  );
}

void main() {
  group('claims are underlined where they sit', () {
    const text =
        'Govt to pay Rs 5,000 a month to every woman from 1 July. Register now at the link.';

    test("the server's anchor wins", () {
      // Worded too differently for the app to find on its own.
      final verdict = _verdict('DO_NOT_SHARE', [
        _claim(
          'The government will pay Rs 5,000 monthly to every woman',
          anchor: {'char_start': 0, 'char_end': 43},
        ),
      ]);
      final spans = locateClaims(text, verdict.claims);
      expect(text.substring(spans.single.start, spans.single.end), startsWith('Govt to pay'));
      expect(spans.single.end, 43);
    });

    test("an anchor that lands on none of the claim's words is not used", () {
      final verdict = _verdict('DO_NOT_SHARE', [
        _claim('Register now at the link.', anchor: {'char_start': 0, 'char_end': 20}),
      ]);
      final span = locateClaims(text, verdict.claims).single;
      expect(text.substring(span.start, span.end), 'Register now at the link');
    });

    test('a Hindi anchor is checked word by word, vowel signs and all', () {
      const hindi = 'सरकार हर महिला को पाँच हज़ार रुपये देगी। अभी पंजीकरण करें।';
      final verdict = _verdict('DO_NOT_SHARE', [
        _claim('सरकार महिलाओं को पैसे देगी', anchor: {'char_start': 0, 'char_end': 39}),
      ]);
      expect(locateClaims(hindi, verdict.claims).single.end, 39);
    });

    test('without one, the claim is found word for word, or by its longest run', () {
      final verdict = _verdict('DO_NOT_SHARE', [
        _claim('Register now at the link.'),
        _claim('The government will pay Rs 5,000 a month to every woman', status: 'UNVERIFIED'),
      ]);
      final spans = locateClaims(text, verdict.claims);
      expect(spans, hasLength(2));
      expect(text.substring(spans[0].start, spans[0].end), 'pay Rs 5,000 a month to every woman');
      expect(
        text.substring(spans[1].start, spans[1].end),
        'register now at the link'.replaceFirst('r', 'R'),
      );
    });

    test('a claim that shares nothing with the text is not underlined anywhere', () {
      final verdict = _verdict('DO_NOT_SHARE', [_claim('The moon is made of cheese today.')]);
      expect(locateClaims(text, verdict.claims), isEmpty);
    });
  });

  group('a picture with nothing to check (2026-09-27, on the phone)', () {
    final landscape = Verdict.fromJson({
      'case_id': 'case-2',
      'action': 'SEND_TO_REVIEW',
      'action_reason': 'r',
      'rule_version': 'v',
      'claims': [
        _claim(
          'This image has been published before, at a date and by a publisher that can be cited.',
          status: 'UNVERIFIED',
        )..['claim_type'] = 'MEDIA',
      ],
      'advisories': <Object>[],
      'skipped': <Object>[],
      'retrieved_at': '2026-09-27T10:00:00Z',
      'image_reading': {'text': '', 'description': 'Two green hills.', 'kind': 'OTHER'},
    });

    test("is not titled by the server's own question about it", () {
      expect(landscape.headline, isNull);
    });

    test('is labelled "Nothing to check" in History, as its page says', () {
      final l10n = lookupAppLocalizations(const Locale('en'));
      expect(ActionStyle.label(landscape, l10n), 'Nothing to check');
      expect(
        ActionStyle.label(_verdict('DO_NOT_SHARE', [_claim('A claim.', confidence: 90)]), l10n),
        'False',
      );
    });
  });

  test('a receipt id is shown in its short form', () {
    expect(shortReceiptId('7f3a21c9-0000-4000-8000-000000000000'), '7F3A-21C');
    expect(shortReceiptId('rcpt_44e09b1f'), '44E0-9B1');
  });

  testWidgets('the Why sheet shows the scale and the parts of the deciding claim', (tester) async {
    final verdict = _verdict('DO_NOT_SHARE', [_claim('A claim.', confidence: 91)], confidence: 91);
    await _show(tester, Scaffold(body: WhySheet(verdict: verdict)));

    expect(find.text('Why 91% confidence'), findsOneWidget);
    expect(find.text('Evidence tiers'), findsOneWidget);
    // The audit wording is put into plain words.
    expect(find.text('2 fact-checks, 1 news report'), findsOneWidget);
    expect(find.text('3 independent publishers, 3 pages'), findsOneWidget);
    expect(find.text('0.92'), findsOneWidget);
    expect(find.text('Excluded from this score: forensic signals.'), findsOneWidget);
  });

  testWidgets('for Unconfirmed the sheet says why there is no verdict, and no number', (
    tester,
  ) async {
    final verdict = _verdict('SEND_TO_REVIEW', [_claim('A claim.', status: 'UNVERIFIED')]);
    await _show(tester, Scaffold(body: WhySheet(verdict: verdict)));

    expect(find.text('Why unconfirmed?'), findsOneWidget);
    expect(find.textContaining('%'), findsNothing);
    expect(find.textContaining('not the same as false'), findsOneWidget);
  });

  group('the receipt', () {
    const receipt = {
      'receipt_id': 'rcpt_44e09b1f',
      'verified': true,
      'issued_at': '2026-09-27T10:00:00Z',
    };

    testWidgets('a fresh result shows the receipt it carries, with no second call', (tester) async {
      await _show(
        tester,
        ResultScreen(
          services: _services(),
          verdict: _verdict(
            'DO_NOT_SHARE',
            [_claim('A claim.', confidence: 90)],
            confidence: 90,
            receipt: receipt,
          ),
          submission: Submission.text('A claim.'),
          justChecked: true,
        ),
      );
      await tester.scrollUntilVisible(
        find.text('Receipt verified'),
        300,
        scrollable: find
            .byWidgetPredicate((w) => w is Scrollable && w.axisDirection == AxisDirection.down)
            .first,
      );

      expect(find.text('Receipt verified'), findsOneWidget);
      expect(find.textContaining('44E0-9B1'), findsOneWidget);
      expect(find.text('Checking the receipt'), findsNothing);
    });

    testWidgets('a result reopened later checks its receipt again', (tester) async {
      await _show(
        tester,
        ResultScreen(
          services: _services(),
          verdict: _verdict(
            'DO_NOT_SHARE',
            [_claim('A claim.', confidence: 90)],
            confidence: 90,
            receipt: receipt,
          ),
          submission: Submission.text('A claim.'),
        ),
      );

      // Asked of the server again, which the test host cannot reach: no seal is
      // claimed from the stored copy.
      expect(find.text('Receipt verified'), findsNothing);
    });

    test('an older server without the field reads as no inline receipt', () {
      expect(_verdict('DO_NOT_SHARE', [_claim('A claim.')]).receipt, isNull);
      expect(ReceiptSummary.tryParse({'verified': true}), isNull);
    });
  });

  group('the bottom bar offers one thing to do next', () {
    for (final (action, status, label) in [
      ('DO_NOT_SHARE', 'CONTRADICTED', 'Share correction'),
      ('SAFE_TO_SHARE', 'SUPPORTED', 'Share result'),
      ('SEND_TO_REVIEW', 'UNVERIFIED', 'Check again'),
    ]) {
      testWidgets('$action: $label', (tester) async {
        await _show(
          tester,
          ResultScreen(
            services: _services(),
            verdict: _verdict(action, [
              _claim('A claim.', status: status, confidence: status == 'UNVERIFIED' ? null : 90),
            ], confidence: status == 'UNVERIFIED' ? null : 90),
            submission: Submission.text('A claim.'),
          ),
        );

        expect(find.text(label), findsOneWidget);
      });
    }
  });
}
