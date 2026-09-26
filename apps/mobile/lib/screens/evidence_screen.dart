/// The sources screen: what was checked, what each claim came to, and the sources.
///
/// Replaces an evidence screen that showed everything the pipeline knew — tiers,
/// independent-origin counts, strength components, match thresholds — most of which
/// a person checking a forward does not need and could not act on. What stays up
/// front is what lets them trust the verdict or check it themselves: each claim with
/// its verdict, a plain reason, where their own message says it, and the sources
/// behind it with the sentence each was cited for. The rest — the timeline, whether
/// this was seen before, what was not checked, what Factify cannot establish — is one
/// tap away under "How we checked", not in the way.
///
/// There are no GlobalKeys here any more. They existed so a strength row could scroll
/// to its citation, and they were keyed by evidence id — so when the same page was
/// cited twice for one claim the screen crashed with "Duplicate keys found". The
/// server now cites each page once per claim, and nothing here needs a key at all.
library;

import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../l10n/app_localizations.dart';
import '../l10n/language_preference.dart';
import '../l10n/phrases.dart';
import '../models/submission.dart';
import '../models/verdict.dart';
import '../theme/colors.dart';
import '../widgets/action_style.dart';
import '../widgets/advisory_panel.dart';
import '../widgets/evidence_timeline.dart';
import '../widgets/language_menu.dart';
import '../widgets/source_tile.dart';
import '../widgets/teaching_line.dart';
import '../widgets/verdict_card.dart' show ConfidenceRing;

class EvidenceScreen extends StatelessWidget {
  const EvidenceScreen({
    super.key,
    required this.verdict,
    required this.language,
    this.submission,
    this.client,
  });

  final Verdict verdict;
  final LanguagePreference language;

  /// What was checked, when the screen was opened from a check in this session.
  /// Lets a claim be marked inside the reader's own words, and a picture be shown
  /// beside the earlier copy it matched.
  final Submission? submission;

  /// Used only to check the receipt. Optional so widget tests can render the
  /// screen without a server.
  final FactifyClient? client;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final theme = Theme.of(context);
    final style = ActionStyle.of(verdict.action, Brightness.light, l10n);

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.evidenceTitle),
        actions: [LanguageMenu(preference: language), const SizedBox(width: 12)],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 28),
          children: [
            _Header(verdict: verdict, style: style),
            const SizedBox(height: 20),
            Text(
              l10n.whatWeCheckedTitle,
              style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 10),
            if (verdict.claims.isEmpty)
              _Plain(text: l10n.unconfirmedBody)
            else
              for (final (index, claim) in verdict.claims.indexed) ...[
                if (index > 0) const SizedBox(height: 12),
                _ClaimCard(claim: claim, submission: submission),
              ],
            if (verdict.completenessNote != null) ...[
              const SizedBox(height: 12),
              _Plain(text: l10n.incompleteNote),
            ],
            const SizedBox(height: 16),
            _HowWeChecked(verdict: verdict),
            if (verdict.advisories.isNotEmpty) ...[
              const SizedBox(height: 12),
              AdvisoryPanel(advisories: verdict.advisories),
            ],
            const SizedBox(height: 20),
            _CaseFooter(verdict: verdict, client: client),
          ],
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.verdict, required this.style});

  final Verdict verdict;
  final ActionStyle style;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final confidence = verdict.confidence;
    final decided = verdict.factVerdict.isDecided;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: style.container,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Row(
        children: [
          Icon(style.icon, color: style.tone, size: 40),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  style.headline,
                  style: theme.textTheme.headlineSmall?.copyWith(color: style.onContainer),
                ),
                const SizedBox(height: 2),
                Text(
                  // The explanation is in the claim cards below; saying it here
                  // too put the same paragraph on screen twice.
                  style.subhead,
                  style: theme.textTheme.bodySmall?.copyWith(color: style.onContainer),
                ),
              ],
            ),
          ),
          if (decided && confidence != null) ...[
            const SizedBox(width: 10),
            ConfidenceRing(value: confidence, tone: style.tone, size: 52),
          ],
        ],
      ),
    );
  }
}

/// One claim: what it says, what the sources made of it, and the sources.
class _ClaimCard extends StatelessWidget {
  const _ClaimCard({required this.claim, required this.submission});

  final Claim claim;
  final Submission? submission;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final colour = ActionStyle.forStatus(claim.status);
    final label = switch (claim.status) {
      ClaimStatus.supported => l10n.headlineSafeToShare,
      ClaimStatus.contradicted => l10n.headlineDoNotShare,
      ClaimStatus.misleadingContext => l10n.headlineShareWithContext,
      ClaimStatus.unverified when claim.wasNotSearched => l10n.statusNotChecked,
      ClaimStatus.unverified => l10n.headlineSendToReview,
    };
    final confidence = claim.confidence;
    final explanation = claim.explanation;
    final anchor = claim.inputAnchor;
    final technique = techniqueFor(claim);
    final picture = submission?.thumbnail;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              claim.text,
              style: theme.textTheme.bodyLarge?.copyWith(
                fontWeight: FontWeight.w600,
                height: 1.35,
              ),
            ),
            if (anchor != null) _InputAnchorBlock(anchor: anchor, submission: submission),
            const SizedBox(height: 10),
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                  decoration: BoxDecoration(
                    color: colour.withValues(alpha: 0.10),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    label,
                    style: TextStyle(color: colour, fontWeight: FontWeight.w800, fontSize: 13),
                  ),
                ),
                if (claim.isDecisive && confidence != null) ...[
                  const SizedBox(width: 8),
                  Text(
                    l10n.confidence(confidence),
                    style: theme.textTheme.labelMedium?.copyWith(color: FactifyColors.inkMuted),
                  ),
                ],
              ],
            ),
            const SizedBox(height: 10),
            Text(
              claim.isDecisive && explanation != null ? explanation : _whyUndecided(claim, l10n),
              style: theme.textTheme.bodySmall,
            ),
            if (technique != null) ...[
              const SizedBox(height: 12),
              TeachingLine(technique: technique),
            ],
            if (claim.evidence.isNotEmpty) ...[
              const SizedBox(height: 12),
              for (final (index, item) in claim.evidence.indexed) ...[
                if (index > 0) const SizedBox(height: 8),
                if (item.isMediaMatch && picture != null) ...[
                  _MediaMatchPreview(picture: picture),
                  const SizedBox(height: 8),
                ],
                SourceTile(evidence: item),
              ],
            ],
          ],
        ),
      ),
    );
  }
}

/// Why a claim has no verdict, in the terms of what was actually done for it.
///
/// "We couldn't find enough reliable sources" was said of every undecided claim,
/// including ones that were never searched: a check searches its three most
/// important claims, and on a Hindu article of four the fourth was below the cap
/// and told the reader no source addressed it.
String _whyUndecided(Claim claim, AppLocalizations l10n) {
  final taking = claim.evidence.where((e) => e.supports || e.contradicts).length;
  final looked = claim.sourcesLookedAt ?? 0;
  return switch (claim.search) {
    'not_searched' => l10n.claimNotSearched,
    'timed_out' when taking == 0 => l10n.claimTimedOut,
    'searched' when taking == 1 => l10n.claimOneSource,
    'searched' when taking == 0 && looked > 0 => l10n.claimNoSources(looked),
    'searched' when taking == 0 => l10n.claimNothingFound,
    _ => l10n.unconfirmedBody,
  };
}

/// Where the claim sits in what was submitted: the reader's own words with the
/// span marked when the message is at hand, or its position otherwise.
class _InputAnchorBlock extends StatelessWidget {
  const _InputAnchorBlock({required this.anchor, required this.submission});

  final InputAnchor anchor;
  final Submission? submission;

  /// Characters of the message kept either side of the marked span.
  static const int _surrounding = 40;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final text = submission?.text;
    final start = anchor.charStart;
    final end = anchor.charEnd;

    final Widget detail;
    if (text != null && start != null && end != null && 0 <= start && start < end && end <= text.length) {
      final from = math.max(0, start - _surrounding);
      final to = math.min(text.length, end + _surrounding);
      detail = Text.rich(
        TextSpan(
          children: [
            if (from > 0) const TextSpan(text: '…'),
            TextSpan(text: text.substring(from, start)),
            TextSpan(
              text: text.substring(start, end),
              style: const TextStyle(
                backgroundColor: FactifyColors.emeraldSoft,
                color: FactifyColors.emeraldDeep,
                fontWeight: FontWeight.w600,
              ),
            ),
            TextSpan(text: text.substring(end, to)),
            if (to < text.length) const TextSpan(text: '…'),
          ],
        ),
        style: theme.textTheme.bodySmall,
      );
    } else {
      final position = l10n.describeInputAnchor(anchor);
      if (position == null) return const SizedBox.shrink();
      detail = Text(position, style: theme.textTheme.bodySmall);
    }

    return Container(
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: FactifyColors.ground,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            l10n.inputAnchorLabel,
            style: theme.textTheme.labelSmall?.copyWith(color: FactifyColors.inkMuted),
          ),
          const SizedBox(height: 4),
          detail,
        ],
      ),
    );
  }
}

/// The submitted picture, beside the finding that it was published before.
class _MediaMatchPreview extends StatelessWidget {
  const _MediaMatchPreview({required this.picture});

  final Uint8List picture;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);

    return Row(
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(10),
          child: Image.memory(
            picture,
            width: 64,
            height: 64,
            fit: BoxFit.cover,
            // A preview that fails to decode must not take the evidence with it.
            errorBuilder: (_, _, _) => const SizedBox(width: 64, height: 64),
          ),
        ),
        const SizedBox(width: 10),
        const Icon(Icons.compare_arrows_rounded, color: FactifyColors.inkMuted),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                l10n.mediaMatchYours,
                style: theme.textTheme.labelSmall?.copyWith(color: FactifyColors.inkMuted),
              ),
              const SizedBox(height: 2),
              Text(l10n.mediaMatchEarlier, style: theme.textTheme.titleSmall),
            ],
          ),
        ),
      ],
    );
  }
}

/// Everything a curious reader may want and a hurried one does not, folded away.
class _HowWeChecked extends StatelessWidget {
  const _HowWeChecked({required this.verdict});

  final Verdict verdict;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final heading = theme.textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w700);
    final body = theme.textTheme.bodySmall;
    final recurrence = verdict.recurrence;
    final provenance = verdict.mediaProvenance;

    return Card(
      child: Theme(
        data: theme.copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          shape: const RoundedRectangleBorder(),
          collapsedShape: const RoundedRectangleBorder(),
          leading: const Icon(Icons.info_outline_rounded, color: FactifyColors.emeraldDark),
          title: Text(
            l10n.howWeCheckedTitle,
            style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
          ),
          childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          expandedCrossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(l10n.howWeCheckedBody, style: body),
            if (recurrence != null) ...[
              const SizedBox(height: 14),
              Text(l10n.historyCardTitle, style: heading),
              const SizedBox(height: 4),
              Text(recurrence.summary, style: body),
              if (recurrence.hasContradictoryCaptions)
                Text(l10n.recurrenceCaptions(recurrence.distinctCaptions), style: body),
            ],
            if (provenance != null) ...[
              const SizedBox(height: 14),
              Text(l10n.contentCredentials, style: heading),
              const SizedBox(height: 4),
              Text(provenance.summary, style: body),
            ],
            if (verdict.skipped.isNotEmpty) ...[
              const SizedBox(height: 14),
              Text(l10n.notCheckedTitle, style: heading),
              const SizedBox(height: 4),
              for (final item in verdict.skipped)
                Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text('${item.check}: ${item.reason}', style: body),
                ),
            ],
            EvidenceTimeline(verdict: verdict, padding: const EdgeInsets.only(top: 14)),
            const SizedBox(height: 14),
            Text(l10n.limitsTitle, style: heading),
            const SizedBox(height: 6),
            for (final line in [
              l10n.limitAi,
              l10n.limitUnreported,
              l10n.limitPrivate,
              l10n.limitIntent,
            ])
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text('•  $line', style: body),
              ),
          ],
        ),
      ),
    );
  }
}

class _Plain extends StatelessWidget {
  const _Plain({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: FactifyColors.ground,
      borderRadius: BorderRadius.circular(14),
    ),
    child: Text(text, style: Theme.of(context).textTheme.bodySmall),
  );
}

/// The case identifier, how long the check took, and the receipt behind it.
///
/// "Verify this result" checks the receipt **in the app** rather than opening it
/// elsewhere. The first version handed `receipt_url` straight to `launchUrl`, and
/// the server sends that as a path (`/v1/receipts/rcpt:...`), not an absolute URL:
/// Android found no activity for a bare path, threw `ACTIVITY_NOT_FOUND`, and
/// because nothing caught it the button did nothing at all on a real device. The
/// host tests missed it because they call [FactifyClient.getReceipt], which resolves
/// the path against the base URL — so the tested path and the shipped path were
/// different code.
///
/// Checking here is also the better answer. A receipt is an integrity claim about
/// the evidence, and what a reader needs is whether it held, not a page of JSON.
class _CaseFooter extends StatefulWidget {
  const _CaseFooter({required this.verdict, this.client});

  final Verdict verdict;

  /// Supplied by the screen that opened this one. Null in widget tests, which
  /// render the footer without ever pressing the button.
  final FactifyClient? client;

  @override
  State<_CaseFooter> createState() => _CaseFooterState();
}

class _CaseFooterState extends State<_CaseFooter> {
  /// Null until the button is pressed; then a sentence to show underneath it.
  String? _outcome;
  bool _verified = false;
  bool _checking = false;

  /// Created only if the screen did not pass one, and disposed only if created
  /// here — closing a client the app still uses would break every later request.
  FactifyClient? _owned;

  @override
  void dispose() {
    _owned?.close();
    super.dispose();
  }

  Future<void> _check() async {
    final l10n = AppLocalizations.of(context);
    final client = widget.client ?? (_owned ??= FactifyClient());

    setState(() {
      _checking = true;
      _outcome = null;
    });

    String message;
    var verified = false;
    try {
      final receipt = await client.getReceipt(widget.verdict.receiptUrl!);
      if (receipt == null) {
        message = l10n.receiptMissing;
      } else {
        verified = receipt.verified;
        message = verified ? l10n.receiptVerified : l10n.receiptFailed;
      }
    } on ApiFailure catch (failure) {
      message = l10n.describeFailure(failure);
    }

    if (!mounted) return;
    setState(() {
      _checking = false;
      _verified = verified;
      _outcome = message;
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final muted = theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final outcome = _outcome;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(l10n.caseLabel(widget.verdict.caseId), style: muted),
        Text(l10n.checkedIn(widget.verdict.elapsedMs), style: muted),
        if (widget.verdict.receiptUrl != null) ...[
          TextButton.icon(
            onPressed: _checking ? null : _check,
            icon: _checking
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.verified_outlined, size: 16),
            label: Text(_checking ? l10n.receiptChecking : l10n.verifyResult),
          ),
          if (outcome != null)
            Padding(
              padding: const EdgeInsets.only(left: 12, bottom: 8),
              child: Text(
                outcome,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: _verified ? theme.colorScheme.primary : theme.colorScheme.error,
                ),
              ),
            ),
        ],
      ],
    );
  }
}
