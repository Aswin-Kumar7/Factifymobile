/// The quick verdict over the chat, and the home-screen widget's buttons (v5, 2.7-2.8).
///
/// Held here: shared text is checked and answered in the sheet - the verdict, how
/// sure, who said so - and "Copy correction" copies the server's polite note with
/// its links; "Open full result" opens the check kept in History. Nobody signed in
/// goes to the full app with the text. A check that does not finish offers to try
/// again. Closing, by X or by tapping the chat, closes the window. The widget's
/// History button opens History, and the quick verdict's "Open full result" opens
/// the kept check in the app.
library;

import 'dart:async';
import 'dart:convert';

import 'package:factify_mobile/api/client.dart';
import 'package:factify_mobile/api/share_intake.dart';
import 'package:factify_mobile/app_services.dart';
import 'package:factify_mobile/auth/auth_service.dart';
import 'package:factify_mobile/checks/check_job.dart';
import 'package:factify_mobile/history/history_store.dart';
import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/l10n/language_preference.dart';
import 'package:factify_mobile/models/submission.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:factify_mobile/quick/quick_verdict.dart';
import 'package:factify_mobile/screens/main_shell.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _claim = 'Govt to pay Rs 5,000 a month to every woman from 1 July.';
const _pib = 'https://pib.gov.in/factcheck/1';

Map<String, dynamic> _verdict({String verdict = 'FALSE', String action = 'DO_NOT_SHARE'}) => {
  'case_id': 'case-1',
  'action': action,
  'action_reason': 'r',
  'verdict': verdict,
  'confidence': verdict == 'UNCONFIRMED' ? null : 91,
  'summary': 'No such scheme has been announced. Other outlets agree.',
  'rule_version': 'v',
  'claims': [
    {
      'id': 'cl_1',
      'text': _claim,
      'claim_type': 'EVENT',
      'status': verdict == 'UNCONFIRMED' ? 'UNVERIFIED' : 'CONTRADICTED',
      'severity': 'HIGH',
      'importance': 'HEADLINE',
      'reason': 'A published fact-check rated this false.',
      'rule_id': 'r',
      'rule_version': 'v',
      'strength': {'score': 0.9, 'band': 'STRONG', 'version': 'v'},
      'evidence': [
        if (verdict != 'UNCONFIRMED')
          {
            'id': 'ev_1',
            'tier': 'C',
            'kind': 'fact_check',
            'direction': 'contradicts',
            'method': 'claim_review',
            'finding': 'Rated false.',
            'citation_url': _pib,
            'snapshot_id': 's',
            'source_excerpt': 'No such scheme.',
            'source_anchor': <String, dynamic>{},
            'match_basis': {'metric': 'm', 'value': 0.9, 'threshold': 0.6},
            'match_quality': 'STRONG',
            'publisher': 'PIB Fact Check',
          },
      ],
    },
  ],
  'retrieved_at': '2026-09-27T10:00:00Z',
};

class _Host implements QuickHost {
  final calls = <String>[];

  @override
  Future<SharedText?> share() async => const SharedText(value: _claim, link: false);

  @override
  Future<void> openFullApp(String text) async => calls.add('full:$text');

  @override
  Future<void> openResult(String recordId) async => calls.add('result:$recordId');

  @override
  Future<void> close() async => calls.add('close');
}

class _Clipboard {
  String? text;

  Future<Object?> handle(MethodCall call) async {
    if (call.method == 'Clipboard.setData') text = (call.arguments as Map)['text'] as String?;
    if (call.method == 'Clipboard.hasStrings') return {'value': false};
    return null;
  }
}

Future<AppServices> _services({bool signedIn = true, http.Response Function()? verify}) async {
  final server = MockClient((request) async {
    final path = request.url.path;
    if (path == '/readyz') return http.Response('{"ready": true, "missing": []}', 200);
    if (path == '/v1/auth/config') {
      return http.Response('{"enabled": true, "required": true, "providers": ["password"]}', 200);
    }
    if (path == '/v1/auth/login') {
      return http.Response(
        jsonEncode({
          'access_token': 't',
          'expires_at': DateTime.now().add(const Duration(days: 1)).toIso8601String(),
          'method': 'password',
          'email': 'asha@example.org',
        }),
        200,
      );
    }
    if (path == '/v1/me') {
      return http.Response(
        jsonEncode({
          'id': 'u-1',
          'email': 'asha@example.org',
          'plan': 'free',
          'credits': {
            'balance': 42,
            'used': 8,
            'checks': 11,
            'check_cost': 1,
            'deep_check_cost': 3,
            'limited': false,
          },
        }),
        200,
      );
    }
    // Started in the background (contract 1.4), then answered when the app asks.
    if (path == '/v1/verify') {
      return http.Response('{"case_id": "case-1", "poll_url": "/v1/cases/case-1"}', 202);
    }
    if (path == '/v1/cases/case-1') {
      return verify?.call() ?? http.Response(jsonEncode(_verdict()), 200);
    }
    if (path.endsWith('/correction-text')) {
      return http.Response(
        jsonEncode({
          'message': 'Hi! I checked this before forwarding. Factify says it\'s false. PIB: $_pib',
          'links': [_pib],
        }),
        200,
      );
    }
    return http.Response('{}', 404);
  });
  final client = FactifyClient(baseUrl: 'http://factify.test', httpClient: server);
  final auth = AuthService(client: client, httpClient: server, persist: false);
  client.tokenProvider = auth.accessToken;
  await auth.start();
  if (signedIn) await auth.signIn(email: 'asha@example.org', password: 'long enough');
  return AppServices(
    client: client,
    auth: auth,
    language: LanguagePreference.inMemory(),
    history: HistoryStore(),
  );
}

Future<(_Host, _Clipboard)> _open(WidgetTester tester, AppServices services) async {
  tester.view.physicalSize = const Size(1080, 2340);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
  final clipboard = _Clipboard();
  final messenger = tester.binding.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(SystemChannels.platform, clipboard.handle);
  addTearDown(() => messenger.setMockMethodCallHandler(SystemChannels.platform, null));
  final host = _Host();
  await tester.pumpWidget(
    QuickVerdictApp(
      services: services,
      shared: const SharedText(value: _claim, link: false),
      host: host,
      ready: true,
      job: (language) => CheckJob(
        services: services,
        submission: Submission.text(_claim),
        language: language,
        // No progress stream in a test: the sheet says it is checking, and waits.
        follow: (_) => const Stream.empty(),
      ),
    ),
  );
  await tester.pumpAndSettle();
  // The first poll of the check, a few seconds in.
  await tester.pump(const Duration(seconds: 3));
  await tester.pumpAndSettle();
  return (host, clipboard);
}

void main() {
  testWidgets('answers over the chat, and copies the polite correction', (tester) async {
    final services = await _services();
    final (host, clipboard) = await _open(tester, services);

    expect(find.text('False'), findsOneWidget);
    expect(find.text('91% confidence'), findsOneWidget);
    expect(find.text('No such scheme has been announced.'), findsOneWidget);
    expect(find.text('Other outlets agree.'), findsNothing);
    expect(find.text('PIB Fact Check'), findsOneWidget);
    expect(find.textContaining('checked in'), findsOneWidget);

    await tester.tap(find.text('Copy correction'));
    await tester.pumpAndSettle();
    expect(clipboard.text, contains("Factify says it's false"));
    expect(clipboard.text, contains(_pib));
    expect(find.text('Copied — paste it in the chat'), findsOneWidget);

    // The check was kept in History, and "Open full result" opens it there.
    final kept = services.history.records.single;
    await tester.tap(find.text('Open full result'));
    expect(host.calls, ['result:${kept.id}']);
  });

  testWidgets('an Unconfirmed answer offers a note, never a correction', (tester) async {
    final services = await _services(
      verify: () => http.Response(
        jsonEncode(_verdict(verdict: 'UNCONFIRMED', action: 'SEND_TO_REVIEW')),
        200,
      ),
    );
    await _open(tester, services);

    expect(find.text('Unconfirmed'), findsOneWidget);
    expect(find.text('Copy a note'), findsOneWidget);
    expect(find.text('Copy correction'), findsNothing);
    expect(find.textContaining('confidence'), findsNothing);
  });

  testWidgets('nobody signed in goes to the full app with the text', (tester) async {
    final services = await _services(signedIn: false);
    final (host, _) = await _open(tester, services);

    expect(find.text('Sign in to Factify to check this.'), findsOneWidget);
    await tester.tap(find.text('Open Factify'));
    expect(host.calls, ['full:$_claim']);
  });

  testWidgets("a check that doesn't finish offers to try again", (tester) async {
    final services = await _services(verify: () => http.Response('{"detail": "x"}', 503));
    final (host, _) = await _open(tester, services);

    expect(find.text('Verification is not available right now.'), findsOneWidget);
    expect(find.text('Try again'), findsOneWidget);
    await tester.tap(find.text('Open Factify'));
    expect(host.calls, ['full:$_claim']);
  });

  testWidgets('X, or a tap on the chat, closes the window', (tester) async {
    final services = await _services();
    final (host, _) = await _open(tester, services);

    await tester.tap(find.byTooltip('Close'));
    await tester.pump();
    expect(host.calls, ['close']);
  });

  group('the app, opened from outside', () {
    Future<(StreamController<SharedContent>, AppServices)> shell(WidgetTester tester) async {
      tester.view.physicalSize = const Size(1080, 2340);
      tester.view.devicePixelRatio = 2.625;
      addTearDown(tester.view.reset);
      final services = await _services();
      final messenger = tester.binding.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(SystemChannels.platform, _Clipboard().handle);
      addTearDown(() => messenger.setMockMethodCallHandler(SystemChannels.platform, null));
      final shares = StreamController<SharedContent>.broadcast();
      addTearDown(shares.close);
      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: MainShell(services: services, intake: _Intake(shares.stream)),
        ),
      );
      await tester.pumpAndSettle();
      return (shares, services);
    }

    testWidgets("the widget's History button opens History", (tester) async {
      final (shares, _) = await shell(tester);
      shares.add(const SharedContent(kind: 'widget', value: 'history'));
      await tester.pumpAndSettle();
      expect(find.text('No checks yet'), findsOneWidget);
    });

    testWidgets('"Open full result" opens the kept check', (tester) async {
      final (shares, services) = await shell(tester);
      final kept = await services.history.add(
        Submission.text(_claim),
        Verdict.fromJson(_verdict()),
      );
      shares.add(SharedContent(kind: 'record', value: kept.id));
      await tester.pumpAndSettle();
      expect(find.text('Result'), findsOneWidget);
    });
  });
}

class _Intake implements ShareIntake {
  _Intake(this._stream);

  final Stream<SharedContent> _stream;

  @override
  Stream<SharedContent> get stream => _stream;

  @override
  Future<SharedContent?> initial() async => null;

  @override
  void dispose() {}
}
