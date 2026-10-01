/// Says that some of what follows is in English, when the interface is not.
///
/// A claim's reason and the summary arrive in the language the claim was made in
/// (its `language`), not necessarily the interface's. The note shows only when
/// that is actually English - a claim marked `en`, or unmarked, as cases stored
/// before claims carried a language are - under a non-English interface. A Hindi
/// claim read in Hindi, or a check with no claims, shows nothing. Saying so beats
/// a screen that silently changes language halfway down.
library;

import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/verdict.dart';

class EnglishOnlyNote extends StatelessWidget {
  const EnglishOnlyNote({required this.verdict, super.key, this.padding = EdgeInsets.zero});

  final Verdict verdict;
  final EdgeInsetsGeometry padding;

  /// Whether any reason on this verdict arrives in English.
  static bool hasEnglish(Verdict verdict) =>
      verdict.claims.any((claim) => claim.language == null || claim.language == 'en');

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    if (l10n.localeName == 'en' || !hasEnglish(verdict)) return const SizedBox.shrink();

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
