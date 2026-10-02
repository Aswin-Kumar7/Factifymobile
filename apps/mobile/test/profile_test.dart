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
import 'package:factify_mobile/theme/theme.dart';
import 'package:factify_mobile/theme/theme_mode_preference.dart';
import 'package:factify_mobile/widgets/ui/fx_switch.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _token = 'fs_session-1';

/// Requests the server was sent, as "METHOD path".
final List<String> _calls = [];

MockClient _server({
  bool plans = false,
  bool prepaid = false,
  int deleteStatus = 204,
}) => MockClient((request) async {
  final path = request.url.path;
  _calls.add('${request.method} $path');
  if (path == '/v1/me' && request.method == 'DELETE') {
    if (deleteStatus == 409) {
      return http.Response(
        jsonEncode({
          'detail':
              'You are the only owner of Acme News. Make someone else an owner or close it first.',
          'error_code': 'owns_organisations',
        }),
        409,
      );
    }
    return http.Response('', deleteStatus);
  }
  if (path == '/v1/billing/packs') {
    return http.Response(
      jsonEncode({
        'costs': {'text': 1, 'link': 1, 'picture': 1, 'pdf': 1, 'video': 3},
      }),
      200,
    );
  }
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
        if (plans)
          'plan_usage': {
            'plan': 'plus',
            'name': 'Plus',
            'interval': 'month',
            'renews_at': '2026-11-01T00:00:00+05:30',
            'cancel_at_end': prepaid,
            'allowance': 120,
            'used': 78,
            'resets_at': '2026-11-01T00:00:00+05:30',
            'credits': 0,
            'extra_enabled': prepaid,
            'extra_cap_paise': 50000,
            'extra_used_paise': 0,
            'extra_price_paise': 100,
            'extra_blocked': prepaid,
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

Future<AppServices> _services({
  bool allowed = true,
  bool signedIn = true,
  bool plans = false,
  bool prepaid = false,
  int deleteStatus = 204,
}) async {
  _calls.clear();
  final server = _server(plans: plans, prepaid: prepaid, deleteStatus: deleteStatus);
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

    testWidgets("on a monthly plan, the card is the plan's month and its button changes the plan", (
      tester,
    ) async {
      final services = await _services(plans: true);
      await _pump(tester, services, ProfileScreen(services: services));

      expect(find.text('Checks this month'), findsOneWidget);
      expect(find.text('Plus plan'), findsOneWidget);
      expect(find.text('checks left'), findsOneWidget);
      expect(find.text('78 of 120 plan checks used'), findsOneWidget);
      expect(find.textContaining('Resets '), findsOneWidget);
      expect(find.text('Change plan'), findsOneWidget);
      expect(find.text('Buy credits'), findsNothing);
      // A plan the server says renews is called renewing; a video's cost is the
      // price list's, not an ordinary check's.
      expect(find.textContaining('Renews '), findsOneWidget);
      expect(find.text('A video uses 3 checks'), findsOneWidget);
      // Nothing is enforced on this server, and the card says so.
      expect(
        find.text("During the preview you can keep checking after your plan's checks run out."),
        findsOneWidget,
      );
    });

    testWidgets('a plan paid once says when it ends, and when extra checks are paused', (
      tester,
    ) async {
      final services = await _services(plans: true, prepaid: true);
      await _pump(tester, services, ProfileScreen(services: services));

      expect(find.textContaining('Ends '), findsOneWidget);
      expect(find.textContaining('Renews '), findsNothing);
      expect(
        find.text('Extra checks are paused until your unpaid extra-usage bill is paid.'),
        findsOneWidget,
      );
    });

    testWidgets('without a plan, the costs name what a video costs', (tester) async {
      final services = await _services();
      await _pump(tester, services, ProfileScreen(services: services));
      expect(find.text('A check costs 1, a video 3'), findsOneWidget);
    });

    testWidgets('deleting the account asks twice, then deletes it and clears this phone', (
      tester,
    ) async {
      final services = await _services();
      await services.history.markReported('case-1');
      await _pump(tester, services, ProfileScreen(services: services));

      await tester.scrollUntilVisible(
        find.text('Delete account'),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Delete account'));
      await tester.pumpAndSettle();
      expect(find.text('Delete your account?'), findsOneWidget);
      expect(_calls, isNot(contains('DELETE /v1/me')));

      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();
      expect(find.text('Delete for good?'), findsOneWidget);
      expect(find.textContaining('asha@example.org will be deleted now'), findsOneWidget);
      expect(_calls, isNot(contains('DELETE /v1/me')));

      await tester.tap(find.text('Delete for good'));
      await tester.pumpAndSettle();
      expect(_calls, contains('DELETE /v1/me'));
      expect(services.auth.signedIn, isFalse);
      expect(services.history.isReported('case-1'), isFalse);
      expect(find.text('Your account has been deleted.'), findsOneWidget);
    });

    testWidgets("the server's reason is shown when it refuses to delete", (tester) async {
      final services = await _services(deleteStatus: 409);
      await _pump(tester, services, ProfileScreen(services: services));

      await tester.scrollUntilVisible(
        find.text('Delete account'),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Delete account'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Delete for good'));
      await tester.pumpAndSettle();

      expect(services.auth.signedIn, isTrue);
      expect(find.textContaining('You are the only owner of Acme News'), findsOneWidget);
      expect(find.textContaining("Your account wasn't deleted."), findsOneWidget);
    });

    testWidgets('the privacy policy is one tap away', (tester) async {
      final services = await _services();
      await _pump(tester, services, ProfileScreen(services: services));
      expect(find.text('Privacy policy'), findsOneWidget);
      expect(services.client.privacyPolicy.toString(), 'http://factify.test/privacy');
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
      await tester.ensureVisible(find.text('Notify when ready'));
      await tester.pumpAndSettle();
      await tester.tap(_switchIn('Notify when ready'));
      await tester.pumpAndSettle();
      expect((refused.notifier as _Notifier).asked, 1);
      expect(refused.notifyByDefault.value, isFalse);
      expect(find.textContaining('Notifications are off'), findsOneWidget);

      final allowed = await _services();
      await _pump(tester, allowed, ProfileScreen(services: allowed));
      await tester.ensureVisible(find.text('Notify when ready'));
      await tester.pumpAndSettle();
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

      // Further down since the credits card gained its Buy credits button.
      await tester.ensureVisible(find.text('Saved checks'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Saved checks'));
      expect(opened, 1);

      // Above "Saved checks", off screen since the floating-button row was added.
      await tester.ensureVisible(find.text('Language'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Language'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('हिन्दी'));
      await tester.pumpAndSettle();
      expect(services.language.value?.languageCode, 'hi');
      await tester.drag(find.byType(ListView).first, const Offset(0, 3000));
      await tester.pumpAndSettle();
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
      // Too many at once is the server's rate limit, not a spent allowance: wait, retry.
      var exits = await show(tester, CheckProblem.rateLimited);
      expect(find.text('Wait a minute, then try again'), findsOneWidget);
      await tester.tap(find.text('Try again'));
      expect(exits, ['retry']);

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
      expect(
        CheckProblem.of(const ApiFailure(FailureKind.rateLimited), link: false),
        CheckProblem.rateLimited,
      );
    });
  });
}
