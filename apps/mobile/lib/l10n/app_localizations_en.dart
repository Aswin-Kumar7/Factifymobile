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
  String get heroTitle => 'Is it true?';

  @override
  String get heroSubtitle =>
      'Paste a message or a link, or check a picture. We check it against reliable sources.';

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
      'Share a forward straight into Factify, paste it above, or check a picture. Every verdict comes with the sources behind it — and when there are none, it says so.';

  @override
  String get working => 'Looking for sources that address this';

  @override
  String get checkAgain => 'Check again';

  @override
  String get checkingTitle => 'Checking…';

  @override
  String get stepReading => 'Read what you shared';

  @override
  String get stepSearching => 'Search trusted news and fact-checkers';

  @override
  String get stepComparing => 'Compare each source with the claim';

  @override
  String get usuallyTakes => 'A check usually takes 20–50 seconds.';

  @override
  String get statusNotChecked => 'Not checked';

  @override
  String get claimNotSearched =>
      'Each check searches its five most important claims, and this wasn\'t one of them.';

  @override
  String get claimTimedOut =>
      'We ran out of time before any source for this could be read. Tap Check again.';

  @override
  String get claimNothingFound =>
      'We searched trusted news and fact-checkers and found nothing that addresses this.';

  @override
  String claimNoSources(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count sources',
      one: '1 source',
    );
    return 'We read $_temp0 and none addressed this directly.';
  }

  @override
  String get claimOneSource =>
      'Only one source addressed this. We need two independent ones before calling it true.';

  @override
  String elapsedSeconds(int seconds) {
    return '${seconds}s';
  }

  @override
  String get videoAcceptedTitle => 'Video accepted';

  @override
  String get videoAcceptedBody =>
      'Longer than a request can stay open. Checking now.';

  @override
  String get retry => 'Retry';

  @override
  String get reportedNote =>
      'Reported. We\'ll take another look at this result.';

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
      'This build has no server address. Rebuild it with --dart-define=FACTIFY_API=https://your-server.';

  @override
  String get errorShareUnreadable => 'Could not read the shared item.';

  @override
  String get errorShareFileUnopenable =>
      'That file could not be opened. Share it again, or use the Gallery button in Factify.';

  @override
  String errorVideoSlow(String caseId) {
    return 'That video is taking longer than expected. Case $caseId is still processing.';
  }

  @override
  String get errorCameraDenied =>
      'Factify needs camera access to check a photo you take.';

  @override
  String get errorFileUnopenable => 'That file could not be opened.';

  @override
  String get reportSent => 'Thanks. We\'ll review this result.';

  @override
  String reportFailed(String reason) {
    return 'Could not report: $reason';
  }

  @override
  String get correctionCopied =>
      'Correction copied - paste it back into the chat';

  @override
  String get correctionHeader => 'Checked with Factify:';

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
      'Factify is taking longer than usual. Try again in a moment.';

  @override
  String get failureUnreachable =>
      'Could not reach Factify. Check your connection and try again.';

  @override
  String get failureInterrupted =>
      'The connection to Factify was interrupted. Try again.';

  @override
  String get failureUnreadableFile =>
      'That file could not be read from this phone.';

  @override
  String get failureBadReply => 'Factify sent a reply this app could not read.';

  @override
  String get failureInvalidInput => 'That input could not be read.';

  @override
  String get failureLinkUnchecked =>
      'We couldn\'t find anything to check on that page. Some sites block automatic reading, so copy the article\'s text and paste it here instead.';

  @override
  String get failureTooLarge => 'That file is too large to check.';

  @override
  String get failureDailyLimit =>
      'Factify is at its daily limit. Please try again tomorrow.';

  @override
  String get failureUnavailable => 'Verification is not available right now.';

  @override
  String get failureGeneric => 'Factify could not complete that check.';

  @override
  String get headlineSafeToShare => 'True';

  @override
  String get subheadSafeToShare => 'Reliable sources confirm this';

  @override
  String get headlineShareWithContext => 'Misleading';

  @override
  String get subheadShareWithContext =>
      'True in part, but missing important context';

  @override
  String get headlineShareWithCorrection => 'Misleading';

  @override
  String get subheadShareWithCorrection => 'Part of this is wrong';

  @override
  String get headlineDoNotShare => 'False';

  @override
  String get subheadDoNotShare => 'Reliable sources show this is false';

  @override
  String get headlineWaitAndRecheck => 'Unconfirmed';

  @override
  String get subheadWaitAndRecheck => 'Too recent to confirm yet';

  @override
  String get headlineSendToReview => 'Unconfirmed';

  @override
  String get subheadSendToReview => 'We couldn\'t confirm or rule this out yet';

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
  String get whyNoVerdict => 'Why unconfirmed?';

  @override
  String seeEvidence(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'See all $count sources',
      one: 'See the source',
    );
    return '$_temp0';
  }

  @override
  String get shareCorrection => 'Share correction';

  @override
  String get report => 'Report wrong result';

  @override
  String get reporting => 'Reporting…';

  @override
  String get evidenceTitle => 'Sources';

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
      'This does not mean the content is false. It means nothing we could cite either supports or contradicts it, so Factify did not decide.';

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
  String get limitsTitle => 'What Factify cannot establish';

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
  String get receiptChecking => 'Checking the receipt';

  @override
  String get receiptVerified =>
      'Receipt verified. The evidence behind this result is unchanged since it was signed.';

  @override
  String get receiptFailed =>
      'Receipt did not verify. The stored evidence no longer matches what was signed.';

  @override
  String get receiptMissing => 'No receipt was issued for this result.';

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
  String get timelineTitle => 'Timeline';

  @override
  String get timelineFirstChecked => 'First checked by Factify';

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

  @override
  String confidence(int value) {
    return '$value% confidence';
  }

  @override
  String get unconfirmedBody =>
      'We couldn\'t find enough reliable sources that address this directly. Treat it with caution until it\'s confirmed.';

  @override
  String get sourcesTitle => 'Sources';

  @override
  String get sourceConfirms => 'Confirms';

  @override
  String get sourceRefutes => 'Refutes';

  @override
  String credibility(String level) {
    String _temp0 = intl.Intl.selectLogic(level, {
      'HIGH': 'Highly credible',
      'MEDIUM': 'Credible',
      'other': 'Source',
    });
    return '$_temp0';
  }

  @override
  String get howWeCheckedTitle => 'How we checked';

  @override
  String get howWeCheckedBody =>
      'We searched trusted news outlets, fact-checkers and official sources, read each one, and kept only the ones that directly address this claim. The verdict comes from what those sources say, weighed by how credible they are.';

  @override
  String get whatWeCheckedTitle => 'What we checked';

  @override
  String checkedAt(DateTime time) {
    final intl.DateFormat timeDateFormat = intl.DateFormat(
      'd MMM, HH:mm',
      localeName,
    );
    final String timeString = timeDateFormat.format(time);

    return 'Checked $timeString';
  }

  @override
  String get incompleteNote =>
      'Some sources couldn\'t be checked in time, so this answer may be incomplete.';

  @override
  String get account => 'Account';

  @override
  String get signIn => 'Sign in';

  @override
  String get signInTitle => 'Sign in to Factify';

  @override
  String get signInBody =>
      'Keep your profile and credits on any phone. We never keep a record of what you check.';

  @override
  String get emailLabel => 'Email';

  @override
  String get orDivider => 'or';

  @override
  String get continueWithGoogle => 'Continue with Google';

  @override
  String get signInUnavailable =>
      'Sign-in can\'t be reached right now. Check your connection and try again.';

  @override
  String get signOut => 'Sign out';

  @override
  String get creditsTitle => 'Credits';

  @override
  String creditsLeft(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count credits left',
      one: '1 credit left',
    );
    return '$_temp0';
  }

  @override
  String creditsUsed(int count) {
    return '$count used';
  }

  @override
  String creditCosts(int check, int deep) {
    return 'A check costs $check · a deep check costs $deep';
  }

  @override
  String checksSoFar(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count checks so far',
      one: '1 check so far',
    );
    return '$_temp0';
  }

  @override
  String memberSince(DateTime date) {
    final intl.DateFormat dateDateFormat = intl.DateFormat.yMMMd(localeName);
    final String dateString = dateDateFormat.format(date);

    return 'Member since $dateString';
  }

  @override
  String get planBeta => 'Free · beta, no limits yet';

  @override
  String get editName => 'Edit name';

  @override
  String get nameLabel => 'Name';

  @override
  String get save => 'Save';

  @override
  String get cancel => 'Cancel';

  @override
  String get failureSignedOut =>
      'Your sign-in has ended. Sign in again from your account.';

  @override
  String get failureOutOfCredits => 'You\'re out of credits for now.';

  @override
  String get authNetwork => 'Couldn\'t reach sign-in. Check your connection.';

  @override
  String get authTooMany => 'Too many tries. Wait a minute and try again.';

  @override
  String get authGeneric => 'Sign-in didn\'t work. Try again.';

  @override
  String get deepCheck => 'Deep check';

  @override
  String get deepCheckHint => 'More claims and sources · takes 1–3 minutes';

  @override
  String get deepChecking => 'Deep check…';

  @override
  String deepProgress(int done, int total) {
    return '$done of $total claims checked';
  }

  @override
  String get deepUsuallyTakes => 'A deep check usually takes 1–3 minutes.';

  @override
  String get deepTooSlow =>
      'The deep check is taking longer than expected. Try Check again in a minute.';

  @override
  String get imageReadTitle => 'What we read in your picture';

  @override
  String imageKind(String kind) {
    String _temp0 = intl.Intl.selectLogic(kind, {
      'NEWS_ARTICLE': 'News article',
      'SOCIAL_POST': 'Social media post',
      'CHAT_MESSAGE': 'Chat forward',
      'TV_GRAPHIC': 'TV news graphic',
      'POSTER': 'Poster',
      'DOCUMENT': 'Document',
      'PHOTO': 'Photo',
      'MEME': 'Meme',
      'other': 'Picture',
    });
    return '$_temp0';
  }

  @override
  String imageFrom(String publisher) {
    return 'Shows: $publisher';
  }

  @override
  String get imageTextLabel => 'Text in the picture';

  @override
  String get imageNoText =>
      'We found no text in this picture, so we checked the picture itself.';

  @override
  String get imageShowAllText => 'Show all the text';

  @override
  String get imageShowLessText => 'Show less';

  @override
  String get splashTagline => 'Check before you share';

  @override
  String get welcomeTitle => 'Know what\'s true before you share it';

  @override
  String get welcomeBody =>
      'Factify checks news, forwards, pictures and documents against reliable sources, and shows you every source it used.';

  @override
  String get welcomePointSources => 'Every answer comes with its sources';

  @override
  String get welcomePointInputs => 'Text, links, pictures and PDFs';

  @override
  String get welcomePointLanguages => 'In English and Hindi';

  @override
  String get welcomeSignInTitle => 'Create your account';

  @override
  String get welcomeSignInBody =>
      'An account is needed to check. Sign up or sign in with your email and a password, or with Google.';

  @override
  String get tabHome => 'Home';

  @override
  String get tabHistory => 'History';

  @override
  String get tabProfile => 'Profile';

  @override
  String homeGreeting(String name) {
    return 'Hi, $name';
  }

  @override
  String get homeGreetingGuest => 'Hi there';

  @override
  String get homeTitle => 'What would you like to check?';

  @override
  String get inputTypeText => 'Text or link';

  @override
  String get inputTypeImage => 'Image';

  @override
  String get inputTypePdf => 'PDF';

  @override
  String get inputTextHint => 'Paste a message, a claim or a news link';

  @override
  String get inputLinkDetected =>
      'Link found. We\'ll read the page and check it.';

  @override
  String get inputLocked =>
      'Remove what you\'ve added to switch to another type.';

  @override
  String get removeInput => 'Remove';

  @override
  String get pasteButton => 'Paste';

  @override
  String get pickImageTitle => 'Add a picture';

  @override
  String get pickImageBody =>
      'A screenshot, a WhatsApp forward or a photo. We read the text in it and check it.';

  @override
  String get pickPdfTitle => 'Add a PDF';

  @override
  String get pickPdfBody =>
      'A circular, a notice or any document. We read it and check what it claims.';

  @override
  String get choosePdf => 'Choose a PDF';

  @override
  String get notAPdf =>
      'That file isn\'t a PDF. Choose a PDF, or switch to Image.';

  @override
  String get checkNow => 'Check now';

  @override
  String get checkingOf => 'Checking';

  @override
  String get checkingCancel => 'Stop waiting';

  @override
  String get checkingFailedTitle => 'The check didn\'t finish';

  @override
  String get backToHome => 'Back to home';

  @override
  String get resultTitle => 'Result';

  @override
  String get newCheck => 'New check';

  @override
  String get historyEmptyTitle => 'No checks yet';

  @override
  String get historyEmptyBody =>
      'Everything you check is listed here, with its sources, so you can come back to it.';

  @override
  String get historyToday => 'Today';

  @override
  String get historyYesterday => 'Yesterday';

  @override
  String get historyClear => 'Clear history';

  @override
  String get historyClearConfirm => 'Delete every saved check from this phone?';

  @override
  String get historyDelete => 'Delete';

  @override
  String get historyFilterAll => 'All';

  @override
  String get historyStoredNote =>
      'Saved only on this phone. Nothing you check is kept on our servers. Swipe a check left to delete it.';

  @override
  String historySources(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count sources',
      one: '1 source',
      zero: 'No sources',
    );
    return '$_temp0';
  }

  @override
  String get profileTitle => 'Profile';

  @override
  String get guestTitle => 'You\'re not signed in';

  @override
  String get guestBody => 'Sign in to check news and keep your credits.';

  @override
  String get signInOrCreate => 'Sign in or create an account';

  @override
  String signedInWith(String method) {
    String _temp0 = intl.Intl.selectLogic(method, {
      'google': 'Signed in with Google',
      'other': 'Signed in with email',
    });
    return '$_temp0';
  }

  @override
  String get profileDetails => 'Account details';

  @override
  String get profileEmail => 'Email';

  @override
  String get profileName => 'Name';

  @override
  String get profilePlan => 'Plan';

  @override
  String get profileJoined => 'Member since';

  @override
  String get settingsTitle => 'Settings';

  @override
  String get settingLanguage => 'Language';

  @override
  String get settingHistory => 'Saved checks';

  @override
  String settingHistoryCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count checks on this phone',
      one: '1 check on this phone',
      zero: 'None saved',
    );
    return '$_temp0';
  }

  @override
  String get aboutTitle => 'About Factify';

  @override
  String get aboutBody =>
      'Factify checks what you share against reliable sources and always shows them. When the sources don\'t settle it, it says Unconfirmed rather than guess.';

  @override
  String get serviceStatus => 'Service';

  @override
  String get done => 'Done';

  @override
  String get modeSignIn => 'Sign in';

  @override
  String get modeCreateAccount => 'Create account';

  @override
  String get welcomeBackTitle => 'Welcome back';

  @override
  String get welcomeBackBody =>
      'Sign in with your email and password, or with Google.';

  @override
  String get passwordLabel => 'Password';

  @override
  String get confirmPasswordLabel => 'Confirm password';

  @override
  String passwordHint(int min) {
    return 'At least $min characters';
  }

  @override
  String get showPassword => 'Show password';

  @override
  String get hidePassword => 'Hide password';

  @override
  String get passwordsDontMatch => 'The passwords don\'t match.';

  @override
  String get createAccountButton => 'Create account';

  @override
  String get signInButton => 'Sign in';

  @override
  String get authInvalidEmail => 'That doesn\'t look like an email address.';

  @override
  String authWeakPassword(int min) {
    return 'Use a password of at least $min characters.';
  }

  @override
  String get authEmailTaken =>
      'There\'s already an account with this email. Sign in instead.';

  @override
  String get authWrongCredentials =>
      'That email and password don\'t match an account.';

  @override
  String get authUseGoogle =>
      'This account was made with Google. Use Continue with Google.';

  @override
  String get authGoogleFailed => 'Google sign-in didn\'t finish. Try again.';

  @override
  String get authGoogleUnavailable =>
      'Google sign-in isn\'t set up on this server yet. Use your email and a password.';

  @override
  String get yourPicture => 'Your picture';

  @override
  String get headlineNothingToCheck => 'Nothing to fact-check';

  @override
  String get subheadNothingToCheck => 'No claim found in it';

  @override
  String get nothingToCheckPicture =>
      'We read this picture and found no claim in it that can be checked - no news, figure or announcement, just an image. There\'s nothing here to confirm or rule out.';

  @override
  String get nothingToCheckText =>
      'We didn\'t find a factual claim in this - it reads as opinion, a joke or conversation, so there\'s nothing here to confirm or rule out.';

  @override
  String get searchUnavailableNote =>
      'Our news search couldn\'t be reached, so this wasn\'t checked against news reports. Tap Check again in a little while.';

  @override
  String get claimSearchUnavailable =>
      'Our news search couldn\'t be reached, so no news reports were looked at for this. It isn\'t the same as finding nothing.';

  @override
  String get documentReadTitle => 'What we read in your document';

  @override
  String get pasteCopiedText => 'Paste copied text';

  @override
  String get deepChip => 'Deep';

  @override
  String get deepChipOnHint => 'Deep check is on';

  @override
  String get shareFromWhatsApp => 'Or share from WhatsApp';

  @override
  String get checkTakes => 'Usually takes 20–50 seconds';

  @override
  String get checkTakesDeep => 'Deep check · usually 1–3 minutes';

  @override
  String get recentTitle => 'Recent';

  @override
  String get seeAll => 'See all';

  @override
  String get historySearchHint => 'Search past checks';

  @override
  String historyWeekRange(String range) {
    return 'This week · $range';
  }

  @override
  String historyChecksUnit(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'checks',
      one: 'check',
    );
    return '$_temp0';
  }

  @override
  String historyChecksCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count checks',
      one: '1 check',
    );
    return '$_temp0';
  }

  @override
  String historyBusiest(String days) {
    return 'Busiest: $days';
  }

  @override
  String historyDaysJoin(String first, String second) {
    return '$first and $second';
  }

  @override
  String historyStopped(int count) {
    return 'You stopped $count false or misleading forwards from spreading this week.';
  }

  @override
  String get historyNoResults => 'No checks match this search.';

  @override
  String get switchLanguage => 'Switch language';

  @override
  String get verdictOverline => 'VERDICT';

  @override
  String get confidenceChip => 'confidence';

  @override
  String get whyChip => 'Why?';

  @override
  String checkedEarlierOn(String date) {
    return 'Checked earlier · reused from $date';
  }

  @override
  String whatWeCheckedKind(String kind) {
    return 'What we checked · $kind';
  }

  @override
  String get kindText => 'Text';

  @override
  String get kindLink => 'Link';

  @override
  String get kindImage => 'Image';

  @override
  String get kindPdf => 'PDF';

  @override
  String claimCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count claims',
      one: '1 claim',
    );
    return '$_temp0';
  }

  @override
  String get claimStateSupported => 'Supported';

  @override
  String get claimStateContradicted => 'Contradicted';

  @override
  String get claimStateMissingContext => 'Missing context';

  @override
  String get claimStateUnconfirmed => 'Unconfirmed';

  @override
  String claimStateCount(int count, String state) {
    return '$count $state';
  }

  @override
  String get tapToRead => 'Tap to read';

  @override
  String get readSource => 'Read';

  @override
  String directionShort(String direction) {
    String _temp0 = intl.Intl.selectLogic(direction, {
      'supports': 'Supports',
      'contradicts': 'Refutes',
      'other': 'Context',
    });
    return '$_temp0';
  }

  @override
  String get noSourceTitle => 'No citable source was found';

  @override
  String get noSourceBody =>
      'This does not mean the content is false. It means nothing we could cite either supports or contradicts it, so Factify did not decide.';

  @override
  String get receiptVerifiedTitle => 'Receipt verified';

  @override
  String get receiptVerifiedBody =>
      'The evidence is unchanged since it was signed';

  @override
  String get receiptFailedTitle => 'Receipt did not verify';

  @override
  String get receiptFailedBody =>
      'The stored evidence no longer matches what was signed';

  @override
  String get shareResult => 'Share result';

  @override
  String get whyOverline => 'HOW SURE WE ARE';

  @override
  String whyTitle(int value) {
    return 'Why $value% confidence';
  }

  @override
  String get whyBody =>
      'Arithmetic on the cited sources: how many, how credible, and whether any disagree. Never a model score.';

  @override
  String get whyScaleLow => '50 · even';

  @override
  String get whyScaleHigh => '97 · never certain';

  @override
  String get whyExcluded => 'Excluded from this score: forensic signals.';

  @override
  String get whyNoVerdictOverline => 'WHY NO VERDICT';

  @override
  String get whyUncNotFalse =>
      'Unconfirmed is not the same as false. Factify decides only when cited sources settle it.';

  @override
  String get whyUncLater =>
      'New claims often get covered within a day or two. Check again later.';

  @override
  String get gotIt => 'Got it';

  @override
  String get mediaYourPicture => 'YOUR PICTURE';

  @override
  String get mediaEarlierCopy => 'EARLIER COPY';

  @override
  String get mediaSharedToday => 'Shared today';

  @override
  String mediaPublished(String date) {
    return 'Published $date';
  }

  @override
  String mediaMatchedBy(String publisher) {
    return '$publisher · earlier copy';
  }

  @override
  String get mediaMatchesEarlier => 'Matches a picture published earlier';

  @override
  String verdictSemantics(String verdict, int value) {
    return '$verdict, $value% confidence';
  }

  @override
  String get textInPicture => 'Text in the picture';

  @override
  String shows(String publisher) {
    return 'Shows: $publisher';
  }

  @override
  String compTier(String tier, int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count signed credentials',
      one: '1 signed credential',
    );
    String _temp1 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count dated sources',
      one: '1 dated source',
    );
    String _temp2 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count fact-checks',
      one: '1 fact-check',
    );
    String _temp3 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count news reports',
      one: '1 news report',
    );
    String _temp4 = intl.Intl.selectLogic(tier, {
      'A': '$_temp0',
      'B': '$_temp1',
      'C': '$_temp2',
      'other': '$_temp3',
    });
    return '$_temp4';
  }

  @override
  String get compNoEvidence => 'No evidence';

  @override
  String compOrigins(int origins, int documents) {
    String _temp0 = intl.Intl.pluralLogic(
      origins,
      locale: localeName,
      other: '$origins independent publishers',
      one: '1 independent publisher',
    );
    String _temp1 = intl.Intl.pluralLogic(
      documents,
      locale: localeName,
      other: '$documents pages',
      one: '1 page',
    );
    return '$_temp0, $_temp1';
  }

  @override
  String get compNoDated => 'No source carries a date';

  @override
  String compDated(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count dated findings',
      one: '1 dated finding',
    );
    return '$_temp0';
  }

  @override
  String compRisk(String risk) {
    String _temp0 = intl.Intl.selectLogic(risk, {
      'LOW': 'Publishers with a clean record',
      'MEDIUM': 'Some publisher risk',
      'HIGH': 'High publisher risk',
      'other': 'Publisher record not assessed',
    });
    return '$_temp0';
  }

  @override
  String get compNoConflict => 'No source disagrees';

  @override
  String compConflict(int supports, int contradicts) {
    return '$supports supporting, $contradicts contradicting';
  }

  @override
  String stepOf(int step, int total) {
    return 'Step $step of $total';
  }

  @override
  String sourcesRead(int read, int total) {
    return '$read of $total read';
  }

  @override
  String get sourcesWaiting => 'Sources appear here as they are opened';

  @override
  String get sourceReading => 'Reading…';

  @override
  String get sourceEvidence => 'Evidence found';

  @override
  String get sourceNotRelevant => 'Not relevant';

  @override
  String get evidenceCollected => 'Evidence collected';

  @override
  String evidenceNote(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count sources address this claim',
      one: '1 source addresses this claim',
      zero: 'Nothing yet, still reading',
    );
    return '$_temp0';
  }

  @override
  String get notifyMe => 'Notify me when ready';

  @override
  String get notifyOn => 'We\'ll notify you when it\'s ready';

  @override
  String get notifyDenied =>
      'Notifications are off for Factify. Turn them on in your phone\'s settings to be told.';

  @override
  String get notifyReadyTitle => 'Your check is ready';

  @override
  String get notifyReadyChannel => 'Finished checks';

  @override
  String get notifyWorkingTitle => 'Checking…';

  @override
  String get notifyWorkingBody => 'We\'ll tell you when the answer is ready.';

  @override
  String get notifyWorkingChannel => 'Checks in progress';

  @override
  String get notifyOpenResult => 'Open result';

  @override
  String get nothingToCheckShort => 'Nothing to check';

  @override
  String get pcTitle => 'Picture checks';

  @override
  String get pcTitleVideo => 'Video checks';

  @override
  String pcFrames(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count still frames',
      one: '1 still frame',
    );
    return '$_temp0';
  }

  @override
  String get pcNote => 'Not part of the verdict';

  @override
  String get pcCredentials => 'Content credentials';

  @override
  String get pcCredAi => 'The file says it was made with an AI tool';

  @override
  String pcCredAiTool(String tool) {
    return 'The file says it was made with an AI tool ($tool)';
  }

  @override
  String pcCredValid(String signer) {
    return 'Signed by $signer';
  }

  @override
  String get pcCredUntrusted => 'Present, but the signer isn\'t verified';

  @override
  String get pcCredInvalid => 'Present, but they don\'t check out';

  @override
  String get pcCredNone => 'None. That\'s normal: most pictures carry none.';

  @override
  String get pcNotChecked => 'Not checked';

  @override
  String get pcHistory => 'Earlier copies online';

  @override
  String pcHistorySince(String date, String source) {
    return 'Online since $date · $source';
  }

  @override
  String pcHistoryOld(String age) {
    return 'Not a new picture: it was online $age before this check.';
  }

  @override
  String pcAgeYears(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count years',
      one: '1 year',
    );
    return '$_temp0';
  }

  @override
  String pcAgeMonths(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count months',
      one: '1 month',
    );
    return '$_temp0';
  }

  @override
  String pcAgeDays(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count days',
      one: '1 day',
    );
    return '$_temp0';
  }

  @override
  String pcHistoryUndated(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Found on $count pages, none dated',
      one: 'Found on 1 page, with no date',
    );
    return '$_temp0';
  }

  @override
  String get pcHistoryNone => 'No earlier copies found online';

  @override
  String get pcOpenPage => 'Opens the page where it appeared';

  @override
  String get pcYourPicture => 'Your picture';

  @override
  String get pcEarlierCopy => 'Earlier copy';

  @override
  String get pcDetector => 'AI-made picture signal';

  @override
  String pcGenerated(int percent) {
    return '$percent% likely made by an AI image generator';
  }

  @override
  String pcFaceSwap(int percent) {
    return '$percent% likely a face was swapped or changed by AI';
  }

  @override
  String get pcDetectorNote => 'A detector\'s estimate, not a finding.';

  @override
  String get pcEditing => 'Editing signals';

  @override
  String get pcEditNoise =>
      'Parts of the picture have uneven noise, which editing can cause';

  @override
  String get pcEditSpectrum =>
      'Unusual patterns in the fine detail, which generators and heavy compression can cause';

  @override
  String get pcEditClean => 'No uneven noise or unusual patterns found';

  @override
  String get pcFooter =>
      'These are checks of the picture itself. They never change the verdict, which rests only on cited sources, and a clean result doesn\'t prove a picture is real.';

  @override
  String get kindVideo => 'Video';

  @override
  String get yourVideo => 'Your video';
}
