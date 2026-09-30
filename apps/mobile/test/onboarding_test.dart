// The way in: the welcome pages, the sign-up screen, the four-question survey a new
// account meets once, and the free checks it starts with.

import 'dart:convert';

import 'package:factify_mobile/api/client.dart';
import 'package:factify_mobile/app_services.dart';
import 'package:factify_mobile/auth/auth_service.dart';
import 'package:factify_mobile/history/history_store.dart';
import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/l10n/language_preference.dart';
import 'package:factify_mobile/notify/ready_notifier.dart';
import 'package:factify_mobile/notify/notify_preference.dart';
import 'package:factify_mobile/screens/main_shell.dart';
import 'package:factify_mobile/screens/survey_screen.dart';
import 'package:factify_mobile/screens/welcome_screen.dart';
import 'package:factify_mobile/theme/theme.dart';
import 'package:factify_mobile/theme/theme_mode_preference.dart';
import 'package:factify_mobile/widgets/brand.dart';
import 'package:factify_mobile/widgets/ui/fx_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// A server with one person, whose survey is due until it is answered or skipped.
class _Server {
  _Server({this.surveyDue = true});

  bool surveyDue;
  final List<Map<String, dynamic>> surveys = [];
  final List<Map<String, dynamic>> registrations = [];

  Map<String, dynamic> _account() => {
    'id': 'u-1',
    'email': 'asha@example.org',
    'name': 'Asha',
    'plan': 'free',
    'joined_at': '2026-09-30T10:00:00Z',
    'credits': {
      'balance': 100,
      'used': 0,
      'checks': 0,
      'check_cost': 1,
      'deep_check_cost': 1,
      'limited': false,
    },
    'survey_due': surveyDue,
  };

  late final MockClient client = MockClient((request) async {
    final path = request.url.path;
    if (path == '/readyz') return http.Response('{"ready": true, "missing": []}', 200);
    if (path == '/v1/auth/config') {
      return http.Response(
        jsonEncode({
          'enabled': true,
          'required': true,
          'providers': ['password'],
          'min_password_length': 8,
        }),
        200,
      );
    }
    if (path == '/v1/auth/register' || path == '/v1/auth/login') {
      if (path.endsWith('register')) {
        registrations.add(jsonDecode(request.body) as Map<String, dynamic>);
      }
      return http.Response(
        jsonEncode({
          'access_token': 'token-1',
          'expires_at': DateTime.now().add(const Duration(days: 30)).toIso8601String(),
          'method': 'password',
          'email': 'asha@example.org',
          'name': 'Asha',
        }),
        path.endsWith('register') ? 201 : 200,
      );
    }
    if (path == '/v1/me/survey' && request.method == 'PUT') {
      surveys.add(jsonDecode(request.body) as Map<String, dynamic>);
      surveyDue = false;
      return http.Response(jsonEncode(_account()), 200);
    }
    if (path == '/v1/me') return http.Response(jsonEncode(_account()), 200);
    return http.Response('{}', 404);
  });
}

Future<AppServices> _services(_Server server) async {
  final client = FactifyClient(baseUrl: 'http://factify.test', httpClient: server.client);
  final auth = AuthService(client: client, httpClient: server.client, persist: false);
  client.tokenProvider = auth.accessToken;
  await auth.start();
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

Future<void> _pump(WidgetTester tester, AppServices services, Widget home) async {
  tester.view.physicalSize = const Size(1080, 2340);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
  // A fresh navigator: a screen pushed in an earlier pump must not stay on top.
  await tester.pumpWidget(const SizedBox());
  await tester.pumpWidget(
    ListenableBuilder(
      listenable: Listenable.merge([services.themeMode, services.language]),
      builder: (context, _) => MaterialApp(
        theme: buildFactifyTheme(Brightness.light),
        darkTheme: buildFactifyTheme(Brightness.dark),
        themeMode: services.themeMode.value,
        locale: services.language.value,
        supportedLocales: AppLocalizations.supportedLocales,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        home: home,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _tap(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

Finder _field(String label) => find.widgetWithText(TextField, label);

Future<void> _createAccount(WidgetTester tester) async {
  await tester.enterText(_field('Your name (optional)'), 'Asha');
  await tester.enterText(_field('Email'), 'asha@example.org');
  await tester.enterText(_field('Password'), 'long enough');
  await tester.enterText(_field('Confirm password'), 'long enough');
  await tester.pump();
  await _tap(tester, find.widgetWithText(FxButton, 'Create account'));
}

void main() {
  group('the welcome pages', () {
    testWidgets('go page by page to the two ways in; Skip goes straight there', (tester) async {
      final services = await _services(_Server());
      await _pump(tester, services, WelcomeScreen(services: services));

      expect(find.byType(FactifyMark), findsOneWidget);
      expect(find.text("Know what's true before you share it"), findsOneWidget);
      await _tap(tester, find.text('Next').last);
      expect(find.text('Every answer comes with its sources'), findsOneWidget);
      // The sample result is invented, and says so.
      expect(find.text('AN EXAMPLE'), findsOneWidget);
      await _tap(tester, find.text('Next').last);
      expect(find.text('Pictures, videos and voice notes too'), findsOneWidget);
      expect(find.text('I have an account'), findsOneWidget);

      await _tap(tester, find.text('Create account'));
      expect(find.text('Create your account'), findsOneWidget);
      expect(find.text('We never keep a record of what you check.'), findsOneWidget);

      await _pump(tester, services, WelcomeScreen(services: services, key: UniqueKey()));
      await _tap(tester, find.text('Skip'));
      expect(find.text('I have an account'), findsOneWidget);
      await _tap(tester, find.text('I have an account'));
      expect(find.text('Welcome back'), findsOneWidget);
      // The other way, from the foot of the form.
      await _tap(tester, find.text('Create one'));
      expect(find.text('Create your account'), findsOneWidget);
    });

    testWidgets('lay out in Hindi at 130% text, light and dark, without overflowing', (
      tester,
    ) async {
      final services = await _services(_Server());
      await services.language.choose(const Locale('hi'));
      tester.platformDispatcher.textScaleFactorTestValue = 1.3;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      for (final mode in [ThemeMode.light, ThemeMode.dark]) {
        await services.themeMode.choose(mode);
        await _pump(tester, services, WelcomeScreen(services: services, key: UniqueKey()));
        await _tap(tester, find.text('आगे').last);
        await _tap(tester, find.text('आगे').last);
        await _tap(tester, find.text('मेरा खाता है'));
        expect(tester.takeException(), isNull);
      }
    });
  });

  group('a new account', () {
    testWidgets('is asked four questions once, then shown its free checks', (tester) async {
      final server = _Server();
      final services = await _services(server);
      await _pump(tester, services, WelcomeScreen(services: services));
      await _tap(tester, find.text('Skip'));
      await _tap(tester, find.text('Create account'));
      await _createAccount(tester);

      expect(server.registrations.single['name'], 'Asha');
      expect(find.byType(SurveyScreen), findsOneWidget);
      expect(find.text('What brings you to Factify?'), findsOneWidget);
      await _tap(tester, find.text('Journalist or fact-checker'));
      await _tap(tester, find.text('Next').last);
      await _tap(tester, find.text('WhatsApp'));
      await _tap(tester, find.text('YouTube'));
      await _tap(tester, find.text('Next').last);
      // Passed over: no answer is stored for it.
      await _tap(tester, find.text('Next').last);
      expect(find.text('How did you hear about Factify?'), findsOneWidget);
      await _tap(tester, find.text('From a friend'));
      await _tap(tester, find.text('Finish'));

      final sent = server.surveys.single;
      expect(sent['role'], 'journalist');
      expect(Set<String>.from(sent['places'] as List), {'whatsapp', 'youtube'});
      expect(sent['wants'], isEmpty);
      expect(sent['heard'], 'friend');
      expect(find.byType(CreditsWelcomeScreen), findsOneWidget);
      expect(find.text("You're in, Asha"), findsOneWidget);
      expect(find.text('100'), findsOneWidget);
    });

    testWidgets('can skip the whole survey', (tester) async {
      final server = _Server();
      final services = await _services(server);
      await _pump(tester, services, WelcomeScreen(services: services));
      await _tap(tester, find.text('Skip'));
      await _tap(tester, find.text('Create account'));
      await _createAccount(tester);

      await _tap(tester, find.text('Skip all'));

      expect(server.surveys.single, {'skipped': true});
      expect(find.byType(CreditsWelcomeScreen), findsOneWidget);
    });

    testWidgets('the survey lays out in Hindi at 130% text', (tester) async {
      final services = await _services(_Server());
      await services.auth.signIn(email: 'asha@example.org', password: 'long enough');
      await services.auth.refreshAccount();
      await services.language.choose(const Locale('hi'));
      tester.platformDispatcher.textScaleFactorTestValue = 1.3;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await _pump(tester, services, SurveyScreen(services: services));
      for (var i = 0; i < 3; i++) {
        await _tap(tester, find.text('आगे').last);
      }
      await _tap(tester, find.text('पूरा करें'));
      expect(find.byType(CreditsWelcomeScreen), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  testWidgets('an account made before the survey goes straight into the app', (tester) async {
    final services = await _services(_Server(surveyDue: false));
    await services.auth.signIn(email: 'asha@example.org', password: 'long enough');
    await services.auth.refreshAccount();

    expect(signedInHome(services), isA<MainShell>());
  });
}
