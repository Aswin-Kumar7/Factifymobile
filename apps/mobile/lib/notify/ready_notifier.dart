/// "Your check is ready" (v5, section 2.8 and 3.2).
///
/// Two things, both local to the phone: while a check someone asked to be told
/// about is running, a quiet ongoing notification keeps the app alive as a
/// foreground service, so Android does not stop the check when they go back to
/// their chat; when it is done, a notification with the verdict and the start of
/// what was checked, and two actions - open the result, or share the correction.
///
/// Nothing is sent anywhere. The notification is drawn from the History record
/// already kept on this phone; the server is never told a notification exists.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import '../history/history_store.dart';
import '../l10n/app_localizations.dart';
import '../models/verdict.dart';
import '../theme/tokens.dart';
import '../widgets/action_style.dart';

/// What a tap on a notification asks for.
class ReadyTap {
  const ReadyTap(this.recordId, {this.share = false});

  final String recordId;

  /// The "Share correction" action rather than the notification itself.
  final bool share;
}

abstract class ReadyNotifier {
  /// Keeps the app running while a check the person will be told about runs.
  Future<void> keepAlive({required String language});

  /// Lets it go again.
  Future<void> release();

  /// Announces a finished check.
  Future<void> ready(HistoryRecord record, {required String language});

  /// Asks for permission to notify, where Android asks (13 and later).
  Future<bool> askPermission();

  /// Whether the app is on screen. A check someone is watching is shown, not
  /// announced.
  bool get appInForeground;

  /// Taps on a notification, while the app runs or as the reason it was opened.
  Stream<ReadyTap> get taps;
}

/// For tests, and anywhere notifications are not wanted: does nothing.
class SilentNotifier implements ReadyNotifier {
  @override
  Future<void> keepAlive({required String language}) async {}

  @override
  Future<void> release() async {}

  @override
  Future<void> ready(HistoryRecord record, {required String language}) async {}

  @override
  Future<bool> askPermission() async => true;

  @override
  bool get appInForeground => true;

  @override
  Stream<ReadyTap> get taps => const Stream.empty();
}

class LocalReadyNotifier with WidgetsBindingObserver implements ReadyNotifier {
  LocalReadyNotifier._();

  static const _channelId = 'check_ready';
  static const _workingChannelId = 'check_running';
  static const _keepAliveId = 7001;
  static const _openAction = 'open';
  static const _shareAction = 'share';

  final _plugin = FlutterLocalNotificationsPlugin();
  final _taps = StreamController<ReadyTap>.broadcast();
  AppLifecycleState? _lifecycle = AppLifecycleState.resumed;
  bool _alive = false;
  ReadyTap? _launch;

  /// Set up once, at start. A notification that opened the app is delivered on
  /// [taps] as soon as something listens.
  static Future<LocalReadyNotifier> start() async {
    final notifier = LocalReadyNotifier._();
    WidgetsBinding.instance.addObserver(notifier);
    try {
      await notifier._plugin.initialize(
        settings: const InitializationSettings(
          android: AndroidInitializationSettings('@mipmap/ic_launcher'),
        ),
        onDidReceiveNotificationResponse: (response) {
          final tap = _tapOf(response);
          if (tap != null) notifier._taps.add(tap);
        },
      );
      final launch = await notifier._plugin.getNotificationAppLaunchDetails();
      if (launch?.didNotificationLaunchApp ?? false) {
        final response = launch!.notificationResponse;
        notifier._launch = response == null ? null : _tapOf(response);
      }
    } on Object {
      // A phone that will not set up notifications still checks; it is not told.
    }
    return notifier;
  }

  static ReadyTap? _tapOf(NotificationResponse response) {
    final id = response.payload;
    if (id == null || id.isEmpty) return null;
    return ReadyTap(id, share: response.actionId == _shareAction);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) => _lifecycle = state;

  @override
  bool get appInForeground => _lifecycle == AppLifecycleState.resumed;

  @override
  Stream<ReadyTap> get taps async* {
    final launch = _launch;
    _launch = null;
    if (launch != null) yield launch;
    yield* _taps.stream;
  }

  AndroidFlutterLocalNotificationsPlugin? get _android =>
      _plugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();

  @override
  Future<bool> askPermission() async {
    try {
      return await _android?.requestNotificationsPermission() ?? false;
    } on Object {
      return false;
    }
  }

  @override
  Future<void> keepAlive({required String language}) async {
    if (_alive) return;
    final l10n = lookupAppLocalizations(Locale(language));
    try {
      await _android?.startForegroundService(
        id: _keepAliveId,
        title: l10n.notifyWorkingTitle,
        body: l10n.notifyWorkingBody,
        notificationDetails: AndroidNotificationDetails(
          _workingChannelId,
          l10n.notifyWorkingChannel,
          importance: Importance.low,
          priority: Priority.low,
          ongoing: true,
          showWhen: false,
          silent: true,
        ),
        foregroundServiceTypes: {AndroidServiceForegroundType.foregroundServiceTypeDataSync},
      );
      _alive = true;
    } on Object {
      // Without the service Android may stop a long check in the background; the
      // check still runs for as long as the app does.
    }
  }

  @override
  Future<void> release() async {
    if (!_alive) return;
    _alive = false;
    try {
      await _android?.stopForegroundService();
    } on Object {
      // Already stopped.
    }
  }

  @override
  Future<void> ready(HistoryRecord record, {required String language}) async {
    final l10n = lookupAppLocalizations(Locale(language));
    final verdict = record.verdict.factVerdict;
    final word = ActionStyle.word(verdict, l10n);
    final colour = ActionStyle.colours(verdict, FactifyTokens.light).$1;
    final correct = verdict == FactVerdict.falseClaim || verdict == FactVerdict.misleading;
    try {
      await _plugin.show(
        id: record.id.hashCode & 0x7fffffff,
        title: l10n.notifyReadyTitle,
        body: '$word · ${record.summary}',
        payload: record.id,
        notificationDetails: NotificationDetails(
          android: AndroidNotificationDetails(
            _channelId,
            l10n.notifyReadyChannel,
            importance: Importance.high,
            priority: Priority.high,
            color: colour,
            subText: word,
            styleInformation: BigTextStyleInformation('$word · ${record.summary}'),
            actions: [
              AndroidNotificationAction(
                _openAction,
                l10n.notifyOpenResult,
                showsUserInterface: true,
              ),
              if (correct)
                AndroidNotificationAction(
                  _shareAction,
                  verdict == FactVerdict.misleading ? l10n.shareContext : l10n.shareCorrection,
                  showsUserInterface: true,
                ),
            ],
          ),
        ),
      );
    } on Object {
      // Not announced; it is in History all the same.
    }
  }
}
