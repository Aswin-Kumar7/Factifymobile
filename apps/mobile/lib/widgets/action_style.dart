/// Wording, colour and icon for each verdict.
///
/// Shared by the result, the sources screen, the history list and the correction
/// card, so the verdict a person reads in the app and the one their group receives
/// can never be worded or coloured differently.
///
/// Four verdicts, four colours, read from the theme's tokens (tC/tS, fC/fS, mC/mS,
/// uC/uS in lib/theme/tokens.dart), and the fourth is deliberately not a warning:
/// "Unconfirmed" is grey, because it means the sources did not settle the claim, not
/// that something bad was found. Painting it red would teach people that "we could
/// not confirm this" and "this is false" are the same answer.
library;

import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/verdict.dart';
import '../theme/icons.dart';
import '../theme/tokens.dart';

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

  /// The verdict's strong colour: the word, the ring, the icon.
  final Color tone;

  /// Its soft tint: the band behind the verdict, a pill's background.
  final Color container;

  /// Text set on [container].
  final Color onContainer;

  static FactifyTokens _tokens(Brightness brightness) =>
      brightness == Brightness.dark ? FactifyTokens.dark : FactifyTokens.light;

  /// The strong colour and the tint for a verdict.
  static (Color strong, Color soft) colours(FactVerdict verdict, FactifyTokens k) =>
      switch (verdict) {
        FactVerdict.trueClaim => (k.tC, k.tS),
        FactVerdict.falseClaim => (k.fC, k.fS),
        FactVerdict.misleading => (k.mC, k.mS),
        FactVerdict.unconfirmed => (k.uC, k.uS),
      };

  static ActionStyle _make({
    required FactVerdict verdict,
    required String headline,
    required String subhead,
    required IconData icon,
    required FactifyTokens tokens,
  }) {
    final (strong, soft) = colours(verdict, tokens);
    return ActionStyle._(
      verdict: verdict,
      headline: headline,
      subhead: subhead,
      icon: icon,
      tone: strong,
      container: soft,
      onContainer: strong,
    );
  }

  /// The style for a whole result: [of] its action, or a neutral "nothing to
  /// fact-check" when nothing in it could be checked ([Verdict.nothingToCheck]).
  static ActionStyle forVerdict(Verdict verdict, Brightness brightness, AppLocalizations l10n) =>
      verdict.nothingToCheck
      ? _make(
          verdict: FactVerdict.unconfirmed,
          headline: l10n.headlineNothingToCheck,
          subhead: l10n.subheadNothingToCheck,
          icon: FxIcons.info,
          tokens: _tokens(brightness),
        )
      : of(verdict.action, brightness, l10n);

  /// The style for a result. The correction card passes [Brightness.light]: the
  /// picture sent to a chat is always the light version, whatever the phone shows.
  static ActionStyle of(VerdictAction action, Brightness brightness, AppLocalizations l10n) {
    final k = _tokens(brightness);
    return switch (action) {
      VerdictAction.safeToShare => _make(
        verdict: FactVerdict.trueClaim,
        headline: l10n.headlineSafeToShare,
        subhead: l10n.subheadSafeToShare,
        icon: FxIcons.trueV,
        tokens: k,
      ),
      VerdictAction.doNotShare => _make(
        verdict: FactVerdict.falseClaim,
        headline: l10n.headlineDoNotShare,
        subhead: l10n.subheadDoNotShare,
        icon: FxIcons.falseV,
        tokens: k,
      ),
      VerdictAction.shareWithContext => _make(
        verdict: FactVerdict.misleading,
        headline: l10n.headlineShareWithContext,
        subhead: l10n.subheadShareWithContext,
        icon: FxIcons.misleadingV,
        tokens: k,
      ),
      VerdictAction.shareWithCorrection => _make(
        verdict: FactVerdict.misleading,
        headline: l10n.headlineShareWithCorrection,
        subhead: l10n.subheadShareWithCorrection,
        icon: FxIcons.misleadingV,
        tokens: k,
      ),
      VerdictAction.waitAndRecheck => _make(
        verdict: FactVerdict.unconfirmed,
        headline: l10n.headlineWaitAndRecheck,
        subhead: l10n.subheadWaitAndRecheck,
        icon: FxIcons.unconfirmedV,
        tokens: k,
      ),
      VerdictAction.sendToReview => _make(
        verdict: FactVerdict.unconfirmed,
        headline: l10n.headlineSendToReview,
        subhead: l10n.subheadSendToReview,
        icon: FxIcons.unconfirmedV,
        tokens: k,
      ),
    };
  }

  /// The one word for a verdict: True, False, Misleading, Unconfirmed.
  static String word(FactVerdict verdict, AppLocalizations l10n) => switch (verdict) {
    FactVerdict.trueClaim => l10n.headlineSafeToShare,
    FactVerdict.falseClaim => l10n.headlineDoNotShare,
    FactVerdict.misleading => l10n.headlineShareWithContext,
    FactVerdict.unconfirmed => l10n.headlineSendToReview,
  };

  /// The icon for a verdict.
  static IconData iconFor(FactVerdict verdict) => switch (verdict) {
    FactVerdict.trueClaim => FxIcons.trueV,
    FactVerdict.falseClaim => FxIcons.falseV,
    FactVerdict.misleading => FxIcons.misleadingV,
    FactVerdict.unconfirmed => FxIcons.unconfirmedV,
  };

  /// The colour for one claim's status, for the smaller per-claim marks.
  static Color forStatus(ClaimStatus status, [Brightness brightness = Brightness.light]) {
    final k = _tokens(brightness);
    return switch (status) {
      ClaimStatus.supported => k.tC,
      ClaimStatus.contradicted => k.fC,
      ClaimStatus.misleadingContext => k.mC,
      ClaimStatus.unverified => k.uC,
    };
  }

  /// The tint behind one claim's status.
  static Color tintForStatus(ClaimStatus status, [Brightness brightness = Brightness.light]) {
    final k = _tokens(brightness);
    return switch (status) {
      ClaimStatus.supported => k.tS,
      ClaimStatus.contradicted => k.fS,
      ClaimStatus.misleadingContext => k.mS,
      ClaimStatus.unverified => k.uS,
    };
  }

  /// The icon for one claim's status.
  static IconData iconForStatus(ClaimStatus status) => switch (status) {
    ClaimStatus.supported => FxIcons.trueV,
    ClaimStatus.contradicted => FxIcons.falseV,
    ClaimStatus.misleadingContext => FxIcons.misleadingV,
    ClaimStatus.unverified => FxIcons.unconfirmedV,
  };
}
