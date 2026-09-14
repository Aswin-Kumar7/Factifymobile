/// The translations, checked as files (M44, PLAN 1.7.6).
///
/// gen-l10n builds happily from a Hindi file that is missing keys — the missing
/// messages quietly fall back to English — and it does not notice a select case
/// whose keyword was translated along with its text, which makes that branch
/// unreachable. Either puts English, or the wrong sentence, on a Hindi screen, so
/// both are caught here.
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

const String _template = 'en';
const List<String> _translations = ['hi'];

Map<String, dynamic> _arb(String locale) =>
    jsonDecode(File('lib/l10n/app_$locale.arb').readAsStringSync()) as Map<String, dynamic>;

Map<String, String> _messages(Map<String, dynamic> arb) => {
  for (final entry in arb.entries)
    if (!entry.key.startsWith('@')) entry.key: entry.value as String,
};

/// Placeholder names the template declares for [key].
Set<String> _declared(Map<String, dynamic> template, String key) {
  final metadata = template['@$key'] as Map<String, dynamic>?;
  final placeholders = metadata?['placeholders'] as Map<String, dynamic>?;
  return placeholders?.keys.toSet() ?? const {};
}

/// The case keywords of a select or plural message: `supports{`, `=0{`, `other{`.
Set<String> _cases(String message) =>
    RegExp(r'(=\d+|[A-Za-z_]+)\{').allMatches(message).map((m) => m.group(1)!).toSet();

void main() {
  final template = _arb(_template);
  final english = _messages(template);

  for (final locale in _translations) {
    group('app_$locale.arb', () {
      final translated = _messages(_arb(locale));

      test('has exactly the template keys', () {
        expect(
          english.keys.toSet().difference(translated.keys.toSet()),
          isEmpty,
          reason: 'untranslated keys',
        );
        expect(
          translated.keys.toSet().difference(english.keys.toSet()),
          isEmpty,
          reason: 'keys the template does not have',
        );
      });

      test('keeps every placeholder and case keyword of the template', () {
        for (final key in english.keys) {
          final message = translated[key] ?? '';
          for (final name in _declared(template, key)) {
            expect(message, contains('{$name'), reason: '$key lost {$name}');
          }
          expect(_cases(message), _cases(english[key]!), reason: '$key changed its cases');
        }
      });

      test('translates every message', () {
        final untouched = [
          for (final key in english.keys)
            if (translated[key] == english[key]) key,
        ];
        expect(untouched, isEmpty, reason: 'identical to the English');
      });
    });
  }
}
