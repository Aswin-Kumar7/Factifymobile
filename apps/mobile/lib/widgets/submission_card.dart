/// Shows what is being checked, above the verdict about it.
///
/// A verdict is a statement about a specific thing. Showing the statement without
/// the thing forces the reader to remember what they submitted and trust that the
/// app remembered the same — which is precisely the kind of unverifiable step this
/// product exists to remove.
library;

import 'package:flutter/material.dart';

import '../models/submission.dart';

class SubmissionCard extends StatelessWidget {
  const SubmissionCard({required this.submission, this.onClear, super.key});

  final Submission submission;
  final VoidCallback? onClear;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final thumbnail = submission.thumbnail;

    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (thumbnail != null)
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: Image.memory(
                  thumbnail,
                  width: 64,
                  height: 64,
                  fit: BoxFit.cover,
                  // A thumbnail that fails to decode must not take the verdict
                  // down with it.
                  errorBuilder: (_, _, _) => _KindBadge(kind: submission.kind),
                ),
              )
            else
              _KindBadge(kind: submission.kind),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Checking this ${submission.label.toLowerCase()}',
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    submission.summary,
                    style: theme.textTheme.bodyMedium,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            if (onClear != null)
              IconButton(
                onPressed: onClear,
                icon: const Icon(Icons.close),
                tooltip: 'Clear',
                visualDensity: VisualDensity.compact,
              ),
          ],
        ),
      ),
    );
  }
}

class _KindBadge extends StatelessWidget {
  const _KindBadge({required this.kind});

  final SubmissionKind kind;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final icon = switch (kind) {
      SubmissionKind.text => Icons.forum_outlined,
      SubmissionKind.link => Icons.link,
      SubmissionKind.image => Icons.image_outlined,
      SubmissionKind.document => Icons.description_outlined,
    };

    return Container(
      width: 64,
      height: 64,
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Icon(icon, color: scheme.onSurfaceVariant),
    );
  }
}
