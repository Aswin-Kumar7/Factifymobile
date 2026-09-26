/// The app once past the welcome: Home, History and Profile, one tab each.
///
/// Shares from other apps arrive here, whichever tab is open, and go to Home, which
/// starts checking them straight away: the thing this app exists to check arrives in
/// a forward, and a share that only fills a box is a share half-finished.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../api/share_intake.dart';
import '../app_services.dart';
import '../l10n/app_localizations.dart';
import 'history_screen.dart';
import 'home_screen.dart';
import 'profile_screen.dart';
import 'welcome_screen.dart';

class MainShell extends StatefulWidget {
  const MainShell({required this.services, this.intake, super.key});

  final AppServices services;

  /// Shares from other apps. Built here unless a test supplies one.
  final ShareIntake? intake;

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  final GlobalKey<HomeScreenState> _home = GlobalKey<HomeScreenState>();
  late final ShareIntake _intake = widget.intake ?? ShareIntake();
  StreamSubscription<SharedContent>? _shares;
  int _tab = 0;
  late bool _signedIn = widget.services.auth.signedIn;

  @override
  void initState() {
    super.initState();
    widget.services.auth.addListener(_onAuth);
    // Two channels, and both are needed: the stream brings shares while the app is
    // open, and `initial` the share that launched it, which arrives before Dart is
    // listening. Wiring only the stream loses the first share after a cold start.
    _shares = _intake.stream.listen(_receive, onError: (_) {});
    unawaited(
      _intake.initial().then((content) {
        if (content != null) _receive(content);
      }),
    );
  }

  @override
  void dispose() {
    widget.services.auth.removeListener(_onAuth);
    _shares?.cancel();
    super.dispose();
  }

  /// Signing out goes back to the welcome screen. Only signing out: a guest, or
  /// sign-in still loading, stays where they are.
  void _onAuth() {
    final auth = widget.services.auth;
    final signedOut = _signedIn && !auth.signedIn;
    _signedIn = auth.signedIn;
    if (!mounted || !signedOut) return;
    unawaited(
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute<void>(builder: (_) => WelcomeScreen(services: widget.services)),
        (_) => false,
      ),
    );
  }

  void _receive(SharedContent content) {
    if (!mounted) return;
    // A share while a result or a check is open replaces it.
    Navigator.of(context).popUntil((route) => route.isFirst);
    setState(() => _tab = 0);
    WidgetsBinding.instance.addPostFrameCallback((_) => _home.currentState?.receiveShare(content));
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      body: IndexedStack(
        index: _tab,
        children: [
          HomeScreen(key: _home, services: widget.services),
          HistoryScreen(services: widget.services, onStartChecking: () => setState(() => _tab = 0)),
          ProfileScreen(services: widget.services),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (index) => setState(() => _tab = index),
        destinations: [
          NavigationDestination(
            icon: const Icon(Icons.home_outlined),
            selectedIcon: const Icon(Icons.home_rounded),
            label: l10n.tabHome,
          ),
          NavigationDestination(
            icon: const Icon(Icons.history_outlined),
            selectedIcon: const Icon(Icons.history_rounded),
            label: l10n.tabHistory,
          ),
          NavigationDestination(
            icon: const Icon(Icons.person_outline_rounded),
            selectedIcon: const Icon(Icons.person_rounded),
            label: l10n.tabProfile,
          ),
        ],
      ),
    );
  }
}
