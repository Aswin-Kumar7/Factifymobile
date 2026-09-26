/// History (v5): the week summary behind the chart and recap, search, and deleting
/// one check by swiping it left. Everything is on the phone; nothing here talks to
/// a server.
library;

import 'package:factify_mobile/app_services.dart';
import 'package:factify_mobile/api/client.dart';
import 'package:factify_mobile/auth/auth_service.dart';
import 'package:factify_mobile/history/history_store.dart';
import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/l10n/language_preference.dart';
import 'package:factify_mobile/models/submission.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:factify_mobile/screens/history_screen.dart';
import 'package:factify_mobile/theme/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Verdict _verdict(String action, {int sources = 0}) => Verdict.fromJson({
  'case_id': 'c',
  'contract_version': '1.2',
  'action': action,
  'action_reason': 'r',
  'rule_version': 'v',
  'claims': [
    {
      'id': 'cl_1',
      'text': 'A claim.',
      'claim_type': 'EVENT',
      'status': 'UNVERIFIED',
      'severity': 'HIGH',
      'importance': 'HEADLINE',
      'reason': 'r',
      'strength': {'score': 0.5, 'band': 'WEAK', 'components': <Object>[], 'version': 'v'},
      'evidence': [
        for (var i = 0; i < sources; i++)
          {
            'id': 'ev_$i',
            'tier': 'D',
            'kind': 'WEB_SOURCE',
            'direction': 'contradicts',
            'method': 'reasoned',
            'finding': 'It says otherwise.',
            'citation_url': 'https://example$i.org/a',
            'source_excerpt': 'q',
          },
      ],
    },
  ],
  'advisories': <Object>[],
  'skipped': <Object>[],
  'retrieved_at': '2026-09-26T10:00:00Z',
  'from_cache': false,
  'elapsed_ms': 10,
});

Future<HistoryStore> _store(List<(String text, String action)> checks) async {
  final store = HistoryStore();
  for (final (text, action) in checks) {
    await store.add(Submission.text(text), _verdict(action, sources: 2));
  }
  return store;
}

void main() {
  test('the week counts each check under its verdict, and the stopped ones', () async {
    final store = await _store([
      ('One', 'DO_NOT_SHARE'),
      ('Two', 'SHARE_WITH_CONTEXT'),
      ('Three', 'SAFE_TO_SHARE'),
      ('Four', 'SEND_TO_REVIEW'),
    ]);

    final week = store.weekSummary();

    expect(week.total, 4);
    expect(week.stopped, 2);
    expect(week.count(FactVerdict.trueClaim), 1);
    expect(week.days, hasLength(7));
    expect(week.days.first.weekday, DateTime.monday);
    // Today's column holds all four, False at the base.
    final today = week.days.indexWhere((d) => DateUtils.isSameDay(d, week.today));
    expect(week.byDay[today].first, FactVerdict.falseClaim);
    expect(week.busiest.single, week.days[today]);
  });

  test('an empty week has no busiest day', () {
    expect(HistoryStore().weekSummary().busiest, isEmpty);
  });

  testWidgets('search finds a check by its words, and a swipe left deletes one', (tester) async {
    tester.view.physicalSize = const Size(1080, 2340);
    tester.view.devicePixelRatio = 2.625;
    addTearDown(tester.view.reset);
    final store = await _store([
      ('RBI withdraws Rs 500 notes', 'DO_NOT_SHARE'),
      ('Monsoon reaches Kerala early', 'SAFE_TO_SHARE'),
    ]);
    final client = FactifyClient(baseUrl: 'http://factify.test');
    final services = AppServices(
      client: client,
      auth: AuthService(client: client, persist: false),
      language: LanguagePreference.inMemory(),
      history: store,
    );
    await tester.pumpWidget(
      MaterialApp(
        theme: buildFactifyTheme(Brightness.light),
        supportedLocales: AppLocalizations.supportedLocales,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        home: HistoryScreen(services: services),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('This week · ${_range(store)}'), findsOneWidget);
    expect(find.textContaining('You stopped 1 false or misleading'), findsOneWidget);

    await tester.enterText(find.byType(TextField), 'monsoon');
    await tester.pumpAndSettle();
    expect(find.text('Monsoon reaches Kerala early'), findsOneWidget);
    expect(find.text('RBI withdraws Rs 500 notes'), findsNothing);

    await tester.enterText(find.byType(TextField), '');
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('RBI withdraws Rs 500 notes'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.drag(find.text('RBI withdraws Rs 500 notes'), const Offset(-200, 0));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').hitTestable());
    await tester.pumpAndSettle();

    expect(store.records.map((r) => r.summary), ['Monsoon reaches Kerala early']);
  });
}

String _range(HistoryStore store) {
  final week = store.weekSummary();
  String d(DateTime x) => '${x.day}';
  const months = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];
  final start = week.start;
  final end = week.end;
  return start.month == end.month
      ? '${d(start)}–${d(end)} ${months[end.month - 1]}'
      : '${d(start)} ${months[start.month - 1]} – ${d(end)} ${months[end.month - 1]}';
}
