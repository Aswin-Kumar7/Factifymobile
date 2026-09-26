/// What was checked: the text, the link, or the picture or file, in one line or three.
///
/// Shown above the wait, above the answer, and in history, so an answer is never
/// seen apart from the thing it is about.
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../models/submission.dart';
import '../theme/colors.dart';

IconData iconForKind(SubmissionKind kind) => switch (kind) {
  SubmissionKind.text => Icons.notes_rounded,
  SubmissionKind.link => Icons.link_rounded,
  SubmissionKind.image => Icons.image_outlined,
  SubmissionKind.document => Icons.picture_as_pdf_outlined,
};

class CheckedItemCard extends StatelessWidget {
  const CheckedItemCard({
    required this.kind,
    required this.summary,
    this.thumbnail,
    this.label,
    super.key,
  });

  CheckedItemCard.of(Submission submission, {String? label, Key? key})
    : this(
        kind: submission.kind,
        summary: submission.summary,
        thumbnail: submission.thumbnail,
        label: label,
        key: key,
      );

  final SubmissionKind kind;
  final String summary;
  final Uint8List? thumbnail;

  /// A small heading above the summary, such as "What you checked".
  final String? label;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final thumb = thumbnail;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: thumb != null
                  ? Image.memory(
                      thumb,
                      width: 56,
                      height: 56,
                      fit: BoxFit.cover,
                      errorBuilder: (_, _, _) => _Badge(kind: kind),
                    )
                  : _Badge(kind: kind),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (label != null) ...[
                    Text(
                      label!,
                      style: theme.textTheme.labelMedium?.copyWith(color: FactifyColors.inkMuted),
                    ),
                    const SizedBox(height: 2),
                  ],
                  Text(
                    summary,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodyMedium,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.kind});

  final SubmissionKind kind;

  @override
  Widget build(BuildContext context) => Container(
    width: 56,
    height: 56,
    color: FactifyColors.emeraldTint,
    child: Icon(iconForKind(kind), color: FactifyColors.emeraldDark),
  );
}
