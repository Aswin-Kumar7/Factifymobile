/// When a check does not finish (v5, 2.11): what happened, and one clear next step.
///
/// One layout for every case - an icon, an overline, a title, a sentence, a row
/// showing what was being checked, the next step and "Back to home" - so a failure
/// always reads the same way and never as a verdict. Nothing here is red: a check
/// that did not finish has found nothing false.
///
/// What was being checked stays in the Check box (Home keeps its input until an
/// answer is shown), and the row says so, so nobody has to find and paste it again.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../l10n/app_localizations.dart';
import '../l10n/phrases.dart';
import '../models/submission.dart';
import '../theme/icons.dart';
import '../theme/tokens.dart';
import '../theme/typography.dart';
import '../widgets/ui/fx_button.dart';

/// Why a check stopped, as far as the next step is concerned.
enum CheckProblem {
  /// A link the server could not read, or found nothing to check on.
  linkUnread,

  /// No route to the server, or the connection dropped.
  offline,

  /// The check ran past its time.
  slow,

  /// The service's daily limit.
  dailyLimit,

  /// This person has no credits left.
  outOfCredits,

  /// The sign-in session ended.
  signedOut,

  /// The file is larger than the server takes.
  tooLarge,

  /// The service is up but cannot check right now.
  paused,

  /// Anything else.
  other;

  static CheckProblem of(ApiFailure failure, {required bool link}) => switch (failure.kind) {
    FailureKind.invalidInput when link => CheckProblem.linkUnread,
    FailureKind.unreachable || FailureKind.interrupted => CheckProblem.offline,
    FailureKind.timeout => CheckProblem.slow,
    FailureKind.dailyLimit => CheckProblem.dailyLimit,
    FailureKind.outOfCredits => CheckProblem.outOfCredits,
    FailureKind.signedOut => CheckProblem.signedOut,
    FailureKind.tooLarge => CheckProblem.tooLarge,
    FailureKind.unavailable => CheckProblem.paused,
    _ => CheckProblem.other,
  };
}

/// Where the next step leads, when it leaves the Checking screen. Home acts on it.
enum CheckExit {
  /// Check, with an empty text box: paste the article's text instead of its link.
  pasteText,

  /// Check, with the file removed: choose a smaller one.
  chooseFile,

  /// The History tab.
  openHistory,

  /// The Profile tab, where the credits are.
  openProfile,
}

class ErrorView extends StatelessWidget {
  const ErrorView({
    required this.problem,
    required this.submission,
    required this.message,
    required this.onRetry,
    required this.onExit,
    required this.onClose,
    this.onSignIn,
    super.key,
  });

  final CheckProblem problem;
  final Submission submission;

  /// What went wrong, in the reader's language.
  final String message;

  /// Null when trying again would fail the same way.
  final VoidCallback? onRetry;
  final ValueChanged<CheckExit> onExit;
  final VoidCallback onClose;
  final VoidCallback? onSignIn;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final shape = _Shape.of(problem, l10n);
    final action = _action(l10n);
    final (rowIcon, row) = _what(submission);
    final note = problem == CheckProblem.linkUnread
        ? l10n.errLinkNote
        : submission.isMedia
        ? l10n.errKeptFile
        : l10n.errKept;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 2, 16, 0),
          child: Align(
            alignment: AlignmentDirectional.centerStart,
            child: FxCircleButton(icon: FxIcons.close, tooltip: l10n.errClose, onPressed: onClose),
          ),
        ),
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(28, 40, 28, 20),
            child: Column(
              children: [
                Container(
                  width: 84,
                  height: 84,
                  decoration: BoxDecoration(
                    color: k.sf,
                    borderRadius: BorderRadius.circular(28),
                    border: k.isDark ? Border.all(color: k.line) : null,
                    boxShadow: k.isDark ? null : k.shadow,
                  ),
                  child: Icon(shape.icon, size: 38, color: k.ink2),
                ),
                const SizedBox(height: 22),
                Text(
                  shape.overline.toUpperCase(),
                  textAlign: TextAlign.center,
                  style: FactifyText.mono(10.5, color: k.ink3),
                ),
                const SizedBox(height: 8),
                Semantics(
                  header: true,
                  child: Text(
                    shape.title,
                    textAlign: TextAlign.center,
                    style: FactifyText.serif(
                      30,
                      color: k.ink,
                    ).copyWith(height: 1.1, letterSpacing: -0.8),
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  message,
                  textAlign: TextAlign.center,
                  style: FactifyText.sans(14, color: k.ink2).copyWith(height: 1.55),
                ),
                const SizedBox(height: 20),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  decoration: BoxDecoration(
                    color: k.sf,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: k.line),
                  ),
                  child: Row(
                    children: [
                      Icon(rowIcon, size: 18, color: k.ink3),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              row,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: FactifyText.sans(13, weight: FontWeight.w600, color: k.ink),
                            ),
                            Text(note, style: FactifyText.sans(11.5, color: k.ink3)),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(18, 12, 18, 10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (action != null) ...[
                FxButton(
                  label: action.$1,
                  icon: action.$2,
                  onPressed: action.$3,
                  height: 54,
                  fontSize: 15,
                ),
                const SizedBox(height: 8),
              ],
              FxButton(
                label: l10n.backToHome,
                variant: FxButtonVariant.ghost,
                onPressed: onClose,
                height: 46,
                fontSize: 14,
              ),
            ],
          ),
        ),
      ],
    );
  }

  /// The one next step: its label, icon and what it does. Null when there is none
  /// beyond going home.
  (String, IconData, VoidCallback)? _action(AppLocalizations l10n) {
    final retry = onRetry;
    return switch (problem) {
      CheckProblem.linkUnread => (
        l10n.errLinkAction,
        FxIcons.paste,
        () => onExit(CheckExit.pasteText),
      ),
      CheckProblem.dailyLimit => (
        l10n.errLimitAction,
        FxIcons.history,
        () => onExit(CheckExit.openHistory),
      ),
      CheckProblem.outOfCredits => (
        l10n.errCreditsAction,
        FxIcons.profile,
        () => onExit(CheckExit.openProfile),
      ),
      CheckProblem.signedOut when onSignIn != null => (
        l10n.signInButton,
        FxIcons.person,
        onSignIn!,
      ),
      CheckProblem.tooLarge => (
        l10n.errTooLargeAction,
        FxIcons.folder,
        () => onExit(CheckExit.chooseFile),
      ),
      _ when retry != null => (l10n.tryAgain, FxIcons.retry, retry),
      _ => null,
    };
  }

  /// What was being checked, on one line, with the icon of its kind.
  static (IconData, String) _what(Submission submission) {
    final file = submission.file;
    final name = file == null ? '' : file.uri.pathSegments.last;
    return switch (submission.kind) {
      SubmissionKind.link => (
        FxIcons.link,
        (submission.text ?? '').replaceFirst(RegExp(r'^https?://(www\.)?'), ''),
      ),
      SubmissionKind.image => (FxIcons.image, name),
      SubmissionKind.document => (FxIcons.pdf, name),
      _ => (FxIcons.text, (submission.text ?? '').split('\n').first.trim()),
    };
  }
}

/// A problem's icon, overline and title.
class _Shape {
  const _Shape(this.icon, this.overline, this.title);

  final IconData icon;
  final String overline;
  final String title;

  static _Shape of(CheckProblem problem, AppLocalizations l10n) => switch (problem) {
    CheckProblem.linkUnread => _Shape(FxIcons.brokenLink, l10n.errUnfinished, l10n.errLinkTitle),
    CheckProblem.offline => _Shape(FxIcons.offline, l10n.errNoConnection, l10n.errOfflineTitle),
    CheckProblem.slow => _Shape(FxIcons.history, l10n.errUnfinished, l10n.errSlowTitle),
    CheckProblem.dailyLimit => _Shape(FxIcons.lock, l10n.errDailyLimit, l10n.errLimitTitle),
    CheckProblem.outOfCredits => _Shape(FxIcons.lock, l10n.creditsTitle, l10n.errCreditsTitle),
    CheckProblem.signedOut => _Shape(FxIcons.person, l10n.errYourAccount, l10n.errSignedOutTitle),
    CheckProblem.tooLarge => _Shape(FxIcons.document, l10n.errUnfinished, l10n.errTooLargeTitle),
    CheckProblem.paused => _Shape(FxIcons.service, l10n.errUnfinished, l10n.errPausedTitle),
    CheckProblem.other => _Shape(FxIcons.info, l10n.errUnfinished, l10n.checkingFailedTitle),
  };
}

/// The sentence for a failure: the link page's own for a link that could not be
/// read, otherwise the failure's.
String errorMessage(AppLocalizations l10n, CheckProblem problem, ApiFailure failure) =>
    problem == CheckProblem.linkUnread ? l10n.errLinkBody : l10n.describeFailure(failure);
