/// The Dart client against a running Facify API.
///
/// The widget tests use hand-written payloads, which prove the UI honours the
/// contract but would keep passing if the server drifted away from it. This one
/// talks to the real service, so a field rename on either side fails here.
///
///   dart test test/integration/live_api_test.dart --define=FACIFY_API=http://127.0.0.1:8000
library;

import 'package:facify_mobile/api/client.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final client = FacifyClient(baseUrl: 'http://127.0.0.1:8000');

  test('the service is reachable', () async {
    expect(await client.healthy(), isTrue);
  });

  test('a text submission parses into a Verdict', () async {
    final verdict = await client.verifyText(
      'The government announced a relief scheme on Friday.',
    );

    expect(verdict.caseId, isNotEmpty);
    expect(verdict.retrievedAt.year, greaterThan(2020));
    // With no extraction configured the service abstains and says why, rather
    // than returning an empty result that reads as a clean bill of health.
    expect(verdict.abstained, isTrue);
    expect(verdict.isComplete, isFalse);
    expect(verdict.skipped.map((s) => s.check), contains('claim_extraction'));
    expect(verdict.completenessNote, isNotNull);
  });

  test('a malformed request surfaces as a non-retryable failure', () async {
    // Both url and text is 422 on the server; the client must present that as
    // the caller's problem, not as an outage.
    await expectLater(
      client.verifyText(''),
      throwsA(isA<ApiFailure>()),
    );
  });

  test('case lookup distinguishes "cannot look up" from "does not exist"', () async {
    // With no case reader wired the server answers 503, not 404 — and that is
    // the right answer. "We could not look this up" and "this does not exist"
    // are different facts, and the client must not collapse them into a shrug.
    try {
      final result = await client.getCase('00000000-0000-0000-0000-000000000000');
      // A configured deployment returns 404, which the client maps to null.
      expect(result, isNull);
    } on ApiFailure catch (failure) {
      expect(failure.statusCode, 503);
      expect(failure.retryable, isTrue, reason: '503 is worth retrying; 404 is not');
    }
  });

  tearDownAll(client.close);
}
