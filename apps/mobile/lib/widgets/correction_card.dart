/// The correction card (M44, PLAN 1.7.5): the verdict as a picture, for the chat
/// the content came from.
///
/// A picture because that is what travels in a group. The claim most likely
/// arrived as one, a pasted paragraph gets skimmed, and a bare link loses its
/// preview. The card uses the result card's own wording, names only the claims
/// that were decided, and says who said so and when — publisher, site and date.
/// The links travel as text beside it ([correctionText]), because a URL drawn into
/// an image cannot be tapped.
///
/// Built only from cited findings. Advisory signals never appear on it: the card
/// leaves the app without the advisory panel's exclusion header, so it must not
/// carry anything that would need one.
library;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../l10n/app_localizations.dart';
import '../models/verdict.dart';
import 'action_style.dart';
import 'english_only_note.dart';

/// The width the card is drawn at, in logical pixels. Captured at 3x, that is a
/// 1080-pixel-wide picture: sharp on any phone, and small enough for any chat.
const double correctionCardWidth = 360;

/// Sources named per claim, on the card and in the text beside it. Two show that
/// a finding is not one outlet's word, and are still readable at a glance.
const int correctionSourcesPerClaim = 2;

/// The correction as text: what travels beside the picture, and what "copy text"
/// puts on the clipboard.
///
/// Built only from cited findings. A correction that cannot point at a source is
/// just a counter-assertion, and sending one starts an argument rather than
/// ending it.
String correctionText(Verdict verdict, AppLocalizations l10n) {
  final buffer = StringBuffer()
    ..writeln(l10n.correctionHeader)
    ..writeln();

  for (final claim in verdict.claims.where((c) => c.isDecisive)) {
    buffer
      ..writeln('"${claim.text}"')
      ..writeln(claim.reason);
    for (final evidence in claim.evidence.take(correctionSourcesPerClaim)) {
      buffer.writeln(
        '- ${evidence.publisher ?? l10n.correctionSourceFallback}: ${evidence.citationUrl}',
      );
    }
    buffer.writeln();
  }

  // Said explicitly rather than left as an empty message. "Nothing could confirm
  // this" is a useful thing to send back; a blank message is not.
  if (verdict.claims.every((c) => !c.isDecisive)) {
    buffer.writeln(l10n.correctionNoSource);
  }

  return buffer.toString().trim();
}

class CorrectionCard extends StatelessWidget {
  const CorrectionCard({required this.verdict, super.key});

  final Verdict verdict;

  /// Always the light rendering. The picture is seen in someone else's chat, on
  /// someone else's theme, and a dark card dropped into a light chat reads as a
  /// screenshot of an app rather than as a message.
  static final ThemeData _light = ThemeData(
    colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF00695C)),
    useMaterial3: true,
  );

  @override
  Widget build(BuildContext context) =>
      Theme(data: _light, child: _CardBody(verdict: verdict));
}

class _CardBody extends StatelessWidget {
  const _CardBody({required this.verdict});

  final Verdict verdict;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final l10n = AppLocalizations.of(context);
    final style = ActionStyle.of(verdict.action, Brightness.light, l10n);
    final decided = verdict.claims.where((c) => c.isDecisive).toList();
    final muted = theme.textTheme.labelSmall?.copyWith(color: scheme.onSurfaceVariant);

    return Material(
      color: scheme.surface,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: BorderSide(color: scheme.outlineVariant),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 12),
            child: Row(
              children: [
                Container(
                  width: 24,
                  height: 24,
                  decoration: BoxDecoration(
                    color: scheme.primary,
                    borderRadius: BorderRadius.circular(7),
                  ),
                  child: const Icon(Icons.fact_check_outlined, color: Colors.white, size: 15),
                ),
                const SizedBox(width: 8),
                // The product name, the same in every language.
                Text(
                  'Facify',
                  style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                ),
                const SizedBox(width: 12),
                // When the evidence was gathered travels with the verdict, here
                // as everywhere: a correction without it is a claim about the
                // present made from evidence about the past.
                Expanded(
                  child: Text(
                    l10n.evidenceRetrievedAt(verdict.retrievedAt.toLocal()),
                    style: muted,
                    textAlign: TextAlign.end,
                  ),
                ),
              ],
            ),
          ),
          Container(
            color: style.container,
            padding: const EdgeInsets.all(16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(style.icon, color: style.onContainer, size: 26),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        style.headline,
                        style: theme.textTheme.titleMedium?.copyWith(
                          color: style.onContainer,
                          fontWeight: FontWeight.w700,
                          height: 1.2,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        style.subhead,
                        style: theme.textTheme.bodySmall?.copyWith(color: style.onContainer),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 2),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const EnglishOnlyNote(padding: EdgeInsets.only(bottom: 10)),
                if (decided.isEmpty)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Text(l10n.correctionNoSource, style: theme.textTheme.bodyMedium),
                  ),
                for (final claim in decided) _CardClaim(claim: claim),
              ],
            ),
          ),
          const Divider(height: 1),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
            child: Text(l10n.correctionCardFooter, style: muted),
          ),
        ],
      ),
    );
  }
}

class _CardClaim extends StatelessWidget {
  const _CardClaim({required this.claim});

  final Claim claim;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final muted = theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '“${claim.text}”',
            style: theme.textTheme.bodyLarge?.copyWith(fontWeight: FontWeight.w600, height: 1.3),
          ),
          const SizedBox(height: 4),
          Text(claim.reason, style: theme.textTheme.bodySmall),
          const SizedBox(height: 4),
          for (final evidence in claim.evidence.take(correctionSourcesPerClaim))
            Padding(
              padding: const EdgeInsets.only(top: 3),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.link, size: 14, color: theme.colorScheme.primary),
                  const SizedBox(width: 6),
                  Expanded(child: Text(_source(evidence, l10n), style: muted)),
                ],
              ),
            ),
        ],
      ),
    );
  }

  /// "Publisher · site · date", from whatever the source actually supplied.
  static String _source(Evidence evidence, AppLocalizations l10n) {
    final host = Uri.tryParse(evidence.citationUrl)?.host.replaceFirst(RegExp(r'^www\.'), '');
    final observed = evidence.observedAt;
    final parts = [
      evidence.publisher,
      if (host != null && host.isNotEmpty && host != evidence.publisher) host,
      if (observed != null) DateFormat('d MMM yyyy', l10n.localeName).format(observed.toLocal()),
    ].whereType<String>().toList();
    return parts.isEmpty ? l10n.correctionSourceFallback : parts.join(' · ');
  }
}
