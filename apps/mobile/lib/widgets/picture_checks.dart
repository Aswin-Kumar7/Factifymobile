/// The picture checks on a result: what can be said about the uploaded picture or
/// video itself (contract 1.3, app/media/report.py).
///
/// Four rows - content credentials, earlier copies online, the AI-made signal, the
/// editing signals - each able to say "not checked", and a footer that says what all
/// of them are: checks of the picture, never part of the verdict above, which rests
/// on cited sources alone. The detector's number is shown as an estimate with a
/// meter, never rounded into a word like "fake"; a raised signal is amber, never red.
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart' hide TextDirection;

import '../l10n/app_localizations.dart';
import '../models/verdict.dart';
import '../theme/icons.dart';
import '../theme/tokens.dart';
import '../theme/typography.dart';
import 'ui/fx_card.dart';

class PictureChecks extends StatelessWidget {
  const PictureChecks({
    required this.report,
    this.thumbnail,
    this.serverUrl,
    this.onOpenPage,
    super.key,
  });

  final MediaReport report;

  /// The person's own picture, for the side-by-side with an earlier copy.
  final Uint8List? thumbnail;

  /// Where relative thumbnail addresses are served from.
  final String? serverUrl;
  final void Function(String url)? onOpenPage;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        FxListCard(
          children: [
            _Credentials(credentials: report.credentials),
            _History(
              history: report.history,
              thumbnail: thumbnail,
              serverUrl: serverUrl,
              onOpenPage: onOpenPage,
            ),
            _Detector(detector: report.detector),
            _Editing(editing: report.editing),
          ],
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(6, 10, 6, 0),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(FxIcons.info, size: 14, color: k.ink3),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  l10n.pcFooter,
                  style: FactifyText.sans(11.5, color: k.ink3).copyWith(height: 1.45),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// One check: an icon, its name, and what it found.
class _Row extends StatelessWidget {
  const _Row({required this.icon, required this.title, required this.children, this.onTap});

  final IconData icon;
  final String title;
  final List<Widget> children;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final body = Padding(
      padding: const EdgeInsets.fromLTRB(14, 13, 14, 13),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 30,
            height: 30,
            alignment: Alignment.center,
            decoration: BoxDecoration(color: k.sf2, borderRadius: BorderRadius.circular(9)),
            child: Icon(icon, size: 16, color: k.ink2),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: FactifyText.sans(12, weight: FontWeight.w600, color: k.ink3),
                ),
                const SizedBox(height: 3),
                ...children,
              ],
            ),
          ),
        ],
      ),
    );
    return onTap == null ? body : InkWell(onTap: onTap, child: body);
  }
}

Text _line(BuildContext context, String text, {bool raised = false, bool quiet = false}) {
  final k = FactifyTokens.of(context);
  return Text(
    text,
    style: FactifyText.sans(
      13.5,
      weight: raised ? FontWeight.w600 : FontWeight.w500,
      color: raised ? k.mC : (quiet ? k.ink3 : k.ink),
    ).copyWith(height: 1.4),
  );
}

class _Credentials extends StatelessWidget {
  const _Credentials({required this.credentials});

  final MediaCredentials credentials;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final generator = credentials.generator;
    final lines = <Widget>[
      if (credentials.declaresAi)
        _line(
          context,
          generator == null || generator.isEmpty ? l10n.pcCredAi : l10n.pcCredAiTool(generator),
          raised: true,
        ),
      switch (credentials.status) {
        'valid' => _line(context, l10n.pcCredValid(credentials.signer ?? '')),
        'untrusted' => _line(context, l10n.pcCredUntrusted),
        'invalid' => _line(context, l10n.pcCredInvalid),
        'none' when credentials.declaresAi => const SizedBox.shrink(),
        'none' => _line(context, l10n.pcCredNone, quiet: true),
        _ => _line(context, l10n.pcNotChecked, quiet: true),
      },
    ];
    return _Row(icon: FxIcons.receipt, title: l10n.pcCredentials, children: lines);
  }
}

class _History extends StatelessWidget {
  const _History({required this.history, this.thumbnail, this.serverUrl, this.onOpenPage});

  final MediaHistory history;
  final Uint8List? thumbnail;
  final String? serverUrl;
  final void Function(String url)? onOpenPage;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final locale = Localizations.localeOf(context).toString();
    final earliest = history.earliest;
    final lines = <Widget>[];

    if (history.status == 'found' && earliest != null) {
      final host = Uri.tryParse(earliest.url)?.host.replaceFirst('www.', '') ?? '';
      lines.add(
        _line(
          context,
          l10n.pcHistorySince(
            DateFormat.yMMMd(locale).format(earliest.publishedAt),
            (earliest.publisher ?? '').trim().isEmpty ? host : earliest.publisher!,
          ),
        ),
      );
      if (earliest.isOld) {
        lines
          ..add(const SizedBox(height: 4))
          ..add(_line(context, l10n.pcHistoryOld(_age(l10n, earliest.daysBefore!)), raised: true));
      }
      final copy = earliest.thumbnailUrl;
      if (copy != null && serverUrl != null) {
        lines
          ..add(const SizedBox(height: 10))
          ..add(_SideBySide(mine: thumbnail, theirs: '$serverUrl$copy'));
      }
    } else if (history.status == 'found') {
      lines.add(_line(context, l10n.pcHistoryUndated(history.pages)));
    } else if (history.status == 'none') {
      lines.add(_line(context, l10n.pcHistoryNone));
    } else {
      lines.add(_line(context, l10n.pcNotChecked, quiet: true));
      // Why, when the server says (contract 1.5): a search that is not set up here
      // reads differently from one that failed this time.
      final why = switch (history.why) {
        'off' => l10n.pcWhyHistoryOff,
        'failed' => l10n.pcWhyFailed,
        _ => null,
      };
      if (why != null) {
        lines
          ..add(const SizedBox(height: 4))
          ..add(_line(context, why, quiet: true));
      }
    }

    return Semantics(
      button: earliest != null && onOpenPage != null,
      hint: earliest != null ? l10n.pcOpenPage : null,
      child: _Row(
        icon: FxIcons.recycled,
        title: l10n.pcHistory,
        onTap: earliest != null && onOpenPage != null ? () => onOpenPage!(earliest.url) : null,
        children: lines,
      ),
    );
  }

  static String _age(AppLocalizations l10n, int days) {
    if (days >= 365) return l10n.pcAgeYears(days ~/ 365);
    if (days >= 60) return l10n.pcAgeMonths(days ~/ 30);
    return l10n.pcAgeDays(days);
  }
}

class _SideBySide extends StatelessWidget {
  const _SideBySide({required this.mine, required this.theirs});

  final Uint8List? mine;
  final String theirs;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    Widget tile(Widget picture, String label) => Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(10),
          child: SizedBox(
            width: 96,
            height: 72,
            child: ColoredBox(color: k.sf2, child: picture),
          ),
        ),
        const SizedBox(height: 4),
        Text(label, style: FactifyText.sans(11, color: k.ink3)),
      ],
    );
    final broken = Icon(FxIcons.image, size: 18, color: k.ink3);
    return Row(
      children: [
        if (mine != null) ...[
          tile(
            Image.memory(mine!, fit: BoxFit.cover, errorBuilder: (_, _, _) => broken),
            l10n.pcYourPicture,
          ),
          const SizedBox(width: 10),
        ],
        tile(
          Image.network(theirs, fit: BoxFit.cover, errorBuilder: (_, _, _) => broken),
          l10n.pcEarlierCopy,
        ),
      ],
    );
  }
}

class _Detector extends StatelessWidget {
  const _Detector({required this.detector});

  final MediaDetector detector;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final k = FactifyTokens.of(context);
    final generated = detector.generated;
    final second = detector.secondOpinion;
    final faceSwap = detector.faceSwap;
    final voice = detector.voice;
    final likelyAi = detector.agreement == 'likely_ai';
    final agreement = switch (detector.agreement) {
      'likely_ai' => second == null ? l10n.pcOneLikelyAi : l10n.pcAgreeLikelyAi,
      'unclear' => l10n.pcAgreeUnclear,
      'no_sign' => l10n.pcAgreeNoSign,
      _ => null,
    };
    final nothing = generated == null && faceSwap == null && voice == null;
    // Why it did not run, when the server says (contract 1.5). A text card is
    // skipped on purpose - its words are what gets checked - and must not read
    // like a detector that broke (2026-09-29).
    final why = switch (detector.why) {
      'text_card' => l10n.pcWhyTextCard,
      'too_small' => l10n.pcWhyTooSmall,
      'unreadable' => l10n.pcWhyUnreadable,
      'off' => l10n.pcWhyDetectorOff,
      'failed' => l10n.pcWhyFailed,
      _ => null,
    };
    final lines = <Widget>[
      if (!detector.checked || nothing) ...[
        _line(context, l10n.pcNotChecked, quiet: true),
        if (why != null) ...[const SizedBox(height: 4), _line(context, why, quiet: true)],
      ] else ...[
        if (agreement != null) ...[
          _line(context, agreement, raised: likelyAi),
          const SizedBox(height: 8),
        ],
        if (generated != null)
          _Meter(value: generated, label: l10n.pcGenerated(_pct(generated)), raised: likelyAi),
        if (second != null) ...[
          const SizedBox(height: 8),
          _Meter(value: second, label: l10n.pcSecondOpinion(_pct(second)), raised: likelyAi),
        ],
        if (faceSwap != null) ...[
          const SizedBox(height: 8),
          _Meter(value: faceSwap, label: l10n.pcFaceSwap(_pct(faceSwap))),
          if (detector.faces != null) ...[
            const SizedBox(height: 4),
            _line(context, l10n.pcFacesChecked(detector.faces!), quiet: true),
          ],
        ] else if (detector.faces == 0) ...[
          const SizedBox(height: 8),
          _line(context, l10n.pcNoFace, quiet: true),
        ],
        if (voice != null) ...[
          const SizedBox(height: 8),
          _Meter(value: voice, label: l10n.pcVoice(_pct(voice))),
        ],
        const SizedBox(height: 6),
        Text(l10n.pcDetectorNote, style: FactifyText.sans(11.5, color: k.ink3)),
        if (detector.onServer) ...[
          const SizedBox(height: 2),
          Text(l10n.pcOnServer, style: FactifyText.sans(11.5, color: k.ink3)),
        ],
      ],
    ];
    return _Row(icon: FxIcons.scales, title: l10n.pcDetector, children: lines);
  }

  static int _pct(double value) => (value * 100).round();
}

class _Meter extends StatelessWidget {
  const _Meter({required this.value, required this.label, bool? raised}) : _raised = raised;

  final double value;
  final String label;

  /// Set by the caller when the server's own boundaries decided it; otherwise 0.7.
  final bool? _raised;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final raised = _raised ?? value >= 0.7;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _line(context, label, raised: raised),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(3),
          child: SizedBox(
            height: 6,
            child: LinearProgressIndicator(
              value: value.clamp(0, 1),
              color: raised ? k.mC : k.ink3,
              backgroundColor: k.line,
            ),
          ),
        ),
      ],
    );
  }
}

class _Editing extends StatelessWidget {
  const _Editing({required this.editing});

  final MediaEditing editing;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final lines = <Widget>[
      if (!editing.checked)
        _line(context, l10n.pcNotChecked, quiet: true)
      else if (!editing.unevenNoise && !editing.spectralPeaks)
        _line(context, l10n.pcEditClean)
      else ...[
        if (editing.unevenNoise) _line(context, l10n.pcEditNoise, raised: true),
        if (editing.spectralPeaks) ...[
          if (editing.unevenNoise) const SizedBox(height: 4),
          _line(context, l10n.pcEditSpectrum, raised: true),
        ],
      ],
    ];
    return _Row(icon: FxIcons.eye, title: l10n.pcEditing, children: lines);
  }
}
