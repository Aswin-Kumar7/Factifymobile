/// The HTTP client against a stand-in server.
///
/// The live integration test proves the contract against the real API; these
/// prove what the client itself does with a request, without a network.
library;

import 'dart:convert';
import 'dart:io';

import 'package:factify_mobile/api/client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Map<String, dynamic> _verdictJson() => {
  'case_id': 'case-1',
  'contract_version': '1.0',
  'action': 'SEND_TO_REVIEW',
  'action_reason': 'Not enough citable evidence to decide.',
  'rule_version': '2026.08.1',
  'claims': <Map<String, dynamic>>[],
  'advisories': <Map<String, dynamic>>[],
  'skipped': <Map<String, dynamic>>[],
  'completeness_note': null,
  'retrieved_at': '2026-09-14T10:00:00Z',
  'from_cache': false,
  'elapsed_ms': 700,
};

void main() {
  test('a file upload reports progress through to the whole body, and sends every field', () async {
    final folder = await Directory.systemTemp.createTemp('factify_upload_test');
    addTearDown(() => folder.delete(recursive: true));
    final file = File('${folder.path}/picture.png')
      ..writeAsBytesSync(List<int>.generate(200000, (i) => i % 256));

    late http.Request received;
    final client = FactifyClient(
      baseUrl: 'http://factify.test',
      httpClient: MockClient((request) async {
        received = request;
        return http.Response(jsonEncode(_verdictJson()), 200);
      }),
    );

    final progress = <(int, int)>[];
    final outcome = await client.verifyFile(
      file,
      consentToProcessMedia: true,
      language: 'hi',
      onProgress: (sent, total) => progress.add((sent, total)),
    );

    expect(outcome.isPending, isFalse);
    expect(progress.length, greaterThan(1), reason: 'progress should arrive in steps');
    final (sent, total) = progress.last;
    expect(sent, total, reason: 'the whole body went out');
    expect(total, received.bodyBytes.length);

    expect(received.headers['content-type'], startsWith('multipart/form-data; boundary='));
    final body = latin1.decode(received.bodyBytes);
    expect(body, contains('name="consent_to_process_media"'));
    expect(body, contains('name="language"'));
  });

  test('an upload the server rejects surfaces as a failure the screen can phrase', () async {
    final folder = await Directory.systemTemp.createTemp('factify_upload_test');
    addTearDown(() => folder.delete(recursive: true));
    final file = File('${folder.path}/big.png')..writeAsBytesSync(List<int>.filled(1024, 7));

    final client = FactifyClient(
      baseUrl: 'http://factify.test',
      httpClient: MockClient(
        (_) async => http.Response('{"detail": "the upload exceeds 1 bytes"}', 413),
      ),
    );

    await expectLater(
      client.verifyFile(file, onProgress: (_, _) {}),
      throwsA(isA<ApiFailure>().having((f) => f.kind, 'kind', FailureKind.tooLarge)),
    );
  });

  test('a connection the server had just closed is tried once more on a fresh one', () async {
    var calls = 0;
    final client = FactifyClient(
      baseUrl: 'http://factify.test',
      httpClient: MockClient((_) async {
        calls += 1;
        if (calls == 1) {
          throw http.ClientException('Connection closed before full header was received');
        }
        return http.Response(jsonEncode(_verdictJson()), 200);
      }),
    );

    final verdict = await client.getCase('case-1');

    expect(calls, 2);
    expect(verdict, isNotNull);
  });

  test('a connection that drops twice is reported as interrupted', () async {
    final client = FactifyClient(
      baseUrl: 'http://factify.test',
      httpClient: MockClient((_) async => throw http.ClientException('Connection reset')),
    );

    await expectLater(
      client.getCase('case-1'),
      throwsA(isA<ApiFailure>().having((f) => f.kind, 'kind', FailureKind.interrupted)),
    );
  });

  test('429 is too many at once, not out of checks; 402 is out of checks', () async {
    for (final (status, kind) in [
      (429, FailureKind.rateLimited),
      (402, FailureKind.outOfCredits),
    ]) {
      final client = FactifyClient(
        baseUrl: 'http://factify.test',
        httpClient: MockClient((_) async => http.Response('{"detail": "x"}', status)),
      );
      await expectLater(
        client.startCheck(text: 'A claim.'),
        throwsA(isA<ApiFailure>().having((f) => f.kind, 'kind', kind)),
      );
    }
  });

  test(
    "deleting the account sends DELETE /v1/me, and a refusal keeps the server's reason",
    () async {
      final sent = <String>[];
      var status = 204;
      final client = FactifyClient(
        baseUrl: 'http://factify.test',
        httpClient: MockClient((request) async {
          sent.add('${request.method} ${request.url.path}');
          return status == 204
              ? http.Response('', 204)
              : http.Response(
                  jsonEncode({
                    'detail': 'You are the only owner of Acme. Make someone else an owner first.',
                    'error_code': 'owns_organisations',
                  }),
                  status,
                );
        }),
      );

      await client.deleteAccount();
      expect(sent, ['DELETE /v1/me']);

      status = 409;
      await expectLater(
        client.deleteAccount(),
        throwsA(
          isA<ApiFailure>()
              .having((f) => f.kind, 'kind', FailureKind.conflict)
              .having((f) => f.detail, 'detail', contains('only owner of Acme')),
        ),
      );
    },
  );

  test('what each kind of check costs comes from the price list', () async {
    final client = FactifyClient(
      baseUrl: 'http://factify.test',
      httpClient: MockClient(
        (_) async => http.Response(
          jsonEncode({
            'packs': <Object>[],
            'costs': {'text': 1, 'link': 1, 'picture': 1, 'pdf': 1, 'video': 3},
          }),
          200,
        ),
      ),
    );
    final costs = await client.checkCosts();
    expect(costs['text'], 1);
    expect(costs['video'], 3);
  });
}
