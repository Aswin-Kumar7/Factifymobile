/// The result card: status, one-line explanation, reasons, three actions.
///
/// The colour and wording rules here are the design law made visible:
///
///   * Abstention is never styled as failure. `SEND_TO_REVIEW` means the system
///     correctly refused to decide, which is the product working. Painting it
///     red would teach people that "we don't know" and "this is false" are the
///     same answer.
///   * `SAFE_TO_SHARE` is not green-ticked as "true". The strongest honest
///     phrasing is that nothing contradicts it and sources agree.
///   * The retrieval time is always shown. A verdict without it is a claim about
///     the present made from evidence about the past.
///
/// Visually: soft tinted surfaces rather than solid colour banners. The solid
/// banners shouted at maximum contrast whatever the verdict, so a calm abstention
/// and a hard contradiction had the same visual temperature. A tint carries the
/// same semantic colour at conversational volume, and the wording does the rest.
library;

import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/verdict.dart';
import 'action_style.dart';
import 'english_only_note.dart';

class VerdictCard extends StatelessWidget {
  const VerdictCard({
    super.key,
    required this.verdict,
    required this.onSeeEvidence,
    required this.onShareCorrection,
    required this.onReportForReview,
    this.reporting = false,
  });

  final Verdict verdict;
  final VoidCallback onSeeEvidence;
  final VoidCallback onShareCorrection;
  final VoidCallback? onReportForReview;

  /// True while a report is in flight, so the button can say so instead of
  /// appearing to do nothing.
  final bool reporting;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final style = ActionStyle.of(verdict.action, theme.brightness, l10n);
    final citations = verdict.allEvidence.length;

    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // The tinted verdict header.
          Container(
            color: style.container,
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: style.tone.withValues(alpha: 0.16),
                        shape: BoxShape.circle,
                      ),
                      child: Icon(style.icon, color: style.onContainer, size: 22),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            style.headline,
                            style: theme.textTheme.titleMedium?.copyWith(
                              color: style.onContainer,
                              fontWeight: FontWeight.w700,
                              height: 1.2,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            style.subhead,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: style.onContainer.withValues(alpha: 0.85),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    _MetaChip(
                      icon: Icons.receipt_long_outlined,
                      label: l10n.citationCount(citations),
                      tone: style.onContainer,
                    ),
                    // Stated in words, not implied by a bare date. The redesign
                    // reduced this to "14 Sep, 10:49", which reads as when the
                    // card was drawn; a verdict without its retrieval time is a
                    // claim about the present made from evidence about the past.
                    _MetaChip(
                      icon: Icons.schedule,
                      label: l10n.evidenceRetrievedAt(verdict.retrievedAt.toLocal()),
                      tone: style.onContainer,
                    ),
                    if (verdict.fromCache)
                      _MetaChip(
                        icon: Icons.bolt,
                        label: l10n.checkedEarlier,
                        tone: style.onContainer,
                      ),
                  ],
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const EnglishOnlyNote(padding: EdgeInsets.only(bottom: 8)),
                Text(verdict.actionReason, style: theme.textTheme.bodyMedium),
                if (verdict.claims.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  ...verdict.claims.map((claim) => _ClaimRow(claim: claim)),
                ],
                if (verdict.recurrence != null && verdict.recurrence!.timesSeen > 0) ...[
                  const SizedBox(height: 10),
                  _RecurrenceLine(recurrence: verdict.recurrence!),
                ],
                if (verdict.completenessNote != null) ...[
                  const SizedBox(height: 10),
                  _IncompleteNote(note: verdict.completenessNote!),
                ],
                if (verdict.fromCache) ...[
                  const SizedBox(height: 10),
                  Text(
                    l10n.reusedNote,
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
                const SizedBox(height: 14),
                Row(
                  children: [
                    Expanded(
                      child: FilledButton.tonalIcon(
                        onPressed: onSeeEvidence,
                        icon: const Icon(Icons.receipt_long, size: 18),
                        label: Text(
                          citations == 0 ? l10n.whyNoVerdict : l10n.seeEvidence(citations),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    // Offered only when a source established something worth
                    // sending back: a correction, or the context that was
                    // missing. An abstention has nothing to send.
                    if (switch (verdict.action) {
                      VerdictAction.shareWithCorrection ||
                      VerdictAction.doNotShare => l10n.shareCorrection,
                      VerdictAction.shareWithContext => l10n.shareContext,
                      _ => null,
                    }
                        case final label?) ...[
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: onShareCorrection,
                          icon: const Icon(Icons.reply, size: 18),
                          label: Text(label),
                        ),
                      ),
                      const SizedBox(width: 8),
                    ],
                    Expanded(
                      child: TextButton.icon(
                        onPressed: reporting ? null : onReportForReview,
                        icon: reporting
                            ? const SizedBox(
                                width: 14,
                                height: 14,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.flag_outlined, size: 18),
                        label: Text(reporting ? l10n.reporting : l10n.report),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MetaChip extends StatelessWidget {
  const _MetaChip({required this.icon, required this.label, required this.tone});

  final IconData icon;
  final String label;
  final Color tone;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
    decoration: BoxDecoration(
      color: tone.withValues(alpha: 0.10),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 13, color: tone),
        const SizedBox(width: 4),
        // Flexible, so a long label wraps inside the chip instead of running
        // past the card's edge — which a Hindi label, or any label at a large
        // system font size, otherwise does.
        Flexible(
          child: Text(
            label,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: tone,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ],
    ),
  );
}

class _ClaimRow extends StatelessWidget {
  const _ClaimRow({required this.claim});

  final Claim claim;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colour = _colour(theme.colorScheme);
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            margin: const EdgeInsets.only(top: 2),
            width: 20,
            height: 20,
            decoration: BoxDecoration(
              color: colour.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Icon(_icon, size: 13, color: colour),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(claim.text, style: theme.textTheme.bodyMedium),
                const SizedBox(height: 1),
                Text(
                  claim.reason,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  IconData get _icon => switch (claim.status) {
    ClaimStatus.supported => Icons.check,
    ClaimStatus.contradicted => Icons.close,
    ClaimStatus.misleadingContext => Icons.priority_high,
    ClaimStatus.unverified => Icons.remove,
  };

  Color _colour(ColorScheme scheme) => switch (claim.status) {
    ClaimStatus.supported => const Color(0xFF2E7D32),
    ClaimStatus.contradicted => const Color(0xFFC62828),
    ClaimStatus.misleadingContext => const Color(0xFFEF6C00),
    ClaimStatus.unverified => scheme.onSurfaceVariant,
  };
}

/// The recurrence line (M39): how long this has circulated, under how many
/// different captions. Counts promoted verifications only, never raw traffic.
class _RecurrenceLine extends StatelessWidget {
  const _RecurrenceLine({required this.recurrence});

  final Recurrence recurrence;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          const Icon(Icons.history, size: 18),
          const SizedBox(width: 8),
          Expanded(child: Text(recurrence.summary, style: theme.textTheme.bodySmall)),
        ],
      ),
    );
  }
}

/// Says plainly that the answer is thinner than it should be.
///
/// A gap the reader cannot see is a gap they will read as an absence of
/// findings, which is the quiet way an incomplete run becomes a clean bill of
/// health.
class _IncompleteNote extends StatelessWidget {
  const _IncompleteNote({required this.note});

  final String note;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dark = theme.brightness == Brightness.dark;
    const amber = Color(0xFFF57F17);
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: amber.withValues(alpha: dark ? 0.18 : 0.08),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.warning_amber, size: 18, color: amber),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              note,
              style: theme.textTheme.bodySmall?.copyWith(
                color: dark ? const Color(0xFFFFE082) : const Color(0xFF6D4C00),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
