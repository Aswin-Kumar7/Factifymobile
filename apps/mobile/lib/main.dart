/// Facify for Android (M44).
///
/// The judged surface. Built against the frozen contract in app/api/schemas.py,
/// and it holds no provider credential of any kind — every key lives server-side,
/// because a key shipped in an APK is a key extracted from that APK.
library;

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'api/client.dart';
import 'screens/home_screen.dart';

void main() => runApp(const FacifyApp());

class FacifyApp extends StatefulWidget {
  const FacifyApp({super.key});

  @override
  State<FacifyApp> createState() => _FacifyAppState();
}

class _FacifyAppState extends State<FacifyApp> {
  final FacifyClient _client = FacifyClient();

  @override
  void dispose() {
    _client.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Facify',
      debugShowCheckedModeBanner: false,
      theme: _theme(Brightness.light),
      darkTheme: _theme(Brightness.dark),
      // Follows the system. A verification tool gets opened in a hurry, often
      // from a chat at night, and forcing a light surface at that moment is the
      // kind of small friction that loses the check.
      themeMode: ThemeMode.system,
      // English and Hindi. Hinglish is deliberately absent as an interface
      // language: it is a register rather than a locale, and the embedding model
      // cannot represent it (measured, see docs/ops-notes.md), so offering it
      // here would promise retrieval quality the backend cannot deliver.
      supportedLocales: const [Locale('en'), Locale('hi')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      home: HomeScreen(client: _client),
    );
  }
}

/// One theme built twice, so light and dark cannot drift apart.
///
/// The seed is deliberately restrained. Verdict severity is carried by the action
/// colours in `VerdictCard` — green through red — and a strongly tinted chrome
/// competes with exactly the signal that has to read at a glance.
ThemeData _theme(Brightness brightness) {
  final scheme = ColorScheme.fromSeed(
    seedColor: const Color(0xFF00695C),
    brightness: brightness,
  );

  return ThemeData(
    colorScheme: scheme,
    useMaterial3: true,
    // The page ground sits one step below the cards, so surfaces read as
    // surfaces without a single drop shadow anywhere.
    scaffoldBackgroundColor: scheme.surfaceContainerLow,
    appBarTheme: AppBarTheme(
      backgroundColor: scheme.surfaceContainerLow,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 1,
      centerTitle: false,
      titleTextStyle: TextStyle(
        color: scheme.onSurface,
        fontSize: 22,
        fontWeight: FontWeight.w600,
      ),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      margin: EdgeInsets.zero,
      color: scheme.surface,
      // An outline rather than a shadow: several cards stack on the result
      // screen, and stacked shadows turn into visual noise that reads as depth
      // where there is no hierarchy.
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: scheme.outlineVariant),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: scheme.surface,
      indicatorColor: scheme.primary.withValues(alpha: 0.12),
      height: 68,
      labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: scheme.outlineVariant),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: scheme.primary, width: 2),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        side: BorderSide(color: scheme.outlineVariant),
      ),
    ),
    listTileTheme: const ListTileThemeData(
      contentPadding: EdgeInsets.symmetric(horizontal: 14, vertical: 4),
    ),
    dividerTheme: DividerThemeData(color: scheme.outlineVariant, thickness: 1),
    chipTheme: ChipThemeData(
      side: BorderSide(color: scheme.outlineVariant),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
    ),
  );
}
