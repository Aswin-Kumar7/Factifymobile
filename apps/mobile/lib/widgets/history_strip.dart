/// Recent checks from this session.
///
/// Deliberately in memory and deliberately not persisted. What someone checked is
/// a record of what they were suspicious about, and writing that to disk creates a
/// file worth reading on a shared or seized phone. The session-scoped list gives
/// back the useful part — returning to the result you looked at a minute ago —
/// without leaving anything behind.
library;

import 'package:flutter/material.dart';

import '../models/submission.dart';
import '../models/verdict.dart';

class HistoryEntry {
  const HistoryEntry({required this.submission, required this.verdict});

  final Submission submission;
  final Verdict verdict;
}

class HistoryStrip extends StatelessWidget {
  const HistoryStrip({required this.entries, required this.onOpen, super.key});

  final List<HistoryEntry> entries;
  final void Function(HistoryEntry) onOpen;

  @override
  Widget build(BuildContext context) {
    if (entries.isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text('Earlier this session', style: theme.textTheme.titleSmall),
            const SizedBox(width: 8),
            Text(
              '${entries.length}',
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        ...entries.map(
          (entry) => _HistoryRow(entry: entry, onTap: () => onOpen(entry)),
        ),
      ],
    );
  }
}

class _HistoryRow extends StatelessWidget {
  const _HistoryRow({required this.entry, required this.onTap});

  final HistoryEntry entry;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final action = entry.verdict.action;

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        onTap: onTap,
        leading: CircleAvatar(
          backgroundColor: _tint(action, theme.colorScheme),
          child: Icon(_icon(action), size: 20, color: Colors.white),
        ),
        title: Text(
          entry.submission.summary,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: theme.textTheme.bodyMedium,
        ),
        subtitle: Text(
          // The citation count, not a confidence figure. How many sources were
          // quoted is checkable; a percentage is not.
          switch (entry.verdict.allEvidence.length) {
            0 => 'No citable evidence',
            1 => '1 citation',
            final n => '$n citations',
          },
          style: theme.textTheme.labelSmall,
        ),
        trailing: const Icon(Icons.chevron_right),
      ),
    );
  }

  static Color _tint(VerdictAction action, ColorScheme scheme) => switch (action) {
    VerdictAction.safeToShare => const Color(0xFF1B5E20),
    VerdictAction.shareWithContext => const Color(0xFF01579B),
    VerdictAction.shareWithCorrection => const Color(0xFFE65100),
    VerdictAction.doNotShare => const Color(0xFFB71C1C),
    VerdictAction.waitAndRecheck => const Color(0xFF4527A0),
    VerdictAction.sendToReview => scheme.outline,
  };

  static IconData _icon(VerdictAction action) => switch (action) {
    VerdictAction.safeToShare => Icons.check,
    VerdictAction.shareWithContext => Icons.info_outline,
    VerdictAction.shareWithCorrection => Icons.edit_outlined,
    VerdictAction.doNotShare => Icons.block,
    VerdictAction.waitAndRecheck => Icons.schedule,
    VerdictAction.sendToReview => Icons.help_outline,
  };
}
