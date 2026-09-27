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

/// A source the check has opened, as the screen shows it.
@immutable
class WatchedSource {
  const WatchedSource({
    required this.publisher,
    required this.domain,
    required this.initials,
    required this.state,
  });

  final String publisher;
  final String domain;
  final String initials;
  final SourceState state;

  WatchedSource withState(SourceState next) =>
      WatchedSource(publisher: publisher, domain: domain, initials: initials, state: next);
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
  });

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

  /// A deep check's claims done of its total.
  final int claimsDone;
  final int claimsTotal;

  int get read => sources.where((s) => s.state != SourceState.reading).length;

  /// The four most recently opened, newest first (the Sources card).
  List<WatchedSource> get recent => sources.reversed.take(4).toList();

  List<WatchedSource> get found => sources.where((s) => s.state == SourceState.evidence).toList();

  CheckWatch copyWith({
    int? step,
    List<WatchedSource>? sources,
    int? evidence,
    bool? heard,
    double? upload,
    bool clearUpload = false,
    int? claimsDone,
    int? claimsTotal,
  }) => CheckWatch(
    step: step ?? this.step,
    sources: sources ?? this.sources,
    evidence: evidence ?? this.evidence,
    heard: heard ?? this.heard,
    upload: clearUpload ? null : upload ?? this.upload,
    claimsDone: claimsDone ?? this.claimsDone,
    claimsTotal: claimsTotal ?? this.claimsTotal,
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
        );
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
        return copyWith(
          heard: true,
          sources: [for (final s in sources) s.domain == event.domain ? s.withState(state) : s],
        );
      case 'evidence_count':
        return copyWith(heard: true, evidence: event.count ?? evidence);
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
    this.deep = false,
    this.recheck = false,
    bool notifyWhenReady = false,
    Stream<CheckEvent> Function(String key)? follow,
  }) : _notify = notifyWhenReady,
       _follow = follow ?? services.client.follow;

  final AppServices services;
  final Submission submission;
  final String language;
  final bool deep;
  final bool recheck;
  final Stream<CheckEvent> Function(String key) _follow;

  final ValueNotifier<CheckWatch> watch = ValueNotifier(const CheckWatch());
  final Completer<Verdict?> _result = Completer();
  StreamSubscription<CheckEvent>? _events;
  bool _cancelled = false;
  bool _notify;
  bool _left = false;

  /// The answer: a verdict, null when a deep check outlasted the wait, or a
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
        if (deep) return _deepCheck(value, link: link);
        final key = newRequestId();
        _listen(key);
        return link
            ? client.verifyUrl(value, language: language, recheck: recheck, requestId: key)
            : client.verifyText(value, language: language, recheck: recheck, requestId: key);
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
          requestId: key,
          onProgress: _showUpload,
        );
        watch.value = watch.value.copyWith(clearUpload: true);
        if (outcome.isPending) {
          // A video is checked in the background: its progress is followed by the
          // case id from here on, as a deep check's is.
          unawaited(_events?.cancel());
          _listen(outcome.pendingCaseId!);
          return _poll(outcome.pendingCaseId!);
        }
        return outcome.verdict;
    }
  }

  /// A deep check: started, then followed until the verdict. Null past the wait.
  Future<Verdict?> _deepCheck(String value, {required bool link}) async {
    final caseId = await services.client.startDeepCheck(
      text: link ? null : value,
      url: link ? value : null,
      language: language,
      recheck: recheck,
    );
    _listen(caseId);
    // Up to five minutes: past the server's own three-minute budget, so a check
    // that finished is always collected.
    for (var attempt = 0; attempt < 100; attempt++) {
      await Future<void>.delayed(const Duration(seconds: 3));
      if (_cancelled) return null;
      final progress = await services.client.checkOn(caseId);
      if (progress.verdict != null) return progress.verdict;
      watch.value = watch.value.copyWith(claimsDone: progress.done, claimsTotal: progress.total);
    }
    return null;
  }

  /// A video: accepted, then polled for. Checked from its still frames - read,
  /// fact-checked and put through the picture checks - which takes up to a couple
  /// of minutes, so the wait is bounded at two and a half.
  Future<Verdict?> _poll(String caseId) async {
    for (var attempt = 0; attempt < 50; attempt++) {
      await Future<void>.delayed(const Duration(seconds: 3));
      if (_cancelled) return null;
      final verdict = await services.client.getCase(caseId);
      if (verdict != null) return verdict;
    }
    return null;
  }

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
