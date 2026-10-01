// Buying credits from the phone: the app opens a one-time browser link and waits
// until the server says the payment is paid, failed or cancelled.

import 'dart:convert';

import 'package:factify_mobile/api/client.dart';
import 'package:factify_mobile/app_services.dart';
import 'package:factify_mobile/auth/auth_service.dart';
import 'package:factify_mobile/history/history_store.dart';
import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/l10n/language_preference.dart';
import 'package:factify_mobile/notify/notify_preference.dart';
import 'package:factify_mobile/notify/ready_notifier.dart';
import 'package:factify_mobile/screens/payment_screen.dart';
import 'package:factify_mobile/theme/theme.dart';
import 'package:factify_mobile/theme/theme_mode_preference.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class _Server {
  _Server(this.statuses);

  /// What each status poll answers, in turn; the last repeats.
  final List<String> statuses;
  int polls = 0;
  final List<String> cancelled = [];

  late final MockClient client = MockClient((request) async {
    final path = request.url.path;
    if (path == '/v1/auth/config') {
      return http.Response(jsonEncode({'enabled': true, 'required': true, 'providers': ['password']}), 200);
    }
    if (path == '/v1/auth/login') {
      return http.Response(
        jsonEncode({
          'access_token': 'fs_token',
          'expires_at': DateTime.now().add(const Duration(days: 1)).toIso8601String(),
          'method': 'password',
          'email': 'asha@example.org',
        }),
        200,
      );
    }
    if (path == '/v1/billing/handoff') {
      return http.Response(
        jsonEncode({'id': 'h-1', 'status': 'waiting', 'url': 'https://factify.test/pay?h=one-time'}),
        200,
      );
    }
    if (path == '/v1/billing/handoff/h-1') {
      final status = statuses[polls < statuses.length ? polls : statuses.length - 1];
      polls++;
      return http.Response(
        jsonEncode({'id': 'h-1', 'status': status, if (status == 'paid') 'credits': 500}),
        200,
      );
    }
    if (path == '/v1/billing/handoff/h-1/finish') {
      cancelled.add('h-1');
      return http.Response('{"status": "cancelled"}', 200);
    }
    return http.Response('{}', 404);
  });
}

Future<AppServices> _services(_Server server) async {
  final client = FactifyClient(baseUrl: 'http://factify.test', httpClient: server.client);
  final auth = AuthService(client: client, httpClient: server.client, persist: false);
  client.tokenProvider = auth.accessToken;
  await auth.start();
  await auth.signIn(email: 'asha@example.org', password: 'long enough');
  return AppServices(
    client: client,
    auth: auth,
    language: LanguagePreference.inMemory(),
    history: HistoryStore(),
    themeMode: ThemeModePreference.inMemory(),
    notifier: SilentNotifier(),
    notifyByDefault: NotifyPreference.inMemory(),
  );
}

Future<void> _pump(WidgetTester tester, Widget home) async {
  tester.view.physicalSize = const Size(1080, 2340);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: buildFactifyTheme(Brightness.light),
      supportedLocales: AppLocalizations.supportedLocales,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      home: home,
    ),
  );
}

void main() {
  testWidgets('opens the one-time link, waits, and shows the credits when paid', (tester) async {
    final server = _Server(['opened', 'paid']);
    final services = await _services(server);
    final opened = <Uri>[];
    await _pump(
      tester,
      PaymentScreen(services: services, opener: (url) async {
        opened.add(url);
        return true;
      }),
    );
    await tester.pump();
    await tester.pump();
    expect(opened.single.toString(), 'https://factify.test/pay?h=one-time');
    expect(find.text('Finish in your browser'), findsOneWidget);

    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    expect(find.textContaining('Waiting for your payment'), findsOneWidget);

    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    expect(find.text('Payment complete'), findsOneWidget);
    expect(find.text('500 credits were added.'), findsOneWidget);
    // Finished: no more asking.
    final polls = server.polls;
    await tester.pump(const Duration(seconds: 9));
    expect(server.polls, polls);
  });

  testWidgets('choosing a plan opens the website at its plans, and says when the plan is on', (
    tester,
  ) async {
    final server = _Server(['opened', 'paid']);
    final services = await _services(server);
    final opened = <Uri>[];
    await _pump(
      tester,
      PaymentScreen(
        services: services,
        plans: true,
        opener: (url) async {
          opened.add(url);
          return true;
        },
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(opened.single.toString(), 'https://factify.test/pay?h=one-time&then=plans');

    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    expect(find.text('Payment complete'), findsOneWidget);
    expect(find.text('Your new plan is active. Its checks are yours from now.'), findsOneWidget);
  });

  testWidgets('a failed payment offers to start again', (tester) async {
    final services = await _services(_Server(['failed']));
    await _pump(tester, PaymentScreen(services: services, opener: (_) async => true));
    await tester.pump();
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    expect(find.text("Payment didn't go through"), findsOneWidget);
    expect(find.text('Start again'), findsOneWidget);
  });

  testWidgets('cancelling while waiting tells the server', (tester) async {
    final server = _Server(['waiting']);
    final services = await _services(server);
    await _pump(
      tester,
      Builder(
        builder: (context) => TextButton(
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute<void>(builder: (_) => PaymentScreen(services: services, opener: (_) async => true)),
          ),
          child: const Text('go'),
        ),
      ),
    );
    await tester.tap(find.text('go'));
    for (var i = 0; i < 6; i++) {
      await tester.pump(const Duration(milliseconds: 200));
    }
    await tester.tap(find.text('Cancel'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(server.cancelled, ['h-1']);
  });
}
