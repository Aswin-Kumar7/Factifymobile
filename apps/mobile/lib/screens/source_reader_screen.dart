/// The source reader (v5, 2.5): a cited passage, read where it sits in its article.
///
/// Opens with what the result already has - the publisher, the direction, the quoted
/// sentence - and fills in the headline, the date, the paragraph around the quote and
/// the article's picture from the server (`GET /v1/cases/{id}/sources/{evidence_id}`).
/// Only the passage and its neighbours are shown; the article itself is on the
/// publisher's page, one tap away. When the page cannot be read now, that is said,
/// and the quote the result rests on is still shown.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart' hide TextDirection;
import 'package:url_launcher/url_launcher.dart';

import '../api/client.dart';
import '../app_services.dart';
import '../l10n/app_localizations.dart';
import '../models/source_view.dart';
import '../models/verdict.dart';
import '../theme/icons.dart';
import '../theme/tokens.dart';
import '../theme/typography.dart';
import '../widgets/ui/fx_button.dart';

class SourceReaderScreen extends StatefulWidget {
  const SourceReaderScreen({
    required this.services,
    required this.caseId,
    required this.evidence,
    super.key,
  });

  final AppServices services;
  final String caseId;
  final Evidence evidence;

  @override
  State<SourceReaderScreen> createState() => _SourceReaderScreenState();
}

class _SourceReaderScreenState extends State<SourceReaderScreen> {
  SourceView? _view;
  bool _loading = true;

  Evidence get _evidence => widget.evidence;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final view = await widget.services.client.source(
        widget.caseId,
        _evidence.id,
        url: _evidence.citationUrl,
      );
      if (mounted) setState(() => _view = view);
    } on ApiFailure {
      // The citation itself is still shown, with the site one tap away.
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _openSite() {
    final uri = Uri.tryParse(_view?.url ?? _evidence.citationUrl);
    if (uri != null) unawaited(launchUrl(uri, mode: LaunchMode.externalApplication));
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final view = _view;
    final domain =
        view?.domain ?? (Uri.tryParse(_evidence.citationUrl)?.host.replaceFirst('www.', '') ?? '');
    final publisher = (view?.publisher ?? _evidence.publisher ?? '').trim();

    return Scaffold(
      backgroundColor: k.bg,
      body: SafeArea(
        child: Column(
          children: [
            _TopBar(
              publisher: publisher.isEmpty ? domain : publisher,
              domain: domain,
              onBack: () => Navigator.of(context).pop(),
              onOpen: _openSite,
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(22, 18, 22, 20),
                children: [
                  _Pills(evidence: _evidence),
                  if (view?.headline case final headline?) ...[
                    const SizedBox(height: 14),
                    Text(
                      headline,
                      style: FactifyText.serif(
                        27,
                        color: k.ink,
                      ).copyWith(height: 1.12, letterSpacing: -0.6),
                    ),
                  ],
                  if (_published(context, view) case final line?) ...[
                    const SizedBox(height: 8),
                    Text(line, style: FactifyText.sans(12, color: k.ink3)),
                  ],
                  if (view?.imageUrl case final image?) ...[
                    const SizedBox(height: 16),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(18),
                      child: SizedBox(
                        height: 150,
                        child: ColoredBox(
                          color: k.sf2,
                          child: Image.network(
                            '${widget.services.client.baseUrl}$image',
                            fit: BoxFit.cover,
                            width: double.infinity,
                            errorBuilder: (_, _, _) => const SizedBox.shrink(),
                          ),
                        ),
                      ),
                    ),
                  ],
                  const SizedBox(height: 16),
                  ..._passage(context, view),
                  if (_loading) ...[
                    const SizedBox(height: 16),
                    Row(
                      children: [
                        SizedBox.square(
                          dimension: 12,
                          child: CircularProgressIndicator(strokeWidth: 1.5, color: k.acc),
                        ),
                        const SizedBox(width: 8),
                        Text(l10n.srLoading, style: FactifyText.sans(12.5, color: k.ink3)),
                      ],
                    ),
                  ] else if (view == null || !view.complete) ...[
                    const SizedBox(height: 16),
                    _Note(
                      text: view == null || view.headline == null
                          ? l10n.srUnavailable
                          : l10n.srMoved,
                    ),
                  ] else ...[
                    const SizedBox(height: 16),
                    _Note(text: l10n.srOnlyPassage),
                  ],
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
              decoration: BoxDecoration(
                color: k.nav,
                border: Border(top: BorderSide(color: k.line)),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: FxButton(
                      label: l10n.srBack,
                      icon: FxIcons.back,
                      variant: FxButtonVariant.secondary,
                      height: 50,
                      onPressed: () => Navigator.of(context).pop(),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: FxButton(
                      label: l10n.srOpenSite,
                      trailingIcon: FxIcons.openExternal,
                      variant: FxButtonVariant.dark,
                      height: 50,
                      onPressed: _openSite,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  String? _published(BuildContext context, SourceView? view) {
    final l10n = AppLocalizations.of(context);
    // The article's own date; the day we read it is not when it was published.
    final date = view?.publishedAt ?? _evidence.publishedOn;
    final minutes = view?.readMinutes;
    final parts = [
      if (date != null)
        l10n.srPublished(
          DateFormat.yMMMd(Localizations.localeOf(context).toString()).format(date.toLocal()),
        ),
      if (minutes != null) l10n.srReadMinutes(minutes),
    ];
    return parts.isEmpty ? null : parts.join(' · ');
  }

  /// The paragraphs around the quote, the quote's own in the highlighted box.
  List<Widget> _passage(BuildContext context, SourceView? view) {
    final k = FactifyTokens.of(context);
    final paragraphs = view?.paragraphs ?? [_evidence.sourceExcerpt];
    final quoted = view?.quoteParagraph ?? 0;
    final prose = FactifyText.serif(
      17,
      weight: FontWeight.w400,
      color: k.ink2,
    ).copyWith(height: 1.55);
    return [
      for (final (index, paragraph) in paragraphs.indexed) ...[
        if (index > 0) const SizedBox(height: 14),
        if (index == quoted)
          _QuoteBox(
            paragraph: paragraph,
            start: view?.quoteStart,
            end: view?.quoteEnd,
            paragraphNumber: _evidence.sourceAnchor.paragraphIndex,
            match: _evidence.matchBasis.value,
          )
        else
          Text(paragraph, style: prose),
      ],
    ];
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({
    required this.publisher,
    required this.domain,
    required this.onBack,
    required this.onOpen,
  });

  final String publisher;
  final String domain;
  final VoidCallback onBack;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 2, 16, 10),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: k.line)),
      ),
      child: Row(
        children: [
          FxCircleButton(
            icon: FxIcons.back,
            tooltip: MaterialLocalizations.of(context).backButtonTooltip,
            onPressed: onBack,
            size: 38,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              children: [
                Text(
                  publisher,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: FactifyText.sans(13, weight: FontWeight.w600, color: k.ink),
                ),
                if (domain.isNotEmpty && domain != publisher)
                  Text(domain, style: FactifyText.sans(11, color: k.ink3)),
              ],
            ),
          ),
          const SizedBox(width: 10),
          FxCircleButton(
            icon: FxIcons.openExternal,
            tooltip: l10n.srOpenSite,
            onPressed: onOpen,
            size: 38,
          ),
        ],
      ),
    );
  }
}

class _Pills extends StatelessWidget {
  const _Pills({required this.evidence});

  final Evidence evidence;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final (strong, soft) = switch (evidence.direction) {
      'supports' => (k.tC, k.tS),
      'contradicts' => (k.fC, k.fS),
      _ => (k.mC, k.mS),
    };
    Widget pill(String text, Color fg, Color bg, {bool bold = false}) => Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(9)),
      child: Text(
        text,
        style: FactifyText.sans(11, weight: bold ? FontWeight.w700 : FontWeight.w600, color: fg),
      ),
    );
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: [
        pill(l10n.srDirection(evidence.direction), strong, soft, bold: true),
        if (evidence.credibility != null)
          pill(l10n.credibility(evidence.credibility!), k.ink2, k.sf2),
        pill(l10n.tierLabel(evidence.tier), k.ink2, k.sf2),
      ],
    );
  }
}

class _QuoteBox extends StatelessWidget {
  const _QuoteBox({
    required this.paragraph,
    this.start,
    this.end,
    this.paragraphNumber,
    this.match,
  });

  final String paragraph;
  final int? start;
  final int? end;
  final int? paragraphNumber;
  final double? match;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final base = FactifyText.serif(
      18,
      weight: FontWeight.w400,
      color: k.ink2,
    ).copyWith(height: 1.5);
    final from = start;
    final to = end;
    final marked = from != null && to != null && from >= 0 && to <= paragraph.length && from < to;
    final details = [
      if (paragraphNumber != null) l10n.srParagraph(paragraphNumber! + 1),
      if (match != null) l10n.srMatch(match!.toStringAsFixed(2)),
    ];
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 12),
      decoration: BoxDecoration(color: k.accS, borderRadius: BorderRadius.circular(16)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(FxIcons.quotes, size: 14, color: k.acc),
              const SizedBox(width: 6),
              Text(
                l10n.srQuoted.toUpperCase(),
                style: FactifyText.mono(10, color: k.acc, spacing: 1),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text.rich(
            marked
                ? TextSpan(
                    children: [
                      TextSpan(text: paragraph.substring(0, from)),
                      TextSpan(
                        text: paragraph.substring(from, to),
                        style: TextStyle(color: k.ink, fontWeight: FontWeight.w500),
                      ),
                      TextSpan(text: paragraph.substring(to)),
                    ],
                  )
                : TextSpan(
                    text: paragraph,
                    style: TextStyle(color: k.ink),
                  ),
            style: base,
          ),
          if (details.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(details.join(' · '), style: FactifyText.sans(11, color: k.ink3)),
          ],
        ],
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
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(FxIcons.info, size: 14, color: k.ink3),
        const SizedBox(width: 6),
        Expanded(
          child: Text(text, style: FactifyText.sans(12, color: k.ink3).copyWith(height: 1.45)),
        ),
      ],
    );
  }
}
