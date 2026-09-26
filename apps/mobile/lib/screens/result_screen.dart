/// The answer, on its own page: what was checked, what was read, the verdict, and
/// the sources it rests on.
///
/// Opened when a check finishes and again from History, from the same saved data.
/// "Check again" runs the same thing fresh; "New check" goes back to an empty Home.
library;

import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../app_services.dart';
import '../l10n/app_localizations.dart';
import '../l10n/phrases.dart';
import '../models/submission.dart';
import '../models/verdict.dart';
import '../theme/colors.dart';
import '../widgets/checked_item_card.dart';
import '../widgets/correction_sheet.dart';
import '../widgets/image_reading_card.dart';
import '../widgets/verdict_card.dart';
import 'checking_screen.dart';
import 'evidence_screen.dart';

class ResultScreen extends StatefulWidget {
  ResultScreen({
    required this.services,
    required this.verdict,
    Submission? submission,
    SubmissionKind? kind,
    String? summary,
    Uint8List? thumbnail,
    super.key,
  }) : submission = submission,
       kind = kind ?? submission?.kind ?? SubmissionKind.text,
       summary = summary ?? submission?.summary ?? '',
       thumbnail = thumbnail ?? submission?.thumbnail;

  final AppServices services;
  final Verdict verdict;

  /// What can be checked again. Null when it cannot, such as a picture from an old
  /// check whose file is no longer on the phone.
  final Submission? submission;
  final SubmissionKind kind;
  final String summary;
  final Uint8List? thumbnail;

  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> {
  bool _reporting = false;
  bool _reported = false;

  Verdict get _verdict => widget.verdict;

  bool get _canCheckAgain {
    final submission = widget.submission;
    if (submission == null) return false;
    return submission.text != null || (submission.file?.existsSync() ?? false);
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

  void _newCheck() => Navigator.of(context).popUntil((route) => route.isFirst);

  void _openEvidence() => unawaited(
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
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final reading = _verdict.imageReading;

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.resultTitle),
        actions: [
          IconButton(
            tooltip: l10n.shareCorrection,
            icon: const Icon(Icons.ios_share_rounded),
            onPressed: () => unawaited(showCorrectionSheet(context, _verdict)),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
          children: [
            CheckedItemCard(
              kind: widget.kind,
              summary: widget.summary,
              thumbnail: widget.thumbnail,
              label: l10n.whatWeCheckedTitle,
            ),
            const SizedBox(height: 12),
            if (reading != null) ...[
              ImageReadingCard(reading: reading),
              const SizedBox(height: 12),
            ],
            VerdictCard(
              verdict: _verdict,
              reporting: _reporting,
              onSeeEvidence: _openEvidence,
              onShareCorrection: () => unawaited(showCorrectionSheet(context, _verdict)),
              onReportForReview: _reported ? null : _report,
            ),
            if (_reported)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  l10n.reportedNote,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.labelSmall?.copyWith(color: FactifyColors.inkMuted),
                ),
              ),
          ],
        ),
      ),
      bottomNavigationBar: SafeArea(
        child: Container(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
          decoration: const BoxDecoration(
            color: Colors.white,
            border: Border(top: BorderSide(color: FactifyColors.line)),
          ),
          child: Row(
            children: [
              if (_canCheckAgain) ...[
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _checkAgain,
                    icon: const Icon(Icons.refresh_rounded),
                    label: Text(l10n.checkAgain),
                    style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(50)),
                  ),
                ),
                const SizedBox(width: 10),
              ],
              Expanded(
                child: FilledButton.icon(
                  onPressed: _newCheck,
                  icon: const Icon(Icons.add_rounded),
                  label: Text(l10n.newCheck),
                  style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(50)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
