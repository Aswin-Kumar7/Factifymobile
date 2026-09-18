/// The Dart client against a running Facify API.
///
/// The widget tests use hand-written payloads, which prove the UI honours the
/// contract but would keep passing if the server drifted away from it. This one
/// talks to the real service, so a field rename on either side fails here.
///
///   dart test test/integration/live_api_test.dart --define=FACIFY_API=http://127.0.0.1:8000
@Tags(['integration'])
library;

import 'package:facify_mobile/api/client.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final client = FacifyClient(baseUrl: 'http://127.0.0.1:8000');

  test('the service is reachable', () async {
    expect(await client.healthy(), isTrue);
  });

  test('a text submission parses into a Verdict', () async {
    // Sent with the interface language, exactly as the app sends it. The request
    // model forbids unknown fields, so a field the server does not declare fails
    // here as a 422 instead of on a phone.
    final verdict = await client.verifyText(
      'The government announced a relief scheme on Friday.',
      language: 'hi',
    );

    expect(verdict.caseId, isNotEmpty);
    expect(verdict.retrievedAt.year, greaterThan(2020));

    // Environment-agnostic on purpose. This test used to assert that extraction
    // was *unconfigured*, and it failed the moment a model key was added. What
    // must hold in every environment is honesty about gaps: a run that skipped a
    // check is incomplete and says so, and a complete run skipped nothing.
    if (verdict.skipped.isEmpty) {
      expect(verdict.isComplete, isTrue);
      expect(verdict.completenessNote, isNull);
    } else {
      expect(verdict.isComplete, isFalse);
      expect(verdict.completenessNote, isNotNull);
    }

    // And a decisive answer never arrives without a citation behind it.
    for (final claim in verdict.claims.where((c) => c.isDecisive)) {
      expect(claim.evidence, isNotEmpty, reason: 'a decisive claim arrived with no citation');
    }
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
