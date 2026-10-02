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
  String get clear => 'Clear';

  @override
  String get sourceGallery => 'Gallery';

  @override
  String get sourceCamera => 'Camera';

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
  String get usuallyTakes =>
      'Every claim is checked, so this usually takes 1–2 minutes.';

  @override
  String get statusNotChecked => 'Not checked';

  @override
  String get claimNotSearched =>
      'This claim wasn\'t checked: an older version of Factify checked only three claims. Tap Check again.';

  @override
  String get claimTimedOut =>
      'No source for this could be read in time. Tap Check again.';

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
  String get retry => 'Retry';

  @override
  String get reportedNote =>
      'Reported. We\'ll take another look at this result.';

  @override
  String get errorShareFileUnopenable =>
      'That file could not be opened. Share it again, or use the Gallery button in Factify.';

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
  String get correctionCopied => 'Copied';

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
  String correctionChecked(String date) {
    return 'Checked $date';
  }

  @override
  String get correctionMessageWith => 'Message with it';

  @override
  String get correctionMessageHint =>
      'A polite note makes it easier to correct family and friends.';

  @override
  String get correctionMessageLabel => 'The message sent with the picture';

  @override
  String get correctionOpening => 'Hi! I checked this before forwarding.';

  @override
  String get correctionSaysFalse => 'Factify says it\'s false';

  @override
  String get correctionSaysMisleading => 'Factify says it\'s misleading';

  @override
  String get correctionSaysPartlyTrue => 'Factify says it\'s only partly true';

  @override
  String get correctionSaysTrue => 'Factify says it\'s true';

  @override
  String get correctionUnconfirmedMessage =>
      'Hi! I tried to check this before forwarding. Factify couldn\'t find reliable sources confirming it yet, so it may be best not to forward it for now.';

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
  String get failureTooLarge => 'That file is too large to check.';

  @override
  String get failureRateLimited =>
      'Too many requests at once. Wait a minute, then try again.';

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
  String get headlineShareWithCorrection => 'Partly true';

  @override
  String get subheadShareWithCorrection =>
      'Some of this is right, some of it isn\'t';

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
  String get englishOnlyNote =>
      'Some details below are shown in English for now.';

  @override
  String get whyNoVerdict => 'Why unconfirmed?';

  @override
  String get shareCorrection => 'Share correction';

  @override
  String get report => 'Report wrong result';

  @override
  String get reporting => 'Reporting…';

  @override
  String get evidenceTitle => 'Sources';

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
  String matchBasis(String metric, String value, String threshold) {
    return '$metric $value (threshold $threshold)';
  }

  @override
  String get openSource => 'Open source';

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
  String uploading(int percent) {
    return 'Uploading $percent%';
  }

  @override
  String get clipboardOffer => 'You have text copied. Check it?';

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
  String creditCosts(int check) {
    return 'A check costs $check';
  }

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
  String claimsProgress(int done, int total) {
    return '$done of $total claims checked';
  }

  @override
  String get checkTooSlow =>
      'This check is taking longer than usual. Try Check again in a minute.';

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
  String get pickImageTitle => 'Add a picture or video';

  @override
  String get pickImageBody =>
      'A screenshot, a WhatsApp forward, a photo or a video. We read what is in it and check it.';

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
      'This list is kept only on this phone. What you check is stored on our server without your name. Swipe a check left to remove it from this list.';

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
  String get profileJoined => 'Member since';

  @override
  String get settingsTitle => 'Settings';

  @override
  String get settingLanguage => 'Language';

  @override
  String get settingHistory => 'Saved checks';

  @override
  String get aboutTitle => 'About Factify';

  @override
  String get aboutBody =>
      'Factify checks what you share against reliable sources and always shows them. When the sources don\'t settle it, it says Unconfirmed rather than guess.';

  @override
  String get done => 'Done';

  @override
  String get modeSignIn => 'Sign in';

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
  String get nothingToCheckVideo =>
      'We checked this video\'s frames and found no claim in them that can be checked - no news, figure or announcement. There\'s nothing here to confirm or rule out.';

  @override
  String get nothingToCheckText =>
      'We didn\'t find a factual claim in this - it reads as opinion, a joke or conversation, so there\'s nothing here to confirm or rule out.';

  @override
  String get nothingToCheckAiPicture =>
      'But our AI-picture check says this picture was likely made by AI. See the picture checks below.';

  @override
  String get nothingToCheckAiVideo =>
      'But our checks say this video was likely made by AI. See the video checks below.';

  @override
  String get nothingToCheckAiDeclared =>
      'But its content credentials say it was made with an AI tool. See the checks below.';

  @override
  String get nothingToCheckVoice =>
      'But our checks say the voice in this video was likely made by a computer, not recorded from a person. See the video checks below.';

  @override
  String get nothingToCheckVoiceToo =>
      'Its voice was also likely made by a computer.';

  @override
  String get nothingToCheckFaceSwap =>
      'But our checks say a face in this video was likely swapped or changed by AI. See the video checks below.';

  @override
  String get nothingToCheckFaceSwapToo =>
      'A face in it was also likely swapped or changed by AI.';

  @override
  String get searchUnavailableNote =>
      'Our news search couldn\'t be reached, so this wasn\'t checked against news reports. Tap Check again in a little while.';

  @override
  String get claimSearchUnavailable =>
      'Our news search couldn\'t be reached, so no news reports were looked at for this. It isn\'t the same as finding nothing.';

  @override
  String get pasteCopiedText => 'Paste copied text';

  @override
  String get shareFromWhatsApp => 'Or share from WhatsApp';

  @override
  String get checkTakes => 'Every claim is checked · usually 1–2 minutes';

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
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other:
          '$count checks this week came back false, misleading or partly true.',
      one: '1 check this week came back false, misleading or partly true.',
    );
    return '$_temp0';
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
  String get claimStatePartlyTrue => 'Partly true';

  @override
  String get claimStateUnconfirmed => 'Unconfirmed';

  @override
  String claimInFull(String text) {
    return 'In full: $text';
  }

  @override
  String get rightWrongTitle => 'What\'s right, what\'s wrong';

  @override
  String get rightWrongRight => 'Right';

  @override
  String get rightWrongWrong => 'Wrong';

  @override
  String get rightWrongPartly => 'Only partly right';

  @override
  String get rightWrongContext => 'Missing context';

  @override
  String get rightWrongUnconfirmed => 'Not confirmed';

  @override
  String get sourcesReport => 'What sources actually report';

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
  String get saidInVideo => 'Said in the video';

  @override
  String get saidInVideoCutOff => 'Only the first three minutes were read.';

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
  String get sourceProfileTitle => 'About this website';

  @override
  String sourceProfileTrusted(String level) {
    return 'Trusted · $level';
  }

  @override
  String get sourceProfileFactChecker => 'Fact-checker';

  @override
  String get sourceProfileUnlisted => 'Not on our trusted list';

  @override
  String get sourceProfileNote =>
      'What we know about the site itself. It never makes a claim true or false.';

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
  String get pcWhyTextCard =>
      'Not needed: this is a text card or a screenshot, so the words in it are checked instead.';

  @override
  String get pcWhyTooSmall => 'The picture is too small to judge.';

  @override
  String get pcWhyUnreadable => 'The picture could not be read.';

  @override
  String get pcWhyDetectorOff =>
      'The AI-picture check is not set up on this server.';

  @override
  String get pcWhyHistoryOff =>
      'Searching for earlier copies is not set up on this server.';

  @override
  String get pcWhyFailed =>
      'It could not be checked this time. Try again later.';

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
  String get pcAgreeLikelyAi => 'Both detectors say this is likely AI-made';

  @override
  String get pcAgreeUnclear => 'The detectors disagree, so it\'s unclear';

  @override
  String get pcAgreeNoSign =>
      'No sign that an AI generator made it. That doesn\'t prove it\'s real.';

  @override
  String get pcOneLikelyAi => 'The detector says this is likely AI-made';

  @override
  String pcSecondOpinion(int percent) {
    return 'Second detector: $percent% likely AI-made';
  }

  @override
  String get pcNoFace => 'No face to check for a swap';

  @override
  String pcFacesChecked(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count faces checked',
      one: '1 face checked',
    );
    return '$_temp0';
  }

  @override
  String pcVoice(int percent) {
    return '$percent% likely a machine-made voice (experimental)';
  }

  @override
  String get pcOnServer => 'This check ran on Factify\'s own server.';

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

  @override
  String srDirection(String direction) {
    String _temp0 = intl.Intl.selectLogic(direction, {
      'supports': 'Supports the claim',
      'contradicts': 'Refutes the claim',
      'other': 'Adds context',
    });
    return '$_temp0';
  }

  @override
  String get srQuoted => 'Quoted in your result';

  @override
  String srParagraph(int number) {
    return 'Paragraph $number';
  }

  @override
  String srMatch(String score) {
    return 'match $score';
  }

  @override
  String srPublished(String date) {
    return 'Published $date';
  }

  @override
  String srReadMinutes(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count min read',
      one: '1 min read',
    );
    return '$_temp0';
  }

  @override
  String get srBack => 'Back to result';

  @override
  String get srOpenSite => 'Open site';

  @override
  String get srLoading => 'Opening the source…';

  @override
  String get srOnlyPassage =>
      'Only the passage around the quote is shown here. Open the site to read the whole article.';

  @override
  String get srUnavailable =>
      'We couldn\'t open this page just now, so this is the passage our result quoted. Open the site to read it.';

  @override
  String get srMoved =>
      'This page no longer carries the passage as we quoted it. It may have been edited since.';

  @override
  String get onbSkip => 'Skip';

  @override
  String get onbNext => 'Next';

  @override
  String onbPage(int page, int total) {
    return 'Page $page of $total';
  }

  @override
  String get onbForwarded => 'Forwarded many times';

  @override
  String get onbSampleForward =>
      'Govt to pay ₹5,000 a month to every woman from 1 July. Register at the link…';

  @override
  String get onbSampleLink =>
      'RBI keeps repo rate unchanged in September review';

  @override
  String get onbExample => 'An example';

  @override
  String get onbSampleClaim =>
      'Govt to pay ₹5,000 a month to every woman from 1 July.';

  @override
  String get onbSourcesBody =>
      'When the sources don\'t settle it, Factify says Unconfirmed rather than guess.';

  @override
  String get onbPrivacy =>
      'Your list of checks stays on your phone. What you check is stored on our server without your name.';

  @override
  String get confirmPasswordHint => 'Repeat it';

  @override
  String profileCreditsLabel(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'credits left',
      one: 'credit left',
    );
    return '$_temp0';
  }

  @override
  String get planBetaShort => 'Free · beta';

  @override
  String profileChecksLabel(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'checks so far',
      one: 'check so far',
    );
    return '$_temp0';
  }

  @override
  String get settingDarkMode => 'Dark mode';

  @override
  String get settingDarkFollowsPhone => 'Following your phone';

  @override
  String get themeBody =>
      'Factify can follow your phone\'s setting, or stay light or dark.';

  @override
  String get themePhone => 'Same as your phone';

  @override
  String get themeLight => 'Always light';

  @override
  String get themeDark => 'Always dark';

  @override
  String get settingNotify => 'Notify when ready';

  @override
  String get settingNotifyBody => 'For checks that take longer';

  @override
  String get settingService => 'Service';

  @override
  String get errUnfinished => 'The check didn\'t finish';

  @override
  String get errNoConnection => 'No connection';

  @override
  String get errRateLimited => 'Too many at once';

  @override
  String get errYourAccount => 'Your account';

  @override
  String get errLinkTitle => 'We couldn\'t read that page';

  @override
  String get errLinkBody =>
      'Some sites block automatic reading. Copy the article\'s text and paste it here instead.';

  @override
  String get errLinkNote => 'Couldn\'t be read automatically';

  @override
  String get errLinkAction => 'Paste the article text';

  @override
  String get errOfflineTitle => 'You\'re offline';

  @override
  String get errKept =>
      'Kept on this phone, so you won\'t need to paste it again';

  @override
  String get tryAgain => 'Try again';

  @override
  String get errSlowTitle => 'This is taking too long';

  @override
  String get errRateLimitTitle => 'Wait a minute, then try again';

  @override
  String get errCreditsTitle => 'You\'re out of credits';

  @override
  String get errCreditsAction => 'See your credits';

  @override
  String get errSignedOutTitle => 'Please sign in again';

  @override
  String get errTooLargeTitle => 'That file is too big';

  @override
  String get errTooLargeAction => 'Choose another file';

  @override
  String get errPausedTitle => 'Checking is paused for now';

  @override
  String get errClose => 'Close';

  @override
  String get errKeptFile =>
      'Still attached, so you won\'t need to choose it again';

  @override
  String settingSavedShort(int count) {
    return '$count on this phone';
  }

  @override
  String quickCheckedIn(int seconds) {
    return 'checked in $seconds s';
  }

  @override
  String get quickCopyCorrection => 'Copy correction';

  @override
  String get quickCopyContext => 'Copy context';

  @override
  String get quickCopyResult => 'Copy result';

  @override
  String get quickCopyNote => 'Copy a note';

  @override
  String get quickCopied => 'Copied — paste it in the chat';

  @override
  String get quickOpenResult => 'Open full result';

  @override
  String get quickOpenApp => 'Open Factify';

  @override
  String get quickSignIn => 'Sign in to Factify to check this.';

  @override
  String get settingQuick => 'Answer over the chat';

  @override
  String get settingQuickBody =>
      'Text you share opens its answer over the chat';

  @override
  String get settingBubble => 'Floating Factify button';

  @override
  String get settingBubbleBody =>
      'Copy a message in WhatsApp or any app, tap the button, and the answer opens over the chat';

  @override
  String get profileLoadFailed => 'Your account couldn\'t be loaded just now.';

  @override
  String mediaVisualMatch(String publisher, int percent) {
    return '$publisher · $percent% visual match';
  }

  @override
  String sourcesFactChecks(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Compared with $count published fact-checks',
      one: 'Compared with 1 published fact-check',
    );
    return '$_temp0';
  }

  @override
  String get sourceSetAside => 'Set aside';

  @override
  String evidenceFoundSoFar(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count sources speak to this claim - checking them next',
      one: '1 source speaks to this claim - checking it next',
      zero: 'Nothing yet, still reading',
    );
    return '$_temp0';
  }

  @override
  String evidenceHeldUp(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count sources held up when checked against the claim',
      one: '1 source held up when checked against the claim',
      zero: 'None held up when checked against the claim',
    );
    return '$_temp0';
  }

  @override
  String get onb3Title => 'Pictures and videos too';

  @override
  String get onb3Body =>
      'Factify spots AI-made pictures, face swaps and machine voices, and checks what\'s said in a video.';

  @override
  String get onbMediaMessages => 'Messages';

  @override
  String get onbMediaLinks => 'Links';

  @override
  String get onbMediaPictures => 'Pictures';

  @override
  String get onbMediaVideos => 'Videos';

  @override
  String get onbMediaVoice => 'Voices in videos';

  @override
  String get onbMediaPdfs => 'PDFs';

  @override
  String get onbHaveAccount => 'I have an account';

  @override
  String get authHaveAccount => 'Have an account?';

  @override
  String get authNewHere => 'New to Factify?';

  @override
  String get authCreateLink => 'Create one';

  @override
  String get nameOptionalLabel => 'Your name (optional)';

  @override
  String get nameOptionalHint => 'What should we call you?';

  @override
  String get signUpTitle => 'Create your account';

  @override
  String get signUpBody => '30 free checks every month. It takes a minute.';

  @override
  String surveyStep(int step, int total) {
    return '$step of $total';
  }

  @override
  String get surveySkipAll => 'Skip all';

  @override
  String get surveyNext => 'Next';

  @override
  String get surveyFinish => 'Finish';

  @override
  String get surveyPickAny => 'Pick any that fit';

  @override
  String get surveyWhy =>
      'Four quick questions help us build Factify for you. Skip any you like.';

  @override
  String get surveyRoleQ => 'What brings you to Factify?';

  @override
  String get surveyRoleJournalist => 'Journalist or fact-checker';

  @override
  String get surveyRoleStudent => 'Student or researcher';

  @override
  String get surveyRoleTeacher => 'Teacher';

  @override
  String get surveyRoleFamily => 'Checking forwards for family and friends';

  @override
  String get surveyRoleCurious => 'Just curious';

  @override
  String get surveyPlacesQ => 'Where do you see things you\'d like to check?';

  @override
  String get surveyPlaceNews => 'News sites';

  @override
  String get surveyWantsQ => 'What do you want to check most?';

  @override
  String get surveyWantForwards => 'Forwards and messages';

  @override
  String get surveyWantLinks => 'News links';

  @override
  String get surveyWantPictures => 'Pictures';

  @override
  String get surveyWantVideos => 'Videos';

  @override
  String get surveyWantVoice => 'Voice notes';

  @override
  String get surveyHeardQ => 'How did you hear about Factify?';

  @override
  String get surveyHeardFriend => 'From a friend';

  @override
  String get surveyHeardSocial => 'On social media';

  @override
  String get surveyHeardCollege => 'At college or an event';

  @override
  String get surveyHeardOther => 'Somewhere else';

  @override
  String get surveySaveFailed =>
      'Your answers couldn\'t be saved. You can carry on anyway.';

  @override
  String creditsTitleNamed(String name) {
    return 'You\'re in, $name';
  }

  @override
  String get creditsWelcomeTitle => 'You\'re in';

  @override
  String get creditsLabel => 'free checks';

  @override
  String get creditsBody =>
      'They\'re on us. Each check uses one, and your balance is always in Profile.';

  @override
  String get creditsStart => 'Start checking';

  @override
  String get buyCredits => 'Buy credits';

  @override
  String get payTitle => 'Finish in your browser';

  @override
  String get payOpening => 'Opening the payment page…';

  @override
  String get payWaiting =>
      'Choose a pack and pay in the browser. This screen moves on by itself when the payment goes through.';

  @override
  String get payOpened => 'Payment page open. Waiting for your payment…';

  @override
  String get payReopen => 'Open the payment page again';

  @override
  String get payCancel => 'Cancel';

  @override
  String get payPaidTitle => 'Payment complete';

  @override
  String payPaidBody(int credits) {
    return '$credits credits were added.';
  }

  @override
  String get payFailedTitle => 'Payment didn\'t go through';

  @override
  String get payFailedBody =>
      'Nothing was charged. Try again, or choose another way to pay.';

  @override
  String get payCancelledTitle => 'Payment cancelled';

  @override
  String get payCancelledBody => 'Nothing was charged.';

  @override
  String get payExpiredTitle => 'The payment link expired';

  @override
  String get payExpiredBody =>
      'It\'s only valid for 10 minutes. Start again to get a new one.';

  @override
  String get payTryAgain => 'Start again';

  @override
  String get payDone => 'Done';

  @override
  String get payCouldNotStart =>
      'The payment couldn\'t be started. Check your connection and try again.';

  @override
  String get planChecksTitle => 'Checks this month';

  @override
  String planName(String name) {
    return '$name plan';
  }

  @override
  String planChecksLeft(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count checks left this month',
      one: '1 check left this month',
    );
    return '$_temp0';
  }

  @override
  String planChecksLabel(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'checks left',
      one: 'check left',
    );
    return '$_temp0';
  }

  @override
  String planUsed(int used, int total) {
    return '$used of $total plan checks used';
  }

  @override
  String planResets(String date) {
    return 'Resets $date';
  }

  @override
  String planCredits(int count) {
    return '+$count credits';
  }

  @override
  String get upgradePlan => 'Upgrade plan';

  @override
  String get changePlan => 'Change plan';

  @override
  String get payPlanPaidBody =>
      'Your new plan is active. Its checks are yours from now.';

  @override
  String get privacyPolicy => 'Privacy policy';

  @override
  String get deleteAccount => 'Delete account';

  @override
  String get deleteAccountTitle => 'Delete your account?';

  @override
  String get deleteAccountBody =>
      'This deletes your account for good: your sign-in, any plan and credits you have left, your payment records and your survey answers. The checks saved on this phone are cleared too.';

  @override
  String get deleteAccountContinue => 'Continue';

  @override
  String get deleteAccountConfirmTitle => 'Delete for good?';

  @override
  String deleteAccountConfirmBody(String email) {
    return 'The account $email will be deleted now. This can\'t be undone.';
  }

  @override
  String get deleteAccountConfirm => 'Delete for good';

  @override
  String get deleteAccountDeleting => 'Deleting…';

  @override
  String get deleteAccountDone => 'Your account has been deleted.';

  @override
  String deleteAccountFailed(String reason) {
    return 'Your account wasn\'t deleted. $reason';
  }

  @override
  String planEnds(String date) {
    return 'Ends $date';
  }

  @override
  String planRenews(String date) {
    return 'Renews $date';
  }

  @override
  String planExtraCapped(String price, String used, String cap) {
    return 'Extra checks on, $price each: $used of $cap used';
  }

  @override
  String planExtraUncapped(String price, String used) {
    return 'Extra checks on, $price each: $used used';
  }

  @override
  String get planExtraBlocked =>
      'Extra checks are paused until your unpaid extra-usage bill is paid.';

  @override
  String get planPreviewNote =>
      'During the preview you can keep checking after your plan\'s checks run out.';

  @override
  String get creditsPreviewNote =>
      'During the preview you can keep checking after your credits run out.';

  @override
  String creditCostsVideo(int check, int video) {
    return 'A check costs $check, a video $video';
  }

  @override
  String planVideoCost(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'A video uses $count checks',
      one: 'A video uses 1 check',
    );
    return '$_temp0';
  }

  @override
  String get sourceVideo => 'Video';

  @override
  String videoTooLarge(int mb) {
    return 'That video is over $mb MB. Choose a shorter one, or trim it first.';
  }

  @override
  String get notAVideo =>
      'That file isn\'t a video Factify can read. Choose an MP4, MOV or WebM video.';

  @override
  String videoFirstSeconds(int seconds) {
    String _temp0 = intl.Intl.pluralLogic(
      seconds,
      locale: localeName,
      other:
          'We look at the first $seconds seconds of a video and listen to its first 3 minutes.',
    );
    return '$_temp0';
  }

  @override
  String whatWeReadKind(String kind) {
    return 'What Factify read · $kind';
  }

  @override
  String kindPostOn(String platform) {
    return '$platform post';
  }

  @override
  String kindVideoOn(String platform) {
    return '$platform video';
  }

  @override
  String get kindPost => 'Post';

  @override
  String readPartial(String kind) {
    String _temp0 = intl.Intl.selectLogic(kind, {
      'post': 'Factify could only read part of this post.',
      'page': 'Factify could only read part of this page.',
      'video': 'Factify could only read part of this video.',
      'picture': 'Factify could only read part of this picture.',
      'document': 'Factify could only read part of this document.',
      'other': 'Factify could only read part of this.',
    });
    return '$_temp0';
  }

  @override
  String get readNothing => 'Nothing could be read from it.';

  @override
  String get readShowAll => 'Show all';

  @override
  String get readInPart => 'Read only in part';

  @override
  String get readNotChecked => 'Description only, not checked';

  @override
  String get readDescribedByFactify => 'Described by Factify';

  @override
  String readHeard(String read, String total) {
    return '$read of $total heard';
  }

  @override
  String readHeardAll(String total) {
    return 'All $total heard';
  }

  @override
  String get readYoutubeLimit =>
      'YouTube doesn\'t let Factify download the video, so its AI, face-swap and voice checks didn\'t run.';

  @override
  String get partMessage => 'Message';

  @override
  String get partPost => 'Post';

  @override
  String get partQuotedPost => 'Quoted post';

  @override
  String partQuotedPostBy(String who) {
    return 'Quoted post by $who';
  }

  @override
  String get partTitle => 'Title';

  @override
  String get partDescription => 'Description';

  @override
  String get partArticle => 'Article';

  @override
  String get partLinkedArticle => 'Linked article';

  @override
  String partLinkedArticleOn(String host) {
    return 'Linked article · $host';
  }

  @override
  String partPictureText(int index, int total) {
    return 'Text in picture $index of $total';
  }

  @override
  String get partOnScreenText => 'Text shown in the video';

  @override
  String get partDocumentText => 'Text in the PDF';

  @override
  String get partPictureDescription => 'What the picture shows';

  @override
  String get partVideoDescription => 'What the video shows';

  @override
  String get gapHeadlineOnly =>
      'Only the page\'s headline and summary could be read, not the article itself.';

  @override
  String get gapTextTruncated =>
      'The post\'s text was cut short, so the rest of it wasn\'t read.';

  @override
  String get gapPostUnavailable =>
      'The post couldn\'t be opened. It may have been deleted or made private, or be a story.';

  @override
  String get gapLoginRequired =>
      'The site shows this only to people who are signed in.';

  @override
  String get gapNotSupported =>
      'Factify can\'t read posts from this site yet. Paste the text or upload a screenshot.';

  @override
  String get gapPictureUnread => 'A picture in it couldn\'t be read.';

  @override
  String get gapVideoUnread => 'The video couldn\'t be read.';

  @override
  String get gapSpeechUnread => 'What is said in the video couldn\'t be heard.';

  @override
  String get gapCutOff =>
      'It was too long to read to the end, so only the start was read.';

  @override
  String get gapPagesUnread => 'Only some of the document\'s pages were read.';

  @override
  String get gapTooLarge => 'The video is too large to download.';

  @override
  String get gapNeedsBackground => 'Videos are read only in a full check.';

  @override
  String get gapReaderUnavailable =>
      'What\'s needed to read this isn\'t available right now.';

  @override
  String get gapFirstPictureOnly =>
      'Only the first picture of the album could be seen.';

  @override
  String get gapArticleTruncated =>
      'The article is long, and its opening part was read.';

  @override
  String get gapDescriptionUnread =>
      'The video\'s description couldn\'t be read.';

  @override
  String get gapLinkedPageUnread =>
      'The article it links to couldn\'t be read, so it was left out.';

  @override
  String get withheldOverline => 'NOT CHECKED';

  @override
  String get withheldTitle => 'Not checked yet';

  @override
  String get withheldShort => 'Not checked';

  @override
  String get withheldBody =>
      'Factify could not read all of this, so it has not given a verdict.';

  @override
  String get withheldCheckWhatWasRead => 'Check what was read';

  @override
  String get withheldPasteText => 'Paste the text';

  @override
  String get withheldUpload => 'Upload the picture or video';

  @override
  String get withheldCheckNote =>
      'Checks only what Factify could read. The answer can\'t be True, because part of it wasn\'t read.';

  @override
  String checkedPartially(String kind) {
    String _temp0 = intl.Intl.selectLogic(kind, {
      'post': 'Checked from part of the post',
      'page': 'Checked from part of the page',
      'video': 'Checked from part of the video',
      'picture': 'Checked from part of the picture',
      'document': 'Checked from part of the document',
      'other': 'Checked from part of it',
    });
    return '$_temp0';
  }

  @override
  String get subheadPartlyRead => 'Part of it could not be read';

  @override
  String get partlyReadBody =>
      'What Factify could read is supported by sources, but part of it couldn\'t be read, so the whole of it isn\'t confirmed.';

  @override
  String get pasteSheetTitle => 'Paste the text to check';

  @override
  String get pasteSheetBody =>
      'Copy the words of the post or the article, and paste them here.';

  @override
  String get pasteSheetHint => 'Paste or type the text';

  @override
  String get notReadTitle => 'What could not be read';

  @override
  String get incompleteChecksNote =>
      'Some checks couldn\'t run, so this answer may be incomplete.';

  @override
  String pcTitleNumbered(int index) {
    return 'Picture $index checks';
  }

  @override
  String quickRead(String list) {
    return 'Read: $list';
  }

  @override
  String get quickReadPost => 'post';

  @override
  String get quickReadQuoted => 'quoted post';

  @override
  String get quickReadPage => 'page';

  @override
  String get quickReadLinked => 'linked article';

  @override
  String quickReadPictures(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count pictures',
      one: '1 picture',
    );
    return '$_temp0';
  }

  @override
  String get quickReadVideo => 'video';

  @override
  String quickReadVideoLength(String length) {
    return 'video $length';
  }

  @override
  String get quickReadDocument => 'document';

  @override
  String get quickReadMessage => 'message';
}
