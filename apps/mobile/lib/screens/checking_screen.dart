/// A check in progress, on its own page, until the answer replaces it.
///
/// What it shows is only what is true. An upload has a real percentage and a deep
/// check reports claims done, so both get real bars. A normal check reports nothing
/// until it answers, so there is no bar pretending to know how far along it is: a
/// timer of the seconds actually spent, the steps every check goes through, and how
/// long one usually takes, so a forty-second wait reads as normal rather than stuck.
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../app_services.dart';
import '../l10n/app_localizations.dart';
import '../l10n/phrases.dart';
import '../models/submission.dart';
import '../models/verdict.dart';
import '../theme/colors.dart';
import '../widgets/checked_item_card.dart';
import 'result_screen.dart';

typedef _Phrase = String Function(AppLocalizations l10n);

class CheckingScreen extends StatefulWidget {
  const CheckingScreen({
    required this.services,
    required this.submission,
    this.deep = false,
    this.recheck = false,
    this.onFinished,
    super.key,
  });

  final AppServices services;
  final Submission submission;
  final bool deep;

  /// Checked fresh rather than answered from the server's store ("Check again").
  final bool recheck;

  /// Called once the answer is in, before it is shown (Home clears its input).
  final VoidCallback? onFinished;

  @override
  State<CheckingScreen> createState() => _CheckingScreenState();
}

class _CheckingScreenState extends State<CheckingScreen> {
  final Stopwatch _clock = Stopwatch();
  Timer? _tick;
  double? _upload;
  (int, int)? _deepProgress;
  _Phrase? _error;
  bool _retryable = false;
  bool _leaving = false;

  AppServices get _services => widget.services;

  @override
  void initState() {
    super.initState();
    // After the first frame: the check is sent in the interface language, which the
    // page can only read once it is in the tree.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) unawaited(_run());
    });
  }

  @override
  void dispose() {
    _leaving = true;
    _tick?.cancel();
    super.dispose();
  }

  String get _language => Localizations.localeOf(context).languageCode;

  Future<void> _run() async {
    setState(() {
      _error = null;
      _upload = null;
      _deepProgress = null;
    });
    _clock
      ..reset()
      ..start();
    _tick?.cancel();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });

    try {
      final verdict = await _verdict();
      if (!mounted || _leaving) return;
      if (verdict == null) {
        _stop((l10n) => l10n.deepTooSlow, retryable: true);
        return;
      }
      await _services.history.add(widget.submission, verdict);
      // The check cost a credit; show the balance the server now holds.
      unawaited(_services.auth.refreshAccount());
      widget.onFinished?.call();
      if (!mounted) return;
      unawaited(
        Navigator.of(context).pushReplacement(
          PageRouteBuilder<void>(
            transitionDuration: const Duration(milliseconds: 350),
            pageBuilder: (_, _, _) =>
                ResultScreen(services: _services, verdict: verdict, submission: widget.submission),
            transitionsBuilder: (_, animation, _, child) => FadeTransition(
              opacity: animation,
              child: SlideTransition(
                position: Tween(begin: const Offset(0, 0.04), end: Offset.zero).animate(animation),
                child: child,
              ),
            ),
          ),
        ),
      );
    } on ApiFailure catch (failure) {
      if (!mounted) return;
      if (failure.kind == FailureKind.signedOut) {
        // The session is over: back to sign-in, which the app shell does on sign-out.
        unawaited(_services.auth.signOut());
      }
      final link = widget.submission.kind == SubmissionKind.link;
      if (link && failure.kind == FailureKind.invalidInput) {
        // A link the server refused is a page it could not read or found nothing
        // to check on - not "Unconfirmed", as though sources had been looked for.
        _stop((l10n) => l10n.failureLinkUnchecked, retryable: false);
      } else {
        _stop((l10n) => l10n.describeFailure(failure), retryable: failure.retryable);
      }
    }
  }

  void _stop(_Phrase message, {required bool retryable}) {
    _tick?.cancel();
    _clock.stop();
    setState(() {
      _error = message;
      _retryable = retryable;
    });
  }

  Future<Verdict?> _verdict() async {
    final submission = widget.submission;
    final client = _services.client;
    final language = _language;
    switch (submission.kind) {
      case SubmissionKind.text:
      case SubmissionKind.link:
        final value = submission.text ?? '';
        final link = submission.kind == SubmissionKind.link;
        if (widget.deep) return _deepCheck(value, link: link);
        return link
            ? client.verifyUrl(value, language: language, recheck: widget.recheck)
            : client.verifyText(value, language: language, recheck: widget.recheck);
      case SubmissionKind.image:
      case SubmissionKind.document:
        final outcome = await client.verifyFile(
          submission.file!,
          // Choosing the file is the consent: it was picked for checking, which is
          // the only thing the flag governs.
          consentToProcessMedia: true,
          language: language,
          recheck: widget.recheck,
          onProgress: _showUpload,
        );
        if (mounted) setState(() => _upload = null);
        if (outcome.isPending) return _poll(outcome.pendingCaseId!);
        return outcome.verdict;
    }
  }

  /// A deep check: started, then followed until the verdict. Null past the wait.
  Future<Verdict?> _deepCheck(String value, {required bool link}) async {
    final caseId = await _services.client.startDeepCheck(
      text: link ? null : value,
      url: link ? value : null,
      language: _language,
      recheck: widget.recheck,
    );
    if (mounted) setState(() => _deepProgress = (0, 0));
    // Up to five minutes: past the server's own three-minute budget, so a check
    // that finished is always collected.
    for (var attempt = 0; attempt < 100; attempt++) {
      await Future<void>.delayed(const Duration(seconds: 3));
      if (!mounted || _leaving) return null;
      final progress = await _services.client.checkOn(caseId);
      if (progress.verdict != null) return progress.verdict;
      setState(() => _deepProgress = (progress.done, progress.total));
    }
    return null;
  }

  /// A video: accepted, then polled for, bounded to about thirty seconds.
  Future<Verdict?> _poll(String caseId) async {
    for (var attempt = 0; attempt < 15; attempt++) {
      await Future<void>.delayed(const Duration(seconds: 2));
      if (!mounted || _leaving) return null;
      final verdict = await _services.client.getCase(caseId);
      if (verdict != null) return verdict;
    }
    return null;
  }

  /// Redrawn in steps of two percent, not on every chunk.
  void _showUpload(int sent, int total) {
    if (!mounted || total <= 0) return;
    final value = sent / total;
    final shown = _upload;
    if (shown == null || value - shown >= 0.02 || value >= 1) setState(() => _upload = value);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final error = _error;
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          tooltip: l10n.checkingCancel,
          icon: const Icon(Icons.close_rounded),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: Text(l10n.checkingOf),
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
          children: [
            CheckedItemCard.of(widget.submission),
            const SizedBox(height: 28),
            if (error == null) ..._working(context) else ..._failed(context, error),
          ],
        ),
      ),
    );
  }

  List<Widget> _working(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final upload = _upload;
    final uploading = upload != null && upload < 1;
    final deep = _deepProgress;
    final seconds = _clock.elapsed.inSeconds;
    final shown = '${seconds ~/ 60}:${(seconds % 60).toString().padLeft(2, '0')}';
    final fraction = uploading
        ? upload
        : deep != null && deep.$2 > 0
        ? deep.$1 / deep.$2
        : null;

    return [
      Center(
        child: SizedBox(
          width: 168,
          height: 168,
          child: Stack(
            alignment: Alignment.center,
            children: [
              SizedBox(
                width: 168,
                height: 168,
                child: CircularProgressIndicator(
                  value: fraction,
                  strokeWidth: 8,
                  strokeCap: StrokeCap.round,
                  color: FactifyColors.emerald,
                  backgroundColor: FactifyColors.emeraldTint,
                ),
              ),
              Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    shown,
                    style: theme.textTheme.displaySmall?.copyWith(
                      fontWeight: FontWeight.w800,
                      color: FactifyColors.ink,
                      fontFeatures: const [FontFeature.tabularFigures()],
                    ),
                  ),
                  if (uploading)
                    Text(
                      '${(upload * 100).round()}%',
                      style: theme.textTheme.labelMedium?.copyWith(color: FactifyColors.inkMuted),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
      const SizedBox(height: 24),
      Text(
        widget.deep ? l10n.deepChecking : l10n.checkingTitle,
        textAlign: TextAlign.center,
        style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
      ),
      const SizedBox(height: 6),
      Text(
        uploading
            ? l10n.uploading((upload * 100).round())
            : deep != null && deep.$2 > 0
            ? l10n.deepProgress(deep.$1, deep.$2)
            : l10n.working,
        textAlign: TextAlign.center,
        style: theme.textTheme.bodyMedium?.copyWith(color: FactifyColors.inkMuted),
      ),
      const SizedBox(height: 26),
      Card(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 6),
          child: Column(
            children: [
              for (final (index, step) in [
                l10n.stepReading,
                l10n.stepSearching,
                l10n.stepComparing,
              ].indexed)
                _Step(
                  number: index + 1,
                  text: step,
                  pulse: _clock.elapsed.inMilliseconds,
                  index: index,
                ),
            ],
          ),
        ),
      ),
      const SizedBox(height: 14),
      Text(
        widget.deep ? l10n.deepUsuallyTakes : l10n.usuallyTakes,
        textAlign: TextAlign.center,
        style: theme.textTheme.bodySmall?.copyWith(color: FactifyColors.inkMuted),
      ),
    ];
  }

  List<Widget> _failed(BuildContext context, _Phrase error) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    return [
      Center(
        child: Container(
          width: 84,
          height: 84,
          decoration: BoxDecoration(
            color: theme.colorScheme.errorContainer,
            shape: BoxShape.circle,
          ),
          child: Icon(Icons.error_outline_rounded, size: 42, color: theme.colorScheme.error),
        ),
      ),
      const SizedBox(height: 18),
      Text(
        l10n.checkingFailedTitle,
        textAlign: TextAlign.center,
        style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
      ),
      const SizedBox(height: 8),
      Text(
        error(l10n),
        textAlign: TextAlign.center,
        style: theme.textTheme.bodyMedium?.copyWith(color: FactifyColors.inkSoft),
      ),
      const SizedBox(height: 26),
      if (_retryable) ...[
        FilledButton.icon(
          onPressed: _run,
          icon: const Icon(Icons.refresh_rounded),
          label: Text(l10n.retry),
        ),
        const SizedBox(height: 10),
      ],
      OutlinedButton(onPressed: () => Navigator.of(context).pop(), child: Text(l10n.backToHome)),
    ];
  }
}

/// One step every check goes through. Listed, not ticked off: the server does not
/// report which step it is on, so none is claimed as done. The gentle pulse says
/// the work is happening, and nothing more.
class _Step extends StatelessWidget {
  const _Step({required this.number, required this.text, required this.pulse, required this.index});

  final int number;
  final String text;
  final int pulse;
  final int index;

  @override
  Widget build(BuildContext context) {
    final glow = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(pulse / 600 + index * 1.2));
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Container(
            width: 26,
            height: 26,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: FactifyColors.emeraldTint.withValues(alpha: glow),
              shape: BoxShape.circle,
            ),
            child: Text(
              '$number',
              style: const TextStyle(
                color: FactifyColors.emeraldDeep,
                fontWeight: FontWeight.w800,
                fontSize: 12,
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(child: Text(text, style: Theme.of(context).textTheme.bodyMedium)),
        ],
      ),
    );
  }
}
