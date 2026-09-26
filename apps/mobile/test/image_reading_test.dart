/// What was read in an uploaded picture is shown on the result, under "What we
/// checked".
///
/// A screenshot used to be checked for nothing, and the answer gave no sign of what,
/// if anything, had been read. These tests hold that the reading arrives from the
/// server's shape and is shown as read: labelled with what kind of picture it is and
/// whose name it carries, described, and its text quoted exactly.
library;

import 'dart:io';

import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/models/submission.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:factify_mobile/widgets/verdict_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const _forward =
    '*BREAKING NEWS*\nRBI has announced that all Rs 500 notes will be banned from '
    '1 October 2026.';

Map<String, dynamic> _payload(Map<String, dynamic>? reading) => {
  'case_id': 'case-1',
  'contract_version': '1.2',
  'action': 'DO_NOT_SHARE',
  'action_reason': 'Published sources contradict this.',
  'rule_version': 'r',
  'claims': const <Map<String, dynamic>>[],
  'advisories': const <Map<String, dynamic>>[],
  'skipped': const <Map<String, dynamic>>[],
  'retrieved_at': '2026-09-26T10:00:00Z',
  'from_cache': false,
  'elapsed_ms': 10,
  'image_reading': reading,
};

/// A picture's result, carrying [reading] as the server sends it.
Future<void> _show(
  WidgetTester tester,
  Map<String, dynamic> reading, {
  Locale locale = const Locale('en'),
}) {
  tester.view.physicalSize = const Size(1080, 4000);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
  return tester.pumpWidget(
    MaterialApp(
      locale: locale,
      supportedLocales: AppLocalizations.supportedLocales,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      home: Scaffold(
        body: SingleChildScrollView(
          child: VerdictCard(
            verdict: Verdict.fromJson(_payload(reading)..['action'] = 'SEND_TO_REVIEW'),
            kind: SubmissionKind.image,
          ),
        ),
      ),
    ),
  );
}

void main() {
  test('the reading is parsed from the response, and absent for text checks', () {
    final verdict = Verdict.fromJson(
      _payload({
        'text': _forward,
        'description': 'A WhatsApp forward in a group called Family Group.',
        'kind': 'CHAT_MESSAGE',
        'publisher': null,
        'language': 'en',
      }),
    );

    expect(verdict.imageReading?.text, _forward);
    expect(verdict.imageReading?.kind, 'CHAT_MESSAGE');
    expect(verdict.imageReading?.hasText, isTrue);
    expect(Verdict.fromJson(_payload(null)).imageReading, isNull);
  });

  testWidgets('the text is shown, labelled with the kind of picture and its source', (
    tester,
  ) async {
    await _show(tester, {
      'text': '#FakeNews! No breakfast was served to world leaders at the summit venue.',
      'description': 'A post by MEA FactCheck.',
      'kind': 'SOCIAL_POST',
      'publisher': 'MEA FactCheck',
    });

    expect(find.text('What we checked · Image'), findsOneWidget);
    expect(find.text('Text in the picture'), findsOneWidget);
    expect(find.text('Social media post'), findsOneWidget);
    expect(find.text('Shows: MEA FactCheck'), findsOneWidget);
    expect(find.text('A post by MEA FactCheck.'), findsOneWidget);
    expect(find.textContaining('No breakfast was served'), findsOneWidget);
  });

  testWidgets('a long screenshot is folded, and opens in full on request', (tester) async {
    final long = List.generate(40, (i) => 'Line ${i + 1} of the article').join('\n');
    await _show(tester, {'text': long, 'kind': 'NEWS_ARTICLE'});

    expect(find.textContaining('Line 40 of'), findsNothing);

    await tester.tap(find.text('Show all the text'));
    await tester.pump();

    expect(find.textContaining('Line 40 of'), findsOneWidget);
    expect(find.text('Show less'), findsOneWidget);
  });

  testWidgets('a picture with no text says the picture itself was checked', (tester) async {
    await _show(tester, {'text': '', 'description': 'A flooded street.', 'kind': 'PHOTO'});

    expect(find.text('Photo'), findsOneWidget);
    expect(
      find.text('We found no text in this picture, so we checked the picture itself.'),
      findsOneWidget,
    );
  });

  testWidgets("the server's own question about a picture is never shown as its text", (
    tester,
  ) async {
    // A landscape with no text: its one claim is the server asking whether the
    // picture was published before. That sentence was quoted as "Text in the
    // picture" on the phone (2026-09-27).
    const question =
        'This image has been published before, at a date and by a publisher that can be cited.';
    tester.view.physicalSize = const Size(1080, 4000);
    tester.view.devicePixelRatio = 2.625;
    addTearDown(tester.view.reset);
    final payload = _payload({'text': '', 'description': 'Two green hills.', 'kind': 'OTHER'})
      ..['action'] = 'SEND_TO_REVIEW'
      ..['claims'] = [
        {
          'id': 'cl_media',
          'text': question,
          'claim_type': 'MEDIA',
          'status': 'UNVERIFIED',
          'severity': 'LOW',
          'importance': 'MAIN_THESIS',
          'reason': 'No earlier copy found.',
          'strength': {'score': 0.0, 'band': 'none', 'components': <Object>[], 'version': 'v'},
          'evidence': <Object>[],
        },
      ];
    await tester.pumpWidget(
      MaterialApp(
        supportedLocales: AppLocalizations.supportedLocales,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        home: Scaffold(
          body: SingleChildScrollView(
            child: VerdictCard(verdict: Verdict.fromJson(payload), kind: SubmissionKind.image),
          ),
        ),
      ),
    );

    expect(find.text('Two green hills.'), findsOneWidget);
    expect(find.text('Text in the picture'), findsNothing);
    expect(find.textContaining('published before'), findsNothing);
  });

  testWidgets('in Hindi, the labels are Hindi and the Devanagari text is shown as read', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.625;
    addTearDown(tester.view.reset);

    const hindi =
        'प्रधानमंत्री मोदी ने घोषणा की है कि 1 अक्टूबर 2026 से देश के सभी छात्रों को हर '
        'महीने 5000 रुपये मिलेंगे।';
    await _show(tester, {
      'text': hindi,
      'kind': 'CHAT_MESSAGE',
      'language': 'hi',
    }, locale: const Locale('hi'));

    expect(find.text('हमने क्या जाँचा · तस्वीर'), findsOneWidget);
    expect(find.text('चैट फ़ॉरवर्ड'), findsOneWidget);
    expect(find.textContaining(hindi), findsOneWidget);
  });

  group('a picture is named by what it says, never by its file name', () {
    final picture = Submission.image(File('/cache/share-1727-IMG-20260927-WA0003.jpg'), null);
    Map<String, dynamic> claim(String text, String importance) => {
      'id': 'cl_$importance',
      'text': text,
      'claim_type': 'EVENT',
      'status': 'SUPPORTED',
      'severity': 'HIGH',
      'importance': importance,
      'reason': 'Reported.',
      'strength': {'score': 0.8, 'band': 'STRONG', 'components': const [], 'version': 'v'},
      'evidence': const <Map<String, dynamic>>[],
    };

    test('before the check it has no name of its own', () {
      expect(picture.summary, '');
      expect(Submission.document(File('/cache/share-1727-circular.pdf')).summary, 'circular.pdf');
    });

    test('after it, the headline claim found in it', () {
      final verdict = Verdict.fromJson(
        _payload({'text': 'x', 'description': 'A TV graphic.'})
          ..['claims'] = [
            claim('Rohit Sharma lifted the trophy.', 'SUPPORTING_DETAIL'),
            claim('India won the T20 World Cup.', 'HEADLINE'),
          ],
      );
      expect(picture.summaryWith(verdict), 'India won the T20 World Cup.');
    });

    test('with nothing to check in it, what it shows', () {
      final verdict = Verdict.fromJson(
        _payload({'text': '', 'description': 'A hillside at sunset.'}),
      );
      expect(picture.summaryWith(verdict), 'A hillside at sunset.');
    });
  });
}
