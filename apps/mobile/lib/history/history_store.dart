/// Past checks, kept on this phone and nowhere else.
///
/// The server keeps no record of who checked what: the credit ledger holds that a
/// check was run, never what it was of. History is therefore the phone's own, so a
/// person can go back to an answer and its sources, and it can be wiped from the
/// profile screen in one tap. It stores the server's response exactly as it came, so
/// an old answer is shown from the same data it was first shown from.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:clock/clock.dart';
import 'package:flutter/material.dart' show DateUtils;
import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/submission.dart';
import '../models/verdict.dart';

/// One finished check, as it is kept.
class HistoryRecord {
  HistoryRecord({
    required this.id,
    required this.kind,
    required this.summary,
    required this.checkedAt,
    required this.verdictJson,
    this.text,
    this.thumbnail,
    this.filePath,
    this.video = false,
  });

  final String id;
  final SubmissionKind kind;

  /// A line to recognise it by: the start of the text, the link, or the file name.
  final String summary;

  /// The whole text or link, so a text check can be run again from history.
  final String? text;

  /// A small preview of a checked picture.
  final Uint8List? thumbnail;

  /// History's own copy of a checked picture, video or PDF, so it can be checked
  /// again. On this phone only; null for text, and for the oldest files once there
  /// are more than [HistoryStore.keptFiles].
  final String? filePath;
  final bool video;

  /// What was checked, as it can be sent again - or null when it cannot.
  Submission? get submission {
    final value = text;
    if (value != null) {
      return kind == SubmissionKind.link ? Submission.link(value) : Submission.text(value);
    }
    final path = filePath;
    if (path == null) return null;
    final file = File(path);
    if (!file.existsSync()) return null;
    return kind == SubmissionKind.document
        ? Submission.document(file)
        : Submission.image(file, thumbnail, video: video);
  }

  final DateTime checkedAt;
  final Map<String, dynamic> verdictJson;

  /// The answer, read once from the kept response.
  late final Verdict verdict = Verdict.fromJson(verdictJson);

  /// The verdict it is listed and counted under. A check with nothing in it to
  /// check is filed with Unconfirmed: it was not found true or false.
  FactVerdict get factVerdict => verdict.factVerdict;

  /// How many different pages the answer cited.
  int get sourceCount => {for (final e in verdict.allEvidence) e.citationUrl}.length;

  /// The calendar day it was checked on, in the phone's time.
  DateTime get day => DateUtils.dateOnly(checkedAt.toLocal());

  Map<String, dynamic> toJson() => {
    'id': id,
    'kind': kind.name,
    'summary': summary,
    'text': text,
    'thumbnail': thumbnail == null ? null : base64Encode(thumbnail!),
    'file': filePath,
    'video': video,
    'checked_at': checkedAt.toIso8601String(),
    'verdict': verdictJson,
  };

  static HistoryRecord? fromJson(Map<String, dynamic> json) {
    final verdict = json['verdict'];
    final at = DateTime.tryParse(json['checked_at'] as String? ?? '');
    if (verdict is! Map || at == null) return null;
    final thumb = json['thumbnail'] as String?;
    return HistoryRecord(
      id: json['id'] as String? ?? at.toIso8601String(),
      kind: SubmissionKind.values.firstWhere(
        (k) => k.name == json['kind'],
        orElse: () => SubmissionKind.text,
      ),
      summary: json['summary'] as String? ?? '',
      text: json['text'] as String?,
      thumbnail: thumb == null ? null : base64Decode(thumb),
      filePath: json['file'] as String?,
      video: json['video'] as bool? ?? false,
      checkedAt: at,
      verdictJson: verdict.cast<String, dynamic>(),
    );
  }
}

class HistoryStore extends ChangeNotifier {
  /// Kept on the phone when [store] is given; in memory only otherwise (tests).
  /// Checked files are copied into [files], or the app's own storage on the phone;
  /// without either (tests), a record points at the file as it was checked.
  HistoryStore({SharedPreferencesAsync? store, Directory? files}) : _store = store, _files = files;

  /// Checked pictures, videos and PDFs kept for "Check again": the newest this many.
  /// Older checks keep their answer and preview; only the file itself goes.
  static const int keptFiles = 12;

  /// A file larger than this is not copied: the server takes nothing bigger.
  static const int largestFile = 30 * 1024 * 1024;

  final Directory? _files;

  static const String _key = 'check_history';

  /// The most kept. Older checks fall off the end.
  static const int limit = 50;

  final SharedPreferencesAsync? _store;
  List<HistoryRecord> _records = const [];
  int _added = 0;
  bool _loaded = false;

  List<HistoryRecord> get records => _records;
  bool get loaded => _loaded;

  /// Reads what is kept on the phone. Called again whenever the app comes back to
  /// the front, since a check answered over a chat (the quick verdict, which runs
  /// apart from the app) may have been kept since.
  Future<void> load() async {
    await _reread();
    _loaded = true;
    notifyListeners();
  }

  /// The kept list, as it is on the phone now. Every change starts from it rather
  /// than from memory: the quick verdict keeps checks from a second copy of the
  /// app, and writing an old list back would drop them.
  Future<void> _reread() async {
    final store = _store;
    if (store == null) return;
    try {
      final saved = await store.getString(_key);
      _records = saved == null
          ? const []
          : [
              for (final item in jsonDecode(saved) as List)
                ?HistoryRecord.fromJson((item as Map).cast<String, dynamic>()),
            ];
    } catch (_) {
      // An unreadable history is started afresh rather than crashing the app.
      _records = const [];
    }
  }

  /// Keep a finished check, newest first.
  Future<HistoryRecord> add(Submission submission, Verdict verdict) async {
    // The counter keeps two checks saved within one clock tick apart.
    final id = '${verdict.caseId}-${DateTime.now().microsecondsSinceEpoch}-${_added++}';
    final record = HistoryRecord(
      id: id,
      kind: submission.kind,
      summary: submission.summaryWith(verdict),
      text: submission.text,
      thumbnail: await _smallPreview(submission.thumbnail),
      filePath: await _keep(submission.file, id),
      video: submission.video,
      checkedAt: clock.now(),
      verdictJson: verdict.raw,
    );
    await _reread();
    final all = [record, ..._records];
    _records = all.take(limit).toList();
    // Files beyond the newest few, and of checks that fell off the list, are let go.
    var files = 0;
    _records = [
      for (final r in _records)
        if (r.filePath != null && ++files > keptFiles) _withoutFile(r) else r,
    ];
    for (final gone in all.skip(limit)) {
      await _forget(gone.filePath);
    }
    notifyListeners();
    await _save();
    return record;
  }

  /// A copy of a checked file that History owns: the one shared or picked may be
  /// in a cache the phone clears. Null when there is nothing to keep, or it could
  /// not be copied - the check is kept either way.
  Future<String?> _keep(File? file, String id) async {
    if (file == null) return null;
    try {
      if (!file.existsSync() || file.lengthSync() > largestFile) return null;
      final folder = _files ?? (_store == null ? null : await _folder());
      if (folder == null) return file.path;
      await folder.create(recursive: true);
      final name = file.uri.pathSegments.last;
      final dot = name.lastIndexOf('.');
      final ending = dot < 0 ? '' : name.substring(dot);
      final safe = id.replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '_');
      return (await file.copy('${folder.path}/$safe$ending')).path;
    } catch (_) {
      return null;
    }
  }

  static Future<Directory> _folder() async =>
      Directory('${(await getApplicationSupportDirectory()).path}/checked');

  HistoryRecord _withoutFile(HistoryRecord r) {
    unawaited(_forget(r.filePath));
    return HistoryRecord(
      id: r.id,
      kind: r.kind,
      summary: r.summary,
      checkedAt: r.checkedAt,
      verdictJson: r.verdictJson,
      text: r.text,
      thumbnail: r.thumbnail,
      video: r.video,
    );
  }

  /// Deletes a kept copy - only ever one History made itself.
  Future<void> _forget(String? path) async {
    if (path == null) return;
    try {
      final folder = _files ?? (_store == null ? null : await _folder());
      if (folder == null || !path.startsWith(folder.path)) return;
      final file = File(path);
      if (file.existsSync()) await file.delete();
    } catch (_) {
      // A copy that could not be deleted is left for the phone to clear.
    }
  }

  /// This week, Monday to Sunday, for History's chart and recap (v5).
  WeekSummary weekSummary([DateTime? now]) {
    final today = DateUtils.dateOnly((now ?? clock.now()).toLocal());
    final monday = today.subtract(Duration(days: today.weekday - DateTime.monday));
    final days = [for (var i = 0; i < 7; i++) DateUtils.addDaysToDate(monday, i)];
    final byDay = [
      for (final day in days)
        [
          for (final record in _records)
            if (DateUtils.isSameDay(record.day, day)) record.factVerdict,
        ]..sort((a, b) => WeekSummary.order.indexOf(a).compareTo(WeekSummary.order.indexOf(b))),
    ];
    return WeekSummary(today: today, days: days, byDay: byDay);
  }

  Future<void> remove(String id) async {
    await _reread();
    for (final r in _records.where((r) => r.id == id)) {
      await _forget(r.filePath);
    }
    _records = _records.where((r) => r.id != id).toList();
    notifyListeners();
    await _save();
  }

  Future<void> clear() async {
    await _reread();
    for (final r in _records) {
      await _forget(r.filePath);
    }
    _records = const [];
    notifyListeners();
    try {
      await _store?.remove(_key);
    } catch (_) {}
  }

  Future<void> _save() async {
    try {
      await _store?.setString(_key, jsonEncode([for (final r in _records) r.toJson()]));
    } catch (_) {
      // Not being able to keep history must never cost the check itself.
    }
  }

  /// A preview small enough to keep fifty of: 160 pixels wide.
  static Future<Uint8List?> _smallPreview(Uint8List? image) async {
    if (image == null) return null;
    try {
      final codec = await ui.instantiateImageCodec(image, targetWidth: 160);
      final frame = await codec.getNextFrame();
      final data = await frame.image.toByteData(format: ui.ImageByteFormat.png);
      frame.image.dispose();
      return data?.buffer.asUint8List();
    } catch (_) {
      return null;
    }
  }
}

/// A week of checks: per day, per verdict, for the History chart and recap.
class WeekSummary {
  const WeekSummary({required this.today, required this.days, required this.byDay});

  /// The order a day's bar is stacked in, from the bottom.
  static const order = [
    FactVerdict.falseClaim,
    FactVerdict.partlyTrue,
    FactVerdict.misleading,
    FactVerdict.trueClaim,
    FactVerdict.unconfirmed,
  ];

  final DateTime today;

  /// Monday to Sunday.
  final List<DateTime> days;

  /// For each of [days], the verdicts checked that day, in [order].
  final List<List<FactVerdict>> byDay;

  DateTime get start => days.first;
  DateTime get end => days.last;

  int get total => byDay.fold(0, (sum, day) => sum + day.length);

  int count(FactVerdict verdict) =>
      byDay.fold(0, (sum, day) => sum + day.where((v) => v == verdict).length);

  /// False, partly true and misleading forwards caught this week: the positive recap.
  int get stopped =>
      count(FactVerdict.falseClaim) +
      count(FactVerdict.partlyTrue) +
      count(FactVerdict.misleading);

  /// The busiest days, at most two, or none in an empty week.
  List<DateTime> get busiest {
    final most = byDay.fold(0, (m, day) => day.length > m ? day.length : m);
    if (most == 0) return const [];
    return [
      for (final (i, day) in byDay.indexed)
        if (day.length == most) days[i],
    ].take(2).toList();
  }
}
