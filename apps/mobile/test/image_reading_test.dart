/// What was read in an uploaded picture is shown above the verdict about it.
///
/// A screenshot used to be checked for nothing, and the card beneath it gave no
/// sign of what, if anything, had been read. These tests hold that the reading
/// arrives from the server's shape and is shown as read: the text first, labelled
/// with what kind of picture it is and whose name it carries.
library;

import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:factify_mobile/widgets/image_reading_card.dart';
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

Future<void> _show(
  WidgetTester tester,
  ImageReading reading, {
  Locale locale = const Locale('en'),
}) => tester.pumpWidget(
  MaterialApp(
    locale: locale,
    supportedLocales: AppLocalizations.supportedLocales,
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    home: Scaffold(
      body: SingleChildScrollView(child: ImageReadingCard(reading: reading)),
    ),
  ),
);

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
    await _show(
      tester,
      const ImageReading(
        text: '#FakeNews! No breakfast was served to world leaders at the summit venue.',
        description: 'A post by MEA FactCheck.',
        kind: 'SOCIAL_POST',
        publisher: 'MEA FactCheck',
      ),
    );

    expect(find.text('What we read in your picture'), findsOneWidget);
    expect(find.text('Social media post'), findsOneWidget);
    expect(find.text('Shows: MEA FactCheck'), findsOneWidget);
    expect(find.text('A post by MEA FactCheck.'), findsOneWidget);
    expect(find.textContaining('No breakfast was served'), findsOneWidget);
  });

  testWidgets('a long screenshot is folded, and opens in full on request', (tester) async {
    final long = List.generate(20, (i) => 'Line ${i + 1} of the article').join('\n');
    await _show(tester, ImageReading(text: long, kind: 'NEWS_ARTICLE'));

    final folded = tester.widget<Text>(find.textContaining('Line 1 of'));
    expect(folded.maxLines, 8);

    await tester.tap(find.text('Show all the text'));
    await tester.pump();

    expect(tester.widget<Text>(find.textContaining('Line 1 of')).maxLines, isNull);
    expect(find.text('Show less'), findsOneWidget);
  });

  testWidgets('a picture with no text says the picture itself was checked', (tester) async {
    await _show(
      tester,
      const ImageReading(text: '', description: 'A flooded street.', kind: 'PHOTO'),
    );

    expect(find.text('Photo'), findsOneWidget);
    expect(
      find.text('We found no text in this picture, so we checked the picture itself.'),
      findsOneWidget,
    );
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
    await _show(
      tester,
      const ImageReading(text: hindi, kind: 'CHAT_MESSAGE', language: 'hi'),
      locale: const Locale('hi'),
    );

    expect(find.text('आपकी तस्वीर में हमने क्या पढ़ा'), findsOneWidget);
    expect(find.text('चैट फ़ॉरवर्ड'), findsOneWidget);
    expect(find.text(hindi), findsOneWidget);
  });
}
