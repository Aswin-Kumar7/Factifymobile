/// Sign-in links handed back to the app.
///
/// Google sign-in finishes in the browser, and Supabase sends the person back to
/// `factify://auth-callback` with their session in the link. MainActivity passes
/// that link here over a platform channel, the way it passes shares — no plugin.
library;

import 'dart:async';

import 'package:flutter/services.dart';

class AuthLinks {
  AuthLinks() {
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'onAuthLink' && call.arguments is String) {
        _links.add(Uri.parse(call.arguments as String));
      }
    });
  }

  static const MethodChannel _channel = MethodChannel('factify/auth');
  final StreamController<Uri> _links = StreamController<Uri>.broadcast();

  /// Links arriving while the app is running.
  Stream<Uri> get links => _links.stream;

  /// The link that launched the app, if one did. Null in tests and on a normal
  /// launch.
  Future<Uri?> initial() async {
    try {
      final link = await _channel.invokeMethod<String>('getInitialAuthLink');
      return link == null ? null : Uri.parse(link);
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
  }
}
