/// Factify for Android (M44).
///
/// The judged surface. Built against the frozen contract in app/api/schemas.py,
/// and it holds no provider credential of any kind — every key lives server-side,
/// because a key shipped in an APK is a key extracted from that APK.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import 'api/client.dart';
import 'l10n/app_localizations.dart';
import 'l10n/language_preference.dart';
import 'screens/home_screen.dart';
import 'auth/auth_links.dart';
import 'auth/auth_service.dart';
import 'theme/colors.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Read before the first frame, so a reader who chose Hindi never sees a frame
  // of English first.
  final language = await LanguagePreference.load();
  runApp(FactifyApp(language: language));
}

class FactifyApp extends StatefulWidget {
  const FactifyApp({super.key, required this.language, this.client, this.auth});

  final LanguagePreference language;

  /// Supplied by tests. The app otherwise builds, and closes, its own.
  final FactifyClient? client;

  /// Supplied by tests. The app otherwise builds its own, and a test that supplies
  /// only a client gets one that never touches the phone's storage.
  final AuthService? auth;

  @override
  State<FactifyApp> createState() => _FactifyAppState();
}

class _FactifyAppState extends State<FactifyApp> {
  late final FactifyClient _client = widget.client ?? FactifyClient();
  late final AuthService _auth =
      widget.auth ??
      AuthService(
        client: _client,
        links: widget.client == null ? AuthLinks() : null,
        persist: widget.client == null,
      );

  @override
  void initState() {
    super.initState();
    // Checks carry the signed-in person's token, so the server can record credits.
    _client.tokenProvider = _auth.accessToken;
    if (widget.auth == null) unawaited(_auth.start());
  }

  @override
  void dispose() {
    if (widget.auth == null) _auth.dispose();
    if (widget.client == null) _client.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<Locale?>(
      valueListenable: widget.language,
      builder: (context, chosen, _) => MaterialApp(
        title: 'Factify',
        debugShowCheckedModeBanner: false,
        // White by design. The emerald-on-white identity is the product's look, and
        // a dark variant is a later, deliberate piece of work rather than an
        // automatic inversion of this one.
        theme: _theme(),
        themeMode: ThemeMode.light,
        // English and Hindi. Hinglish is deliberately absent as an interface
        // language: it is a register rather than a locale, and the embedding model
        // cannot represent it (measured, see docs/ops-notes.md), so offering it
        // here would promise retrieval quality the backend cannot deliver.
        //
        // The list comes from the ARB files in lib/l10n: a language is added
        // there, with its strings, rather than here.
        locale: chosen,
        supportedLocales: AppLocalizations.supportedLocales,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        localeListResolutionCallback: _resolveLocale,
        home: HomeScreen(client: _client, language: widget.language, auth: _auth),
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

/// White, with emerald for everything that acts.
///
/// Kept deliberately quiet: the one loud thing on a result screen should be the
/// verdict badge — green, red, amber or grey — and a strongly tinted chrome would
/// compete with exactly the signal that has to read at a glance. Emerald marks what
/// can be tapped; slate carries the text; the page is white.
ThemeData _theme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: FactifyColors.emerald,
    brightness: Brightness.light,
  ).copyWith(
    primary: FactifyColors.emerald,
    onPrimary: Colors.white,
    primaryContainer: FactifyColors.emeraldSoft,
    onPrimaryContainer: FactifyColors.emeraldDeep,
    secondary: FactifyColors.emeraldDark,
    surface: Colors.white,
    onSurface: FactifyColors.ink,
    onSurfaceVariant: FactifyColors.inkMuted,
    outline: FactifyColors.line,
    outlineVariant: FactifyColors.line,
    surfaceContainerLowest: Colors.white,
    surfaceContainerLow: FactifyColors.ground,
    surfaceContainer: FactifyColors.ground,
    surfaceContainerHigh: const Color(0xFFF1F5F9),
    surfaceContainerHighest: const Color(0xFFF1F5F9),
  );

  final base = ThemeData(colorScheme: scheme, useMaterial3: true);
  final text = base.textTheme.apply(
    bodyColor: FactifyColors.ink,
    displayColor: FactifyColors.ink,
  );

  return base.copyWith(
    scaffoldBackgroundColor: Colors.white,
    textTheme: text.copyWith(
      headlineSmall: text.headlineSmall?.copyWith(fontWeight: FontWeight.w800, letterSpacing: -0.4),
      titleLarge: text.titleLarge?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -0.2),
      titleMedium: text.titleMedium?.copyWith(fontWeight: FontWeight.w600),
      bodyMedium: text.bodyMedium?.copyWith(height: 1.45, color: FactifyColors.ink),
      bodySmall: text.bodySmall?.copyWith(height: 1.4, color: FactifyColors.inkSoft),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: Colors.white,
      foregroundColor: FactifyColors.ink,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0.5,
      centerTitle: false,
      titleTextStyle: TextStyle(
        color: FactifyColors.ink,
        fontSize: 20,
        fontWeight: FontWeight.w800,
        letterSpacing: -0.3,
      ),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      margin: EdgeInsets.zero,
      color: Colors.white,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: const BorderSide(color: FactifyColors.line),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: Colors.white,
      surfaceTintColor: Colors.transparent,
      indicatorColor: FactifyColors.emeraldSoft,
      height: 66,
      labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      iconTheme: WidgetStateProperty.resolveWith(
        (states) => IconThemeData(
          color: states.contains(WidgetState.selected)
              ? FactifyColors.emeraldDeep
              : FactifyColors.inkMuted,
        ),
      ),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: FactifyColors.ink,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: FactifyColors.ground,
      hintStyle: const TextStyle(color: FactifyColors.inkMuted),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: FactifyColors.line),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: FactifyColors.line),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: FactifyColors.emerald, width: 1.6),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: FactifyColors.emerald,
        foregroundColor: Colors.white,
        disabledBackgroundColor: FactifyColors.line,
        minimumSize: const Size.fromHeight(52),
        textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: FactifyColors.emeraldDeep,
        minimumSize: const Size.fromHeight(46),
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        side: const BorderSide(color: FactifyColors.line),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: FactifyColors.emeraldDark,
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
    ),
    dividerTheme: const DividerThemeData(color: FactifyColors.line, thickness: 1, space: 1),
    chipTheme: ChipThemeData(
      side: const BorderSide(color: FactifyColors.line),
      backgroundColor: Colors.white,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: FactifyColors.emerald,
      linearTrackColor: FactifyColors.emeraldSoft,
    ),
  );
}
