/// Share-sheet intake, over a platform channel to MainActivity.
///
/// Replaces `receive_sharing_intent`, which cannot be built with the current
/// Android toolchain: its `build.gradle` calls `kotlin { ... }` without applying
/// the Kotlin plugin, so evaluating it aborts the build. This path is the app's
/// primary intake, so it is worth owning rather than depending on.
library;

import 'dart:async';

import 'package:flutter/services.dart';

/// What arrived from another app.
class SharedContent {
  const SharedContent({required this.kind, required this.value, this.mimeType});

  /// One of `text`, `url`, `file` or `error`.
  final String kind;

  /// The text itself, or a path to a file already copied into our cache.
  final String value;
  final String? mimeType;

  bool get isFile => kind == 'file';
  bool get isUrl => kind == 'url';

  /// The share arrived but could not be read. [value] then carries the native
  /// side's English description, for logs — the interface shows its own message,
  /// in the reader's language.
  bool get isError => kind == 'error';

  static SharedContent? fromMap(Map<Object?, Object?>? map) {
    if (map == null) return null;
    final kind = map['kind'] as String?;
    final value = map['value'] as String?;
    if (kind == null || value == null || value.isEmpty) return null;
    return SharedContent(kind: kind, value: value, mimeType: map['mimeType'] as String?);
  }
}

/// Both delivery paths, because either alone drops shares.
///
/// [initial] is the share that *launched* the app — it happens before Dart is
/// listening, so the native side parks it and Dart collects it once. [stream]
/// carries shares that arrive while the app is already running. Wiring only the
/// stream is the classic bug: the first share after a cold start does nothing.
class ShareIntake {
  ShareIntake() {
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'onShare') {
        final content = SharedContent.fromMap((call.arguments as Map?)?.cast<Object?, Object?>());
        if (content != null) _controller.add(content);
      }
    });
  }

  static const MethodChannel _channel = MethodChannel('factify/share');
  final StreamController<SharedContent> _controller = StreamController<SharedContent>.broadcast();

  Stream<SharedContent> get stream => _controller.stream;

  /// The share that launched the app, if there was one. Returns null on a
  /// normal launch, and null on every call after the first.
  Future<SharedContent?> initial() async {
    try {
      final result = await _channel.invokeMethod<Map<Object?, Object?>>('getInitialShare');
      return SharedContent.fromMap(result);
    } on PlatformException {
      // A share we cannot read is an absent share, not a crash on startup.
      return null;
    } on MissingPluginException {
      // Running under a test harness or a platform without the channel.
      return null;
    }
  }

  void dispose() => _controller.close();
}
