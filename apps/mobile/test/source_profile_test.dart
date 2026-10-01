/// What is known about a link's website, on the result (2026-10-01): its name, on our
/// trusted list or not, what was observed, and that it is not part of the verdict.
library;

import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/models/submission.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:factify_mobile/theme/theme.dart';
import 'package:factify_mobile/widgets/verdict_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Verdict _verdict(Map<String, dynamic>? profile) => Verdict.fromJson({
  'case_id': 'case-1',
  'contract_version': '1.5',
  'action': 'SEND_TO_REVIEW',
  'action_reason': 'r',
  'rule_version': 'v',
  'claims': <Object>[],
  'advisories': <Object>[],
  'skipped': <Object>[],
  'retrieved_at': '2026-10-01T10:00:00Z',
  'source_profile': ?profile,
});

Future<void> _show(WidgetTester tester, Verdict verdict) {
  tester.view.physicalSize = const Size(1080, 5000);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
  return tester.pumpWidget(
    MaterialApp(
      theme: buildFactifyTheme(Brightness.light),
      supportedLocales: AppLocalizations.supportedLocales,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      home: Scaffold(
        body: SingleChildScrollView(
          child: VerdictCard(verdict: verdict, kind: SubmissionKind.link, submittedText: 'https://x.example/a'),
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('an unlisted site says so, with what was observed', (tester) async {
    await _show(
      tester,
      _verdict({
        'domain': 'dailyviralnews.in',
        'trusted': false,
        'level': 'MEDIUM',
        'findings': ["dailyviralnews.in is not on Factify's trusted-source list."],
        'warnings': ['Domain registered 20 days ago'],
      }),
    );
    expect(find.text('About this website'), findsOneWidget);
    expect(find.text('dailyviralnews.in'), findsOneWidget);
    expect(find.text('Not on our trusted list'), findsOneWidget);
    expect(find.text('Domain registered 20 days ago'), findsOneWidget);
  });

  testWidgets('a listed newsroom shows its level', (tester) async {
    await _show(
      tester,
      _verdict({
        'domain': 'indianexpress.com',
        'trusted': true,
        'trust': 'highly credible',
        'level': 'LOW',
        'findings': ["indianexpress.com is on Factify's trusted-source list (highly credible)."],
      }),
    );
    expect(find.text('Trusted · highly credible'), findsOneWidget);
  });

  testWidgets('no section for anything that is not a link', (tester) async {
    await _show(tester, _verdict(null));
    expect(find.text('About this website'), findsNothing);
  });
}
