/// Words for values that arrive as data: a failure kind, a position in a source.
///
/// Kept beside the translations rather than in the models, so `lib/models` and
/// `lib/api` hold no display text and every sentence the reader sees comes from
/// the ARB files.
library;

import '../api/client.dart';
import '../models/verdict.dart';
import 'app_localizations.dart';

extension Phrases on AppLocalizations {
  /// A failure in the reader's language.
  ///
  /// [ApiFailure.detail] is deliberately not used: the server writes it for
  /// developers, and only in English.
  String describeFailure(ApiFailure failure) => switch (failure.kind) {
    FailureKind.timeout => failureTimeout,
    FailureKind.unreachable => failureUnreachable,
    FailureKind.interrupted => failureInterrupted,
    FailureKind.unreadableFile => failureUnreadableFile,
    FailureKind.badReply => failureBadReply,
    FailureKind.invalidInput => failureInvalidInput,
    FailureKind.tooLarge => failureTooLarge,
    FailureKind.dailyLimit => failureDailyLimit,
    FailureKind.unavailable => failureUnavailable,
    FailureKind.generic => failureGeneric,
  };

  /// Where in the source the quoted excerpt sits, or null when the source gave
  /// no position at all.
  String? describeAnchor(SourceAnchor anchor) {
    final page = anchor.pageNumber;
    if (page != null) return anchorPage(page);
    final paragraph = anchor.paragraphIndex;
    // Counted from zero on the wire, from one for a reader.
    if (paragraph != null) return anchorParagraph(paragraph + 1);
    final start = anchor.charStart;
    if (start != null) return anchorCharacters(start, anchor.charEnd ?? start);
    return null;
  }
}
