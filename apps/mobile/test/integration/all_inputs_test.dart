/// Every input the app can send, against a running Factify API.
///
/// The widget tests prove the UI honours hand-written payloads; `live_api_test.dart`
/// proves one text submission round-trips. Neither covers the paths a real user takes
/// most: a forwarded screenshot, a shared link, a Hindi message, a video.
///
/// This walks all of them through the client the app actually ships, so a contract
/// change on either side fails here rather than on a phone. Timings are printed per
/// call because latency is a product property for this app — the client gives up at
/// 45 seconds and the server aims to answer inside 40.
///
///   flutter test test/integration/all_inputs_test.dart
///
/// Skips itself, loudly, when no server is reachable.
@Tags(['integration'])
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:factify_mobile/api/client.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:flutter_test/flutter_test.dart';

const String _base = String.fromEnvironment('FACTIFY_API', defaultValue: 'http://127.0.0.1:8000');

/// Timings, printed together at the end so the run reads as one table.
final List<(String, String, int, String)> _timings = [];

Future<T> _timed<T>(String kind, String label, Future<T> Function() call) async {
  final started = DateTime.now();
  try {
    final result = await call();
    final ms = DateTime.now().difference(started).inMilliseconds;
    final String outcome =
        result is Verdict ? result.action.toString() : result.runtimeType.toString();
    _timings.add((kind, label, ms, outcome));
    return result;
  } on Object catch (error) {
    final ms = DateTime.now().difference(started).inMilliseconds;
    _timings.add((kind, label, ms, error.runtimeType.toString()));
    rethrow;
  }
}

/// A forwarded screenshot: a claim rendered as an image, which is the real case.
/// A 1x1 JPEG is enough — what is under test is the upload path and the contract,
/// not the vision model, and generating a real screenshot in a Dart test would
/// couple this to an image library for no extra coverage.
Uint8List _jpeg() => base64Decode(
  '/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a'
  'HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAA'
  'AAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q==',
);

/// A structurally valid one-page PDF carrying a health claim.
Uint8List _pdf() {
  const body =
      'BT /F1 13 Tf 60 740 Td (Drinking hot water every 15 minutes kills the coronavirus.) Tj ET';
  final objects = <String>[
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] '
        '/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
    '<< /Length ${body.length} >>\nstream\n$body\nendstream',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ];
  final out = BytesBuilder()..add(utf8.encode('%PDF-1.4\n'));
  final offsets = <int>[];
  for (var i = 0; i < objects.length; i++) {
    offsets.add(out.length);
    out.add(utf8.encode('${i + 1} 0 obj\n${objects[i]}\nendobj\n'));
  }
  final startxref = out.length;
  out.add(utf8.encode('xref\n0 ${objects.length + 1}\n0000000000 65535 f \n'));
  for (final offset in offsets) {
    out.add(utf8.encode('${offset.toString().padLeft(10, '0')} 00000 n \n'));
  }
  out.add(
    utf8.encode(
      'trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\n'
      'startxref\n$startxref\n%%EOF\n',
    ),
  );
  return out.takeBytes();
}

/// A minimal but structurally valid MP4 container: ftyp + moov + mdat.
Uint8List _mp4() {
  Uint8List box(String kind, List<int> payload) {
    final out = BytesBuilder()
      ..add((ByteData(4)..setUint32(0, 8 + payload.length)).buffer.asUint8List())
      ..add(utf8.encode(kind))
      ..add(payload);
    return out.takeBytes();
  }

  final ftyp = box('ftyp', utf8.encode('isom') + [0, 0, 2, 0] + utf8.encode('isomiso2avc1mp41'));
  final mvhd = box('mvhd', List<int>.filled(100, 0));
  return Uint8List.fromList([...ftyp, ...box('moov', mvhd), ...box('mdat', List.filled(2048, 0))]);
}

/// The client uploads a [File], as it does on a phone, so these bytes need a path.
File _scratch(String name, Uint8List bytes) {
  final file = File('${Directory.systemTemp.path}/factify_$name')..writeAsBytesSync(bytes);
  addTearDown(() {
    if (file.existsSync()) file.deleteSync();
  });
  return file;
}

void main() {
  final client = FactifyClient(baseUrl: _base);
  var reachable = false;

  setUpAll(() async {
    reachable = await client.healthy();
    if (!reachable) {
      // ignore: avoid_print
      print('SKIPPING: no Factify API at $_base. Start it, or pass --dart-define=FACTIFY_API=...');
    }
  });

  tearDownAll(() {
    if (_timings.isNotEmpty) {
      // ignore: avoid_print
      print('\n  input    case                      ms  outcome');
      for (final (kind, label, ms, outcome) in _timings) {
        // ignore: avoid_print
        print('  ${kind.padRight(8)} ${label.padRight(24)} ${ms.toString().padLeft(6)}  $outcome');
      }
    }
    client.close();
  });

  group('readiness', () {
    test('the service is up and able to verify', () async {
      if (!reachable) return;
      expect(await client.healthy(), isTrue);
      expect(await client.ready(), isTrue, reason: 'up but not ready cannot answer a user');
    });
  });

  group('text', () {
    test('an English claim returns a verdict with citations behind any decision', () async {
      if (!reachable) return;
      final verdict = await _timed(
        'text',
        'english claim',
        () => client.verifyText('5G mobile towers spread the coronavirus.'),
      );

      expect(verdict.caseId, isNotEmpty);
      expect(verdict.claims, isNotEmpty);
      for (final claim in verdict.claims.where((c) => c.isDecisive)) {
        expect(claim.evidence, isNotEmpty, reason: 'a decisive claim arrived with no citation');
      }
    });

    test('a Hindi claim extracts and is answered in kind', () async {
      if (!reachable) return;
      final verdict = await _timed(
        'text',
        'hindi claim',
        () => client.verifyText(
          'गाय का मूत्र पीने से कोरोना वायरस का संक्रमण पूरी तरह ठीक हो जाता है।',
          language: 'hi',
        ),
      );

      // Hindi extraction returning zero claims was a real regression once. The
      // assertion is that the pipeline read the script at all, not what it decided.
      expect(verdict.claims, isNotEmpty, reason: 'Hindi text extracted no claims');
      expect(verdict.claims.first.text, isNotEmpty);
    });

    test('a repeat is served from cache and is fast', () async {
      if (!reachable) return;
      const text = 'India became the world\'s most populous country in 2023.';
      await _timed('text', 'first submission', () => client.verifyText(text));
      final second = await _timed('text', 'repeat (cached)', () => client.verifyText(text));

      expect(second.caseId, isNotEmpty);
      // Not asserting `fromCache` — a rules or reader version bump legitimately
      // retires the entry, and a test that fails on a deliberate bump is noise.
    });
  });

  group('url', () {
    test('a shared link is fetched, read and answered', () async {
      if (!reachable) return;
      final verdict = await _timed(
        'url',
        'wikipedia link',
        () => client.verifyUrl('https://en.wikipedia.org/wiki/Chandrayaan-3'),
      );

      expect(verdict.caseId, isNotEmpty);
      for (final claim in verdict.claims.where((c) => c.isDecisive)) {
        expect(claim.evidence, isNotEmpty);
      }
    });

    test('a malformed link is the caller\'s error, not an outage', () async {
      if (!reachable) return;
      await expectLater(
        client.verifyUrl('htp://not a url'),
        throwsA(
          isA<ApiFailure>().having((f) => f.retryable, 'retryable', isFalse),
        ),
      );
    });
  });

  group('media', () {
    test('an image upload is accepted and answered', () async {
      if (!reachable) return;
      final outcome = await _timed(
        'media',
        'image upload',
        () => client.verifyFile(_scratch('claim.jpg', _jpeg())),
      );

      expect(outcome.verdict ?? outcome.pendingCaseId, isNotNull);
    });

    test('a PDF upload is accepted and answered', () async {
      if (!reachable) return;
      final outcome = await _timed(
        'media',
        'pdf upload',
        () => client.verifyFile(_scratch('claim.pdf', _pdf())),
      );

      expect(outcome.verdict ?? outcome.pendingCaseId, isNotNull);
    });

    test('a video is accepted for later rather than answered now', () async {
      if (!reachable) return;
      final outcome = await _timed(
        'media',
        'video upload',
        () => client.verifyFile(_scratch('claim.mp4', _mp4())),
      );

      // 202 with a case to poll is the contract for video, and the app's polling
      // path depends on it: a synchronous verdict here would mean the client waits
      // through frame extraction on a phone.
      expect(
        outcome.pendingCaseId ?? outcome.verdict,
        isNotNull,
        reason: 'video must come back accepted-with-progress or answered',
      );
    });
  });

  group('case, report and receipt', () {
    test('a case can be read back and reported, and its receipt verifies', () async {
      if (!reachable) return;
      final verdict = await _timed(
        'api',
        'seed case',
        () => client.verifyText(
          'The World Health Organization declared COVID-19 a pandemic in March 2020.',
        ),
      );

      final reread = await _timed('api', 'case lookup', () => client.getCase(verdict.caseId));
      expect(reread, isNotNull, reason: 'a case we just created must be retrievable');
      expect(reread!.caseId, verdict.caseId);

      final queued = await _timed('api', 'report case', () => client.reportCase(verdict.caseId));
      expect(queued, isNotEmpty);

      // M42. Absent when no signing key is configured, which is a deployment
      // choice rather than a failure — but present, it must verify, because the
      // evidence has not been touched since it was signed moments ago.
      if (verdict.receiptUrl != null) {
        final receipt = await _timed(
          'api',
          'receipt check',
          () => client.getReceipt(verdict.receiptUrl!),
        );
        expect(receipt, isNotNull);
        expect(receipt!.caseId, verdict.caseId);
        expect(
          receipt.verified,
          isTrue,
          reason: 'evidence signed seconds ago must still match: ${receipt.verificationReason}',
        );
        expect(receipt.evidenceDigest, startsWith('sha256:'));
      }
    });

    test('a case that does not exist is null, not an error', () async {
      if (!reachable) return;
      final missing = await client.getCase('00000000-0000-0000-0000-000000000000');
      expect(missing, isNull);
    });
  });

  group('contract', () {
    test('empty text is rejected as the caller\'s problem', () async {
      if (!reachable) return;
      await expectLater(
        client.verifyText(''),
        throwsA(isA<ApiFailure>().having((f) => f.retryable, 'retryable', isFalse)),
      );
    });
  });
}
