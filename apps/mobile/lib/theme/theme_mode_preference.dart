/// Light, dark, or the phone's own setting (v5, Profile → Dark mode).
///
/// "System" is the default: a phone already set to dark gets Factify dark without
/// being asked. A choice is remembered beside the interface language
/// (lib/l10n/language_preference.dart), on this phone only.
library;

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class ThemeModePreference extends ValueNotifier<ThemeMode> {
  ThemeModePreference._(super.value, this._store);

  /// A preference that is never written anywhere - for tests.
  factory ThemeModePreference.inMemory([ThemeMode mode = ThemeMode.system]) =>
      ThemeModePreference._(mode, null);

  static const String _key = 'theme_mode';

  final SharedPreferencesAsync? _store;

  /// The saved choice. Never throws: an unreadable store costs one launch the saved
  /// choice, never the launch.
  static Future<ThemeModePreference> load() async {
    try {
      final store = SharedPreferencesAsync();
      final saved = await store.getString(_key);
      final mode = ThemeMode.values.where((m) => m.name == saved).firstOrNull ?? ThemeMode.system;
      return ThemeModePreference._(mode, store);
    } on Object {
      return ThemeModePreference.inMemory();
    }
  }

  Future<void> choose(ThemeMode mode) async {
    value = mode;
    try {
      await _store?.setString(_key, mode.name);
    } on Object {
      // Still applied for this session; only remembering it failed.
    }
  }
}
