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
    FailureKind.signedOut => failureSignedOut,
    FailureKind.outOfCredits => failureOutOfCredits,
    FailureKind.generic => failureGeneric,
  };

  /// Where a claim sits in the submission, or null when nothing locates it.
  String? describeInputAnchor(InputAnchor anchor) {
    final page = anchor.pageNumber;
    if (page != null) return inputAnchorPage(page);
    final moment = anchor.frameStartMs;
    if (moment != null) return inputAnchorMoment(moment ~/ 1000);
    // A bare character range ("Characters 110-249") says nothing to a reader. Where
    // the words themselves are at hand they are shown instead; where they are not -
    // a link, a picture's reading - the claim above says it.
    return null;
  }

  /// A cited source named for a reader: its publisher, else its site.
  String describeSource(Evidence evidence) {
    final publisher = evidence.publisher;
    if (publisher != null && publisher.isNotEmpty) return publisher;
    final host = Uri.tryParse(evidence.citationUrl)?.host.replaceFirst(RegExp(r'^www\.'), '');
    return host == null || host.isEmpty ? correctionSourceFallback : host;
  }
}
