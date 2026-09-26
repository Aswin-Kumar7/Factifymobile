/// Home: choose what to check, add it, and check it.
///
/// One kind of input at a time - text or a link, a picture, or a PDF. Once something
/// is added the other kinds are locked, and it is removed with its own X to switch:
/// a check is of one thing, and a screen that took a message, a picture and a file
/// together left it unclear which one the answer was about.
///
/// The check itself opens on its own page (`checking_screen.dart`), and the answer
/// on another (`result_screen.dart`); past checks live on the History tab. This page
/// only ever holds what is about to be checked.
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

import '../api/share_intake.dart';
import '../app_services.dart';
import '../l10n/app_localizations.dart';
import '../models/submission.dart';
import '../theme/colors.dart';
import '../widgets/language_menu.dart';
import 'checking_screen.dart';

/// The largest picture read into memory for its preview.
const int _previewBytesLimit = 4 * 1024 * 1024;

/// What is being checked: exactly one of these at a time.
enum InputType { text, image, pdf }

class HomeScreen extends StatefulWidget {
  const HomeScreen({required this.services, super.key});

  final AppServices services;

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

  /// Reads the clipboard, only now, because the person asked, and checks it.
  Future<void> _pasteAndCheck() async {
    setState(() => _clipboardOffer = false);
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    final text = data?.text?.trim() ?? '';
    if (!mounted || text.isEmpty) return;
    _text.text = text;
    _check();
  }

  void _select(InputType type) {
    if (type == _type) return;
    if (_hasInput) {
      _say(AppLocalizations.of(context).inputLocked);
      return;
    }
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
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final auth = _services.auth;

    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
          children: [
            Row(
              children: [
                Expanded(
                  child: ListenableBuilder(
                    listenable: auth,
                    builder: (context, _) {
                      final account = auth.account;
                      return Text(
                        account == null
                            ? l10n.homeGreetingGuest
                            : l10n.homeGreeting(account.displayName),
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.titleMedium?.copyWith(
                          color: FactifyColors.inkMuted,
                          fontWeight: FontWeight.w600,
                        ),
                      );
                    },
                  ),
                ),
                _StatusPill(ready: _serviceReady, onTap: _probeService),
                const SizedBox(width: 8),
                LanguageMenu(preference: _services.language),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              l10n.homeTitle,
              style: theme.textTheme.headlineSmall?.copyWith(
                fontWeight: FontWeight.w800,
                letterSpacing: -0.5,
                height: 1.2,
              ),
            ),
            const SizedBox(height: 18),
            _TypeSelector(selected: _type, locked: _hasInput, onSelect: _select),
            const SizedBox(height: 16),
            AnimatedSwitcher(
              duration: const Duration(milliseconds: 200),
              child: switch (_type) {
                InputType.text => _TextPanel(
                  key: const ValueKey('text'),
                  controller: _text,
                  showLinkNote: _looksLikeLink,
                  clipboardOffer: _clipboardOffer && !_hasInput,
                  onPasteAndCheck: _pasteAndCheck,
                  onDismissClipboard: () => setState(() => _clipboardOffer = false),
                  onClear: clearInput,
                ),
                InputType.image => _ImagePanel(
                  key: const ValueKey('image'),
                  file: _file,
                  preview: _preview,
                  size: _fileSize,
                  onGallery: () => _pickImage(ImageSource.gallery),
                  onCamera: () => _pickImage(ImageSource.camera),
                  onClear: clearInput,
                ),
                InputType.pdf => _PdfPanel(
                  key: const ValueKey('pdf'),
                  file: _file,
                  size: _fileSize,
                  onPick: _pickPdf,
                  onClear: clearInput,
                ),
              },
            ),
            if (_type == InputType.text) ...[
              const SizedBox(height: 12),
              _DeepSwitch(value: _deep, onChanged: (value) => setState(() => _deep = value)),
            ],
            const SizedBox(height: 18),
            FilledButton.icon(
              onPressed: _hasInput ? _check : null,
              icon: const Icon(Icons.fact_check_rounded),
              label: Text(l10n.checkNow),
              style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(56)),
            ),
            const SizedBox(height: 24),
            _Tip(text: l10n.emptyBody),
          ],
        ),
      ),
    );
  }
}

/// Text or link, Image, PDF: one at a time, the others locked while one is added.
class _TypeSelector extends StatelessWidget {
  const _TypeSelector({required this.selected, required this.locked, required this.onSelect});

  final InputType selected;
  final bool locked;
  final ValueChanged<InputType> onSelect;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: FactifyColors.ground,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: FactifyColors.line),
      ),
      child: Row(
        children: [
          for (final (type, icon, label) in [
            (InputType.text, Icons.notes_rounded, l10n.inputTypeText),
            (InputType.image, Icons.image_outlined, l10n.inputTypeImage),
            (InputType.pdf, Icons.picture_as_pdf_outlined, l10n.inputTypePdf),
          ])
            Expanded(
              child: _TypeButton(
                icon: icon,
                label: label,
                selected: type == selected,
                enabled: type == selected || !locked,
                onTap: () => onSelect(type),
              ),
            ),
        ],
      ),
    );
  }
}

class _TypeButton extends StatelessWidget {
  const _TypeButton({
    required this.icon,
    required this.label,
    required this.selected,
    required this.enabled,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool selected;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colour = selected ? FactifyColors.emeraldDeep : FactifyColors.inkMuted;
    return Semantics(
      button: true,
      selected: selected,
      enabled: enabled,
      child: Opacity(
        opacity: enabled ? 1 : 0.38,
        child: Material(
          color: selected ? Colors.white : Colors.transparent,
          elevation: selected ? 1 : 0,
          shadowColor: Colors.black26,
          borderRadius: BorderRadius.circular(12),
          child: InkWell(
            // Still tappable when locked, so the lock can explain itself.
            onTap: onTap,
            borderRadius: BorderRadius.circular(12),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 4),
              child: Column(
                children: [
                  Icon(icon, size: 22, color: colour),
                  const SizedBox(height: 4),
                  Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: colour,
                      fontWeight: selected ? FontWeight.w700 : FontWeight.w600,
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _TextPanel extends StatelessWidget {
  const _TextPanel({
    required this.controller,
    required this.showLinkNote,
    required this.clipboardOffer,
    required this.onPasteAndCheck,
    required this.onDismissClipboard,
    required this.onClear,
    super.key,
  });

  final TextEditingController controller;
  final bool showLinkNote;
  final bool clipboardOffer;
  final VoidCallback onPasteAndCheck;
  final VoidCallback onDismissClipboard;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final filled = controller.text.isNotEmpty;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (clipboardOffer) ...[
          _ClipboardOffer(onCheck: onPasteAndCheck, onDismiss: onDismissClipboard),
          const SizedBox(height: 10),
        ],
        TextField(
          controller: controller,
          minLines: 5,
          maxLines: 10,
          textInputAction: TextInputAction.newline,
          decoration: InputDecoration(
            hintText: l10n.inputTextHint,
            contentPadding: const EdgeInsets.fromLTRB(16, 16, 8, 16),
            suffixIcon: filled
                ? Align(
                    widthFactor: 1,
                    heightFactor: 1,
                    alignment: Alignment.topCenter,
                    child: IconButton(
                      tooltip: l10n.removeInput,
                      onPressed: onClear,
                      icon: const Icon(Icons.close_rounded),
                    ),
                  )
                : null,
          ),
        ),
        if (showLinkNote) ...[
          const SizedBox(height: 8),
          Row(
            children: [
              const Icon(Icons.link_rounded, size: 18, color: FactifyColors.emeraldDark),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  l10n.inputLinkDetected,
                  style: theme.textTheme.bodySmall?.copyWith(color: FactifyColors.emeraldDeep),
                ),
              ),
            ],
          ),
        ],
      ],
    );
  }
}

class _ImagePanel extends StatelessWidget {
  const _ImagePanel({
    required this.file,
    required this.preview,
    required this.size,
    required this.onGallery,
    required this.onCamera,
    required this.onClear,
    super.key,
  });

  final File? file;
  final Uint8List? preview;
  final int? size;
  final VoidCallback onGallery;
  final VoidCallback onCamera;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final chosen = file;
    if (chosen == null) {
      return _DropArea(
        icon: Icons.add_photo_alternate_outlined,
        title: l10n.pickImageTitle,
        body: l10n.pickImageBody,
        actions: [
          Expanded(
            child: FilledButton.tonalIcon(
              onPressed: onGallery,
              icon: const Icon(Icons.photo_library_outlined),
              label: Text(l10n.sourceGallery),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: OutlinedButton.icon(
              onPressed: onCamera,
              icon: const Icon(Icons.photo_camera_outlined),
              label: Text(l10n.sourceCamera),
            ),
          ),
        ],
      );
    }

    final image = preview;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Stack(
            children: [
              Container(
                height: 220,
                color: FactifyColors.ground,
                child: image == null
                    ? const Center(
                        child: Icon(Icons.image_outlined, size: 48, color: FactifyColors.inkMuted),
                      )
                    : Image.memory(
                        image,
                        fit: BoxFit.contain,
                        errorBuilder: (_, _, _) => const Center(
                          child: Icon(
                            Icons.image_outlined,
                            size: 48,
                            color: FactifyColors.inkMuted,
                          ),
                        ),
                      ),
              ),
              PositionedDirectional(top: 8, end: 8, child: _RemoveButton(onPressed: onClear)),
            ],
          ),
          _FileLine(icon: Icons.image_outlined, name: _nameOf(chosen), size: size),
        ],
      ),
    );
  }
}

class _PdfPanel extends StatelessWidget {
  const _PdfPanel({
    required this.file,
    required this.size,
    required this.onPick,
    required this.onClear,
    super.key,
  });

  final File? file;
  final int? size;
  final VoidCallback onPick;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final chosen = file;
    if (chosen == null) {
      return _DropArea(
        icon: Icons.upload_file_rounded,
        title: l10n.pickPdfTitle,
        body: l10n.pickPdfBody,
        actions: [
          Expanded(
            child: FilledButton.tonalIcon(
              onPressed: onPick,
              icon: const Icon(Icons.folder_open_rounded),
              label: Text(l10n.choosePdf),
            ),
          ),
        ],
      );
    }
    return Card(
      child: Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(4, 4, 4, 4),
        child: Row(
          children: [
            Expanded(
              child: _FileLine(
                icon: Icons.picture_as_pdf_rounded,
                name: _nameOf(chosen),
                size: size,
                large: true,
              ),
            ),
            _RemoveButton(onPressed: onClear, flat: true),
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

class _FileLine extends StatelessWidget {
  const _FileLine({required this.icon, required this.name, this.size, this.large = false});

  final IconData icon;
  final String name;
  final int? size;
  final bool large;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        children: [
          Container(
            width: large ? 44 : 34,
            height: large ? 44 : 34,
            decoration: BoxDecoration(
              color: FactifyColors.emeraldTint,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, color: FactifyColors.emeraldDark, size: large ? 24 : 20),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
                ),
                if (size != null)
                  Text(
                    _sizeOf(size!),
                    style: theme.textTheme.bodySmall?.copyWith(color: FactifyColors.inkMuted),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _RemoveButton extends StatelessWidget {
  const _RemoveButton({required this.onPressed, this.flat = false});

  final VoidCallback onPressed;
  final bool flat;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return IconButton(
      tooltip: l10n.removeInput,
      onPressed: onPressed,
      style: flat
          ? null
          : IconButton.styleFrom(
              backgroundColor: Colors.black.withValues(alpha: 0.55),
              foregroundColor: Colors.white,
            ),
      icon: const Icon(Icons.close_rounded),
    );
  }
}

class _DropArea extends StatelessWidget {
  const _DropArea({
    required this.icon,
    required this.title,
    required this.body,
    required this.actions,
  });

  final IconData icon;
  final String title;
  final String body;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.fromLTRB(18, 22, 18, 18),
      decoration: BoxDecoration(
        color: FactifyColors.ground,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: FactifyColors.line, width: 1.2),
      ),
      child: Column(
        children: [
          Container(
            width: 56,
            height: 56,
            decoration: const BoxDecoration(
              color: FactifyColors.emeraldTint,
              shape: BoxShape.circle,
            ),
            child: Icon(icon, color: FactifyColors.emeraldDark, size: 28),
          ),
          const SizedBox(height: 12),
          Text(title, style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Text(
            body,
            textAlign: TextAlign.center,
            style: theme.textTheme.bodySmall?.copyWith(color: FactifyColors.inkMuted),
          ),
          const SizedBox(height: 16),
          Row(children: actions),
        ],
      ),
    );
  }
}

class _DeepSwitch extends StatelessWidget {
  const _DeepSwitch({required this.value, required this.onChanged});

  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Material(
      color: value ? FactifyColors.emeraldTint : Colors.white,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: value ? FactifyColors.emeraldSoft : FactifyColors.line),
      ),
      clipBehavior: Clip.antiAlias,
      child: SwitchListTile.adaptive(
        value: value,
        onChanged: onChanged,
        contentPadding: const EdgeInsetsDirectional.fromSTEB(12, 0, 8, 0),
        secondary: Icon(
          Icons.travel_explore_rounded,
          color: value ? FactifyColors.emeraldDark : FactifyColors.inkMuted,
        ),
        title: Text(l10n.deepCheck, style: const TextStyle(fontWeight: FontWeight.w700)),
        subtitle: Text(l10n.deepCheckHint),
      ),
    );
  }
}

class _Tip extends StatelessWidget {
  const _Tip({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      const Icon(Icons.lightbulb_outline_rounded, size: 18, color: FactifyColors.inkMuted),
      const SizedBox(width: 8),
      Expanded(
        child: Text(
          text,
          style: Theme.of(context).textTheme.bodySmall?.copyWith(color: FactifyColors.inkMuted),
        ),
      ),
    ],
  );
}

/// Offers to check what was copied, without reading it until asked.
class _ClipboardOffer extends StatelessWidget {
  const _ClipboardOffer({required this.onCheck, required this.onDismiss});

  final VoidCallback onCheck;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    return Material(
      color: FactifyColors.emeraldTint,
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(12, 4, 4, 4),
        child: Row(
          children: [
            const Icon(Icons.content_paste_rounded, size: 18, color: FactifyColors.emeraldDeep),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                l10n.clipboardOffer,
                style: theme.textTheme.bodySmall?.copyWith(color: FactifyColors.emeraldDeep),
              ),
            ),
            TextButton(onPressed: onCheck, child: Text(l10n.clipboardPasteAndCheck)),
            IconButton(
              onPressed: onDismiss,
              icon: const Icon(Icons.close, size: 18),
              tooltip: l10n.clipboardDismiss,
              visualDensity: VisualDensity.compact,
            ),
          ],
        ),
      ),
    );
  }
}

/// Whether the service can check right now: checking, online, or offline.
class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.ready, required this.onTap});

  final bool? ready;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final (colour, label) = switch (ready) {
      true => (FactifyColors.emerald, l10n.statusOnline),
      false => (theme.colorScheme.error, l10n.statusOffline),
      null => (FactifyColors.inkMuted, l10n.statusChecking),
    };
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(999),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: colour.withValues(alpha: 0.10),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 7,
              height: 7,
              decoration: BoxDecoration(color: colour, shape: BoxShape.circle),
            ),
            const SizedBox(width: 6),
            Text(
              label,
              style: theme.textTheme.labelSmall?.copyWith(
                color: colour,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
