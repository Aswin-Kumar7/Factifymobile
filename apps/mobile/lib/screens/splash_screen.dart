/// The first screen: the mark, while the saved session and history load.
///
/// It stays only as long as there is something to wait for, plus a moment so the
/// mark is seen rather than flashed: the saved sign-in and the server's sign-in
/// settings decide whether the next screen is the welcome or the app itself.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../app_services.dart';
import '../l10n/app_localizations.dart';
import '../theme/typography.dart';
import '../widgets/brand.dart';
import 'survey_screen.dart';
import 'welcome_screen.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({required this.services, super.key});

  final AppServices services;

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> with SingleTickerProviderStateMixin {
  late final AnimationController _intro = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..forward();

  @override
  void initState() {
    super.initState();
    unawaited(_proceed());
  }

  Future<void> _proceed() async {
    final auth = widget.services.auth;
    final ready = Completer<void>();
    void check() {
      if (auth.started && !ready.isCompleted) ready.complete();
    }

    auth.addListener(check);
    check();
    try {
      await Future.wait([
        // Never stuck on the splash: past a few seconds the app opens regardless,
        // and sign-in simply shows as unavailable until the server answers.
        ready.future.timeout(const Duration(seconds: 6), onTimeout: () {}),
        widget.services.history.load(),
        Future<void>.delayed(const Duration(milliseconds: 1400)),
      ]);
    } finally {
      auth.removeListener(check);
    }
    // A new account that has not had the survey meets it first. The server says
    // whether it is due; without an answer in time the app simply opens.
    if (auth.welcomed) {
      await auth
          .refreshAccount()
          .timeout(const Duration(seconds: 4), onTimeout: () => null)
          .catchError((Object _) => null);
    }
    if (!mounted) return;
    unawaited(
      Navigator.of(context).pushReplacement(
        PageRouteBuilder<void>(
          transitionDuration: const Duration(milliseconds: 450),
          pageBuilder: (_, _, _) => auth.welcomed
              ? signedInHome(widget.services)
              : WelcomeScreen(services: widget.services),
          transitionsBuilder: (_, animation, _, child) =>
              FadeTransition(opacity: animation, child: child),
        ),
      ),
    );
  }

  @override
  void dispose() {
    _intro.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final scale = CurvedAnimation(parent: _intro, curve: Curves.easeOutBack);
    final fade = CurvedAnimation(
      parent: _intro,
      curve: const Interval(0.3, 1, curve: Curves.easeOut),
    );

    return AnnotatedRegion<SystemUiOverlayStyle>(
      // White status-bar icons on the emerald.
      value: SystemUiOverlayStyle.light,
      child: Scaffold(
        body: Container(
          width: double.infinity,
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [FactifyBrand.emerald, FactifyBrand.emeraldDeep],
            ),
          ),
          child: SafeArea(
            child: Column(
              children: [
                const Spacer(flex: 3),
                ScaleTransition(scale: scale, child: const FactifyMark(size: 96, onDark: true)),
                const SizedBox(height: 22),
                FadeTransition(
                  opacity: fade,
                  child: Column(
                    children: [
                      const Text(
                        'Factify',
                        // The wordmark is set in the serif, as on the seal's F.
                        style: TextStyle(
                          fontFamily: FxFonts.serif,
                          color: Colors.white,
                          fontSize: 38,
                          fontWeight: FontWeight.w600,
                          letterSpacing: -0.6,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        l10n.splashTagline,
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.85),
                          fontSize: 16,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ),
                const Spacer(flex: 3),
                FadeTransition(
                  opacity: fade,
                  child: SizedBox(
                    width: 28,
                    height: 28,
                    child: CircularProgressIndicator(
                      strokeWidth: 2.6,
                      color: Colors.white.withValues(alpha: 0.9),
                    ),
                  ),
                ),
                const SizedBox(height: 40),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
