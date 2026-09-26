/// Welcome, and sign up or sign in.
///
/// Shown after the splash to anyone not signed in. An account is compulsory: there
/// is no way past this screen without creating one or signing in, with an email and
/// a password or with Google - and the server refuses a check from anyone who has
/// not, whatever the app does.
///
/// Also opened from the profile screen when a guest decides to sign in, and then
/// returns there instead of opening the app afresh.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../app_services.dart';
import '../l10n/app_localizations.dart';
import '../theme/colors.dart';
import '../widgets/brand.dart';
import '../widgets/language_menu.dart';
import 'account_screen.dart';
import 'main_shell.dart';

class WelcomeScreen extends StatefulWidget {
  const WelcomeScreen({required this.services, this.fromProfile = false, super.key});

  final AppServices services;

  /// Opened from the profile: close on sign-in rather than opening the app.
  final bool fromProfile;

  @override
  State<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends State<WelcomeScreen> {
  bool _left = false;
  bool _creating = true;

  @override
  void initState() {
    super.initState();
    widget.services.auth.addListener(_onAuth);
  }

  @override
  void dispose() {
    widget.services.auth.removeListener(_onAuth);
    super.dispose();
  }

  void _onAuth() {
    if (!mounted || _left || !widget.services.auth.signedIn) return;
    _left = true;
    if (widget.fromProfile) {
      Navigator.of(context).pop();
    } else {
      _openApp();
    }
  }

  void _openApp() {
    unawaited(
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute<void>(builder: (_) => MainShell(services: widget.services)),
        (_) => false,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final auth = widget.services.auth;

    return Scaffold(
      appBar: widget.fromProfile ? AppBar() : null,
      body: SafeArea(
        child: ListenableBuilder(
          listenable: auth,
          builder: (context, _) => ListView(
            padding: const EdgeInsets.fromLTRB(24, 16, 24, 32),
            children: [
              Row(
                children: [
                  const FactifyWordmark(size: 34),
                  const Spacer(),
                  LanguageMenu(preference: widget.services.language),
                ],
              ),
              const SizedBox(height: 32),
              Text(
                l10n.welcomeTitle,
                style: theme.textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.6,
                  height: 1.15,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                l10n.welcomeBody,
                style: theme.textTheme.bodyLarge?.copyWith(
                  color: FactifyColors.inkSoft,
                  height: 1.45,
                ),
              ),
              const SizedBox(height: 22),
              _Point(icon: Icons.verified_rounded, text: l10n.welcomePointSources),
              _Point(icon: Icons.layers_rounded, text: l10n.welcomePointInputs),
              _Point(icon: Icons.translate_rounded, text: l10n.welcomePointLanguages),
              const SizedBox(height: 28),
              Card(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(18, 20, 18, 18),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        _creating ? l10n.welcomeSignInTitle : l10n.welcomeBackTitle,
                        style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        _creating ? l10n.welcomeSignInBody : l10n.welcomeBackBody,
                        style: theme.textTheme.bodyMedium?.copyWith(color: FactifyColors.inkMuted),
                      ),
                      const SizedBox(height: 18),
                      SignInPanel(
                        auth: auth,
                        showHeader: false,
                        padded: false,
                        onModeChanged: (creating) => setState(() => _creating = creating),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Point extends StatelessWidget {
  const _Point({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: Row(
      children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: FactifyColors.emeraldTint,
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(icon, size: 20, color: FactifyColors.emeraldDark),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            text,
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(fontWeight: FontWeight.w600),
          ),
        ),
      ],
    ),
  );
}
