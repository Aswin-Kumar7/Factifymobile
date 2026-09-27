/// Whether text shared to Factify is answered over the chat, or opens the full app
/// (v5, 2.7; Profile -> "Answer over the chat").
///
/// On by default: answering over the chat is the point of sharing to Factify. Off
/// keeps the earlier way, the full app with the text in the Check box. Remembered
/// on this phone only, and read by the quick verdict when a share arrives.
library;

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class QuickVerdictPreference extends ValueNotifier<bool> {
  QuickVerdictPreference._(super.value, this._store);

  /// A preference that is never written anywhere - for tests.
  factory QuickVerdictPreference.inMemory([bool on = true]) => QuickVerdictPreference._(on, null);

  static const String _key = 'quick_verdict';

  final SharedPreferencesAsync? _store;

  /// The saved choice. Never throws: an unreadable store keeps the default.
  static Future<QuickVerdictPreference> load() async {
    try {
      final store = SharedPreferencesAsync();
      return QuickVerdictPreference._(await store.getBool(_key) ?? true, store);
    } on Object {
      return QuickVerdictPreference.inMemory();
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
