/// Wording and colour for each verdict action.
///
/// Shared by the result card and the correction card, so the verdict a person
/// reads in the app and the one their group receives can never be worded
/// differently.
///
/// Every headline is a statement about *evidence*, never about truth — in every
/// language. The ARB descriptions carry that rule to whoever translates them, and
/// test/widget_test.dart checks the Hindi cards for the words that would break it.
library;

import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/verdict.dart';

class ActionStyle {
  const ActionStyle._({
    required this.headline,
    required this.subhead,
    required this.icon,
    required this.tone,
    required this.container,
    required this.onContainer,
  });

  final String headline;
  final String subhead;
  final IconData icon;
  final Color tone;
  final Color container;
  final Color onContainer;

  /// Soft container + legible foreground for one semantic colour, per theme.
  ///
  /// Dark mode lightens the foreground instead of darkening it — the same seed
  /// colour, read against the opposite ground.
  static ActionStyle _tinted({
    required String headline,
    required String subhead,
    required IconData icon,
    required Color tone,
    required Brightness brightness,
  }) {
    final dark = brightness == Brightness.dark;
    return ActionStyle._(
      headline: headline,
      subhead: subhead,
      icon: icon,
      tone: tone,
      container: tone.withValues(alpha: dark ? 0.20 : 0.10),
      onContainer: Color.lerp(tone, dark ? Colors.white : Colors.black, dark ? 0.55 : 0.45)!,
    );
  }

  static ActionStyle of(VerdictAction action, Brightness brightness, AppLocalizations l10n) =>
      switch (action) {
        VerdictAction.safeToShare => _tinted(
          headline: l10n.headlineSafeToShare,
          subhead: l10n.subheadSafeToShare,
          icon: Icons.verified_outlined,
          tone: const Color(0xFF2E7D32),
          brightness: brightness,
        ),
        VerdictAction.shareWithContext => _tinted(
          headline: l10n.headlineShareWithContext,
          subhead: l10n.subheadShareWithContext,
          icon: Icons.info_outline,
          tone: const Color(0xFF0277BD),
          brightness: brightness,
        ),
        VerdictAction.shareWithCorrection => _tinted(
          headline: l10n.headlineShareWithCorrection,
          subhead: l10n.subheadShareWithCorrection,
          icon: Icons.error_outline,
          tone: const Color(0xFFEF6C00),
          brightness: brightness,
        ),
        VerdictAction.doNotShare => _tinted(
          headline: l10n.headlineDoNotShare,
          subhead: l10n.subheadDoNotShare,
          icon: Icons.gpp_bad_outlined,
          tone: const Color(0xFFC62828),
          brightness: brightness,
        ),
        VerdictAction.waitAndRecheck => _tinted(
          headline: l10n.headlineWaitAndRecheck,
          subhead: l10n.subheadWaitAndRecheck,
          icon: Icons.schedule,
          tone: const Color(0xFF5E35B1),
          brightness: brightness,
        ),
        // Deliberately neutral, not red. Abstaining is the designed answer for a
        // case with no citable evidence, and colouring it as danger would tell
        // people we found something when we found nothing.
        VerdictAction.sendToReview => _tinted(
          headline: l10n.headlineSendToReview,
          subhead: l10n.subheadSendToReview,
          icon: Icons.help_outline,
          tone: const Color(0xFF546E7A),
          brightness: brightness,
        ),
      };
}
