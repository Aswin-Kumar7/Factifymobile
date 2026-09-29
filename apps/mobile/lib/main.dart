/// Factify for Android (M44).
///
/// The judged surface. Built against the frozen contract in app/api/schemas.py,
/// and it holds no provider credential of any kind — every key lives server-side,
/// because a key shipped in an APK is a key extracted from that APK.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:shared_preferences/shared_preferences.dart';

import 'api/client.dart';
import 'app_services.dart';
import 'auth/auth_links.dart';
import 'auth/auth_service.dart';
import 'debug/error_log.dart';
import 'history/history_store.dart';
import 'l10n/app_localizations.dart';
import 'l10n/language_preference.dart';
import 'notify/notify_preference.dart';
import 'notify/ready_notifier.dart';
import 'quick/quick_preference.dart';
import 'quick/quick_verdict.dart';
import 'screens/history_screen.dart';
import 'screens/main_shell.dart';
import 'screens/splash_screen.dart';
import 'theme/theme.dart';
import 'theme/theme_mode_preference.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Debug builds only: a red error screen can be read in full afterwards.
  await keepFrameworkErrors();
  // Read before the first frame, so a reader who chose Hindi never sees a frame
  // of English first.
  final language = await LanguagePreference.load();
  final themeMode = await ThemeModePreference.load();
  final notifyByDefault = await NotifyPreference.load();
  final notifier = await LocalReadyNotifier.start();
  final quickVerdict = await QuickVerdictPreference.load();
  runApp(
    FactifyApp(
      language: language,
      themeMode: themeMode,
      notifier: notifier,
      notifyByDefault: notifyByDefault,
      quickVerdict: quickVerdict,
    ),
  );
}

/// The quick verdict over the chat (android QuickVerdictActivity): text shared to
/// Factify, answered in a sheet over the app it came from. Its own entry point, so
/// that window starts one check and one sheet rather than the whole app.
@pragma('vm:entry-point')
Future<void> quickVerdictMain() => runQuickVerdict();

class FactifyApp extends StatefulWidget {
  const FactifyApp({
    super.key,
    required this.language,
    this.themeMode,
    this.client,
    this.auth,
    this.history,
    this.notifier,
    this.notifyByDefault,
    this.quickVerdict,
    bool? showIntro,
  }) : showIntro = showIntro ?? client == null;

  final LanguagePreference language;

  /// Light, dark or the phone's setting. Tests that leave it out get light.
  final ThemeModePreference? themeMode;

  /// Supplied by tests. The app otherwise builds, and closes, its own.
  final FactifyClient? client;

  /// Supplied by tests. The app otherwise builds its own, and a test that supplies
  /// only a client gets one that never touches the phone's storage.
  final AuthService? auth;

  /// Supplied by tests; kept on the phone otherwise.
  final HistoryStore? history;

  /// "Your check is ready". Tests leave it out and are notified of nothing.
  final ReadyNotifier? notifier;
  final NotifyPreference? notifyByDefault;

  /// Whether shared text is answered over the chat (Profile).
  final QuickVerdictPreference? quickVerdict;

  /// The splash and the welcome. On for the app; a test that supplies a client
  /// starts in the app itself unless it asks for them.
  final bool showIntro;

  @override
  State<FactifyApp> createState() => _FactifyAppState();
}

class _FactifyAppState extends State<FactifyApp> with WidgetsBindingObserver {
  late final FactifyClient _client = widget.client ?? FactifyClient();
  late final AuthService _auth =
      widget.auth ??
      AuthService(
        client: _client,
        links: widget.client == null ? AuthLinks() : null,
        persist: widget.client == null,
      );
  late final HistoryStore _history =
      widget.history ??
      HistoryStore(store: widget.client == null ? SharedPreferencesAsync() : null);
  late final AppServices _services = AppServices(
    client: _client,
    auth: _auth,
    language: widget.language,
    history: _history,
    themeMode: widget.themeMode ?? ThemeModePreference.inMemory(ThemeMode.light),
    notifier: widget.notifier,
    notifyByDefault: widget.notifyByDefault,
    quickVerdict: widget.quickVerdict,
  );

  final _navigator = GlobalKey<NavigatorState>();
  StreamSubscription<ReadyTap>? _taps;

  @override
  void initState() {
    super.initState();
    // Checks carry the signed-in person's token, so the server can record credits.
    _client.tokenProvider = _auth.accessToken;
    if (widget.auth == null) unawaited(_auth.start());
    // Without the splash (tests), nothing else would load the saved history.
    if (!widget.showIntro) unawaited(_history.load());
    _taps = _services.notifier.taps.listen((tap) => unawaited(_open(tap)));
    WidgetsBinding.instance.addObserver(this);
  }

  /// Back to the front: History is read again, since a check answered over a chat
  /// (the quick verdict, which runs apart from the app) may have been kept since.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _history.loaded) unawaited(_history.load());
  }

  /// A tapped "your check is ready": the result, from History, where the finished
  /// check was kept. Waits for History to load when the tap is what opened the app.
  Future<void> _open(ReadyTap tap) async {
    await _history.load();
    final record = _history.records.where((r) => r.id == tap.recordId).firstOrNull;
    final context = _navigator.currentContext;
    if (record == null || context == null || !context.mounted) return;
    openHistoryRecord(context, _services, record, openShare: tap.share);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_taps?.cancel());
    if (widget.auth == null) _auth.dispose();
    if (widget.client == null) _client.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([widget.language, _services.themeMode]),
      builder: (context, _) => MaterialApp(
        title: 'Factify',
        navigatorKey: _navigator,
        debugShowCheckedModeBanner: false,
        // Both built from the v5 tokens (lib/theme/tokens.dart): dark mode is the
        // same layout with the other colour set, never an automatic inversion.
        theme: _light,
        darkTheme: _dark,
        themeMode: _services.themeMode.value,
        // English and Hindi. Hinglish is deliberately absent as an interface
        // language: it is a register rather than a locale, and the embedding model
        // cannot represent it (measured, see docs/ops-notes.md), so offering it
        // here would promise retrieval quality the backend cannot deliver.
        //
        // The list comes from the ARB files in lib/l10n: a language is added
        // there, with its strings, rather than here.
        locale: widget.language.value,
        supportedLocales: AppLocalizations.supportedLocales,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        localeListResolutionCallback: _resolveLocale,
        // Dark status-bar icons on the light theme, light ones on the dark: a screen
        // with its own colours (the splash) sets its own over this.
        builder: (context, child) => AnnotatedRegion<SystemUiOverlayStyle>(
          value:
              (Theme.of(context).brightness == Brightness.dark
                      ? SystemUiOverlayStyle.light
                      : SystemUiOverlayStyle.dark)
                  .copyWith(statusBarColor: Colors.transparent),
          child: child ?? const SizedBox.shrink(),
        ),
        home: widget.showIntro ? SplashScreen(services: _services) : MainShell(services: _services),
      ),
    );
  }
}

/// The phone's language when Factify has strings for it, English otherwise.
///
/// Written out rather than left to the default, which falls back to whichever
/// supported locale happens to be listed first.
Locale _resolveLocale(List<Locale>? preferred, Iterable<Locale> supported) {
  for (final locale in preferred ?? const <Locale>[]) {
    for (final candidate in supported) {
      if (candidate.languageCode == locale.languageCode) return candidate;
    }
  }
  return const Locale('en');
}

final ThemeData _light = buildFactifyTheme(Brightness.light);
final ThemeData _dark = buildFactifyTheme(Brightness.dark);
