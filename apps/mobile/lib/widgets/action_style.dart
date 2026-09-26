/// Wording, colour and icon for each verdict.
///
/// Shared by the result card, the sources screen, the history list and the
/// correction card, so the verdict a person reads in the app and the one their group
/// receives can never be worded or coloured differently.
///
/// Four verdicts, four colours, and the fourth is deliberately not a warning:
/// "Unconfirmed" is grey, because it means the sources did not settle the claim,
/// not that something bad was found. Painting it red would teach people that "we
/// could not confirm this" and "this is false" are the same answer.
library;

import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/verdict.dart';

class ActionStyle {
  const ActionStyle._({
    required this.verdict,
    required this.headline,
    required this.subhead,
    required this.icon,
    required this.tone,
    required this.container,
    required this.onContainer,
  });

  final FactVerdict verdict;
  final String headline;
  final String subhead;
  final IconData icon;
  final Color tone;
  final Color container;
  final Color onContainer;

  static const _true = Color(0xFF059669);
  static const _false = Color(0xFFDC2626);
  static const _misleading = Color(0xFFD97706);
  static const _unconfirmed = Color(0xFF64748B);

  static ActionStyle _tinted({
    required FactVerdict verdict,
    required String headline,
    required String subhead,
    required IconData icon,
    required Color tone,
  }) => ActionStyle._(
    verdict: verdict,
    headline: headline,
    subhead: subhead,
    icon: icon,
    tone: tone,
    container: tone.withValues(alpha: 0.08),
    onContainer: Color.lerp(tone, Colors.black, 0.35)!,
  );

  /// The style for a whole result: [of] its action, or a neutral "nothing to
  /// fact-check" when nothing in it could be checked ([Verdict.nothingToCheck]).
  static ActionStyle forVerdict(Verdict verdict, Brightness brightness, AppLocalizations l10n) =>
      verdict.nothingToCheck
      ? _tinted(
          verdict: FactVerdict.unconfirmed,
          headline: l10n.headlineNothingToCheck,
          subhead: l10n.subheadNothingToCheck,
          icon: Icons.info_rounded,
          tone: _unconfirmed,
        )
      : of(verdict.action, brightness, l10n);

  /// The style for a result. [brightness] is accepted for the correction card,
  /// which always renders on white, and otherwise unused: the app is light only.
  static ActionStyle of(VerdictAction action, Brightness brightness, AppLocalizations l10n) =>
      switch (action) {
        VerdictAction.safeToShare => _tinted(
          verdict: FactVerdict.trueClaim,
          headline: l10n.headlineSafeToShare,
          subhead: l10n.subheadSafeToShare,
          icon: Icons.check_circle_rounded,
          tone: _true,
        ),
        VerdictAction.doNotShare => _tinted(
          verdict: FactVerdict.falseClaim,
          headline: l10n.headlineDoNotShare,
          subhead: l10n.subheadDoNotShare,
          icon: Icons.cancel_rounded,
          tone: _false,
        ),
        VerdictAction.shareWithContext => _tinted(
          verdict: FactVerdict.misleading,
          headline: l10n.headlineShareWithContext,
          subhead: l10n.subheadShareWithContext,
          icon: Icons.error_rounded,
          tone: _misleading,
        ),
        VerdictAction.shareWithCorrection => _tinted(
          verdict: FactVerdict.misleading,
          headline: l10n.headlineShareWithCorrection,
          subhead: l10n.subheadShareWithCorrection,
          icon: Icons.error_rounded,
          tone: _misleading,
        ),
        VerdictAction.waitAndRecheck => _tinted(
          verdict: FactVerdict.unconfirmed,
          headline: l10n.headlineWaitAndRecheck,
          subhead: l10n.subheadWaitAndRecheck,
          icon: Icons.schedule_rounded,
          tone: _unconfirmed,
        ),
        VerdictAction.sendToReview => _tinted(
          verdict: FactVerdict.unconfirmed,
          headline: l10n.headlineSendToReview,
          subhead: l10n.subheadSendToReview,
          icon: Icons.help_rounded,
          tone: _unconfirmed,
        ),
      };

  /// The colour for one claim's status, for the smaller per-claim badges.
  static Color forStatus(ClaimStatus status) => switch (status) {
    ClaimStatus.supported => _true,
    ClaimStatus.contradicted => _false,
    ClaimStatus.misleadingContext => _misleading,
    ClaimStatus.unverified => _unconfirmed,
  };
}
