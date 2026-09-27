/// The correction card (v5, 2.6): the verdict as a picture, for the chat the content
/// came from.
///
/// A picture because that is what travels in a group. The claim most likely
/// arrived as one, a pasted paragraph gets skimmed, and a bare link loses its
/// preview. The card carries the verdict word in its colour, how sure the sources
/// make us, the claim, the one-line summary and who said so. The links travel as
/// text beside it ([correctionMessage]), because a URL drawn into an image cannot be
/// tapped.
///
/// Built only from cited findings. Advisory signals never appear on it: the card
/// leaves the app without the advisory panel's exclusion header, so it must not
/// carry anything that would need one.
library;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../l10n/app_localizations.dart';
import '../l10n/phrases.dart';
import '../models/correction_message.dart';
import '../models/verdict.dart';
import '../theme/tokens.dart';
import '../theme/typography.dart';
import 'action_style.dart';

/// The width the card is drawn at, in logical pixels. Captured at 3x, that is a
/// 1080-pixel-wide picture: sharp on any phone, and small enough for any chat.
const double correctionCardWidth = 360;

/// Publishers named on the card, as chips.
const int _chips = 3;

/// Links sent beside the message.
const int _links = 2;

/// The summary in the message is cut here, at a word.
const int _summaryCharacters = 280;

/// The citations behind the verdict, best first - the ones a correction may name.
///
/// From the most important claim that decided the verdict, and only those pointing
/// the verdict's way: a source that supports a claim never stands behind "false".
/// Stronger tiers come before weaker, credible publishers before others. The same
/// order the server uses for the message, so the card and the note name one source.
List<Evidence> decidingSources(Verdict verdict) {
  final (statuses, directions) = switch (verdict.factVerdict) {
    FactVerdict.falseClaim => ({ClaimStatus.contradicted}, {'contradicts'}),
    FactVerdict.misleading => (
      {ClaimStatus.misleadingContext, ClaimStatus.contradicted},
      {'contradicts', 'contextualizes', 'context'},
    ),
    FactVerdict.trueClaim => ({ClaimStatus.supported}, {'supports'}),
    FactVerdict.unconfirmed => (<ClaimStatus>{}, <String>{}),
  };
  const importance = ['HEADLINE', 'MAIN_THESIS', 'SUPPORTING_DETAIL', 'BACKGROUND'];
  const tiers = ['A', 'B', 'C', 'D'];
  const credibility = ['HIGH', 'MEDIUM'];
  int rank(List<String> order, String? value) {
    final at = order.indexOf(value ?? '');
    return at < 0 ? order.length : at;
  }

  final claims = verdict.claims.where((c) => statuses.contains(c.status)).toList()
    ..sort((a, b) => rank(importance, a.importance).compareTo(rank(importance, b.importance)));
  for (final claim in claims) {
    final cited = claim.evidence.where((e) => directions.contains(e.direction)).toList();
    if (cited.isEmpty) continue;
    // A stable sort, so equal sources keep the order the server gave them.
    return _bestFirst(cited, (e) => (rank(tiers, e.tier), rank(credibility, e.credibility)));
  }
  return const [];
}

List<Evidence> _bestFirst(List<Evidence> items, (int, int) Function(Evidence) key) {
  final indexed = items.indexed.toList()
    ..sort((a, b) {
      final (a1, a2) = key(a.$2);
      final (b1, b2) = key(b.$2);
      return a1 != b1 ? a1.compareTo(b1) : (a2 != b2 ? a2.compareTo(b2) : a.$1.compareTo(b.$1));
    });
  return [for (final (_, item) in indexed) item];
}

/// The polite note sent with the picture, in [l10n]'s language.
///
/// Built here the way the server builds it (`POST /v1/cases/{id}/correction-text`),
/// for when the server cannot be reached. A decided verdict always names the source
/// behind it, with the link; Unconfirmed never says "false" and names no source. The
/// summary is written in English, so only the English note carries it.
CorrectionMessage correctionMessage(Verdict verdict, AppLocalizations l10n) {
  final sources = decidingSources(verdict);
  final says = switch (verdict.factVerdict) {
    FactVerdict.falseClaim => l10n.correctionSaysFalse,
    FactVerdict.misleading => l10n.correctionSaysMisleading,
    FactVerdict.trueClaim => l10n.correctionSaysTrue,
    FactVerdict.unconfirmed => null,
  };
  if (says == null || sources.isEmpty) {
    return CorrectionMessage(message: l10n.correctionUnconfirmedMessage);
  }
  final top = sources.first;
  final summary = l10n.localeName == 'en' ? _shortened(verdict.summary ?? '') : '';
  // A sentence ends in a full stop in English, a purna viram in Hindi.
  final stop = l10n.localeName == 'hi' ? '।' : '.';
  final said = summary.isEmpty ? '$says$stop' : '$says: $summary';
  return CorrectionMessage(
    message: '${l10n.correctionOpening} $said ${l10n.describeSource(top)}: ${top.citationUrl}',
    links: sources.map((e) => e.citationUrl).toSet().take(_links).toList(),
  );
}

/// Where one sentence ends and the next begins. A dot inside a name
/// (factcheck.afp.com) has no space after it, so it is not an end.
final RegExp _sentenceEnd = RegExp(r'(?<=[.!?])\s+(?=[A-Z0-9"“(])');

/// The first sentence of a result's summary. A summary can run to several
/// sentences; the card and the note carry one, as the design does.
String firstSentence(String summary) {
  final text = summary.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).join(' ');
  final first = text.split(_sentenceEnd).first;
  // A first "sentence" this short is an abbreviation ("Dr."), not a sentence.
  return first.length >= 20 ? first : text;
}

String _shortened(String summary) {
  var text = firstSentence(summary);
  if (text.length > _summaryCharacters) {
    final cut = text.substring(0, _summaryCharacters);
    final space = cut.lastIndexOf(' ');
    text = '${(space > 0 ? cut.substring(0, space) : cut).replaceFirst(RegExp(r'[,;:]$'), '')}…';
  } else if (text.isNotEmpty && !'.!?…'.contains(text[text.length - 1])) {
    text = '$text.';
  }
  return text;
}

/// What travels beside the picture: the note as the person left it, and any source
/// link it does not already carry, one to a line.
String correctionShareText(String note, List<String> links) {
  final extra = links.where((link) => !note.contains(link));
  return [note.trim(), ...extra].where((part) => part.isNotEmpty).join('\n');
}

class CorrectionCard extends StatelessWidget {
  const CorrectionCard({required this.verdict, super.key});

  final Verdict verdict;

  /// Always the light colours. The picture is seen in someone else's chat, on
  /// someone else's theme, and a dark card dropped into a light chat reads as a
  /// screenshot of an app rather than as a message.
  static const FactifyTokens _k = FactifyTokens.light;

  @override
  Widget build(BuildContext context) {
    const k = _k;
    final l10n = AppLocalizations.of(context);
    final word = ActionStyle.label(verdict, l10n);
    final (tone, _) = verdict.nothingToCheck
        ? (k.uC, k.uS)
        : ActionStyle.colours(verdict.factVerdict, k);
    final confidence = verdict.confidence;
    final claim = verdict.headline;
    final summary = _summary(l10n);
    final chips = decidingSources(
      verdict,
    ).map(l10n.describeSource).where((w) => w.isNotEmpty).toSet().take(_chips);
    final checked = DateFormat('d MMM', l10n.localeName).format(verdict.retrievedAt.toLocal());

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: k.sf, borderRadius: BorderRadius.circular(18)),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 20,
                height: 20,
                decoration: BoxDecoration(color: k.acc, borderRadius: BorderRadius.circular(6)),
                child: const Icon(Icons.check_rounded, size: 13, color: Colors.white),
              ),
              const SizedBox(width: 6),
              // The product name, the same in every language.
              Text(
                'Factify',
                style: FactifyText.serif(15, weight: FontWeight.w600, color: k.ink),
              ),
              const SizedBox(width: 12),
              // When the evidence was gathered travels with the verdict, here as
              // everywhere: a correction without it is a claim about the present
              // made from evidence about the past.
              Expanded(
                child: Text(
                  l10n.correctionChecked(checked).toUpperCase(),
                  textAlign: TextAlign.end,
                  style: FactifyText.mono(9.5, color: k.ink3, spacing: 0.6),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Wrap(
            crossAxisAlignment: WrapCrossAlignment.end,
            spacing: 8,
            runSpacing: 4,
            children: [
              Text(
                word,
                style: FactifyText.serif(
                  40,
                  weight: FontWeight.w600,
                  color: tone,
                ).copyWith(height: 1, letterSpacing: -1.2),
              ),
              // Only a decided verdict has a confidence; Unconfirmed has none.
              if (confidence != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text(
                    l10n.confidence(confidence),
                    style: FactifyText.sans(12, weight: FontWeight.w600, color: k.ink2),
                  ),
                ),
            ],
          ),
          if (claim != null) ...[
            const SizedBox(height: 8),
            Text(
              '“$claim”',
              style: FactifyText.serif(
                14,
                weight: FontWeight.w400,
                color: k.ink2,
              ).copyWith(fontStyle: FontStyle.italic, height: 1.4),
            ),
          ],
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: SizedBox(
              height: 1,
              width: double.infinity,
              child: ColoredBox(color: k.line),
            ),
          ),
          Text(summary, style: FactifyText.sans(12.5, color: k.ink).copyWith(height: 1.5)),
          if (chips.isNotEmpty) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final who in chips)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(color: k.sf2, borderRadius: BorderRadius.circular(7)),
                    child: Text(
                      who,
                      style: FactifyText.sans(10.5, weight: FontWeight.w600, color: k.ink2),
                    ),
                  ),
              ],
            ),
          ],
          const SizedBox(height: 12),
          Text(l10n.correctionCardFooter, style: FactifyText.sans(9.5, color: k.ink3)),
        ],
      ),
    );
  }

  /// The first sentence of the result's summary, or the deciding claim's reason, or - with nothing
  /// decided - that no published source settled it.
  String _summary(AppLocalizations l10n) {
    final summary = firstSentence(verdict.summary ?? '');
    if (summary.isNotEmpty) return summary;
    final decided = verdict.claims.where((c) => c.isDecisive && c.reason.isNotEmpty);
    return decided.isEmpty ? l10n.correctionNoSource : decided.first.reason;
  }
}
