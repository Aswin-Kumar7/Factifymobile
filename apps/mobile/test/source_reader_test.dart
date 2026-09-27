/// The source reader (v5, 2.5): a cited passage in its article, and never less than
/// the quote the result rests on.
library;

import 'dart:convert';

import 'package:factify_mobile/api/client.dart';
import 'package:factify_mobile/app_services.dart';
import 'package:factify_mobile/auth/auth_service.dart';
import 'package:factify_mobile/history/history_store.dart';
import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/l10n/language_preference.dart';
import 'package:factify_mobile/models/submission.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:factify_mobile/screens/result_screen.dart';
import 'package:factify_mobile/screens/source_reader_screen.dart';
import 'package:factify_mobile/theme/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _quote = 'The ministry said no such scheme has been announced.';
const _url = 'https://www.thehindu.com/news/article1.ece';

final Map<String, dynamic> _evidenceJson = {
  'id': 'ev_1',
  'tier': 'C',
  'kind': 'fact_check',
  'direction': 'contradicts',
  'method': 'claim_review',
  'finding': 'Denied.',
  'citation_url': _url,
  'snapshot_id': 's',
  'source_excerpt': _quote,
  'source_anchor': {'paragraph_index': 4},
  'match_basis': {'metric': 'claim_similarity', 'value': 0.86, 'threshold': 0.62},
  'match_quality': 'STRONG',
  'publisher': 'The Hindu',
  'credibility': 'HIGH',
};

Map<String, dynamic> _sourceJson({bool complete = true, String? headline = 'No cash scheme'}) => {
  'url': _url,
  'domain': 'thehindu.com',
  'publisher': 'The Hindu',
  'headline': headline,
  'published_at': '2026-09-24T08:00:00Z',
  'read_minutes': 3,
  'paragraphs': complete
      ? ['Before the quote.', 'Officials were clear. $_quote They urged caution.', 'After it.']
      : [_quote],
  'quote': complete
      ? {'text': _quote, 'paragraph_index': 1, 'char_start': 22, 'char_end': 22 + _quote.length}
      : {'text': _quote, 'paragraph_index': 0, 'char_start': 0, 'char_end': _quote.length},
  'tier': 'C',
  'direction': 'contradicts',
  'credibility': 'HIGH',
  'complete': complete,
  'limitations': complete ? <String>[] : ['the passage is no longer on the page as quoted'],
};

AppServices _services(http.Response Function(http.Request) answer) {
  final client = FactifyClient(
    baseUrl: 'http://factify.test',
    httpClient: MockClient((request) async => answer(request)),
  );
  return AppServices(
    client: client,
    auth: AuthService(client: client, persist: false),
    language: LanguagePreference.inMemory(),
    history: HistoryStore(),
  );
}

Future<void> _show(WidgetTester tester, Widget child) async {
  tester.view.physicalSize = const Size(1080, 2600);
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

void main() {
  final evidence = Evidence.fromJson(_evidenceJson);

  testWidgets('the passage is read in its article, the quote marked', (tester) async {
    Uri? asked;
    await _show(
      tester,
      SourceReaderScreen(
        services: _services((request) {
          asked = request.url;
          return http.Response(jsonEncode(_sourceJson()), 200);
        }),
        caseId: 'case-1',
        evidence: evidence,
      ),
    );

    expect(asked!.path, '/v1/cases/case-1/sources/ev_1');
    expect(asked!.queryParameters['url'], _url);
    expect(find.text('The Hindu'), findsOneWidget);
    expect(find.text('thehindu.com'), findsOneWidget);
    expect(find.text('Refutes the claim'), findsOneWidget);
    expect(find.text('Highly credible'), findsOneWidget);
    expect(find.text('No cash scheme'), findsOneWidget);
    expect(find.text('Published Sep 24, 2026 · 3 min read'), findsOneWidget);
    expect(find.text('QUOTED IN YOUR RESULT'), findsOneWidget);
    expect(find.text('Paragraph 5 · match 0.86'), findsOneWidget);
    expect(find.text('Before the quote.'), findsOneWidget);
    expect(find.text('After it.'), findsOneWidget);
    expect(find.textContaining('Only the passage around the quote'), findsOneWidget);
    expect(find.text('Back to result'), findsOneWidget);
    expect(find.text('Open site'), findsOneWidget);
  });

  testWidgets('a page that will not open still shows the quote, and says so', (tester) async {
    await _show(
      tester,
      SourceReaderScreen(
        services: _services((_) => http.Response('{"detail": "down"}', 503)),
        caseId: 'case-1',
        evidence: evidence,
      ),
    );

    expect(find.textContaining(_quote), findsOneWidget);
    expect(find.textContaining("couldn't open this page just now"), findsOneWidget);
    expect(find.text('Open site'), findsOneWidget);
  });

  testWidgets('a page that changed since is said to have changed', (tester) async {
    await _show(
      tester,
      SourceReaderScreen(
        services: _services((_) => http.Response(jsonEncode(_sourceJson(complete: false)), 200)),
        caseId: 'case-1',
        evidence: evidence,
      ),
    );

    expect(find.textContaining('no longer carries the passage'), findsOneWidget);
  });

  testWidgets('a source on the result opens in the reader', (tester) async {
    final verdict = Verdict.fromJson({
      'case_id': 'case-9',
      'action': 'DO_NOT_SHARE',
      'action_reason': 'r',
      'rule_version': 'v',
      'confidence': 88,
      'claims': [
        {
          'id': 'cl_1',
          'text': 'Rs 5,000 a month for every woman.',
          'claim_type': 'EVENT',
          'status': 'CONTRADICTED',
          'severity': 'HIGH',
          'importance': 'HEADLINE',
          'reason': 'r',
          'confidence': 88,
          'strength': {'score': 0.9, 'band': 'STRONG', 'components': <Object>[], 'version': 'v'},
          'evidence': [_evidenceJson],
        },
      ],
      'advisories': <Object>[],
      'skipped': <Object>[],
      'retrieved_at': '2026-09-27T10:00:00Z',
    });
    await _show(
      tester,
      ResultScreen(
        services: _services((request) {
          if (request.url.path.contains('/sources/')) {
            return http.Response(jsonEncode(_sourceJson()), 200);
          }
          return http.Response('{}', 404);
        }),
        verdict: verdict,
        submission: Submission.text('Rs 5,000 a month for every woman.'),
      ),
    );

    await tester.scrollUntilVisible(
      find.text('Read'),
      300,
      scrollable: find
          .byWidgetPredicate((w) => w is Scrollable && w.axisDirection == AxisDirection.down)
          .first,
    );
    await tester.tap(find.text('Read'));
    await tester.pumpAndSettle();

    expect(find.byType(SourceReaderScreen), findsOneWidget);
    expect(find.text('QUOTED IN YOUR RESULT'), findsOneWidget);
  });
}
