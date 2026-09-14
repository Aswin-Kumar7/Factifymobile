/// HTTP client for the Facify contract.
///
/// **This file holds no credential and never will.** The app talks only to our
/// own API, which holds the provider keys server-side. An app that carried a
/// Gemini or Vision key would ship that key to every device that installed it,
/// where it can be extracted from the APK in minutes.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../models/verdict.dart';

/// Where the API lives. Supplied at build time, never hard-coded to a secret:
///
///   flutter run --dart-define=FACIFY_API=https://facify-xxxx.a.run.app
const String apiBaseUrl = String.fromEnvironment(
  'FACIFY_API',
  // 10.0.2.2 is the host machine as seen from the Android emulator.
  defaultValue: 'http://10.0.2.2:8000',
);

/// Whether this build was compiled without `FACIFY_API`, and so still points at
/// the emulator's host address — which no real phone can reach.
const bool apiUsesEmulatorDefault = !bool.hasEnvironment('FACIFY_API');

/// A failure the interface can act on.
///
/// [retryable] separates "your request was wrong" from "try again shortly",
/// which is the difference between showing a correction and showing a spinner.
class ApiFailure implements Exception {
  const ApiFailure(this.message, {this.retryable = false, this.statusCode});

  final String message;
  final bool retryable;
  final int? statusCode;

  @override
  String toString() => message;
}

class FacifyClient {
  FacifyClient({http.Client? httpClient, this.baseUrl = apiBaseUrl})
    : _http = httpClient ?? http.Client();

  final http.Client _http;
  final String baseUrl;

  /// The synchronous budget the server targets is 3-8 seconds; allow headroom
  /// for a cold start rather than failing a request that was about to succeed.
  static const Duration _timeout = Duration(seconds: 45);

  Future<Verdict> verifyText(String text, {String? language}) =>
      _verify({'text': text, 'language': ?language});

  Future<Verdict> verifyUrl(String url, {String? language}) =>
      _verify({'url': url, 'language': ?language});

  Future<Verdict> _verify(Map<String, dynamic> body) async {
    final response = await _send(
      () => _http
          .post(
            Uri.parse('$baseUrl/v1/verify'),
            headers: const {'content-type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(_timeout),
    );
    return Verdict.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  /// Submit a file. Images and PDFs resolve synchronously; video returns 202
  /// with a case id to poll, because it cannot finish inside the budget.
  ///
  /// Sent through the injected client rather than `request.send()`, so the
  /// upload path is testable like every other call.
  Future<VerifyFileOutcome> verifyFile(File file, {bool consentToProcessMedia = false}) =>
      _guard(() async {
        final request = http.MultipartRequest('POST', Uri.parse('$baseUrl/v1/verify/file'))
          ..files.add(await http.MultipartFile.fromPath('file', file.path))
          ..fields['consent_to_process_media'] = consentToProcessMedia.toString();

        final streamed = await _http.send(request).timeout(_timeout);
        final response = await http.Response.fromStream(streamed).timeout(_timeout);
        _raiseFor(response);

        final payload = jsonDecode(response.body) as Map<String, dynamic>;
        if (response.statusCode == 202) {
          return VerifyFileOutcome.accepted(payload['case_id'] as String);
        }
        return VerifyFileOutcome.done(Verdict.fromJson(payload));
      });

  /// Retrieve a case previously computed, for polling an accepted video.
  Future<Verdict?> getCase(String caseId) => _guard(() async {
    final response = await _http.get(Uri.parse('$baseUrl/v1/cases/$caseId')).timeout(_timeout);
    if (response.statusCode == 404) return null;
    _raiseFor(response);
    return Verdict.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  });

  /// Flag a verdict for human review. Returns the queue confirmation.
  ///
  /// This is what the Report button actually does now. It previously showed
  /// "Reported for human review" while sending nothing anywhere — a fabricated
  /// confirmation in a product whose one claim is that it does not fabricate.
  Future<String> reportCase(String caseId) async {
    final response = await _send(
      () => _http
          .post(Uri.parse('$baseUrl/v1/cases/$caseId/report'))
          .timeout(const Duration(seconds: 15)),
    );
    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return (payload['status'] as String?) ?? 'queued for human review';
  }

  /// Whether the service can actually verify, not merely whether it is up.
  /// Distinct from [healthy]: a booted service with no database answers
  /// healthz 200 and readyz false.
  Future<bool> ready() async {
    try {
      final response = await _http
          .get(Uri.parse('$baseUrl/readyz'))
          .timeout(const Duration(seconds: 8));
      if (response.statusCode != 200) return false;
      final payload = jsonDecode(response.body) as Map<String, dynamic>;
      return payload['ready'] == true;
    } on Object {
      return false;
    }
  }

  Future<bool> healthy() async {
    try {
      final response = await _http
          .get(Uri.parse('$baseUrl/healthz'))
          .timeout(const Duration(seconds: 8));
      return response.statusCode == 200;
    } on Object {
      return false;
    }
  }

  Future<http.Response> _send(Future<http.Response> Function() call) async {
    final response = await _guard(call);
    _raiseFor(response);
    return response;
  }

  /// Every transport failure becomes an [ApiFailure] here, and only here.
  ///
  /// Image upload and case polling used to bypass this. They called `.timeout()`
  /// directly while the screen catches only [ApiFailure], so a timeout or a
  /// dropped connection on those paths escaped as an uncaught exception and the
  /// check simply stopped with nothing on screen. The text path fared little
  /// better: a timeout reached a catch-all and rendered, verbatim, as
  /// "Something went wrong: TimeoutException after 0:00:45.000000".
  Future<T> _guard<T>(Future<T> Function() call) async {
    try {
      return await call();
    } on ApiFailure {
      rethrow;
    } on TimeoutException {
      throw const ApiFailure(
        'Facify is taking longer than usual. Try again in a moment.',
        retryable: true,
      );
    } on SocketException {
      throw const ApiFailure(
        'Could not reach Facify. Check your connection and try again.',
        retryable: true,
      );
    } on http.ClientException {
      throw const ApiFailure(
        'The connection to Facify was interrupted. Try again.',
        retryable: true,
      );
    } on FileSystemException {
      throw const ApiFailure('That file could not be read from this phone.');
    } on FormatException {
      throw const ApiFailure('Facify sent a reply this app could not read.', retryable: true);
    } on Exception {
      throw const ApiFailure('Facify could not complete that check.', retryable: true);
    }
  }

  /// Turn a status code into a message a person can act on.
  ///
  /// 503 is called out separately: it means the service is up but not fully
  /// configured, which is a different situation from being down and a different
  /// one again from the request being wrong.
  void _raiseFor(http.Response response) {
    if (response.statusCode < 400) return;

    final detail = _detailOf(response.body);
    throw switch (response.statusCode) {
      400 ||
      422 => ApiFailure(detail ?? 'That input could not be read.', statusCode: response.statusCode),
      413 => const ApiFailure('That file is too large to check.', statusCode: 413),
      429 => const ApiFailure(
        'Facify is at its daily limit. Please try again tomorrow.',
        retryable: true,
        statusCode: 429,
      ),
      503 => ApiFailure(
        detail ?? 'Verification is not available right now.',
        retryable: true,
        statusCode: 503,
      ),
      _ => ApiFailure(
        'Facify could not complete that check.',
        retryable: response.statusCode >= 500,
        statusCode: response.statusCode,
      ),
    };
  }

  String? _detailOf(String body) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map && decoded['detail'] is String) return decoded['detail'] as String;
    } on FormatException {
      return null;
    }
    return null;
  }

  void close() => _http.close();
}

/// Either a finished verdict, or a case id to poll.
class VerifyFileOutcome {
  const VerifyFileOutcome._({this.verdict, this.pendingCaseId});

  factory VerifyFileOutcome.done(Verdict verdict) => VerifyFileOutcome._(verdict: verdict);
  factory VerifyFileOutcome.accepted(String caseId) => VerifyFileOutcome._(pendingCaseId: caseId);

  final Verdict? verdict;
  final String? pendingCaseId;

  bool get isPending => pendingCaseId != null;
}
