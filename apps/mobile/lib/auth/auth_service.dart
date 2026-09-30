/// Signing in, and the signed-in person.
///
/// An account is compulsory: every check is made by someone signed in, and the
/// server refuses one that is not. Sign-in is the Factify server's own - an email
/// and a password, or Google in the browser - so this class talks only to our
/// server. The session is an opaque token the server issued; it is kept on this
/// phone and sent with every check. The server alone reads the credit ledger; this
/// class only shows what it is told.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/client.dart';
import '../models/account.dart';
import 'auth_links.dart';

/// Where the browser comes back to after signing in with Google.
const String authRedirect = 'factify://auth-callback';

/// Why signing in did not work, in terms the screen can put into words.
enum AuthProblem {
  invalidEmail,
  weakPassword,
  emailTaken,
  wrongCredentials,
  useGoogle,
  googleFailed,
  googleUnavailable,
  tooMany,
  network,
  unavailable,
  generic,
}

class AuthFailure implements Exception {
  const AuthFailure(this.problem);

  final AuthProblem problem;

  @override
  String toString() => 'AuthFailure(${problem.name})';
}

/// A session the server issued.
class AuthSession {
  const AuthSession({
    required this.accessToken,
    required this.expiresAt,
    required this.email,
    this.method = 'password',
  });

  final String accessToken;
  final DateTime expiresAt;
  final String email;

  /// How the person signed in: 'google' or 'password'. Shown on the profile.
  final String method;

  bool get expired => DateTime.now().isAfter(expiresAt);

  Map<String, dynamic> toJson() => {
    'access_token': accessToken,
    'expires_at': expiresAt.toIso8601String(),
    'email': email,
    'method': method,
  };

  static AuthSession? fromJson(Map<String, dynamic> json) {
    final access = json['access_token'] as String?;
    final expires = DateTime.tryParse(json['expires_at'] as String? ?? '');
    if (access == null || expires == null) return null;
    return AuthSession(
      accessToken: access,
      expiresAt: expires,
      email: json['email'] as String? ?? '',
      method: json['method'] as String? ?? 'password',
    );
  }
}

class AuthService extends ChangeNotifier {
  AuthService({
    required FactifyClient client,
    http.Client? httpClient,
    SharedPreferencesAsync? store,
    AuthLinks? links,
    bool persist = true,
  }) : _client = client,
       _http = httpClient ?? client.httpClient,
       _store = persist ? (store ?? SharedPreferencesAsync()) : null,
       _links = links;

  static const String _key = 'factify_session';

  final FactifyClient _client;
  final http.Client _http;
  final SharedPreferencesAsync? _store;
  final AuthLinks? _links;
  StreamSubscription<Uri>? _linkSubscription;

  AuthConfig _config = AuthConfig.off;
  AuthSession? _session;
  Account? _account;
  bool _started = false;
  AuthProblem? _lastLinkProblem;

  /// Whether this server can sign anyone in right now.
  bool get available => _config.enabled;

  /// Whether a check needs an account. The server decides, and enforces it.
  bool get required => _config.required;

  /// Whether Google sign-in is set up on this server.
  bool get googleAvailable => _config.providers.contains('google');

  int get minPasswordLength => _config.minPasswordLength;

  bool get signedIn => _session != null;
  AuthSession? get session => _session;
  Account? get account => _account;

  /// Whether [start] has finished: the saved session and the server's answer are in.
  bool get started => _started;

  /// Whether the app itself may open: only for someone signed in.
  bool get welcomed => signedIn;

  /// What the last Google sign-in came back with, when it failed.
  AuthProblem? get lastLinkProblem => _lastLinkProblem;

  /// Load the saved session, ask the server how to sign in, and listen for the link
  /// Google sign-in returns with. Never throws.
  Future<void> start() async {
    try {
      final saved = await _store?.getString(_key);
      if (saved != null) {
        final session = AuthSession.fromJson(jsonDecode(saved) as Map<String, dynamic>);
        _session = session == null || session.expired ? null : session;
      }
    } catch (_) {
      _session = null;
    }
    await reloadConfig();
    final links = _links;
    if (links != null) {
      _linkSubscription = links.links.listen((uri) => unawaited(completeFromLink(uri)));
      final first = await links.initial();
      if (first != null) await completeFromLink(first);
    }
    _started = true;
    notifyListeners();
    if (signedIn) unawaited(refreshAccount());
  }

  /// Ask the server again how to sign in: after coming back online, say.
  Future<void> reloadConfig() async {
    try {
      _config = await _client.authConfig();
    } catch (_) {
      _config = AuthConfig.off;
    }
    notifyListeners();
  }

  /// Create an account with an email and a password, and sign in.
  Future<void> register({required String email, required String password, String? name}) async {
    final body = await _post('register', {
      'email': email.trim(),
      'password': password,
      if (name != null && name.trim().isNotEmpty) 'name': name.trim(),
    });
    await _adopt(body);
  }

  /// Sign in with an email and a password.
  Future<void> signIn({required String email, required String password}) async {
    await _adopt(await _post('login', {'email': email.trim(), 'password': password}));
  }

  /// Sign in with Google: in the browser, which returns to [authRedirect].
  Future<void> startGoogle() async {
    if (!googleAvailable) throw const AuthFailure(AuthProblem.googleUnavailable);
    final opened = await launchUrl(
      Uri.parse('${_client.baseUrl}/v1/auth/google/start'),
      mode: LaunchMode.externalApplication,
    );
    if (!opened) throw const AuthFailure(AuthProblem.generic);
  }

  /// Finish a Google sign-in from the link the server sent the browser back with.
  /// The session is in the link's fragment, so it never reached any server's logs.
  Future<void> completeFromLink(Uri link) async {
    if (link.scheme != 'factify' || link.host != 'auth-callback') return;
    final values = Uri.splitQueryString(link.fragment.isNotEmpty ? link.fragment : link.query);
    final error = values['error'];
    if (error != null) {
      _lastLinkProblem = error == 'google_unavailable'
          ? AuthProblem.googleUnavailable
          : AuthProblem.googleFailed;
      notifyListeners();
      return;
    }
    _lastLinkProblem = null;
    await _adopt(values, method: 'google');
  }

  /// The token to send with a check. Null when signed out or the session is over.
  Future<String?> accessToken() async {
    final session = _session;
    if (session == null) return null;
    if (session.expired) {
      await signOut();
      return null;
    }
    return session.accessToken;
  }

  /// Ask the server for the latest profile and balance.
  Future<Account?> refreshAccount() async {
    if (!signedIn) return null;
    try {
      _account = await _client.me();
      notifyListeners();
    } on ApiFailure catch (failure) {
      if (failure.kind == FailureKind.signedOut) await signOut();
    }
    return _account;
  }

  Future<void> rename(String name) async {
    _account = await _client.rename(name);
    notifyListeners();
  }

  /// Answer the survey (null skips it). The account comes back with it no longer due.
  Future<void> answerSurvey(SurveyAnswers? answers) async {
    _account = await _client.answerSurvey(answers);
    notifyListeners();
  }

  Future<void> signOut() async {
    final session = _session;
    _session = null;
    _account = null;
    notifyListeners();
    try {
      await _store?.remove(_key);
    } catch (_) {}
    if (session != null) {
      // Best effort: the session is gone from this phone either way.
      unawaited(
        _http
            .post(
              Uri.parse('${_client.baseUrl}/v1/auth/logout'),
              headers: {'authorization': 'Bearer ${session.accessToken}'},
            )
            .then((_) {}, onError: (_) {}),
      );
    }
  }

  @override
  void dispose() {
    _linkSubscription?.cancel();
    super.dispose();
  }

  Future<void> _adopt(Map<String, dynamic> body, {String? method}) async {
    final access = body['access_token'] as String?;
    final expires = DateTime.tryParse(body['expires_at'] as String? ?? '');
    if (access == null || expires == null) throw const AuthFailure(AuthProblem.generic);
    final session = AuthSession(
      accessToken: access,
      expiresAt: expires,
      email: body['email'] as String? ?? '',
      method: method ?? body['method'] as String? ?? 'password',
    );
    _session = session;
    try {
      await _store?.setString(_key, jsonEncode(session.toJson()));
    } catch (_) {}
    notifyListeners();
    await refreshAccount();
  }

  Future<Map<String, dynamic>> _post(String path, Map<String, dynamic> body) async {
    if (!available) throw const AuthFailure(AuthProblem.unavailable);
    final http.Response response;
    try {
      response = await _http
          .post(
            Uri.parse('${_client.baseUrl}/v1/auth/$path'),
            headers: {'content-type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 20));
    } catch (_) {
      throw const AuthFailure(AuthProblem.network);
    }
    if (response.statusCode >= 300) throw AuthFailure(_problemOf(response));
    final decoded = jsonDecode(response.body);
    return decoded is Map<String, dynamic> ? decoded : const {};
  }

  static AuthProblem _problemOf(http.Response response) {
    String? reason;
    try {
      final detail = (jsonDecode(response.body) as Map<String, dynamic>)['detail'];
      reason = detail is String ? detail : null;
    } catch (_) {}
    return switch (reason) {
      'invalid_email' => AuthProblem.invalidEmail,
      'weak_password' => AuthProblem.weakPassword,
      'email_taken' => AuthProblem.emailTaken,
      'wrong_credentials' => AuthProblem.wrongCredentials,
      'use_google' => AuthProblem.useGoogle,
      'too_many_attempts' => AuthProblem.tooMany,
      'sign_in_unavailable' => AuthProblem.unavailable,
      _ =>
        response.statusCode == 429
            ? AuthProblem.tooMany
            : response.statusCode >= 500
            ? AuthProblem.unavailable
            : AuthProblem.generic,
    };
  }
}
