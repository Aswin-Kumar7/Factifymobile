/// The answer, on its own page (v5): the verdict in its colour, then what was
/// checked, each claim, the sources and the receipt.
///
/// Opened when a check finishes and again from History, from the same saved data.
/// The bottom bar re-runs the check fresh, and carries the one thing to do next:
/// send a correction back for False, context for Misleading, the result for True,
/// or check again for Unconfirmed.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/client.dart';
import '../app_services.dart';
import '../l10n/app_localizations.dart';
import '../l10n/phrases.dart';
import '../models/submission.dart';
import '../models/verdict.dart';
import '../widgets/action_style.dart';
import '../widgets/correction_sheet.dart';
import '../widgets/ui/ui.dart';
import '../widgets/verdict_card.dart';
import '../widgets/why_sheet.dart';
import 'checking_screen.dart';
import 'evidence_screen.dart';
import 'source_reader_screen.dart';

class ResultScreen extends StatefulWidget {
  ResultScreen({
    required this.services,
    required this.verdict,
    Submission? submission,
    SubmissionKind? kind,
    String? summary,
    Uint8List? thumbnail,
    this.justChecked = false,
    this.openShare = false,
    super.key,
  }) : submission = submission,
       kind = kind ?? submission?.kind ?? SubmissionKind.text,
       summary = summary ?? submission?.summaryWith(verdict) ?? '',
       thumbnail = thumbnail ?? submission?.thumbnail;

  final AppServices services;
  final Verdict verdict;

  /// What can be checked again. Null when it cannot, such as a picture from an old
  /// check whose file is no longer on the phone.
  final Submission? submission;
  final SubmissionKind kind;
  final String summary;
  final Uint8List? thumbnail;

  /// The verdict arrived just now, so the receipt it carries was checked just now.
  /// A result reopened from History checks its receipt again: the seal says the
  /// evidence is unchanged, and that is only true of the moment it was looked at.
  final bool justChecked;

  /// Opened from a notification's "Share correction": the share sheet opens at once.
  final bool openShare;

  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> {
  bool _reporting = false;
  bool _reported = false;
  ReceiptState? _receipt;
  String? _receiptId;

  Verdict get _verdict => widget.verdict;

  bool get _canCheckAgain {
    final submission = widget.submission;
    if (submission == null) return false;
    return submission.text != null || (submission.file?.existsSync() ?? false);
  }

  @override
  void initState() {
    super.initState();
    // A pulse as the verdict appears (v5 accessibility): felt, not only seen.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(HapticFeedback.mediumImpact());
      if (widget.openShare && mounted) _share();
    });
    final inline = _verdict.receipt;
    final receiptUrl = _verdict.receiptUrl;
    if (widget.justChecked && inline != null) {
      _receipt = inline.verified ? ReceiptState.verified : ReceiptState.failed;
      _receiptId = shortReceiptId(inline.receiptId);
    } else if (receiptUrl != null) {
      _receipt = ReceiptState.checking;
      unawaited(_checkReceipt(receiptUrl));
    }
  }

  Future<void> _checkReceipt(String url) async {
    try {
      final receipt = await widget.services.client.getReceipt(url);
      if (!mounted) return;
      setState(() {
        _receipt = receipt == null
            ? null
            : receipt.verified
            ? ReceiptState.verified
            : ReceiptState.failed;
        _receiptId = receipt == null ? null : shortReceiptId(receipt.receiptId);
      });
    } on ApiFailure {
      if (mounted) setState(() => _receipt = null);
    }
  }

  void _checkAgain() {
    final submission = widget.submission;
    if (submission == null) return;
    unawaited(
      Navigator.of(context).pushReplacement(
        MaterialPageRoute<void>(
          builder: (_) =>
              CheckingScreen(services: widget.services, submission: submission, recheck: true),
        ),
      ),
    );
  }

  void _home() => Navigator.of(context).popUntil((route) => route.isFirst);

  void _share() => unawaited(
    showCorrectionSheet(
      context,
      _verdict,
      load: (language) => widget.services.client.correctionText(_verdict.caseId, language),
    ),
  );

  void _openClaim(Claim claim) => unawaited(
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => EvidenceScreen(
          verdict: _verdict,
          language: widget.services.language,
          submission: widget.submission,
          client: widget.services.client,
        ),
      ),
    ),
  );

  /// A page where the picture appeared before, in the person's own browser.
  void _openPage(String url) {
    final uri = Uri.tryParse(url);
    if (uri != null) unawaited(launchUrl(uri, mode: LaunchMode.externalApplication));
  }

  /// A cited source, read in the app around the passage the result quoted.
  Future<void> _openSource(Evidence evidence) => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => SourceReaderScreen(
        services: widget.services,
        caseId: _verdict.caseId,
        evidence: evidence,
      ),
    ),
  );

  /// Flag this verdict for human review: a real request, confirmed only once the
  /// server has queued it.
  Future<void> _report() async {
    if (_reporting) return;
    setState(() => _reporting = true);
    final l10n = AppLocalizations.of(context);
    final messenger = ScaffoldMessenger.of(context);
    try {
      await widget.services.client.reportCase(_verdict.caseId);
      if (!mounted) return;
      setState(() => _reported = true);
      messenger.showSnackBar(SnackBar(content: Text(l10n.reportSent)));
    } on ApiFailure catch (failure) {
      messenger.showSnackBar(
        SnackBar(content: Text(l10n.reportFailed(l10n.describeFailure(failure)))),
      );
    } finally {
      if (mounted) setState(() => _reporting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final nothing = _verdict.nothingToCheck;
    final (_, soft) = nothing ? (k.uC, k.uS) : ActionStyle.colours(_verdict.factVerdict, k);
    final tint = Color.alphaBlend(soft, k.bg);
    final top = MediaQuery.paddingOf(context).top;

    final (label, icon, action) = switch (_verdict.factVerdict) {
      _ when nothing => (l10n.newCheck, FxIcons.forward, _home),
      FactVerdict.falseClaim => (l10n.shareCorrection, FxIcons.correction, _share),
      FactVerdict.misleading => (l10n.shareContext, FxIcons.correction, _share),
      FactVerdict.trueClaim => (l10n.shareResult, FxIcons.share, _share),
      FactVerdict.unconfirmed when _canCheckAgain => (
        l10n.checkAgain,
        FxIcons.recheck,
        _checkAgain,
      ),
      FactVerdict.unconfirmed => (l10n.newCheck, FxIcons.forward, _home),
    };

    return Scaffold(
      body: Stack(
        children: [
          ListView(
            padding: EdgeInsets.zero,
            children: [
              Container(
                color: tint,
                padding: EdgeInsets.fromLTRB(12, top + 2, 12, 0),
                child: Row(
                  children: [
                    FxCircleButton(
                      icon: FxIcons.back,
                      tooltip: MaterialLocalizations.of(context).backButtonTooltip,
                      onPressed: () => Navigator.of(context).maybePop(),
                    ),
                    Expanded(
                      child: Text(
                        l10n.resultTitle,
                        textAlign: TextAlign.center,
                        style: FactifyText.sans(13, weight: FontWeight.w600, color: k.ink2),
                      ),
                    ),
                    FxCircleButton(
                      icon: FxIcons.share,
                      tooltip: l10n.shareCorrection,
                      iconSize: 19,
                      onPressed: nothing ? null : _share,
                    ),
                  ],
                ),
              ),
              VerdictCard(
                verdict: _verdict,
                kind: widget.kind,
                submittedText: widget.submission?.text,
                thumbnail: widget.thumbnail,
                onWhy: () => unawaited(showWhySheet(context, _verdict)),
                onOpenClaim: _openClaim,
                onOpenSource: _openSource,
                onReportForReview: _reported ? null : _report,
                reporting: _reporting,
                reported: _reported,
                receipt: _receipt,
                receiptId: _receiptId,
                serverUrl: widget.services.client.baseUrl,
                onOpenPage: _openPage,
              ),
            ],
          ),
          // The status bar keeps the verdict's tint, so the page scrolls beneath it
          // rather than under the clock.
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            height: top,
            child: ColoredBox(color: tint),
          ),
        ],
      ),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: k.nav,
          border: Border(top: BorderSide(color: k.line)),
        ),
        child: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Row(
              children: [
                Semantics(
                  button: true,
                  label: l10n.checkAgain,
                  excludeSemantics: true,
                  child: AnimatedOpacity(
                    duration: const Duration(milliseconds: 200),
                    opacity: _canCheckAgain ? 1 : 0.4,
                    child: Material(
                      color: k.sf2,
                      borderRadius: BorderRadius.circular(18),
                      clipBehavior: Clip.antiAlias,
                      child: InkWell(
                        onTap: _canCheckAgain ? _checkAgain : null,
                        child: SizedBox(
                          width: 52,
                          height: 52,
                          child: Icon(FxIcons.recheck, size: 22, color: k.ink),
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: FxButton(
                    label: label,
                    icon: icon,
                    variant: FxButtonVariant.dark,
                    height: 52,
                    radius: 18,
                    fontSize: 15,
                    onPressed: action,
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

/// A receipt id as shown on the seal: its first seven characters, "7F3A-21C".
String shortReceiptId(String id) {
  final plain = id
      .replaceFirst(RegExp(r'^[A-Za-z]+[_:]'), '')
      .replaceAll(RegExp('[^0-9A-Za-z]'), '')
      .toUpperCase();
  if (plain.length < 7) return plain;
  return '${plain.substring(0, 4)}-${plain.substring(4, 7)}';
}
