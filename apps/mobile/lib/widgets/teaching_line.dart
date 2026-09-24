/// The teaching-mode line (PLAN 1.7.4): the manipulation technique a decided claim
/// fits, named so the reader recognises the next one without needing an app.
///
/// Chosen by rule from what the evidence established — the claim's type, its
/// status and the kind of evidence behind it — never by a model. Only a claim a
/// cited source contradicted or recontextualised gets one: a supported or
/// unverified claim has no technique to teach, and naming one would suggest a
/// finding that does not exist.
library;

import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/verdict.dart';

enum Technique {
  recycledMedia,
  missingContext,
  misattributedQuote,
  twistedNumber,
  wrongIdentity,
}

/// The technique [claim] fits, or null when there is none to name.
Technique? techniqueFor(Claim claim) {
  final contradicted = claim.status == ClaimStatus.contradicted;
  final recontextualised = claim.status == ClaimStatus.misleadingContext;
  if (!contradicted && !recontextualised) return null;

  // A matched earlier publication is the most specific finding there is, so it
  // decides before the claim's type does.
  if (claim.claimType == 'MEDIA' && claim.evidence.any((e) => e.isMediaMatch)) {
    return Technique.recycledMedia;
  }
  if (recontextualised) return Technique.missingContext;

  return switch (claim.claimType) {
    'QUOTE' || 'ATTRIBUTION' => Technique.misattributedQuote,
    'STATISTIC' => Technique.twistedNumber,
    'IDENTITY' => Technique.wrongIdentity,
    // EVENT is the catch-all type for a plain factual claim — a health myth, a
    // scam, a rumour — so it names no technique. "Distorted event" used to be
    // shown for all of them, which taught the wrong lesson more often than not.
    _ => null,
  };
}

/// The technique's name and its one-sentence lesson, in the reader's language.
(String, String) techniqueWords(Technique technique, AppLocalizations l10n) => switch (technique) {
  Technique.recycledMedia => (l10n.techniqueRecycledMediaTitle, l10n.techniqueRecycledMediaBody),
  Technique.missingContext => (l10n.techniqueMissingContextTitle, l10n.techniqueMissingContextBody),
  Technique.misattributedQuote => (
    l10n.techniqueMisattributedQuoteTitle,
    l10n.techniqueMisattributedQuoteBody,
  ),
  Technique.twistedNumber => (l10n.techniqueTwistedNumberTitle, l10n.techniqueTwistedNumberBody),
  Technique.wrongIdentity => (l10n.techniqueWrongIdentityTitle, l10n.techniqueWrongIdentityBody),
};

class TeachingLine extends StatelessWidget {
  const TeachingLine({required this.technique, super.key});

  final Technique technique;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final l10n = AppLocalizations.of(context);
    final (title, lesson) = techniqueWords(technique, l10n);

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: scheme.secondaryContainer.withValues(alpha: 0.55),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.lightbulb_outline, size: 18, color: scheme.onSecondaryContainer),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  l10n.techniqueLabel,
                  style: theme.textTheme.labelSmall?.copyWith(color: scheme.onSecondaryContainer),
                ),
                const SizedBox(height: 2),
                Text(title, style: theme.textTheme.titleSmall),
                const SizedBox(height: 2),
                Text(lesson, style: theme.textTheme.bodySmall),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
