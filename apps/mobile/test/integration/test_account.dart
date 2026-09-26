/// An account for the live-server tests: every check needs one now.
///
/// Makes a fresh throwaway account on the server under test (an address on the
/// reserved `.test` domain, so it can never be a real person's) and returns its
/// session token, which the tests' client then sends like the app does.
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

Future<String> signUpForTests(String baseUrl) async {
  final stamp = DateTime.now().microsecondsSinceEpoch;
  final response = await http.post(
    Uri.parse('$baseUrl/v1/auth/register'),
    headers: {'content-type': 'application/json'},
    body: jsonEncode({
      'email': 'integration-$stamp@factify.test',
      'password': 'integration-test-$stamp',
      'name': 'Integration test',
    }),
  );
  if (response.statusCode != 201) {
    throw StateError('could not make a test account: ${response.statusCode} ${response.body}');
  }
  return (jsonDecode(response.body) as Map<String, dynamic>)['access_token'] as String;
}
