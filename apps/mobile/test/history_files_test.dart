/// "Check again" on a kept picture or PDF (2026-09-27).
///
/// History kept only a small preview of a checked picture, so a picture reopened
/// from History could not be checked again, and neither could a fresh one once the
/// phone cleared the shared file from its cache. Held here: History keeps its own
/// copy, a kept check can be sent again from it, deleting the check deletes the
/// copy, and only the newest few files are kept.
library;

import 'dart:io';

import 'package:factify_mobile/history/history_store.dart';
import 'package:factify_mobile/models/submission.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:flutter_test/flutter_test.dart';

Verdict _verdict() => Verdict.fromJson({
  'case_id': 'case-1',
  'action': 'SEND_TO_REVIEW',
  'action_reason': 'r',
  'rule_version': 'v',
  'claims': <Object>[],
  'retrieved_at': '2026-09-27T10:00:00Z',
});

void main() {
  late Directory temp;
  late Directory kept;

  setUp(() {
    temp = Directory.systemTemp.createTempSync('factify-history-');
    kept = Directory('${temp.path}/checked');
  });
  tearDown(() => temp.deleteSync(recursive: true));

  File picture(String name) =>
      File('${temp.path}/$name')..writeAsBytesSync(List<int>.generate(64, (i) => i));

  test('a checked picture is kept, and can be checked again after the original is gone', () async {
    final history = HistoryStore(files: kept);
    final shared = picture('share-123.jpg');
    final record = await history.add(Submission.image(shared, null), _verdict());

    shared.deleteSync(); // the phone cleared its cache
    final again = record.submission;
    expect(again, isNotNull);
    expect(again!.kind, SubmissionKind.image);
    expect(again.file!.existsSync(), isTrue);
    expect(again.file!.path, startsWith(kept.path));

    // Survives being written out and read back.
    final restored = HistoryRecord.fromJson(record.toJson())!;
    expect(restored.submission?.file?.path, again.file!.path);
  });

  test('a PDF comes back as a PDF, and a video as a video', () async {
    final history = HistoryStore(files: kept);
    final pdf = await history.add(Submission.document(picture('notice.pdf')), _verdict());
    final video = await history.add(
      Submission.image(picture('clip.mp4'), null, video: true),
      _verdict(),
    );
    expect(pdf.submission!.kind, SubmissionKind.document);
    expect(video.submission!.video, isTrue);
  });

  test('deleting a check, or all of them, deletes the kept copies', () async {
    final history = HistoryStore(files: kept);
    final one = await history.add(Submission.image(picture('a.jpg'), null), _verdict());
    final two = await history.add(Submission.image(picture('b.jpg'), null), _verdict());

    await history.remove(one.id);
    expect(File(one.filePath!).existsSync(), isFalse);
    expect(File(two.filePath!).existsSync(), isTrue);

    await history.clear();
    expect(File(two.filePath!).existsSync(), isFalse);
  });

  test('only the newest files are kept; older checks keep their answer', () async {
    final history = HistoryStore(files: kept);
    final records = [
      for (var i = 0; i < HistoryStore.keptFiles + 2; i++)
        await history.add(Submission.image(picture('p$i.jpg'), null), _verdict()),
    ];
    final withFiles = history.records.where((r) => r.filePath != null).length;
    expect(withFiles, HistoryStore.keptFiles);
    expect(File(records.first.filePath!).existsSync(), isFalse);
    expect(history.records, hasLength(HistoryStore.keptFiles + 2));
  });

  test('a text check needs no file to be checked again', () async {
    final history = HistoryStore(files: kept);
    final record = await history.add(Submission.text('RBI is withdrawing notes.'), _verdict());
    expect(record.filePath, isNull);
    expect(record.submission?.text, 'RBI is withdrawing notes.');
    expect(kept.existsSync(), isFalse);
  });
}
