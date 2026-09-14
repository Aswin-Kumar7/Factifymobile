// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get tabCheck => 'Check';

  @override
  String get tabActivity => 'Activity';

  @override
  String get statusOnline => 'Online';

  @override
  String get statusOffline => 'Offline';

  @override
  String get statusChecking => 'Checking';

  @override
  String get languageMenuTooltip => 'Language';

  @override
  String get languagePhone => 'Phone language';

  @override
  String get heroTitle =>
      'Verdicts from cited sources,\nnever from a model score';

  @override
  String get heroSubtitle =>
      'Paste a forward, drop a link, or check a picture.';

  @override
  String get inputLabel => 'Paste a message or a link';

  @override
  String get inputHint =>
      'Or share straight from WhatsApp, a browser, or the gallery';

  @override
  String get clear => 'Clear';

  @override
  String get checkThis => 'Check this';

  @override
  String get sourceGallery => 'Gallery';

  @override
  String get sourceCamera => 'Camera';

  @override
  String get sourceFile => 'File';

  @override
  String checkingSubmission(String kind) {
    String _temp0 = intl.Intl.selectLogic(kind, {
      'text': 'Checking this message',
      'link': 'Checking this link',
      'image': 'Checking this image',
      'other': 'Checking this document',
    });
    return '$_temp0';
  }

  @override
  String get emptyTitle => 'Nothing checked yet';

  @override
  String get emptyBody =>
      'Share a forward straight into Facify, paste it above, or check a picture. Every verdict comes with the sources behind it — and when there are none, it says so.';

  @override
  String get working => 'Looking for sources that address this';

  @override
  String get videoAcceptedTitle => 'Video accepted';

  @override
  String get videoAcceptedBody =>
      'Longer than a request can stay open. Checking now.';

  @override
  String get retry => 'Retry';

  @override
  String get reportedNote => 'Reported. A reviewer will see this case.';

  @override
  String get activityEmptyTitle => 'No checks this session';

  @override
  String get activityEmptyBody =>
      'Results stay on this device for the session and are gone when the app closes — what you check is nobody\'s record.';

  @override
  String get activityFooter =>
      'Session only, by design: what you check is a record of what you were suspicious about, and this app does not keep one.';

  @override
  String get historyTitle => 'Earlier this session';

  @override
  String historyCitations(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count citations',
      one: '1 citation',
      zero: 'No citable evidence',
    );
    return '$_temp0';
  }

  @override
  String get errorNoServerAddress =>
      'This build has no server address. Rebuild it with --dart-define=FACIFY_API=https://your-server.';

  @override
  String get errorShareUnreadable => 'Could not read the shared item.';

  @override
  String get errorShareFileUnopenable =>
      'That file could not be opened. Share it again, or use the Gallery button in Facify.';

  @override
  String errorVideoSlow(String caseId) {
    return 'That video is taking longer than expected. Case $caseId is still processing.';
  }

  @override
  String get errorCameraDenied =>
      'Facify needs camera access to check a photo you take.';

  @override
  String get errorFileUnopenable => 'That file could not be opened.';

  @override
  String get reportSent => 'Sent for human review';

  @override
  String reportFailed(String reason) {
    return 'Could not report: $reason';
  }

  @override
  String get correctionCopied =>
      'Correction copied - paste it back into the chat';

  @override
  String get correctionHeader => 'Checked with Facify:';

  @override
  String get correctionSourceFallback => 'Source';

  @override
  String get correctionNoSource =>
      'No published source could confirm or contradict this.';

  @override
  String get correctionSheetTitle => 'Send this back to the chat';

  @override
  String get shareContext => 'Share with context';

  @override
  String get correctionSheetBody =>
      'This picture goes to the chat, with the source links as text beside it.';

  @override
  String get correctionShareImage => 'Share picture';

  @override
  String get correctionCopyText => 'Copy text only';

  @override
  String get correctionShareFailed =>
      'Sharing could not open. The correction was copied instead — paste it into the chat.';

  @override
  String get correctionCardFooter =>
      'Verdict from cited sources, never from a model score.';

  @override
  String get failureTimeout =>
      'Facify is taking longer than usual. Try again in a moment.';

  @override
  String get failureUnreachable =>
      'Could not reach Facify. Check your connection and try again.';

  @override
  String get failureInterrupted =>
      'The connection to Facify was interrupted. Try again.';

  @override
  String get failureUnreadableFile =>
      'That file could not be read from this phone.';

  @override
  String get failureBadReply => 'Facify sent a reply this app could not read.';

  @override
  String get failureInvalidInput => 'That input could not be read.';

  @override
  String get failureTooLarge => 'That file is too large to check.';

  @override
  String get failureDailyLimit =>
      'Facify is at its daily limit. Please try again tomorrow.';

  @override
  String get failureUnavailable => 'Verification is not available right now.';

  @override
  String get failureGeneric => 'Facify could not complete that check.';

  @override
  String get headlineSafeToShare => 'Nothing contradicts this';

  @override
  String get subheadSafeToShare => 'Independent sources agree';

  @override
  String get headlineShareWithContext => 'True, but missing context';

  @override
  String get subheadShareWithContext => 'Share the context with it';

  @override
  String get headlineShareWithCorrection => 'A detail here is wrong';

  @override
  String get subheadShareWithCorrection => 'Share only with a correction';

  @override
  String get headlineDoNotShare => 'Contradicted by sources';

  @override
  String get subheadDoNotShare => 'Published sources say otherwise';

  @override
  String get headlineWaitAndRecheck => 'Still developing';

  @override
  String get subheadWaitAndRecheck => 'Early reports are often revised';

  @override
  String get headlineSendToReview => 'Not enough evidence to decide';

  @override
  String get subheadSendToReview => 'Queued for human review';

  @override
  String citationCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count citations',
      one: '1 citation',
      zero: 'No citations',
    );
    return '$_temp0';
  }

  @override
  String evidenceRetrievedAt(DateTime time) {
    final intl.DateFormat timeDateFormat = intl.DateFormat(
      'd MMM, HH:mm',
      localeName,
    );
    final String timeString = timeDateFormat.format(time);

    return 'Evidence retrieved $timeString';
  }

  @override
  String get checkedEarlier => 'Checked earlier';

  @override
  String get reusedNote =>
      'Reused from an earlier check of the same content. The evidence below is from that check.';

  @override
  String get englishOnlyNote =>
      'Some details below are shown in English for now.';

  @override
  String get whyNoVerdict => 'Why no verdict?';

  @override
  String seeEvidence(int count) {
    return 'See evidence ($count)';
  }

  @override
  String get shareCorrection => 'Share correction';

  @override
  String get report => 'Report';

  @override
  String get reporting => 'Reporting…';

  @override
  String get evidenceTitle => 'Evidence';

  @override
  String get theClaim => 'The claim';

  @override
  String evidenceStrength(String band) {
    return 'Evidence strength: $band';
  }

  @override
  String strengthBand(String band) {
    String _temp0 = intl.Intl.selectLogic(band, {
      'none': 'none',
      'weak': 'weak',
      'moderate': 'moderate',
      'strong': 'strong',
      'conclusive': 'conclusive',
      'other': '$band',
    });
    return '$_temp0';
  }

  @override
  String strengthComponent(String name) {
    String _temp0 = intl.Intl.selectLogic(name, {
      'tier_composition': 'Evidence tiers',
      'independent_origins': 'Independent origins',
      'temporal_confidence': 'Dating',
      'source_transparency': 'Publisher transparency',
      'conflict_penalty': 'Conflicting evidence',
      'other': '$name',
    });
    return '$_temp0';
  }

  @override
  String excludedFromScore(String providers) {
    return 'Excluded from this score: $providers';
  }

  @override
  String tierLabel(String tier) {
    String _temp0 = intl.Intl.selectLogic(tier, {
      'A': 'Signed content credential',
      'B': 'Dated source',
      'C': 'Published fact-check',
      'other': 'Corroboration',
    });
    return '$_temp0';
  }

  @override
  String directionLabel(String direction) {
    String _temp0 = intl.Intl.selectLogic(direction, {
      'supports': 'Supports',
      'contradicts': 'Contradicts',
      'risk_signal': 'Risk signal',
      'other': 'Context',
    });
    return '$_temp0';
  }

  @override
  String anchorPage(int page) {
    return 'Found at page $page';
  }

  @override
  String anchorParagraph(int paragraph) {
    return 'Found at paragraph $paragraph';
  }

  @override
  String anchorCharacters(int start, int end) {
    return 'Found at characters $start to $end';
  }

  @override
  String matchBasis(String metric, String value, String threshold) {
    return '$metric $value (threshold $threshold)';
  }

  @override
  String get openSource => 'Open source';

  @override
  String get noEvidenceTitle => 'No citable source was found';

  @override
  String get noEvidenceBody =>
      'This does not mean the content is false. It means nothing we could cite either supports or contradicts it, so Facify did not decide.';

  @override
  String get historyCardTitle => 'History';

  @override
  String recurrenceCaptions(int count) {
    return 'The same media has carried $count different captions. An authentic photograph does not usually acquire several mutually exclusive stories.';
  }

  @override
  String get contentCredentials => 'Content credentials';

  @override
  String get notCheckedTitle => 'What could not be checked';

  @override
  String get limitsTitle => 'What Facify cannot establish';

  @override
  String get limitAi =>
      'Whether an image or video was generated by AI. No detector is reliable enough to say so, and we do not pretend otherwise.';

  @override
  String get limitUnreported =>
      'Whether something unreported is false. Absence of coverage is not evidence either way.';

  @override
  String get limitPrivate =>
      'Anything about private content, or claims no published source has addressed.';

  @override
  String get limitIntent =>
      'Intent. We can show what a source said and when, not why someone shared it.';

  @override
  String caseLabel(String caseId) {
    return 'Case $caseId';
  }

  @override
  String checkedIn(int ms) {
    return 'Checked in $ms ms';
  }

  @override
  String get verifyResult => 'Verify this result';

  @override
  String sourceRiskTitle(String risk) {
    String _temp0 = intl.Intl.selectLogic(risk, {
      'HIGH': 'Publisher has a high risk profile',
      'MEDIUM': 'Publisher has a mixed record',
      'LOW': 'Publisher has an established record',
      'other': 'Publisher risk not assessed',
    });
    return '$_temp0';
  }

  @override
  String sourceRiskDetail(String risk) {
    String _temp0 = intl.Intl.selectLogic(risk, {
      'HIGH':
          'Recently registered, or with a record of unreliable material. This describes the publisher, not this claim.',
      'MEDIUM':
          'Some signals worth noting about the source. This describes the publisher, not this claim.',
      'LOW':
          'No adverse signals about the source. This is not evidence that the claim itself is true.',
      'other': 'Nothing is known either way.',
    });
    return '$_temp0';
  }

  @override
  String get advisoryHeader =>
      'Forensic signals - shown for transparency. These are not used in the verdict and cannot change it.';

  @override
  String advisoryCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count signals',
      one: '1 signal',
    );
    return '$_temp0';
  }

  @override
  String get advisoryFooter =>
      'None of these can establish that content is authentic or fabricated. The verdict above is based only on cited sources.';

  @override
  String get advisoryRowExcluded =>
      'Forensic signal - not used in this verdict.';

  @override
  String get techniqueLabel => 'How posts like this mislead';

  @override
  String get techniqueRecycledMediaTitle => 'Recycled picture';

  @override
  String get techniqueRecycledMediaBody =>
      'A picture published earlier, shared again as if it showed something new. Before trusting a photo, look for when it first appeared.';

  @override
  String get techniqueMissingContextTitle => 'Missing context';

  @override
  String get techniqueMissingContextBody =>
      'Published material framed to suggest something its sources do not say. Ask what the post leaves out.';

  @override
  String get techniqueMisattributedQuoteTitle =>
      'Words put in someone\'s mouth';

  @override
  String get techniqueMisattributedQuoteBody =>
      'A quote credited to someone that published sources do not record them saying. Look for the original speech or statement.';

  @override
  String get techniqueTwistedNumberTitle => 'Twisted number';

  @override
  String get techniqueTwistedNumberBody =>
      'A figure changed, or taken from a source that says something different. Find the number in its original source.';

  @override
  String get techniqueWrongIdentityTitle => 'Wrong label';

  @override
  String get techniqueWrongIdentityBody =>
      'A person or place presented as someone or somewhere else. Check names and places against a dated source.';

  @override
  String get techniqueDistortedEventTitle => 'Distorted event';

  @override
  String get techniqueDistortedEventBody =>
      'An event described differently from how published sources report it. Look for reporting from more than one outlet.';

  @override
  String get timelineTitle => 'Timeline';

  @override
  String get timelineFirstChecked => 'First checked by Facify';

  @override
  String get timelineRetrieved => 'Evidence gathered for this result';

  @override
  String get inputAnchorLabel => 'Where your submission says this';

  @override
  String inputAnchorCharacters(int start, int end) {
    return 'Characters $start–$end';
  }

  @override
  String inputAnchorPage(int page) {
    return 'Page $page';
  }

  @override
  String inputAnchorMoment(int seconds) {
    return 'At $seconds s in the video';
  }

  @override
  String get mediaMatchYours => 'Your picture';

  @override
  String get mediaMatchEarlier => 'Matches a picture published earlier';

  @override
  String strengthComponentCitations(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count sources',
      one: '1 source',
    );
    return '$_temp0';
  }

  @override
  String uploading(int percent) {
    return 'Uploading $percent%';
  }

  @override
  String get clipboardOffer => 'You have text copied. Check it?';

  @override
  String get clipboardPasteAndCheck => 'Paste and check';

  @override
  String get clipboardDismiss => 'Not now';
}
