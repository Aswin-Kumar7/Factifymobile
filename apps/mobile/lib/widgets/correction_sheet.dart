/// Previews the correction card and sends it (M44, PLAN 1.7.5).
///
/// The preview is the picture itself, not a mock-up of it: the widget on screen is
/// the one inside the boundary that gets captured, so what the person approves is
/// exactly what their group receives.
library;

import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';

import '../l10n/app_localizations.dart';
import '../models/verdict.dart';
import 'correction_card.dart';

/// Hands [params] to a share sheet and reports what the person did with it.
typedef ShareLauncher = Future<ShareResultStatus> Function(ShareParams params);

Future<ShareResultStatus> _systemShare(ShareParams params) async =>
    (await SharePlus.instance.share(params)).status;

Future<void> showCorrectionSheet(BuildContext context, Verdict verdict) =>
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => CorrectionSheet(verdict: verdict),
    );

class CorrectionSheet extends StatefulWidget {
  const CorrectionSheet({required this.verdict, this.share = _systemShare, super.key});

  final Verdict verdict;

  /// The platform share sheet; replaced in tests.
  final ShareLauncher share;

  @override
  State<CorrectionSheet> createState() => _CorrectionSheetState();
}

class _CorrectionSheetState extends State<CorrectionSheet> {
  final GlobalKey _card = GlobalKey();
  bool _sharing = false;

  /// The card as PNG bytes, at three times its logical size.
  Future<Uint8List> _capture() async {
    final boundary = _card.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final image = await boundary.toImage(pixelRatio: 3);
    try {
      final png = await image.toByteData(format: ui.ImageByteFormat.png);
      return png!.buffer.asUint8List();
    } finally {
      image.dispose();
    }
  }

  Future<void> _sharePicture() async {
    final l10n = AppLocalizations.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final navigator = Navigator.of(context);
    final text = correctionText(widget.verdict, l10n);

    setState(() => _sharing = true);
    try {
      final png = await _capture();
      final status = await widget.share(
        ShareParams(
          files: [XFile.fromData(png, mimeType: 'image/png')],
          // XFile.fromData ignores its name everywhere but the web, so the file
          // would otherwise reach the chat under a random identifier.
          fileNameOverrides: const ['factify-correction.png'],
          text: text,
        ),
      );
      // Closed only once something was sent. A dismissed share sheet leaves the
      // preview open, with "copy text" still one tap away.
      if (status == ShareResultStatus.success && navigator.canPop()) navigator.pop();
    } on Object {
      // The picture could not be drawn, or sharing could not open. The correction
      // is still worth sending, so it goes to the clipboard instead, and the
      // person is told so once the sheet is out of the way.
      await Clipboard.setData(ClipboardData(text: text));
      if (navigator.canPop()) navigator.pop();
      messenger.showSnackBar(SnackBar(content: Text(l10n.correctionShareFailed)));
    } finally {
      if (mounted) setState(() => _sharing = false);
    }
  }

  Future<void> _copyText() async {
    final l10n = AppLocalizations.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final navigator = Navigator.of(context);

    await Clipboard.setData(ClipboardData(text: correctionText(widget.verdict, l10n)));
    if (navigator.canPop()) navigator.pop();
    messenger.showSnackBar(SnackBar(content: Text(l10n.correctionCopied)));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);

    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              l10n.correctionSheetTitle,
              style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 4),
            Text(
              l10n.correctionSheetBody,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 14),
            // Scaled down to fit a narrow phone. The scaling sits above the
            // boundary, so the captured picture is always drawn at full size.
            Center(
              child: FittedBox(
                fit: BoxFit.scaleDown,
                child: RepaintBoundary(
                  key: _card,
                  child: SizedBox(
                    width: correctionCardWidth,
                    child: CorrectionCard(verdict: widget.verdict),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: _sharing ? null : _sharePicture,
              icon: _sharing
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.share),
              label: Text(l10n.correctionShareImage),
              style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48)),
            ),
            const SizedBox(height: 4),
            TextButton(
              onPressed: _sharing ? null : _copyText,
              child: Text(l10n.correctionCopyText),
            ),
          ],
        ),
      ),
    );
  }
}
