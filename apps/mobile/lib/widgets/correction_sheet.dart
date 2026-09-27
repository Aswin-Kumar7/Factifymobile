/// "Send this back to the chat" (v5, 2.6): the correction picture and the note that
/// goes with it.
///
/// The preview is the picture itself, not a mock-up of it: the card on screen is the
/// one inside the boundary that gets captured, so what the person approves is exactly
/// what their group receives. Beside it goes a short, polite note, in English or
/// Hindi, which the person can edit before sending - it is their message to their
/// family, not ours. The note comes from the server (`POST /v1/cases/{id}/correction-text`)
/// and is built on the phone the same way when the server cannot be reached.
library;

import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';

import '../l10n/app_localizations.dart';
import '../models/correction_message.dart';
import '../models/verdict.dart';
import '../theme/icons.dart';
import '../theme/tokens.dart';
import '../theme/typography.dart';
import 'correction_card.dart';
import 'ui/fx_button.dart';
import 'ui/fx_tap_area.dart';

/// Hands [params] to a share sheet and reports what the person did with it.
typedef ShareLauncher = Future<ShareResultStatus> Function(ShareParams params);

/// Asks the server for the note in a language, "en" or "hi".
typedef CorrectionLoader = Future<CorrectionMessage> Function(String language);

Future<ShareResultStatus> _systemShare(ShareParams params) async =>
    (await SharePlus.instance.share(params)).status;

Future<void> showCorrectionSheet(BuildContext context, Verdict verdict, {CorrectionLoader? load}) =>
    Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => CorrectionSheet(verdict: verdict, load: load),
      ),
    );

/// The note's languages, each named in itself - someone looking for Hindi in an
/// English interface is scanning for "हिन्दी" (as in the language menu).
const Map<String, String> _languages = {'en': 'English', 'hi': 'हिन्दी'};

/// The picture is drawn at three times its size.
const double _scale = 3;

class CorrectionSheet extends StatefulWidget {
  const CorrectionSheet({required this.verdict, this.load, this.share = _systemShare, super.key});

  final Verdict verdict;

  /// The server's note; null, or failing, leaves the one built on the phone.
  final CorrectionLoader? load;

  /// The platform share sheet; replaced in tests.
  final ShareLauncher share;

  @override
  State<CorrectionSheet> createState() => _CorrectionSheetState();
}

class _CorrectionSheetState extends State<CorrectionSheet> {
  final GlobalKey _card = GlobalKey();
  final TextEditingController _note = TextEditingController();

  String? _language;

  /// Each language's note as the person last saw it, and its links.
  final Map<String, String> _notes = {};
  final Map<String, List<String>> _links = {};

  /// Languages whose note the person has changed: the server's never replaces it.
  final Set<String> _edited = {};
  final Set<String> _asked = {};

  bool _copied = false;
  bool _sharing = false;
  bool _filling = false;

  @override
  void initState() {
    super.initState();
    _note.addListener(_changed);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_language == null) {
      final locale = Localizations.localeOf(context).languageCode;
      _choose(_languages.containsKey(locale) ? locale : 'en');
    }
  }

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  void _changed() {
    final language = _language;
    if (_filling || language == null || _note.text == _notes[language]) return;
    _notes[language] = _note.text;
    _edited.add(language);
    if (_copied) setState(() => _copied = false);
  }

  void _fill(String text) {
    _filling = true;
    _note.text = text;
    _filling = false;
  }

  void _choose(String language) {
    if (!_notes.containsKey(language)) {
      final local = correctionMessage(widget.verdict, lookupAppLocalizations(Locale(language)));
      _notes[language] = local.message;
      _links[language] = local.links;
    }
    setState(() {
      _language = language;
      _copied = false;
      _fill(_notes[language]!);
    });
    unawaited(_ask(language));
  }

  Future<void> _ask(String language) async {
    final load = widget.load;
    if (load == null || !_asked.add(language)) return;
    try {
      final served = await load(language);
      if (!mounted || served.message.trim().isEmpty || _edited.contains(language)) return;
      setState(() {
        _notes[language] = served.message;
        _links[language] = served.links;
        if (_language == language) _fill(served.message);
      });
    } on Object {
      // The note built on the phone stays; it says the same thing.
    }
  }

  String get _text => correctionShareText(_note.text, _links[_language] ?? const []);

  /// The card as PNG bytes: drawn at three times its size, then set on the page
  /// colour with a margin. Chats turn a picture's transparent corners black, so the
  /// card's rounded corners are filled in before it leaves the phone.
  Future<Uint8List> _capture() async {
    final boundary = _card.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final card = await boundary.toImage(pixelRatio: _scale);
    try {
      const margin = 14 * _scale;
      final width = card.width + 2 * margin;
      final height = card.height + 2 * margin;
      final recorder = ui.PictureRecorder();
      Canvas(recorder)
        ..drawRect(Rect.fromLTWH(0, 0, width, height), Paint()..color = FactifyTokens.light.bg)
        ..drawImage(card, const Offset(margin, margin), Paint());
      final picture = recorder.endRecording();
      final flat = await picture.toImage(width.round(), height.round());
      try {
        final png = await flat.toByteData(format: ui.ImageByteFormat.png);
        return png!.buffer.asUint8List();
      } finally {
        flat.dispose();
        picture.dispose();
      }
    } finally {
      card.dispose();
    }
  }

  Future<void> _sharePicture() async {
    final l10n = AppLocalizations.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final navigator = Navigator.of(context);
    final text = _text;

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
      // screen open, with "copy text" still one tap away.
      if (status == ShareResultStatus.success && navigator.canPop()) navigator.pop();
    } on Object {
      // The picture could not be drawn, or sharing could not open. The correction
      // is still worth sending, so it goes to the clipboard instead.
      await Clipboard.setData(ClipboardData(text: text));
      if (mounted) setState(() => _copied = true);
      messenger.showSnackBar(SnackBar(content: Text(l10n.correctionShareFailed)));
    } finally {
      if (mounted) setState(() => _sharing = false);
    }
  }

  Future<void> _copyText() async {
    await Clipboard.setData(ClipboardData(text: _text));
    if (mounted) setState(() => _copied = true);
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);

    return Scaffold(
      backgroundColor: k.bg,
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 2, 16, 0),
              child: Row(
                children: [
                  FxCircleButton(
                    icon: FxIcons.back,
                    tooltip: MaterialLocalizations.of(context).backButtonTooltip,
                    onPressed: () => Navigator.of(context).maybePop(),
                    background: k.sf,
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      l10n.correctionSheetTitle,
                      style: FactifyText.sans(14, weight: FontWeight.w600, color: k.ink),
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(18, 14, 18, 20),
                children: [
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 2),
                    child: Text(
                      l10n.correctionSheetBody,
                      style: FactifyText.sans(13, color: k.ink2).copyWith(height: 1.5),
                    ),
                  ),
                  const SizedBox(height: 14),
                  Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(
                      color: k.sf2,
                      borderRadius: BorderRadius.circular(24),
                    ),
                    // Scaled down to fit a narrow phone, and tilted a degree as a
                    // picture lying on the page. Both sit above the boundary, so the
                    // captured picture is always drawn square and at full size.
                    child: Center(
                      child: FittedBox(
                        fit: BoxFit.scaleDown,
                        child: Transform.rotate(
                          angle: -math.pi / 180,
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(18),
                              boxShadow: const [
                                BoxShadow(
                                  offset: Offset(0, 16),
                                  blurRadius: 36,
                                  spreadRadius: -20,
                                  color: Color.fromRGBO(0, 0, 0, .35),
                                ),
                              ],
                            ),
                            child: RepaintBoundary(
                              key: _card,
                              child: SizedBox(
                                width: correctionCardWidth,
                                child: CorrectionCard(verdict: widget.verdict),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(4, 20, 4, 8),
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(
                            l10n.correctionMessageWith,
                            style: FactifyText.sans(13, weight: FontWeight.w600, color: k.ink),
                          ),
                        ),
                        _LanguageSwitch(selected: _language ?? 'en', onChanged: _choose),
                      ],
                    ),
                  ),
                  Container(
                    decoration: BoxDecoration(
                      color: k.sf,
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(color: k.line),
                    ),
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
                    child: TextField(
                      controller: _note,
                      minLines: 3,
                      maxLines: null,
                      keyboardType: TextInputType.multiline,
                      style: FactifyText.sans(14, color: k.ink).copyWith(height: 1.5),
                      cursorColor: k.acc,
                      decoration: InputDecoration(
                        // The box is drawn by the container; the app's input
                        // theme would draw a second outline inside it.
                        border: InputBorder.none,
                        enabledBorder: InputBorder.none,
                        focusedBorder: InputBorder.none,
                        filled: false,
                        isDense: true,
                        contentPadding: const EdgeInsets.symmetric(vertical: 8),
                        semanticCounterText: '',
                        hintText: l10n.correctionMessageLabel,
                        hintStyle: FactifyText.sans(14, color: k.ink3),
                      ),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(4, 8, 4, 0),
                    child: Text(
                      l10n.correctionMessageHint,
                      style: FactifyText.sans(11.5, color: k.ink3),
                    ),
                  ),
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
                    flex: 10,
                    child: FxButton(
                      label: _copied ? l10n.correctionCopied : l10n.correctionCopyText,
                      icon: FxIcons.copy,
                      variant: FxButtonVariant.secondary,
                      onPressed: _sharing ? null : _copyText,
                      height: 52,
                      radius: 18,
                      fontSize: 14,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    flex: 12,
                    child: FxButton(
                      label: l10n.correctionShareImage,
                      icon: FxIcons.shareNetwork,
                      onPressed: _sharePicture,
                      busy: _sharing,
                      height: 52,
                      radius: 18,
                      fontSize: 14.5,
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
}

/// English | हिन्दी, as a small segmented control.
class _LanguageSwitch extends StatelessWidget {
  const _LanguageSwitch({required this.selected, required this.onChanged});

  final String selected;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    // The track is drawn 34 tall, as designed; each half answers a tap over 44.
    return Stack(
      alignment: Alignment.center,
      children: [
        Positioned.fill(
          child: Center(
            child: Container(
              height: 34,
              decoration: BoxDecoration(color: k.sf2, borderRadius: BorderRadius.circular(12)),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 3),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (final MapEntry(key: code, value: name) in _languages.entries) ...[
                if (code != _languages.keys.first) const SizedBox(width: 2),
                FxTapArea(
                  selected: code == selected,
                  // The chosen half stays a button a screen reader can reach.
                  onTap: () => onChanged(code),
                  child: Container(
                    height: 28,
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: code == selected ? k.sf : null,
                      borderRadius: BorderRadius.circular(9),
                      boxShadow: code == selected ? k.shadow : null,
                    ),
                    child: Text(
                      name,
                      style: FactifyText.sans(
                        12.5,
                        weight: FontWeight.w600,
                        color: code == selected ? k.ink : k.ink3,
                      ),
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}
