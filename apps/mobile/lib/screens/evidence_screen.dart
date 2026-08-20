/// The evidence screen (M44).
///
/// Everything the verdict rests on, plus an explicit statement of what it does
/// not cover. The limits block is not a disclaimer bolted on at the end — it is
/// the difference between a tool people can calibrate their trust against and
/// one they either over-trust or abandon at the first miss.
library;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/verdict.dart';
import '../widgets/advisory_panel.dart';

class EvidenceScreen extends StatelessWidget {
  const EvidenceScreen({super.key, required this.verdict});

  final Verdict verdict;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Evidence')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          for (final claim in verdict.claims) _ClaimSection(claim: claim),
          if (verdict.allEvidence.isEmpty) const _NoEvidenceBlock(),
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
          _CaseFooter(verdict: verdict),
        ],
      ),
    );
  }
}

class _ClaimSection extends StatelessWidget {
  const _ClaimSection({required this.claim});

  final Claim claim;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('The claim', style: theme.textTheme.labelMedium),
                const SizedBox(height: 4),
                Text(claim.text, style: theme.textTheme.bodyLarge),
                const SizedBox(height: 8),
                Text(claim.reason, style: theme.textTheme.bodySmall),
                const SizedBox(height: 10),
                _StrengthBar(strength: claim.strength),
              ],
            ),
          ),
        ),
        for (final evidence in claim.evidence) _EvidenceCard(evidence: evidence),
        const SizedBox(height: 8),
      ],
    );
  }
}

/// The explainable score and its components.
///
/// Every component states why it contributed, because a number without a reason
/// is exactly the model-confidence figure this product refuses to show.
class _StrengthBar extends StatelessWidget {
  const _StrengthBar({required this.strength});

  final Strength strength;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              'Evidence strength: ${strength.band.toLowerCase()}',
              style: theme.textTheme.labelMedium,
            ),
            const Spacer(),
            Text(strength.score.toStringAsFixed(2), style: theme.textTheme.labelMedium),
          ],
        ),
        const SizedBox(height: 4),
        LinearProgressIndicator(value: strength.score.clamp(0, 1)),
        const SizedBox(height: 6),
        for (final component in strength.components)
          Padding(
            padding: const EdgeInsets.only(bottom: 2),
            child: Text(
              '${component.name}: ${component.explanation}',
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
        if (strength.advisoryExcluded.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(
              'Excluded from this score: ${strength.advisoryExcluded.join(', ')}',
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
      ],
    );
  }
}

/// One source card: publisher, date, excerpt, anchor and link.
class _EvidenceCard extends StatelessWidget {
  const _EvidenceCard({required this.evidence});

  final Evidence evidence;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final date = evidence.observedAt == null
        ? null
        : DateFormat('d MMM yyyy').format(evidence.observedAt!.toLocal());

    return Card(
      margin: const EdgeInsets.only(top: 6),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                _DirectionChip(direction: evidence.direction),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    evidence.tierLabel,
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (evidence.publisher != null)
              Text(evidence.publisher!, style: theme.textTheme.titleSmall),
            if (date != null)
              Text(
                date,
                style: theme.textTheme.labelSmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            const SizedBox(height: 8),
            // The quoted passage, which is what makes this a citation rather
            // than a link. An evidence row without it is a search result.
            // Styled as a blockquote — the accent bar says "this text is the
            // source speaking, not us".
            Container(
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.6),
                borderRadius: const BorderRadius.only(
                  topRight: Radius.circular(10),
                  bottomRight: Radius.circular(10),
                ),
                border: Border(
                  left: BorderSide(color: theme.colorScheme.primary, width: 3),
                ),
              ),
              child: Text(
                '“${evidence.sourceExcerpt}”',
                style: theme.textTheme.bodySmall?.copyWith(height: 1.45),
              ),
            ),
            if (evidence.sourceAnchor.describe != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  'Found at ${evidence.sourceAnchor.describe}',
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ),
            const SizedBox(height: 6),
            // How the match was judged, so a reader can recompute it instead of
            // taking our word for the quality label.
            Text(
              '${evidence.matchBasis.metric} '
              '${evidence.matchBasis.value.toStringAsFixed(3)} '
              '(threshold ${evidence.matchBasis.threshold.toStringAsFixed(3)})',
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 6),
            TextButton.icon(
              onPressed: () =>
                  launchUrl(Uri.parse(evidence.citationUrl), mode: LaunchMode.externalApplication),
              icon: const Icon(Icons.open_in_new, size: 16),
              label: const Text('Open source'),
            ),
          ],
        ),
      ),
    );
  }
}

class _DirectionChip extends StatelessWidget {
  const _DirectionChip({required this.direction});

  final String direction;

  @override
  Widget build(BuildContext context) {
    final (label, colour) = switch (direction) {
      'supports' => ('Supports', const Color(0xFF2E7D32)),
      'contradicts' => ('Contradicts', const Color(0xFFC62828)),
      'risk_signal' => ('Risk signal', const Color(0xFFEF6C00)),
      _ => ('Context', const Color(0xFF01579B)),
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
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('No citable source was found', style: theme.textTheme.titleSmall),
            const SizedBox(height: 6),
            Text(
              'This does not mean the content is false. It means nothing we could '
              'cite either supports or contradicts it, so Facify did not decide.',
              style: theme.textTheme.bodySmall,
            ),
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
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('History', style: theme.textTheme.titleSmall),
            const SizedBox(height: 6),
            Text(recurrence.summary, style: theme.textTheme.bodySmall),
            if (recurrence.hasContradictoryCaptions) ...[
              const SizedBox(height: 8),
              Text(
                'The same media has carried ${recurrence.distinctCaptions} different '
                'captions. An authentic photograph does not usually acquire several '
                'mutually exclusive stories.',
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
            Text('Content credentials', style: theme.textTheme.titleSmall),
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
            Text('What could not be checked', style: theme.textTheme.titleSmall),
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

/// The "what Facify cannot establish" block.
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

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('What Facify cannot establish', style: theme.textTheme.titleSmall),
            const SizedBox(height: 8),
            ...[
              'Whether an image or video was generated by AI. No detector is '
                  'reliable enough to say so, and we do not pretend otherwise.',
              'Whether something unreported is false. Absence of coverage is not '
                  'evidence either way.',
              'Anything about private content, or claims no published source has '
                  'addressed.',
              'Intent. We can show what a source said and when, not why someone '
                  'shared it.',
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

class _CaseFooter extends StatelessWidget {
  const _CaseFooter({required this.verdict});

  final Verdict verdict;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Case ${verdict.caseId}', style: muted),
        Text('Checked in ${verdict.elapsedMs} ms', style: muted),
        if (verdict.receiptUrl != null)
          TextButton.icon(
            onPressed: () =>
                launchUrl(Uri.parse(verdict.receiptUrl!), mode: LaunchMode.externalApplication),
            icon: const Icon(Icons.verified_outlined, size: 16),
            label: const Text('Verify this result'),
          ),
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
    final (label, detail) = switch (risk) {
      'HIGH' => (
        'Publisher has a high risk profile',
        'Recently registered, or with a record of unreliable material. This '
            'describes the publisher, not this claim.',
      ),
      'MEDIUM' => (
        'Publisher has a mixed record',
        'Some signals worth noting about the source. This describes the '
            'publisher, not this claim.',
      ),
      'LOW' => (
        'Publisher has an established record',
        'No adverse signals about the source. This is not evidence that the '
            'claim itself is true.',
      ),
      _ => ('Publisher risk not assessed', 'Nothing is known either way.'),
    };

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
                Expanded(child: Text(label, style: theme.textTheme.titleSmall)),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              detail,
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
