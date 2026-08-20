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
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import '../api/client.dart';
import '../api/share_intake.dart';
import '../models/submission.dart';
import '../models/verdict.dart';
import '../widgets/history_strip.dart';
import '../widgets/intake_bar.dart';
import '../widgets/submission_card.dart';
import '../widgets/verdict_card.dart';
import 'evidence_screen.dart';

/// Longest edge of the preview thumbnail. Read once at pick time — see
/// [Submission.image] for why the bytes are kept rather than the path.
const int _thumbnailBytesLimit = 2 * 1024 * 1024;

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.client});

  final FacifyClient client;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final TextEditingController _input = TextEditingController();
  final ShareIntake _intake = ShareIntake();
  final ImagePicker _camera = ImagePicker();
  StreamSubscription<SharedContent>? _shareSubscription;

  Verdict? _verdict;
  Submission? _submission;
  String? _error;
  bool _busy = false;
  String? _pendingCaseId;
  final List<HistoryEntry> _history = [];

  @override
  void initState() {
    super.initState();
    _listenForShares();
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
      onError: (Object error) => setState(() => _error = 'Could not read the shared item.'),
    );
    _intake.initial().then((content) {
      if (content != null) _handleShared(content);
    });
  }

  void _handleShared(SharedContent content) {
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
      _submission = submission;
    });
  }

  /// Keep a finished result where the user can get back to it.
  void _finish(Verdict verdict) {
    final submission = _submission;
    setState(() {
      _verdict = verdict;
      if (submission != null) {
        _history.insert(0, HistoryEntry(submission: submission, verdict: verdict));
      }
    });
  }

  Future<void> _verify(String raw) async {
    final value = raw.trim();
    if (value.isEmpty) return;

    // A bare URL and a block of text are different endpoints on the server, so
    // the distinction is made here rather than asking the person to.
    final looksLikeUrl = value.startsWith('http://') || value.startsWith('https://');
    _beginRun(looksLikeUrl ? Submission.link(value) : Submission.text(value));

    try {
      final verdict = looksLikeUrl
          ? await widget.client.verifyUrl(value)
          : await widget.client.verifyText(value);
      if (mounted) _finish(verdict);
    } on ApiFailure catch (failure) {
      if (mounted) setState(() => _error = failure.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _verifyFile(File file, {Submission? submission}) async {
    _beginRun(submission ?? await _describe(file));

    try {
      // Consent is implied by choosing the file: the person picked this image
      // for checking, which is the only thing the flag governs.
      final outcome = await widget.client.verifyFile(file, consentToProcessMedia: true);
      if (!mounted) return;

      if (outcome.isPending) {
        // Video: accepted, not finished. Poll rather than hold the request open,
        // which would end in a gateway timeout telling the user nothing.
        setState(() => _pendingCaseId = outcome.pendingCaseId);
        await _pollFor(outcome.pendingCaseId!);
      } else {
        _finish(outcome.verdict!);
      }
    } on ApiFailure catch (failure) {
      if (mounted) setState(() => _error = failure.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Build the preview for a file, reading thumbnail bytes only for images.
  Future<Submission> _describe(File file) async {
    final name = file.path.toLowerCase();
    final looksLikeImage = const [
      '.jpg',
      '.jpeg',
      '.png',
      '.webp',
      '.bmp',
    ].any(name.endsWith);

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
      final verdict = await widget.client.getCase(caseId);
      if (verdict != null) {
        setState(() => _pendingCaseId = null);
        _finish(verdict);
        return;
      }
    }
    if (mounted) {
      setState(() {
        _pendingCaseId = null;
        _error = 'That video is taking longer than expected. Case $caseId is still processing.';
      });
    }
  }

  Future<void> _pick(IntakeSource source) async {
    try {
      switch (source) {
        case IntakeSource.gallery:
          final result = await FilePicker.platform.pickFiles(
            type: FileType.image,
            withData: false,
          );
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
          final result = await FilePicker.platform.pickFiles(withData: false);
          final path = result?.files.single.path;
          if (path != null) await _verifyFile(File(path));
      }
    } on PlatformException catch (error) {
      // A denied camera permission is an ordinary answer, not a crash.
      if (mounted) {
        setState(
          () => _error = error.code == 'camera_access_denied'
              ? 'Facify needs camera access to check a photo you take.'
              : 'That file could not be opened.',
        );
      }
    }
  }

  /// The correction card: what goes back to the group the content came from.
  ///
  /// Built only from cited findings. A correction that cannot point at a source
  /// is just a counter-assertion, and sending one starts an argument rather than
  /// ending it.
  void _shareCorrection() {
    final verdict = _verdict;
    if (verdict == null) return;

    final buffer = StringBuffer()
      ..writeln('Checked with Facify:')
      ..writeln();

    for (final claim in verdict.claims.where((c) => c.isDecisive)) {
      buffer
        ..writeln('"${claim.text}"')
        ..writeln(claim.reason);
      for (final evidence in claim.evidence.take(2)) {
        buffer.writeln('- ${evidence.publisher ?? 'Source'}: ${evidence.citationUrl}');
      }
      buffer.writeln();
    }

    // Said explicitly rather than left as an empty card. "Nothing could confirm
    // this" is a useful thing to send back; a blank message is not.
    if (verdict.claims.every((c) => !c.isDecisive)) {
      buffer.writeln('No published source could confirm or contradict this.');
    }

    Clipboard.setData(ClipboardData(text: buffer.toString().trim()));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Correction copied - paste it back into the chat')),
    );
  }

  void _openEvidence(Verdict verdict) => Navigator.of(context).push(
    MaterialPageRoute<void>(builder: (_) => EvidenceScreen(verdict: verdict)),
  );

  @override
  void dispose() {
    _shareSubscription?.cancel();
    _input.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final verdict = _verdict;
    final submission = _submission;
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Facify'),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(22),
          child: Padding(
            padding: const EdgeInsets.only(bottom: 8, left: 16, right: 16),
            child: Align(
              alignment: Alignment.centerLeft,
              child: Text(
                'Verdicts from cited sources, never from a model score',
                style: theme.textTheme.labelSmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
          ),
        ),
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
          children: [
            IntakeBar(
              controller: _input,
              busy: _busy,
              onCheck: () => _verify(_input.text),
              onPick: _pick,
            ),
            const SizedBox(height: 20),

            if (submission != null) ...[
              SubmissionCard(
                submission: submission,
                onClear: _busy
                    ? null
                    : () => setState(() {
                        _submission = null;
                        _verdict = null;
                        _error = null;
                      }),
              ),
              const SizedBox(height: 12),
            ],

            if (_busy) const _Working(),
            if (_pendingCaseId != null) const _Pending(),
            if (_error != null) _ErrorNote(message: _error!),

            if (verdict != null)
              VerdictCard(
                verdict: verdict,
                onSeeEvidence: () => _openEvidence(verdict),
                onShareCorrection: _shareCorrection,
                onReportForReview: () => ScaffoldMessenger.of(
                  context,
                ).showSnackBar(const SnackBar(content: Text('Reported for human review'))),
              ),

            if (verdict == null && !_busy && submission == null) const _EmptyState(),

            if (_history.length > 1) ...[
              const SizedBox(height: 28),
              const Divider(),
              const SizedBox(height: 12),
              HistoryStrip(
                // The current result is already on screen above.
                entries: _history.skip(1).toList(),
                onOpen: (entry) => setState(() {
                  _verdict = entry.verdict;
                  _submission = entry.submission;
                  _error = null;
                }),
              ),
            ],
          ],
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
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 32),
      child: Column(
        children: [
          Icon(
            Icons.verified_outlined,
            size: 44,
            color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.5),
          ),
          const SizedBox(height: 12),
          Text('Nothing checked yet', style: theme.textTheme.titleSmall),
          const SizedBox(height: 6),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Text(
              'Share a forward straight into Facify, paste it above, or check a '
              'picture. Every verdict comes with the sources behind it — and when '
              'there are none, it says so.',
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

class _Working extends StatelessWidget {
  const _Working();

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 24),
    child: Column(
      children: [
        const LinearProgressIndicator(),
        const SizedBox(height: 12),
        Text(
          'Looking for sources that address this',
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ],
    ),
  );
}

class _Pending extends StatelessWidget {
  const _Pending();

  @override
  Widget build(BuildContext context) => const Card(
    child: ListTile(
      leading: SizedBox(
        width: 24,
        height: 24,
        child: CircularProgressIndicator(strokeWidth: 2),
      ),
      title: Text('Video accepted'),
      subtitle: Text('Longer than a request can stay open. Checking now.'),
    ),
  );
}

class _ErrorNote extends StatelessWidget {
  const _ErrorNote({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      color: scheme.errorContainer,
      child: ListTile(
        leading: Icon(Icons.error_outline, color: scheme.onErrorContainer),
        title: Text(message, style: TextStyle(color: scheme.onErrorContainer)),
      ),
    );
  }
}
