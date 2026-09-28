/// What a claim's state is called, and why an undecided one has no verdict.
///
/// Shared by the result and the evidence screen, so the two can never describe the
/// same claim differently.
library;

import '../l10n/app_localizations.dart';
import '../models/verdict.dart';

/// Supported, Contradicted, Partly true, Missing context, Unconfirmed.
String claimStateLabel(ClaimMark mark, AppLocalizations l10n) => switch (mark) {
  ClaimMark.right => l10n.claimStateSupported,
  ClaimMark.wrong => l10n.claimStateContradicted,
  ClaimMark.partly => l10n.claimStatePartlyTrue,
  ClaimMark.missingContext => l10n.claimStateMissingContext,
  ClaimMark.unconfirmed => l10n.claimStateUnconfirmed,
};

/// One line on why a claim stands where it does. A decided claim gives the source
/// check's own explanation; an undecided one says what was actually done for it.
///
/// "We couldn't find enough reliable sources" used to be said of every undecided
/// claim, including ones that were never searched: a check searches its most
/// important claims, and the next one down was told no source addressed it.
String claimReason(Claim claim, AppLocalizations l10n) {
  if (claim.isDecisive) {
    final explanation = claim.explanation;
    return explanation != null && explanation.trim().isNotEmpty ? explanation : claim.reason;
  }
  final taking = claim.evidence.where((e) => e.supports || e.contradicts).length;
  final looked = claim.sourcesLookedAt ?? 0;
  return switch (claim.search) {
    'not_searched' => l10n.claimNotSearched,
    'unavailable' when taking == 0 => l10n.claimSearchUnavailable,
    'timed_out' when taking == 0 => l10n.claimTimedOut,
    'searched' when taking == 1 => l10n.claimOneSource,
    'searched' when taking == 0 && looked > 0 => l10n.claimNoSources(looked),
    'searched' when taking == 0 => l10n.claimNothingFound,
    _ => l10n.unconfirmedBody,
  };
}
