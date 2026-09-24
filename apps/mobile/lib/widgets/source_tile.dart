/// One cited source: who published it, how credible they are, which way it points,
/// and the sentence it was cited for.
///
/// Every source shown here has already been checked by the server against the exact
/// claim — sources that were merely on the topic are no longer sent — so this does not
/// need to hedge about relevance. What it must still show is the quote, because a
/// verdict a person cannot trace back to words on a page is a verdict they have to take
/// on trust.
library;

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../l10n/app_localizations.dart';
import '../theme/colors.dart';
import '../models/verdict.dart';

class SourceTile extends StatelessWidget {
  const SourceTile({super.key, required this.evidence, this.compact = false});

  final Evidence evidence;

  /// The result card shows sources on one line each; the sources screen shows the
  /// quote as well.
  final bool compact;

  Future<void> _open() async {
    final uri = Uri.tryParse(evidence.citationUrl);
    if (uri == null) return;
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final refutes = evidence.contradicts;
    final stanceColour = refutes ? const Color(0xFFDC2626) : FactifyColors.emerald;
    final name = evidence.sourceName;

    final header = Row(
      children: [
        _Avatar(name: name),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
              ),
              if (evidence.credibility != null)
                Text(
                  l10n.credibility(evidence.credibility!),
                  style: theme.textTheme.labelSmall?.copyWith(color: FactifyColors.inkMuted),
                ),
            ],
          ),
        ),
        const SizedBox(width: 8),
        _Stance(
          label: refutes ? l10n.sourceRefutes : l10n.sourceConfirms,
          icon: refutes ? Icons.close_rounded : Icons.check_rounded,
          colour: stanceColour,
        ),
      ],
    );

    return InkWell(
      onTap: _open,
      borderRadius: BorderRadius.circular(14),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: FactifyColors.line),
        ),
        child: compact
            ? header
            : Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  header,
                  const SizedBox(height: 10),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
                    decoration: BoxDecoration(
                      color: FactifyColors.ground,
                      borderRadius: BorderRadius.circular(10),
                      border: Border(left: BorderSide(color: stanceColour, width: 3)),
                    ),
                    child: Text(
                      '“${evidence.sourceExcerpt}”',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: FactifyColors.ink,
                        height: 1.45,
                      ),
                    ),
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      const Icon(Icons.open_in_new_rounded, size: 14, color: FactifyColors.emeraldDark),
                      const SizedBox(width: 4),
                      Text(
                        l10n.openSource,
                        style: theme.textTheme.labelMedium?.copyWith(
                          color: FactifyColors.emeraldDark,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
      ),
    );
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar({required this.name});

  final String name;

  @override
  Widget build(BuildContext context) {
    final letter = name.isEmpty ? '?' : name.characters.first.toUpperCase();
    return Container(
      width: 34,
      height: 34,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: FactifyColors.emeraldTint,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        letter,
        style: const TextStyle(
          color: FactifyColors.emeraldDeep,
          fontWeight: FontWeight.w800,
          fontSize: 15,
        ),
      ),
    );
  }
}

class _Stance extends StatelessWidget {
  const _Stance({required this.label, required this.icon, required this.colour});

  final String label;
  final IconData icon;
  final Color colour;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
    decoration: BoxDecoration(
      color: colour.withValues(alpha: 0.10),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 14, color: colour),
        const SizedBox(width: 3),
        Text(
          label,
          style: TextStyle(color: colour, fontWeight: FontWeight.w700, fontSize: 12),
        ),
      ],
    ),
  );
}
