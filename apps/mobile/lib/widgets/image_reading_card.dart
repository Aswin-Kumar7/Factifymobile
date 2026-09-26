/// What was read in an uploaded picture, shown above the verdict about it.
///
/// The verdict is about the text found in the picture, so that text is shown first:
/// a person can see exactly what was checked, and catch a misread before trusting
/// the answer built on it. The description says what the picture is and shows, in
/// the reader's words - context for the person, never evidence.
library;

import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/verdict.dart';
import '../theme/colors.dart';

class ImageReadingCard extends StatefulWidget {
  const ImageReadingCard({required this.reading, super.key});

  final ImageReading reading;

  @override
  State<ImageReadingCard> createState() => _ImageReadingCardState();
}

class _ImageReadingCardState extends State<ImageReadingCard> {
  // A long screenshot is folded to its opening lines; the whole text is a tap away.
  static const _foldedLines = 8;
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final reading = widget.reading;
    final description = reading.description?.trim() ?? '';
    final publisher = reading.publisher?.trim() ?? '';
    final lines = reading.text.trim().split('\n').length;
    final foldable = lines > _foldedLines;
    final muted = theme.textTheme.bodySmall?.copyWith(color: FactifyColors.inkMuted);

    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.document_scanner_outlined, color: FactifyColors.emerald),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    l10n.imageReadTitle,
                    style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 6,
              children: [
                _Tag(label: l10n.imageKind(reading.kind ?? 'OTHER')),
                if (publisher.isNotEmpty) _Tag(label: l10n.imageFrom(publisher)),
              ],
            ),
            if (description.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(description, style: theme.textTheme.bodyMedium),
            ],
            const SizedBox(height: 12),
            if (reading.hasText) ...[
              Text(l10n.imageTextLabel, style: muted),
              const SizedBox(height: 6),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: FactifyColors.ground,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: FactifyColors.line),
                ),
                child: Text(
                  reading.text.trim(),
                  style: theme.textTheme.bodyMedium?.copyWith(height: 1.4),
                  maxLines: foldable && !_expanded ? _foldedLines : null,
                  overflow: foldable && !_expanded ? TextOverflow.fade : null,
                ),
              ),
              if (foldable)
                TextButton(
                  onPressed: () => setState(() => _expanded = !_expanded),
                  child: Text(_expanded ? l10n.imageShowLessText : l10n.imageShowAllText),
                ),
            ] else
              Text(l10n.imageNoText, style: muted),
          ],
        ),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: FactifyColors.emeraldTint,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelMedium?.copyWith(
          color: FactifyColors.emeraldDeep,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
