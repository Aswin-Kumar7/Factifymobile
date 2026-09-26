/// Check: choose what to check, add it, and check it (v5).
///
/// One kind of input at a time - text or a link, a picture, or a PDF. Once something
/// is added the other kinds are locked, and it is removed to switch: a check is of
/// one thing, and a screen that took a message, a picture and a file together left
/// it unclear which one the answer was about.
///
/// The composer card is the page's focus: the three kinds as tabs, then the input
/// itself - a large serif text box, or a picture or a PDF - and one row of actions
/// under it. The check opens on its own page (`checking_screen.dart`) and the answer
/// on another (`result_screen.dart`); the last three checks are listed under
/// "Recent", and all of them on the History tab.
///
/// Permissions: the camera is the only one requested, and only when the camera
/// button is pressed. The gallery and the file picker go through the system picker,
/// which grants one file without a storage permission.
library;

import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:intl/intl.dart';

import '../api/share_intake.dart';
import '../app_services.dart';
import '../history/history_store.dart';
import '../l10n/app_localizations.dart';
import '../models/submission.dart';
import '../widgets/action_style.dart';
import '../widgets/ui/ui.dart';
import 'checking_screen.dart';
import 'history_screen.dart';

/// The largest picture read into memory for its preview.
const int _previewBytesLimit = 4 * 1024 * 1024;

/// What is being checked: exactly one of these at a time.
enum InputType { text, image, pdf }

class HomeScreen extends StatefulWidget {
  const HomeScreen({required this.services, this.onSeeAll, super.key});

  final AppServices services;

  /// Opens the History tab, from "See all".
  final VoidCallback? onSeeAll;

  @override
  State<HomeScreen> createState() => HomeScreenState();
}

class HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  final TextEditingController _text = TextEditingController();
  final ImagePicker _camera = ImagePicker();

  InputType _type = InputType.text;
  File? _file;
  Uint8List? _preview;
  int? _fileSize;
  bool _deep = false;

  /// Whether copied text is waiting. Asked with `Clipboard.hasStrings`, which does
  /// not read it: nothing on the clipboard is read until the person taps.
  bool _clipboardOffer = false;

  /// Whether the service can check right now: unknown until the first probe.
  bool? _serviceReady;

  AppServices get _services => widget.services;

  bool get _hasInput => switch (_type) {
    InputType.text => _text.text.trim().isNotEmpty,
    InputType.image || InputType.pdf => _file != null,
  };

  bool get _looksLikeLink {
    final value = _text.text.trim();
    return value.startsWith('http://') || value.startsWith('https://') || value.startsWith('www.');
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _text.addListener(() => setState(() {}));
    unawaited(_probeService());
    // After the first frame: Android answers clipboard questions only for the app
    // that has focus, and the window does not have it during initState.
    WidgetsBinding.instance.addPostFrameCallback((_) => unawaited(_offerClipboard()));
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Coming back to Factify is when someone has usually just copied something.
    if (state == AppLifecycleState.resumed) unawaited(_offerClipboard());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _text.dispose();
    super.dispose();
  }

  Future<void> _probeService() async {
    final ready = await _services.client.ready();
    if (mounted) setState(() => _serviceReady = ready);
  }

  Future<void> _offerClipboard() async {
    if (_hasInput || _type != InputType.text) return;
    final bool hasText;
    try {
      hasText = await Clipboard.hasStrings();
    } on Exception {
      return;
    }
    if (mounted && hasText != _clipboardOffer) setState(() => _clipboardOffer = hasText);
  }

  /// Reads the clipboard, only now, because the person asked, into the text box.
  Future<void> _paste() async {
    setState(() => _clipboardOffer = false);
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    final text = data?.text?.trim() ?? '';
    if (!mounted || text.isEmpty) return;
    _text.text = text;
  }

  void _select(InputType type) {
    if (type == _type) return;
    setState(() {
      _type = type;
      _clipboardOffer = false;
    });
    if (type == InputType.text) unawaited(_offerClipboard());
  }

  /// Remove what was added, which unlocks the other kinds.
  void clearInput() {
    setState(() {
      _text.clear();
      _file = null;
      _preview = null;
      _fileSize = null;
    });
  }

  /// Opens Check with this text in the box, ready to check (from an error screen).
  void fillText(String text) {
    clearInput();
    setState(() => _type = InputType.text);
    _text.text = text;
  }

  void _say(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _pickImage(ImageSource source) async {
    try {
      final File? file;
      if (source == ImageSource.camera) {
        final shot = await _camera.pickImage(
          source: ImageSource.camera,
          // Capped on the way in: a 12 MP photograph is far more than reading its
          // text needs, and the upload limit is what would refuse it.
          maxWidth: 1600,
          imageQuality: 88,
        );
        file = shot == null ? null : File(shot.path);
      } else {
        final picked = await FilePicker.platform.pickFiles(type: FileType.image);
        final path = picked?.files.single.path;
        file = path == null ? null : File(path);
      }
      if (file != null) await _useFile(file, InputType.image);
    } on PlatformException catch (error) {
      if (!mounted) return;
      final l10n = AppLocalizations.of(context);
      _say(
        error.code == 'camera_access_denied' ? l10n.errorCameraDenied : l10n.errorFileUnopenable,
      );
    }
  }

  /// Opens the camera straight away (the home-screen widget's "Photo").
  Future<void> takePhoto() async {
    clearInput();
    setState(() => _type = InputType.image);
    await _pickImage(ImageSource.camera);
  }

  Future<void> _pickPdf() async {
    try {
      final picked = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: const ['pdf'],
      );
      final path = picked?.files.single.path;
      if (path == null) return;
      if (!path.toLowerCase().endsWith('.pdf')) {
        if (mounted) _say(AppLocalizations.of(context).notAPdf);
        return;
      }
      await _useFile(File(path), InputType.pdf);
    } on PlatformException {
      if (mounted) _say(AppLocalizations.of(context).errorFileUnopenable);
    }
  }

  Future<void> _useFile(File file, InputType type) async {
    int? size;
    Uint8List? preview;
    try {
      size = await file.length();
      if (type == InputType.image && size <= _previewBytesLimit) {
        preview = await file.readAsBytes();
      }
    } on FileSystemException {
      if (mounted) _say(AppLocalizations.of(context).errorFileUnopenable);
      return;
    }
    if (!mounted) return;
    setState(() {
      _type = type;
      _file = file;
      _preview = preview;
      _fileSize = size;
      _clipboardOffer = false;
    });
  }

  Submission? _submission() {
    switch (_type) {
      case InputType.text:
        final value = _text.text.trim();
        if (value.isEmpty) return null;
        final link = _looksLikeLink && !value.contains(RegExp(r'\s'));
        return link
            ? Submission.link(value.startsWith('www.') ? 'https://$value' : value)
            : Submission.text(value);
      case InputType.image:
        final file = _file;
        return file == null ? null : Submission.image(file, _preview);
      case InputType.pdf:
        final file = _file;
        return file == null ? null : Submission.document(file);
    }
  }

  void _check() {
    final submission = _submission();
    if (submission == null) return;
    // Let go of the text box, or the keyboard opens again over the page on return.
    FocusManager.instance.primaryFocus?.unfocus();
    unawaited(
      Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => CheckingScreen(
            services: _services,
            submission: submission,
            deep: _type == InputType.text && _deep,
            onFinished: clearInput,
          ),
        ),
      ),
    );
  }

  /// A share from another app: added as the matching kind, and checked at once.
  Future<void> receiveShare(SharedContent content) async {
    final l10n = AppLocalizations.of(context);
    if (content.isError) {
      _say(l10n.errorShareFileUnopenable);
      return;
    }
    clearInput();
    if (content.isFile) {
      final mime = content.mimeType ?? '';
      final isPdf = mime == 'application/pdf' || content.value.toLowerCase().endsWith('.pdf');
      await _useFile(File(content.value), isPdf ? InputType.pdf : InputType.image);
    } else {
      setState(() => _type = InputType.text);
      _text.text = content.value;
    }
    if (mounted && _hasInput) _check();
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final t = FactifyText.of(context);
    final l10n = AppLocalizations.of(context);

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 20),
          children: [
            _Header(services: _services, ready: _serviceReady, onProbe: _probeService),
            const SizedBox(height: 26),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 2),
              child: Text(l10n.homeTitle, style: t.display),
            ),
            const SizedBox(height: 18),
            _Composer(
              type: _type,
              hasInput: _hasInput,
              onSelect: _select,
              onLocked: (_) => _say(l10n.inputLocked),
              child: switch (_type) {
                InputType.text => _TextInput(
                  controller: _text,
                  isLink: _looksLikeLink,
                  clipboardOffer: _clipboardOffer && !_hasInput,
                  deep: _deep,
                  onPaste: _paste,
                  onClear: clearInput,
                  onToggleDeep: () => setState(() => _deep = !_deep),
                ),
                InputType.image when _file == null => _DropArea(
                  icon: FxIcons.addImage,
                  title: l10n.pickImageTitle,
                  body: l10n.pickImageBody,
                  buttons: [
                    _DropButton(
                      icon: FxIcons.gallery,
                      label: l10n.sourceGallery,
                      primary: true,
                      onTap: () => _pickImage(ImageSource.gallery),
                    ),
                    _DropButton(
                      icon: FxIcons.camera,
                      label: l10n.sourceCamera,
                      onTap: () => _pickImage(ImageSource.camera),
                    ),
                  ],
                ),
                InputType.pdf when _file == null => _DropArea(
                  icon: FxIcons.addFile,
                  title: l10n.pickPdfTitle,
                  body: l10n.pickPdfBody,
                  buttons: [
                    _DropButton(
                      icon: FxIcons.folder,
                      label: l10n.choosePdf,
                      primary: true,
                      onTap: _pickPdf,
                    ),
                  ],
                ),
                _ => _FilePreview(
                  image: _type == InputType.image,
                  preview: _preview,
                  name: _nameOf(_file!),
                  size: _fileSize,
                  onClear: clearInput,
                ),
              },
            ),
            const SizedBox(height: 14),
            FxButton(
              label: l10n.checkNow,
              trailingIcon: FxIcons.forward,
              onPressed: _hasInput ? _check : null,
            ),
            const SizedBox(height: 10),
            Text(
              _type == InputType.text && _deep ? l10n.checkTakesDeep : l10n.checkTakes,
              textAlign: TextAlign.center,
              style: t.caption.copyWith(color: k.ink3),
            ),
            _Recent(services: _services, onSeeAll: widget.onSeeAll),
          ],
        ),
      ),
    );
  }
}

String _nameOf(File file) => file.uri.pathSegments.isEmpty ? file.path : file.uri.pathSegments.last;

String _sizeOf(int bytes) {
  if (bytes >= 1024 * 1024) return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  return '${(bytes / 1024).ceil()} KB';
}

/// Avatar, greeting and date; the service's status and the language switch.
class _Header extends StatelessWidget {
  const _Header({required this.services, required this.ready, required this.onProbe});

  final AppServices services;
  final bool? ready;
  final VoidCallback onProbe;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final locale = Localizations.localeOf(context);
    final hindi = locale.languageCode == 'hi';
    final (dot, status) = switch (ready) {
      true => (k.tC, l10n.statusOnline),
      false => (k.fC, l10n.statusOffline),
      null => (k.ink3, l10n.statusChecking),
    };

    return SizedBox(
      height: 44,
      child: Row(
        children: [
          ListenableBuilder(
            listenable: services.auth,
            builder: (context, _) {
              final name = services.auth.account?.displayName;
              final shown = (name == null || name.trim().isEmpty) ? null : name.trim();
              return Expanded(
                child: Row(
                  children: [
                    Container(
                      width: 36,
                      height: 36,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(color: k.accS, shape: BoxShape.circle),
                      child: Text(
                        (shown ?? 'F').characters.first.toUpperCase(),
                        style: FactifyText.sans(14, weight: FontWeight.w700, color: k.acc),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            shown == null ? l10n.homeGreetingGuest : l10n.homeGreeting(shown),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: FactifyText.sans(14, weight: FontWeight.w600, color: k.ink),
                          ),
                          Text(
                            DateFormat(
                              'EEEE, d MMMM',
                              locale.toLanguageTag(),
                            ).format(DateTime.now()),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: FactifyText.sans(12, color: k.ink3),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              );
            },
          ),
          Semantics(
            button: true,
            label: status,
            child: GestureDetector(
              onTap: onProbe,
              behavior: HitTestBehavior.opaque,
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 4),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 6,
                      height: 6,
                      decoration: BoxDecoration(color: dot, shape: BoxShape.circle),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      status,
                      style: FactifyText.sans(12, weight: FontWeight.w600, color: k.ink2),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(width: 6),
          Semantics(
            button: true,
            label: l10n.switchLanguage,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => unawaited(services.language.choose(Locale(hindi ? 'en' : 'hi'))),
              child: Container(
                height: 36,
                padding: const EdgeInsets.symmetric(horizontal: 10),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: k.line),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(FxIcons.language, size: 16, color: k.ink),
                    const SizedBox(width: 5),
                    Text(
                      hindi ? 'हि' : 'EN',
                      style: FactifyText.sans(12, weight: FontWeight.w600, color: k.ink),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// The composer card: the three kinds as tabs over the input itself.
class _Composer extends StatelessWidget {
  const _Composer({
    required this.type,
    required this.hasInput,
    required this.onSelect,
    required this.onLocked,
    required this.child,
  });

  final InputType type;
  final bool hasInput;
  final ValueChanged<InputType> onSelect;
  final ValueChanged<InputType> onLocked;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    return Container(
      padding: const EdgeInsets.all(6),
      decoration: BoxDecoration(
        color: k.sf,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: k.line),
        boxShadow: const [
          BoxShadow(
            offset: Offset(0, 12),
            blurRadius: 32,
            spreadRadius: -22,
            color: Color(0x4D000000),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          FxSegmented<InputType>(
            segments: [
              FxSegment(InputType.text, l10n.inputTypeText, icon: FxIcons.text),
              FxSegment(InputType.image, l10n.inputTypeImage, icon: FxIcons.image),
              FxSegment(InputType.pdf, l10n.inputTypePdf, icon: FxIcons.pdf),
            ],
            selected: type,
            locked: hasInput ? InputType.values.toSet() : const {},
            onChanged: onSelect,
            onLocked: onLocked,
          ),
          AnimatedSize(
            duration: const Duration(milliseconds: 200),
            alignment: Alignment.topCenter,
            child: child,
          ),
        ],
      ),
    );
  }
}

/// The text box (Newsreader 21, 196 tall) and the row of actions under it.
class _TextInput extends StatelessWidget {
  const _TextInput({
    required this.controller,
    required this.isLink,
    required this.clipboardOffer,
    required this.deep,
    required this.onPaste,
    required this.onClear,
    required this.onToggleDeep,
  });

  final TextEditingController controller;
  final bool isLink;
  final bool clipboardOffer;
  final bool deep;
  final VoidCallback onPaste;
  final VoidCallback onClear;
  final VoidCallback onToggleDeep;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final t = FactifyText.of(context);
    final l10n = AppLocalizations.of(context);
    final filled = controller.text.trim().isNotEmpty;

    final Widget left;
    if (clipboardOffer && !filled) {
      left = FxChip(label: l10n.pasteCopiedText, icon: FxIcons.paste, height: 30, onTap: onPaste);
    } else {
      final (icon, label, colour, onTap) = isLink
          ? (FxIcons.link, l10n.inputLinkDetected, k.acc, null)
          : filled
          ? (FxIcons.close, l10n.removeInput, k.ink3, onClear)
          : (FxIcons.chat, l10n.shareFromWhatsApp, k.ink3, null);
      left = Semantics(
        button: onTap != null,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, size: 15, color: colour),
                const SizedBox(width: 6),
                Flexible(
                  child: Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: FactifyText.sans(12, weight: FontWeight.w500, color: colour),
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SizedBox(
          height: 196,
          child: TextField(
            controller: controller,
            expands: true,
            maxLines: null,
            textAlignVertical: TextAlignVertical.top,
            keyboardType: TextInputType.multiline,
            style: t.input,
            decoration: InputDecoration(
              hintText: l10n.inputTextHint,
              hintStyle: t.input.copyWith(color: k.ink3),
              filled: false,
              border: InputBorder.none,
              enabledBorder: InputBorder.none,
              focusedBorder: InputBorder.none,
              contentPadding: const EdgeInsets.fromLTRB(12, 16, 12, 8),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(8, 0, 6, 6),
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 32),
            child: Row(
              children: [
                Expanded(
                  child: Align(alignment: AlignmentDirectional.centerStart, child: left),
                ),
                const SizedBox(width: 8),
                FxChip(
                  label: l10n.deepChip,
                  icon: FxIcons.deep,
                  height: 30,
                  fontSize: 12,
                  iconSize: 14,
                  selected: deep,
                  background: deep ? k.accS : Colors.transparent,
                  foreground: deep ? k.acc : k.ink3,
                  border: deep ? null : k.line,
                  onTap: onToggleDeep,
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _DropArea extends StatelessWidget {
  const _DropArea({
    required this.icon,
    required this.title,
    required this.body,
    required this.buttons,
  });

  final IconData icon;
  final String title;
  final String body;
  final List<Widget> buttons;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(10, 30, 10, 12),
      child: Column(
        children: [
          Container(
            width: 52,
            height: 52,
            decoration: BoxDecoration(color: k.accS, borderRadius: BorderRadius.circular(17)),
            child: Icon(icon, size: 25, color: k.acc),
          ),
          const SizedBox(height: 12),
          Text(
            title,
            textAlign: TextAlign.center,
            style: FactifyText.sans(16, weight: FontWeight.w600, color: k.ink),
          ),
          const SizedBox(height: 4),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 240),
            child: Text(
              body,
              textAlign: TextAlign.center,
              style: FactifyText.sans(12.5, color: k.ink3).copyWith(height: 1.5),
            ),
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              for (final (index, button) in buttons.indexed) ...[
                if (index > 0) const SizedBox(width: 8),
                Expanded(child: button),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

class _DropButton extends StatelessWidget {
  const _DropButton({
    required this.icon,
    required this.label,
    required this.onTap,
    this.primary = false,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool primary;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final fg = primary ? k.onAcc : k.ink;
    return Material(
      color: primary ? k.acc : k.sf2,
      borderRadius: BorderRadius.circular(12),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: SizedBox(
          height: 44,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 18, color: fg),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: FactifyText.sans(14, weight: FontWeight.w600, color: fg),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The added picture or PDF: its preview, name and size, and the X to remove it.
class _FilePreview extends StatelessWidget {
  const _FilePreview({
    required this.image,
    required this.preview,
    required this.name,
    required this.size,
    required this.onClear,
  });

  final bool image;
  final Uint8List? preview;
  final String name;
  final int? size;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final shown = preview;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (image)
          Container(
            height: 170,
            margin: const EdgeInsets.only(top: 6),
            clipBehavior: Clip.antiAlias,
            decoration: BoxDecoration(color: k.sf2, borderRadius: BorderRadius.circular(18)),
            child: shown == null
                ? Icon(FxIcons.image, size: 40, color: k.ink3)
                : Image.memory(
                    shown,
                    fit: BoxFit.cover,
                    errorBuilder: (_, _, _) => Icon(FxIcons.image, size: 40, color: k.ink3),
                  ),
          ),
        Padding(
          padding: const EdgeInsets.fromLTRB(8, 12, 8, 6),
          child: Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(color: k.accS, borderRadius: BorderRadius.circular(12)),
                child: Icon(image ? FxIcons.image : FxIcons.pdf, size: 18, color: k.acc),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: FactifyText.sans(13.5, weight: FontWeight.w600, color: k.ink),
                    ),
                    if (size != null)
                      Text(_sizeOf(size!), style: FactifyText.sans(11.5, color: k.ink3)),
                  ],
                ),
              ),
              FxCircleButton(
                icon: FxIcons.close,
                tooltip: l10n.removeInput,
                onPressed: onClear,
                size: 32,
                iconSize: 16,
                background: k.sf2,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// The last three checks, opening their answers; "See all" goes to History.
class _Recent extends StatelessWidget {
  const _Recent({required this.services, required this.onSeeAll});

  final AppServices services;
  final VoidCallback? onSeeAll;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final t = FactifyText.of(context);
    final l10n = AppLocalizations.of(context);
    return ListenableBuilder(
      listenable: services.history,
      builder: (context, _) {
        final recent = services.history.records.take(3).toList();
        if (recent.isEmpty) return const SizedBox.shrink();
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(4, 28, 4, 10),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.baseline,
                textBaseline: TextBaseline.alphabetic,
                children: [
                  Expanded(child: Text(l10n.recentTitle, style: t.section)),
                  if (onSeeAll != null)
                    Semantics(
                      button: true,
                      child: GestureDetector(
                        onTap: onSeeAll,
                        behavior: HitTestBehavior.opaque,
                        child: Padding(
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          child: Text(
                            l10n.seeAll,
                            style: FactifyText.sans(12.5, weight: FontWeight.w600, color: k.acc),
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
            FxListCard(
              bordered: true,
              children: [
                for (final record in recent) _RecentRow(services: services, record: record),
              ],
            ),
          ],
        );
      },
    );
  }
}

class _RecentRow extends StatelessWidget {
  const _RecentRow({required this.services, required this.record});

  final AppServices services;
  final HistoryRecord record;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final locale = Localizations.localeOf(context).toLanguageTag();
    final verdict = record.factVerdict;
    return InkWell(
      onTap: () => openHistoryRecord(context, services, record),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(color: k.sf2, borderRadius: BorderRadius.circular(12)),
              child: Icon(FxIcons.forKind(record.kind), size: 17, color: k.ink2),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    record.summary.isEmpty ? l10n.yourPicture : record.summary,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: FactifyText.sans(13.5, weight: FontWeight.w500, color: k.ink),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${DateFormat.Hm(locale).format(record.checkedAt.toLocal())} · '
                    '${l10n.historySources(record.sourceCount)}',
                    style: FactifyText.sans(11.5, color: k.ink3),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            FxVerdictPill(verdict: verdict, label: ActionStyle.word(verdict, l10n)),
          ],
        ),
      ),
    );
  }
}
