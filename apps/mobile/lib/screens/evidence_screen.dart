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
library;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../l10n/app_localizations.dart';
import '../l10n/language_preference.dart';
import '../l10n/phrases.dart';
import '../models/verdict.dart';
import '../widgets/advisory_panel.dart';
import '../widgets/english_only_note.dart';
import '../widgets/language_menu.dart';

class EvidenceScreen extends StatelessWidget {
  const EvidenceScreen({super.key, required this.verdict, required this.language});

  final Verdict verdict;
  final LanguagePreference language;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.evidenceTitle),
        actions: [
          LanguageMenu(preference: language),
          const SizedBox(width: 12),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const EnglishOnlyNote(padding: EdgeInsets.only(bottom: 10)),
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
    final l10n = AppLocalizations.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
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
          Padding(
            padding: const EdgeInsets.only(bottom: 2),
            child: Text(
              // The component is named for a reader; its explanation is the
              // server's, and stays English until B5.
              '${l10n.strengthComponent(component.name)}: ${component.explanation}',
              style: muted,
            ),
          ),
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

/// One source card: publisher, date, excerpt, anchor and link.
class _EvidenceCard extends StatelessWidget {
  const _EvidenceCard({required this.evidence});

  final Evidence evidence;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final muted = theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final date = evidence.observedAt == null
        ? null
        : DateFormat('d MMM yyyy', l10n.localeName).format(evidence.observedAt!.toLocal());
    final anchor = l10n.describeAnchor(evidence.sourceAnchor);

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

class _CaseFooter extends StatelessWidget {
  const _CaseFooter({required this.verdict});

  final Verdict verdict;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final muted = theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(l10n.caseLabel(verdict.caseId), style: muted),
        Text(l10n.checkedIn(verdict.elapsedMs), style: muted),
        if (verdict.receiptUrl != null)
          TextButton.icon(
            onPressed: () =>
                launchUrl(Uri.parse(verdict.receiptUrl!), mode: LaunchMode.externalApplication),
            icon: const Icon(Icons.verified_outlined, size: 16),
            label: Text(l10n.verifyResult),
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
