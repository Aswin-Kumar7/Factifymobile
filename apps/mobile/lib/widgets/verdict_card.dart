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
library;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/verdict.dart';

class VerdictCard extends StatelessWidget {
  const VerdictCard({
    super.key,
    required this.verdict,
    required this.onSeeEvidence,
    required this.onShareCorrection,
    required this.onReportForReview,
  });

  final Verdict verdict;
  final VoidCallback onSeeEvidence;
  final VoidCallback onShareCorrection;
  final VoidCallback onReportForReview;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final style = _ActionStyle.of(verdict.action, theme.colorScheme);

    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            color: style.background,
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Icon(style.icon, color: style.foreground, size: 28),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        style.headline,
                        style: theme.textTheme.titleMedium?.copyWith(
                          color: style.foreground,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        style.subhead,
                        style: theme.textTheme.bodySmall?.copyWith(color: style.foreground),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(verdict.actionReason, style: theme.textTheme.bodyMedium),
                if (verdict.claims.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  ...verdict.claims.map((claim) => _ClaimRow(claim: claim)),
                ],
                if (verdict.recurrence != null && verdict.recurrence!.timesSeen > 0) ...[
                  const SizedBox(height: 12),
                  _RecurrenceLine(recurrence: verdict.recurrence!),
                ],
                if (verdict.completenessNote != null) ...[
                  const SizedBox(height: 12),
                  _IncompleteNote(note: verdict.completenessNote!),
                ],
                const SizedBox(height: 12),
                _Provenance(verdict: verdict),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  children: [
                    FilledButton.tonalIcon(
                      onPressed: onSeeEvidence,
                      icon: const Icon(Icons.receipt_long, size: 18),
                      label: Text('See evidence (${verdict.allEvidence.length})'),
                    ),
                    if (verdict.action == VerdictAction.shareWithCorrection ||
                        verdict.action == VerdictAction.doNotShare)
                      OutlinedButton.icon(
                        onPressed: onShareCorrection,
                        icon: const Icon(Icons.reply, size: 18),
                        label: const Text('Share correction'),
                      ),
                    TextButton.icon(
                      onPressed: onReportForReview,
                      icon: const Icon(Icons.flag_outlined, size: 18),
                      label: const Text('Report'),
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

/// Wording and colour per action.
///
/// Every headline is a statement about *evidence*, never about truth. "Nothing
/// contradicts this" is what we can support; "this is true" is not.
class _ActionStyle {
  const _ActionStyle({
    required this.headline,
    required this.subhead,
    required this.icon,
    required this.background,
    required this.foreground,
  });

  final String headline;
  final String subhead;
  final IconData icon;
  final Color background;
  final Color foreground;

  static _ActionStyle of(VerdictAction action, ColorScheme scheme) => switch (action) {
    VerdictAction.safeToShare => _ActionStyle(
      headline: 'Nothing contradicts this',
      subhead: 'Independent sources agree',
      icon: Icons.check_circle_outline,
      background: const Color(0xFF1B5E20),
      foreground: Colors.white,
    ),
    VerdictAction.shareWithContext => _ActionStyle(
      headline: 'True, but missing context',
      subhead: 'Share the context with it',
      icon: Icons.info_outline,
      background: const Color(0xFF01579B),
      foreground: Colors.white,
    ),
    VerdictAction.shareWithCorrection => _ActionStyle(
      headline: 'A detail here is wrong',
      subhead: 'Share only with a correction',
      icon: Icons.error_outline,
      background: const Color(0xFFE65100),
      foreground: Colors.white,
    ),
    VerdictAction.doNotShare => _ActionStyle(
      headline: 'Contradicted by sources',
      subhead: 'Published sources say otherwise',
      icon: Icons.cancel_outlined,
      background: const Color(0xFFB71C1C),
      foreground: Colors.white,
    ),
    VerdictAction.waitAndRecheck => _ActionStyle(
      headline: 'Still developing',
      subhead: 'Early reports are often revised',
      icon: Icons.schedule,
      background: const Color(0xFF4527A0),
      foreground: Colors.white,
    ),
    // Deliberately neutral, not red. Abstaining is the designed answer for a
    // case with no citable evidence, and colouring it as danger would tell
    // people we found something when we found nothing.
    VerdictAction.sendToReview => _ActionStyle(
      headline: 'Not enough evidence to decide',
      subhead: 'Sent for human review',
      icon: Icons.help_outline,
      background: const Color(0xFF37474F),
      foreground: Colors.white,
    ),
  };
}

class _ClaimRow extends StatelessWidget {
  const _ClaimRow({required this.claim});

  final Claim claim;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Icon(_icon, size: 16, color: _colour(theme.colorScheme)),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(claim.text, style: theme.textTheme.bodyMedium),
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
        borderRadius: BorderRadius.circular(8),
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
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF8E1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFFFFE082)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.warning_amber, size: 18, color: Color(0xFFF57F17)),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              note,
              style: theme.textTheme.bodySmall?.copyWith(color: const Color(0xFF6D4C00)),
            ),
          ),
        ],
      ),
    );
  }
}

/// When the evidence was gathered, and whether it was reused.
class _Provenance extends StatelessWidget {
  const _Provenance({required this.verdict});

  final Verdict verdict;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final when = DateFormat('d MMM yyyy, HH:mm').format(verdict.retrievedAt.toLocal());
    final suffix = verdict.fromCache ? ' - reused from an earlier check' : '';

    return Text(
      'Evidence retrieved $when$suffix',
      style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
    );
  }
}
