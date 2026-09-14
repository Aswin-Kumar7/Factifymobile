/// The timeline (M44, PLAN 1.7.4): the dates behind a verdict, in order.
///
/// Built only from dates the response carries — when each cited source was
/// published or seen, when Facify first checked this content, and when this
/// result's evidence was gathered. A source without a date is left off rather than
/// placed by guesswork, and with nothing dated beyond this check the card is not
/// drawn at all: a timeline of one point is decoration.
///
/// Stored cases carry no source dates yet (B6, B7 in docs/hackathon-workflow.md),
/// so until those land the card appears only on freshly computed results.
library;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../l10n/app_localizations.dart';
import '../l10n/phrases.dart';
import '../models/verdict.dart';

class TimelineEntry {
  const TimelineEntry({required this.at, required this.title, this.direction});

  final DateTime at;
  final String title;

  /// How a cited source bears on the claim; null for Facify's own checks.
  final String? direction;
}

/// Every dated point behind [verdict], oldest first.
List<TimelineEntry> timelineFor(Verdict verdict, AppLocalizations l10n) {
  final firstChecked = verdict.recurrence?.firstVerifiedAt;
  return [
    for (final evidence in verdict.allEvidence)
      if (evidence.observedAt case final at?)
        TimelineEntry(at: at, title: l10n.describeSource(evidence), direction: evidence.direction),
    if (firstChecked != null) TimelineEntry(at: firstChecked, title: l10n.timelineFirstChecked),
    TimelineEntry(at: verdict.retrievedAt, title: l10n.timelineRetrieved),
  ]..sort((a, b) => a.at.compareTo(b.at));
}

class EvidenceTimeline extends StatelessWidget {
  const EvidenceTimeline({required this.verdict, this.padding = EdgeInsets.zero, super.key});

  final Verdict verdict;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final entries = timelineFor(verdict, l10n);
    // This check's own retrieval is always an entry; with nothing dated beside it
    // there is no sequence to show.
    if (entries.length < 2) return const SizedBox.shrink();

    final theme = Theme.of(context);
    final dates = DateFormat('d MMM yyyy', l10n.localeName);

    return Padding(
      padding: padding,
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(l10n.timelineTitle, style: theme.textTheme.titleSmall),
              const SizedBox(height: 10),
              for (final (index, entry) in entries.indexed)
                _TimelineRow(
                  entry: entry,
                  date: dates.format(entry.at.toLocal()),
                  last: index == entries.length - 1,
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TimelineRow extends StatelessWidget {
  const _TimelineRow({required this.entry, required this.date, required this.last});

  final TimelineEntry entry;
  final String date;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final l10n = AppLocalizations.of(context);
    final muted = theme.textTheme.labelSmall?.copyWith(color: scheme.onSurfaceVariant);
    final direction = entry.direction;

    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(width: 84, child: Text(date, style: muted)),
          SizedBox(
            width: 20,
            child: Column(
              children: [
                // Facify's own checks are filled; cited sources are hollow.
                Container(
                  margin: const EdgeInsets.only(top: 3),
                  width: 10,
                  height: 10,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: direction == null ? scheme.primary : scheme.surface,
                    border: Border.all(color: scheme.primary, width: 2),
                  ),
                ),
                if (!last) Expanded(child: Container(width: 2, color: scheme.outlineVariant)),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: last ? 0 : 14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    entry.title,
                    style: theme.textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w600),
                  ),
                  if (direction != null) Text(l10n.directionLabel(direction), style: muted),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
