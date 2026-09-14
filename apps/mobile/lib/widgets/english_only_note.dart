/// Says that some of what follows is in English, when the interface is not.
///
/// Until the server phrases verdicts in the request's language (B5 in
/// docs/hackathon-workflow.md), claim reasons, summaries and notes arrive in
/// English. Saying so beats a screen that silently changes language halfway
/// down. In an English interface this renders nothing.
library;

import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';

class EnglishOnlyNote extends StatelessWidget {
  const EnglishOnlyNote({super.key, this.padding = EdgeInsets.zero});

  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    if (l10n.localeName == 'en') return const SizedBox.shrink();

    final theme = Theme.of(context);
    final muted = theme.colorScheme.onSurfaceVariant;
    return Padding(
      padding: padding,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.translate, size: 14, color: muted),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              l10n.englishOnlyNote,
              style: theme.textTheme.labelSmall?.copyWith(color: muted),
            ),
          ),
        ],
      ),
    );
  }
}
