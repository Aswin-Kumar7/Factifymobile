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
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/submission.dart';
import '../models/verdict.dart';

/// One finished check, as it is kept.
class HistoryRecord {
  const HistoryRecord({
    required this.id,
    required this.kind,
    required this.summary,
    required this.checkedAt,
    required this.verdictJson,
    this.text,
    this.thumbnail,
  });

  final String id;
  final SubmissionKind kind;

  /// A line to recognise it by: the start of the text, the link, or the file name.
  final String summary;

  /// The whole text or link, so a text check can be run again from history.
  final String? text;

  /// A small preview of a checked picture.
  final Uint8List? thumbnail;
  final DateTime checkedAt;
  final Map<String, dynamic> verdictJson;

  Verdict get verdict => Verdict.fromJson(verdictJson);

  Map<String, dynamic> toJson() => {
    'id': id,
    'kind': kind.name,
    'summary': summary,
    'text': text,
    'thumbnail': thumbnail == null ? null : base64Encode(thumbnail!),
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
      checkedAt: at,
      verdictJson: verdict.cast<String, dynamic>(),
    );
  }
}

class HistoryStore extends ChangeNotifier {
  /// Kept on the phone when [store] is given; in memory only otherwise (tests).
  HistoryStore({SharedPreferencesAsync? store}) : _store = store;

  static const String _key = 'check_history';

  /// The most kept. Older checks fall off the end.
  static const int limit = 50;

  final SharedPreferencesAsync? _store;
  List<HistoryRecord> _records = const [];
  bool _loaded = false;

  List<HistoryRecord> get records => _records;
  bool get loaded => _loaded;

  Future<void> load() async {
    try {
      final saved = await _store?.getString(_key);
      if (saved != null) {
        _records = [
          for (final item in jsonDecode(saved) as List)
            ?HistoryRecord.fromJson((item as Map).cast<String, dynamic>()),
        ];
      }
    } catch (_) {
      // An unreadable history is started afresh rather than crashing the app.
      _records = const [];
    }
    _loaded = true;
    notifyListeners();
  }

  /// Keep a finished check, newest first.
  Future<HistoryRecord> add(Submission submission, Verdict verdict) async {
    final record = HistoryRecord(
      id: '${verdict.caseId}-${DateTime.now().microsecondsSinceEpoch}',
      kind: submission.kind,
      summary: submission.summary,
      text: submission.text,
      thumbnail: await _smallPreview(submission.thumbnail),
      checkedAt: DateTime.now(),
      verdictJson: verdict.raw,
    );
    _records = [record, ..._records].take(limit).toList();
    notifyListeners();
    await _save();
    return record;
  }

  Future<void> remove(String id) async {
    _records = _records.where((r) => r.id != id).toList();
    notifyListeners();
    await _save();
  }

  Future<void> clear() async {
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
