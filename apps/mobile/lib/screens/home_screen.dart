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
import '../models/submission.dart';
import '../models/verdict.dart';
import '../widgets/history_strip.dart';
import '../widgets/intake_bar.dart';
import '../widgets/submission_card.dart';
import '../widgets/verdict_card.dart';
import 'evidence_screen.dart';

/// Largest image read into memory for the preview thumbnail. See
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

  int _tab = 0;
  Verdict? _verdict;
  Submission? _submission;
  String? _error;
  bool _errorRetryable = false;
  bool _busy = false;
  bool _reporting = false;
  String? _pendingCaseId;
  final List<HistoryEntry> _history = [];
  final Set<String> _reported = {};

  /// Whether the service can verify right now. Three states, honestly:
  /// unknown (null) until the first probe answers, then ready or not.
  bool? _serviceReady;

  /// Re-runs the submission that produced the current error. Retry exists
  /// because [ApiFailure.retryable] was modelled and then ignored — the client
  /// knew "try again shortly" from "your request was wrong" and the interface
  /// collapsed both into a dead end.
  Future<void> Function()? _lastRun;

  @override
  void initState() {
    super.initState();
    _listenForShares();
    _probeService();
  }

  Future<void> _probeService() async {
    final ready = await widget.client.ready();
    if (!mounted) return;
    setState(() {
      _serviceReady = ready;
      // A release build compiled without FACIFY_API still points at the
      // emulator's host address, which no real phone can reach. That build is
      // misconfigured rather than offline, and whoever installed it needs to
      // know which.
      if (!ready && kReleaseMode && apiUsesEmulatorDefault) {
        _error =
            'This build has no server address. Rebuild it with '
            '--dart-define=FACIFY_API=https://your-server.';
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
      onError: (Object error) => setState(() => _error = 'Could not read the shared item.'),
    );
    _intake.initial().then((content) {
      if (content != null) _handleShared(content);
    });
  }

  void _handleShared(SharedContent content) {
    setState(() => _tab = 0);
    if (content.isError) {
      // The share arrived but could not be read — typically a gallery app whose
      // grant did not reach us. Said out loud, and whatever result is already on
      // screen stays there: a failed share must not look like a cleared one.
      setState(() {
        _error = content.value;
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

  void _fail(ApiFailure failure) {
    setState(() {
      _error = failure.message;
      _errorRetryable = failure.retryable;
    });
    // A failure is the moment the status dot is most likely stale.
    unawaited(_probeService());
  }

  Future<void> _verify(String raw) async {
    final value = raw.trim();
    if (value.isEmpty) return;
    _lastRun = () => _verify(raw);

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
      if (mounted) _fail(failure);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _verifyFile(File file, {Submission? submission}) async {
    _lastRun = () => _verifyFile(file, submission: submission);
    _beginRun(submission ?? await _describe(file));

    try {
      // Consent is implied by choosing the file: the person picked this image
      // for checking, which is the only thing the flag governs.
      final outcome = await widget.client.verifyFile(file, consentToProcessMedia: true);
      if (!mounted) return;

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
      if (mounted) setState(() => _busy = false);
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
        _error = 'That video is taking longer than expected. Case $caseId is still processing.';
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
        setState(
          () => _error = error.code == 'camera_access_denied'
              ? 'Facify needs camera access to check a photo you take.'
              : 'That file could not be opened.',
        );
      }
    }
  }

  /// Flag this verdict for human review — a real request, not a snackbar.
  ///
  /// The previous version showed "Reported for human review" while sending
  /// nothing anywhere: a fabricated confirmation in a product whose one claim
  /// is that it does not fabricate. It now calls the endpoint, and the
  /// confirmation is the server's own reply.
  Future<void> _reportCase() async {
    final verdict = _verdict;
    if (verdict == null || _reporting) return;

    setState(() => _reporting = true);
    try {
      final status = await widget.client.reportCase(verdict.caseId);
      if (!mounted) return;
      _reported.add(verdict.caseId);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Reported — $status')));
    } on ApiFailure catch (failure) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Could not report: ${failure.message}')));
    } finally {
      if (mounted) setState(() => _reporting = false);
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

  void _openEvidence(Verdict verdict) => Navigator.of(
    context,
  ).push(MaterialPageRoute<void>(builder: (_) => EvidenceScreen(verdict: verdict)));

  void _openHistoryEntry(HistoryEntry entry) => setState(() {
    _tab = 0;
    _verdict = entry.verdict;
    _submission = entry.submission;
    _error = null;
  });

  @override
  void dispose() {
    _shareSubscription?.cancel();
    _input.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
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
            const Text('Facify'),
          ],
        ),
        actions: [
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
          const NavigationDestination(
            icon: Icon(Icons.fact_check_outlined),
            selectedIcon: Icon(Icons.fact_check),
            label: 'Check',
          ),
          NavigationDestination(
            icon: Badge(
              isLabelVisible: _history.isNotEmpty,
              label: Text('${_history.length}'),
              child: const Icon(Icons.history_outlined),
            ),
            selectedIcon: const Icon(Icons.history),
            label: 'Activity',
          ),
        ],
      ),
    );
  }

  Widget _checkTab(BuildContext context) {
    final theme = Theme.of(context);
    final verdict = _verdict;
    final submission = _submission;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        Text(
          'Verdicts from cited sources,\nnever from a model score',
          style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700, height: 1.25),
        ),
        const SizedBox(height: 4),
        Text(
          'Paste a forward, drop a link, or check a picture.',
          style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
        const SizedBox(height: 16),
        IntakeBar(
          controller: _input,
          busy: _busy,
          onCheck: () => _verify(_input.text),
          onPick: _pick,
        ),
        const SizedBox(height: 18),

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
        if (_error != null)
          _ErrorNote(
            message: _error!,
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
              'Reported. A reviewer will see this case.',
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
            Text('No checks this session', style: theme.textTheme.titleSmall),
            const SizedBox(height: 6),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 40),
              child: Text(
                'Results stay on this device for the session and are gone when '
                'the app closes — what you check is nobody\'s record.',
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
          'Session only, by design: what you check is a record of what you were '
          'suspicious about, and this app does not keep one.',
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
    final (colour, label) = switch (ready) {
      true => (const Color(0xFF2E7D32), 'Online'),
      false => (theme.colorScheme.error, 'Offline'),
      null => (theme.colorScheme.outline, 'Checking'),
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

/// What the app is for, said once, before anything has been checked.
class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 28),
      child: Column(
        children: [
          Icon(
            Icons.verified_outlined,
            size: 44,
            color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.45),
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
    padding: const EdgeInsets.symmetric(vertical: 20),
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
  const _ErrorNote({required this.message, this.onRetry});

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      color: scheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 10, 8, 10),
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
                child: Text('Retry', style: TextStyle(color: scheme.onErrorContainer)),
              ),
          ],
        ),
      ),
    );
  }
}
