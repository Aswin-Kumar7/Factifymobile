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

enum SubmissionKind { text, link, image, document }

class Submission {
  const Submission._({
    required this.kind,
    this.text,
    this.file,
    this.thumbnail,
  });

  factory Submission.text(String value) => Submission._(kind: SubmissionKind.text, text: value);

  factory Submission.link(String value) => Submission._(kind: SubmissionKind.link, text: value);

  /// [thumbnail] is read once at pick time rather than re-read on every rebuild:
  /// the picked file lives in a cache directory the system may clear, and a
  /// preview that vanishes mid-session looks like a bug in the verdict.
  factory Submission.image(File file, Uint8List thumbnail) => Submission._(
    kind: SubmissionKind.image,
    file: file,
    thumbnail: thumbnail,
  );

  factory Submission.document(File file) => Submission._(
    kind: SubmissionKind.document,
    file: file,
  );

  final SubmissionKind kind;
  final String? text;
  final File? file;
  final Uint8List? thumbnail;

  bool get isMedia => kind == SubmissionKind.image || kind == SubmissionKind.document;

  /// A short line naming the submission, for history rows and the preview card:
  /// the text itself, or the file's name.
  String get summary {
    final value = text;
    if (value != null) {
      final flat = value.replaceAll(RegExp(r'\s+'), ' ').trim();
      return flat.length <= 90 ? flat : '${flat.substring(0, 88)}…';
    }
    return file?.uri.pathSegments.last ?? '';
  }
}
