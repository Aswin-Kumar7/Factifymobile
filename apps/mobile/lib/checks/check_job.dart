/// One check, run apart from the screen that shows it (v5, "Notify me when ready").
///
/// The Checking screen used to own its check: leaving the screen dropped the answer,
/// even though the server had already been asked and would answer anyway. A job
/// outlives the screen, so a person who asked to be told when it is ready can go
/// back to the chat they came from; the answer is kept in History and announced in
/// a notification. Without that request, leaving still means leaving: the answer is
/// dropped, as before.
///
/// The progress the screen draws comes from the server's events (contract 1.3,
/// lib/api/check_events.dart) and from nothing else.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api/check_events.dart';
import '../api/client.dart';
import '../app_services.dart';
import '../history/history_store.dart';
import '../models/submission.dart';
import '../models/verdict.dart';

enum SourceState { reading, evidence, notRelevant }

/// Which way a source points: the words the server uses.
enum Stance {
  supports,
  contradicts,
  context;

  static Stance? parse(String? raw) => switch (raw) {
    'supports' => Stance.supports,
    'contradicts' => Stance.contradicts,
    'context' => Stance.context,
    _ => null,
  };

  /// As the result names it ("Supports", "Refutes", "Context").
  String get wire => switch (this) {
    Stance.supports => 'supports',
    Stance.contradicts => 'contradicts',
    Stance.context => 'context',
  };
}

/// A source the check has opened, as the screen shows it: what the server reported
/// about it and nothing more.
@immutable
class WatchedSource {
  const WatchedSource({
    required this.publisher,
    required this.domain,
    required this.initials,
    required this.state,
    this.title,
    this.stance,
    this.quote,
    this.kept = false,
  });

  final String publisher;
  final String domain;
  final String initials;
  final SourceState state;

  /// The page's headline, when known.
  final String? title;

  /// Which way it points, once read and found to speak to the claim.
  final Stance? stance;

  /// The sentence it was read for.
  final String? quote;

  /// It held up when checked against the claim: it is in the answer.
  final bool kept;

  WatchedSource copyWith({SourceState? state, Stance? stance, String? quote, bool? kept}) =>
      WatchedSource(
        publisher: publisher,
        domain: domain,
        initials: initials,
        state: state ?? this.state,
        title: title,
        stance: stance ?? this.stance,
        quote: quote ?? this.quote,
        kept: kept ?? this.kept,
      );
}

/// Where a check has got to. Everything in it was reported; nothing is estimated.
@immutable
class CheckWatch {
  const CheckWatch({
    this.step = -1,
    this.sources = const [],
    this.evidence = 0,
    this.heard = false,
    this.upload,
    this.claimsDone = 0,
    this.claimsTotal = 0,
    this.factChecks = const [],
    this.checked = false,
  });

  /// Published fact-checks compared with the claim. Many are compared at once and
  /// few are about it, so they are counted, not put on the ring - unless one is.
  final List<WatchedSource> factChecks;

  /// The source check has run: what is left is what the answer cites.
  final bool checked;

  /// 0 read, 1 search, 2 compare; -1 before the server has said.
  final int step;

  /// In the order they were opened.
  final List<WatchedSource> sources;

  /// Sources that speak to the claim, as the server counts them. Ends on the
  /// number the answer cites: a page the source check throws out is taken back.
  final int evidence;

  /// Whether the server has reported anything. An older server, or one whose
  /// stream could not be read, never does; the screen then claims no progress.
  final bool heard;

  /// How much of an upload has been sent, 0 to 1, while it is being sent.
  final double? upload;

  /// Claims checked so far, of all the claims found (0 until they are found).
  final int claimsDone;
  final int claimsTotal;

  int get read => sources.where((s) => s.state != SourceState.reading).length;

  /// The four most recently opened, newest first (the Sources card).
  List<WatchedSource> get recent => sources.reversed.take(4).toList();

  List<WatchedSource> get found => sources.where((s) => s.state == SourceState.evidence).toList();

  /// How many of the found sources point each way.
  Map<Stance, int> get stances {
    final counts = <Stance, int>{};
    for (final s in found) {
      final stance = s.stance;
      if (stance != null) counts[stance] = (counts[stance] ?? 0) + 1;
    }
    return counts;
  }

  CheckWatch copyWith({
    int? step,
    List<WatchedSource>? sources,
    int? evidence,
    bool? heard,
    double? upload,
    bool clearUpload = false,
    int? claimsDone,
    int? claimsTotal,
    List<WatchedSource>? factChecks,
    bool? checked,
  }) => CheckWatch(
    step: step ?? this.step,
    sources: sources ?? this.sources,
    evidence: evidence ?? this.evidence,
    heard: heard ?? this.heard,
    upload: clearUpload ? null : upload ?? this.upload,
    claimsDone: claimsDone ?? this.claimsDone,
    claimsTotal: claimsTotal ?? this.claimsTotal,
    factChecks: factChecks ?? this.factChecks,
    checked: checked ?? this.checked,
  );

  static const _steps = ['read', 'search', 'compare'];

  /// This watch, moved on by one event.
  CheckWatch apply(CheckEvent event) {
    switch (event.type) {
      case 'step':
        final index = _steps.indexOf(event.step ?? '');
        return copyWith(heard: true, step: index > step ? index : step);
      case 'source_started':
        final domain = event.domain ?? '';
        if (domain.isEmpty) return copyWith(heard: true);
        final started = WatchedSource(
          publisher: event.publisher ?? domain,
          domain: domain,
          initials: event.initials ?? '',
          state: SourceState.reading,
          title: event.title,
        );
        if (event.via == 'fact_check') {
          final known = factChecks.indexWhere((s) => s.domain == domain);
          return copyWith(
            heard: true,
            step: step < 1 ? 1 : step,
            factChecks: known < 0
                ? [...factChecks, started]
                : [for (final s in factChecks) s.domain == domain ? started : s],
          );
        }
        final known = sources.indexWhere((s) => s.domain == domain);
        return copyWith(
          heard: true,
          step: step < 1 ? 1 : step,
          sources: known < 0
              ? [...sources, started]
              : [for (final s in sources) s.domain == domain ? started : s],
        );
      case 'source_done':
        final state = event.outcome == 'evidence' ? SourceState.evidence : SourceState.notRelevant;
        WatchedSource done(WatchedSource s) => s.copyWith(
          state: state,
          stance: Stance.parse(event.stance),
          quote: event.quote,
          // Set aside by the source check: no longer in the answer.
          kept: state == SourceState.evidence && s.kept,
        );
        // A fact-check that speaks to the claim is a source like any other: it
        // joins the ring. One that does not stays a count.
        final compared = factChecks.where((s) => s.domain == event.domain).firstOrNull;
        if (compared != null && state == SourceState.evidence) {
          return copyWith(
            heard: true,
            factChecks: [
              for (final s in factChecks)
                if (s.domain != event.domain) s,
            ],
            sources: [...sources, done(compared)],
          );
        }
        return copyWith(
          heard: true,
          factChecks: [for (final s in factChecks) s.domain == event.domain ? done(s) : s],
          sources: [for (final s in sources) s.domain == event.domain ? done(s) : s],
        );
      case 'source_checked':
        // Held up against the claim, with the stance it holds after the check.
        final compared = factChecks.where((s) => s.domain == event.domain).firstOrNull;
        WatchedSource kept(WatchedSource s) => s.copyWith(
          state: SourceState.evidence,
          stance: Stance.parse(event.stance),
          quote: event.quote,
          kept: true,
        );
        return copyWith(
          heard: true,
          factChecks: compared == null
              ? factChecks
              : [
                  for (final s in factChecks)
                    if (s.domain != event.domain) s,
                ],
          sources: [
            for (final s in sources) s.domain == event.domain ? kept(s) : s,
            if (compared != null) kept(compared),
          ],
        );
      case 'evidence_count':
        return copyWith(
          heard: true,
          evidence: event.count ?? evidence,
          checked: checked || event.checked,
        );
      default:
        return copyWith(heard: true);
    }
  }
}

/// Why a job ended without an answer to show.
class CheckFailed implements Exception {
  const CheckFailed(this.failure);

  final ApiFailure failure;
}

class CheckJob {
  CheckJob({
    required this.services,
    required this.submission,
    required this.language,
    this.recheck = false,
    this.acceptPartial = false,
    bool notifyWhenReady = false,
    Stream<CheckEvent> Function(String key)? follow,
  }) : _notify = notifyWhenReady,
       _follow = follow ?? services.client.follow;

  final AppServices services;
  final Submission submission;
  final String language;
  final bool recheck;

  /// "Check what was read" (contract 1.8): an answer held back because part of the
  /// input could not be read, asked for again on what could be.
  final bool acceptPartial;
  final Stream<CheckEvent> Function(String key) _follow;

  final ValueNotifier<CheckWatch> watch = ValueNotifier(const CheckWatch());
  final Completer<Verdict?> _result = Completer();
  StreamSubscription<CheckEvent>? _events;
  bool _cancelled = false;
  bool _notify;
  bool _left = false;

  /// The answer: a verdict, null when the check outlasted the wait, or a
  /// [CheckFailed] error.
  Future<Verdict?> get result => _result.future;

  bool get notifyWhenReady => _notify;

  /// The check as History kept it, once answered: its own copy of a checked file
  /// outlives the one that was shared, which may sit in a cache the phone clears.
  HistoryRecord? get record => _record;
  HistoryRecord? _record;

  /// Turned on from the Checking screen. On means the check keeps running if the
  /// person leaves, and a notification announces the answer.
  set notifyWhenReady(bool value) {
    _notify = value;
    if (_result.isCompleted) return;
    if (value) {
      unawaited(services.notifier.keepAlive(language: language));
    } else {
      unawaited(services.notifier.release());
    }
  }

  /// The person left the Checking screen. With notify on, the check carries on and
  /// is announced; otherwise it is dropped.
  void leave() {
    _left = true;
    if (!_notify) cancel();
  }

  void cancel() {
    _cancelled = true;
    _pause?.cancel();
    final waiting = _waiting;
    if (waiting != null && !waiting.isCompleted) waiting.complete();
    unawaited(_events?.cancel());
    unawaited(services.notifier.release());
  }

  void start() {
    if (_notify) unawaited(services.notifier.keepAlive(language: language));
    unawaited(_run());
  }

  Future<void> _run() async {
    try {
      final verdict = await _verdict();
      if (_cancelled) return;
      if (verdict != null) await _finished(verdict);
      if (!_result.isCompleted) _result.complete(verdict);
    } on ApiFailure catch (failure) {
      if (!_result.isCompleted) _result.completeError(CheckFailed(failure));
    } on Object {
      // Anything unforeseen ends the check with an answer the person can act on -
      // "try again" - rather than a screen left waiting on a result that never comes.
      if (!_result.isCompleted) {
        _result.completeError(const CheckFailed(ApiFailure(FailureKind.generic, retryable: true)));
      }
    } finally {
      unawaited(_events?.cancel());
      if (!_notify || _cancelled) unawaited(services.notifier.release());
    }
  }

  Future<void> _finished(Verdict verdict) async {
    final record = _record = await services.history.add(submission, verdict);
    // The check cost a credit; show the balance the server now holds.
    unawaited(services.auth.refreshAccount());
    if (_notify) {
      await services.notifier.release();
      // Announced when nobody is looking at the Checking screen: it was left, or
      // the app is in the background. A person watching it is shown the answer.
      if (_left || !services.notifier.appInForeground) {
        await services.notifier.ready(record, language: language);
      }
    }
  }

  void _listen(String key) {
    _events = _follow(
      key,
    ).listen((event) => watch.value = watch.value.apply(event), onError: (_) {});
  }

  Future<Verdict?> _verdict() async {
    final client = services.client;
    switch (submission.kind) {
      case SubmissionKind.text:
      case SubmissionKind.link:
        final value = submission.text ?? '';
        final link = submission.kind == SubmissionKind.link;
        // Every claim is checked, in the background, with the time that takes: the
        // server answers at once with a case id, and the check is followed by it.
        final caseId = await client.startCheck(
          text: link ? null : value,
          url: link ? value : null,
          language: language,
          recheck: recheck,
          acceptPartial: acceptPartial,
        );
        _listen(caseId);
        return _followCase(caseId);
      case SubmissionKind.image:
      case SubmissionKind.document:
        final key = newRequestId();
        _listen(key);
        final outcome = await client.verifyFile(
          submission.file!,
          // Choosing the file is the consent: it was picked for checking, which is
          // the only thing the flag governs.
          consentToProcessMedia: true,
          language: language,
          recheck: recheck,
          background: true,
          acceptPartial: acceptPartial,
          requestId: key,
          onProgress: _showUpload,
        );
        watch.value = watch.value.copyWith(clearUpload: true);
        if (outcome.isPending) {
          // Checked in the background, like text: followed by the case id from here.
          unawaited(_events?.cancel());
          _listen(outcome.pendingCaseId!);
          return _followCase(outcome.pendingCaseId!);
        }
        // An older server answers a picture in the one request.
        return outcome.verdict;
    }
  }

  /// A check running in the background, followed until its verdict. Null past the
  /// wait: [polls] of three seconds, eight and a half minutes, past the server's own
  /// ceiling of seven, so a check that finished is always collected.
  ///
  /// A poll that fails on the way - the phone's connection dropping for a moment -
  /// does not end a check the server is still running: a few in a row are
  /// waited out. A refusal from the server (nothing on that page to check) still
  /// ends it at once.
  Future<Verdict?> _followCase(String caseId) async {
    var misses = 0;
    for (var attempt = 0; attempt < polls; attempt++) {
      await _wait(const Duration(seconds: 3));
      if (_cancelled) return null;
      final CheckProgress progress;
      try {
        progress = await services.client.checkOn(caseId);
      } on ApiFailure catch (failure) {
        if (!_passing(failure) || ++misses > _missesAllowed) rethrow;
        continue;
      }
      misses = 0;
      if (progress.verdict != null) return progress.verdict;
      watch.value = watch.value.copyWith(claimsDone: progress.done, claimsTotal: progress.total);
    }
    return null;
  }

  /// Polls before a background check is given up on: 170 of three seconds, 510 s.
  /// The server gives a check at least 150 s of reading once its claims are found,
  /// and never more than 420 s in all (contract 1.8, `BACKGROUND_CEILING_SECONDS`);
  /// this was 130 (390 s) for its earlier 300, and would drop a slow post the server
  /// was still checking.
  static const polls = 170;

  Timer? _pause;
  Completer<void>? _waiting;

  /// A pause between polls that [cancel] ends at once, so a check someone left
  /// leaves no timer behind.
  Future<void> _wait(Duration duration) {
    final waiting = _waiting = Completer<void>();
    _pause = Timer(duration, () {
      if (!waiting.isCompleted) waiting.complete();
    });
    return waiting.future;
  }

  /// Polls in a row that may fail before the check is given up on (about 30 s).
  static const _missesAllowed = 10;

  /// A failure of the connection rather than an answer from the server.
  static bool _passing(ApiFailure failure) => switch (failure.kind) {
    FailureKind.timeout || FailureKind.unreachable || FailureKind.interrupted => true,
    _ => false,
  };

  /// Redrawn in steps of two percent, not on every chunk.
  void _showUpload(int sent, int total) {
    if (total <= 0) return;
    final value = sent / total;
    final shown = watch.value.upload;
    if (shown == null || value - shown >= 0.02 || value >= 1) {
      watch.value = watch.value.copyWith(upload: value);
    }
  }
}
