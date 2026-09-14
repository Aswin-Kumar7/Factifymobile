/// Client-side tests for the design law.
///
/// The server enforces these rules in its types; these tests check that the
/// interface does not undo them. The failure mode they exist to catch is not a
/// crash — it is a screen that renders an honest payload dishonestly. A
/// translation counts: a Hindi headline that says "true" breaks the law exactly
/// as an English one would.
library;

import 'dart:convert';

import 'package:facify_mobile/api/client.dart';
import 'package:facify_mobile/l10n/app_localizations.dart';
import 'package:facify_mobile/l10n/language_preference.dart';
import 'package:facify_mobile/main.dart';
import 'package:facify_mobile/models/verdict.dart';
import 'package:facify_mobile/screens/evidence_screen.dart';
import 'package:facify_mobile/widgets/advisory_panel.dart';
import 'package:facify_mobile/widgets/language_menu.dart';
import 'package:facify_mobile/widgets/verdict_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// A response shaped exactly as the server emits one.
Map<String, dynamic> _payload({
  String action = 'DO_NOT_SHARE',
  List<Map<String, dynamic>> claims = const [],
  List<Map<String, dynamic>> advisories = const [],
  List<Map<String, dynamic>> skipped = const [],
  String? completenessNote,
}) => {
  'case_id': 'case-1',
  'contract_version': '1.0',
  'action': action,
  'action_reason': 'Published sources contradict this.',
  'rule_version': '2026.08.1',
  'claims': claims,
  'advisories': advisories,
  'skipped': skipped,
  'completeness_note': completenessNote,
  'retrieved_at': '2026-08-18T10:00:00Z',
  'from_cache': false,
  'elapsed_ms': 1200,
};

Map<String, dynamic> _claim({
  String status = 'CONTRADICTED',
  List<Map<String, dynamic>> evidence = const [],
}) => {
  'id': 'cl_1',
  'text': 'The scheme was cancelled on Friday.',
  'claim_type': 'EVENT',
  'status': status,
  'severity': 'HIGH',
  'importance': 'HEADLINE',
  'reason': 'A published fact-check rated this false.',
  'rule_id': 'r1',
  'rule_version': '2026.08.1',
  'strength': {
    'score': 0.82,
    'band': 'STRONG',
    'components': [
      {'name': 'tier_composition', 'value': 0.95, 'explanation': 'one Tier C finding'},
    ],
    'advisory_excluded': <String>[],
    'version': '2026.08.1',
  },
  'evidence': evidence,
};

Map<String, dynamic> _evidence() => {
  'id': 'ev_1',
  'tier': 'C',
  'kind': 'fact_check',
  'direction': 'contradicts',
  'method': 'claim_review',
  'finding': 'Rated false.',
  'citation_url': 'https://factchecker.example/1',
  'snapshot_id': 'snap_1',
  'source_excerpt': 'rated False on 2 June 2026',
  'source_anchor': {'char_start': 0, 'char_end': 26},
  'match_basis': {'metric': 'claim_overlap', 'value': 0.91, 'threshold': 0.55},
  'match_quality': 'STRONG',
  'publisher': 'Factchecker',
  'observed_at': '2026-06-02T00:00:00Z',
};

Map<String, dynamic> _advisory() => {
  'id': 'adv_1',
  'provider': 'local_forensics',
  'signal': 'ADVISORY_SUSPICION',
  'note': 'Noise levels vary across this image.',
  'score': 0.87,
  'excluded_note': 'Forensic signal - not used in this verdict.',
};

const Locale _english = Locale('en');
const Locale _hindi = Locale('hi');

/// [home] under the app's own localization setup, so it renders exactly the
/// strings a phone set to [locale] would show.
Widget _app(Widget home, {Locale locale = _english}) => MaterialApp(
  locale: locale,
  supportedLocales: AppLocalizations.supportedLocales,
  localizationsDelegates: AppLocalizations.localizationsDelegates,
  home: home,
);

Future<void> _pump(WidgetTester tester, Widget child, {Locale locale = _english}) =>
    tester.pumpWidget(_app(Scaffold(body: SingleChildScrollView(child: child)), locale: locale));

/// A result card whose actions do nothing.
VerdictCard _card(Verdict verdict) => VerdictCard(
  verdict: verdict,
  onSeeEvidence: () {},
  onShareCorrection: () {},
  onReportForReview: () {},
);

/// A 411-dp-wide phone: the width the longer Hindi strings have to fit into.
/// [height] is in physical pixels; a tall one lays out a whole scrolling screen,
/// including the parts a real phone would build only once scrolled to.
void _phoneSized(WidgetTester tester, {double height = 2340}) {
  tester.view.physicalSize = Size(1080, height);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
}

void main() {
  group('parsing the contract', () {
    test('advisories parse into a type that is not Evidence', () {
      final verdict = Verdict.fromJson(_payload(advisories: [_advisory()]));

      expect(verdict.advisories, hasLength(1));
      // The structural guarantee. `Advisory` shares no supertype with
      // `Evidence`, so this is not merely false — there is no assignment
      // between them that would compile.
      expect(verdict.advisories.first, isNot(isA<Evidence>()));
      expect(verdict.allEvidence, isEmpty);
    });

    test('an advisory never appears in a claim evidence list', () {
      final verdict = Verdict.fromJson(
        _payload(
          claims: [
            _claim(evidence: [_evidence()]),
          ],
          advisories: [_advisory()],
        ),
      );

      expect(verdict.allEvidence, hasLength(1));
      expect(verdict.allEvidence.every((e) => e.citationUrl.isNotEmpty), isTrue);
    });

    test('a decisive claim arrives with citations', () {
      final verdict = Verdict.fromJson(
        _payload(
          claims: [
            _claim(evidence: [_evidence()]),
          ],
        ),
      );

      final claim = verdict.claims.single;
      expect(claim.isDecisive, isTrue);
      expect(claim.evidence, isNotEmpty);
    });

    test('abstention is distinguishable from a finding of falsehood', () {
      final abstained = Verdict.fromJson(
        _payload(
          action: 'SEND_TO_REVIEW',
          claims: [_claim(status: 'UNVERIFIED')],
        ),
      );
      final contradicted = Verdict.fromJson(
        _payload(
          claims: [
            _claim(evidence: [_evidence()]),
          ],
        ),
      );

      expect(abstained.abstained, isTrue);
      expect(abstained.action.isConclusion, isFalse);
      expect(contradicted.abstained, isFalse);
      expect(contradicted.action.isConclusion, isTrue);
    });

    test('a skipped check makes the run incomplete', () {
      final verdict = Verdict.fromJson(
        _payload(
          skipped: [
            {'check': 'claim_extraction', 'reason': 'not configured'},
          ],
          completenessNote: 'Not everything could be checked.',
        ),
      );

      expect(verdict.isComplete, isFalse);
      expect(verdict.skipped.single.check, 'claim_extraction');
    });

    test('the payload round-trips through real JSON', () {
      final verdict = Verdict.fromJson(
        jsonDecode(
              jsonEncode(
                _payload(
                  claims: [
                    _claim(evidence: [_evidence()]),
                  ],
                ),
              ),
            )
            as Map<String, dynamic>,
      );

      expect(verdict.caseId, 'case-1');
      expect(verdict.retrievedAt.year, 2026);
    });
  });

  group('the advisory panel', () {
    testWidgets('always shows its exclusion header, collapsed', (tester) async {
      await _pump(tester, AdvisoryPanel(advisories: [Advisory.fromJson(_advisory())]));

      // Visible without expanding anything. A caveat that only appears once the
      // reader opens the panel is a caveat most readers never see.
      expect(find.textContaining('not used in the verdict'), findsOneWidget);
    });

    testWidgets('never renders the numeric score', (tester) async {
      await _pump(tester, AdvisoryPanel(advisories: [Advisory.fromJson(_advisory())]));
      await tester.tap(find.byType(ExpansionTile));
      await tester.pumpAndSettle();

      // 0.87 beside a warning icon is a verdict in everything but name.
      expect(find.textContaining('0.87'), findsNothing);
      expect(find.textContaining('Noise levels vary'), findsOneWidget);
    });

    testWidgets('renders nothing when there are no signals', (tester) async {
      await _pump(tester, const AdvisoryPanel(advisories: []));

      expect(find.byType(ExpansionTile), findsNothing);
    });
  });

  group('the verdict card', () {
    testWidgets('never claims something is true, only that nothing contradicts it', (tester) async {
      await _pump(
        tester,
        VerdictCard(
          verdict: Verdict.fromJson(_payload(action: 'SAFE_TO_SHARE')),
          onSeeEvidence: () {},
          onShareCorrection: () {},
          onReportForReview: () {},
        ),
      );

      expect(find.textContaining('Nothing contradicts this'), findsOneWidget);
      expect(find.textContaining('True'), findsNothing);
      expect(find.textContaining('Verified'), findsNothing);
    });

    testWidgets('states when the evidence was retrieved', (tester) async {
      await _pump(
        tester,
        VerdictCard(
          verdict: Verdict.fromJson(_payload()),
          onSeeEvidence: () {},
          onShareCorrection: () {},
          onReportForReview: () {},
        ),
      );

      // Without this the card is a claim about the present made from evidence
      // about the past.
      expect(find.textContaining('Evidence retrieved'), findsOneWidget);
    });

    testWidgets('surfaces an incomplete run rather than hiding it', (tester) async {
      await _pump(
        tester,
        VerdictCard(
          verdict: Verdict.fromJson(
            _payload(
              skipped: [
                {'check': 'factcheck', 'reason': 'not configured'},
              ],
              completenessNote: 'Not everything could be checked. factcheck was not checked.',
            ),
          ),
          onSeeEvidence: () {},
          onShareCorrection: () {},
          onReportForReview: () {},
        ),
      );

      expect(find.textContaining('Not everything could be checked'), findsOneWidget);
    });

    testWidgets('an abstaining case reads as undecided, not as danger', (tester) async {
      await _pump(
        tester,
        VerdictCard(
          verdict: Verdict.fromJson(_payload(action: 'SEND_TO_REVIEW')),
          onSeeEvidence: () {},
          onShareCorrection: () {},
          onReportForReview: () {},
        ),
      );

      expect(find.textContaining('Not enough evidence to decide'), findsOneWidget);
      // No correction to share when nothing was established.
      expect(find.text('Share correction'), findsNothing);
    });
  });

  group('the design law, in Hindi', () {
    testWidgets('an abstention still reads as undecided, not as danger', (tester) async {
      await _pump(
        tester,
        _card(Verdict.fromJson(_payload(action: 'SEND_TO_REVIEW'))),
        locale: _hindi,
      );

      expect(find.text('निर्णय के लिए पर्याप्त साक्ष्य नहीं'), findsOneWidget);
      expect(find.textContaining('Not enough evidence'), findsNothing);
      expect(find.text('सुधार साझा करें'), findsNothing);
    });

    testWidgets('"nothing contradicts this" is not translated into "true"', (tester) async {
      await _pump(
        tester,
        _card(Verdict.fromJson(_payload(action: 'SAFE_TO_SHARE'))),
        locale: _hindi,
      );

      expect(find.text('इसका कोई खंडन नहीं मिला'), findsOneWidget);
      // सच and सही say "true"; सत्य is "truth", and also begins सत्यापित, "verified".
      for (final word in const ['सच', 'सही', 'सत्य']) {
        expect(find.textContaining(word), findsNothing, reason: 'the card says "$word"');
      }
    });

    testWidgets('states when the evidence was retrieved, and what is still English', (
      tester,
    ) async {
      await _pump(tester, _card(Verdict.fromJson(_payload())), locale: _hindi);

      expect(find.textContaining('साक्ष्य जुटाए गए'), findsOneWidget);
      // Reasons still arrive from the server in English (B5), and the card says
      // so rather than switching language halfway down without a word.
      expect(find.text('नीचे के कुछ विवरण अभी सिर्फ़ अंग्रेज़ी में हैं।'), findsOneWidget);
    });

    testWidgets('the advisory exclusion header survives translation', (tester) async {
      await _pump(
        tester,
        AdvisoryPanel(advisories: [Advisory.fromJson(_advisory())]),
        locale: _hindi,
      );

      // Collapsed, like the English test: the caveat may not wait for a tap.
      expect(find.textContaining('निर्णय में उपयोग नहीं'), findsOneWidget);

      await tester.tap(find.byType(ExpansionTile));
      await tester.pumpAndSettle();
      expect(find.textContaining('0.87'), findsNothing);
    });
  });

  group('languages (PLAN 1.7.6)', () {
    testWidgets('an English card carries no English-only note', (tester) async {
      await _pump(tester, _card(Verdict.fromJson(_payload())));

      expect(find.textContaining('shown in English'), findsNothing);
    });

    testWidgets('the toggle switches the interface, and the language sent with a check', (
      tester,
    ) async {
      _phoneSized(tester);
      final sent = <Map<String, dynamic>>[];
      final client = FacifyClient(
        baseUrl: 'http://facify.test',
        httpClient: MockClient((request) async {
          if (request.url.path == '/readyz') {
            return http.Response('{"ready": true, "missing": []}', 200);
          }
          sent.add(jsonDecode(request.body) as Map<String, dynamic>);
          return http.Response(jsonEncode(_payload(action: 'SEND_TO_REVIEW')), 200);
        }),
      );

      await tester.pumpWidget(FacifyApp(language: LanguagePreference.inMemory(), client: client));
      await tester.pumpAndSettle();
      expect(find.textContaining('never from a model score'), findsOneWidget);

      await tester.tap(find.byType(LanguageMenu));
      await tester.pumpAndSettle();
      await tester.tap(find.text('हिन्दी'));
      await tester.pumpAndSettle();
      expect(find.textContaining('मॉडल स्कोर से कभी नहीं'), findsOneWidget);

      await tester.enterText(find.byType(TextField), 'The scheme was cancelled on Friday.');
      await tester.pump();
      await tester.tap(find.text('इसे जाँचें'));
      await tester.pumpAndSettle();

      expect(sent.single['language'], 'hi');
      expect(find.text('निर्णय के लिए पर्याप्त साक्ष्य नहीं'), findsOneWidget);
    });

    testWidgets('with nothing chosen, the phone language decides, falling back to English', (
      tester,
    ) async {
      _phoneSized(tester);
      addTearDown(tester.platformDispatcher.clearLocalesTestValue);
      final client = FacifyClient(
        baseUrl: 'http://facify.test',
        httpClient: MockClient((_) async => http.Response('{"ready": true, "missing": []}', 200)),
      );

      tester.platformDispatcher.localesTestValue = const [Locale('hi', 'IN')];
      await tester.pumpWidget(FacifyApp(language: LanguagePreference.inMemory(), client: client));
      await tester.pumpAndSettle();
      expect(find.textContaining('मॉडल स्कोर से कभी नहीं'), findsOneWidget);

      // A phone in a language Facify has no strings for gets English.
      tester.platformDispatcher.localesTestValue = const [Locale('ta', 'IN')];
      await tester.pumpAndSettle();
      expect(find.textContaining('never from a model score'), findsOneWidget);
    });

    testWidgets('the result and the evidence lay out at phone width, in both languages and '
        'right to left', (tester) async {
      _phoneSized(tester, height: 12000);
      final verdict = Verdict.fromJson(
        _payload(
          claims: [
            _claim(evidence: [_evidence()]),
          ],
          advisories: [_advisory()],
          skipped: [
            {'check': 'factcheck', 'reason': 'not configured'},
          ],
          completenessNote: 'Not everything could be checked.',
        ),
      );

      for (final locale in const [_english, _hindi]) {
        for (final direction in TextDirection.values) {
          for (final screen in <Widget>[
            Scaffold(body: SingleChildScrollView(child: _card(verdict))),
            EvidenceScreen(verdict: verdict, language: LanguagePreference.inMemory()),
          ]) {
            // An overflowing row is reported to the framework, which fails the
            // test and names the offending widget. Taking the exception here
            // would keep only its message and lose that name.
            printOnFailure('${screen.runtimeType}, $locale, ${direction.name}');
            await tester.pumpWidget(
              _app(Directionality(textDirection: direction, child: screen), locale: locale),
            );
            await tester.pumpAndSettle();
          }
        }
      }
    });
  });
}
