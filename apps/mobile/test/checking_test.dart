/// The Checking screen drawn from what the server reports (v5, contract 1.3), and
/// "Notify me when ready".
///
/// Held here: the events are read from the stream, or polled when it fails; the
/// screen shows the step, each source and the evidence count the server reported
/// and nothing it did not; a source the check throws out is taken back; and a
/// person who asked to be told can leave, and is told.
library;

import 'dart:async';
import 'dart:convert';

import 'package:factify_mobile/api/check_events.dart';
import 'package:factify_mobile/api/client.dart';
import 'package:factify_mobile/app_services.dart';
import 'package:factify_mobile/auth/auth_service.dart';
import 'package:factify_mobile/checks/check_job.dart';
import 'package:factify_mobile/history/history_store.dart';
import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/l10n/language_preference.dart';
import 'package:factify_mobile/models/submission.dart';
import 'package:factify_mobile/notify/notify_preference.dart';
import 'package:factify_mobile/notify/ready_notifier.dart';
import 'package:factify_mobile/screens/checking_screen.dart';
import 'package:factify_mobile/theme/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Map<String, dynamic> _verdictJson() => {
  'case_id': 'case-1',
  'contract_version': '1.3',
  'action': 'SEND_TO_REVIEW',
  'action_reason': 'Not enough citable evidence to decide.',
  'rule_version': 'v',
  'claims': [
    {
      'id': 'cl_1',
      'text': 'RBI is withdrawing Rs 500 notes.',
      'claim_type': 'EVENT',
      'status': 'UNVERIFIED',
      'severity': 'HIGH',
      'importance': 'HEADLINE',
      'reason': 'Not enough citable evidence.',
      'strength': {'score': 0.0, 'band': 'WEAK', 'components': <Object>[], 'version': 'v'},
      'evidence': <Object>[],
    },
  ],
  'advisories': <Object>[],
  'skipped': <Object>[],
  'retrieved_at': '2026-09-27T10:00:00Z',
  'from_cache': false,
  'elapsed_ms': 10,
};

CheckEvent _event(int seq, Map<String, dynamic> json) => CheckEvent.fromJson({...json, 'seq': seq});

class _RecordingNotifier extends SilentNotifier {
  final announced = <String>[];
  var alive = 0;

  @override
  Future<void> keepAlive({required String language}) async => alive++;

  @override
  Future<void> ready(HistoryRecord record, {required String language}) async =>
      announced.add(record.summary);

  @override
  bool get appInForeground => false;
}

AppServices _services(
  http.Client server, {
  ReadyNotifier? notifier,
  bool notifyByDefault = false,
  HistoryStore? history,
}) {
  final client = FactifyClient(baseUrl: 'http://factify.test', httpClient: server);
  return AppServices(
    client: client,
    auth: AuthService(client: client, persist: false),
    language: LanguagePreference.inMemory(),
    history: history ?? HistoryStore(),
    notifier: notifier,
    notifyByDefault: NotifyPreference.inMemory(notifyByDefault),
  );
}

void main() {
  group('reading the events', () {
    test('a Server-Sent Events body is read one message at a time', () async {
      const body =
          'retry: 2000\n\n'
          ': waiting\n\n'
          'id: 1\nevent: step\ndata: {"type":"step","step":"read","seq":1}\n\n'
          'id: 2\nevent: source_started\n'
          'data: {"type":"source_started","publisher":"Alt News",'
          '"domain":"altnews.in","initials":"AN","seq":2}\n\n'
          'data: not json\n\n'
          'id: 3\nevent: done\ndata: {"type":"done","case_id":"c1","seq":3}\n\n';
      final events = await parseServerSentEvents(Stream.fromIterable(body.split('\n'))).toList();

      expect(events.map((e) => e.type), ['step', 'source_started', 'done']);
      expect(events[1].publisher, 'Alt News');
      expect(events[1].initials, 'AN');
      expect(events.last.caseId, 'c1');
    });

    test('the stream is followed to its end', () async {
      final server = MockClient.streaming((request, _) async {
        expect(request.url.path, '/v1/cases/k1/events');
        const body =
            'data: {"type":"step","step":"search","seq":1}\n\n'
            'data: {"type":"evidence_count","n":2,"seq":2}\n\n'
            'data: {"type":"done","case_id":"c1","seq":3}\n\n';
        return http.StreamedResponse(Stream.value(utf8.encode(body)), 200);
      });

      final events = await followCheck('http://factify.test', 'k1', connect: () => server).toList();

      expect(events.map((e) => e.type), ['step', 'evidence_count', 'done']);
      expect(events[1].count, 2);
    });

    test('when the stream is refused, the events are polled instead', () async {
      final asked = <String>[];
      final server = MockClient((request) async {
        asked.add(request.url.path);
        if (request.url.path.endsWith('/events')) return http.Response('', 404);
        final after = request.url.queryParameters['after'];
        return http.Response(
          jsonEncode(
            after == '0'
                ? {
                    'events': [
                      {'type': 'step', 'step': 'read', 'seq': 1},
                    ],
                    'finished': false,
                  }
                : {
                    'events': [
                      {'type': 'done', 'case_id': 'c1', 'seq': 2},
                    ],
                    'finished': true,
                  },
          ),
          200,
        );
      });

      final events = await followCheck(
        'http://factify.test',
        'k1',
        connect: () => server,
        pollEvery: Duration.zero,
      ).toList();

      expect(events.map((e) => e.type), ['step', 'done']);
      expect(asked.where((path) => path.endsWith('/progress')), hasLength(2));
    });

    test('a server that reports nothing is given up on, quietly', () async {
      final server = MockClient((_) async => http.Response('', 404));
      final events = await followCheck(
        'http://factify.test',
        'k1',
        connect: () => server,
        pollEvery: Duration.zero,
      ).toList();
      expect(events, isEmpty);
    });

    test('a request id is a random UUID', () {
      final id = newRequestId();
      expect(
        id,
        matches(RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')),
      );
      expect(newRequestId(), isNot(id));
    });
  });

  group('what the screen is drawn from', () {
    test('sources are kept in the order they were opened, and change state', () {
      var watch = const CheckWatch();
      final events = [
        {'type': 'step', 'step': 'read'},
        {'type': 'step', 'step': 'search'},
        for (final site in ['pib.gov.in', 'altnews.in', 'ndtv.com', 'boomlive.in', 'factly.in'])
          {'type': 'source_started', 'publisher': site, 'domain': site, 'initials': 'XX'},
        {'type': 'source_done', 'domain': 'pib.gov.in', 'outcome': 'evidence'},
        {'type': 'source_done', 'domain': 'ndtv.com', 'outcome': 'not_relevant'},
        {'type': 'evidence_count', 'n': 1},
        {'type': 'step', 'step': 'read'}, // late, and ignored
      ];
      for (final (i, json) in events.indexed) {
        watch = watch.apply(_event(i + 1, json));
      }

      expect(watch.step, 1);
      expect(watch.sources.map((s) => s.domain).first, 'pib.gov.in');
      expect(watch.read, 2);
      expect(watch.evidence, 1);
      expect(watch.found.single.domain, 'pib.gov.in');
      // The card shows the four most recent, newest first.
      expect(watch.recent.map((s) => s.domain), [
        'factly.in',
        'boomlive.in',
        'ndtv.com',
        'altnews.in',
      ]);
    });

    test('a source keeps what it said, and is marked kept once checked', () {
      var watch = const CheckWatch();
      watch = watch.apply(
        _event(1, {'type': 'source_started', 'domain': 'pib.gov.in', 'title': 'It is fake'}),
      );
      watch = watch.apply(
        _event(2, {
          'type': 'source_done',
          'domain': 'pib.gov.in',
          'outcome': 'evidence',
          'stance': 'contradicts',
          'quote': 'No such scheme.',
        }),
      );
      var pib = watch.sources.single;
      expect(pib.title, 'It is fake');
      expect(pib.stance, Stance.contradicts);
      expect(pib.quote, 'No such scheme.');
      expect(pib.kept, isFalse);

      watch = watch.apply(
        _event(3, {'type': 'source_checked', 'domain': 'pib.gov.in', 'stance': 'contradicts'}),
      );
      pib = watch.sources.single;
      expect(pib.kept, isTrue);
      expect(watch.stances, {Stance.contradicts: 1});
    });

    test('a published fact-check joins the ring only if it speaks to the claim', () {
      var watch = const CheckWatch();
      for (final (i, domain) in ['altnews.in', 'factly.in'].indexed) {
        watch = watch.apply(
          _event(i + 1, {'type': 'source_started', 'domain': domain, 'via': 'fact_check'}),
        );
      }
      expect(watch.sources, isEmpty);
      expect(watch.factChecks, hasLength(2));

      watch = watch.apply(
        _event(3, {'type': 'source_done', 'domain': 'altnews.in', 'outcome': 'not_relevant'}),
      );
      watch = watch.apply(
        _event(4, {
          'type': 'source_done',
          'domain': 'factly.in',
          'outcome': 'evidence',
          'stance': 'contradicts',
        }),
      );
      expect(watch.sources.map((s) => s.domain), ['factly.in']);
      expect(watch.factChecks.map((s) => s.domain), ['altnews.in']);
    });

    test('a source taken back after the source check is not evidence', () {
      var watch = const CheckWatch();
      watch = watch.apply(_event(1, {'type': 'source_started', 'domain': 'x.com'}));
      watch = watch.apply(
        _event(2, {'type': 'source_done', 'domain': 'x.com', 'outcome': 'evidence'}),
      );
      watch = watch.apply(
        _event(3, {'type': 'source_done', 'domain': 'x.com', 'outcome': 'not_relevant'}),
      );
      expect(watch.found, isEmpty);
    });
  });

  group('the Checking screen', () {
    Future<StreamController<CheckEvent>> show(
      WidgetTester tester,
      AppServices services, {
      Completer<http.Response>? answer,
    }) async {
      tester.view.physicalSize = const Size(1080, 2340);
      tester.view.devicePixelRatio = 2.625;
      addTearDown(tester.view.reset);
      final events = StreamController<CheckEvent>();
      await tester.pumpWidget(
        MaterialApp(
          theme: buildFactifyTheme(Brightness.light),
          supportedLocales: AppLocalizations.supportedLocales,
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          home: Builder(
            builder: (context) => Scaffold(
              body: Center(
                child: TextButton(
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => CheckingScreen(
                        services: services,
                        submission: Submission.text('RBI is withdrawing Rs 500 notes.'),
                        job: (language) => CheckJob(
                          services: services,
                          submission: Submission.text('RBI is withdrawing Rs 500 notes.'),
                          language: language,
                          notifyWhenReady: services.notifyByDefault.value,
                          follow: (_) => events.stream,
                        ),
                      ),
                    ),
                  ),
                  child: const Text('go'),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('go'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      return events;
    }

    testWidgets('shows the step, the sources and the evidence the server reports', (tester) async {
      final answer = Completer<http.Response>();
      final services = _services(MockClient((_) => answer.future));
      final events = await show(tester, services);

      expect(find.text('STEP 1 OF 3'), findsOneWidget);
      expect(find.text('Sources appear here as they are opened'), findsOneWidget);
      expect(find.text('Nothing yet, still reading'), findsOneWidget);

      var seq = 0;
      void send(Map<String, dynamic> json) => events.add(_event(++seq, json));
      send({'type': 'step', 'step': 'search'});
      send({
        'type': 'source_started',
        'publisher': 'Press Information Bureau',
        'domain': 'pib.gov.in',
        'initials': 'PIB',
        'title': 'Rs 500 notes are not being withdrawn',
        'via': 'page',
      });
      send({
        'type': 'source_started',
        'publisher': 'BOOM',
        'domain': 'boomlive.in',
        'initials': 'BO',
        'via': 'page',
      });
      // A published fact-check compared in bulk: counted, not listed.
      send({
        'type': 'source_started',
        'publisher': 'factly.in',
        'domain': 'factly.in',
        'initials': 'FA',
        'via': 'fact_check',
      });
      send({'type': 'source_done', 'domain': 'factly.in', 'outcome': 'not_relevant'});
      await tester.pump();
      await tester.pump();

      expect(find.text('STEP 2 OF 3'), findsOneWidget);
      expect(find.text('Search trusted news and fact-checkers'), findsOneWidget);
      expect(find.text('Press Information Bureau'), findsOneWidget);
      // The page's own headline: what this source actually is.
      expect(find.text('Rs 500 notes are not being withdrawn'), findsOneWidget);
      expect(find.text('Reading…'), findsNWidgets(2));
      expect(find.text('0 of 2 read'), findsOneWidget);
      expect(find.text('Compared with 1 published fact-check'), findsOneWidget);
      expect(find.text('factly.in'), findsNothing);

      send({
        'type': 'source_done',
        'domain': 'pib.gov.in',
        'outcome': 'evidence',
        'stance': 'contradicts',
        'quote': 'RBI has not announced any withdrawal of Rs 500 notes.',
      });
      send({'type': 'source_done', 'domain': 'boomlive.in', 'outcome': 'not_relevant'});
      send({'type': 'evidence_count', 'n': 1, 'checked': false});
      send({'type': 'step', 'step': 'compare'});
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      // What it said, before the source check has confirmed it.
      expect(find.text('STEP 3 OF 3'), findsOneWidget);
      expect(find.text('Refutes'), findsWidgets);
      expect(find.text('Not relevant'), findsOneWidget);
      expect(find.text('2 of 2 read'), findsOneWidget);
      expect(find.text('1 source speaks to this claim - checking it next'), findsOneWidget);

      // Held up when checked against the claim.
      send({
        'type': 'source_checked',
        'domain': 'pib.gov.in',
        'stance': 'contradicts',
        'quote': 'RBI has not announced any withdrawal of Rs 500 notes.',
      });
      send({'type': 'evidence_count', 'n': 1, 'checked': true});
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text('1 source held up when checked against the claim'), findsOneWidget);

      answer.complete(http.Response(jsonEncode(_verdictJson()), 200));
      await tester.pumpAndSettle();
      expect(find.text('Result'), findsOneWidget);
      unawaited(events.close());
    });

    testWidgets('a server that reports nothing is not given invented progress', (tester) async {
      final answer = Completer<http.Response>();
      final services = _services(MockClient((_) => answer.future));
      final events = await show(tester, services);

      await tester.pump(const Duration(seconds: 5));

      expect(find.textContaining('STEP'), findsNothing);
      expect(find.text('Looking for sources that address this'), findsOneWidget);
      expect(find.text('A check usually takes 20–50 seconds.'), findsOneWidget);
      expect(find.text('Evidence collected'), findsNothing);

      answer.complete(http.Response(jsonEncode(_verdictJson()), 200));
      await tester.pumpAndSettle();
      unawaited(events.close());
    });

    testWidgets('with notify on, leaving keeps the check and announces it', (tester) async {
      final answer = Completer<http.Response>();
      final notifier = _RecordingNotifier();
      final history = HistoryStore();
      final services = _services(
        MockClient((_) => answer.future),
        notifier: notifier,
        history: history,
      );
      final events = await show(tester, services);

      await tester.tap(find.text('Notify me when ready'));
      await tester.pump();
      expect(find.text("We'll notify you when it's ready"), findsOneWidget);
      expect(notifier.alive, 1);

      await tester.tap(find.byTooltip('Stop waiting'));
      await tester.pumpAndSettle();
      expect(find.text('go'), findsOneWidget);

      answer.complete(http.Response(jsonEncode(_verdictJson()), 200));
      await tester.pumpAndSettle();

      expect(history.records, hasLength(1));
      expect(notifier.announced, ['RBI is withdrawing Rs 500 notes.']);
      unawaited(events.close());
    });

    testWidgets('without it, leaving drops the answer, as before', (tester) async {
      final answer = Completer<http.Response>();
      final notifier = _RecordingNotifier();
      final history = HistoryStore();
      final services = _services(
        MockClient((_) => answer.future),
        notifier: notifier,
        history: history,
      );
      final events = await show(tester, services);

      await tester.tap(find.byTooltip('Stop waiting'));
      await tester.pumpAndSettle();
      answer.complete(http.Response(jsonEncode(_verdictJson()), 200));
      await tester.pumpAndSettle();

      expect(history.records, isEmpty);
      expect(notifier.announced, isEmpty);
      unawaited(events.close());
    });
  });
}
