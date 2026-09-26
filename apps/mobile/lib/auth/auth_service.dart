/// Signing in, staying signed in, and the signed-in person's account.
///
/// Sign-in is Supabase Auth, spoken to directly over HTTP — an emailed six-digit
/// code, or Google through the browser — so no auth SDK ships in the app. What the
/// app holds afterwards is the session: an access token it sends with each check, and
/// a refresh token to renew it. Nothing about what was checked is stored.
///
/// The server decides everything that matters. It verifies the token with Supabase
/// on every request, and it alone reads the credit ledger; this class only shows
/// what `/v1/me` returns.
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

/// Where Supabase sends someone back after Google sign-in. Must be listed in the
/// Supabase project's allowed redirect URLs.
const String authRedirect = 'factify://auth-callback';

enum AuthProblem { unavailable, network, wrongCode, tooMany, generic }

class AuthFailure implements Exception {
  const AuthFailure(this.problem);
  final AuthProblem problem;

  @override
  String toString() => 'AuthFailure(${problem.name})';
}

/// The session Supabase issued.
class AuthSession {
  const AuthSession({
    required this.accessToken,
    required this.refreshToken,
    required this.expiresAt,
    required this.email,
  });

  final String accessToken;
  final String refreshToken;
  final DateTime expiresAt;
  final String email;

  /// Renewed a minute early, so a check never leaves with a token that expires
  /// on the way.
  bool get stale => DateTime.now().isAfter(expiresAt.subtract(const Duration(minutes: 1)));

  Map<String, dynamic> toJson() => {
    'access_token': accessToken,
    'refresh_token': refreshToken,
    'expires_at': expiresAt.toIso8601String(),
    'email': email,
  };

  static AuthSession? fromJson(Map<String, dynamic> json) {
    final access = json['access_token'] as String?;
    final refresh = json['refresh_token'] as String?;
    final expires = DateTime.tryParse(json['expires_at'] as String? ?? '');
    if (access == null || refresh == null || expires == null) return null;
    return AuthSession(
      accessToken: access,
      refreshToken: refresh,
      expiresAt: expires,
      email: json['email'] as String? ?? '',
    );
  }

  /// From Supabase's token response, or a sign-in link's fragment.
  static AuthSession? fromSupabase(Map<String, dynamic> body) {
    final access = body['access_token'] as String?;
    final refresh = body['refresh_token'] as String?;
    if (access == null || refresh == null) return null;
    final seconds = int.tryParse('${body['expires_in'] ?? 3600}') ?? 3600;
    final user = body['user'];
    final email = user is Map ? (user['email'] as String? ?? '') : '';
    return AuthSession(
      accessToken: access,
      refreshToken: refresh,
      expiresAt: DateTime.now().add(Duration(seconds: seconds)),
      email: email,
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
       _http = httpClient ?? http.Client(),
       _store = persist ? (store ?? SharedPreferencesAsync()) : null,
       _links = links;

  static const String _key = 'auth_session';

  final FactifyClient _client;
  final http.Client _http;
  final SharedPreferencesAsync? _store;
  final AuthLinks? _links;
  StreamSubscription<Uri>? _linkSubscription;
  Future<AuthSession?>? _refreshing;

  AuthConfig _config = AuthConfig.off;
  AuthSession? _session;
  Account? _account;

  /// Whether this server offers sign-in at all.
  bool get available => _config.enabled;
  bool get signedIn => _session != null;
  AuthSession? get session => _session;
  Account? get account => _account;

  /// Load the saved session, ask the server how to sign in, and listen for the
  /// link Google sign-in returns with. Never throws: a failure leaves sign-in off.
  Future<void> start() async {
    try {
      final saved = await _store?.getString(_key);
      if (saved != null) {
        _session = AuthSession.fromJson(jsonDecode(saved) as Map<String, dynamic>);
      }
    } catch (_) {
      _session = null;
    }
    try {
      _config = await _client.authConfig();
    } catch (_) {
      _config = AuthConfig.off;
    }
    final links = _links;
    if (links != null) {
      _linkSubscription = links.links.listen((uri) => unawaited(completeFromLink(uri)));
      final first = await links.initial();
      if (first != null) await completeFromLink(first);
    }
    notifyListeners();
    if (signedIn) unawaited(refreshAccount());
  }

  /// Email a six-digit sign-in code.
  Future<void> sendCode(String email) async {
    await _supabase('otp', {'email': email.trim(), 'create_user': true});
  }

  /// Sign in with the code from the email.
  Future<void> verifyCode(String email, String code) async {
    final body = await _supabase('verify', {
      'type': 'email',
      'email': email.trim(),
      'token': code.trim(),
    });
    await _adopt(AuthSession.fromSupabase(body));
  }

  /// Where Google sign-in starts: Supabase's authorize page, in the browser.
  Uri googleSignIn() {
    _requireAvailable();
    return Uri.parse(
      '${_config.supabaseUrl}/auth/v1/authorize',
    ).replace(queryParameters: {'provider': 'google', 'redirect_to': authRedirect});
  }

  Future<void> startGoogle() async {
    final opened = await launchUrl(googleSignIn(), mode: LaunchMode.externalApplication);
    if (!opened) throw const AuthFailure(AuthProblem.generic);
  }

  /// Finish a sign-in from the link Supabase sent the person back with. The session
  /// is in the link's fragment, so it never reached any server's logs on the way.
  Future<void> completeFromLink(Uri link) async {
    if (link.scheme != 'factify' || link.host != 'auth-callback') return;
    final values = Uri.splitQueryString(link.fragment.isNotEmpty ? link.fragment : link.query);
    await _adopt(AuthSession.fromSupabase(values));
  }

  /// The token to send with a check, renewed first if it is about to expire. Null
  /// when signed out, or when renewal is refused (the person is then signed out).
  Future<String?> accessToken() async {
    final session = _session;
    if (session == null) return null;
    if (!session.stale) return session.accessToken;
    final renewed = await (_refreshing ??= _renew(session).whenComplete(() => _refreshing = null));
    return renewed?.accessToken;
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

  Future<void> signOut() async {
    final session = _session;
    _session = null;
    _account = null;
    notifyListeners();
    try {
      await _store?.remove(_key);
    } catch (_) {}
    if (session != null && available) {
      // Best effort: the local session is already gone either way.
      unawaited(
        _http
            .post(
              Uri.parse('${_config.supabaseUrl}/auth/v1/logout'),
              headers: {..._headers, 'authorization': 'Bearer ${session.accessToken}'},
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

  Future<AuthSession?> _renew(AuthSession session) async {
    try {
      final body = await _supabase('token?grant_type=refresh_token', {
        'refresh_token': session.refreshToken,
      });
      final renewed = AuthSession.fromSupabase(body);
      if (renewed == null) throw const AuthFailure(AuthProblem.generic);
      final kept = AuthSession(
        accessToken: renewed.accessToken,
        refreshToken: renewed.refreshToken,
        expiresAt: renewed.expiresAt,
        email: renewed.email.isEmpty ? session.email : renewed.email,
      );
      await _save(kept);
      return kept;
    } on AuthFailure catch (failure) {
      // Refused: the session is over. A network failure keeps it for next time.
      if (failure.problem != AuthProblem.network) await signOut();
      return null;
    }
  }

  Future<void> _adopt(AuthSession? session) async {
    if (session == null) throw const AuthFailure(AuthProblem.generic);
    await _save(session);
    notifyListeners();
    await refreshAccount();
  }

  Future<void> _save(AuthSession session) async {
    _session = session;
    try {
      await _store?.setString(_key, jsonEncode(session.toJson()));
    } catch (_) {}
  }

  Map<String, String> get _headers => {
    'apikey': _config.anonKey ?? '',
    'content-type': 'application/json',
  };

  void _requireAvailable() {
    if (!available || _config.supabaseUrl == null) {
      throw const AuthFailure(AuthProblem.unavailable);
    }
  }

  Future<Map<String, dynamic>> _supabase(String path, Map<String, dynamic> body) async {
    _requireAvailable();
    final http.Response response;
    try {
      response = await _http
          .post(
            Uri.parse('${_config.supabaseUrl}/auth/v1/$path'),
            headers: _headers,
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 20));
    } catch (_) {
      throw const AuthFailure(AuthProblem.network);
    }
    if (response.statusCode == 429) throw const AuthFailure(AuthProblem.tooMany);
    if (response.statusCode == 400 || response.statusCode == 401 || response.statusCode == 403) {
      throw const AuthFailure(AuthProblem.wrongCode);
    }
    if (response.statusCode >= 300) throw const AuthFailure(AuthProblem.generic);
    if (response.body.isEmpty) return const {};
    final decoded = jsonDecode(response.body);
    return decoded is Map<String, dynamic> ? decoded : const {};
  }
}
