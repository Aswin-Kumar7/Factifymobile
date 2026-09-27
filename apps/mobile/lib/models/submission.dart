/// What the user actually handed over, kept so the interface can show it back.
///
/// The app previously picked an image, uploaded it, and displayed a verdict with
/// no sign of the picture anywhere. When a verdict says "this image was published
/// earlier", the one thing a person needs on screen is *which* image — otherwise
/// they are trusting a claim about a file they can no longer see.
///
/// No display words live here. What *kind* of thing was submitted is named by the
/// interface, in the reader's language (`checkingSubmission` in lib/l10n).
library;

import 'dart:io';
import 'dart:typed_data';

import 'verdict.dart';

enum SubmissionKind { text, link, image, document }

class Submission {
  const Submission._({
    required this.kind,
    this.text,
    this.file,
    this.thumbnail,
    this.video = false,
  });

  factory Submission.text(String value) => Submission._(kind: SubmissionKind.text, text: value);

  factory Submission.link(String value) => Submission._(kind: SubmissionKind.link, text: value);

  /// [thumbnail] is read once at pick time rather than re-read on every rebuild:
  /// the picked file lives in a cache directory the system may clear, and a
  /// preview that vanishes mid-session looks like a bug in the verdict.
  /// A picture, or a video shared into the app: both go up as a file and the
  /// server tells them apart by their bytes. [video] only changes what the
  /// interface calls it while it is being checked.
  factory Submission.image(File file, Uint8List? thumbnail, {bool video = false}) =>
      Submission._(kind: SubmissionKind.image, file: file, thumbnail: thumbnail, video: video);

  factory Submission.document(File file) => Submission._(kind: SubmissionKind.document, file: file);

  final SubmissionKind kind;
  final String? text;
  final File? file;
  final Uint8List? thumbnail;
  final bool video;

  bool get isMedia => kind == SubmissionKind.image || kind == SubmissionKind.document;

  /// A short line naming the submission, for history rows and the preview card:
  /// the text itself, or a document's name. Empty for a picture: its file name
  /// ("IMG-20260927-WA0003.jpg") means nothing to anyone, so the interface names it
  /// until the check says what it is about ([summaryWith]).
  String get summary {
    final value = text;
    if (value != null) return _short(value);
    if (kind == SubmissionKind.image) return '';
    // A shared file is copied under "share-<time>-<name>" (MainActivity); the name
    // is what the person would recognise.
    final name = file?.uri.pathSegments.last ?? '';
    return name.replaceFirst(RegExp(r'^share-\d+-'), '');
  }

  /// [summary], with a picture named by what the check found in it: its headline
  /// claim, else what the picture shows.
  String summaryWith(Verdict? verdict) {
    if (kind != SubmissionKind.image || verdict == null) return summary;
    final named = verdict.headline ?? verdict.imageReading?.description ?? '';
    return named.trim().isEmpty ? '' : _short(named);
  }

  static String _short(String value) {
    final flat = value.replaceAll(RegExp(r'\s+'), ' ').trim();
    return flat.length <= 90 ? flat : '${flat.substring(0, 88)}…';
  }
}
