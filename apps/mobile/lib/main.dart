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
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF00695C)),
        useMaterial3: true,
      ),
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
