/// Profile, the welcome pages and the error screen (v5, 2.10, 2.1, 2.11).
///
/// Held here: Profile shows the account the server reports; the dark mode switch
/// flips light and dark and the row offers "same as your phone"; "Notify when
/// ready" asks for permission before it turns on, and stays off when refused;
/// "Saved checks" opens History. The welcome pages go 1 -> 2 -> sign-up and Skip
/// goes straight there, and the example result says it is an example. Each check
/// failure has one clear next step, and a link that could not be read offers to
/// paste the article's text instead.
library;

import 'dart:convert';

import 'package:factify_mobile/api/client.dart';
import 'package:factify_mobile/app_services.dart';
import 'package:factify_mobile/auth/auth_service.dart';
import 'package:factify_mobile/history/history_store.dart';
import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/l10n/language_preference.dart';
import 'package:factify_mobile/models/submission.dart';
import 'package:factify_mobile/notify/notify_preference.dart';
import 'package:factify_mobile/notify/ready_notifier.dart';
import 'package:factify_mobile/screens/error_screen.dart';
import 'package:factify_mobile/screens/profile_screen.dart';
import 'package:factify_mobile/screens/welcome_screen.dart';
import 'package:factify_mobile/theme/theme.dart';
import 'package:factify_mobile/theme/theme_mode_preference.dart';
import 'package:factify_mobile/widgets/ui/fx_switch.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _token = 'fs_session-1';

MockClient _server() => MockClient((request) async {
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
  if (path == '/v1/auth/login') {
    return http.Response(
      jsonEncode({
        'access_token': _token,
        'expires_at': DateTime.now().add(const Duration(days: 30)).toIso8601String(),
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
        'name': 'Asha',
        'plan': 'free',
        'joined_at': '2026-09-26T10:00:00Z',
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
  return http.Response('{}', 404);
});

class _Notifier extends SilentNotifier {
  _Notifier({required this.allowed});

  final bool allowed;
  int asked = 0;

  @override
  Future<bool> askPermission() async {
    asked++;
    return allowed;
  }
}

Future<AppServices> _services({bool allowed = true, bool signedIn = true}) async {
  final server = _server();
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
    themeMode: ThemeModePreference.inMemory(),
    notifier: _Notifier(allowed: allowed),
    notifyByDefault: NotifyPreference.inMemory(),
  );
}

Future<void> _pump(WidgetTester tester, AppServices services, Widget home) async {
  tester.view.physicalSize = const Size(1080, 2340);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
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

Finder _switchIn(String row) => find.descendant(
  of: find.ancestor(of: find.text(row), matching: find.byType(InkWell)).first,
  matching: find.byType(FxSwitch),
);

void main() {
  group('Profile', () {
    testWidgets("shows the account the server reports, and that it's online", (tester) async {
      final services = await _services();
      await _pump(tester, services, ProfileScreen(services: services));

      expect(find.text('Asha'), findsOneWidget);
      expect(find.text('asha@example.org'), findsOneWidget);
      expect(find.text('Signed in with email'), findsOneWidget);
      expect(find.text('42'), findsOneWidget);
      expect(find.text('credits left'), findsOneWidget);
      expect(find.text('8 used'), findsOneWidget);
      expect(find.text('11'), findsOneWidget);
      expect(find.text('checks so far'), findsOneWidget);
      expect(find.text('Sep ’26'), findsOneWidget);
      expect(find.text('Online'), findsOneWidget);
    });

    testWidgets('the dark mode switch flips the theme; the row offers "same as your phone"', (
      tester,
    ) async {
      final services = await _services();
      await _pump(tester, services, ProfileScreen(services: services));
      expect(find.text('Following your phone'), findsOneWidget);

      await tester.tap(_switchIn('Dark mode'));
      await tester.pumpAndSettle();
      expect(services.themeMode.value, ThemeMode.dark);
      expect(find.text('Following your phone'), findsNothing);

      await tester.tap(find.text('Dark mode'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Same as your phone'));
      await tester.pumpAndSettle();
      expect(services.themeMode.value, ThemeMode.system);
    });

    testWidgets('"Notify when ready" asks first, and stays off when refused', (tester) async {
      final refused = await _services(allowed: false);
      await _pump(tester, refused, ProfileScreen(services: refused));
      await tester.tap(_switchIn('Notify when ready'));
      await tester.pumpAndSettle();
      expect((refused.notifier as _Notifier).asked, 1);
      expect(refused.notifyByDefault.value, isFalse);
      expect(find.textContaining('Notifications are off'), findsOneWidget);

      final allowed = await _services();
      await _pump(tester, allowed, ProfileScreen(services: allowed));
      await tester.tap(_switchIn('Notify when ready'));
      await tester.pumpAndSettle();
      expect(allowed.notifyByDefault.value, isTrue);
    });

    testWidgets('the language row chooses a language, and saved checks open History', (
      tester,
    ) async {
      final services = await _services();
      var opened = 0;
      await _pump(
        tester,
        services,
        ProfileScreen(services: services, onOpenHistory: () => opened++),
      );

      await tester.tap(find.text('Saved checks'));
      expect(opened, 1);

      await tester.tap(find.text('Language'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('हिन्दी'));
      await tester.pumpAndSettle();
      expect(services.language.value?.languageCode, 'hi');
      expect(find.text('प्रोफ़ाइल'), findsOneWidget);
    });
  });

  testWidgets('Profile lays out in Hindi at 130% text, light and dark', (tester) async {
    final services = await _services();
    await services.language.choose(const Locale('hi'));
    tester.platformDispatcher.textScaleFactorTestValue = 1.3;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      await services.themeMode.choose(mode);
      await _pump(tester, services, ProfileScreen(services: services));
      expect(find.text('प्रोफ़ाइल'), findsOneWidget);
    }
  });

  group('welcome', () {
    testWidgets('goes page by page to sign-up, and Skip goes straight there', (tester) async {
      final services = await _services(signedIn: false);
      await _pump(tester, services, WelcomeScreen(services: services));

      expect(find.text("Know what's true before you share it"), findsOneWidget);
      await tester.tap(find.text('Next'));
      await tester.pumpAndSettle();
      expect(find.text('Every answer comes with its sources'), findsOneWidget);
      // The sample result is invented, and says so.
      expect(find.text('AN EXAMPLE'), findsOneWidget);
      await tester.ensureVisible(find.text('Get started'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Get started'));
      await tester.pumpAndSettle();
      expect(find.text('Create your account'), findsOneWidget);
      expect(find.text('We never keep a record of what you check.'), findsOneWidget);

      await _pump(tester, services, WelcomeScreen(services: services, key: UniqueKey()));
      await tester.tap(find.text('Skip'));
      await tester.pumpAndSettle();
      expect(find.text('Create your account'), findsOneWidget);
    });

    testWidgets('lays out in Hindi at 130% text without overflowing', (tester) async {
      final services = await _services(signedIn: false);
      await services.language.choose(const Locale('hi'));
      tester.platformDispatcher.textScaleFactorTestValue = 1.3;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await _pump(tester, services, WelcomeScreen(services: services));
      await tester.ensureVisible(find.text('आगे'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('आगे'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('शुरू करें'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('शुरू करें'));
      await tester.pumpAndSettle();
    });
  });

  group('the error screen', () {
    Future<List<String>> show(
      WidgetTester tester,
      CheckProblem problem, {
      Submission? submission,
      bool retry = true,
    }) async {
      final exits = <String>[];
      final services = await _services();
      await _pump(
        tester,
        services,
        Scaffold(
          body: ErrorView(
            problem: problem,
            submission: submission ?? Submission.text('Govt to pay ₹5,000 a month'),
            message: 'Something went wrong.',
            onRetry: retry ? () => exits.add('retry') : null,
            onExit: (exit) => exits.add(exit.name),
            onClose: () => exits.add('close'),
          ),
        ),
      );
      return exits;
    }

    testWidgets("a link that couldn't be read offers to paste the article text", (tester) async {
      final exits = await show(
        tester,
        CheckProblem.linkUnread,
        submission: Submission.link('https://www.newsdaily.example/viral-scheme'),
        retry: false,
      );
      expect(find.text("We couldn't read that page"), findsOneWidget);
      expect(find.text('newsdaily.example/viral-scheme'), findsOneWidget);
      await tester.tap(find.text('Paste the article text'));
      await tester.tap(find.text('Back to home'));
      expect(exits, ['pasteText', 'close']);
    });

    testWidgets("offline keeps what was being checked, and offers to try again", (tester) async {
      final exits = await show(tester, CheckProblem.offline);
      expect(find.text("You're offline"), findsOneWidget);
      expect(find.text("Kept on this phone, so you won't need to paste it again"), findsOneWidget);
      await tester.tap(find.text('Try again'));
      expect(exits, ['retry']);
    });

    testWidgets('each limit has its own next step', (tester) async {
      var exits = await show(tester, CheckProblem.dailyLimit);
      await tester.tap(find.text('See saved checks'));
      expect(exits, ['openHistory']);

      exits = await show(tester, CheckProblem.outOfCredits);
      await tester.tap(find.text('See your credits'));
      expect(exits, ['openProfile']);

      exits = await show(tester, CheckProblem.tooLarge);
      await tester.tap(find.text('Choose another file'));
      expect(exits, ['chooseFile']);
    });

    test('failures map to their problem', () {
      expect(
        CheckProblem.of(const ApiFailure(FailureKind.invalidInput), link: true),
        CheckProblem.linkUnread,
      );
      expect(
        CheckProblem.of(const ApiFailure(FailureKind.invalidInput), link: false),
        CheckProblem.other,
      );
      expect(
        CheckProblem.of(const ApiFailure(FailureKind.interrupted), link: false),
        CheckProblem.offline,
      );
      expect(
        CheckProblem.of(const ApiFailure(FailureKind.outOfCredits), link: false),
        CheckProblem.outOfCredits,
      );
    });
  });
}
