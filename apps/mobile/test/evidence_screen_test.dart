/// The sources screen: each claim with its verdict, confidence and sources; the
/// teaching line, claim anchor and media match preview; and the timeline folded
/// under "How we checked" (M44, PLAN 1.7.4).
///
/// Each renders only from data the response carries. These tests hold both halves
/// of that rule: the element appears when its data is present, and nothing appears
/// — not a guess — when it is not.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/l10n/language_preference.dart';
import 'package:factify_mobile/models/submission.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:factify_mobile/screens/evidence_screen.dart';
import 'package:factify_mobile/widgets/evidence_timeline.dart';
import 'package:factify_mobile/widgets/teaching_line.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> _evidence({
  String id = 'ev_1',
  String kind = 'fact_check',
  String url = 'https://factchecker.example/1',
  String? publisher = 'Factchecker',
  String? observedAt = '2026-06-02T00:00:00Z',
  // The page's own date - what the timeline shows. `observedAt` is our fetch.
  String? publishedOn = '2026-06-02',
  Map<String, dynamic>? inputAnchor,
}) => {
  'id': id,
  'tier': 'C',
  'kind': kind,
  'direction': 'contradicts',
  'method': 'claim_review',
  'finding': 'Rated false.',
  'citation_url': url,
  'snapshot_id': 'snap_1',
  'source_excerpt': 'rated False on 2 June 2026',
  'source_anchor': {'char_start': 0, 'char_end': 26},
  'match_basis': {'metric': 'claim_overlap', 'value': 0.91, 'threshold': 0.55},
  'match_quality': 'STRONG',
  'publisher': publisher,
  'observed_at': observedAt,
  'published_on': publishedOn,
  'input_anchor': inputAnchor,
};

Map<String, dynamic> _claim({
  String type = 'QUOTE',
  String status = 'CONTRADICTED',
  List<Map<String, dynamic>> evidence = const [],
  List<String> citations = const [],
}) => {
  'id': 'cl_1',
  'text': 'The minister said the scheme was cancelled.',
  'claim_type': type,
  'status': status,
  'severity': 'HIGH',
  'importance': 'HEADLINE',
  'reason': 'A published fact-check rated this false.',
  'rule_id': 'r1',
  'rule_version': '2026.08.1',
  'strength': {
    'score': 0.82,
    'band': 'strong',
    'components': [
      {'name': 'tier_composition', 'value': 0.95, 'explanation': '1×C', 'citations': citations},
    ],
    'advisory_excluded': <String>[],
    'version': '2026.08.1',
  },
  'evidence': evidence,
};

Verdict _verdict({
  String action = 'DO_NOT_SHARE',
  List<Map<String, dynamic>> claims = const [],
  Map<String, dynamic>? recurrence,
}) => Verdict.fromJson({
  'case_id': 'case-1',
  'contract_version': '1.0',
  'action': action,
  'action_reason': 'Published sources contradict this.',
  'rule_version': '2026.08.1',
  'claims': claims,
  'advisories': const <Map<String, dynamic>>[],
  'skipped': const <Map<String, dynamic>>[],
  'completeness_note': null,
  'retrieved_at': '2026-08-18T10:00:00Z',
  'from_cache': false,
  'elapsed_ms': 1200,
  'recurrence': recurrence,
});

/// A one-pixel PNG, for a submission that carries a picture.
final Uint8List _pixel = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAMAASsJTYQAAAAASUVORK5CYII=',
);

Future<void> _open(
  WidgetTester tester,
  Verdict verdict, {
  Locale locale = const Locale('en'),
  Submission? submission,
}) async {
  tester.view.physicalSize = const Size(1080, 2340);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      locale: locale,
      supportedLocales: AppLocalizations.supportedLocales,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      home: EvidenceScreen(
        verdict: verdict,
        language: LanguagePreference.inMemory(),
        submission: submission,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _expandHowWeChecked(WidgetTester tester) async {
  await tester.scrollUntilVisible(find.text('How we checked'), 200);
  await tester.tap(find.text('How we checked'));
  await tester.pumpAndSettle();
}

void main() {
  group('the teaching line', () {
    test('names a technique only for a claim a source contradicted or recontextualised', () {
      Technique? of(String type, String status, {String kind = 'fact_check'}) => techniqueFor(
        Claim.fromJson(_claim(type: type, status: status, evidence: [_evidence(kind: kind)])),
      );

      expect(of('MEDIA', 'MISLEADING_CONTEXT', kind: 'media_match'), Technique.recycledMedia);
      expect(of('EVENT', 'MISLEADING_CONTEXT'), Technique.missingContext);
      expect(of('QUOTE', 'CONTRADICTED'), Technique.misattributedQuote);
      expect(of('ATTRIBUTION', 'CONTRADICTED'), Technique.misattributedQuote);
      expect(of('STATISTIC', 'CONTRADICTED'), Technique.twistedNumber);
      expect(of('IDENTITY', 'CONTRADICTED'), Technique.wrongIdentity);
      // EVENT is the catch-all type: a health myth is not a "distorted event".
      expect(of('EVENT', 'CONTRADICTED'), isNull);
      // Nothing to teach where nothing was found wrong, or nothing was decided.
      expect(of('QUOTE', 'SUPPORTED'), isNull);
      expect(techniqueFor(Claim.fromJson(_claim(status: 'UNVERIFIED'))), isNull);
      expect(of('OPINION', 'CONTRADICTED'), isNull);
    });

    test('no technique, in either language, calls anything true', () {
      for (final locale in const [Locale('en'), Locale('hi')]) {
        final l10n = lookupAppLocalizations(locale);
        for (final technique in Technique.values) {
          final (title, lesson) = techniqueWords(technique, l10n);
          for (final word in const ['true', 'True', 'सच', 'सही', 'सत्य']) {
            expect('$title $lesson', isNot(contains(word)), reason: '$technique, $locale');
          }
        }
      }
    });

    testWidgets('appears with the claim it describes', (tester) async {
      await _open(tester, _verdict(claims: [_claim(evidence: [_evidence()])]));

      expect(find.text("Words put in someone's mouth"), findsOneWidget);
    });
  });

  group('the timeline', () {
    test('orders every dated point, names sources, and leaves undated ones off', () {
      final verdict = _verdict(
        claims: [
          _claim(
            evidence: [
              _evidence(id: 'a', publishedOn: '2026-06-02'),
              _evidence(
                id: 'b',
                url: 'https://www.news.example/story',
                publisher: null,
                publishedOn: '2023-05-28',
              ),
              // Fetched, like every source, but carrying no date of its own.
              _evidence(id: 'c', publishedOn: null),
            ],
          ),
        ],
        recurrence: {
          'times_seen': 2,
          'first_verified_at': '2026-07-01T00:00:00Z',
          'distinct_captions': 1,
          'languages': <String>[],
          'summary': 'Seen twice.',
        },
      );

      final entries = timelineFor(verdict, lookupAppLocalizations(const Locale('en')));

      expect(entries.map((e) => e.title), [
        'news.example',
        'Factchecker',
        'First checked by Factify',
        'Evidence gathered for this result',
      ]);
    });

    testWidgets('is drawn from the dates the evidence carries, under How we checked', (tester) async {
      await _open(tester, _verdict(claims: [_claim(evidence: [_evidence()])]));

      // Folded away until asked for: a hurried reader does not need it.
      expect(find.text('Timeline'), findsNothing);
      await _expandHowWeChecked(tester);

      expect(find.text('Timeline'), findsOneWidget);
      expect(find.text('Evidence gathered for this result'), findsOneWidget);
    });

    testWidgets('is not drawn when nothing is dated beyond this check', (tester) async {
      await _open(tester, _verdict(action: 'SEND_TO_REVIEW', claims: [_claim(status: 'UNVERIFIED')]));
      await _expandHowWeChecked(tester);

      expect(find.text('Timeline'), findsNothing);
    });
  });

  group("the claim's anchor", () {
    testWidgets("marks the claim inside the reader's own message", (tester) async {
      const message = 'Forwarded: The minister said the scheme was cancelled. Share widely!';
      final start = message.indexOf('The minister');
      final end = message.indexOf('cancelled.') + 'cancelled.'.length;

      await _open(
        tester,
        _verdict(
          claims: [
            _claim(evidence: [_evidence(inputAnchor: {'char_start': start, 'char_end': end})]),
          ],
        ),
        submission: Submission.text(message),
      );

      expect(find.text('Where your submission says this'), findsOneWidget);
      // The words around the claim come from the message itself.
      expect(find.textContaining('Share widely!'), findsOneWidget);
    });

    testWidgets('gives the position when the message is not at hand', (tester) async {
      await _open(
        tester,
        _verdict(
          claims: [
            _claim(evidence: [_evidence(inputAnchor: {'page_number': 3})]),
          ],
        ),
      );

      expect(find.text('Page 3'), findsOneWidget);
    });

    testWidgets('shows nothing where the server located nothing', (tester) async {
      await _open(tester, _verdict(claims: [_claim(evidence: [_evidence()])]));

      expect(find.text('Where your submission says this'), findsNothing);
    });
  });

  group('each claim', () {
    testWidgets('shows its verdict, how sure, the reason and the quoted source', (tester) async {
      final claim = _claim(evidence: [_evidence()])
        ..['confidence'] = 89
        ..['explanation'] = 'Factchecker rated the quote false on 2 June.';
      await _open(tester, _verdict(claims: [claim]));

      expect(find.text('89% confidence'), findsOneWidget);
      expect(find.text('Factchecker rated the quote false on 2 June.'), findsOneWidget);
      expect(find.textContaining('rated False on 2 June 2026'), findsOneWidget);
      expect(find.text('Refutes'), findsOneWidget);
    });

    testWidgets('an unsettled claim shows no confidence figure', (tester) async {
      final claim = _claim(status: 'UNVERIFIED')..['confidence'] = 60;
      await _open(tester, _verdict(action: 'SEND_TO_REVIEW', claims: [claim]));

      expect(find.textContaining('% confidence'), findsNothing);
    });

    testWidgets('a claim that was never searched says so, not "no sources found"', (tester) async {
      // Only a result kept from before 1.4 carries this: every claim is checked now.
      final claim = _claim(status: 'UNVERIFIED')..['search'] = 'not_searched';
      await _open(tester, _verdict(action: 'SEND_TO_REVIEW', claims: [claim]));

      expect(find.text('Not checked'), findsOneWidget);
      expect(find.textContaining("This claim wasn't checked"), findsOneWidget);
      expect(find.textContaining("couldn't find enough reliable sources"), findsNothing);
    });

    testWidgets('a searched claim says how many sources were read', (tester) async {
      final claim = _claim(status: 'UNVERIFIED')
        ..['search'] = 'searched'
        ..['sources_looked_at'] = 6;
      await _open(tester, _verdict(action: 'SEND_TO_REVIEW', claims: [claim]));

      expect(find.text('We read 6 sources and none addressed this directly.'), findsOneWidget);
    });

    testWidgets('the same page cited twice does not crash the screen', (tester) async {
      // "Duplicate keys found": the old screen keyed each citation by evidence id,
      // and one page cited twice for a claim took the whole screen down.
      await _open(
        tester,
        _verdict(claims: [_claim(evidence: [_evidence(), _evidence()])]),
      );

      expect(tester.takeException(), isNull);
      expect(find.textContaining('rated False on 2 June 2026'), findsNWidgets(2));
    });
  });

  testWidgets('a media match shows the submitted picture beside it', (tester) async {
    await _open(
      tester,
      _verdict(
        action: 'SHARE_WITH_CONTEXT',
        claims: [
          _claim(
            type: 'MEDIA',
            status: 'MISLEADING_CONTEXT',
            evidence: [_evidence(kind: 'media_match')],
          ),
        ],
      ),
      submission: Submission.image(File('shared.png'), _pixel),
    );

    expect(find.text('Your picture'), findsOneWidget);
    expect(find.text('Matches a picture published earlier'), findsOneWidget);
    expect(find.text('Recycled picture'), findsOneWidget);
  });
}
