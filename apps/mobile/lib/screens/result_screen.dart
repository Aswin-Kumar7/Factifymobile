/// The answer, on its own page (v5): the verdict in its colour, then what was
/// checked, each claim, the sources and the receipt.
///
/// Opened when a check finishes and again from History, from the same saved data.
/// The bottom bar re-runs the check fresh, and carries the one thing to do next:
/// send a correction back for False, context for Misleading, the result for True,
/// or check again for Unconfirmed.
///
/// An answer held back because part of the input could not be read (contract 1.8)
/// offers, at the top, the ways on: check what could be read, paste the text, or
/// upload the picture or video. Each starts a new check from here.
library;

import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/client.dart';
import '../app_services.dart';
import '../l10n/app_localizations.dart';
import '../l10n/phrases.dart';
import '../models/submission.dart';
import '../models/verdict.dart';
import '../widgets/action_style.dart';
import '../widgets/correction_sheet.dart';
import '../widgets/ui/ui.dart';
import '../widgets/verdict_card.dart';
import '../widgets/why_sheet.dart';
import 'checking_screen.dart';
import 'evidence_screen.dart';
import 'source_reader_screen.dart';

/// Picks a picture or a video from the phone for "Upload the picture or video".
/// Null when the person chose nothing.
typedef MediaPicker = Future<File?> Function();

// The upload rules of Check (home_screen.dart), for a file chosen from a result: a
// video over the server's limit is refused here rather than after the upload, and a
// picture is read once for its preview.
const int _largestUpload = 25 * 1024 * 1024;
const int _previewBytesLimit = 4 * 1024 * 1024;
const Set<String> _videoEndings = {'mp4', 'm4v', 'mov', '3gp', 'webm', 'mkv'};

class ResultScreen extends StatefulWidget {
  ResultScreen({
    required this.services,
    required this.verdict,
    Submission? submission,
    SubmissionKind? kind,
    String? summary,
    Uint8List? thumbnail,
    this.justChecked = false,
    this.openShare = false,
    this.pickMedia,
    super.key,
  }) : submission = submission,
       kind = kind ?? submission?.kind ?? SubmissionKind.text,
       summary = summary ?? submission?.summaryWith(verdict) ?? '',
       thumbnail = thumbnail ?? submission?.thumbnail;

  final AppServices services;
  final Verdict verdict;

  /// What can be checked again. Null when it cannot, such as a picture from an old
  /// check whose file is no longer on the phone.
  final Submission? submission;
  final SubmissionKind kind;
  final String summary;
  final Uint8List? thumbnail;

  /// The verdict arrived just now, so the receipt it carries was checked just now.
  /// A result reopened from History checks its receipt again: the seal says the
  /// evidence is unchanged, and that is only true of the moment it was looked at.
  final bool justChecked;

  /// Opened from a notification's "Share correction": the share sheet opens at once.
  final bool openShare;

  /// Supplied by tests; the system's file picker otherwise.
  final MediaPicker? pickMedia;

  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> {
  bool _reporting = false;

  /// Remembered on the phone, so a result reopened from History is not offered
  /// for reporting a second time.
  late bool _reported = widget.services.history.isReported(widget.verdict.caseId);
  ReceiptState? _receipt;
  String? _receiptId;

  Verdict get _verdict => widget.verdict;

  bool get _canCheckAgain {
    final submission = widget.submission;
    if (submission == null) return false;
    return submission.text != null || (submission.file?.existsSync() ?? false);
  }

  @override
  void initState() {
    super.initState();
    // A pulse as the verdict appears (v5 accessibility): felt, not only seen.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(HapticFeedback.mediumImpact());
      if (widget.openShare && mounted) _share();
    });
    final inline = _verdict.receipt;
    final receiptUrl = _verdict.receiptUrl;
    if (widget.justChecked && inline != null) {
      _receipt = inline.verified ? ReceiptState.verified : ReceiptState.failed;
      _receiptId = shortReceiptId(inline.receiptId);
    } else if (receiptUrl != null) {
      _receipt = ReceiptState.checking;
      unawaited(_checkReceipt(receiptUrl));
    }
  }

  Future<void> _checkReceipt(String url) async {
    try {
      final receipt = await widget.services.client.getReceipt(url);
      if (!mounted) return;
      setState(() {
        _receipt = receipt == null
            ? null
            : receipt.verified
            ? ReceiptState.verified
            : ReceiptState.failed;
        _receiptId = receipt == null ? null : shortReceiptId(receipt.receiptId);
      });
    } on ApiFailure {
      if (mounted) setState(() => _receipt = null);
    }
  }

  void _checkAgain() {
    final submission = widget.submission;
    if (submission == null) return;
    unawaited(
      Navigator.of(context).pushReplacement(
        MaterialPageRoute<void>(
          builder: (_) => CheckingScreen(
            services: widget.services,
            submission: submission,
            recheck: true,
            // An answer checked from part of a post, checked again, is checked the
            // same way: without it, a post still read in part is only held back.
            acceptPartial: _verdict.inputRead?.checkedPartially ?? false,
          ),
        ),
      ),
    );
  }

  /// "Check what was read" is offered only where it can give an answer: the same
  /// thing can be sent again, and enough of it was read to check anything at all.
  /// Otherwise the server would only hold the answer back a second time.
  bool get _canCheckWhatWasRead {
    final read = _verdict.inputRead;
    return _canCheckAgain && read != null && read.verdictWithheld && read.substantive;
  }

  /// "Upload the picture or video" is for a link or a message whose post could not
  /// be read in full; an upload that could not be read is not helped by sending it
  /// again.
  bool get _canUpload => switch (_verdict.inputRead?.kind) {
    'link' || 'social_post' || 'text' => true,
    _ => false,
  };

  /// The same input again, checked from what could be read (1.8).
  void _checkWhatWasRead() {
    final submission = widget.submission;
    if (submission != null) _startCheck(submission, acceptPartial: true);
  }

  /// A new check, in place of this answer.
  void _startCheck(Submission submission, {bool acceptPartial = false}) => unawaited(
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(
        builder: (_) => CheckingScreen(
          services: widget.services,
          submission: submission,
          acceptPartial: acceptPartial,
        ),
      ),
    ),
  );

  /// "Paste the text": the words of the post or the page, checked as a message is.
  Future<void> _pasteText() async {
    final text = await showFxSheet<String>(context, builder: (_) => const _PasteSheet());
    if (!mounted || text == null || text.trim().isEmpty) return;
    _startCheck(Submission.text(text.trim()));
  }

  /// "Upload the picture or video": the thing itself, rather than the link to it.
  Future<void> _upload() async {
    final l10n = AppLocalizations.of(context);
    final messenger = ScaffoldMessenger.of(context);
    void say(String message) => messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
    try {
      final file = await (widget.pickMedia ?? _pickFromPhone)();
      if (!mounted || file == null) return;
      final path = file.path;
      final ending = path.contains('.') ? path.split('.').last.toLowerCase() : '';
      final video = _videoEndings.contains(ending);
      final size = await file.length();
      if (!mounted) return;
      if (video && size > _largestUpload) {
        say(l10n.videoTooLarge(_largestUpload ~/ (1024 * 1024)));
        return;
      }
      final preview = !video && size <= _previewBytesLimit ? await file.readAsBytes() : null;
      if (!mounted) return;
      _startCheck(Submission.image(file, preview, video: video));
    } on PlatformException {
      say(l10n.errorFileUnopenable);
    } on FileSystemException {
      say(l10n.errorFileUnopenable);
    }
  }

  static Future<File?> _pickFromPhone() async {
    final picked = await FilePicker.platform.pickFiles(type: FileType.media);
    final path = picked?.files.single.path;
    return path == null ? null : File(path);
  }

  void _home() => Navigator.of(context).popUntil((route) => route.isFirst);

  void _share() => unawaited(
    showCorrectionSheet(
      context,
      _verdict,
      load: (language) => widget.services.client.correctionText(_verdict.caseId, language),
    ),
  );

  void _openClaim(Claim claim) => unawaited(
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => EvidenceScreen(
          verdict: _verdict,
          language: widget.services.language,
          submission: widget.submission,
          client: widget.services.client,
          focus: claim,
        ),
      ),
    ),
  );

  /// A page where the picture appeared before, in the person's own browser.
  void _openPage(String url) {
    final uri = Uri.tryParse(url);
    if (uri != null) unawaited(launchUrl(uri, mode: LaunchMode.externalApplication));
  }

  /// A cited source, read in the app around the passage the result quoted.
  Future<void> _openSource(Evidence evidence) => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => SourceReaderScreen(
        services: widget.services,
        caseId: _verdict.caseId,
        evidence: evidence,
      ),
    ),
  );

  /// Flag this verdict for human review: a real request, confirmed only once the
  /// server has queued it.
  Future<void> _report() async {
    if (_reporting) return;
    setState(() => _reporting = true);
    final l10n = AppLocalizations.of(context);
    final messenger = ScaffoldMessenger.of(context);
    try {
      await widget.services.client.reportCase(_verdict.caseId);
      await widget.services.history.markReported(_verdict.caseId);
      if (!mounted) return;
      setState(() => _reported = true);
      messenger.showSnackBar(SnackBar(content: Text(l10n.reportSent)));
    } on ApiFailure catch (failure) {
      messenger.showSnackBar(
        SnackBar(content: Text(l10n.reportFailed(l10n.describeFailure(failure)))),
      );
    } finally {
      if (mounted) setState(() => _reporting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final nothing = _verdict.nothingToCheck;
    final withheld = _verdict.withheld;
    final (_, soft) = nothing ? (k.uC, k.uS) : ActionStyle.colours(_verdict.factVerdict, k);
    final tint = Color.alphaBlend(soft, k.bg);
    final top = MediaQuery.paddingOf(context).top;

    final (label, icon, action) = switch (_verdict.factVerdict) {
      _ when nothing => (l10n.newCheck, FxIcons.forward, _home),
      // The ways on are at the top of an answer held back; the bar starts afresh.
      _ when withheld => (l10n.newCheck, FxIcons.forward, _home),
      FactVerdict.falseClaim ||
      FactVerdict.partlyTrue => (l10n.shareCorrection, FxIcons.correction, _share),
      FactVerdict.misleading => (l10n.shareContext, FxIcons.correction, _share),
      FactVerdict.trueClaim => (l10n.shareResult, FxIcons.share, _share),
      FactVerdict.unconfirmed when _canCheckAgain => (
        l10n.checkAgain,
        FxIcons.recheck,
        _checkAgain,
      ),
      FactVerdict.unconfirmed => (l10n.newCheck, FxIcons.forward, _home),
    };

    return Scaffold(
      body: Stack(
        children: [
          ListView(
            padding: EdgeInsets.zero,
            children: [
              Container(
                color: tint,
                padding: EdgeInsets.fromLTRB(12, top + 2, 12, 0),
                child: Row(
                  children: [
                    FxCircleButton(
                      icon: FxIcons.back,
                      tooltip: MaterialLocalizations.of(context).backButtonTooltip,
                      onPressed: () => Navigator.of(context).maybePop(),
                    ),
                    Expanded(
                      child: Text(
                        l10n.resultTitle,
                        textAlign: TextAlign.center,
                        style: FactifyText.sans(13, weight: FontWeight.w600, color: k.ink2),
                      ),
                    ),
                    FxCircleButton(
                      icon: FxIcons.share,
                      // Named for what it shares, as the button below is: a true
                      // result is not a correction.
                      tooltip: switch (_verdict.factVerdict) {
                        FactVerdict.trueClaim => l10n.shareResult,
                        FactVerdict.misleading => l10n.shareContext,
                        _ => l10n.shareCorrection,
                      },
                      iconSize: 19,
                      // An answer held back says nothing about the claims to share.
                      onPressed: nothing || withheld ? null : _share,
                    ),
                  ],
                ),
              ),
              VerdictCard(
                verdict: _verdict,
                kind: widget.kind,
                submittedText: widget.submission?.text,
                thumbnail: widget.thumbnail,
                onWhy: () => unawaited(showWhySheet(context, _verdict)),
                onOpenClaim: _openClaim,
                onOpenSource: _openSource,
                onReportForReview: _reported ? null : _report,
                reporting: _reporting,
                reported: _reported,
                receipt: _receipt,
                receiptId: _receiptId,
                serverUrl: widget.services.client.baseUrl,
                onOpenPage: _openPage,
                onCheckWhatWasRead: _canCheckWhatWasRead ? _checkWhatWasRead : null,
                onPasteText: withheld ? () => unawaited(_pasteText()) : null,
                onUpload: withheld && _canUpload ? () => unawaited(_upload()) : null,
              ),
            ],
          ),
          // The status bar keeps the verdict's tint, so the page scrolls beneath it
          // rather than under the clock.
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            height: top,
            child: ColoredBox(color: tint),
          ),
        ],
      ),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: k.nav,
          border: Border(top: BorderSide(color: k.line)),
        ),
        child: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Row(
              children: [
                Semantics(
                  button: true,
                  label: l10n.checkAgain,
                  excludeSemantics: true,
                  child: AnimatedOpacity(
                    duration: const Duration(milliseconds: 200),
                    opacity: _canCheckAgain ? 1 : 0.4,
                    child: Material(
                      color: k.sf2,
                      borderRadius: BorderRadius.circular(18),
                      clipBehavior: Clip.antiAlias,
                      child: InkWell(
                        onTap: _canCheckAgain ? _checkAgain : null,
                        child: SizedBox(
                          width: 52,
                          height: 52,
                          child: Icon(FxIcons.recheck, size: 22, color: k.ink),
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: FxButton(
                    label: label,
                    icon: icon,
                    variant: FxButtonVariant.dark,
                    height: 52,
                    radius: 18,
                    fontSize: 15,
                    onPressed: action,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// "Paste the text": a box for the words of a post or a page that could not be read
/// in full. The clipboard is read only when the person taps "Paste copied text", as
/// on Check. Closes with the text to check, or with nothing.
class _PasteSheet extends StatefulWidget {
  const _PasteSheet();

  @override
  State<_PasteSheet> createState() => _PasteSheetState();
}

class _PasteSheetState extends State<_PasteSheet> {
  final TextEditingController _text = TextEditingController();

  @override
  void initState() {
    super.initState();
    _text.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _paste() async {
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    final text = data?.text?.trim() ?? '';
    if (mounted && text.isNotEmpty) _text.text = text;
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final ready = _text.text.trim().isNotEmpty;
    return Padding(
      // Above the keyboard, which opens over a bottom sheet.
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            l10n.pasteSheetTitle,
            style: FactifyText.sans(17, weight: FontWeight.w600, color: k.ink),
          ),
          const SizedBox(height: 6),
          Text(
            l10n.pasteSheetBody,
            style: FactifyText.sans(13, color: k.ink2).copyWith(height: 1.45),
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            decoration: BoxDecoration(
              color: k.bg,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: k.line),
            ),
            child: TextField(
              key: const ValueKey('paste-sheet-text'),
              controller: _text,
              autofocus: true,
              minLines: 4,
              maxLines: 8,
              style: FactifyText.sans(15, color: k.ink).copyWith(height: 1.45),
              decoration: InputDecoration(
                hintText: l10n.pasteSheetHint,
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
              ),
            ),
          ),
          const SizedBox(height: 10),
          if (!ready) ...[
            FxButton(
              label: l10n.pasteCopiedText,
              icon: FxIcons.paste,
              variant: FxButtonVariant.outline,
              height: 46,
              fontSize: 14,
              onPressed: () => unawaited(_paste()),
            ),
            const SizedBox(height: 8),
          ],
          FxButton(
            label: l10n.checkNow,
            icon: FxIcons.check,
            height: 52,
            fontSize: 15,
            onPressed: ready ? () => Navigator.of(context).pop(_text.text) : null,
          ),
        ],
      ),
    );
  }
}

/// A receipt id as shown on the seal: its first seven characters, "7F3A-21C".
String shortReceiptId(String id) {
  final plain = id
      .replaceFirst(RegExp(r'^[A-Za-z]+[_:]'), '')
      .replaceAll(RegExp('[^0-9A-Za-z]'), '')
      .toUpperCase();
  if (plain.length < 7) return plain;
  return '${plain.substring(0, 4)}-${plain.substring(4, 7)}';
}
