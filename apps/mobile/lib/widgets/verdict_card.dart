/// The result (v5): the verdict, how sure it is, and everything it rests on.
///
/// Built for a person who opened the app from a chat in a hurry. The tinted top
/// answers the question they came with - is it true? - in the verdict's own colour
/// and word; everything below it is there to let them trust that answer or check
/// it: what was checked, with each claim underlined in its colour; each claim and
/// why it stands where it does; and the sources, each opening the page it was
/// quoted from.
///
/// Rules that survive from the evidence-first design this replaced:
///
///   * True, False and Misleading only ever appear with sources beneath them. The
///     server never sends a decided verdict without citations, and this card shows
///     them rather than asking to be believed.
///   * "Unconfirmed" is grey, never red. It means the sources did not settle the
///     claim, which is a different answer from "this is false".
///   * Confidence (50-97) is shown only for a decided verdict; it is arithmetic on
///     the sources, never a model's score.
///   * Advisories - forensic signals - are never evidence and never change it.
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart' hide TextDirection;

import '../l10n/app_localizations.dart';
import '../models/submission.dart';
import '../models/verdict.dart';
import 'action_style.dart';
import 'claim_spans.dart';
import 'claim_words.dart';
import 'picture_checks.dart';
import 'english_only_note.dart';
import 'teaching_line.dart';
import 'ui/ui.dart';

/// Where the receipt check stands.
enum ReceiptState { checking, verified, failed }

/// Two or more line breaks with only spaces between: a paragraph gap.
final RegExp _blankLines = RegExp(r'\n\s*\n');

class VerdictCard extends StatelessWidget {
  const VerdictCard({
    super.key,
    required this.verdict,
    this.kind = SubmissionKind.text,
    this.submittedText,
    this.thumbnail,
    this.onWhy,
    this.onOpenClaim,
    this.onOpenSource,
    this.onReportForReview,
    this.reporting = false,
    this.reported = false,
    this.receipt,
    this.receiptId,
    this.serverUrl,
    this.onOpenPage,
  });

  final Verdict verdict;
  final SubmissionKind kind;

  /// The text that was checked, when it was text: underlined claim by claim.
  final String? submittedText;
  final Uint8List? thumbnail;

  /// Opens the "Why" sheet.
  final VoidCallback? onWhy;

  /// Opens one claim with all of its evidence.
  final ValueChanged<Claim>? onOpenClaim;

  /// Opens one source.
  final ValueChanged<Evidence>? onOpenSource;

  /// Where the picture checks' copies of earlier appearances are served from.
  final String? serverUrl;

  /// Opens a page where the picture appeared before.
  final ValueChanged<String>? onOpenPage;

  /// Reports this result as wrong. Null once reported.
  final VoidCallback? onReportForReview;
  final bool reporting;
  final bool reported;

  /// The signed receipt, when one was issued; its id as shown.
  final ReceiptState? receipt;
  final String? receiptId;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final nothing = verdict.nothingToCheck;
    final (strong, soft) = nothing ? (k.uC, k.uS) : ActionStyle.colours(verdict.factVerdict, k);
    // The tint is laid over the page, so dark mode's translucent tints read the same.
    final tint = Color.alphaBlend(soft, k.bg);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          key: const ValueKey('verdict-header'),
          color: tint,
          child: _Header(verdict: verdict, strong: strong, soft: soft, onWhy: onWhy),
        ),
        Container(
          color: tint,
          child: Container(
            decoration: BoxDecoration(
              color: k.bg,
              borderRadius: const BorderRadius.vertical(top: Radius.circular(28)),
            ),
            padding: const EdgeInsets.fromLTRB(14, 16, 14, 20),
            child: _Body(card: this),
          ),
        ),
      ],
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({
    required this.verdict,
    required this.strong,
    required this.soft,
    required this.onWhy,
  });

  final Verdict verdict;
  final Color strong;
  final Color soft;
  final VoidCallback? onWhy;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final locale = Localizations.localeOf(context).toLanguageTag();
    final style = ActionStyle.forVerdict(verdict, k.brightness, l10n);
    final nothing = verdict.nothingToCheck;
    final decided = verdict.factVerdict.isDecided;
    final confidence = decided ? verdict.confidence : null;
    final size = switch (verdict.factVerdict) {
      FactVerdict.misleading => 44.0,
      FactVerdict.unconfirmed => 38.0,
      _ => 68.0,
    };
    final summary = decided
        ? (verdict.summary ?? verdict.actionReason)
        : nothing
        ? (verdict.imageReading != null ? l10n.nothingToCheckPicture : l10n.nothingToCheckText)
        : l10n.unconfirmedBody;

    return Padding(
      padding: const EdgeInsets.fromLTRB(22, 22, 22, 22),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Semantics(
            container: true,
            label: confidence != null
                ? l10n.verdictSemantics(style.headline, confidence)
                : style.headline,
            excludeSemantics: true,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Icon(style.icon, size: 16, color: strong),
                          const SizedBox(width: 6),
                          Text(l10n.verdictOverline, style: FactifyText.mono(10.5, color: strong)),
                        ],
                      ),
                      const SizedBox(height: 8),
                      FittedBox(
                        fit: BoxFit.scaleDown,
                        alignment: AlignmentDirectional.centerStart,
                        child: Text(
                          style.headline,
                          maxLines: 1,
                          style: FactifyText.verdict(nothing ? 38 : size, strong),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 10),
                if (confidence != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Column(
                      children: [
                        FxConfidenceRing(value: confidence, colour: strong, tint: soft),
                        const SizedBox(height: 6),
                        _Chip(
                          label: l10n.confidenceChip,
                          accent: strong,
                          onTap: onWhy,
                          height: 26,
                          fontSize: 11,
                        ),
                      ],
                    ),
                  )
                else if (!nothing)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: _Chip(
                      label: l10n.whyChip,
                      accent: strong,
                      onTap: onWhy,
                      height: 30,
                      fontSize: 12,
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          Text(
            style.subhead,
            style: FactifyText.sans(15, weight: FontWeight.w600, color: k.ink),
          ),
          const SizedBox(height: 6),
          Text(summary, style: FactifyText.sans(13.5, color: k.ink2).copyWith(height: 1.5)),
          // Summaries and quotes arrive in the language of the claim, not the app's;
          // a Hindi reader is told so rather than surprised.
          const EnglishOnlyNote(padding: EdgeInsets.only(top: 8)),
          if (verdict.fromCache) ...[
            const SizedBox(height: 12),
            Container(
              height: 28,
              padding: const EdgeInsets.symmetric(horizontal: 11),
              decoration: BoxDecoration(color: k.sf, borderRadius: BorderRadius.circular(14)),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(FxIcons.history, size: 15, color: k.ink2),
                  const SizedBox(width: 6),
                  Flexible(
                    child: Text(
                      l10n.checkedEarlierOn(
                        DateFormat('d MMM', locale).format(verdict.retrievedAt.toLocal()),
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: FactifyText.sans(12, weight: FontWeight.w600, color: k.ink2),
                    ),
                  ),
                ],
              ),
            ),
          ],
          if (verdict.searchUnavailable)
            _Note(text: l10n.searchUnavailableNote)
          else if (verdict.completenessNote != null)
            _Note(text: l10n.incompleteNote),
        ],
      ),
    );
  }
}

/// "confidence ⓘ" and "Why? ⓘ": the way into the Why sheet.
class _Chip extends StatelessWidget {
  const _Chip({
    required this.label,
    required this.accent,
    required this.onTap,
    required this.height,
    required this.fontSize,
  });

  final String label;
  final Color accent;
  final VoidCallback? onTap;
  final double height;
  final double fontSize;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Padding(
          padding: EdgeInsets.symmetric(vertical: (44 - height) / 2),
          child: Container(
            height: height,
            padding: EdgeInsetsDirectional.fromSTEB(height * 0.36, 0, height * 0.24, 0),
            decoration: BoxDecoration(color: k.sf, borderRadius: BorderRadius.circular(height / 2)),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  label,
                  style: FactifyText.sans(fontSize, weight: FontWeight.w600, color: k.ink2),
                ),
                const SizedBox(width: 3),
                Icon(FxIcons.info, size: 16, color: accent),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Note extends StatelessWidget {
  const _Note({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Container(
      margin: const EdgeInsets.only(top: 12),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(color: k.sf, borderRadius: BorderRadius.circular(14)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(FxIcons.info, size: 16, color: k.mC),
          const SizedBox(width: 8),
          Expanded(
            child: Text(text, style: FactifyText.sans(12.5, color: k.ink2).copyWith(height: 1.45)),
          ),
        ],
      ),
    );
  }
}

class _Body extends StatelessWidget {
  const _Body({required this.card});

  final VerdictCard card;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final t = FactifyText.of(context);
    final l10n = AppLocalizations.of(context);
    final verdict = card.verdict;
    final nothing = verdict.nothingToCheck;
    final claims = nothing
        ? const <Claim>[]
        : verdict.claims.where((c) => c.claimType != 'MEDIA' || c.isDecisive).toList();
    final sources = _sources(verdict);
    final media = verdict.claims.expand((c) => c.evidence).where((e) => e.isMediaMatch).firstOrNull;
    final technique = _technique(verdict);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _WhatWeChecked(card: card),
        if (media != null && verdict.factVerdict != FactVerdict.trueClaim) ...[
          const SizedBox(height: 10),
          _MediaMatch(evidence: media, thumbnail: card.thumbnail),
        ],
        if (verdict.mediaReport case final report?) ...[
          _SectionTitle(
            title: report.isVideo ? l10n.pcTitleVideo : l10n.pcTitle,
            note: report.frames == null
                ? l10n.pcNote
                : '${l10n.pcFrames(report.frames!)} · ${l10n.pcNote}',
          ),
          PictureChecks(
            report: report,
            thumbnail: card.thumbnail,
            serverUrl: card.serverUrl,
            onOpenPage: card.onOpenPage,
          ),
        ],
        if (claims.isNotEmpty) ...[
          _SectionTitle(title: l10n.claimCount(claims.length), note: _statusNote(claims, l10n)),
          FxListCard(
            children: [
              for (final claim in claims)
                _ClaimRow(
                  claim: claim,
                  onTap: card.onOpenClaim == null ? null : () => card.onOpenClaim!(claim),
                ),
            ],
          ),
        ],
        if (technique != null && verdict.factVerdict.isDecided) ...[
          const SizedBox(height: 10),
          _TechniqueCard(technique: technique),
        ],
        if (sources.isNotEmpty) ...[
          _SectionTitle(title: l10n.sourcesTitle, note: l10n.tapToRead),
          SizedBox(
            height: 196,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              clipBehavior: Clip.none,
              padding: const EdgeInsets.only(bottom: 4),
              itemCount: sources.length,
              separatorBuilder: (_, _) => const SizedBox(width: 10),
              itemBuilder: (context, i) => _SourceCard(
                evidence: sources[i],
                onTap: card.onOpenSource == null ? null : () => card.onOpenSource!(sources[i]),
              ),
            ),
          ),
        ] else if (!verdict.factVerdict.isDecided && !nothing) ...[
          const SizedBox(height: 10),
          FxCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(FxIcons.search, size: 17, color: k.ink),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        l10n.noSourceTitle,
                        style: FactifyText.sans(14, weight: FontWeight.w600, color: k.ink),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  l10n.noSourceBody,
                  style: FactifyText.sans(12.5, color: k.ink2).copyWith(height: 1.5),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(6, 22, 6, 10),
            child: Text(l10n.limitsTitle, style: t.section),
          ),
          FxListCard(
            children: [
              for (final (icon, text) in [
                (FxIcons.hidden, l10n.limitUnreported),
                (FxIcons.lock, l10n.limitPrivate),
                (FxIcons.person, l10n.limitIntent),
              ])
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(icon, size: 16, color: k.ink3),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          text,
                          style: FactifyText.sans(12.5, color: k.ink2).copyWith(height: 1.5),
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ],
        if (card.receipt != null) ...[
          const SizedBox(height: 14),
          _ReceiptSeal(state: card.receipt!, id: card.receiptId),
        ],
        Padding(
          padding: const EdgeInsets.fromLTRB(6, 16, 6, 0),
          // A Wrap, not a Row: in Hindi the two do not fit on one line at phone
          // width, and the report link drops below instead of overflowing.
          child: Wrap(
            alignment: WrapAlignment.spaceBetween,
            crossAxisAlignment: WrapCrossAlignment.center,
            runSpacing: 4,
            children: [
              Text(
                l10n.checkedAt(verdict.retrievedAt.toLocal()),
                style: FactifyText.sans(12, color: k.ink3),
              ),
              Semantics(
                button: true,
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: card.reporting || card.reported ? null : card.onReportForReview,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (card.reporting)
                          const SizedBox(
                            width: 14,
                            height: 14,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        else
                          Icon(FxIcons.report, size: 15, color: k.ink2),
                        const SizedBox(width: 4),
                        Flexible(
                          child: Text(
                            card.reported
                                ? l10n.reportedNote
                                : card.reporting
                                ? l10n.reporting
                                : l10n.report,
                            style: FactifyText.sans(12, weight: FontWeight.w600, color: k.ink2),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  /// Every page cited, once, the ones that decided the verdict first.
  static List<Evidence> _sources(Verdict verdict) {
    final seen = <String>{};
    final all = <Evidence>[];
    for (final claim in verdict.claims) {
      for (final e in claim.evidence) {
        if (e.direction == 'risk_signal' || e.isMediaMatch) continue;
        if (seen.add(e.citationUrl)) all.add(e);
      }
    }
    final leading = switch (verdict.factVerdict) {
      FactVerdict.falseClaim => 'contradicts',
      FactVerdict.trueClaim => 'supports',
      _ => null,
    };
    if (leading != null) {
      all.sort(
        (a, b) => (b.direction == leading ? 1 : 0).compareTo(a.direction == leading ? 1 : 0),
      );
    }
    return all;
  }

  /// The manipulation technique to teach: the server's (contract 1.3), else the
  /// app's own rule over the evidence (teaching_line.dart).
  static Technique? _technique(Verdict verdict) {
    for (final claim in verdict.claims) {
      final named = switch (claim.technique) {
        'RECYCLED_MEDIA' => Technique.recycledMedia,
        'MISSING_CONTEXT' => Technique.missingContext,
        'MISATTRIBUTED_QUOTE' => Technique.misattributedQuote,
        'TWISTED_NUMBER' => Technique.twistedNumber,
        'WRONG_IDENTITY' => Technique.wrongIdentity,
        _ => techniqueFor(claim),
      };
      if (named != null) return named;
    }
    return null;
  }

  /// "2 contradicted · 1 unconfirmed".
  static String _statusNote(List<Claim> claims, AppLocalizations l10n) {
    const order = [
      ClaimStatus.contradicted,
      ClaimStatus.misleadingContext,
      ClaimStatus.supported,
      ClaimStatus.unverified,
    ];
    return [
      for (final status in order)
        if (claims.any((c) => c.status == status))
          l10n.claimStateCount(
            claims.where((c) => c.status == status).length,
            claimStateLabel(status, l10n).toLowerCase(),
          ),
    ].join(' · ');
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({required this.title, this.note});

  final String title;
  final String? note;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(6, 22, 6, 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.baseline,
        textBaseline: TextBaseline.alphabetic,
        children: [
          Text(title, style: FactifyText.of(context).section),
          const SizedBox(width: 12),
          if (note != null)
            Expanded(
              child: Text(
                note!,
                textAlign: TextAlign.end,
                maxLines: 2,
                style: FactifyText.sans(12, color: k.ink3),
              ),
            ),
        ],
      ),
    );
  }
}

/// What was checked, quoted, with each claim underlined in its colour and a key.
///
/// A long text is quoted from its start, and opens in full on request: what was
/// read in a picture is shown exactly, all of it, for anyone who wants to see it.
class _WhatWeChecked extends StatefulWidget {
  const _WhatWeChecked({required this.card});

  final VerdictCard card;

  @override
  State<_WhatWeChecked> createState() => _WhatWeCheckedState();
}

class _WhatWeCheckedState extends State<_WhatWeChecked> {
  bool _whole = false;

  @override
  Widget build(BuildContext context) {
    final card = widget.card;
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final verdict = card.verdict;
    final reading = verdict.imageReading;
    final headline = verdict.headline;

    final String kindLabel;
    switch (card.kind) {
      case SubmissionKind.text:
        kindLabel = l10n.kindText;
      case SubmissionKind.link:
        final host = Uri.tryParse(card.submittedText ?? '')?.host.replaceFirst('www.', '');
        kindLabel = host == null || host.isEmpty ? l10n.kindLink : '${l10n.kindLink} · $host';
      case SubmissionKind.image:
        // A shared video arrives as a file like a picture; the server says which.
        kindLabel = (verdict.mediaReport?.isVideo ?? false) ? l10n.kindVideo : l10n.kindImage;
      case SubmissionKind.document:
        kindLabel = l10n.kindPdf;
    }

    // Text is quoted as sent; a picture as it was read; a link or a PDF by the
    // claim it was checked for, since its whole page is not on this phone.
    final fromPicture =
        card.kind == SubmissionKind.image && (reading?.text.trim().isNotEmpty ?? false);
    var quote = switch (card.kind) {
      SubmissionKind.text => card.submittedText ?? headline ?? '',
      // A reading keeps a blank line between the blocks of the picture; shown as a
      // quote, one line apart is enough.
      SubmissionKind.image when fromPicture => reading!.text.replaceAll(_blankLines, '\n'),
      // A picture with no text has nothing to quote. Its only claim is the server's
      // own question about it ("This image has been published before...") and was
      // shown here, labelled as the picture's text, on a landscape with none.
      SubmissionKind.image => '',
      _ => headline ?? '',
    }.trim();
    const limit = 600;
    final long = quote.length > limit;
    final shortened = long && !_whole;
    if (shortened) quote = quote.substring(0, limit);
    final spans = verdict.nothingToCheck
        ? const <ClaimSpan>[]
        : locateClaims(quote, verdict.claims, useAnchors: card.kind == SubmissionKind.text);
    final keys = {for (final s in spans) s.status}.toList();

    return FxCard(
      padding: const EdgeInsets.fromLTRB(14, 13, 14, 13),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              if (card.thumbnail != null)
                ClipRRect(
                  borderRadius: BorderRadius.circular(6),
                  child: Image.memory(
                    card.thumbnail!,
                    width: 22,
                    height: 22,
                    fit: BoxFit.cover,
                    errorBuilder: (_, _, _) =>
                        Icon(FxIcons.forKind(card.kind), size: 14, color: k.ink3),
                  ),
                )
              else
                Icon(FxIcons.forKind(card.kind), size: 14, color: k.ink3),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  l10n.whatWeCheckedKind(kindLabel),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: FactifyText.sans(11.5, weight: FontWeight.w600, color: k.ink3),
                ),
              ),
            ],
          ),
          if (reading != null && card.kind != SubmissionKind.text) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                if (reading.kind != null)
                  FxChip(label: l10n.imageKind(reading.kind!), height: 26, fontSize: 11.5),
                if ((reading.publisher ?? '').trim().isNotEmpty)
                  FxChip(label: l10n.shows(reading.publisher!.trim()), height: 26, fontSize: 11.5),
              ],
            ),
            if ((reading.description ?? '').trim().isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                reading.description!,
                style: FactifyText.sans(13, color: k.ink2).copyWith(height: 1.5),
              ),
            ],
            if (fromPicture && quote.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(
                l10n.textInPicture,
                style: FactifyText.sans(11.5, weight: FontWeight.w600, color: k.ink3),
              ),
            ],
          ],
          if (quote.isNotEmpty) ...[
            const SizedBox(height: 8),
            _Underlined(text: quote, spans: spans, shortened: shortened),
            if (long)
              Semantics(
                button: true,
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () => setState(() => _whole = !_whole),
                  child: Padding(
                    padding: const EdgeInsets.only(top: 8, bottom: 4),
                    child: Text(
                      _whole ? l10n.imageShowLessText : l10n.imageShowAllText,
                      style: FactifyText.sans(12.5, weight: FontWeight.w600, color: k.acc),
                    ),
                  ),
                ),
              ),
          ] else if (card.kind == SubmissionKind.image && reading != null) ...[
            const SizedBox(height: 8),
            Text(l10n.imageNoText, style: FactifyText.sans(12, color: k.ink3)),
          ],
          if (keys.isNotEmpty) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 12,
              runSpacing: 4,
              children: [
                for (final status in keys)
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 14,
                        height: 2,
                        decoration: BoxDecoration(
                          color: ActionStyle.forStatus(status, k.brightness),
                          borderRadius: BorderRadius.circular(1),
                        ),
                      ),
                      const SizedBox(width: 5),
                      Text(
                        claimStateLabel(status, l10n),
                        style: FactifyText.sans(11, color: k.ink3),
                      ),
                    ],
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _Underlined extends StatelessWidget {
  const _Underlined({required this.text, required this.spans, required this.shortened});

  final String text;
  final List<ClaimSpan> spans;
  final bool shortened;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final base = FactifyText.serif(
      16.5,
      weight: FontWeight.w400,
      color: k.ink,
    ).copyWith(height: 1.5);
    final parts = <InlineSpan>[const TextSpan(text: '“')];
    var at = 0;
    for (final span in spans) {
      if (span.start > at) parts.add(TextSpan(text: text.substring(at, span.start)));
      parts.add(
        TextSpan(
          text: text.substring(span.start, span.end),
          style: TextStyle(
            decoration: TextDecoration.underline,
            decorationColor: ActionStyle.forStatus(span.status, k.brightness),
            decorationThickness: 2,
            backgroundColor: ActionStyle.tintForStatus(span.status, k.brightness),
          ),
        ),
      );
      at = span.end;
    }
    if (at < text.length) parts.add(TextSpan(text: text.substring(at)));
    parts.add(TextSpan(text: shortened ? '…”' : '”'));
    return Text.rich(TextSpan(children: parts), style: base);
  }
}

/// The picture checked beside the earlier copy it matched (Misleading, recycled).
class _MediaMatch extends StatelessWidget {
  const _MediaMatch({required this.evidence, required this.thumbnail});

  final Evidence evidence;
  final Uint8List? thumbnail;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final locale = Localizations.localeOf(context).toLanguageTag();
    final seen = evidence.observedAt;

    Widget tile(Color stripe, Color ink, String label, Uint8List? image) => Container(
      height: 92,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(borderRadius: BorderRadius.circular(14), color: k.bg),
      child: image != null
          ? Image.memory(image, fit: BoxFit.cover)
          : CustomPaint(
              painter: _Stripes(stripe),
              child: Center(
                child: Text(label, style: FactifyText.mono(9, color: ink, spacing: 1)),
              ),
            ),
    );

    return FxCard(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    tile(k.sf2, k.ink3, l10n.mediaYourPicture, thumbnail),
                    const SizedBox(height: 6),
                    Text(
                      l10n.yourPicture,
                      style: FactifyText.sans(11.5, weight: FontWeight.w600, color: k.ink),
                    ),
                    Text(l10n.mediaSharedToday, style: FactifyText.sans(11, color: k.ink3)),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    tile(k.mS, k.mC, l10n.mediaEarlierCopy, null),
                    const SizedBox(height: 6),
                    Text(
                      seen == null
                          ? l10n.mediaEarlierCopy
                          : l10n.mediaPublished(DateFormat('d MMM yyyy', locale).format(seen)),
                      style: FactifyText.sans(11.5, weight: FontWeight.w600, color: k.ink),
                    ),
                    Text(
                      l10n.mediaMatchedBy(evidence.sourceName),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: FactifyText.sans(11, color: k.ink3),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Icon(FxIcons.recycled, size: 16, color: k.mC),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  l10n.mediaMatchesEarlier,
                  style: FactifyText.sans(12.5, weight: FontWeight.w600, color: k.mC),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Stripes extends CustomPainter {
  _Stripes(this.colour);

  final Color colour;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = colour
      ..strokeWidth = 6;
    for (double x = -size.height; x < size.width + size.height; x += 12) {
      canvas.drawLine(Offset(x, size.height), Offset(x + size.height, 0), paint);
    }
  }

  @override
  bool shouldRepaint(_Stripes old) => old.colour != colour;
}

class _ClaimRow extends StatelessWidget {
  const _ClaimRow({required this.claim, this.onTap});

  final Claim claim;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final colour = ActionStyle.forStatus(claim.status, k.brightness);
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 28,
              height: 28,
              decoration: BoxDecoration(
                color: ActionStyle.tintForStatus(claim.status, k.brightness),
                shape: BoxShape.circle,
              ),
              child: Icon(ActionStyle.iconForStatus(claim.status), size: 17, color: colour),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    claim.text,
                    style: FactifyText.sans(
                      14,
                      weight: FontWeight.w500,
                      color: k.ink,
                    ).copyWith(height: 1.4),
                  ),
                  const SizedBox(height: 4),
                  Text.rich(
                    TextSpan(
                      children: [
                        TextSpan(
                          text: '${claimStateLabel(claim.status, l10n)}. ',
                          style: TextStyle(fontWeight: FontWeight.w600, color: colour),
                        ),
                        TextSpan(text: claimReason(claim, l10n)),
                      ],
                    ),
                    style: FactifyText.sans(12.5, color: k.ink3).copyWith(height: 1.45),
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

class _TechniqueCard extends StatelessWidget {
  const _TechniqueCard({required this.technique});

  final Technique technique;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final (title, lesson) = techniqueWords(technique, l10n);
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Color.alphaBlend(k.mS, k.bg),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(FxIcons.lightbulb, size: 15, color: k.mC),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  l10n.techniqueLabel.toUpperCase(),
                  style: FactifyText.mono(10, color: k.mC, spacing: 1),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            title,
            style: FactifyText.serif(19, weight: FontWeight.w400, color: k.ink),
          ),
          const SizedBox(height: 4),
          Text(lesson, style: FactifyText.sans(13, color: k.ink2).copyWith(height: 1.5)),
        ],
      ),
    );
  }
}

/// A source, 240 wide: who, what kind, which way it points, what it said, and when.
class _SourceCard extends StatelessWidget {
  const _SourceCard({required this.evidence, this.onTap});

  final Evidence evidence;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final locale = Localizations.localeOf(context).toLanguageTag();
    final direction = evidence.direction;
    final (dirC, dirS) = switch (direction) {
      'contradicts' => (k.fC, k.fS),
      'supports' => (k.tC, k.tS),
      _ => (k.mC, k.mS),
    };
    final seen = evidence.observedAt;
    final meta = [
      l10n.credibility(evidence.credibility ?? ''),
      if (seen != null) DateFormat('d MMM', locale).format(seen.toLocal()),
    ].join(' · ');

    return SizedBox(
      width: 240,
      child: FxCard(
        onTap: onTap,
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                FxSourceAvatar(
                  initials: FxSourceAvatar.initialsOf(evidence.sourceName),
                  radius: 10,
                  fontSize: 10,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        evidence.sourceName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: FactifyText.sans(13.5, weight: FontWeight.w600, color: k.ink),
                      ),
                      Text(
                        l10n.tierLabel(evidence.tier),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: FactifyText.sans(11, color: k.ink3),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 6),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(color: dirS, borderRadius: BorderRadius.circular(8)),
                  child: Text(
                    l10n.directionShort(direction),
                    style: FactifyText.sans(11, weight: FontWeight.w700, color: dirC),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 9),
            Expanded(
              child: Text(
                '“${evidence.sourceExcerpt.trim()}”',
                maxLines: 4,
                overflow: TextOverflow.ellipsis,
                style: FactifyText.serif(
                  14.5,
                  weight: FontWeight.w400,
                  color: k.ink,
                ).copyWith(height: 1.4),
              ),
            ),
            Row(
              children: [
                Expanded(
                  child: Text(
                    meta,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: FactifyText.sans(11.5, color: k.ink3),
                  ),
                ),
                Text(
                  l10n.readSource,
                  style: FactifyText.sans(11.5, weight: FontWeight.w600, color: k.acc),
                ),
                const SizedBox(width: 3),
                Icon(FxIcons.forward, size: 14, color: k.acc),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _ReceiptSeal extends StatelessWidget {
  const _ReceiptSeal({required this.state, required this.id});

  final ReceiptState state;
  final String? id;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final (icon, colour, title, body) = switch (state) {
      ReceiptState.verified => (
        FxIcons.receipt,
        k.acc,
        l10n.receiptVerifiedTitle,
        l10n.receiptVerifiedBody,
      ),
      ReceiptState.failed => (
        FxIcons.falseV,
        k.fC,
        l10n.receiptFailedTitle,
        l10n.receiptFailedBody,
      ),
      ReceiptState.checking => (FxIcons.receipt, k.ink3, l10n.receiptChecking, ''),
    };
    return CustomPaint(
      painter: _DashedBorder(k.line),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        child: Row(
          children: [
            Icon(icon, size: 20, color: colour),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: FactifyText.sans(12.5, weight: FontWeight.w600, color: k.ink),
                  ),
                  if (body.isNotEmpty) Text(body, style: FactifyText.sans(11.5, color: k.ink3)),
                ],
              ),
            ),
            if (id != null) ...[
              const SizedBox(width: 8),
              Text(id!, style: FactifyText.mono(10, color: k.ink3, spacing: 0.5)),
            ],
          ],
        ),
      ),
    );
  }
}

class _DashedBorder extends CustomPainter {
  _DashedBorder(this.colour);

  final Color colour;

  @override
  void paint(Canvas canvas, Size size) {
    final path = Path()
      ..addRRect(RRect.fromRectAndRadius(Offset.zero & size, const Radius.circular(16)));
    final paint = Paint()
      ..color = colour
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;
    for (final metric in path.computeMetrics()) {
      for (double d = 0; d < metric.length; d += 7) {
        canvas.drawPath(metric.extractPath(d, (d + 4).clamp(0, metric.length)), paint);
      }
    }
  }

  @override
  bool shouldRepaint(_DashedBorder old) => old.colour != colour;
}
