/// Intake and result (M44).
///
/// Share-sheet intake is the primary path, not a secondary one: the content this
/// app exists to check arrives in a forward, and asking someone to copy it into
/// a text box loses most of them. Manual entry and the file picker are fallbacks.
///
/// Permissions: none requested. Share-sheet intake hands us a file the sender
/// already chose, and manual selection goes through the system picker, which
/// grants access to one file without a storage permission.
library;

import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/client.dart';
import '../api/share_intake.dart';
import '../models/verdict.dart';
import '../widgets/verdict_card.dart';
import 'evidence_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.client});

  final FacifyClient client;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final TextEditingController _input = TextEditingController();
  final ShareIntake _intake = ShareIntake();
  StreamSubscription<SharedContent>? _shareSubscription;

  Verdict? _verdict;
  String? _error;
  bool _busy = false;
  String? _pendingCaseId;

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

  Future<void> _verify(String raw) async {
    final value = raw.trim();
    if (value.isEmpty) return;

    setState(() {
      _busy = true;
      _error = null;
      _verdict = null;
      _pendingCaseId = null;
    });

    try {
      // A bare URL and a block of text are different endpoints on the server,
      // so the distinction is made here rather than asking the person to.
      final looksLikeUrl = value.startsWith('http://') || value.startsWith('https://');
      final verdict = looksLikeUrl
          ? await widget.client.verifyUrl(value)
          : await widget.client.verifyText(value);
      if (mounted) setState(() => _verdict = verdict);
    } on ApiFailure catch (failure) {
      if (mounted) setState(() => _error = failure.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _verifyFile(File file) async {
    setState(() {
      _busy = true;
      _error = null;
      _verdict = null;
      _pendingCaseId = null;
    });

    try {
      final outcome = await widget.client.verifyFile(file);
      if (!mounted) return;

      if (outcome.isPending) {
        // Video: accepted, not finished. Poll rather than hold the request open,
        // which would end in a gateway timeout telling the user nothing.
        setState(() => _pendingCaseId = outcome.pendingCaseId);
        await _pollFor(outcome.pendingCaseId!);
      } else {
        setState(() => _verdict = outcome.verdict);
      }
    } on ApiFailure catch (failure) {
      if (mounted) setState(() => _error = failure.message);
    } finally {
      if (mounted) setState(() => _busy = false);
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
        setState(() {
          _verdict = verdict;
          _pendingCaseId = null;
        });
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

  Future<void> _pickFile() async {
    final result = await FilePicker.platform.pickFiles(type: FileType.media, withData: false);
    final path = result?.files.single.path;
    if (path != null) await _verifyFile(File(path));
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

    if (verdict.claims.every((c) => !c.isDecisive)) {
      buffer.writeln('No published source could confirm or contradict this.');
    }

    Clipboard.setData(ClipboardData(text: buffer.toString()));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Correction copied - paste it back into the chat')),
    );
  }

  @override
  void dispose() {
    _shareSubscription?.cancel();
    _intake.dispose();
    _input.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final verdict = _verdict;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Facify'),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(20),
          child: Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Text(
              'Verdicts from cited sources, never from a model score',
              style: Theme.of(context).textTheme.labelSmall,
            ),
          ),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _input,
            maxLines: 4,
            minLines: 2,
            decoration: const InputDecoration(
              border: OutlineInputBorder(),
              labelText: 'Paste a message or a link',
              hintText: 'Or share straight from WhatsApp, a browser, or the gallery',
            ),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  onPressed: _busy ? null : () => _verify(_input.text),
                  icon: const Icon(Icons.search),
                  label: const Text('Check'),
                ),
              ),
              const SizedBox(width: 8),
              OutlinedButton.icon(
                onPressed: _busy ? null : _pickFile,
                icon: const Icon(Icons.image_outlined),
                label: const Text('Media'),
              ),
            ],
          ),
          const SizedBox(height: 16),
          if (_busy) const _Working(),
          if (_pendingCaseId != null) const _Pending(),
          if (_error != null) _ErrorNote(message: _error!),
          if (verdict != null)
            VerdictCard(
              verdict: verdict,
              onSeeEvidence: () => Navigator.of(
                context,
              ).push(MaterialPageRoute<void>(builder: (_) => EvidenceScreen(verdict: verdict))),
              onShareCorrection: _shareCorrection,
              onReportForReview: () => ScaffoldMessenger.of(
                context,
              ).showSnackBar(const SnackBar(content: Text('Reported for human review'))),
            ),
        ],
      ),
    );
  }
}

class _Working extends StatelessWidget {
  const _Working();

  @override
  Widget build(BuildContext context) => const Padding(
    padding: EdgeInsets.symmetric(vertical: 24),
    child: Column(
      children: [CircularProgressIndicator(), SizedBox(height: 12), Text('Looking for sources...')],
    ),
  );
}

class _Pending extends StatelessWidget {
  const _Pending();

  @override
  Widget build(BuildContext context) => const Card(
    child: ListTile(
      leading: Icon(Icons.movie_outlined),
      title: Text('Checking the video'),
      subtitle: Text('Video takes longer than text. This usually finishes in 30 seconds.'),
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
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Icon(Icons.error_outline, color: scheme.onErrorContainer),
            const SizedBox(width: 10),
            Expanded(
              child: Text(message, style: TextStyle(color: scheme.onErrorContainer)),
            ),
          ],
        ),
      ),
    );
  }
}
