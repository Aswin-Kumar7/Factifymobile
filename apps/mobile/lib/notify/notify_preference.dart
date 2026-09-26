/// Whether a check is announced when it is ready, unless the person says otherwise
/// on the Checking screen (v5, Profile -> "Notify when ready").
///
/// Off by default: a notification is something a person asks for. Remembered on
/// this phone only, beside the interface language and the theme.
library;

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class NotifyPreference extends ValueNotifier<bool> {
  NotifyPreference._(super.value, this._store);

  /// A preference that is never written anywhere - for tests.
  factory NotifyPreference.inMemory([bool on = false]) => NotifyPreference._(on, null);

  static const String _key = 'notify_when_ready';

  final SharedPreferencesAsync? _store;

  /// The saved choice. Never throws: an unreadable store costs the saved choice,
  /// never the launch.
  static Future<NotifyPreference> load() async {
    try {
      final store = SharedPreferencesAsync();
      return NotifyPreference._(await store.getBool(_key) ?? false, store);
    } on Object {
      return NotifyPreference.inMemory();
    }
  }

  Future<void> choose(bool on) async {
    value = on;
    try {
      await _store?.setBool(_key, on);
    } on Object {
      // Still applied for this session; only remembering it failed.
    }
  }
}
