/// Signing up and signing in (compulsory accounts; v5, 2.1).
///
/// Sign-in is the Factify server's own: create an account with an email and a
/// password, or sign in with one; Google returns through factify://auth-callback.
/// The server decides every number shown; the app only shows it.
library;

import 'dart:convert';

import 'package:factify_mobile/api/client.dart';
import 'package:factify_mobile/auth/auth_service.dart';
import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/widgets/auth_form.dart';
import 'package:factify_mobile/widgets/ui/fx_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _token = 'fs_session-1';

Map<String, dynamic> _me({int balance = 99, int used = 1}) => {
  'id': 'u-1',
  'email': 'asha@example.org',
  'name': 'Asha',
  'avatar_url': null,
  'plan': 'free',
  'joined_at': '2026-09-26T10:00:00Z',
  'credits': {
    'balance': balance,
    'used': used,
    'checks': used,
    'check_cost': 1,
    'deep_check_cost': 3,
    'limited': false,
  },
};

Map<String, dynamic> _session() => {
  'access_token': _token,
  'expires_at': DateTime.now().add(const Duration(days: 30)).toIso8601String(),
  'method': 'password',
  'email': 'asha@example.org',
  'name': 'Asha',
};

/// A stand-in Factify server: its sign-in, and the profile of whoever holds a session.
MockClient _server({
  bool signInOn = true,
  List<String> google = const [],
  List<Map<String, dynamic>>? posted,
}) => MockClient((request) async {
  final path = request.url.path;
  if (path == '/v1/auth/config') {
    return http.Response(
      jsonEncode({
        'enabled': signInOn,
        'required': true,
        'providers': signInOn ? ['password', ...google] : [],
        'min_password_length': 8,
      }),
      200,
    );
  }
  if (path == '/v1/auth/register' || path == '/v1/auth/login') {
    final body = jsonDecode(request.body) as Map<String, dynamic>;
    posted?.add({'path': path, ...body});
    if (path == '/v1/auth/login' && body['password'] != 'long enough') {
      return http.Response('{"detail": "wrong_credentials"}', 401);
    }
    if (path == '/v1/auth/register' && body['email'] == 'taken@example.org') {
      return http.Response('{"detail": "email_taken"}', 409);
    }
    return http.Response(jsonEncode(_session()), path.endsWith('register') ? 201 : 200);
  }
  if (path == '/v1/me') {
    return request.headers['authorization'] == 'Bearer $_token'
        ? http.Response(jsonEncode(_me()), 200)
        : http.Response('{"detail": "sign in"}', 401);
  }
  if (path == '/v1/auth/logout') return http.Response('', 204);
  return http.Response('{}', 404);
});

(AuthService, FactifyClient) _auth(MockClient server) {
  final client = FactifyClient(baseUrl: 'http://factify.test', httpClient: server);
  final auth = AuthService(client: client, httpClient: server, persist: false);
  client.tokenProvider = auth.accessToken;
  return (auth, client);
}

Future<void> _open(WidgetTester tester, AuthService auth) async {
  tester.view.physicalSize = const Size(1080, 2340);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      supportedLocales: AppLocalizations.supportedLocales,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      home: Scaffold(
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: AuthForm(auth: auth),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Finder _field(String label) => find.widgetWithText(TextField, label);

void main() {
  testWidgets('says plainly when sign-in cannot be reached', (tester) async {
    final (auth, _) = _auth(_server(signInOn: false));
    await auth.start();

    await _open(tester, auth);

    expect(find.textContaining("can't be reached"), findsOneWidget);
    expect(find.text('Create account'), findsNothing);
  });

  testWidgets('creates an account with an email and a password, and no name', (tester) async {
    final posted = <Map<String, dynamic>>[];
    final (auth, _) = _auth(_server(posted: posted));
    await auth.start();
    await _open(tester, auth);

    // A name is optional, added later from Profile: the form does not ask.
    expect(_field('Name'), findsNothing);
    await tester.enterText(_field('Email'), 'asha@example.org');
    await tester.enterText(_field('Password'), 'long enough');
    await tester.enterText(_field('Confirm password'), 'long enough');
    await tester.pump();
    await tester.tap(find.widgetWithText(FxButton, 'Create account'));
    await tester.pumpAndSettle();

    expect(posted.single['path'], '/v1/auth/register');
    expect(posted.single.containsKey('name'), isFalse);
    expect(auth.signedIn, isTrue);
    expect(auth.session?.method, 'password');
    expect(auth.account?.balance, 99);
  });

  testWidgets('passwords that do not match are caught before anything is sent', (tester) async {
    final posted = <Map<String, dynamic>>[];
    final (auth, _) = _auth(_server(posted: posted));
    await auth.start();
    await _open(tester, auth);

    await tester.enterText(_field('Email'), 'asha@example.org');
    await tester.enterText(_field('Password'), 'long enough');
    await tester.enterText(_field('Confirm password'), 'something else');
    await tester.pump();
    await tester.tap(find.widgetWithText(FxButton, 'Create account'));
    await tester.pumpAndSettle();

    expect(find.text("The passwords don't match."), findsOneWidget);
    expect(posted, isEmpty);
  });

  testWidgets('"next" on the password goes to confirming it, not the eye button', (tester) async {
    final (auth, _) = _auth(_server());
    await auth.start();
    await _open(tester, auth);

    await tester.tap(_field('Password'));
    await tester.enterText(_field('Password'), 'long enough');
    await tester.testTextInput.receiveAction(TextInputAction.next);
    await tester.pumpAndSettle();

    final confirm = tester.widget<TextField>(_field('Confirm password'));
    expect(confirm.focusNode?.hasFocus, isTrue);
  });

  testWidgets('an email that already has an account says so', (tester) async {
    final (auth, _) = _auth(_server());
    await auth.start();
    await _open(tester, auth);

    await tester.enterText(_field('Email'), 'taken@example.org');
    await tester.enterText(_field('Password'), 'long enough');
    await tester.enterText(_field('Confirm password'), 'long enough');
    await tester.pump();
    await tester.tap(find.widgetWithText(FxButton, 'Create account'));
    await tester.pumpAndSettle();

    expect(find.textContaining("There's already an account with this email"), findsOneWidget);
    expect(auth.signedIn, isFalse);
  });

  testWidgets('signs in, and a wrong password says so', (tester) async {
    final (auth, _) = _auth(_server());
    await auth.start();
    await _open(tester, auth);

    await tester.tap(find.text('Sign in').first);
    await tester.pumpAndSettle();
    expect(_field('Confirm password'), findsNothing);

    await tester.enterText(_field('Email'), 'asha@example.org');
    await tester.enterText(_field('Password'), 'not the password');
    await tester.pump();
    await tester.tap(find.widgetWithText(FxButton, 'Sign in'));
    await tester.pumpAndSettle();
    expect(find.text("That email and password don't match an account."), findsOneWidget);

    await tester.enterText(_field('Password'), 'long enough');
    await tester.pump();
    await tester.tap(find.widgetWithText(FxButton, 'Sign in'));
    await tester.pumpAndSettle();
    expect(auth.signedIn, isTrue);
    expect(auth.account?.balance, 99);
  });

  testWidgets('Google is offered only once the server has it set up', (tester) async {
    final (auth, _) = _auth(_server());
    await auth.start();
    await _open(tester, auth);

    final google = tester.widget<ButtonStyleButton>(
      find.ancestor(
        of: find.text('Continue with Google'),
        matching: find.bySubtype<ButtonStyleButton>(),
      ),
    );
    expect(google.onPressed, isNull);
    expect(find.textContaining("Google sign-in isn't set up"), findsOneWidget);
  });

  test('Google sign-in returns through factify://auth-callback with the session', () async {
    final (auth, _) = _auth(_server(google: ['google']));
    await auth.start();
    expect(auth.googleAvailable, isTrue);

    await auth.completeFromLink(
      Uri.parse(
        'factify://auth-callback#access_token=$_token'
        '&expires_at=${Uri.encodeQueryComponent(DateTime.now().add(const Duration(days: 30)).toIso8601String())}'
        '&method=google&email=asha%40example.org',
      ),
    );

    expect(auth.signedIn, isTrue);
    expect(auth.session?.method, 'google');
    expect(auth.account?.displayName, 'Asha');
  });

  test('a Google sign-in that failed says so, and signs no one in', () async {
    final (auth, _) = _auth(_server(google: ['google']));
    await auth.start();

    await auth.completeFromLink(Uri.parse('factify://auth-callback#error=google_failed'));

    expect(auth.signedIn, isFalse);
    expect(auth.lastLinkProblem, AuthProblem.googleFailed);
  });

  test('signing out forgets the session here and ends it on the server', () async {
    final (auth, _) = _auth(_server());
    await auth.start();
    await auth.signIn(email: 'asha@example.org', password: 'long enough');
    expect(await auth.accessToken(), _token);

    await auth.signOut();

    expect(auth.signedIn, isFalse);
    expect(await auth.accessToken(), isNull);
  });

  test('a check carries the signed-in token, and "out of credits" is its own failure', () async {
    final seen = <String?>[];
    final client = FactifyClient(
      baseUrl: 'http://factify.test',
      httpClient: MockClient((request) async {
        seen.add(request.headers['authorization']);
        return http.Response('{"detail": "out of credits"}', 402);
      }),
    )..tokenProvider = () async => _token;

    await expectLater(
      client.verifyText('A forward.'),
      throwsA(isA<ApiFailure>().having((f) => f.kind, 'kind', FailureKind.outOfCredits)),
    );
    expect(seen.single, 'Bearer $_token');
  });
}
