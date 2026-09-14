/// The forensic advisory panel (M37, M44).
///
/// This widget takes `List<Advisory>` and nothing else. It cannot be handed
/// `Evidence` — the two are unrelated classes — so the separation the server
/// enforces in its types survives into the interface rather than depending on
/// whoever wires the screen.
///
/// Three rules, all visible in the code below:
///
///   1. **A permanently visible exclusion header.** Not a tooltip, not a
///      collapsed hint. The header renders whether or not the panel is expanded.
///   2. **Greyed, and below the evidence.** A forensic signal that looks like a
///      finding will be read as one, whatever the caption says.
///   3. **No score is rendered as a number.** A "0.87" beside a red icon is a
///      verdict in everything but name, and this panel is not allowed to reach
///      a verdict. The signal is described in words instead.
library;

import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/verdict.dart';

class AdvisoryPanel extends StatelessWidget {
  const AdvisoryPanel({super.key, required this.advisories});

  /// Deliberately typed to [Advisory]. There is no overload taking evidence.
  final List<Advisory> advisories;

  @override
  Widget build(BuildContext context) {
    if (advisories.isEmpty) return const SizedBox.shrink();

    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    // Muted on purpose. This panel must never compete visually with the cited
    // evidence above it.
    final muted = theme.colorScheme.onSurfaceVariant;

    return Card(
      color: theme.colorScheme.surfaceContainerHighest,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // The header sits outside the ExpansionTile so it is on screen even
          // when the panel is collapsed. Putting it inside would make the
          // caveat disappear exactly when the signals are summarised.
          Container(
            width: double.infinity,
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.science_outlined, size: 18, color: muted),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    l10n.advisoryHeader,
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: muted,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          ExpansionTile(
            title: Text(
              l10n.advisoryCount(advisories.length),
              style: theme.textTheme.bodyMedium?.copyWith(color: muted),
            ),
            childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            children: [
              for (final advisory in advisories) _AdvisoryRow(advisory: advisory, muted: muted),
              const SizedBox(height: 8),
              Text(
                l10n.advisoryFooter,
                style: theme.textTheme.labelSmall?.copyWith(color: muted),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _AdvisoryRow extends StatelessWidget {
  const _AdvisoryRow({required this.advisory, required this.muted});

  final Advisory advisory;
  final Color muted;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              // One neutral icon for every signal. A red flag for "suspicion"
              // and a green tick for "no signal" would be a verdict drawn in
              // iconography, which is the failure this panel exists to avoid.
              Icon(Icons.remove_circle_outline, size: 14, color: muted),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  advisory.provider,
                  style: theme.textTheme.labelSmall?.copyWith(color: muted),
                ),
              ),
            ],
          ),
          const SizedBox(height: 2),
          Text(advisory.note, style: theme.textTheme.bodySmall?.copyWith(color: muted)),
          const SizedBox(height: 2),
          // Carried from the server so the caveat is data, not something a
          // future refactor of this widget could drop. The server writes it in
          // English only until B5, so another interface language shows the same
          // caveat in the reader's own words rather than a line they may not read.
          Text(
            l10n.localeName == 'en' ? advisory.excludedNote : l10n.advisoryRowExcluded,
            style: theme.textTheme.labelSmall?.copyWith(color: muted, fontStyle: FontStyle.italic),
          ),
        ],
      ),
    );
  }
}
