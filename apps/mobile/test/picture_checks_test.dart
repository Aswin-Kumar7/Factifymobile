/// The picture checks on a result (contract 1.3): what was found about the picture
/// itself, shown beside the verdict, each check able to say "not checked", and a
/// raised signal amber - never red, never a verdict.
library;

import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/models/submission.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:factify_mobile/theme/theme.dart';
import 'package:factify_mobile/theme/tokens.dart';
import 'package:factify_mobile/widgets/picture_checks.dart';
import 'package:factify_mobile/widgets/verdict_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> _report({
  String kind = 'image',
  Map<String, dynamic>? credentials,
  Map<String, dynamic>? history,
  Map<String, dynamic>? detector,
  Map<String, dynamic>? editing,
  int? frames,
}) => {
  'kind': kind,
  'credentials':
      credentials ??
      {
        'status': 'untrusted',
        'signer': 'Test',
        'declares_ai': true,
        'generator': 'Test Image Model',
      },
  'history':
      history ??
      {
        'status': 'found',
        'pages': 4,
        'dated': 2,
        'earliest': {
          'url': 'https://www.reuters.com/2019/flood',
          'publisher': 'Reuters',
          'published_at': '2019-03-12T00:00:00Z',
          'days_before': 2756,
        },
      },
  'detector': detector ?? {'status': 'checked', 'generated': 0.91, 'face_swap': 0.12},
  'editing': editing ?? {'status': 'checked', 'uneven_noise': true, 'spectral_peaks': false},
  'frames': ?frames,
};

Verdict _verdict(Map<String, dynamic> report, {Map<String, dynamic>? speech}) =>
    Verdict.fromJson({
  'speech': ?speech,
  'case_id': 'case-1',
  'contract_version': '1.3',
  'action': 'SEND_TO_REVIEW',
  'action_reason': 'r',
  'rule_version': 'v',
  'claims': <Object>[],
  'advisories': <Object>[],
  'skipped': <Object>[],
  'retrieved_at': '2026-09-27T10:00:00Z',
  'image_reading': {'text': '', 'description': 'Flood water in a street.', 'kind': 'PHOTO'},
  'media_report': report,
});

Future<void> _show(WidgetTester tester, Verdict verdict, {Locale locale = const Locale('en')}) {
  tester.view.physicalSize = const Size(1080, 6000);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
  return tester.pumpWidget(
    MaterialApp(
      locale: locale,
      theme: buildFactifyTheme(Brightness.light),
      supportedLocales: AppLocalizations.supportedLocales,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      home: Scaffold(
        body: SingleChildScrollView(
          child: VerdictCard(verdict: verdict, kind: SubmissionKind.image),
        ),
      ),
    ),
  );
}

void main() {
  test('the report is read from the response, and absent from older ones', () {
    final report = _verdict(_report()).mediaReport!;
    expect(report.credentials.declaresAi, isTrue);
    expect(report.history.earliest!.publisher, 'Reuters');
    expect(report.history.earliest!.isOld, isTrue);
    expect(report.detector.generated, 0.91);
    expect(report.editing.unevenNoise, isTrue);
    expect(MediaReport.tryParse(null), isNull);
  });

  testWidgets('every check is shown with what it found', (tester) async {
    await _show(tester, _verdict(_report()));

    expect(find.text('Picture checks'), findsOneWidget);
    expect(find.text('Not part of the verdict'), findsOneWidget);
    expect(
      find.text('The file says it was made with an AI tool (Test Image Model)'),
      findsOneWidget,
    );
    expect(find.text("Present, but the signer isn't verified"), findsOneWidget);
    expect(find.text('Online since Mar 12, 2019 · Reuters'), findsOneWidget);
    expect(
      find.text('Not a new picture: it was online 7 years before this check.'),
      findsOneWidget,
    );
    expect(find.text('91% likely made by an AI image generator'), findsOneWidget);
    expect(find.text('12% likely a face was swapped or changed by AI'), findsOneWidget);
    expect(find.text("A detector's estimate, not a finding."), findsOneWidget);
    expect(
      find.text('Parts of the picture have uneven noise, which editing can cause'),
      findsOneWidget,
    );
    expect(find.textContaining('never change the verdict'), findsOneWidget);
  });

  testWidgets('a check that did not run says so, and nothing reads as clean', (tester) async {
    await _show(
      tester,
      _verdict(
        _report(
          credentials: {'status': 'none'},
          history: {'status': 'not_checked'},
          detector: {'status': 'not_checked'},
          editing: {'status': 'checked'},
        ),
      ),
    );

    expect(find.text('Not checked'), findsNWidgets(2));
    expect(find.text("None. That's normal: most pictures carry none."), findsOneWidget);
    expect(find.text('No uneven noise or unusual patterns found'), findsOneWidget);
    expect(find.textContaining('likely made by'), findsNothing);
  });

  testWidgets('a check that did not run says why (contract 1.5)', (tester) async {
    await _show(
      tester,
      _verdict(
        _report(
          credentials: {'status': 'none'},
          history: {'status': 'not_checked', 'why': 'off'},
          detector: {'status': 'not_checked', 'why': 'text_card'},
        ),
      ),
    );

    expect(find.text('Not checked'), findsNWidgets(2));
    expect(
      find.text(
        'Not needed: this is a text card or a screenshot, so the words in it are checked instead.',
      ),
      findsOneWidget,
    );
    expect(
      find.text('Searching for earlier copies is not set up on this server.'),
      findsOneWidget,
    );
  });

  testWidgets('a picture with nothing to check that looks AI-made says so at the top', (
    tester,
  ) async {
    await _show(
      tester,
      _verdict(
        _report(
          credentials: {'status': 'none'},
          history: {'status': 'none'},
          detector: {'status': 'checked', 'generated': 0.97, 'agreement': 'likely_ai'},
        ),
      ),
    );

    expect(find.text('Nothing to fact-check'), findsOneWidget);
    expect(
      find.text(
        'But our AI-picture check says this picture was likely made by AI. '
        'See the picture checks below.',
      ),
      findsOneWidget,
    );
  });

  testWidgets('a video with nothing to check and a computer voice says so at the top', (
    tester,
  ) async {
    await _show(
      tester,
      _verdict(
        _report(
          kind: 'video',
          frames: 4,
          credentials: {'status': 'none'},
          history: {'status': 'none'},
          detector: {
            'status': 'checked',
            'generated': 0.02,
            'agreement': 'no_sign',
            'voice': 0.9998,
            'machine_voice': true,
          },
        ),
      ),
    );

    expect(find.textContaining('the voice in this video was likely made by a computer'), findsOneWidget);
  });

  testWidgets("what is said in a video is shown with the video's text (contract 1.5)", (
    tester,
  ) async {
    await _show(
      tester,
      _verdict(
        _report(kind: 'video', frames: 4),
        speech: {'text': 'सरकार हर महिला को पाँच हज़ार रुपये देगी।', 'language': 'hi'},
      ),
    );

    expect(find.text('Said in the video'), findsOneWidget);
    expect(find.textContaining('सरकार हर महिला को'), findsOneWidget);
  });

  testWidgets('a video with nothing to check and a swapped face says so at the top', (
    tester,
  ) async {
    await _show(
      tester,
      _verdict(
        _report(
          kind: 'video',
          frames: 4,
          credentials: {'status': 'none'},
          history: {'status': 'none'},
          detector: {
            'status': 'checked',
            'generated': 0.02,
            'agreement': 'no_sign',
            'face_swap': 0.93,
            'faces': 2,
            'face_swapped': true,
          },
        ),
      ),
    );

    expect(find.textContaining('a face in this video was likely swapped'), findsOneWidget);
  });

  testWidgets('nothing is said at the top when the checks found no sign of AI', (tester) async {
    await _show(
      tester,
      _verdict(
        _report(
          credentials: {'status': 'none'},
          history: {'status': 'none'},
          detector: {'status': 'checked', 'generated': 0.02, 'agreement': 'no_sign'},
        ),
      ),
    );

    expect(find.textContaining('likely made by AI'), findsNothing);
  });

  testWidgets('no earlier copy is its own answer', (tester) async {
    await _show(tester, _verdict(_report(history: {'status': 'none'})));
    expect(find.text('No earlier copies found online'), findsOneWidget);
  });

  testWidgets('a video is named as one, with the frames it was checked on', (tester) async {
    await _show(tester, _verdict(_report(kind: 'video', frames: 3)));

    expect(find.text('What we checked · Video'), findsOneWidget);
    expect(find.text('Video checks'), findsOneWidget);
    expect(find.text('3 still frames · Not part of the verdict'), findsOneWidget);
  });

  testWidgets('a raised signal is amber, and nothing here is red', (tester) async {
    await _show(tester, _verdict(_report()));
    final k = FactifyTokens.light;
    final colours = tester
        .widgetList<Text>(
          find.descendant(of: find.byType(PictureChecks), matching: find.byType(Text)),
        )
        .map((t) => t.style?.color)
        .toSet();

    expect(colours, contains(k.mC));
    expect(colours, isNot(contains(k.fC)));
  });

  testWidgets('in Hindi', (tester) async {
    await _show(tester, _verdict(_report()), locale: const Locale('hi'));

    expect(find.text('तस्वीर की जाँच'), findsOneWidget);
    expect(find.text('यह डिटेक्टर का अनुमान है, निष्कर्ष नहीं।'), findsOneWidget);
    expect(find.textContaining('7 साल'), findsOneWidget);
  });
}
