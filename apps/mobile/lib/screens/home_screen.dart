/// Intake and result (M44).
///
/// Share-sheet intake is the primary path, not a secondary one: the content this
/// app exists to check arrives in a forward, and asking someone to copy it into
/// a text box loses most of them. Manual entry, the gallery, the camera and the
/// file picker are fallbacks, in roughly that order of use.
///
/// Permissions: the camera is the only one requested, and only when the camera
/// button is pressed. Share-sheet intake hands us a file the sender already
/// chose, and gallery selection goes through the system picker, which grants
/// access to one file without a storage permission.
library;

import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart' show kReleaseMode;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import '../api/client.dart';
import '../api/share_intake.dart';
import '../auth/auth_service.dart';
import '../l10n/app_localizations.dart';
import '../l10n/language_preference.dart';
import '../l10n/phrases.dart';
import '../models/submission.dart';
import '../models/verdict.dart';
import '../theme/colors.dart';
import '../widgets/correction_sheet.dart';
import '../widgets/history_strip.dart';
import '../widgets/intake_bar.dart';
import '../widgets/language_menu.dart';
import '../widgets/image_reading_card.dart';
import '../widgets/submission_card.dart';
import '../widgets/verdict_card.dart';
import 'account_screen.dart';
import 'evidence_screen.dart';

/// Largest image read into memory for the preview thumbnail. See
/// [Submission.image] for why the bytes are kept rather than the path.
const int _thumbnailBytesLimit = 2 * 1024 * 1024;

/// A message chosen now and put into words when the screen is drawn.
///
/// Errors are stored this way rather than as finished strings. A string built
/// when the error happened stays in that language, so a reader who switches to
/// Hindi to understand an error would find the error still in English.
typedef _Phrase = String Function(AppLocalizations l10n);

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.client, required this.language, this.auth});

  final FactifyClient client;
  final LanguagePreference language;

  /// Sign-in and the account; the account button opens it.
  final AuthService? auth;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  final TextEditingController _input = TextEditingController();
  final ShareIntake _intake = ShareIntake();
  final ImagePicker _camera = ImagePicker();
  StreamSubscription<SharedContent>? _shareSubscription;

  int _tab = 0;
  Verdict? _verdict;
  Submission? _submission;
  _Phrase? _error;
  bool _errorRetryable = false;
  bool _busy = false;
  bool _reporting = false;
  String? _pendingCaseId;
  final List<HistoryEntry> _history = [];
  final Set<String> _reported = {};

  /// How much of a file upload has gone, from 0 to 1, or null when no upload is
  /// under way.
  double? _uploadProgress;

  /// Whether copied text is waiting to be checked (PLAN 1.7.2).
  ///
  /// Set from `Clipboard.hasStrings`, which asks whether text is there without
  /// reading it. Nothing on the clipboard is read until the person taps, and
  /// Android then shows its own notice that the app pasted — which is the honest
  /// moment for that notice to appear.
  bool _clipboardOffer = false;

  /// Whether the service can verify right now. Three states, honestly:
  /// unknown (null) until the first probe answers, then ready or not.
  bool? _serviceReady;

  /// Re-runs the submission that produced the current error. Retry exists
  /// because [ApiFailure.retryable] was modelled and then ignored — the client
  /// knew "try again shortly" from "your request was wrong" and the interface
  /// collapsed both into a dead end.
  Future<void> Function()? _lastRun;

  /// "Check again": the same submission, checked fresh rather than served from the
  /// server's store. Separate from [_lastRun], which retries a failed request as
  /// it was.
  Future<void> Function()? _recheckRun;

  /// What the last finished check was of, as the input box held it ('' for a
  /// picture or document). Null while a check runs and before the first one.
  String? _checkedText;

  /// Whether text and links are checked deeply. Pictures and documents always get
  /// the normal check.
  bool _deep = false;

  /// A running deep check's progress: claims done of total (0 of 0 while its claims
  /// are still being read out).
  (int, int)? _deepProgress;

  /// The interface language, sent with every check so the verdict can come back
  /// in the language it will be read in (PLAN 1.7.6). The phone's language unless
  /// the reader picked another from the language menu.
  String get _language => Localizations.localeOf(context).languageCode;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _listenForShares();
    _probeService();
    // After the first frame: Android answers clipboard queries only for the app
    // that has focus, and the window does not have it during initState.
    WidgetsBinding.instance.addPostFrameCallback((_) => unawaited(_offerClipboard()));
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Coming back to Factify is the moment someone has usually just copied the
    // thing they want checked.
    if (state == AppLifecycleState.resumed) unawaited(_offerClipboard());
  }

  Future<void> _offerClipboard() async {
    if (_busy || _input.text.trim().isNotEmpty) return;
    final bool hasText;
    try {
      hasText = await Clipboard.hasStrings();
    } on Exception {
      // A platform that cannot answer has nothing to offer.
      return;
    }
    if (mounted && hasText != _clipboardOffer) setState(() => _clipboardOffer = hasText);
  }

  /// Reads the clipboard — only now, because the person asked — and checks it.
  Future<void> _checkClipboard() async {
    setState(() => _clipboardOffer = false);
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    final text = data?.text?.trim() ?? '';
    if (!mounted || text.isEmpty) return;
    _input.text = text;
    await _verify(text);
  }

  Future<void> _probeService() async {
    final ready = await widget.client.ready();
    if (!mounted) return;
    setState(() {
      _serviceReady = ready;
      // A release build compiled without FACTIFY_API still points at the
      // emulator's host address, which no real phone can reach. That build is
      // misconfigured rather than offline, and whoever installed it needs to
      // know which.
      if (!ready && kReleaseMode && apiUsesEmulatorDefault) {
        _error = (l10n) => l10n.errorNoServerAddress;
        _errorRetryable = false;
      }
    });
  }

  /// Two channels, and both are needed.
  ///
  /// The stream delivers shares while the app is already running; [initial]
  /// delivers the share that *launched* it, which arrives before Dart is
  /// listening. Wiring only the stream is the common bug — the first share
  /// after a cold start silently does nothing.
  void _listenForShares() {
    _shareSubscription = _intake.stream.listen(
      _handleShared,
      onError: (Object error) => setState(() {
        _error = (l10n) => l10n.errorShareUnreadable;
        _errorRetryable = false;
      }),
    );
    _intake.initial().then((content) {
      if (content != null) _handleShared(content);
    });
  }

  void _handleShared(SharedContent content) {
    setState(() {
      _tab = 0;
      // Something arrived to be checked; an offer to check the clipboard instead
      // would only compete with it.
      _clipboardOffer = false;
    });
    if (content.isError) {
      // The share arrived but could not be read — typically a gallery app whose
      // grant did not reach us. Said out loud, and whatever result is already on
      // screen stays there: a failed share must not look like a cleared one.
      setState(() {
        _error = (l10n) => l10n.errorShareFileUnopenable;
        _errorRetryable = false;
      });
      return;
    }
    if (content.isFile) {
      unawaited(_verifyFile(File(content.value)));
      return;
    }
    _input.text = content.value;
    unawaited(_verify(content.value));
  }

  void _beginRun(Submission submission) {
    setState(() {
      _busy = true;
      _error = null;
      _verdict = null;
      _pendingCaseId = null;
      _uploadProgress = null;
      _clipboardOffer = false;
      _submission = submission;
    });
  }

  /// Keep a finished result where the user can get back to it.
  void _finish(Verdict verdict) {
    // The check cost a credit; show the balance the server now holds.
    unawaited(widget.auth?.refreshAccount());
    final submission = _submission;
    setState(() {
      _verdict = verdict;
      if (submission != null) {
        _history.insert(0, HistoryEntry(submission: submission, verdict: verdict));
      }
    });
  }

  void _fail(ApiFailure failure) {
    setState(() {
      _error = (l10n) => l10n.describeFailure(failure);
      _errorRetryable = failure.retryable;
    });
    // A failure is the moment the status dot is most likely stale.
    unawaited(_probeService());
  }

  Future<void> _verify(String raw, {bool recheck = false}) async {
    final value = raw.trim();
    if (value.isEmpty) return;
    _lastRun = () => _verify(raw);
    _recheckRun = () => _verify(raw, recheck: true);
    _checkedText = null;
    final language = _language;

    // A bare URL and a block of text are different endpoints on the server, so
    // the distinction is made here rather than asking the person to.
    final looksLikeUrl = value.startsWith('http://') || value.startsWith('https://');
    _beginRun(looksLikeUrl ? Submission.link(value) : Submission.text(value));

    try {
      final verdict = _deep
          ? await _deepCheck(value, looksLikeUrl: looksLikeUrl, recheck: recheck)
          : looksLikeUrl
          ? await widget.client.verifyUrl(value, language: language, recheck: recheck)
          : await widget.client.verifyText(value, language: language, recheck: recheck);
      if (mounted && verdict != null) _finish(verdict);
    } on ApiFailure catch (failure) {
      if (!mounted) return;
      // A link the server refused is a page it could not read or found nothing to
      // check on. "That input could not be read" said neither, and before the
      // server refused them these came back as "Unconfirmed", as though sources
      // had been looked for.
      if (looksLikeUrl && failure.kind == FailureKind.invalidInput) {
        setState(() {
          _error = (l10n) => l10n.failureLinkUnchecked;
          _errorRetryable = false;
        });
      } else {
        _fail(failure);
      }
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _checkedText = value;
        });
      }
    }
  }

  /// Run a deep check: start it, then follow its progress until the verdict.
  /// Null when it outlasts the wait, which is said on screen.
  Future<Verdict?> _deepCheck(
    String value, {
    required bool looksLikeUrl,
    required bool recheck,
  }) async {
    final caseId = await widget.client.startDeepCheck(
      text: looksLikeUrl ? null : value,
      url: looksLikeUrl ? value : null,
      language: _language,
      recheck: recheck,
    );
    if (mounted) setState(() => _deepProgress = (0, 0));
    try {
      // Up to five minutes: past the server's own three-minute budget, so a check
      // that finished is always collected.
      for (var attempt = 0; attempt < 100; attempt++) {
        await Future<void>.delayed(const Duration(seconds: 3));
        if (!mounted) return null;
        final progress = await widget.client.checkOn(caseId);
        if (progress.verdict != null) return progress.verdict;
        setState(() => _deepProgress = (progress.done, progress.total));
      }
      if (mounted) {
        setState(() {
          _error = (l10n) => l10n.deepTooSlow;
          _errorRetryable = false;
        });
      }
      return null;
    } finally {
      if (mounted) setState(() => _deepProgress = null);
    }
  }

  Future<void> _verifyFile(File file, {Submission? submission, bool recheck = false}) async {
    _lastRun = () => _verifyFile(file, submission: submission);
    final language = _language;
    final described = submission ?? await _describe(file);
    _recheckRun = () => _verifyFile(file, submission: described, recheck: true);
    _checkedText = null;
    _beginRun(described);

    try {
      // Consent is implied by choosing the file: the person picked this image
      // for checking, which is the only thing the flag governs.
      final outcome = await widget.client.verifyFile(
        file,
        consentToProcessMedia: true,
        language: language,
        recheck: recheck,
        onProgress: _showUploadProgress,
      );
      if (!mounted) return;
      setState(() => _uploadProgress = null);

      if (outcome.isPending) {
        // Video: accepted, not finished. Poll rather than hold the request open,
        // which would end in a gateway timeout telling the client nothing.
        setState(() => _pendingCaseId = outcome.pendingCaseId);
        await _pollFor(outcome.pendingCaseId!);
      } else {
        _finish(outcome.verdict!);
      }
    } on ApiFailure catch (failure) {
      if (mounted) _fail(failure);
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _uploadProgress = null;
          // The box cannot show a picture; an empty box stands for it.
          if (_input.text.trim().isEmpty) _checkedText = '';
        });
      }
    }
  }

  /// Redrawn in steps of two percent rather than on every chunk: a large file
  /// arrives in hundreds of chunks, and a rebuild for each is work the eye cannot
  /// see.
  void _showUploadProgress(int sent, int total) {
    if (!mounted || total <= 0) return;
    final value = sent / total;
    final shown = _uploadProgress;
    if (shown == null || value - shown >= 0.02 || value >= 1) {
      setState(() => _uploadProgress = value);
    }
  }

  /// Build the preview for a file, reading thumbnail bytes only for images.
  Future<Submission> _describe(File file) async {
    final name = file.path.toLowerCase();
    final looksLikeImage = const ['.jpg', '.jpeg', '.png', '.webp', '.bmp'].any(name.endsWith);

    if (!looksLikeImage) return Submission.document(file);

    try {
      final length = await file.length();
      // Skipped rather than resized: decoding a very large image to build a
      // 64px preview would cost more memory than the verification itself.
      if (length > _thumbnailBytesLimit) return Submission.document(file);
      return Submission.image(file, await file.readAsBytes());
    } on FileSystemException {
      return Submission.document(file);
    }
  }

  Future<void> _pollFor(String caseId) async {
    // Bounded: roughly 30 seconds, matching the server's own video budget. An
    // unbounded poll would spin forever on a case that failed.
    for (var attempt = 0; attempt < 15; attempt++) {
      await Future<void>.delayed(const Duration(seconds: 2));
      if (!mounted) return;
      Verdict? verdict;
      try {
        verdict = await widget.client.getCase(caseId);
      } on ApiFailure catch (failure) {
        // A poll that cannot reach the server stops and says so, rather than
        // escaping as an uncaught exception and leaving a spinner forever.
        if (mounted) {
          setState(() => _pendingCaseId = null);
          _fail(failure);
        }
        return;
      }
      if (verdict != null) {
        setState(() => _pendingCaseId = null);
        _finish(verdict);
        return;
      }
    }
    if (mounted) {
      setState(() {
        _pendingCaseId = null;
        _error = (l10n) => l10n.errorVideoSlow(caseId);
        _errorRetryable = false;
      });
    }
  }

  Future<void> _pick(IntakeSource source) async {
    try {
      switch (source) {
        case IntakeSource.gallery:
          final result = await FilePicker.platform.pickFiles(type: FileType.image);
          final path = result?.files.single.path;
          if (path != null) await _verifyFile(File(path));

        case IntakeSource.camera:
          final shot = await _camera.pickImage(
            source: ImageSource.camera,
            // Capped on the way in. A 12 MP phone photograph is far more detail
            // than perceptual hashing or CLIP uses, and the upload limit is the
            // thing most likely to reject an otherwise fine check.
            maxWidth: 1600,
            imageQuality: 88,
          );
          if (shot != null) await _verifyFile(File(shot.path));

        case IntakeSource.document:
          final result = await FilePicker.platform.pickFiles();
          final path = result?.files.single.path;
          if (path != null) await _verifyFile(File(path));
      }
    } on PlatformException catch (error) {
      // A denied camera permission is an ordinary answer, not a crash.
      if (mounted) {
        final _Phrase message = error.code == 'camera_access_denied'
            ? (l10n) => l10n.errorCameraDenied
            : (l10n) => l10n.errorFileUnopenable;
        setState(() => _error = message);
      }
    }
  }

  /// Flag this verdict for human review — a real request, not a snackbar.
  ///
  /// The previous version showed "Reported for human review" while sending
  /// nothing anywhere: a fabricated confirmation in a product whose one claim
  /// is that it does not fabricate. It now calls the endpoint, and the
  /// confirmation appears only once the server has queued the case.
  Future<void> _reportCase() async {
    final verdict = _verdict;
    if (verdict == null || _reporting) return;

    setState(() => _reporting = true);
    try {
      await widget.client.reportCase(verdict.caseId);
      if (!mounted) return;
      _reported.add(verdict.caseId);
      final l10n = AppLocalizations.of(context);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l10n.reportSent)));
    } on ApiFailure catch (failure) {
      if (!mounted) return;
      final l10n = AppLocalizations.of(context);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(l10n.reportFailed(l10n.describeFailure(failure)))),
      );
    } finally {
      if (mounted) setState(() => _reporting = false);
    }
  }

  /// The correction card: what goes back to the group the content came from.
  ///
  /// Opens a preview of the exact picture that will be sent, with the source links
  /// as text beside it (`correction_sheet.dart`). This used to copy text to the
  /// clipboard and nothing more, leaving a wall of URLs to paste into a chat that
  /// had received a picture.
  void _shareCorrection() {
    final verdict = _verdict;
    if (verdict == null) return;
    unawaited(showCorrectionSheet(context, verdict));
  }

  void _openEvidence(Verdict verdict) => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => EvidenceScreen(
        verdict: verdict,
        language: widget.language,
        submission: _submission,
        client: widget.client,
      ),
    ),
  );

  void _openHistoryEntry(HistoryEntry entry) => setState(() {
    _tab = 0;
    _verdict = entry.verdict;
    _submission = entry.submission;
    _error = null;
  });

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _shareSubscription?.cancel();
    _input.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            Container(
              width: 30,
              height: 30,
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.primary,
                borderRadius: BorderRadius.circular(9),
              ),
              child: const Icon(Icons.fact_check_outlined, color: Colors.white, size: 18),
            ),
            const SizedBox(width: 10),
            // The product name, the same in every interface language. It gives
            // way first on a narrow phone or at a large font size, so the language
            // and status pills beside it keep their room.
            const Flexible(child: Text('Factify', overflow: TextOverflow.ellipsis)),
          ],
        ),
        actions: [
          if (widget.auth != null)
            AccountAvatar(
              auth: widget.auth!,
              onTap: () => Navigator.of(
                context,
              ).push(MaterialPageRoute<void>(builder: (_) => AccountScreen(auth: widget.auth!))),
            ),
          LanguageMenu(preference: widget.language),
          const SizedBox(width: 8),
          _StatusDot(ready: _serviceReady, onTap: _probeService),
          const SizedBox(width: 12),
        ],
      ),
      body: SafeArea(
        child: switch (_tab) {
          0 => _checkTab(context),
          _ => _activityTab(context),
        },
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (index) => setState(() => _tab = index),
        destinations: [
          NavigationDestination(
            icon: const Icon(Icons.fact_check_outlined),
            selectedIcon: const Icon(Icons.fact_check),
            label: l10n.tabCheck,
          ),
          NavigationDestination(
            icon: Badge(
              isLabelVisible: _history.isNotEmpty,
              label: Text('${_history.length}'),
              child: const Icon(Icons.history_outlined),
            ),
            selectedIcon: const Icon(Icons.history),
            label: l10n.tabActivity,
          ),
        ],
      ),
    );
  }

  Widget _checkTab(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final verdict = _verdict;
    final submission = _submission;
    final error = _error;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        Text(
          l10n.heroTitle,
          style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700, height: 1.25),
        ),
        const SizedBox(height: 4),
        Text(
          l10n.heroSubtitle,
          style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
        const SizedBox(height: 16),
        if (_clipboardOffer && !_busy)
          _ClipboardOffer(
            onCheck: _checkClipboard,
            onDismiss: () => setState(() => _clipboardOffer = false),
          ),
        IntakeBar(
          controller: _input,
          busy: _busy,
          onCheck: () => _verify(_input.text),
          onPick: _pick,
          recheckFor: _busy || (verdict == null && error == null) ? null : _checkedText,
          deep: _deep,
          onDeepChanged: (value) => setState(() => _deep = value),
          onRecheck: _recheckRun == null ? null : () => unawaited(_recheckRun!()),
        ),
        const SizedBox(height: 18),

        // A picture or document is shown back, since the box above cannot show
        // it. Text and links are already there, in the box, and were shown twice.
        if (submission != null && submission.isMedia) ...[
          SubmissionCard(submission: submission),
          const SizedBox(height: 12),
        ],

        // What was read in the picture, right under it and above the verdict: the
        // verdict is about this text, so the text comes first.
        if (verdict?.imageReading case final reading?) ...[
          ImageReadingCard(reading: reading),
          const SizedBox(height: 12),
        ],

        if (_busy) _Working(uploadProgress: _uploadProgress, deep: _deepProgress),
        if (_pendingCaseId != null) const _Pending(),
        if (error != null)
          _ErrorNote(
            message: error(l10n),
            onRetry: _errorRetryable && _lastRun != null && !_busy
                ? () {
                    final run = _lastRun!;
                    unawaited(run());
                  }
                : null,
          ),

        if (verdict != null)
          VerdictCard(
            verdict: verdict,
            reporting: _reporting,
            onSeeEvidence: () => _openEvidence(verdict),
            onShareCorrection: _shareCorrection,
            onReportForReview: _reported.contains(verdict.caseId) ? null : _reportCase,
          ),

        if (verdict != null && _reported.contains(verdict.caseId))
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              l10n.reportedNote,
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
              textAlign: TextAlign.center,
            ),
          ),

        if (verdict == null && !_busy && submission == null) const _EmptyState(),
      ],
    );
  }

  Widget _activityTab(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);

    if (_history.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.history,
              size: 44,
              color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.4),
            ),
            const SizedBox(height: 12),
            Text(l10n.activityEmptyTitle, style: theme.textTheme.titleSmall),
            const SizedBox(height: 6),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 40),
              child: Text(
                l10n.activityEmptyBody,
                textAlign: TextAlign.center,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
          ],
        ),
      );
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        HistoryStrip(entries: _history, onOpen: _openHistoryEntry),
        const SizedBox(height: 12),
        Text(
          l10n.activityFooter,
          style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}

/// The service state, honestly: checking, ready, or unavailable.
class _StatusDot extends StatelessWidget {
  const _StatusDot({required this.ready, required this.onTap});

  final bool? ready;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final (colour, label) = switch (ready) {
      true => (FactifyColors.emerald, l10n.statusOnline),
      false => (theme.colorScheme.error, l10n.statusOffline),
      null => (theme.colorScheme.outline, l10n.statusChecking),
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

/// Offers to check what was copied, without reading it until asked.
class _ClipboardOffer extends StatelessWidget {
  const _ClipboardOffer({required this.onCheck, required this.onDismiss});

  final VoidCallback onCheck;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final l10n = AppLocalizations.of(context);

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Material(
        color: scheme.primaryContainer.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(12, 4, 4, 4),
          child: Row(
            children: [
              Icon(Icons.content_paste, size: 18, color: scheme.onPrimaryContainer),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  l10n.clipboardOffer,
                  style: theme.textTheme.bodySmall?.copyWith(color: scheme.onPrimaryContainer),
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
      ),
    );
  }
}

/// What the app is for, said once, before anything has been checked.
class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 28),
      child: Column(
        children: [
          Container(
            width: 72,
            height: 72,
            decoration: const BoxDecoration(
              color: FactifyColors.emeraldTint,
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.verified_rounded, size: 36, color: FactifyColors.emerald),
          ),
          const SizedBox(height: 14),
          Text(l10n.emptyTitle, style: theme.textTheme.titleSmall),
          const SizedBox(height: 6),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Text(
              l10n.emptyBody,
              textAlign: TextAlign.center,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Work in progress: a measured upload, then a check whose length is unknown.
///
/// What it shows is only what is true. An upload has a real percentage, so it gets
/// a real bar. The check itself reports no progress, so there is no bar pretending
/// to know how far along it is: a counter of the seconds actually spent, the steps
/// every check goes through (listed, not ticked off), and how long one usually
/// takes, so a forty-second wait reads as normal rather than stuck.
class _Working extends StatefulWidget {
  const _Working({this.uploadProgress, this.deep});

  final double? uploadProgress;

  /// A deep check's progress, claims done of total, which the server reports; so
  /// unlike a normal check this one has a real bar.
  final (int, int)? deep;

  @override
  State<_Working> createState() => _WorkingState();
}

class _WorkingState extends State<_Working> {
  final Stopwatch _clock = Stopwatch()..start();
  late final Timer _tick = Timer.periodic(const Duration(seconds: 1), (_) {
    if (mounted) setState(() {});
  });

  @override
  void initState() {
    super.initState();
    _tick; // started with the card, stopped with it
  }

  @override
  void dispose() {
    _tick.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final progress = widget.uploadProgress;
    final uploading = progress != null && progress < 1;
    final deep = widget.deep;
    final muted = theme.textTheme.bodySmall?.copyWith(color: FactifyColors.inkMuted);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                SizedBox(
                  width: 44,
                  height: 44,
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      const SizedBox(
                        width: 44,
                        height: 44,
                        child: CircularProgressIndicator(
                          strokeWidth: 3,
                          color: FactifyColors.emerald,
                          backgroundColor: FactifyColors.emeraldTint,
                        ),
                      ),
                      Icon(
                        uploading ? Icons.upload_rounded : Icons.travel_explore_rounded,
                        size: 20,
                        color: FactifyColors.emeraldDark,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        widget.deep != null ? l10n.deepChecking : l10n.checkingTitle,
                        style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        uploading
                            ? l10n.uploading((progress * 100).round())
                            : deep != null && deep.$2 > 0
                            ? l10n.deepProgress(deep.$1, deep.$2)
                            : l10n.working,
                        style: muted,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  l10n.elapsedSeconds(_clock.elapsed.inSeconds),
                  style: theme.textTheme.labelLarge?.copyWith(
                    color: FactifyColors.inkMuted,
                    fontFeatures: const [FontFeature.tabularFigures()],
                  ),
                ),
              ],
            ),
            if (deep != null && deep.$2 > 0) ...[
              const SizedBox(height: 14),
              ClipRRect(
                borderRadius: BorderRadius.circular(999),
                child: LinearProgressIndicator(
                  value: deep.$1 / deep.$2,
                  minHeight: 6,
                  color: FactifyColors.emerald,
                  backgroundColor: FactifyColors.emeraldTint,
                ),
              ),
            ],
            if (uploading) ...[
              const SizedBox(height: 14),
              ClipRRect(
                borderRadius: BorderRadius.circular(999),
                child: LinearProgressIndicator(
                  value: progress,
                  minHeight: 6,
                  color: FactifyColors.emerald,
                  backgroundColor: FactifyColors.emeraldTint,
                ),
              ),
            ],
            const SizedBox(height: 16),
            for (final (index, step) in [
              l10n.stepReading,
              l10n.stepSearching,
              l10n.stepComparing,
            ].indexed)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Row(
                  children: [
                    Container(
                      width: 22,
                      height: 22,
                      alignment: Alignment.center,
                      decoration: const BoxDecoration(
                        color: FactifyColors.emeraldTint,
                        shape: BoxShape.circle,
                      ),
                      child: Text(
                        '${index + 1}',
                        style: const TextStyle(
                          color: FactifyColors.emeraldDeep,
                          fontWeight: FontWeight.w700,
                          fontSize: 12,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(child: Text(step, style: theme.textTheme.bodyMedium)),
                  ],
                ),
              ),
            const SizedBox(height: 4),
            Text(deep != null ? l10n.deepUsuallyTakes : l10n.usuallyTakes, style: muted),
          ],
        ),
      ),
    );
  }
}

class _Pending extends StatelessWidget {
  const _Pending();

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Card(
      child: ListTile(
        leading: const SizedBox(
          width: 24,
          height: 24,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
        title: Text(l10n.videoAcceptedTitle),
        subtitle: Text(l10n.videoAcceptedBody),
      ),
    );
  }
}

class _ErrorNote extends StatelessWidget {
  const _ErrorNote({required this.message, this.onRetry});

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      color: scheme.errorContainer,
      child: Padding(
        // Start and end rather than left and right, so the retry button stays at
        // the trailing edge in a right-to-left layout (PLAN 1.7.6).
        padding: const EdgeInsetsDirectional.fromSTEB(14, 10, 8, 10),
        child: Row(
          children: [
            Icon(Icons.error_outline, color: scheme.onErrorContainer),
            const SizedBox(width: 10),
            Expanded(
              child: Text(message, style: TextStyle(color: scheme.onErrorContainer)),
            ),
            if (onRetry != null)
              TextButton(
                onPressed: onRetry,
                child: Text(
                  AppLocalizations.of(context).retry,
                  style: TextStyle(color: scheme.onErrorContainer),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
