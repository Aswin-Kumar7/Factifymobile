/// The app once past the welcome: Check, History and Profile, one tab each.
///
/// Shares from other apps arrive here, whichever tab is open, and go to Check, which
/// starts checking them straight away: the thing this app exists to check arrives in
/// a forward, and a share that only fills a box is a share half-finished.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../api/share_intake.dart';
import '../app_services.dart';
import '../l10n/app_localizations.dart';
import '../widgets/ui/ui.dart';
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
    switch (content.kind) {
      case 'record':
        unawaited(_openRecord(content.value));
      case 'widget':
        _widgetButton(content.value);
      default:
        setState(() => _tab = 0);
        WidgetsBinding.instance.addPostFrameCallback(
          (_) => _home.currentState?.receiveShare(content),
        );
    }
  }

  /// "Open full result" on the quick verdict: the check it kept in History, which
  /// this copy of the app reads again first, since the quick verdict wrote it.
  Future<void> _openRecord(String id) async {
    final history = widget.services.history;
    await history.load();
    final record = history.records.where((r) => r.id == id).firstOrNull;
    if (!mounted) return;
    setState(() => _tab = 1);
    if (record != null) openHistoryRecord(context, widget.services, record);
  }

  /// A home-screen widget button: Check with the copied text, the camera, or History.
  void _widgetButton(String button) {
    if (button == 'history') {
      setState(() => _tab = 1);
      return;
    }
    setState(() => _tab = 0);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final home = _home.currentState;
      if (home == null) return;
      unawaited(button == 'camera' ? home.takePhoto() : home.pasteCopiedText());
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      body: IndexedStack(
        index: _tab,
        children: [
          HomeScreen(
            key: _home,
            services: widget.services,
            onSeeAll: () => setState(() => _tab = 1),
            onOpenProfile: () => setState(() => _tab = 2),
          ),
          HistoryScreen(services: widget.services, onStartChecking: () => setState(() => _tab = 0)),
          ProfileScreen(services: widget.services, onOpenHistory: () => setState(() => _tab = 1)),
        ],
      ),
      bottomNavigationBar: FxBottomNav(
        selected: _tab,
        onSelected: (index) => setState(() => _tab = index),
        items: [
          FxNavItem(label: l10n.tabCheck, icon: FxIcons.check, selectedIcon: FxIcons.checkFill),
          FxNavItem(
            label: l10n.tabHistory,
            icon: FxIcons.history,
            selectedIcon: FxIcons.historyFill,
          ),
          FxNavItem(
            label: l10n.tabProfile,
            icon: FxIcons.profile,
            selectedIcon: FxIcons.profileFill,
          ),
        ],
      ),
    );
  }
}
