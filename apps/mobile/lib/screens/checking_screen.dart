/// A check in progress, on its own page, until the answer replaces it (v5).
///
/// What it shows is only what is true. The scanner, the step and the sources come
/// from the server's own reports as the check runs (contract 1.3): which step it is
/// on, each source as it is opened, and whether that source had anything to say
/// about the claim. An upload has a real percentage and a deep check reports claims
/// done, so both are shown. A server that reports nothing - an older one, or a
/// stream that could not be read - gets no invented progress: the clock of seconds
/// actually spent, the steps every check goes through, and how long one usually
/// takes, so a forty-second wait reads as normal rather than stuck.
///
/// "Notify me when ready" lets the person leave: the check carries on
/// (lib/checks/check_job.dart) and a notification brings them back to the answer.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../app_services.dart';
import '../checks/check_job.dart';
import '../l10n/app_localizations.dart';
import '../l10n/phrases.dart';
import '../models/submission.dart';
import '../models/verdict.dart';
import '../theme/icons.dart';
import '../theme/tokens.dart';
import '../theme/typography.dart';
import '../widgets/scanner.dart';
import '../widgets/ui/fx_button.dart';
import 'result_screen.dart';

typedef _Phrase = String Function(AppLocalizations l10n);

class CheckingScreen extends StatefulWidget {
  const CheckingScreen({
    required this.services,
    required this.submission,
    this.deep = false,
    this.recheck = false,
    this.onFinished,
    this.job,
    super.key,
  });

  final AppServices services;
  final Submission submission;
  final bool deep;

  /// Checked fresh rather than answered from the server's store ("Check again").
  final bool recheck;

  /// Called once the answer is in, before it is shown (Home clears its input).
  final VoidCallback? onFinished;

  /// Supplied by tests; the screen otherwise starts its own.
  final CheckJob Function(String language)? job;

  @override
  State<CheckingScreen> createState() => _CheckingScreenState();
}

class _CheckingScreenState extends State<CheckingScreen> {
  // How long the server may stay silent before the screen stops expecting reports.
  static const _silence = Duration(seconds: 4);

  final Stopwatch _clock = Stopwatch();
  Timer? _tick;
  Timer? _quiet;
  bool _silent = false;
  CheckJob? _job;
  _Phrase? _error;
  bool _retryable = false;
  bool _left = false;

  AppServices get _services => widget.services;

  @override
  void initState() {
    super.initState();
    // After the first frame: the check is sent in the interface language, which the
    // page can only read once it is in the tree.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _run();
    });
  }

  @override
  void dispose() {
    _tick?.cancel();
    _quiet?.cancel();
    if (!_left) _job?.leave();
    super.dispose();
  }

  String get _language => Localizations.localeOf(context).languageCode;

  void _run() {
    final job =
        widget.job?.call(_language) ??
        CheckJob(
          services: _services,
          submission: widget.submission,
          language: _language,
          deep: widget.deep,
          recheck: widget.recheck,
          notifyWhenReady: _services.notifyByDefault.value,
        );
    setState(() {
      _error = null;
      _job = job;
      _silent = false;
    });
    _quiet?.cancel();
    _quiet = Timer(_silence, () {
      if (mounted) setState(() => _silent = true);
    });
    _clock
      ..reset()
      ..start();
    _tick?.cancel();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
    job.start();
    unawaited(_await(job));
  }

  Future<void> _await(CheckJob job) async {
    try {
      final verdict = await job.result;
      if (!mounted || _left || job != _job) return;
      if (verdict == null) {
        _stop((l10n) => l10n.deepTooSlow, retryable: true);
        return;
      }
      _show(verdict);
    } on CheckFailed catch (failed) {
      if (!mounted || job != _job) return;
      final failure = failed.failure;
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

  void _show(Verdict verdict) {
    widget.onFinished?.call();
    unawaited(
      Navigator.of(context).pushReplacement(
        PageRouteBuilder<void>(
          transitionDuration: const Duration(milliseconds: 350),
          pageBuilder: (_, _, _) => ResultScreen(
            services: _services,
            verdict: verdict,
            submission: widget.submission,
            justChecked: true,
          ),
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
  }

  void _stop(_Phrase message, {required bool retryable}) {
    _tick?.cancel();
    _clock.stop();
    setState(() {
      _error = message;
      _retryable = retryable;
    });
  }

  void _leave() {
    _left = true;
    _job?.leave();
    Navigator.of(context).pop();
  }

  Future<void> _toggleNotify() async {
    final job = _job;
    if (job == null) return;
    final l10n = AppLocalizations.of(context);
    final messenger = ScaffoldMessenger.of(context);
    if (!job.notifyWhenReady && !await _services.notifier.askPermission()) {
      messenger.showSnackBar(SnackBar(content: Text(l10n.notifyDenied)));
      return;
    }
    setState(() => job.notifyWhenReady = !job.notifyWhenReady);
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final error = _error;
    final job = _job;
    return PopScope(
      canPop: true,
      onPopInvokedWithResult: (didPop, _) {
        if (didPop && !_left) {
          _left = true;
          _job?.leave();
        }
      },
      child: Scaffold(
        backgroundColor: k.bg,
        body: SafeArea(
          child: CustomScrollView(
            slivers: [
              SliverFillRemaining(
                hasScrollBody: false,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(20, 2, 20, 16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _TopRow(
                        seconds: _clock.elapsed.inSeconds,
                        onClose: _leave,
                        showTimer: error == null,
                      ),
                      if (error != null)
                        ..._failed(context, error)
                      else if (job != null)
                        ValueListenableBuilder<CheckWatch>(
                          valueListenable: job.watch,
                          builder: (context, watch, _) => _Working(
                            submission: widget.submission,
                            deep: widget.deep,
                            watch: watch,
                            silent: !watch.heard && _silent,
                            notify: job.notifyWhenReady,
                            onNotify: _toggleNotify,
                          ),
                        ),
                      if (error == null && job == null) const Spacer(),
                      if (error == null && job == null)
                        Text(
                          l10n.checkingTitle,
                          textAlign: TextAlign.center,
                          style: FactifyText.sans(14, color: k.ink3),
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

  List<Widget> _failed(BuildContext context, _Phrase error) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    return [
      const Spacer(),
      Center(
        child: Container(
          width: 84,
          height: 84,
          decoration: BoxDecoration(color: k.uS, shape: BoxShape.circle),
          child: Icon(FxIcons.offline, size: 38, color: k.uC),
        ),
      ),
      const SizedBox(height: 18),
      Text(
        l10n.checkingFailedTitle,
        textAlign: TextAlign.center,
        style: FactifyText.serif(24, color: k.ink),
      ),
      const SizedBox(height: 8),
      Text(
        error(l10n),
        textAlign: TextAlign.center,
        style: FactifyText.sans(14.5, color: k.ink2),
      ),
      const Spacer(),
      if (_retryable) ...[
        FxButton(label: l10n.retry, icon: FxIcons.retry, onPressed: _run),
        const SizedBox(height: 10),
      ],
      FxButton(
        label: l10n.backToHome,
        variant: FxButtonVariant.secondary,
        onPressed: () => Navigator.of(context).pop(),
      ),
    ];
  }
}

class _TopRow extends StatelessWidget {
  const _TopRow({required this.seconds, required this.onClose, required this.showTimer});

  final int seconds;
  final VoidCallback onClose;
  final bool showTimer;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final shown = seconds < 60
        ? l10n.elapsedSeconds(seconds)
        : '${seconds ~/ 60}:${(seconds % 60).toString().padLeft(2, '0')}';
    return SizedBox(
      height: 44,
      child: Row(
        children: [
          FxCircleButton(
            icon: FxIcons.close,
            tooltip: l10n.checkingCancel,
            onPressed: onClose,
            size: 38,
            iconSize: 20,
            bordered: true,
          ),
          Expanded(
            child: Text(
              l10n.checkingOf.toUpperCase(),
              textAlign: TextAlign.center,
              style: FactifyText.mono(11, color: k.ink3, spacing: 1.4),
            ),
          ),
          SizedBox(
            width: 44,
            child: showTimer
                ? Text(
                    shown,
                    textAlign: TextAlign.end,
                    style: FactifyText.mono(
                      13,
                      color: k.ink3,
                      spacing: 0,
                    ).copyWith(fontFeatures: const [FontFeature.tabularFigures()]),
                  )
                : null,
          ),
        ],
      ),
    );
  }
}

class _Working extends StatelessWidget {
  const _Working({
    required this.submission,
    required this.deep,
    required this.watch,
    required this.silent,
    required this.notify,
    required this.onNotify,
  });

  final Submission submission;
  final bool deep;
  final CheckWatch watch;

  /// Nothing reported yet, well into the check: the server is not reporting.
  final bool silent;
  final bool notify;
  final VoidCallback onNotify;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final uploading = watch.upload != null && watch.upload! < 1;
    // Sending the file is part of reading it; before the first report the check is
    // being read, which every check starts with.
    final step = watch.step < 0 ? 0 : watch.step;
    final labels = [l10n.stepReading, l10n.stepSearching, l10n.stepComparing];
    final what = submission.kind == SubmissionKind.image && submission.summary.isEmpty
        ? (submission.video ? l10n.yourVideo : l10n.yourPicture)
        : submission.summary;
    final detail = uploading
        ? l10n.uploading((watch.upload! * 100).round())
        : deep && watch.claimsTotal > 0
        ? l10n.deepProgress(watch.claimsDone, watch.claimsTotal)
        : null;

    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: 10),
          Text(
            '“$what”',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: FactifyText.serif(
              15,
              weight: FontWeight.w400,
              color: k.ink2,
            ).copyWith(fontStyle: FontStyle.italic),
          ),
          const SizedBox(height: 16),
          Center(child: Scanner(sources: watch.sources)),
          const SizedBox(height: 16),
          if (silent) ...[
            Text(
              deep ? l10n.deepChecking : l10n.working,
              textAlign: TextAlign.center,
              style: FactifyText.serif(22, color: k.ink).copyWith(height: 1.2),
            ),
            if (detail != null) _Detail(detail),
            const SizedBox(height: 20),
            _StepsCard(labels: labels),
            const SizedBox(height: 12),
            Text(
              deep ? l10n.deepUsuallyTakes : l10n.usuallyTakes,
              textAlign: TextAlign.center,
              style: FactifyText.sans(12.5, color: k.ink3),
            ),
          ] else ...[
            Semantics(
              liveRegion: true,
              child: Column(
                children: [
                  Text(
                    l10n.stepOf(step + 1, 3).toUpperCase(),
                    textAlign: TextAlign.center,
                    style: FactifyText.mono(10.5, color: k.acc),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    labels[step],
                    textAlign: TextAlign.center,
                    style: FactifyText.serif(
                      22,
                      color: k.ink,
                    ).copyWith(height: 1.2, letterSpacing: -0.3),
                  ),
                ],
              ),
            ),
            if (detail != null) _Detail(detail),
            const SizedBox(height: 12),
            _Segments(step: step, upload: uploading ? watch.upload : null),
            const SizedBox(height: 20),
            _SourcesCard(watch: watch),
          ],
          const Spacer(),
          const SizedBox(height: 12),
          if (!silent) _EvidenceStrip(watch: watch),
          const SizedBox(height: 10),
          _NotifyButton(on: notify, onTap: onNotify),
        ],
      ),
    );
  }
}

class _Detail extends StatelessWidget {
  const _Detail(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 4),
    child: Text(
      text,
      textAlign: TextAlign.center,
      style: FactifyText.sans(12.5, color: FactifyTokens.of(context).ink3),
    ),
  );
}

/// Three bars, one per step: done steps full, the current one moving (or filling
/// with an upload, which has a real fraction), later ones empty.
class _Segments extends StatelessWidget {
  const _Segments({required this.step, this.upload});

  final int step;
  final double? upload;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Center(
      child: SizedBox(
        width: 168,
        child: Row(
          children: [
            for (var i = 0; i < 3; i++) ...[
              if (i > 0) const SizedBox(width: 4),
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(2),
                  child: SizedBox(
                    height: 4,
                    child: i < step
                        ? ColoredBox(color: k.acc)
                        : i == step
                        ? upload != null
                              ? LinearProgressIndicator(
                                  value: upload,
                                  color: k.acc,
                                  backgroundColor: k.line,
                                )
                              : LinearProgressIndicator(color: k.acc, backgroundColor: k.line)
                        : ColoredBox(color: k.line),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _SourcesCard extends StatelessWidget {
  const _SourcesCard({required this.watch});

  final CheckWatch watch;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final recent = watch.recent;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14),
      decoration: BoxDecoration(
        color: k.sf,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: k.line),
      ),
      child: Column(
        children: [
          SizedBox(
            height: 40,
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    l10n.sourcesTitle,
                    style: FactifyText.sans(13, weight: FontWeight.w600, color: k.ink),
                  ),
                ),
                if (watch.sources.isNotEmpty)
                  Text(
                    l10n.sourcesRead(watch.read, watch.sources.length),
                    style: FactifyText.sans(12, color: k.ink3),
                  ),
              ],
            ),
          ),
          if (recent.isEmpty)
            _Row(initials: '·', name: l10n.sourcesWaiting, state: null, muted: true)
          else
            for (final source in recent)
              _Row(initials: source.initials, name: source.publisher, state: source.state),
        ],
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({required this.initials, required this.name, required this.state, this.muted = false});

  final String initials;
  final String name;
  final SourceState? state;
  final bool muted;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final found = state == SourceState.evidence;
    final (label, colour) = switch (state) {
      SourceState.reading => (l10n.sourceReading, k.ink2),
      SourceState.evidence => (l10n.sourceEvidence, k.acc),
      SourceState.notRelevant => (l10n.sourceNotRelevant, k.ink3),
      null => ('', k.ink3),
    };
    return Container(
      height: 44,
      decoration: BoxDecoration(
        border: Border(top: BorderSide(color: k.line)),
      ),
      child: Row(
        children: [
          AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            width: 28,
            height: 28,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: found ? k.acc : k.sf2,
              borderRadius: BorderRadius.circular(9),
            ),
            child: Text(
              initials,
              style: FactifyText.sans(
                8.5,
                weight: FontWeight.w700,
                color: found ? k.onAcc : (muted ? k.ink3 : k.ink2),
              ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: FactifyText.sans(
                13.5,
                weight: muted ? FontWeight.w400 : FontWeight.w500,
                color: muted ? k.ink3 : k.ink,
              ),
            ),
          ),
          if (state != null) ...[
            const SizedBox(width: 8),
            if (state == SourceState.reading)
              SizedBox.square(
                dimension: 10,
                child: CircularProgressIndicator(strokeWidth: 1.5, color: k.acc),
              )
            else
              Icon(found ? FxIcons.check : FxIcons.minus, size: 15, color: colour),
            const SizedBox(width: 5),
            Text(
              label,
              style: FactifyText.sans(12, weight: FontWeight.w600, color: colour),
            ),
          ],
        ],
      ),
    );
  }
}

class _EvidenceStrip extends StatelessWidget {
  const _EvidenceStrip({required this.watch});

  final CheckWatch watch;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final found = watch.found.take(4).toList();
    final count = watch.evidence;
    return Semantics(
      liveRegion: true,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(color: k.accS, borderRadius: BorderRadius.circular(20)),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    l10n.evidenceCollected,
                    style: FactifyText.sans(12.5, weight: FontWeight.w600, color: k.acc),
                  ),
                  const SizedBox(height: 2),
                  Text(l10n.evidenceNote(count), style: FactifyText.sans(12, color: k.ink2)),
                ],
              ),
            ),
            if (found.isNotEmpty)
              SizedBox(
                height: 28,
                width: 28 + 20.0 * (found.length - 1),
                child: Stack(
                  children: [
                    for (var i = 0; i < found.length; i++)
                      PositionedDirectional(
                        start: 20.0 * i,
                        child: Container(
                          width: 28,
                          height: 28,
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: k.acc,
                            shape: BoxShape.circle,
                            border: Border.all(color: k.bg, width: 2),
                          ),
                          child: Text(
                            found[i].initials,
                            style: FactifyText.sans(8.5, weight: FontWeight.w700, color: k.onAcc),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            const SizedBox(width: 12),
            ConstrainedBox(
              constraints: const BoxConstraints(minWidth: 18),
              child: Text(
                '$count',
                textAlign: TextAlign.end,
                style: FactifyText.serif(30, color: k.acc).copyWith(height: 1),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _NotifyButton extends StatelessWidget {
  const _NotifyButton({required this.on, required this.onTap});

  final bool on;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final colour = on ? k.acc : k.ink2;
    return Semantics(
      toggled: on,
      button: true,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(14),
          child: Container(
            constraints: const BoxConstraints(minHeight: 44),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: k.line),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(on ? FxIcons.bellRinging : FxIcons.bell, size: 17, color: colour),
                const SizedBox(width: 8),
                Flexible(
                  child: Text(
                    on ? l10n.notifyOn : l10n.notifyMe,
                    textAlign: TextAlign.center,
                    style: FactifyText.sans(13.5, weight: FontWeight.w600, color: colour),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The three steps every check goes through, listed and not ticked off: shown
/// when the server does not report which one it is on.
class _StepsCard extends StatelessWidget {
  const _StepsCard({required this.labels});

  final List<String> labels;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 4),
      decoration: BoxDecoration(
        color: k.sf,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: k.line),
      ),
      child: Column(
        children: [
          for (final (index, label) in labels.indexed)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                children: [
                  Container(
                    width: 24,
                    height: 24,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(color: k.accS, shape: BoxShape.circle),
                    child: Text(
                      '${index + 1}',
                      style: FactifyText.sans(11.5, weight: FontWeight.w700, color: k.acc),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(label, style: FactifyText.sans(13.5, color: k.ink)),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
