/// Client-side tests for the design law.
///
/// The server enforces these rules in its types; these tests check that the
/// interface does not undo them. The failure mode they exist to catch is not a
/// crash — it is a screen that renders an honest payload dishonestly. The law now:
/// True, False and Misleading appear only with the sources beneath them, and
/// "Unconfirmed" never reads as either. A translation counts: a Hindi card that
/// says "true" for an abstention breaks the law exactly as an English one would.
library;

import 'dart:convert';

import 'package:factify_mobile/api/client.dart';
import 'package:factify_mobile/app_services.dart';
import 'package:factify_mobile/auth/auth_service.dart';
import 'package:factify_mobile/history/history_store.dart';
import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/l10n/language_preference.dart';
import 'package:factify_mobile/main.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:factify_mobile/screens/evidence_screen.dart';
import 'package:factify_mobile/screens/result_screen.dart';
import 'package:factify_mobile/widgets/advisory_panel.dart';
import 'package:factify_mobile/widgets/correction_card.dart';
import 'package:factify_mobile/widgets/correction_sheet.dart';
import 'package:factify_mobile/widgets/verdict_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:share_plus/share_plus.dart';

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

Map<String, dynamic> _evidence({String direction = 'contradicts'}) => {
  'id': 'ev_1',
  'tier': 'C',
  'kind': 'fact_check',
  'direction': direction,
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
    tester.pumpWidget(
      _app(
        Scaffold(body: SingleChildScrollView(child: child)),
        locale: locale,
      ),
    );

/// A claim was found and no source settled it.
Verdict _abstention({String? search}) => Verdict.fromJson(
  _payload(
    action: 'SEND_TO_REVIEW',
    claims: [
      _claim(status: 'UNVERIFIED')
        ..['importance'] = 'HEADLINE'
        ..['search'] = search,
    ],
  ),
);

AppServices _services() {
  final client = FactifyClient(baseUrl: 'http://factify.test');
  return AppServices(
    client: client,
    auth: AuthService(client: client, persist: false),
    language: LanguagePreference.inMemory(),
    history: HistoryStore(),
  );
}

/// A result whose actions do nothing.
VerdictCard _card(Verdict verdict) => VerdictCard(verdict: verdict, onReportForReview: () {});

/// The verdict itself - word, confidence, subhead, summary - apart from the
/// explanations under it.
Finder _inHeader(Finder finder) =>
    find.descendant(of: find.byKey(const ValueKey('verdict-header')), matching: finder);

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
    Verdict confirmed() => Verdict.fromJson(
      _payload(
        action: 'SAFE_TO_SHARE',
        claims: [
          _claim(
            status: 'SUPPORTED',
            evidence: [_evidence(direction: 'supports')],
          ),
        ],
      )..addAll({'verdict': 'TRUE', 'confidence': 89, 'summary': 'Two outlets report it.'}),
    );

    testWidgets('says True with how sure, and the sources it rests on', (tester) async {
      await _pump(tester, _card(confirmed()));

      expect(find.text('True'), findsOneWidget);
      expect(find.text('89%'), findsOneWidget);
      expect(find.text('Two outlets report it.'), findsOneWidget);
      // The verdict is never asked to be believed on its own.
      expect(find.text('Factchecker'), findsOneWidget);
      expect(find.text('Supports'), findsOneWidget);
    });

    testWidgets('says False, with the source that refutes it', (tester) async {
      await _pump(
        tester,
        _card(
          Verdict.fromJson(
            _payload(
              claims: [
                _claim(evidence: [_evidence()]),
              ],
            )..addAll({'verdict': 'FALSE', 'confidence': 78}),
          ),
        ),
      );

      expect(_inHeader(find.text('False')), findsOneWidget);
      expect(find.text('78%'), findsOneWidget);
      expect(find.text('Refutes'), findsOneWidget);
    });

    testWidgets('states when the check was made', (tester) async {
      await _pump(tester, _card(Verdict.fromJson(_payload())));

      // Without this the card is a claim about the present made from evidence
      // about the past.
      expect(find.textContaining(RegExp(r'^Checked \d')), findsOneWidget);
    });

    testWidgets('surfaces an incomplete run rather than hiding it', (tester) async {
      await _pump(
        tester,
        _card(
          Verdict.fromJson(
            _payload(
              skipped: [
                {'check': 'factcheck', 'reason': 'not configured'},
              ],
              completenessNote: 'Not everything could be checked. factcheck was not checked.',
            ),
          ),
        ),
      );

      expect(find.textContaining('may be incomplete'), findsOneWidget);
    });

    testWidgets('an abstaining case reads as unconfirmed — not true, not false', (tester) async {
      await _pump(tester, _card(_abstention()));

      expect(_inHeader(find.text('Unconfirmed')), findsOneWidget);
      expect(find.text('True'), findsNothing);
      expect(find.text('False'), findsNothing);
      // No confidence figure when nothing was decided.
      expect(find.textContaining('%'), findsNothing);
      // No correction to share when nothing was established.
      expect(find.text('Share correction'), findsNothing);
    });

    testWidgets('with no claim in it, there is nothing to fact-check - not "unconfirmed"', (
      tester,
    ) async {
      final opinion = Verdict.fromJson(_payload(action: 'SEND_TO_REVIEW'));
      await _pump(tester, _card(opinion));

      expect(find.text('Nothing to fact-check'), findsOneWidget);
      expect(find.text('Unconfirmed'), findsNothing);
      expect(find.textContaining('caution'), findsNothing);
      expect(find.text('Why unconfirmed?'), findsNothing);
    });

    testWidgets('a picture whose only question was its own history has nothing to check', (
      tester,
    ) async {
      final picture = Verdict.fromJson(
        _payload(
          action: 'SEND_TO_REVIEW',
          claims: [
            _claim(status: 'UNVERIFIED')
              ..['claim_type'] = 'MEDIA'
              ..['text'] = 'This image has been published before.',
          ],
        )..['image_reading'] = {'text': '', 'description': 'A hillside at sunset.'},
      );
      await _pump(tester, _card(picture));

      expect(find.text('Nothing to fact-check'), findsOneWidget);
      expect(find.textContaining('found no claim in it'), findsOneWidget);
    });

    testWidgets('a picture that could not be read is not "nothing to check"', (tester) async {
      final unread = Verdict.fromJson(
        _payload(
          action: 'SEND_TO_REVIEW',
          skipped: [
            {'check': 'image_text', 'reason': 'the image could not be read (provider failed)'},
          ],
        ),
      );
      await _pump(tester, _card(unread));

      expect(find.text('Unconfirmed'), findsOneWidget);
      expect(find.text('Nothing to fact-check'), findsNothing);
    });

    testWidgets('a search that could not run says so, not "incomplete in time"', (tester) async {
      await _pump(
        tester,
        _card(
          Verdict.fromJson(
            _payload(
              action: 'SEND_TO_REVIEW',
              completenessNote: 'web_search skipped: provider error',
              claims: [
                _claim(status: 'UNVERIFIED')
                  ..['importance'] = 'HEADLINE'
                  ..['search'] = 'unavailable',
              ],
            ),
          ),
        ),
      );

      expect(_inHeader(find.textContaining("news search couldn't be reached")), findsOneWidget);
      expect(find.textContaining('in time'), findsNothing);
    });

    testWidgets('a wrong result can be reported from the card', (tester) async {
      var reported = 0;
      await _pump(tester, VerdictCard(verdict: confirmed(), onReportForReview: () => reported++));

      await tester.ensureVisible(find.text('Report wrong result'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Report wrong result'));
      expect(reported, 1);
    });
  });

  group('the design law, in Hindi', () {
    testWidgets('an abstention reads as unconfirmed, and never as true or false', (tester) async {
      await _pump(tester, _card(_abstention()), locale: _hindi);

      expect(_inHeader(find.text('अपुष्ट')), findsOneWidget);
      expect(find.textContaining('Unconfirmed'), findsNothing);
      expect(find.text('सुधार साझा करें'), findsNothing);
      // सच and सही say "true", झूठ says "false"; सत्य is "truth", and also begins
      // सत्यापित, "verified". The verdict itself never uses them. (The explanation
      // below it may: "this does not mean it is false" is the point of Unconfirmed.)
      for (final word in const ['सच', 'सही', 'सत्य', 'झूठ']) {
        expect(
          _inHeader(find.textContaining(word)),
          findsNothing,
          reason: 'the verdict says "$word"',
        );
      }
    });

    testWidgets('a confirmed claim is called true, in Hindi, with its sources', (tester) async {
      await _pump(
        tester,
        _card(
          Verdict.fromJson(
            _payload(
              action: 'SAFE_TO_SHARE',
              claims: [
                _claim(
                  status: 'SUPPORTED',
                  evidence: [_evidence(direction: 'supports')],
                ),
              ],
            )..addAll({'verdict': 'TRUE', 'confidence': 89}),
          ),
        ),
        locale: _hindi,
      );

      expect(_inHeader(find.text('सच')), findsOneWidget);
      expect(find.text('Factchecker'), findsOneWidget);
    });

    testWidgets('states when the check was made, and what is still English', (tester) async {
      await _pump(tester, _card(Verdict.fromJson(_payload())), locale: _hindi);

      expect(find.textContaining('को जाँचा गया'), findsOneWidget);
      // Summaries still arrive in the claim's language (B5), and the card says so
      // rather than switching language halfway down without a word.
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

  group('the correction card (M44, PLAN 1.7.5)', () {
    Verdict contradicted() => Verdict.fromJson(
      _payload(
        claims: [
          _claim(evidence: [_evidence()]),
        ],
        advisories: [_advisory()],
      ),
    );

    Widget correctionCard(Verdict verdict) => SizedBox(
      width: correctionCardWidth,
      child: CorrectionCard(verdict: verdict),
    );

    testWidgets('names the decided claim, who said so and when, and no advisory', (tester) async {
      await _pump(tester, correctionCard(contradicted()));

      expect(find.text('False'), findsOneWidget);
      expect(find.textContaining('The scheme was cancelled on Friday.'), findsOneWidget);
      expect(find.textContaining('Factchecker · factchecker.example'), findsOneWidget);
      expect(find.textContaining('Evidence retrieved'), findsOneWidget);
      // The picture leaves the app without the advisory panel's exclusion
      // header, so no forensic signal may travel on it.
      expect(find.textContaining('Noise levels vary'), findsNothing);
      expect(find.textContaining('local_forensics'), findsNothing);
    });

    testWidgets('a false claim is never called true, in Hindi', (tester) async {
      await _pump(tester, correctionCard(contradicted()), locale: _hindi);

      expect(find.text('झूठ'), findsOneWidget);
      for (final word in const ['सच', 'सही', 'सत्य']) {
        expect(find.textContaining(word), findsNothing, reason: 'the card says "$word"');
      }
    });

    test('the text beside it carries the links, or says nothing could be confirmed', () {
      final l10n = lookupAppLocalizations(_english);

      final text = correctionText(contradicted(), l10n);
      expect(text, startsWith('Checked with Factify:'));
      expect(text, contains('https://factchecker.example/1'));

      final undecided = Verdict.fromJson(
        _payload(
          action: 'SEND_TO_REVIEW',
          claims: [_claim(status: 'UNVERIFIED')],
        ),
      );
      expect(correctionText(undecided, l10n), contains('No published source could confirm'));
    });

    testWidgets('the sheet hands the share sheet a real picture, with the links as text', (
      tester,
    ) async {
      _phoneSized(tester);
      ShareParams? shared;
      await tester.pumpWidget(
        _app(
          Scaffold(
            body: CorrectionSheet(
              verdict: contradicted(),
              share: (params) async {
                shared = params;
                return ShareResultStatus.dismissed;
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Drawing the picture is real engine work, which completes only outside
      // the test's fake clock.
      await tester.runAsync(() async {
        await tester.tap(find.text('Share picture'));
        for (var i = 0; i < 300 && shared == null; i++) {
          await Future<void>.delayed(const Duration(milliseconds: 10));
        }
      });

      expect(shared, isNotNull, reason: 'the share sheet was never opened');
      final png = await tester.runAsync(() => shared!.files!.single.readAsBytes());
      expect(png!.sublist(0, 4), const [0x89, 0x50, 0x4E, 0x47], reason: 'not a PNG');
      expect(shared!.fileNameOverrides, const ['factify-correction.png']);
      expect(shared!.text, contains('https://factchecker.example/1'));
      await tester.pump();
    });

    testWidgets('missing context can be sent back too; an abstention cannot', (tester) async {
      Widget result(String action, List<Map<String, dynamic>> claims) => ResultScreen(
        services: _services(),
        verdict: Verdict.fromJson(_payload(action: action, claims: claims)),
      );

      await tester.pumpWidget(
        _app(
          result('SHARE_WITH_CONTEXT', [
            _claim(
              status: 'MISLEADING_CONTEXT',
              evidence: [_evidence(direction: 'context')],
            ),
          ]),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Share with context'), findsOneWidget);

      await tester.pumpWidget(_app(result('SEND_TO_REVIEW', [_claim(status: 'UNVERIFIED')])));
      await tester.pumpAndSettle();
      expect(find.text('Share with context'), findsNothing);
      expect(find.text('Share correction'), findsNothing);
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
      final client = FactifyClient(
        baseUrl: 'http://factify.test',
        httpClient: MockClient((request) async {
          if (request.url.path == '/readyz') {
            return http.Response('{"ready": true, "missing": []}', 200);
          }
          sent.add(jsonDecode(request.body) as Map<String, dynamic>);
          return http.Response(jsonEncode(_abstention().raw), 200);
        }),
      );

      await tester.pumpWidget(FactifyApp(language: LanguagePreference.inMemory(), client: client));
      await tester.pumpAndSettle();
      expect(find.text('What would you like to check?'), findsOneWidget);

      // One tap on the EN pill switches to Hindi.
      await tester.tap(find.text('EN'));
      await tester.pumpAndSettle();
      expect(find.text('आप क्या जाँचना चाहते हैं?'), findsOneWidget);

      await tester.enterText(find.byType(TextField), 'The scheme was cancelled on Friday.');
      await tester.pump();
      await tester.tap(find.text('अभी जाँचें'));
      await tester.pumpAndSettle();

      expect(sent.single['language'], 'hi');
      expect(_inHeader(find.text('अपुष्ट')), findsOneWidget);
    });

    testWidgets('with nothing chosen, the phone language decides, falling back to English', (
      tester,
    ) async {
      _phoneSized(tester);
      addTearDown(tester.platformDispatcher.clearLocalesTestValue);
      final client = FactifyClient(
        baseUrl: 'http://factify.test',
        httpClient: MockClient((_) async => http.Response('{"ready": true, "missing": []}', 200)),
      );

      tester.platformDispatcher.localesTestValue = const [Locale('hi', 'IN')];
      await tester.pumpWidget(FactifyApp(language: LanguagePreference.inMemory(), client: client));
      await tester.pumpAndSettle();
      expect(find.text('आप क्या जाँचना चाहते हैं?'), findsOneWidget);

      // A phone in a language Factify has no strings for gets English.
      tester.platformDispatcher.localesTestValue = const [Locale('ta', 'IN')];
      await tester.pumpAndSettle();
      expect(find.text('What would you like to check?'), findsOneWidget);
    });

    testWidgets('the result, the evidence and the correction lay out at phone width, in both '
        'languages and right to left', (tester) async {
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
            Scaffold(
              body: CorrectionSheet(
                verdict: verdict,
                share: (_) async => ShareResultStatus.dismissed,
              ),
            ),
          ]) {
            // An overflowing row is reported to the framework, which fails the
            // test and names the offending widget. Taking the exception here
            // would keep only its message and lose that name.
            printOnFailure('${screen.runtimeType}, $locale, ${direction.name}');
            await tester.pumpWidget(
              _app(
                Directionality(textDirection: direction, child: screen),
                locale: locale,
              ),
            );
            await tester.pumpAndSettle();
          }
        }
      }
    });
  });
}
