/// HTTP client for the Factify contract.
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
///   flutter run --dart-define=FACTIFY_API=https://factify-xxxx.a.run.app
const String apiBaseUrl = String.fromEnvironment(
  'FACTIFY_API',
  // 10.0.2.2 is the host machine as seen from the Android emulator.
  defaultValue: 'http://10.0.2.2:8000',
);

/// Whether this build was compiled without `FACTIFY_API`, and so still points at
/// the emulator's host address — which no real phone can reach.
const bool apiUsesEmulatorDefault = !bool.hasEnvironment('FACTIFY_API');

/// Why a request failed, named rather than worded.
///
/// This client used to carry English sentences, which pinned every error to one
/// language however the interface was set. It now says *what* went wrong, and
/// the screen puts that into the reader's language (`lib/l10n/phrases.dart`).
enum FailureKind {
  /// The server did not answer within the client's budget.
  timeout,

  /// No route to the server at all.
  unreachable,

  /// The connection dropped part-way through.
  interrupted,

  /// The chosen file could not be read on the phone.
  unreadableFile,

  /// The reply was not the JSON the contract promises.
  badReply,

  /// 400 or 422: the request itself was wrong.
  invalidInput,

  /// 413.
  tooLarge,

  /// 429.
  dailyLimit,

  /// 503: the service is up but cannot verify.
  unavailable,

  /// Anything else.
  generic,
}

/// A failure the interface can act on.
///
/// [retryable] separates "your request was wrong" from "try again shortly",
/// which is the difference between showing a correction and showing a spinner.
class ApiFailure implements Exception {
  const ApiFailure(this.kind, {this.retryable = false, this.statusCode, this.detail});

  final FailureKind kind;
  final bool retryable;
  final int? statusCode;

  /// The server's own explanation, when it sent one. Kept for logs and never
  /// shown: the API writes these for developers ("unavailable", "the upload
  /// exceeds 26214400 bytes"), and only in English.
  final String? detail;

  @override
  String toString() =>
      'ApiFailure(${kind.name}'
      '${statusCode == null ? '' : ', HTTP $statusCode'}'
      '${detail == null ? '' : ': $detail'})';
}

class FactifyClient {
  FactifyClient({http.Client? httpClient, this.baseUrl = apiBaseUrl})
    : _http = httpClient ?? http.Client();

  final http.Client _http;
  final String baseUrl;

  /// How long to wait before deciding the server is not coming back.
  ///
  /// This said "the server targets 3-8 seconds" and allowed 45, which was true
  /// before verification read its sources. The server now gives itself forty
  /// (`REASONING_TARGET_SECONDS`), answers at that mark with whatever it has, and
  /// marks the run incomplete — so 45 left five seconds of margin, and a long
  /// article spends all of it. Measured: a request that returned a perfectly good
  /// verdict in 42.3 seconds, five times over, right on the edge of being thrown
  /// away by the app that asked for it.
  ///
  /// Seventy-five is not a slower app. It is the difference between showing a
  /// verdict the server already computed and showing a timeout instead.
  static const Duration _timeout = Duration(seconds: 75);

  /// [language] is the interface language, so the verdict can be phrased in the
  /// language it will be read in (PLAN 1.7.6).
  ///
  /// [recheck] is "Check again": the server skips its stored verdict and checks
  /// from scratch, because the stored one is what the person is asking to replace.
  Future<Verdict> verifyText(String text, {String? language, bool recheck = false}) =>
      _verify({'text': text, 'language': ?language, if (recheck) 'recheck': true});

  Future<Verdict> verifyUrl(String url, {String? language, bool recheck = false}) =>
      _verify({'url': url, 'language': ?language, if (recheck) 'recheck': true});

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
  ///
  /// [language] travels as a form field, like the JSON endpoints' field. The file
  /// endpoint does not read it yet (B5 in docs/hackathon-workflow.md); sending it
  /// now means the server can start honouring it without an app release.
  ///
  /// [onProgress] reports bytes the connection has taken against the whole body,
  /// so a slow upload shows how far it has got instead of an endless spinner.
  Future<VerifyFileOutcome> verifyFile(
    File file, {
    bool consentToProcessMedia = false,
    String? language,
    bool recheck = false,
    void Function(int sent, int total)? onProgress,
  }) => _guard(() async {
    final request = http.MultipartRequest('POST', Uri.parse('$baseUrl/v1/verify/file'))
      ..files.add(await http.MultipartFile.fromPath('file', file.path))
      ..fields['consent_to_process_media'] = consentToProcessMedia.toString();
    if (language != null) request.fields['language'] = language;
    if (recheck) request.fields['recheck'] = 'true';

    final streamed = await _http.send(_CountedUpload(request, onProgress)).timeout(_timeout);
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

  /// Fetch a receipt and the outcome of re-checking it against stored evidence.
  ///
  /// Takes the path the verdict handed us rather than building one from an id: the
  /// server decides where its receipts live, and a client that guesses the route is
  /// a client that breaks when the route changes. Returns null for 404 — a receipt
  /// that does not exist is an answer, not an error.
  Future<Receipt?> getReceipt(String receiptPath) => _guard(() async {
    final path = receiptPath.startsWith('http') ? receiptPath : '$baseUrl$receiptPath';
    final response = await _http.get(Uri.parse(path)).timeout(_timeout);
    if (response.statusCode == 404) return null;
    _raiseFor(response);
    return Receipt.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  });

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
      throw const ApiFailure(FailureKind.timeout, retryable: true);
    } on SocketException {
      throw const ApiFailure(FailureKind.unreachable, retryable: true);
    } on http.ClientException {
      throw const ApiFailure(FailureKind.interrupted, retryable: true);
    } on FileSystemException {
      throw const ApiFailure(FailureKind.unreadableFile);
    } on FormatException {
      throw const ApiFailure(FailureKind.badReply, retryable: true);
    } on Exception {
      throw const ApiFailure(FailureKind.generic, retryable: true);
    }
  }

  /// Turn a status code into a failure the interface can phrase and act on.
  ///
  /// 503 is called out separately: it means the service is up but not fully
  /// configured, which is a different situation from being down and a different
  /// one again from the request being wrong.
  void _raiseFor(http.Response response) {
    final code = response.statusCode;
    if (code < 400) return;

    final detail = _detailOf(response.body);
    throw switch (code) {
      400 || 422 => ApiFailure(FailureKind.invalidInput, statusCode: code, detail: detail),
      413 => ApiFailure(FailureKind.tooLarge, statusCode: code, detail: detail),
      429 => ApiFailure(
        FailureKind.dailyLimit,
        retryable: true,
        statusCode: code,
        detail: detail,
      ),
      503 => ApiFailure(
        FailureKind.unavailable,
        retryable: true,
        statusCode: code,
        detail: detail,
      ),
      _ => ApiFailure(
        FailureKind.generic,
        retryable: code >= 500,
        statusCode: code,
        detail: detail,
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

/// A multipart upload whose body is counted as the connection takes it.
///
/// Counted in the stream the HTTP client consumes, not while the file is read
/// into a buffer: the client pulls chunks only as fast as the socket accepts them,
/// so the count follows the upload rather than jumping to done before a byte has
/// left the phone.
class _CountedUpload extends http.BaseRequest {
  _CountedUpload(this._request, this._onProgress) : super(_request.method, _request.url);

  final http.MultipartRequest _request;
  final void Function(int sent, int total)? _onProgress;

  @override
  http.ByteStream finalize() {
    // Read before finalizing the inner request, which is what writes the
    // multipart boundary into its headers.
    final total = _request.contentLength;
    final body = _request.finalize();
    headers.addAll(_request.headers);
    contentLength = total;
    super.finalize();

    var sent = 0;
    return http.ByteStream(
      body.map((chunk) {
        sent += chunk.length;
        _onProgress?.call(sent, total);
        return chunk;
      }),
    );
  }
}
