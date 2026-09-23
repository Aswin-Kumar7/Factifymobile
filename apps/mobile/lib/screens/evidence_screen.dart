/// The evidence screen (M44).
///
/// Everything the verdict rests on, plus an explicit statement of what it does
/// not cover. The limits block is not a disclaimer bolted on at the end — it is
/// the difference between a tool people can calibrate their trust against and
/// one they either over-trust or abandon at the first miss.
///
/// M44 puts the language toggle on this screen. Someone reading the evidence is
/// the person most likely to want it in the other language, and sending them
/// back to the home screen to switch would lose their place.
///
/// PLAN 1.7.4 and 1.7.7 add the rest of what is here: where the claim sits in the
/// submission, the technique it fits, the timeline behind the verdict, the
/// submitted picture beside a media match, and strength rows that lead to the
/// citations they came from. Each renders only from data the response carries.
/// Several of those fields are not sent yet (B6–B10 in docs/hackathon-workflow.md),
/// and a missing field shows nothing rather than a guess.
library;

import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/client.dart';
import '../l10n/app_localizations.dart';
import '../l10n/language_preference.dart';
import '../l10n/phrases.dart';
import '../models/submission.dart';
import '../models/verdict.dart';
import '../widgets/advisory_panel.dart';
import '../widgets/english_only_note.dart';
import '../widgets/evidence_timeline.dart';
import '../widgets/language_menu.dart';
import '../widgets/teaching_line.dart';

class EvidenceScreen extends StatefulWidget {
  const EvidenceScreen({
    super.key,
    required this.verdict,
    required this.language,
    this.submission,
    this.client,
  });

  final Verdict verdict;
  final LanguagePreference language;

  /// Used only to check the receipt. Optional so widget tests can render the
  /// screen without a server; the button is the one thing that needs it.
  final FactifyClient? client;

  /// What was checked, when the screen was opened from a check in this session.
  /// Lets a claim's anchor be shown inside the reader's own words, and a media
  /// match beside the picture they submitted.
  final Submission? submission;

  @override
  State<EvidenceScreen> createState() => _EvidenceScreenState();
}

class _EvidenceScreenState extends State<EvidenceScreen> {
  /// One key per evidence card, so a strength row can bring its citation into view.
  final Map<String, GlobalKey> _cardKeys = {};
  String? _highlighted;
  Timer? _highlightTimer;

  GlobalKey _keyFor(Evidence evidence) => _cardKeys.putIfAbsent(evidence.id, GlobalKey.new);

  /// Scrolls to the first card citing one of [urls], and marks it for a moment.
  void _showCitations(List<String> urls) {
    final target = widget.verdict.allEvidence.where((e) => urls.contains(e.citationUrl)).firstOrNull;
    final cardContext = target == null ? null : _cardKeys[target.id]?.currentContext;
    if (target == null || cardContext == null) return;

    unawaited(
      Scrollable.ensureVisible(
        cardContext,
        duration: const Duration(milliseconds: 350),
        alignment: 0.1,
      ),
    );
    setState(() => _highlighted = target.id);
    _highlightTimer?.cancel();
    _highlightTimer = Timer(const Duration(seconds: 2), () {
      if (mounted) setState(() => _highlighted = null);
    });
  }

  @override
  void dispose() {
    _highlightTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final verdict = widget.verdict;

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.evidenceTitle),
        actions: [
          LanguageMenu(preference: widget.language),
          const SizedBox(width: 12),
        ],
      ),
      // A column rather than a lazy list: every card must exist for a strength row
      // to scroll to it, and this screen is a handful of cards, not a feed.
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const EnglishOnlyNote(padding: EdgeInsets.only(bottom: 10)),
            for (final claim in verdict.claims)
              _ClaimSection(
                claim: claim,
                submission: widget.submission,
                highlighted: _highlighted,
                keyFor: _keyFor,
                onShowCitations: _showCitations,
              ),
            if (verdict.allEvidence.isEmpty) const _NoEvidenceBlock(),
            EvidenceTimeline(verdict: verdict, padding: const EdgeInsets.only(top: 8)),
            if (verdict.recurrence != null && verdict.recurrence!.timesSeen > 0) ...[
              const SizedBox(height: 8),
              _RecurrenceCard(recurrence: verdict.recurrence!),
            ],
            if (verdict.mediaProvenance != null) ...[
              const SizedBox(height: 8),
              _ProvenanceCard(provenance: verdict.mediaProvenance!),
            ],
            if (verdict.sourceRisk != 'UNKNOWN') ...[
              const SizedBox(height: 8),
              _SourceRiskCard(risk: verdict.sourceRisk),
            ],
            if (verdict.skipped.isNotEmpty) ...[
              const SizedBox(height: 8),
              _SkippedCard(skipped: verdict.skipped),
            ],
            const SizedBox(height: 8),
            _LimitsBlock(verdict: verdict),
            const SizedBox(height: 8),
            // Last, and visually quietest, by design.
            AdvisoryPanel(advisories: verdict.advisories),
            const SizedBox(height: 24),
            _CaseFooter(verdict: verdict, client: widget.client),
          ],
        ),
      ),
    );
  }
}

class _ClaimSection extends StatelessWidget {
  const _ClaimSection({
    required this.claim,
    required this.submission,
    required this.highlighted,
    required this.keyFor,
    required this.onShowCitations,
  });

  final Claim claim;
  final Submission? submission;
  final String? highlighted;
  final GlobalKey Function(Evidence evidence) keyFor;
  final void Function(List<String> urls) onShowCitations;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final anchor = claim.inputAnchor;
    final technique = techniqueFor(claim);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(l10n.theClaim, style: theme.textTheme.labelMedium),
                const SizedBox(height: 4),
                Text(claim.text, style: theme.textTheme.bodyLarge),
                if (anchor != null) ...[
                  const SizedBox(height: 8),
                  _InputAnchorBlock(anchor: anchor, submission: submission),
                ],
                const SizedBox(height: 8),
                Text(claim.reason, style: theme.textTheme.bodySmall),
                const SizedBox(height: 10),
                _StrengthBar(strength: claim.strength, onShowCitations: onShowCitations),
                if (technique != null) ...[
                  const SizedBox(height: 12),
                  TeachingLine(technique: technique),
                ],
              ],
            ),
          ),
        ),
        for (final evidence in claim.evidence)
          _EvidenceCard(
            key: keyFor(evidence),
            evidence: evidence,
            highlighted: evidence.id == highlighted,
            thumbnail: evidence.isMediaMatch ? submission?.thumbnail : null,
          ),
        const SizedBox(height: 8),
      ],
    );
  }
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
    final scheme = theme.colorScheme;
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
              style: TextStyle(
                backgroundColor: scheme.tertiaryContainer,
                color: scheme.onTertiaryContainer,
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
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            l10n.inputAnchorLabel,
            style: theme.textTheme.labelSmall?.copyWith(color: scheme.onSurfaceVariant),
          ),
          const SizedBox(height: 4),
          detail,
        ],
      ),
    );
  }
}

/// The explainable score and its components.
///
/// Every component states why it contributed, because a number without a reason
/// is exactly the model-confidence figure this product refuses to show.
class _StrengthBar extends StatelessWidget {
  const _StrengthBar({required this.strength, required this.onShowCitations});

  final Strength strength;
  final void Function(List<String> urls) onShowCitations;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final muted = theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                l10n.evidenceStrength(l10n.strengthBand(strength.band.toLowerCase())),
                style: theme.textTheme.labelMedium,
              ),
            ),
            Text(strength.score.toStringAsFixed(2), style: theme.textTheme.labelMedium),
          ],
        ),
        const SizedBox(height: 4),
        LinearProgressIndicator(value: strength.score.clamp(0, 1)),
        const SizedBox(height: 6),
        for (final component in strength.components)
          _ComponentRow(component: component, onShowCitations: onShowCitations),
        if (strength.advisoryExcluded.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(
              l10n.excludedFromScore(strength.advisoryExcluded.join(', ')),
              style: muted,
            ),
          ),
      ],
    );
  }
}

/// One component of the score, leading to its citations when it has any.
///
/// Every component tappable through to its citations is the plan (1.7.7). The
/// server records which citations produced each component but does not send them
/// yet (B9), so until it does a row is plain text rather than a link to nothing.
class _ComponentRow extends StatelessWidget {
  const _ComponentRow({required this.component, required this.onShowCitations});

  final StrengthComponent component;
  final void Function(List<String> urls) onShowCitations;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final muted = theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    // The component is named for a reader; its explanation is the server's, and
    // stays English until B5.
    final label = Text(
      '${l10n.strengthComponent(component.name)}: ${component.explanation}',
      style: muted,
    );

    if (component.citations.isEmpty) {
      return Padding(padding: const EdgeInsets.only(bottom: 2), child: label);
    }

    return InkWell(
      onTap: () => onShowCitations(component.citations),
      borderRadius: BorderRadius.circular(6),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          children: [
            Expanded(child: label),
            const SizedBox(width: 6),
            Icon(Icons.link, size: 14, color: theme.colorScheme.primary),
            const SizedBox(width: 2),
            Text(
              l10n.strengthComponentCitations(component.citations.length),
              style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.primary),
            ),
          ],
        ),
      ),
    );
  }
}

/// One source card: publisher, date, excerpt, anchor and link.
class _EvidenceCard extends StatelessWidget {
  const _EvidenceCard({
    super.key,
    required this.evidence,
    this.highlighted = false,
    this.thumbnail,
  });

  final Evidence evidence;

  /// Marked briefly after a strength row led here, so the eye lands on it.
  final bool highlighted;

  /// The submitted picture, shown beside a media match. There is no picture of
  /// the earlier publication to put next to it: the contract carries its page,
  /// not the image (B10).
  final Uint8List? thumbnail;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final muted = theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final date = evidence.observedAt == null
        ? null
        : DateFormat('d MMM yyyy', l10n.localeName).format(evidence.observedAt!.toLocal());
    final anchor = l10n.describeAnchor(evidence.sourceAnchor);
    final picture = thumbnail;

    return Card(
      margin: const EdgeInsets.only(top: 6),
      shape: highlighted
          ? RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(14),
              side: BorderSide(color: theme.colorScheme.primary, width: 2),
            )
          : null,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (picture != null) ...[
              _MediaMatchPreview(picture: picture),
              const SizedBox(height: 10),
            ],
            Row(
              children: [
                _DirectionChip(direction: evidence.direction),
                const SizedBox(width: 6),
                Expanded(
                  // What the tier means, in words rather than a letter nobody
                  // can decode.
                  child: Text(l10n.tierLabel(evidence.tier), style: muted),
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (evidence.publisher != null)
              Text(evidence.publisher!, style: theme.textTheme.titleSmall),
            if (date != null) Text(date, style: muted),
            const SizedBox(height: 8),
            // The quoted passage, which is what makes this a citation rather
            // than a link. An evidence row without it is a search result.
            // Styled as a blockquote — the accent bar says "this text is the
            // source speaking, not us". The bar sits on the reading-start edge,
            // so it stays on the correct side in a right-to-left layout.
            Container(
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.6),
                borderRadius: const BorderRadiusDirectional.only(
                  topEnd: Radius.circular(10),
                  bottomEnd: Radius.circular(10),
                ),
                border: BorderDirectional(
                  start: BorderSide(color: theme.colorScheme.primary, width: 3),
                ),
              ),
              child: Text(
                '“${evidence.sourceExcerpt}”',
                style: theme.textTheme.bodySmall?.copyWith(height: 1.45),
              ),
            ),
            if (anchor != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(anchor, style: muted),
              ),
            const SizedBox(height: 6),
            // How the match was judged, so a reader can recompute it instead of
            // taking our word for the quality label.
            Text(
              l10n.matchBasis(
                evidence.matchBasis.metric,
                evidence.matchBasis.value.toStringAsFixed(3),
                evidence.matchBasis.threshold.toStringAsFixed(3),
              ),
              style: muted,
            ),
            const SizedBox(height: 6),
            TextButton.icon(
              onPressed: () =>
                  launchUrl(Uri.parse(evidence.citationUrl), mode: LaunchMode.externalApplication),
              icon: const Icon(Icons.open_in_new, size: 16),
              label: Text(l10n.openSource),
            ),
          ],
        ),
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
    final muted = theme.colorScheme.onSurfaceVariant;
    final l10n = AppLocalizations.of(context);

    return Row(
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: Image.memory(
            picture,
            width: 72,
            height: 72,
            fit: BoxFit.cover,
            // A preview that fails to decode must not take the evidence with it.
            errorBuilder: (_, _, _) => const SizedBox(width: 72, height: 72),
          ),
        ),
        const SizedBox(width: 10),
        Icon(Icons.compare_arrows, color: muted),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(l10n.mediaMatchYours, style: theme.textTheme.labelSmall?.copyWith(color: muted)),
              const SizedBox(height: 2),
              Text(l10n.mediaMatchEarlier, style: theme.textTheme.titleSmall),
            ],
          ),
        ),
      ],
    );
  }
}

class _DirectionChip extends StatelessWidget {
  const _DirectionChip({required this.direction});

  final String direction;

  @override
  Widget build(BuildContext context) {
    final label = AppLocalizations.of(context).directionLabel(direction);
    final colour = switch (direction) {
      'supports' => const Color(0xFF2E7D32),
      'contradicts' => const Color(0xFFC62828),
      'risk_signal' => const Color(0xFFEF6C00),
      _ => const Color(0xFF01579B),
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(color: colour, borderRadius: BorderRadius.circular(10)),
      child: Text(
        label,
        style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600),
      ),
    );
  }
}

/// Shown when there is no evidence at all.
///
/// Phrased as an absence of findings rather than a finding of absence, because
/// those are different and only one of them is true.
class _NoEvidenceBlock extends StatelessWidget {
  const _NoEvidenceBlock();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(l10n.noEvidenceTitle, style: theme.textTheme.titleSmall),
            const SizedBox(height: 6),
            Text(l10n.noEvidenceBody, style: theme.textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}

class _RecurrenceCard extends StatelessWidget {
  const _RecurrenceCard({required this.recurrence});

  final Recurrence recurrence;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(l10n.historyCardTitle, style: theme.textTheme.titleSmall),
            const SizedBox(height: 6),
            Text(recurrence.summary, style: theme.textTheme.bodySmall),
            if (recurrence.hasContradictoryCaptions) ...[
              const SizedBox(height: 8),
              Text(
                l10n.recurrenceCaptions(recurrence.distinctCaptions),
                style: theme.textTheme.bodySmall,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ProvenanceCard extends StatelessWidget {
  const _ProvenanceCard({required this.provenance});

  final MediaProvenance provenance;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              AppLocalizations.of(context).contentCredentials,
              style: theme.textTheme.titleSmall,
            ),
            const SizedBox(height: 6),
            Text(provenance.summary, style: theme.textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}

class _SkippedCard extends StatelessWidget {
  const _SkippedCard({required this.skipped});

  final List<SkippedCheck> skipped;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              AppLocalizations.of(context).notCheckedTitle,
              style: theme.textTheme.titleSmall,
            ),
            const SizedBox(height: 6),
            for (final item in skipped)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text('${item.check}: ${item.reason}', style: theme.textTheme.bodySmall),
              ),
          ],
        ),
      ),
    );
  }
}

/// The "what Factify cannot establish" block.
///
/// Fixed text, always shown. Stating the limits up front is what lets someone
/// calibrate how much to rely on a result, and a tool that hides them gets
/// abandoned wholesale the first time it misses something.
class _LimitsBlock extends StatelessWidget {
  const _LimitsBlock({required this.verdict});

  final Verdict verdict;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(l10n.limitsTitle, style: theme.textTheme.titleSmall),
            const SizedBox(height: 8),
            ...[
              l10n.limitAi,
              l10n.limitUnreported,
              l10n.limitPrivate,
              l10n.limitIntent,
            ].map(
              (line) => Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('- '),
                    Expanded(child: Text(line, style: theme.textTheme.bodySmall)),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
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

/// What is known about the publisher, kept apart from what is known about the claim.
///
/// Rule 6 in the verdict engine caps a source-risk-only case at abstention, and the
/// wording here matches that: a risky publisher is a reason to look harder, never a
/// finding that the content is false. Presenting it as a verdict would let the
/// messenger decide the message.
class _SourceRiskCard extends StatelessWidget {
  const _SourceRiskCard({required this.risk});

  final String risk;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.storefront_outlined, size: 18, color: theme.colorScheme.onSurfaceVariant),
                const SizedBox(width: 8),
                Expanded(child: Text(l10n.sourceRiskTitle(risk), style: theme.textTheme.titleSmall)),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              l10n.sourceRiskDetail(risk),
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
