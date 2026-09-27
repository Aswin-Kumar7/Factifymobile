/// The quick verdict over the chat (v5, 2.7).
///
/// Text or a link shared to Factify is checked in a see-through window over the
/// chat it came from (android QuickVerdictActivity), and the answer shown in a sheet
/// at the bottom: the verdict, one line on why, who said so, and a button that
/// copies a polite correction to paste straight back into the conversation. "Open
/// full result" opens the app on the result, which is kept in History like any
/// other check.
///
/// This is its own small Flutter entry point (`quickVerdictMain`), not the whole
/// app: it reads the saved sign-in, runs one check and shows one sheet. With the
/// quick verdict turned off in Profile, or nobody signed in, the text goes on to
/// the full app instead.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/client.dart';
import '../app_services.dart';
import '../auth/auth_service.dart';
import '../checks/check_job.dart';
import '../history/history_store.dart';
import '../l10n/app_localizations.dart';
import '../l10n/language_preference.dart';
import '../l10n/phrases.dart';
import '../models/submission.dart';
import '../models/verdict.dart';
import '../notify/ready_notifier.dart';
import '../screens/error_screen.dart';
import '../theme/icons.dart';
import '../theme/theme.dart';
import '../theme/theme_mode_preference.dart';
import '../theme/tokens.dart';
import '../theme/typography.dart';
import '../widgets/action_style.dart';
import '../widgets/correction_card.dart';
import '../widgets/ui/fx_button.dart';
import 'quick_preference.dart';

/// What the window over the chat can do: hand over the shared text, and close -
/// alone, or opening the full app on the way.
abstract class QuickHost {
  /// The shared text, once; null if there is none.
  Future<SharedText?> share();

  /// The full app, with [text] in the Check box. Closes this window.
  Future<void> openFullApp(String text);

  /// The full app on a result kept in History. Closes this window.
  Future<void> openResult(String recordId);

  Future<void> close();
}

class SharedText {
  const SharedText({required this.value, required this.link});

  final String value;
  final bool link;

  Submission get submission => link ? Submission.link(value) : Submission.text(value);
}

/// QuickVerdictActivity, over the `factify/quick` channel.
class QuickChannel implements QuickHost {
  static const MethodChannel _channel = MethodChannel('factify/quick');

  @override
  Future<SharedText?> share() async {
    try {
      final map = await _channel.invokeMethod<Map<Object?, Object?>>('getShare');
      final value = map?['value'] as String?;
      if (value == null || value.isEmpty) return null;
      return SharedText(value: value, link: map?['kind'] == 'url');
    } on PlatformException {
      return null;
    } on MissingPluginException {
      return null;
    }
  }

  @override
  Future<void> openFullApp(String text) => _call('openFullApp', {'text': text});

  @override
  Future<void> openResult(String recordId) => _call('openResult', {'record': recordId});

  @override
  Future<void> close() => _call('close');

  Future<void> _call(String method, [Map<String, Object?>? arguments]) async {
    try {
      await _channel.invokeMethod<void>(method, arguments);
    } on PlatformException {
      await SystemNavigator.pop();
    } on MissingPluginException {
      await SystemNavigator.pop();
    }
  }
}

/// Starts the quick verdict. Called from `quickVerdictMain` in lib/main.dart.
Future<void> runQuickVerdict() async {
  WidgetsFlutterBinding.ensureInitialized();
  final host = QuickChannel();
  final shared = await host.share();
  if (shared == null) return host.close();
  final quick = await QuickVerdictPreference.load();
  // Turned off in Profile: the earlier way, the full app with the text in Check.
  if (!quick.value) return host.openFullApp(shared.value);

  final language = await LanguagePreference.load();
  final themeMode = await ThemeModePreference.load();
  final client = FactifyClient();
  final auth = AuthService(client: client);
  client.tokenProvider = auth.accessToken;
  final services = AppServices(
    client: client,
    auth: auth,
    language: language,
    history: HistoryStore(store: SharedPreferencesAsync()),
    themeMode: themeMode,
    // Nobody leaves this window to wait for an answer: nothing to announce.
    notifier: SilentNotifier(),
  );
  runApp(QuickVerdictApp(services: services, shared: shared, host: host));
}

class QuickVerdictApp extends StatelessWidget {
  const QuickVerdictApp({
    required this.services,
    required this.shared,
    required this.host,
    this.job,
    this.ready = false,
    super.key,
  });

  final AppServices services;
  final SharedText shared;
  final QuickHost host;

  /// Supplied by tests.
  final CheckJob Function(String language)? job;

  /// Sign-in and History already loaded (tests).
  final bool ready;

  @override
  Widget build(BuildContext context) {
    ThemeData clear(Brightness brightness) =>
        buildFactifyTheme(brightness).copyWith(scaffoldBackgroundColor: Colors.transparent);
    return ListenableBuilder(
      listenable: Listenable.merge([services.language, services.themeMode]),
      builder: (context, _) => MaterialApp(
        title: 'Factify',
        debugShowCheckedModeBanner: false,
        color: Colors.transparent,
        theme: clear(Brightness.light),
        darkTheme: clear(Brightness.dark),
        themeMode: services.themeMode.value,
        locale: services.language.value,
        supportedLocales: AppLocalizations.supportedLocales,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        home: QuickVerdictSheet(
          services: services,
          shared: shared,
          host: host,
          job: job,
          ready: ready,
        ),
      ),
    );
  }
}

enum _Phase { starting, signIn, checking, done, failed }

class QuickVerdictSheet extends StatefulWidget {
  const QuickVerdictSheet({
    required this.services,
    required this.shared,
    required this.host,
    this.job,
    this.ready = false,
    super.key,
  });

  final AppServices services;
  final SharedText shared;
  final QuickHost host;
  final CheckJob Function(String language)? job;
  final bool ready;

  @override
  State<QuickVerdictSheet> createState() => _QuickVerdictSheetState();
}

class _QuickVerdictSheetState extends State<QuickVerdictSheet> {
  _Phase _phase = _Phase.starting;
  CheckJob? _job;
  final Stopwatch _clock = Stopwatch();
  Timer? _tick;
  Verdict? _verdict;
  String? _recordId;
  int _seconds = 0;
  CheckProblem? _problem;
  String? _failure;
  bool _retryable = false;

  /// The note to paste, fetched as soon as the answer is in so "Copy" is instant.
  Future<String>? _note;
  bool _copied = false;
  bool _closing = false;

  AppServices get _services => widget.services;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => unawaited(_start()));
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  String get _language => Localizations.localeOf(context).languageCode;

  Future<void> _start() async {
    if (!widget.ready) {
      await Future.wait([_services.auth.start(), _services.history.load()]);
    }
    if (!mounted) return;
    if (!_services.auth.signedIn) {
      setState(() => _phase = _Phase.signIn);
      return;
    }
    _check();
  }

  void _check() {
    final job =
        widget.job?.call(_language) ??
        CheckJob(services: _services, submission: widget.shared.submission, language: _language);
    setState(() {
      _phase = _Phase.checking;
      _job = job;
      _copied = false;
    });
    _clock
      ..reset()
      ..start();
    _tick?.cancel();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
    job.start();
    unawaited(_await(job));
  }

  Future<void> _await(CheckJob job) async {
    try {
      final verdict = await job.result;
      if (!mounted || job != _job) return;
      _stopClock();
      if (verdict == null) {
        _fail(CheckProblem.slow, (l10n) => l10n.deepTooSlow, retryable: true);
        return;
      }
      final record = _services.history.records
          .where((r) => r.verdict.caseId == verdict.caseId)
          .firstOrNull;
      unawaited(HapticFeedback.mediumImpact());
      setState(() {
        _phase = _Phase.done;
        _verdict = verdict;
        _recordId = record?.id;
        _seconds = _clock.elapsed.inSeconds;
        _note = _fetchNote(verdict);
      });
    } on CheckFailed catch (failed) {
      if (!mounted || job != _job) return;
      _stopClock();
      final failure = failed.failure;
      final problem = CheckProblem.of(failure, link: widget.shared.link);
      _fail(
        problem,
        (l10n) => errorMessage(l10n, problem, failure),
        retryable: failure.retryable && problem != CheckProblem.linkUnread,
      );
    }
  }

  void _stopClock() {
    _tick?.cancel();
    _clock.stop();
  }

  void _fail(
    CheckProblem problem,
    String Function(AppLocalizations) say, {
    required bool retryable,
  }) {
    setState(() {
      _phase = _Phase.failed;
      _problem = problem;
      _failure = say(AppLocalizations.of(context));
      _retryable = retryable;
    });
  }

  /// The server's polite note in the reader's language, or the same note built
  /// here when the server cannot be reached; with its links, one to a line.
  Future<String> _fetchNote(Verdict verdict) async {
    final l10n = AppLocalizations.of(context);
    var note = correctionMessage(verdict, l10n);
    try {
      note = await _services.client.correctionText(verdict.caseId, _language);
    } on Object {
      // The note built here says the same thing.
    }
    return correctionShareText(note.message, note.links);
  }

  Future<void> _copy() async {
    final note = _note;
    if (note == null) return;
    await Clipboard.setData(ClipboardData(text: await note));
    if (mounted) setState(() => _copied = true);
  }

  Future<void> _close() async {
    if (_closing) return;
    _closing = true;
    _job?.leave();
    await widget.host.close();
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final reduce = MediaQuery.of(context).disableAnimations;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) unawaited(_close());
      },
      child: Scaffold(
        backgroundColor: Colors.transparent,
        body: Stack(
          children: [
            // The chat shows through, dimmed; a tap on it closes the sheet.
            Positioned.fill(
              child: GestureDetector(
                onTap: () => unawaited(_close()),
                child: const ColoredBox(color: Color.fromRGBO(5, 8, 6, .4)),
              ),
            ),
            Align(
              alignment: Alignment.bottomCenter,
              child: SafeArea(
                child: TweenAnimationBuilder<double>(
                  tween: Tween(begin: reduce ? 0 : 1, end: 0),
                  duration: const Duration(milliseconds: 280),
                  curve: Curves.easeOutCubic,
                  builder: (context, offset, child) =>
                      FractionalTranslation(translation: Offset(0, offset), child: child),
                  child: Container(
                    margin: const EdgeInsets.all(8),
                    padding: const EdgeInsets.fromLTRB(16, 10, 16, 16),
                    constraints: BoxConstraints(
                      maxHeight: MediaQuery.sizeOf(context).height * 0.85,
                    ),
                    decoration: BoxDecoration(
                      color: k.bg,
                      borderRadius: BorderRadius.circular(30),
                      boxShadow: const [
                        BoxShadow(
                          offset: Offset(0, -10),
                          blurRadius: 40,
                          color: Color.fromRGBO(0, 0, 0, .2),
                        ),
                      ],
                    ),
                    child: SingleChildScrollView(child: _content(context)),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _content(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Center(
          child: Container(
            width: 40,
            height: 4,
            margin: const EdgeInsets.only(bottom: 12),
            decoration: BoxDecoration(color: k.line, borderRadius: BorderRadius.circular(2)),
          ),
        ),
        _Header(
          checkedIn: _phase == _Phase.done ? _seconds : null,
          onClose: () => unawaited(_close()),
        ),
        const SizedBox(height: 12),
        ...switch (_phase) {
          _Phase.starting => [_waiting(context, l10n.notifyWorkingTitle)],
          _Phase.signIn => [
            Text(l10n.quickSignIn, style: FactifyText.sans(14, color: k.ink2)),
            const SizedBox(height: 14),
            FxButton(
              label: l10n.quickOpenApp,
              height: 52,
              onPressed: () => unawaited(widget.host.openFullApp(widget.shared.value)),
            ),
          ],
          _Phase.checking => _checking(context),
          _Phase.done => _answer(context, _verdict!),
          _Phase.failed => _failed(context),
        },
      ],
    );
  }

  Widget _waiting(BuildContext context, String label) {
    final k = FactifyTokens.of(context);
    return Row(
      children: [
        SizedBox.square(
          dimension: 16,
          child: CircularProgressIndicator(strokeWidth: 2, color: k.acc),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            label,
            style: FactifyText.sans(14, weight: FontWeight.w600, color: k.ink),
          ),
        ),
      ],
    );
  }

  List<Widget> _checking(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final job = _job;
    return [
      ValueListenableBuilder<CheckWatch>(
        valueListenable: job?.watch ?? ValueNotifier(const CheckWatch()),
        builder: (context, watch, _) {
          final labels = [l10n.stepReading, l10n.stepSearching, l10n.stepComparing];
          final label = watch.step >= 0 && watch.step < labels.length
              ? labels[watch.step]
              : l10n.notifyWorkingTitle;
          return Row(
            children: [
              Expanded(child: _waiting(context, label)),
              Text(
                l10n.elapsedSeconds(_clock.elapsed.inSeconds),
                style: FactifyText.mono(12, color: k.ink3, spacing: 0),
              ),
            ],
          );
        },
      ),
      const SizedBox(height: 10),
      Text(
        '“${widget.shared.value}”',
        maxLines: 3,
        overflow: TextOverflow.ellipsis,
        style: FactifyText.serif(
          14,
          weight: FontWeight.w400,
          color: k.ink2,
        ).copyWith(fontStyle: FontStyle.italic, height: 1.4),
      ),
      const SizedBox(height: 8),
      Text(l10n.checkTakes, style: FactifyText.sans(12, color: k.ink3)),
    ];
  }

  List<Widget> _answer(BuildContext context, Verdict verdict) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final fact = verdict.nothingToCheck ? FactVerdict.unconfirmed : verdict.factVerdict;
    final (strong, soft) = ActionStyle.colours(fact, k);
    final style = ActionStyle.forVerdict(verdict, Theme.of(context).brightness, l10n);
    final word = ActionStyle.label(verdict, l10n);
    final confidence = verdict.confidence;
    final summary = firstSentence(verdict.summary ?? '');
    final chips = decidingSources(verdict).map(l10n.describeSource).toSet().take(3).toList();
    final copy = switch (fact) {
      FactVerdict.falseClaim => l10n.quickCopyCorrection,
      FactVerdict.misleading => l10n.quickCopyContext,
      FactVerdict.trueClaim => l10n.quickCopyResult,
      FactVerdict.unconfirmed => l10n.quickCopyNote,
    };
    final glyph = switch (fact) {
      FactVerdict.falseClaim => Icons.close_rounded,
      FactVerdict.misleading => Icons.priority_high_rounded,
      FactVerdict.trueClaim => Icons.check_rounded,
      FactVerdict.unconfirmed => Icons.question_mark_rounded,
    };
    final recordId = _recordId;

    return [
      Semantics(
        label: confidence == null ? word : l10n.verdictSemantics(word, confidence),
        excludeSemantics: true,
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: soft, borderRadius: BorderRadius.circular(20)),
          child: Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(color: strong, shape: BoxShape.circle),
                child: Icon(glyph, size: 24, color: k.isDark ? k.bg : Colors.white),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Wrap(
                      crossAxisAlignment: WrapCrossAlignment.end,
                      spacing: 8,
                      children: [
                        Text(
                          word,
                          style: FactifyText.serif(
                            30,
                            weight: FontWeight.w600,
                            color: strong,
                          ).copyWith(height: 1, letterSpacing: -0.8),
                        ),
                        if (confidence != null)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 3),
                            child: Text(
                              l10n.confidence(confidence),
                              style: FactifyText.sans(12, weight: FontWeight.w600, color: k.ink2),
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 3),
                    Text(style.subhead, style: FactifyText.sans(12, color: k.ink2)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
      if (summary.isNotEmpty) ...[
        const SizedBox(height: 10),
        Text(summary, style: FactifyText.sans(13, color: k.ink2).copyWith(height: 1.5)),
      ],
      if (chips.isNotEmpty) ...[
        const SizedBox(height: 10),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            for (final who in chips)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                decoration: BoxDecoration(
                  color: k.sf,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: k.line),
                ),
                child: Text(
                  who,
                  style: FactifyText.sans(11, weight: FontWeight.w600, color: k.ink),
                ),
              ),
          ],
        ),
      ],
      const SizedBox(height: 14),
      FxButton(
        label: _copied ? l10n.quickCopied : copy,
        icon: FxIcons.copy,
        height: 52,
        fontSize: 15,
        onPressed: () => unawaited(_copy()),
      ),
      if (recordId != null) ...[
        const SizedBox(height: 8),
        FxButton(
          label: l10n.quickOpenResult,
          trailingIcon: FxIcons.forward,
          variant: FxButtonVariant.ghost,
          height: 46,
          fontSize: 14,
          onPressed: () => unawaited(widget.host.openResult(recordId)),
        ),
      ],
    ];
  }

  List<Widget> _failed(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    return [
      Text(_failure ?? '', style: FactifyText.sans(14, color: k.ink2).copyWith(height: 1.5)),
      const SizedBox(height: 14),
      if (_retryable && _problem != CheckProblem.signedOut) ...[
        FxButton(label: l10n.tryAgain, icon: FxIcons.retry, height: 52, onPressed: _check),
        const SizedBox(height: 8),
      ],
      FxButton(
        label: l10n.quickOpenApp,
        variant: _retryable ? FxButtonVariant.ghost : FxButtonVariant.primary,
        height: _retryable ? 46 : 52,
        onPressed: () => unawaited(widget.host.openFullApp(widget.shared.value)),
      ),
    ];
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.checkedIn, required this.onClose});

  final int? checkedIn;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final checkedIn = this.checkedIn;
    return Row(
      children: [
        Container(
          width: 22,
          height: 22,
          decoration: BoxDecoration(color: k.acc, borderRadius: BorderRadius.circular(7)),
          child: Icon(Icons.check_rounded, size: 14, color: k.onAcc),
        ),
        const SizedBox(width: 7),
        // The product name, the same in every language.
        Text(
          'Factify',
          style: FactifyText.serif(16, weight: FontWeight.w600, color: k.ink),
        ),
        if (checkedIn != null) ...[
          const SizedBox(width: 7),
          Flexible(
            child: Text(
              '· ${l10n.quickCheckedIn(checkedIn)}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: FactifyText.sans(11.5, color: k.ink3),
            ),
          ),
        ],
        const Spacer(),
        IconButton(
          tooltip: l10n.errClose,
          onPressed: onClose,
          icon: Icon(FxIcons.close, size: 18, color: k.ink3),
        ),
      ],
    );
  }
}
