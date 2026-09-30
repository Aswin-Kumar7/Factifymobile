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

import '../models/account.dart';
import '../models/correction_message.dart';
import '../models/source_view.dart';
import 'check_events.dart';
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

  /// 401: the sign-in session has ended; the person must sign in again.
  signedOut,

  /// 402: the server says this person has no credits left for this check.
  outOfCredits,

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
    : _http = httpClient ?? http.Client(),
      _ownsHttp = httpClient == null;

  final http.Client _http;
  final bool _ownsHttp;

  /// The connection this client uses, shared with sign-in so there is one pool.
  http.Client get httpClient => _http;
  final String baseUrl;

  /// The signed-in person's access token, when there is one (see
  /// lib/auth/auth_service.dart). Sent with checks and account calls so the server
  /// can record and decide credits; the app decides nothing about them itself.
  Future<String?> Function()? tokenProvider;

  Future<Map<String, String>> _signedIn() async {
    final token = await tokenProvider?.call();
    return token == null ? const {} : {'authorization': 'Bearer $token'};
  }

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
  ///
  /// [requestId] is the id the Checking screen follows this check's progress by
  /// (lib/api/check_events.dart). Sent as `X-Request-ID`, which the server also logs
  /// the request under.
  Future<Verdict> verifyText(
    String text, {
    String? language,
    bool recheck = false,
    String? requestId,
  }) => _verify({
    'text': text,
    'language': ?language,
    if (recheck) 'recheck': true,
  }, requestId: requestId);

  Future<Verdict> verifyUrl(
    String url, {
    String? language,
    bool recheck = false,
    String? requestId,
  }) => _verify({
    'url': url,
    'language': ?language,
    if (recheck) 'recheck': true,
  }, requestId: requestId);

  Future<Verdict> _verify(Map<String, dynamic> body, {String? requestId}) async {
    final auth = await _signedIn();
    final response = await _send(
      () => _http
          .post(
            Uri.parse('$baseUrl/v1/verify'),
            headers: {'content-type': 'application/json', ...auth, 'x-request-id': ?requestId},
            body: jsonEncode(body),
          )
          .timeout(_timeout),
    );
    return Verdict.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  /// Submit a file. With [background] (what the app sends, contract 1.4) the
  /// server answers 202 with a case id for any file and checks it while the app
  /// follows it; without it, images and PDFs resolve in this request and only
  /// video returns 202.
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
    bool background = false,
    String? requestId,
    void Function(int sent, int total)? onProgress,
  }) => _guard(() async {
    final request = http.MultipartRequest('POST', Uri.parse('$baseUrl/v1/verify/file'))
      ..files.add(await http.MultipartFile.fromPath('file', file.path))
      ..fields['consent_to_process_media'] = consentToProcessMedia.toString();
    if (language != null) request.fields['language'] = language;
    if (recheck) request.fields['recheck'] = 'true';
    if (background) request.fields['background'] = 'true';
    request.headers.addAll(await _signedIn());
    if (requestId != null) request.headers['x-request-id'] = requestId;

    final streamed = await _http.send(_CountedUpload(request, onProgress)).timeout(_timeout);
    final response = await http.Response.fromStream(streamed).timeout(_timeout);
    _raiseFor(response);

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode == 202) {
      return VerifyFileOutcome.accepted(payload['case_id'] as String);
    }
    return VerifyFileOutcome.done(Verdict.fromJson(payload));
  });

  /// Start a check. The server answers at once with a case id and checks every
  /// claim in the background, taking the time that needs (contract 1.4); follow it
  /// with [checkOn].
  Future<String> startCheck({
    String? text,
    String? url,
    String? language,
    bool recheck = false,
  }) async {
    final auth = await _signedIn();
    final response = await _send(
      () => _http
          .post(
            Uri.parse('$baseUrl/v1/verify'),
            headers: {'content-type': 'application/json', ...auth},
            body: jsonEncode({
              'text': ?text,
              'url': ?url,
              'language': ?language,
              'mode': 'background',
              if (recheck) 'recheck': true,
            }),
          )
          .timeout(const Duration(seconds: 30)),
    );
    return (jsonDecode(response.body) as Map<String, dynamic>)['case_id'] as String;
  }

  /// Where a check running in the background has got to: its progress while it
  /// runs, its verdict when done. A refusal (such as nothing to check on a page) is
  /// raised as a failure.
  Future<CheckProgress> checkOn(String caseId) async {
    final response = await _send(
      () => _http.get(Uri.parse('$baseUrl/v1/cases/$caseId')).timeout(const Duration(seconds: 20)),
    );
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode == 202) {
      return CheckProgress(
        done: (body['claims_done'] as num?)?.toInt() ?? 0,
        total: (body['claims_total'] as num?)?.toInt() ?? 0,
      );
    }
    return CheckProgress(verdict: Verdict.fromJson(body));
  }

  /// How to sign in, from the server. Public values only.
  Future<AuthConfig> authConfig() async {
    final response = await _send(
      () => _http.get(Uri.parse('$baseUrl/v1/auth/config')).timeout(const Duration(seconds: 15)),
    );
    return AuthConfig.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  /// The signed-in person's profile and credits.
  Future<Account> me() async {
    final auth = await _signedIn();
    final response = await _send(
      () => _http
          .get(Uri.parse('$baseUrl/v1/me'), headers: auth)
          .timeout(const Duration(seconds: 20)),
    );
    return Account.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<Account> rename(String name) async {
    final auth = await _signedIn();
    final response = await _send(
      () => _http
          .patch(
            Uri.parse('$baseUrl/v1/me'),
            headers: {'content-type': 'application/json', ...auth},
            body: jsonEncode({'name': name}),
          )
          .timeout(const Duration(seconds: 20)),
    );
    return Account.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  /// Answer the survey, or skip it with null. Asked once, after a new account.
  Future<Account> answerSurvey(SurveyAnswers? answers) async {
    final auth = await _signedIn();
    final response = await _send(
      () => _http
          .put(
            Uri.parse('$baseUrl/v1/me/survey'),
            headers: {'content-type': 'application/json', ...auth},
            body: jsonEncode(answers == null ? {'skipped': true} : answers.toJson()),
          )
          .timeout(const Duration(seconds: 20)),
    );
    return Account.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<Verdict?> getCase(String caseId) => _guard(() async {
    final response = await _http.get(Uri.parse('$baseUrl/v1/cases/$caseId')).timeout(_timeout);
    // 202 is a video still being checked: not an answer yet. It was read as one,
    // failed on the missing verdict, and left the Checking screen waiting forever.
    if (response.statusCode == 404 || response.statusCode == 202) return null;
    _raiseFor(response);
    return Verdict.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  });

  /// A cited passage in its article, for the source reader. [url] finds the
  /// citation by its page when [evidenceId] is a fresh result's own id rather than
  /// the stored one.
  Future<SourceView> source(String caseId, String evidenceId, {String? url}) => _guard(() async {
    final uri = Uri.parse(
      '$baseUrl/v1/cases/$caseId/sources/${Uri.encodeComponent(evidenceId)}',
    ).replace(queryParameters: url == null ? null : {'url': url});
    final response = await _http.get(uri).timeout(const Duration(seconds: 30));
    _raiseFor(response);
    return SourceView.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  });

  /// The polite note to send back to the chat with a correction, in English ("en")
  /// or Hindi ("hi"). Written by the server from the stored answer, by template.
  Future<CorrectionMessage> correctionText(String caseId, String language) => _guard(() async {
    final response = await _http
        .post(
          Uri.parse('$baseUrl/v1/cases/$caseId/correction-text'),
          headers: {'content-type': 'application/json'},
          body: jsonEncode({'language': language}),
        )
        .timeout(const Duration(seconds: 15));
    _raiseFor(response);
    return CorrectionMessage.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
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

  /// What a check is doing while it runs, from the id it was sent with (1.3). Read
  /// over its own connection, so leaving the check can close it; a test's client
  /// is borrowed instead, so the test answers these requests like any other.
  Stream<CheckEvent> follow(String key) =>
      followCheck(baseUrl, key, connect: _ownsHttp ? http.Client.new : () => _Borrowed(_http));

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
  ///
  /// A dropped connection is tried once more first. The server closes a connection
  /// that has sat idle, and a check started just as it did failed as "The connection
  /// to Factify was interrupted" - three times in an evening of checks, each time the
  /// request never having reached the server (2026-09-30). Every call builds its
  /// request inside [call], so the retry sends a fresh one.
  Future<T> _guard<T>(Future<T> Function() call, {bool again = true}) async {
    try {
      return await call();
    } on ApiFailure {
      rethrow;
    } on TimeoutException {
      throw const ApiFailure(FailureKind.timeout, retryable: true);
    } on SocketException {
      throw const ApiFailure(FailureKind.unreachable, retryable: true);
    } on http.ClientException {
      if (again) return _guard(call, again: false);
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
      401 => ApiFailure(FailureKind.signedOut, statusCode: code, detail: detail),
      402 => ApiFailure(FailureKind.outOfCredits, statusCode: code, detail: detail),
      429 => ApiFailure(FailureKind.dailyLimit, retryable: true, statusCode: code, detail: detail),
      503 => ApiFailure(FailureKind.unavailable, retryable: true, statusCode: code, detail: detail),
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
/// A background check's state: claims done of total while it runs, the verdict
/// when done. The total is zero until the claims have been read out of the input.
class CheckProgress {
  const CheckProgress({this.verdict, this.done = 0, this.total = 0});

  final Verdict? verdict;
  final int done;
  final int total;
}

class VerifyFileOutcome {
  const VerifyFileOutcome._({this.verdict, this.pendingCaseId});

  factory VerifyFileOutcome.done(Verdict verdict) => VerifyFileOutcome._(verdict: verdict);
  factory VerifyFileOutcome.accepted(String caseId) => VerifyFileOutcome._(pendingCaseId: caseId);

  final Verdict? verdict;
  final String? pendingCaseId;

  bool get isPending => pendingCaseId != null;
}

/// Someone else's client, used without closing it.
class _Borrowed extends http.BaseClient {
  _Borrowed(this._inner);

  final http.Client _inner;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) => _inner.send(request);

  @override
  void close() {}
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
