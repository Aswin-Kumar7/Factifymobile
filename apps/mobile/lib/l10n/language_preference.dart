/// The interface language (M44, PLAN 1.7.6): the phone's, unless the reader chose one.
///
/// A null value means "follow the phone" — the device language when Factify has
/// strings for it, English when it does not. A choice is remembered across
/// launches, because a Hindi reader on an English-language phone, a common setup,
/// would otherwise have to switch it back every time.
///
/// Kept on the phone beside the sign-in session and the history of checks (see
/// `history/history_store.dart`), which the person can clear from their profile.
library;

import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app_localizations.dart';

class LanguagePreference extends ValueNotifier<Locale?> {
  LanguagePreference._(super.value, this._store);

  /// A preference that is never written anywhere — for tests, and for a phone
  /// whose preference store could not be opened.
  factory LanguagePreference.inMemory([Locale? locale]) => LanguagePreference._(locale, null);

  static const String _key = 'interface_language';

  final SharedPreferencesAsync? _store;

  /// The saved choice, if there is one Factify still has strings for.
  ///
  /// Never throws. A store that cannot be read costs the reader their saved
  /// choice for one launch; it must not cost them the launch.
  static Future<LanguagePreference> load() async {
    try {
      final store = SharedPreferencesAsync();
      final saved = await store.getString(_key);
      final locale = AppLocalizations.supportedLocales
          .where((candidate) => candidate.languageCode == saved)
          .firstOrNull;
      return LanguagePreference._(locale, store);
    } on Object {
      return LanguagePreference.inMemory();
    }
  }

  /// Apply [locale] now, and remember it. Null returns to the phone's language.
  Future<void> choose(Locale? locale) async {
    value = locale;
    final store = _store;
    if (store == null) return;
    try {
      if (locale == null) {
        await store.remove(_key);
      } else {
        await store.setString(_key, locale.languageCode);
      }
    } on Object {
      // The choice still applies for this session; only remembering it failed.
    }
  }
}
