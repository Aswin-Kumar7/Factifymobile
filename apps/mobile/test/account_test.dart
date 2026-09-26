/// Accounts in the app: sign in with an emailed code, then see the profile and the
/// credits the server reports. The server decides everything; these tests check the
/// app shows what it is told and sends who is asking.
library;

import 'dart:convert';

import 'package:factify_mobile/api/client.dart';
import 'package:factify_mobile/auth/auth_service.dart';
import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/screens/account_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _supabase = 'https://project.supabase.co';

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

/// Our server: sign-in on or off, and the profile for whoever sends the token.
FactifyClient _server({required bool signInOn, List<String?>? tokensSeen}) => FactifyClient(
  baseUrl: 'http://factify.test',
  httpClient: MockClient((request) async {
    tokensSeen?.add(request.headers['authorization']);
    if (request.url.path == '/v1/auth/config') {
      return http.Response(
        jsonEncode({
          'enabled': signInOn,
          'supabase_url': signInOn ? _supabase : null,
          'anon_key': signInOn ? 'public-key' : null,
          'required': false,
          'providers': signInOn ? ['email', 'google'] : [],
        }),
        200,
      );
    }
    if (request.url.path == '/v1/me') {
      return request.headers['authorization'] == 'Bearer access-1'
          ? http.Response(jsonEncode(_me()), 200)
          : http.Response('{"detail": "sign in"}', 401);
    }
    return http.Response('{}', 404);
  }),
);

/// Supabase Auth: sends a code, and accepts 123456.
MockClient _supabaseAuth(List<String> calls) => MockClient((request) async {
  calls.add(request.url.path);
  expect(request.headers['apikey'], 'public-key');
  if (request.url.path == '/auth/v1/otp') return http.Response('{}', 200);
  if (request.url.path == '/auth/v1/verify') {
    final body = jsonDecode(request.body) as Map<String, dynamic>;
    if (body['token'] != '123456') return http.Response('{"msg": "invalid"}', 403);
    return http.Response(
      jsonEncode({
        'access_token': 'access-1',
        'refresh_token': 'refresh-1',
        'expires_in': 3600,
        'user': {'email': 'asha@example.org'},
      }),
      200,
    );
  }
  return http.Response('{}', 404);
});

Future<void> _open(WidgetTester tester, AuthService auth) async {
  tester.view.physicalSize = const Size(1080, 2340);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      supportedLocales: AppLocalizations.supportedLocales,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      home: AccountScreen(auth: auth),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('says plainly when this server has sign-in switched off', (tester) async {
    final auth = AuthService(client: _server(signInOn: false), persist: false);
    await auth.start();

    await _open(tester, auth);

    expect(find.textContaining("isn't switched on"), findsOneWidget);
    expect(find.text('Email me a code'), findsNothing);
  });

  testWidgets('signs in with an emailed code and shows the credits the server reports', (
    tester,
  ) async {
    final calls = <String>[];
    final client = _server(signInOn: true);
    final auth = AuthService(client: client, httpClient: _supabaseAuth(calls), persist: false);
    client.tokenProvider = auth.accessToken;
    await auth.start();
    await _open(tester, auth);

    await tester.enterText(find.byType(TextField), 'asha@example.org');
    await tester.tap(find.text('Email me a code'));
    await tester.pumpAndSettle();
    expect(find.textContaining('We sent a 6-digit code'), findsOneWidget);

    await tester.enterText(find.byType(TextField).last, '123456');
    await tester.tap(find.text('Sign in'));
    await tester.pumpAndSettle();

    expect(calls, ['/auth/v1/otp', '/auth/v1/verify']);
    expect(find.text('Asha'), findsOneWidget);
    expect(find.text('asha@example.org'), findsOneWidget);
    expect(find.text('99 credits left'), findsOneWidget);
    expect(find.text('A check costs 1 · a deep check costs 3'), findsOneWidget);
  });

  testWidgets('a wrong code says so and stays on the code step', (tester) async {
    final client = _server(signInOn: true);
    final auth = AuthService(client: client, httpClient: _supabaseAuth([]), persist: false);
    await auth.start();
    await _open(tester, auth);

    await tester.enterText(find.byType(TextField), 'asha@example.org');
    await tester.tap(find.text('Email me a code'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, '000000');
    await tester.tap(find.text('Sign in'));
    await tester.pumpAndSettle();

    expect(find.textContaining("That code didn't work"), findsOneWidget);
    expect(auth.signedIn, isFalse);
  });

  test('Google sign-in returns through factify://auth-callback with the session', () async {
    final client = _server(signInOn: true);
    final auth = AuthService(client: client, persist: false);
    client.tokenProvider = auth.accessToken;
    await auth.start();

    expect(
      auth.googleSignIn().toString(),
      startsWith('$_supabase/auth/v1/authorize?provider=google'),
    );

    await auth.completeFromLink(
      Uri.parse(
        'factify://auth-callback#access_token=access-1&refresh_token=refresh-1'
        '&expires_in=3600&token_type=bearer',
      ),
    );

    expect(auth.signedIn, isTrue);
    expect(auth.account?.displayName, 'Asha');
  });

  test('a check carries the signed-in token, and "out of credits" is its own failure', () async {
    final seen = <String?>[];
    final client = FactifyClient(
      baseUrl: 'http://factify.test',
      httpClient: MockClient((request) async {
        seen.add(request.headers['authorization']);
        return http.Response('{"detail": "out of credits"}', 402);
      }),
    )..tokenProvider = () async => 'access-1';

    await expectLater(
      client.verifyText('A forward.'),
      throwsA(isA<ApiFailure>().having((f) => f.kind, 'kind', FailureKind.outOfCredits)),
    );
    expect(seen.single, 'Bearer access-1');
  });
}
