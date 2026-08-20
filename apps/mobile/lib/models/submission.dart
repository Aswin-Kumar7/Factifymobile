/// What the user actually handed over, kept so the interface can show it back.
///
/// The app previously picked an image, uploaded it, and displayed a verdict with
/// no sign of the picture anywhere. When a verdict says "this image was published
/// earlier", the one thing a person needs on screen is *which* image — otherwise
/// they are trusting a claim about a file they can no longer see.
library;

import 'dart:io';
import 'dart:typed_data';

enum SubmissionKind { text, link, image, document }

class Submission {
  const Submission._({
    required this.kind,
    required this.label,
    this.text,
    this.file,
    this.thumbnail,
  });

  factory Submission.text(String value) =>
      Submission._(kind: SubmissionKind.text, label: 'Message', text: value);

  factory Submission.link(String value) =>
      Submission._(kind: SubmissionKind.link, label: 'Link', text: value);

  /// [thumbnail] is read once at pick time rather than re-read on every rebuild:
  /// the picked file lives in a cache directory the system may clear, and a
  /// preview that vanishes mid-session looks like a bug in the verdict.
  factory Submission.image(File file, Uint8List thumbnail) => Submission._(
    kind: SubmissionKind.image,
    label: 'Image',
    file: file,
    thumbnail: thumbnail,
  );

  factory Submission.document(File file) => Submission._(
    kind: SubmissionKind.document,
    label: 'Document',
    file: file,
  );

  final SubmissionKind kind;
  final String label;
  final String? text;
  final File? file;
  final Uint8List? thumbnail;

  bool get isMedia => kind == SubmissionKind.image || kind == SubmissionKind.document;

  /// A short line naming the submission, for history rows and the preview card.
  String get summary {
    final value = text;
    if (value != null) {
      final flat = value.replaceAll(RegExp(r'\s+'), ' ').trim();
      return flat.length <= 90 ? flat : '${flat.substring(0, 88)}…';
    }
    return file?.uri.pathSegments.last ?? label;
  }
}
