/// The result: a verdict, how sure it is, one sentence on why, and the sources.
///
/// Built for a person who opened the app from a chat in a hurry. The badge answers
/// the question they came with — is it true? — and everything below it is there to
/// let them trust that answer or check it: the confidence, the plain reason, and the
/// sources it rests on, each of which opens the page it was quoted from.
///
/// Two rules survive from the evidence-first design this replaced:
///
///   * True, False and Misleading only ever appear with sources beneath them. The
///     server never sends a decided verdict without citations, and this card shows
///     them rather than asking to be believed.
///   * "Unconfirmed" is grey, never red. It means the sources did not settle the
///     claim, which is a different answer from "this is false".
library;

import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/verdict.dart';
import '../theme/colors.dart';
import 'action_style.dart';
import 'english_only_note.dart';
import 'source_tile.dart';

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

  /// Reports this result as wrong. Null once it has been reported.
  final VoidCallback? onReportForReview;

  /// True while a report is in flight, so the button can say so instead of
  /// appearing to do nothing.
  final bool reporting;

  /// How many sources the card itself lists before offering the rest.
  static const _preview = 3;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final style = ActionStyle.forVerdict(verdict, Brightness.light, l10n);
    final decided = verdict.factVerdict.isDecided;
    final sources = verdict.allEvidence;
    final confidence = verdict.confidence;

    final summary = decided
        ? (verdict.summary ?? verdict.actionReason)
        : verdict.nothingToCheck
        ? (verdict.imageReading != null ? l10n.nothingToCheckPicture : l10n.nothingToCheckText)
        : l10n.unconfirmedBody;

    final correctionLabel = switch (verdict.factVerdict) {
      FactVerdict.falseClaim => l10n.shareCorrection,
      FactVerdict.misleading => l10n.shareContext,
      _ => null,
    };

    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            color: style.container,
            padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
            child: Row(
              children: [
                Container(
                  width: 52,
                  height: 52,
                  decoration: BoxDecoration(color: style.tone, shape: BoxShape.circle),
                  child: Icon(style.icon, color: Colors.white, size: 30),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        style.headline,
                        style: theme.textTheme.headlineSmall?.copyWith(
                          color: style.onContainer,
                          height: 1.1,
                        ),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        style.subhead,
                        style: theme.textTheme.bodySmall?.copyWith(color: style.onContainer),
                      ),
                    ],
                  ),
                ),
                if (decided && confidence != null) ...[
                  const SizedBox(width: 10),
                  ConfidenceRing(value: confidence, tone: style.tone),
                ],
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(18, 16, 18, 14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Summaries and quotes arrive in the language of the claim, not
                // the app's; a Hindi reader is told so rather than surprised.
                const EnglishOnlyNote(padding: EdgeInsets.only(bottom: 8)),
                Text(summary, style: theme.textTheme.bodyMedium),
                if (verdict.searchUnavailable) ...[
                  const SizedBox(height: 10),
                  _Note(text: l10n.searchUnavailableNote),
                ] else if (verdict.completenessNote != null) ...[
                  const SizedBox(height: 10),
                  _Note(text: l10n.incompleteNote),
                ],
                if (sources.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  Text(
                    l10n.sourcesTitle,
                    style: theme.textTheme.labelLarge?.copyWith(
                      color: FactifyColors.inkMuted,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 8),
                  for (final (index, item) in sources.take(_preview).indexed) ...[
                    if (index > 0) const SizedBox(height: 8),
                    SourceTile(evidence: item, compact: true),
                  ],
                ],
                const SizedBox(height: 16),
                if (!verdict.nothingToCheck)
                  FilledButton.tonal(
                    style: FilledButton.styleFrom(
                      backgroundColor: FactifyColors.emeraldTint,
                      foregroundColor: FactifyColors.emeraldDeep,
                    ),
                    onPressed: onSeeEvidence,
                    child: Text(
                      sources.isEmpty ? l10n.whyNoVerdict : l10n.seeEvidence(sources.length),
                    ),
                  ),
                if (correctionLabel != null) ...[
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                    onPressed: onShareCorrection,
                    icon: const Icon(Icons.reply_rounded, size: 18),
                    label: Text(correctionLabel),
                  ),
                ],
                const SizedBox(height: 4),
                // A Wrap, not a Row: in Hindi the two do not fit on one line at
                // phone width, and the button drops below instead of overflowing.
                Wrap(
                  alignment: WrapAlignment.spaceBetween,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Text(
                      l10n.checkedAt(verdict.retrievedAt.toLocal()),
                      style: theme.textTheme.labelSmall?.copyWith(color: FactifyColors.inkMuted),
                    ),
                    TextButton.icon(
                      style: TextButton.styleFrom(foregroundColor: FactifyColors.inkMuted),
                      onPressed: reporting ? null : onReportForReview,
                      icon: reporting
                          ? const SizedBox(
                              width: 14,
                              height: 14,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.flag_outlined, size: 16),
                      label: Text(reporting ? l10n.reporting : l10n.report),
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

/// How sure the verdict is, as a ring and a number.
///
/// Shown only with a decided verdict. The number is arithmetic on the cited sources
/// — how many, how credible, whether any disagree — and runs from 50 to 97: never
/// certain, and never less than even, because below that it is not a verdict.
class ConfidenceRing extends StatelessWidget {
  const ConfidenceRing({super.key, required this.value, required this.tone, this.size = 58});

  final int value;
  final Color tone;
  final double size;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Semantics(
      label: l10n.confidence(value),
      child: SizedBox(
        width: size,
        height: size,
        child: Stack(
          alignment: Alignment.center,
          children: [
            SizedBox(
              width: size,
              height: size,
              child: CircularProgressIndicator(
                value: value / 100,
                strokeWidth: 5,
                strokeCap: StrokeCap.round,
                color: tone,
                backgroundColor: tone.withValues(alpha: 0.15),
              ),
            ),
            ExcludeSemantics(
              child: Text(
                '$value%',
                style: TextStyle(
                  color: tone,
                  fontWeight: FontWeight.w800,
                  fontSize: size * 0.26,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Note extends StatelessWidget {
  const _Note({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(10),
    decoration: BoxDecoration(
      color: const Color(0xFFFFFBEB),
      borderRadius: BorderRadius.circular(10),
    ),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Icon(Icons.info_outline_rounded, size: 18, color: Color(0xFFB45309)),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            text,
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: const Color(0xFF92400E)),
          ),
        ),
      ],
    ),
  );
}
