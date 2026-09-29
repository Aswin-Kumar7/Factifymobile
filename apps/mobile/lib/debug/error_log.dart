/// Framework errors kept on the phone, in debug builds only.
///
/// A red error screen on the emulator (2026-09-29: "check that it really is our
/// descendant", from InheritedElement.notifyClients, after the app sat for hours on a
/// result) could not be traced: the phone's log had already rolled over, and ten
/// tries did not bring it back. Each error is now also appended to `errors.log` in
/// the app's own files, whole and with its stack, so the next one can be read with
/// `adb shell run-as com.factify.factify_mobile cat files/errors.log`.
///
/// Nothing here runs in a release build, and the file never leaves the phone.
library;

import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

/// Past this the file is started again, so it cannot fill the phone.
const int _maxBytes = 200 * 1024;

/// Keep every framework error in `errors.log` as well as the console.
Future<void> keepFrameworkErrors() async {
  if (!kDebugMode) return;
  final Directory directory;
  try {
    directory = await getApplicationSupportDirectory();
  } catch (_) {
    return;
  }
  final file = File('${directory.path}/errors.log');
  final shown = FlutterError.onError;
  FlutterError.onError = (details) {
    shown?.call(details);
    try {
      if (file.existsSync() && file.lengthSync() > _maxBytes) {
        file.writeAsStringSync('');
      }
      file.writeAsStringSync(
        '=== ${DateTime.now().toIso8601String()}\n$details\n${details.stack ?? ''}\n\n',
        mode: FileMode.append,
        flush: true,
      );
    } catch (_) {}
  };
}
