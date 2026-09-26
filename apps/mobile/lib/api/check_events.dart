/// What a check is doing while it runs (contract 1.3), for the Checking screen.
///
/// The server publishes each step, each source as it is opened and whether it had
/// anything to say, and the evidence count, at `/v1/cases/{key}/events` as
/// Server-Sent Events. Read here over a plain `http` request, no SSE package: the
/// format is a few lines of text per event.
///
/// When the stream cannot be held open - a proxy that buffers it, a dropped
/// connection - the same events are polled from `/progress`. When neither answers,
/// the reader simply ends: the screen then shows what it knows (the clock, the
/// steps every check has) and never invents sources or counts.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:http/http.dart' as http;

/// One event, as the server numbered it.
class CheckEvent {
  const CheckEvent({
    required this.seq,
    required this.type,
    this.step,
    this.publisher,
    this.domain,
    this.initials,
    this.outcome,
    this.count,
    this.caseId,
    this.code,
  });

  factory CheckEvent.fromJson(Map<String, dynamic> json) => CheckEvent(
    seq: (json['seq'] as num?)?.toInt() ?? 0,
    type: json['type'] as String? ?? '',
    step: json['step'] as String?,
    publisher: json['publisher'] as String?,
    domain: json['domain'] as String?,
    initials: json['initials'] as String?,
    outcome: json['outcome'] as String?,
    count: (json['n'] as num?)?.toInt(),
    caseId: json['case_id'] as String?,
    code: json['code'] as String?,
  );

  final int seq;

  /// step, source_started, source_done, evidence_count, done or error.
  final String type;

  /// read, search or compare.
  final String? step;
  final String? publisher;
  final String? domain;
  final String? initials;

  /// evidence or not_relevant.
  final String? outcome;
  final int? count;
  final String? caseId;
  final String? code;

  bool get isFinal => type == 'done' || type == 'error';
}

/// A fresh id to follow a check by, sent as its `X-Request-ID`: a random UUID.
String newRequestId([Random? random]) {
  final source = random ?? Random.secure();
  final bytes = List<int>.generate(16, (_) => source.nextInt(256));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  final hex = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-'
      '${hex.substring(16, 20)}-${hex.substring(20)}';
}

/// The events in a Server-Sent Events body, one per message.
///
/// A message is its `data:` lines up to a blank line; `event:`, `id:` and comment
/// lines are ignored because the JSON carries the type and number itself.
Stream<CheckEvent> parseServerSentEvents(Stream<String> lines) async* {
  final data = StringBuffer();
  await for (final line in lines) {
    if (line.isEmpty) {
      if (data.isNotEmpty) {
        final decoded = _decode(data.toString());
        data.clear();
        if (decoded != null) yield decoded;
      }
      continue;
    }
    if (line.startsWith('data:')) {
      if (data.isNotEmpty) data.write('\n');
      data.write(line.substring(5).trimLeft());
    }
  }
}

CheckEvent? _decode(String data) {
  try {
    final json = jsonDecode(data);
    return json is Map<String, dynamic> ? CheckEvent.fromJson(json) : null;
  } on FormatException {
    return null;
  }
}

/// Follows one check: the stream first, polling if it fails, until the check ends.
///
/// [connect] makes the connection the stream is read over. It is closed, and any
/// wait between polls cut short, the moment the listener stops listening - which is
/// how a check that finished, or that the person left, stops being followed.
Stream<CheckEvent> followCheck(
  String baseUrl,
  String key, {
  http.Client Function() connect = http.Client.new,
  Duration pollEvery = const Duration(milliseconds: 1500),
  int giveUpAfter = 3,
}) {
  final client = connect();
  var stopped = false;
  var last = 0;
  Timer? sleeping;
  Completer<void>? woken;
  StreamSubscription<CheckEvent>? reading;
  late final StreamController<CheckEvent> out;

  Future<void> sleep(Duration duration) {
    final done = woken = Completer<void>();
    sleeping = Timer(duration, () {
      if (!done.isCompleted) done.complete();
    });
    return done.future;
  }

  // Passes an event on, once; true when it ends the check.
  bool pass(CheckEvent event) {
    if (stopped || event.seq <= last) return false;
    last = event.seq;
    out.add(event);
    return event.isFinal;
  }

  Future<bool> stream() async {
    final request = http.Request('GET', Uri.parse('$baseUrl/v1/cases/$key/events'))
      ..headers['accept'] = 'text/event-stream'
      ..headers['cache-control'] = 'no-cache';
    if (last > 0) request.headers['last-event-id'] = '$last';
    final response = await client.send(request).timeout(const Duration(seconds: 15));
    if (stopped || response.statusCode != 200) return false;
    final ended = Completer<bool>();
    final lines = response.stream.transform(utf8.decoder).transform(const LineSplitter());
    reading = parseServerSentEvents(lines).listen(
      (event) {
        if (pass(event) && !ended.isCompleted) ended.complete(true);
      },
      onError: (Object _) {
        if (!ended.isCompleted) ended.complete(false);
      },
      onDone: () {
        if (!ended.isCompleted) ended.complete(false);
      },
      cancelOnError: true,
    );
    final finished = await ended.future;
    await reading?.cancel();
    return finished;
  }

  Future<void> run() async {
    try {
      // The stream. Resumed once from the last event if the connection drops.
      for (var attempt = 0; attempt < 2 && !stopped; attempt++) {
        try {
          if (await stream()) return;
        } on Exception {
          // A second try, then polling.
        }
      }

      // Polling. Gives up after a few failures in a row: the answer itself is what
      // matters, and it arrives on its own request.
      var failures = 0;
      while (!stopped && failures < giveUpAfter) {
        await sleep(pollEvery);
        if (stopped) return;
        try {
          final response = await client
              .get(Uri.parse('$baseUrl/v1/cases/$key/progress?after=$last'))
              .timeout(const Duration(seconds: 10));
          final body = response.statusCode == 200 ? jsonDecode(response.body) : null;
          if (body is! Map || body['events'] is! List) {
            failures++;
            continue;
          }
          failures = 0;
          for (final item in body['events'] as List) {
            if (item is! Map) continue;
            if (pass(CheckEvent.fromJson(item.cast<String, dynamic>()))) return;
          }
          if (body['finished'] == true) return;
        } on Exception {
          failures++;
        }
      }
    } finally {
      client.close();
      if (!out.isClosed) unawaited(out.close());
    }
  }

  out = StreamController<CheckEvent>(
    onListen: () => unawaited(run()),
    onCancel: () {
      stopped = true;
      sleeping?.cancel();
      final waiting = woken;
      if (waiting != null && !waiting.isCompleted) waiting.complete();
      unawaited(reading?.cancel());
      client.close();
    },
  );
  return out.stream;
}
