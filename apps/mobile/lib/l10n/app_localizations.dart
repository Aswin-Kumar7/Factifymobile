import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_en.dart';
import 'app_localizations_hi.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('en'),
    Locale('hi'),
  ];

  /// No description provided for @tabCheck.
  ///
  /// In en, this message translates to:
  /// **'Check'**
  String get tabCheck;

  /// No description provided for @statusOnline.
  ///
  /// In en, this message translates to:
  /// **'Online'**
  String get statusOnline;

  /// No description provided for @statusOffline.
  ///
  /// In en, this message translates to:
  /// **'Offline'**
  String get statusOffline;

  /// No description provided for @statusChecking.
  ///
  /// In en, this message translates to:
  /// **'Checking'**
  String get statusChecking;

  /// No description provided for @languageMenuTooltip.
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get languageMenuTooltip;

  /// No description provided for @languagePhone.
  ///
  /// In en, this message translates to:
  /// **'Phone language'**
  String get languagePhone;

  /// No description provided for @clear.
  ///
  /// In en, this message translates to:
  /// **'Clear'**
  String get clear;

  /// No description provided for @sourceGallery.
  ///
  /// In en, this message translates to:
  /// **'Gallery'**
  String get sourceGallery;

  /// No description provided for @sourceCamera.
  ///
  /// In en, this message translates to:
  /// **'Camera'**
  String get sourceCamera;

  /// Label above the preview of what was submitted. kind is text, link, image or document.
  ///
  /// In en, this message translates to:
  /// **'{kind, select, text{Checking this message} link{Checking this link} image{Checking this image} other{Checking this document}}'**
  String checkingSubmission(String kind);

  /// No description provided for @working.
  ///
  /// In en, this message translates to:
  /// **'Looking for sources that address this'**
  String get working;

  /// No description provided for @checkAgain.
  ///
  /// In en, this message translates to:
  /// **'Check again'**
  String get checkAgain;

  /// No description provided for @checkingTitle.
  ///
  /// In en, this message translates to:
  /// **'Checking…'**
  String get checkingTitle;

  /// No description provided for @stepReading.
  ///
  /// In en, this message translates to:
  /// **'Read what you shared'**
  String get stepReading;

  /// No description provided for @stepSearching.
  ///
  /// In en, this message translates to:
  /// **'Search trusted news and fact-checkers'**
  String get stepSearching;

  /// No description provided for @stepComparing.
  ///
  /// In en, this message translates to:
  /// **'Compare each source with the claim'**
  String get stepComparing;

  /// No description provided for @usuallyTakes.
  ///
  /// In en, this message translates to:
  /// **'Every claim is checked, so this usually takes 1–2 minutes.'**
  String get usuallyTakes;

  /// No description provided for @statusNotChecked.
  ///
  /// In en, this message translates to:
  /// **'Not checked'**
  String get statusNotChecked;

  /// No description provided for @claimNotSearched.
  ///
  /// In en, this message translates to:
  /// **'This claim wasn\'t checked: an older version of Factify checked only three claims. Tap Check again.'**
  String get claimNotSearched;

  /// No description provided for @claimTimedOut.
  ///
  /// In en, this message translates to:
  /// **'No source for this could be read in time. Tap Check again.'**
  String get claimTimedOut;

  /// No description provided for @claimNothingFound.
  ///
  /// In en, this message translates to:
  /// **'We searched trusted news and fact-checkers and found nothing that addresses this.'**
  String get claimNothingFound;

  /// No description provided for @claimNoSources.
  ///
  /// In en, this message translates to:
  /// **'We read {count, plural, =1{1 source} other{{count} sources}} and none addressed this directly.'**
  String claimNoSources(int count);

  /// No description provided for @claimOneSource.
  ///
  /// In en, this message translates to:
  /// **'Only one source addressed this. We need two independent ones before calling it true.'**
  String get claimOneSource;

  /// No description provided for @elapsedSeconds.
  ///
  /// In en, this message translates to:
  /// **'{seconds}s'**
  String elapsedSeconds(int seconds);

  /// No description provided for @retry.
  ///
  /// In en, this message translates to:
  /// **'Retry'**
  String get retry;

  /// No description provided for @reportedNote.
  ///
  /// In en, this message translates to:
  /// **'Reported. We\'ll take another look at this result.'**
  String get reportedNote;

  /// No description provided for @errorShareFileUnopenable.
  ///
  /// In en, this message translates to:
  /// **'That file could not be opened. Share it again, or use the Gallery button in Factify.'**
  String get errorShareFileUnopenable;

  /// No description provided for @errorCameraDenied.
  ///
  /// In en, this message translates to:
  /// **'Factify needs camera access to check a photo you take.'**
  String get errorCameraDenied;

  /// No description provided for @errorFileUnopenable.
  ///
  /// In en, this message translates to:
  /// **'That file could not be opened.'**
  String get errorFileUnopenable;

  /// Shown only after the server has accepted the report.
  ///
  /// In en, this message translates to:
  /// **'Thanks. We\'ll review this result.'**
  String get reportSent;

  /// No description provided for @reportFailed.
  ///
  /// In en, this message translates to:
  /// **'Could not report: {reason}'**
  String reportFailed(String reason);

  /// No description provided for @correctionCopied.
  ///
  /// In en, this message translates to:
  /// **'Copied'**
  String get correctionCopied;

  /// No description provided for @correctionSourceFallback.
  ///
  /// In en, this message translates to:
  /// **'Source'**
  String get correctionSourceFallback;

  /// No description provided for @correctionNoSource.
  ///
  /// In en, this message translates to:
  /// **'No published source could confirm or contradict this.'**
  String get correctionNoSource;

  /// No description provided for @correctionSheetTitle.
  ///
  /// In en, this message translates to:
  /// **'Send this back to the chat'**
  String get correctionSheetTitle;

  /// No description provided for @shareContext.
  ///
  /// In en, this message translates to:
  /// **'Share with context'**
  String get shareContext;

  /// No description provided for @correctionSheetBody.
  ///
  /// In en, this message translates to:
  /// **'This picture goes to the chat, with the source links as text beside it.'**
  String get correctionSheetBody;

  /// No description provided for @correctionShareImage.
  ///
  /// In en, this message translates to:
  /// **'Share picture'**
  String get correctionShareImage;

  /// No description provided for @correctionCopyText.
  ///
  /// In en, this message translates to:
  /// **'Copy text only'**
  String get correctionCopyText;

  /// No description provided for @correctionShareFailed.
  ///
  /// In en, this message translates to:
  /// **'Sharing could not open. The correction was copied instead — paste it into the chat.'**
  String get correctionShareFailed;

  /// Printed on the shared picture. States the method, and must not claim the content is true or false.
  ///
  /// In en, this message translates to:
  /// **'Verdict from cited sources, never from a model score.'**
  String get correctionCardFooter;

  /// On the shared picture, beside the Factify name: the day the sources were read. Shown in capitals.
  ///
  /// In en, this message translates to:
  /// **'Checked {date}'**
  String correctionChecked(String date);

  /// No description provided for @correctionMessageWith.
  ///
  /// In en, this message translates to:
  /// **'Message with it'**
  String get correctionMessageWith;

  /// No description provided for @correctionMessageHint.
  ///
  /// In en, this message translates to:
  /// **'A polite note makes it easier to correct family and friends.'**
  String get correctionMessageHint;

  /// No description provided for @correctionMessageLabel.
  ///
  /// In en, this message translates to:
  /// **'The message sent with the picture'**
  String get correctionMessageLabel;

  /// Opens the note sent back to a family or friends chat. Warm and polite, never accusing. Must match the server's template in app/orchestration/correction.py.
  ///
  /// In en, this message translates to:
  /// **'Hi! I checked this before forwarding.'**
  String get correctionOpening;

  /// No description provided for @correctionSaysFalse.
  ///
  /// In en, this message translates to:
  /// **'Factify says it\'s false'**
  String get correctionSaysFalse;

  /// No description provided for @correctionSaysMisleading.
  ///
  /// In en, this message translates to:
  /// **'Factify says it\'s misleading'**
  String get correctionSaysMisleading;

  /// No description provided for @correctionSaysPartlyTrue.
  ///
  /// In en, this message translates to:
  /// **'Factify says it\'s only partly true'**
  String get correctionSaysPartlyTrue;

  /// No description provided for @correctionSaysTrue.
  ///
  /// In en, this message translates to:
  /// **'Factify says it\'s true'**
  String get correctionSaysTrue;

  /// The note for an Unconfirmed result. Must never say the content is false.
  ///
  /// In en, this message translates to:
  /// **'Hi! I tried to check this before forwarding. Factify couldn\'t find reliable sources confirming it yet, so it may be best not to forward it for now.'**
  String get correctionUnconfirmedMessage;

  /// No description provided for @failureTimeout.
  ///
  /// In en, this message translates to:
  /// **'Factify is taking longer than usual. Try again in a moment.'**
  String get failureTimeout;

  /// No description provided for @failureUnreachable.
  ///
  /// In en, this message translates to:
  /// **'Could not reach Factify. Check your connection and try again.'**
  String get failureUnreachable;

  /// No description provided for @failureInterrupted.
  ///
  /// In en, this message translates to:
  /// **'The connection to Factify was interrupted. Try again.'**
  String get failureInterrupted;

  /// No description provided for @failureUnreadableFile.
  ///
  /// In en, this message translates to:
  /// **'That file could not be read from this phone.'**
  String get failureUnreadableFile;

  /// No description provided for @failureBadReply.
  ///
  /// In en, this message translates to:
  /// **'Factify sent a reply this app could not read.'**
  String get failureBadReply;

  /// No description provided for @failureInvalidInput.
  ///
  /// In en, this message translates to:
  /// **'That input could not be read.'**
  String get failureInvalidInput;

  /// No description provided for @failureTooLarge.
  ///
  /// In en, this message translates to:
  /// **'That file is too large to check.'**
  String get failureTooLarge;

  /// No description provided for @failureRateLimited.
  ///
  /// In en, this message translates to:
  /// **'Too many requests at once. Wait a minute, then try again.'**
  String get failureRateLimited;

  /// No description provided for @failureUnavailable.
  ///
  /// In en, this message translates to:
  /// **'Verification is not available right now.'**
  String get failureUnavailable;

  /// No description provided for @failureGeneric.
  ///
  /// In en, this message translates to:
  /// **'Factify could not complete that check.'**
  String get failureGeneric;

  /// The verdict, in the words a person would use. Shown only with cited sources.
  ///
  /// In en, this message translates to:
  /// **'True'**
  String get headlineSafeToShare;

  /// No description provided for @subheadSafeToShare.
  ///
  /// In en, this message translates to:
  /// **'Reliable sources confirm this'**
  String get subheadSafeToShare;

  /// No description provided for @headlineShareWithContext.
  ///
  /// In en, this message translates to:
  /// **'Misleading'**
  String get headlineShareWithContext;

  /// No description provided for @subheadShareWithContext.
  ///
  /// In en, this message translates to:
  /// **'True in part, but missing important context'**
  String get subheadShareWithContext;

  /// No description provided for @headlineShareWithCorrection.
  ///
  /// In en, this message translates to:
  /// **'Partly true'**
  String get headlineShareWithCorrection;

  /// No description provided for @subheadShareWithCorrection.
  ///
  /// In en, this message translates to:
  /// **'Some of this is right, some of it isn\'t'**
  String get subheadShareWithCorrection;

  /// No description provided for @headlineDoNotShare.
  ///
  /// In en, this message translates to:
  /// **'False'**
  String get headlineDoNotShare;

  /// No description provided for @subheadDoNotShare.
  ///
  /// In en, this message translates to:
  /// **'Reliable sources show this is false'**
  String get subheadDoNotShare;

  /// No description provided for @headlineWaitAndRecheck.
  ///
  /// In en, this message translates to:
  /// **'Unconfirmed'**
  String get headlineWaitAndRecheck;

  /// No description provided for @subheadWaitAndRecheck.
  ///
  /// In en, this message translates to:
  /// **'Too recent to confirm yet'**
  String get subheadWaitAndRecheck;

  /// Abstention. Neutral wording: not deciding is the designed answer, not a failure.
  ///
  /// In en, this message translates to:
  /// **'Unconfirmed'**
  String get headlineSendToReview;

  /// No description provided for @subheadSendToReview.
  ///
  /// In en, this message translates to:
  /// **'We couldn\'t confirm or rule this out yet'**
  String get subheadSendToReview;

  /// Shown only when the interface is not in English and some claim reasons arrive in English (claims made in English).
  ///
  /// In en, this message translates to:
  /// **'Some details below are shown in English for now.'**
  String get englishOnlyNote;

  /// No description provided for @whyNoVerdict.
  ///
  /// In en, this message translates to:
  /// **'Why unconfirmed?'**
  String get whyNoVerdict;

  /// No description provided for @shareCorrection.
  ///
  /// In en, this message translates to:
  /// **'Share correction'**
  String get shareCorrection;

  /// No description provided for @report.
  ///
  /// In en, this message translates to:
  /// **'Report wrong result'**
  String get report;

  /// No description provided for @reporting.
  ///
  /// In en, this message translates to:
  /// **'Reporting…'**
  String get reporting;

  /// No description provided for @evidenceTitle.
  ///
  /// In en, this message translates to:
  /// **'Sources'**
  String get evidenceTitle;

  /// One term of the explainable strength score, named for a reader.
  ///
  /// In en, this message translates to:
  /// **'{name, select, tier_composition{Evidence tiers} independent_origins{Independent origins} temporal_confidence{Dating} source_transparency{Publisher transparency} conflict_penalty{Conflicting evidence} other{{name}}}'**
  String strengthComponent(String name);

  /// No description provided for @tierLabel.
  ///
  /// In en, this message translates to:
  /// **'{tier, select, A{Signed content credential} B{Dated source} C{Published fact-check} other{Corroboration}}'**
  String tierLabel(String tier);

  /// No description provided for @directionLabel.
  ///
  /// In en, this message translates to:
  /// **'{direction, select, supports{Supports} contradicts{Contradicts} risk_signal{Risk signal} other{Context}}'**
  String directionLabel(String direction);

  /// No description provided for @matchBasis.
  ///
  /// In en, this message translates to:
  /// **'{metric} {value} (threshold {threshold})'**
  String matchBasis(String metric, String value, String threshold);

  /// No description provided for @openSource.
  ///
  /// In en, this message translates to:
  /// **'Open source'**
  String get openSource;

  /// No description provided for @historyCardTitle.
  ///
  /// In en, this message translates to:
  /// **'History'**
  String get historyCardTitle;

  /// No description provided for @recurrenceCaptions.
  ///
  /// In en, this message translates to:
  /// **'The same media has carried {count} different captions. An authentic photograph does not usually acquire several mutually exclusive stories.'**
  String recurrenceCaptions(int count);

  /// No description provided for @contentCredentials.
  ///
  /// In en, this message translates to:
  /// **'Content credentials'**
  String get contentCredentials;

  /// No description provided for @notCheckedTitle.
  ///
  /// In en, this message translates to:
  /// **'What could not be checked'**
  String get notCheckedTitle;

  /// No description provided for @limitsTitle.
  ///
  /// In en, this message translates to:
  /// **'What Factify cannot establish'**
  String get limitsTitle;

  /// No description provided for @limitAi.
  ///
  /// In en, this message translates to:
  /// **'Whether an image or video was generated by AI. No detector is reliable enough to say so, and we do not pretend otherwise.'**
  String get limitAi;

  /// No description provided for @limitUnreported.
  ///
  /// In en, this message translates to:
  /// **'Whether something unreported is false. Absence of coverage is not evidence either way.'**
  String get limitUnreported;

  /// No description provided for @limitPrivate.
  ///
  /// In en, this message translates to:
  /// **'Anything about private content, or claims no published source has addressed.'**
  String get limitPrivate;

  /// No description provided for @limitIntent.
  ///
  /// In en, this message translates to:
  /// **'Intent. We can show what a source said and when, not why someone shared it.'**
  String get limitIntent;

  /// No description provided for @caseLabel.
  ///
  /// In en, this message translates to:
  /// **'Case {caseId}'**
  String caseLabel(String caseId);

  /// No description provided for @checkedIn.
  ///
  /// In en, this message translates to:
  /// **'Checked in {ms} ms'**
  String checkedIn(int ms);

  /// No description provided for @verifyResult.
  ///
  /// In en, this message translates to:
  /// **'Verify this result'**
  String get verifyResult;

  /// No description provided for @receiptChecking.
  ///
  /// In en, this message translates to:
  /// **'Checking the receipt'**
  String get receiptChecking;

  /// No description provided for @receiptVerified.
  ///
  /// In en, this message translates to:
  /// **'Receipt verified. The evidence behind this result is unchanged since it was signed.'**
  String get receiptVerified;

  /// Shown when the digest does not match. The server also sends a reason, which is developer English and is not shown.
  ///
  /// In en, this message translates to:
  /// **'Receipt did not verify. The stored evidence no longer matches what was signed.'**
  String get receiptFailed;

  /// No description provided for @receiptMissing.
  ///
  /// In en, this message translates to:
  /// **'No receipt was issued for this result.'**
  String get receiptMissing;

  /// Permanent exclusion header. Must stay visible and must keep saying the signals are not used in the verdict.
  ///
  /// In en, this message translates to:
  /// **'Forensic signals - shown for transparency. These are not used in the verdict and cannot change it.'**
  String get advisoryHeader;

  /// No description provided for @advisoryCount.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 signal} other{{count} signals}}'**
  String advisoryCount(int count);

  /// No description provided for @advisoryFooter.
  ///
  /// In en, this message translates to:
  /// **'None of these can establish that content is authentic or fabricated. The verdict above is based only on cited sources.'**
  String get advisoryFooter;

  /// No description provided for @advisoryRowExcluded.
  ///
  /// In en, this message translates to:
  /// **'Forensic signal - not used in this verdict.'**
  String get advisoryRowExcluded;

  /// Heads the teaching-mode line. Techniques are named only for claims a cited source contradicted or recontextualised, and never claim anything is true.
  ///
  /// In en, this message translates to:
  /// **'How posts like this mislead'**
  String get techniqueLabel;

  /// No description provided for @techniqueRecycledMediaTitle.
  ///
  /// In en, this message translates to:
  /// **'Recycled picture'**
  String get techniqueRecycledMediaTitle;

  /// No description provided for @techniqueRecycledMediaBody.
  ///
  /// In en, this message translates to:
  /// **'A picture published earlier, shared again as if it showed something new. Before trusting a photo, look for when it first appeared.'**
  String get techniqueRecycledMediaBody;

  /// No description provided for @techniqueMissingContextTitle.
  ///
  /// In en, this message translates to:
  /// **'Missing context'**
  String get techniqueMissingContextTitle;

  /// No description provided for @techniqueMissingContextBody.
  ///
  /// In en, this message translates to:
  /// **'Published material framed to suggest something its sources do not say. Ask what the post leaves out.'**
  String get techniqueMissingContextBody;

  /// No description provided for @techniqueMisattributedQuoteTitle.
  ///
  /// In en, this message translates to:
  /// **'Words put in someone\'s mouth'**
  String get techniqueMisattributedQuoteTitle;

  /// No description provided for @techniqueMisattributedQuoteBody.
  ///
  /// In en, this message translates to:
  /// **'A quote credited to someone that published sources do not record them saying. Look for the original speech or statement.'**
  String get techniqueMisattributedQuoteBody;

  /// No description provided for @techniqueTwistedNumberTitle.
  ///
  /// In en, this message translates to:
  /// **'Twisted number'**
  String get techniqueTwistedNumberTitle;

  /// No description provided for @techniqueTwistedNumberBody.
  ///
  /// In en, this message translates to:
  /// **'A figure changed, or taken from a source that says something different. Find the number in its original source.'**
  String get techniqueTwistedNumberBody;

  /// No description provided for @techniqueWrongIdentityTitle.
  ///
  /// In en, this message translates to:
  /// **'Wrong label'**
  String get techniqueWrongIdentityTitle;

  /// No description provided for @techniqueWrongIdentityBody.
  ///
  /// In en, this message translates to:
  /// **'A person or place presented as someone or somewhere else. Check names and places against a dated source.'**
  String get techniqueWrongIdentityBody;

  /// No description provided for @timelineTitle.
  ///
  /// In en, this message translates to:
  /// **'Timeline'**
  String get timelineTitle;

  /// No description provided for @timelineFirstChecked.
  ///
  /// In en, this message translates to:
  /// **'First checked by Factify'**
  String get timelineFirstChecked;

  /// No description provided for @timelineRetrieved.
  ///
  /// In en, this message translates to:
  /// **'Evidence gathered for this result'**
  String get timelineRetrieved;

  /// No description provided for @inputAnchorLabel.
  ///
  /// In en, this message translates to:
  /// **'Where your submission says this'**
  String get inputAnchorLabel;

  /// No description provided for @inputAnchorPage.
  ///
  /// In en, this message translates to:
  /// **'Page {page}'**
  String inputAnchorPage(int page);

  /// No description provided for @inputAnchorMoment.
  ///
  /// In en, this message translates to:
  /// **'At {seconds} s in the video'**
  String inputAnchorMoment(int seconds);

  /// No description provided for @mediaMatchYours.
  ///
  /// In en, this message translates to:
  /// **'Your picture'**
  String get mediaMatchYours;

  /// No description provided for @mediaMatchEarlier.
  ///
  /// In en, this message translates to:
  /// **'Matches a picture published earlier'**
  String get mediaMatchEarlier;

  /// No description provided for @uploading.
  ///
  /// In en, this message translates to:
  /// **'Uploading {percent}%'**
  String uploading(int percent);

  /// Shown when the clipboard holds text. The text itself is not read until the person taps.
  ///
  /// In en, this message translates to:
  /// **'You have text copied. Check it?'**
  String get clipboardOffer;

  /// How sure the verdict is, from 50 to 97. Shown only with True, False or Misleading.
  ///
  /// In en, this message translates to:
  /// **'{value}% confidence'**
  String confidence(int value);

  /// No description provided for @unconfirmedBody.
  ///
  /// In en, this message translates to:
  /// **'We couldn\'t find enough reliable sources that address this directly. Treat it with caution until it\'s confirmed.'**
  String get unconfirmedBody;

  /// No description provided for @sourcesTitle.
  ///
  /// In en, this message translates to:
  /// **'Sources'**
  String get sourcesTitle;

  /// No description provided for @sourceConfirms.
  ///
  /// In en, this message translates to:
  /// **'Confirms'**
  String get sourceConfirms;

  /// No description provided for @sourceRefutes.
  ///
  /// In en, this message translates to:
  /// **'Refutes'**
  String get sourceRefutes;

  /// How credible a publisher is, from the curated source list.
  ///
  /// In en, this message translates to:
  /// **'{level, select, HIGH{Highly credible} MEDIUM{Credible} other{Source}}'**
  String credibility(String level);

  /// No description provided for @howWeCheckedTitle.
  ///
  /// In en, this message translates to:
  /// **'How we checked'**
  String get howWeCheckedTitle;

  /// No description provided for @howWeCheckedBody.
  ///
  /// In en, this message translates to:
  /// **'We searched trusted news outlets, fact-checkers and official sources, read each one, and kept only the ones that directly address this claim. The verdict comes from what those sources say, weighed by how credible they are.'**
  String get howWeCheckedBody;

  /// No description provided for @whatWeCheckedTitle.
  ///
  /// In en, this message translates to:
  /// **'What we checked'**
  String get whatWeCheckedTitle;

  /// When the sources behind this result were gathered.
  ///
  /// In en, this message translates to:
  /// **'Checked {time}'**
  String checkedAt(DateTime time);

  /// No description provided for @incompleteNote.
  ///
  /// In en, this message translates to:
  /// **'Some sources couldn\'t be checked in time, so this answer may be incomplete.'**
  String get incompleteNote;

  /// No description provided for @account.
  ///
  /// In en, this message translates to:
  /// **'Account'**
  String get account;

  /// No description provided for @signIn.
  ///
  /// In en, this message translates to:
  /// **'Sign in'**
  String get signIn;

  /// No description provided for @emailLabel.
  ///
  /// In en, this message translates to:
  /// **'Email'**
  String get emailLabel;

  /// No description provided for @orDivider.
  ///
  /// In en, this message translates to:
  /// **'or'**
  String get orDivider;

  /// No description provided for @continueWithGoogle.
  ///
  /// In en, this message translates to:
  /// **'Continue with Google'**
  String get continueWithGoogle;

  /// No description provided for @signInUnavailable.
  ///
  /// In en, this message translates to:
  /// **'Sign-in can\'t be reached right now. Check your connection and try again.'**
  String get signInUnavailable;

  /// No description provided for @signOut.
  ///
  /// In en, this message translates to:
  /// **'Sign out'**
  String get signOut;

  /// No description provided for @creditsTitle.
  ///
  /// In en, this message translates to:
  /// **'Credits'**
  String get creditsTitle;

  /// No description provided for @creditsLeft.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 credit left} other{{count} credits left}}'**
  String creditsLeft(int count);

  /// No description provided for @creditsUsed.
  ///
  /// In en, this message translates to:
  /// **'{count} used'**
  String creditsUsed(int count);

  /// No description provided for @creditCosts.
  ///
  /// In en, this message translates to:
  /// **'A check costs {check}'**
  String creditCosts(int check);

  /// No description provided for @editName.
  ///
  /// In en, this message translates to:
  /// **'Edit name'**
  String get editName;

  /// No description provided for @nameLabel.
  ///
  /// In en, this message translates to:
  /// **'Name'**
  String get nameLabel;

  /// No description provided for @save.
  ///
  /// In en, this message translates to:
  /// **'Save'**
  String get save;

  /// No description provided for @cancel.
  ///
  /// In en, this message translates to:
  /// **'Cancel'**
  String get cancel;

  /// No description provided for @failureSignedOut.
  ///
  /// In en, this message translates to:
  /// **'Your sign-in has ended. Sign in again from your account.'**
  String get failureSignedOut;

  /// No description provided for @failureOutOfCredits.
  ///
  /// In en, this message translates to:
  /// **'You\'re out of credits for now.'**
  String get failureOutOfCredits;

  /// No description provided for @authNetwork.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t reach sign-in. Check your connection.'**
  String get authNetwork;

  /// No description provided for @authTooMany.
  ///
  /// In en, this message translates to:
  /// **'Too many tries. Wait a minute and try again.'**
  String get authTooMany;

  /// No description provided for @authGeneric.
  ///
  /// In en, this message translates to:
  /// **'Sign-in didn\'t work. Try again.'**
  String get authGeneric;

  /// No description provided for @claimsProgress.
  ///
  /// In en, this message translates to:
  /// **'{done} of {total} claims checked'**
  String claimsProgress(int done, int total);

  /// No description provided for @checkTooSlow.
  ///
  /// In en, this message translates to:
  /// **'This check is taking longer than usual. Try Check again in a minute.'**
  String get checkTooSlow;

  /// No description provided for @imageKind.
  ///
  /// In en, this message translates to:
  /// **'{kind, select, NEWS_ARTICLE{News article} SOCIAL_POST{Social media post} CHAT_MESSAGE{Chat forward} TV_GRAPHIC{TV news graphic} POSTER{Poster} DOCUMENT{Document} PHOTO{Photo} MEME{Meme} other{Picture}}'**
  String imageKind(String kind);

  /// No description provided for @imageNoText.
  ///
  /// In en, this message translates to:
  /// **'We found no text in this picture, so we checked the picture itself.'**
  String get imageNoText;

  /// No description provided for @imageShowAllText.
  ///
  /// In en, this message translates to:
  /// **'Show all the text'**
  String get imageShowAllText;

  /// No description provided for @imageShowLessText.
  ///
  /// In en, this message translates to:
  /// **'Show less'**
  String get imageShowLessText;

  /// No description provided for @splashTagline.
  ///
  /// In en, this message translates to:
  /// **'Check before you share'**
  String get splashTagline;

  /// No description provided for @welcomeTitle.
  ///
  /// In en, this message translates to:
  /// **'Know what\'s true before you share it'**
  String get welcomeTitle;

  /// No description provided for @welcomeBody.
  ///
  /// In en, this message translates to:
  /// **'Factify checks news, forwards, pictures and documents against reliable sources, and shows you every source it used.'**
  String get welcomeBody;

  /// No description provided for @welcomePointSources.
  ///
  /// In en, this message translates to:
  /// **'Every answer comes with its sources'**
  String get welcomePointSources;

  /// No description provided for @tabHistory.
  ///
  /// In en, this message translates to:
  /// **'History'**
  String get tabHistory;

  /// No description provided for @tabProfile.
  ///
  /// In en, this message translates to:
  /// **'Profile'**
  String get tabProfile;

  /// No description provided for @homeGreeting.
  ///
  /// In en, this message translates to:
  /// **'Hi, {name}'**
  String homeGreeting(String name);

  /// No description provided for @homeGreetingGuest.
  ///
  /// In en, this message translates to:
  /// **'Hi there'**
  String get homeGreetingGuest;

  /// No description provided for @homeTitle.
  ///
  /// In en, this message translates to:
  /// **'What would you like to check?'**
  String get homeTitle;

  /// No description provided for @inputTypeText.
  ///
  /// In en, this message translates to:
  /// **'Text or link'**
  String get inputTypeText;

  /// No description provided for @inputTypeImage.
  ///
  /// In en, this message translates to:
  /// **'Image'**
  String get inputTypeImage;

  /// No description provided for @inputTypePdf.
  ///
  /// In en, this message translates to:
  /// **'PDF'**
  String get inputTypePdf;

  /// No description provided for @inputTextHint.
  ///
  /// In en, this message translates to:
  /// **'Paste a message, a claim or a news link'**
  String get inputTextHint;

  /// No description provided for @inputLinkDetected.
  ///
  /// In en, this message translates to:
  /// **'Link found. We\'ll read the page and check it.'**
  String get inputLinkDetected;

  /// No description provided for @inputLocked.
  ///
  /// In en, this message translates to:
  /// **'Remove what you\'ve added to switch to another type.'**
  String get inputLocked;

  /// No description provided for @removeInput.
  ///
  /// In en, this message translates to:
  /// **'Remove'**
  String get removeInput;

  /// No description provided for @pickImageTitle.
  ///
  /// In en, this message translates to:
  /// **'Add a picture or video'**
  String get pickImageTitle;

  /// No description provided for @pickImageBody.
  ///
  /// In en, this message translates to:
  /// **'A screenshot, a WhatsApp forward, a photo or a video. We read what is in it and check it.'**
  String get pickImageBody;

  /// No description provided for @pickPdfTitle.
  ///
  /// In en, this message translates to:
  /// **'Add a PDF'**
  String get pickPdfTitle;

  /// No description provided for @pickPdfBody.
  ///
  /// In en, this message translates to:
  /// **'A circular, a notice or any document. We read it and check what it claims.'**
  String get pickPdfBody;

  /// No description provided for @choosePdf.
  ///
  /// In en, this message translates to:
  /// **'Choose a PDF'**
  String get choosePdf;

  /// No description provided for @notAPdf.
  ///
  /// In en, this message translates to:
  /// **'That file isn\'t a PDF. Choose a PDF, or switch to Image.'**
  String get notAPdf;

  /// No description provided for @checkNow.
  ///
  /// In en, this message translates to:
  /// **'Check now'**
  String get checkNow;

  /// No description provided for @checkingOf.
  ///
  /// In en, this message translates to:
  /// **'Checking'**
  String get checkingOf;

  /// No description provided for @checkingCancel.
  ///
  /// In en, this message translates to:
  /// **'Stop waiting'**
  String get checkingCancel;

  /// No description provided for @checkingFailedTitle.
  ///
  /// In en, this message translates to:
  /// **'The check didn\'t finish'**
  String get checkingFailedTitle;

  /// No description provided for @backToHome.
  ///
  /// In en, this message translates to:
  /// **'Back to home'**
  String get backToHome;

  /// No description provided for @resultTitle.
  ///
  /// In en, this message translates to:
  /// **'Result'**
  String get resultTitle;

  /// No description provided for @newCheck.
  ///
  /// In en, this message translates to:
  /// **'New check'**
  String get newCheck;

  /// No description provided for @historyEmptyTitle.
  ///
  /// In en, this message translates to:
  /// **'No checks yet'**
  String get historyEmptyTitle;

  /// No description provided for @historyEmptyBody.
  ///
  /// In en, this message translates to:
  /// **'Everything you check is listed here, with its sources, so you can come back to it.'**
  String get historyEmptyBody;

  /// No description provided for @historyToday.
  ///
  /// In en, this message translates to:
  /// **'Today'**
  String get historyToday;

  /// No description provided for @historyYesterday.
  ///
  /// In en, this message translates to:
  /// **'Yesterday'**
  String get historyYesterday;

  /// No description provided for @historyClear.
  ///
  /// In en, this message translates to:
  /// **'Clear history'**
  String get historyClear;

  /// No description provided for @historyClearConfirm.
  ///
  /// In en, this message translates to:
  /// **'Delete every saved check from this phone?'**
  String get historyClearConfirm;

  /// No description provided for @historyDelete.
  ///
  /// In en, this message translates to:
  /// **'Delete'**
  String get historyDelete;

  /// No description provided for @historyFilterAll.
  ///
  /// In en, this message translates to:
  /// **'All'**
  String get historyFilterAll;

  /// No description provided for @historyStoredNote.
  ///
  /// In en, this message translates to:
  /// **'This list is kept only on this phone. What you check is stored on our server without your name. Swipe a check left to remove it from this list.'**
  String get historyStoredNote;

  /// No description provided for @historySources.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =0{No sources} =1{1 source} other{{count} sources}}'**
  String historySources(int count);

  /// No description provided for @profileTitle.
  ///
  /// In en, this message translates to:
  /// **'Profile'**
  String get profileTitle;

  /// No description provided for @guestTitle.
  ///
  /// In en, this message translates to:
  /// **'You\'re not signed in'**
  String get guestTitle;

  /// No description provided for @guestBody.
  ///
  /// In en, this message translates to:
  /// **'Sign in to check news and keep your credits.'**
  String get guestBody;

  /// No description provided for @signInOrCreate.
  ///
  /// In en, this message translates to:
  /// **'Sign in or create an account'**
  String get signInOrCreate;

  /// No description provided for @signedInWith.
  ///
  /// In en, this message translates to:
  /// **'{method, select, google{Signed in with Google} other{Signed in with email}}'**
  String signedInWith(String method);

  /// No description provided for @profileJoined.
  ///
  /// In en, this message translates to:
  /// **'Member since'**
  String get profileJoined;

  /// No description provided for @settingsTitle.
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get settingsTitle;

  /// No description provided for @settingLanguage.
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get settingLanguage;

  /// No description provided for @settingHistory.
  ///
  /// In en, this message translates to:
  /// **'Saved checks'**
  String get settingHistory;

  /// No description provided for @aboutTitle.
  ///
  /// In en, this message translates to:
  /// **'About Factify'**
  String get aboutTitle;

  /// No description provided for @aboutBody.
  ///
  /// In en, this message translates to:
  /// **'Factify checks what you share against reliable sources and always shows them. When the sources don\'t settle it, it says Unconfirmed rather than guess.'**
  String get aboutBody;

  /// No description provided for @done.
  ///
  /// In en, this message translates to:
  /// **'Done'**
  String get done;

  /// No description provided for @modeSignIn.
  ///
  /// In en, this message translates to:
  /// **'Sign in'**
  String get modeSignIn;

  /// No description provided for @welcomeBackTitle.
  ///
  /// In en, this message translates to:
  /// **'Welcome back'**
  String get welcomeBackTitle;

  /// No description provided for @welcomeBackBody.
  ///
  /// In en, this message translates to:
  /// **'Sign in with your email and password, or with Google.'**
  String get welcomeBackBody;

  /// No description provided for @passwordLabel.
  ///
  /// In en, this message translates to:
  /// **'Password'**
  String get passwordLabel;

  /// No description provided for @confirmPasswordLabel.
  ///
  /// In en, this message translates to:
  /// **'Confirm password'**
  String get confirmPasswordLabel;

  /// No description provided for @passwordHint.
  ///
  /// In en, this message translates to:
  /// **'At least {min} characters'**
  String passwordHint(int min);

  /// No description provided for @showPassword.
  ///
  /// In en, this message translates to:
  /// **'Show password'**
  String get showPassword;

  /// No description provided for @hidePassword.
  ///
  /// In en, this message translates to:
  /// **'Hide password'**
  String get hidePassword;

  /// No description provided for @passwordsDontMatch.
  ///
  /// In en, this message translates to:
  /// **'The passwords don\'t match.'**
  String get passwordsDontMatch;

  /// No description provided for @createAccountButton.
  ///
  /// In en, this message translates to:
  /// **'Create account'**
  String get createAccountButton;

  /// No description provided for @signInButton.
  ///
  /// In en, this message translates to:
  /// **'Sign in'**
  String get signInButton;

  /// No description provided for @authInvalidEmail.
  ///
  /// In en, this message translates to:
  /// **'That doesn\'t look like an email address.'**
  String get authInvalidEmail;

  /// No description provided for @authWeakPassword.
  ///
  /// In en, this message translates to:
  /// **'Use a password of at least {min} characters.'**
  String authWeakPassword(int min);

  /// No description provided for @authEmailTaken.
  ///
  /// In en, this message translates to:
  /// **'There\'s already an account with this email. Sign in instead.'**
  String get authEmailTaken;

  /// No description provided for @authWrongCredentials.
  ///
  /// In en, this message translates to:
  /// **'That email and password don\'t match an account.'**
  String get authWrongCredentials;

  /// No description provided for @authUseGoogle.
  ///
  /// In en, this message translates to:
  /// **'This account was made with Google. Use Continue with Google.'**
  String get authUseGoogle;

  /// No description provided for @authGoogleFailed.
  ///
  /// In en, this message translates to:
  /// **'Google sign-in didn\'t finish. Try again.'**
  String get authGoogleFailed;

  /// No description provided for @authGoogleUnavailable.
  ///
  /// In en, this message translates to:
  /// **'Google sign-in isn\'t set up on this server yet. Use your email and a password.'**
  String get authGoogleUnavailable;

  /// Names a picture being checked before anything is known about it; its file name is never shown.
  ///
  /// In en, this message translates to:
  /// **'Your picture'**
  String get yourPicture;

  /// No description provided for @headlineNothingToCheck.
  ///
  /// In en, this message translates to:
  /// **'Nothing to fact-check'**
  String get headlineNothingToCheck;

  /// No description provided for @subheadNothingToCheck.
  ///
  /// In en, this message translates to:
  /// **'No claim found in it'**
  String get subheadNothingToCheck;

  /// No description provided for @nothingToCheckPicture.
  ///
  /// In en, this message translates to:
  /// **'We read this picture and found no claim in it that can be checked - no news, figure or announcement, just an image. There\'s nothing here to confirm or rule out.'**
  String get nothingToCheckPicture;

  /// No description provided for @nothingToCheckVideo.
  ///
  /// In en, this message translates to:
  /// **'We checked this video\'s frames and found no claim in them that can be checked - no news, figure or announcement. There\'s nothing here to confirm or rule out.'**
  String get nothingToCheckVideo;

  /// No description provided for @nothingToCheckText.
  ///
  /// In en, this message translates to:
  /// **'We didn\'t find a factual claim in this - it reads as opinion, a joke or conversation, so there\'s nothing here to confirm or rule out.'**
  String get nothingToCheckText;

  /// No description provided for @nothingToCheckAiPicture.
  ///
  /// In en, this message translates to:
  /// **'But our AI-picture check says this picture was likely made by AI. See the picture checks below.'**
  String get nothingToCheckAiPicture;

  /// No description provided for @nothingToCheckAiVideo.
  ///
  /// In en, this message translates to:
  /// **'But our checks say this video was likely made by AI. See the video checks below.'**
  String get nothingToCheckAiVideo;

  /// No description provided for @nothingToCheckAiDeclared.
  ///
  /// In en, this message translates to:
  /// **'But its content credentials say it was made with an AI tool. See the checks below.'**
  String get nothingToCheckAiDeclared;

  /// No description provided for @nothingToCheckVoice.
  ///
  /// In en, this message translates to:
  /// **'But our checks say the voice in this video was likely made by a computer, not recorded from a person. See the video checks below.'**
  String get nothingToCheckVoice;

  /// No description provided for @nothingToCheckVoiceToo.
  ///
  /// In en, this message translates to:
  /// **'Its voice was also likely made by a computer.'**
  String get nothingToCheckVoiceToo;

  /// No description provided for @nothingToCheckFaceSwap.
  ///
  /// In en, this message translates to:
  /// **'But our checks say a face in this video was likely swapped or changed by AI. See the video checks below.'**
  String get nothingToCheckFaceSwap;

  /// No description provided for @nothingToCheckFaceSwapToo.
  ///
  /// In en, this message translates to:
  /// **'A face in it was also likely swapped or changed by AI.'**
  String get nothingToCheckFaceSwapToo;

  /// No description provided for @searchUnavailableNote.
  ///
  /// In en, this message translates to:
  /// **'Our news search couldn\'t be reached, so this wasn\'t checked against news reports. Tap Check again in a little while.'**
  String get searchUnavailableNote;

  /// No description provided for @claimSearchUnavailable.
  ///
  /// In en, this message translates to:
  /// **'Our news search couldn\'t be reached, so no news reports were looked at for this. It isn\'t the same as finding nothing.'**
  String get claimSearchUnavailable;

  /// No description provided for @pasteCopiedText.
  ///
  /// In en, this message translates to:
  /// **'Paste copied text'**
  String get pasteCopiedText;

  /// No description provided for @shareFromWhatsApp.
  ///
  /// In en, this message translates to:
  /// **'Or share from WhatsApp'**
  String get shareFromWhatsApp;

  /// No description provided for @checkTakes.
  ///
  /// In en, this message translates to:
  /// **'Every claim is checked · usually 1–2 minutes'**
  String get checkTakes;

  /// No description provided for @recentTitle.
  ///
  /// In en, this message translates to:
  /// **'Recent'**
  String get recentTitle;

  /// No description provided for @seeAll.
  ///
  /// In en, this message translates to:
  /// **'See all'**
  String get seeAll;

  /// No description provided for @historySearchHint.
  ///
  /// In en, this message translates to:
  /// **'Search past checks'**
  String get historySearchHint;

  /// No description provided for @historyWeekRange.
  ///
  /// In en, this message translates to:
  /// **'This week · {range}'**
  String historyWeekRange(String range);

  /// No description provided for @historyChecksUnit.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{check} other{checks}}'**
  String historyChecksUnit(int count);

  /// No description provided for @historyChecksCount.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 check} other{{count} checks}}'**
  String historyChecksCount(int count);

  /// No description provided for @historyBusiest.
  ///
  /// In en, this message translates to:
  /// **'Busiest: {days}'**
  String historyBusiest(String days);

  /// No description provided for @historyDaysJoin.
  ///
  /// In en, this message translates to:
  /// **'{first} and {second}'**
  String historyDaysJoin(String first, String second);

  /// No description provided for @historyStopped.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 check this week came back false, misleading or partly true.} other{{count} checks this week came back false, misleading or partly true.}}'**
  String historyStopped(int count);

  /// No description provided for @historyNoResults.
  ///
  /// In en, this message translates to:
  /// **'No checks match this search.'**
  String get historyNoResults;

  /// No description provided for @switchLanguage.
  ///
  /// In en, this message translates to:
  /// **'Switch language'**
  String get switchLanguage;

  /// No description provided for @verdictOverline.
  ///
  /// In en, this message translates to:
  /// **'VERDICT'**
  String get verdictOverline;

  /// No description provided for @confidenceChip.
  ///
  /// In en, this message translates to:
  /// **'confidence'**
  String get confidenceChip;

  /// No description provided for @whyChip.
  ///
  /// In en, this message translates to:
  /// **'Why?'**
  String get whyChip;

  /// No description provided for @checkedEarlierOn.
  ///
  /// In en, this message translates to:
  /// **'Checked earlier · reused from {date}'**
  String checkedEarlierOn(String date);

  /// No description provided for @whatWeCheckedKind.
  ///
  /// In en, this message translates to:
  /// **'What we checked · {kind}'**
  String whatWeCheckedKind(String kind);

  /// No description provided for @kindText.
  ///
  /// In en, this message translates to:
  /// **'Text'**
  String get kindText;

  /// No description provided for @kindLink.
  ///
  /// In en, this message translates to:
  /// **'Link'**
  String get kindLink;

  /// No description provided for @kindImage.
  ///
  /// In en, this message translates to:
  /// **'Image'**
  String get kindImage;

  /// No description provided for @kindPdf.
  ///
  /// In en, this message translates to:
  /// **'PDF'**
  String get kindPdf;

  /// No description provided for @claimCount.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 claim} other{{count} claims}}'**
  String claimCount(int count);

  /// No description provided for @claimStateSupported.
  ///
  /// In en, this message translates to:
  /// **'Supported'**
  String get claimStateSupported;

  /// No description provided for @claimStateContradicted.
  ///
  /// In en, this message translates to:
  /// **'Contradicted'**
  String get claimStateContradicted;

  /// No description provided for @claimStateMissingContext.
  ///
  /// In en, this message translates to:
  /// **'Missing context'**
  String get claimStateMissingContext;

  /// No description provided for @claimStatePartlyTrue.
  ///
  /// In en, this message translates to:
  /// **'Partly true'**
  String get claimStatePartlyTrue;

  /// No description provided for @claimStateUnconfirmed.
  ///
  /// In en, this message translates to:
  /// **'Unconfirmed'**
  String get claimStateUnconfirmed;

  /// Under a claim made in another language: the claim as one self-contained English sentence.
  ///
  /// In en, this message translates to:
  /// **'In full: {text}'**
  String claimInFull(String text);

  /// No description provided for @rightWrongTitle.
  ///
  /// In en, this message translates to:
  /// **'What\'s right, what\'s wrong'**
  String get rightWrongTitle;

  /// No description provided for @rightWrongRight.
  ///
  /// In en, this message translates to:
  /// **'Right'**
  String get rightWrongRight;

  /// No description provided for @rightWrongWrong.
  ///
  /// In en, this message translates to:
  /// **'Wrong'**
  String get rightWrongWrong;

  /// No description provided for @rightWrongPartly.
  ///
  /// In en, this message translates to:
  /// **'Only partly right'**
  String get rightWrongPartly;

  /// No description provided for @rightWrongContext.
  ///
  /// In en, this message translates to:
  /// **'Missing context'**
  String get rightWrongContext;

  /// No description provided for @rightWrongUnconfirmed.
  ///
  /// In en, this message translates to:
  /// **'Not confirmed'**
  String get rightWrongUnconfirmed;

  /// No description provided for @sourcesReport.
  ///
  /// In en, this message translates to:
  /// **'What sources actually report'**
  String get sourcesReport;

  /// No description provided for @claimStateCount.
  ///
  /// In en, this message translates to:
  /// **'{count} {state}'**
  String claimStateCount(int count, String state);

  /// No description provided for @tapToRead.
  ///
  /// In en, this message translates to:
  /// **'Tap to read'**
  String get tapToRead;

  /// No description provided for @readSource.
  ///
  /// In en, this message translates to:
  /// **'Read'**
  String get readSource;

  /// No description provided for @directionShort.
  ///
  /// In en, this message translates to:
  /// **'{direction, select, supports{Supports} contradicts{Refutes} other{Context}}'**
  String directionShort(String direction);

  /// No description provided for @noSourceTitle.
  ///
  /// In en, this message translates to:
  /// **'No citable source was found'**
  String get noSourceTitle;

  /// No description provided for @noSourceBody.
  ///
  /// In en, this message translates to:
  /// **'This does not mean the content is false. It means nothing we could cite either supports or contradicts it, so Factify did not decide.'**
  String get noSourceBody;

  /// No description provided for @receiptVerifiedTitle.
  ///
  /// In en, this message translates to:
  /// **'Receipt verified'**
  String get receiptVerifiedTitle;

  /// No description provided for @receiptVerifiedBody.
  ///
  /// In en, this message translates to:
  /// **'The evidence is unchanged since it was signed'**
  String get receiptVerifiedBody;

  /// No description provided for @receiptFailedTitle.
  ///
  /// In en, this message translates to:
  /// **'Receipt did not verify'**
  String get receiptFailedTitle;

  /// No description provided for @receiptFailedBody.
  ///
  /// In en, this message translates to:
  /// **'The stored evidence no longer matches what was signed'**
  String get receiptFailedBody;

  /// No description provided for @shareResult.
  ///
  /// In en, this message translates to:
  /// **'Share result'**
  String get shareResult;

  /// No description provided for @whyOverline.
  ///
  /// In en, this message translates to:
  /// **'HOW SURE WE ARE'**
  String get whyOverline;

  /// No description provided for @whyTitle.
  ///
  /// In en, this message translates to:
  /// **'Why {value}% confidence'**
  String whyTitle(int value);

  /// No description provided for @whyBody.
  ///
  /// In en, this message translates to:
  /// **'Arithmetic on the cited sources: how many, how credible, and whether any disagree. Never a model score.'**
  String get whyBody;

  /// No description provided for @whyScaleLow.
  ///
  /// In en, this message translates to:
  /// **'50 · even'**
  String get whyScaleLow;

  /// No description provided for @whyScaleHigh.
  ///
  /// In en, this message translates to:
  /// **'97 · never certain'**
  String get whyScaleHigh;

  /// No description provided for @whyExcluded.
  ///
  /// In en, this message translates to:
  /// **'Excluded from this score: forensic signals.'**
  String get whyExcluded;

  /// No description provided for @whyNoVerdictOverline.
  ///
  /// In en, this message translates to:
  /// **'WHY NO VERDICT'**
  String get whyNoVerdictOverline;

  /// No description provided for @whyUncNotFalse.
  ///
  /// In en, this message translates to:
  /// **'Unconfirmed is not the same as false. Factify decides only when cited sources settle it.'**
  String get whyUncNotFalse;

  /// No description provided for @whyUncLater.
  ///
  /// In en, this message translates to:
  /// **'New claims often get covered within a day or two. Check again later.'**
  String get whyUncLater;

  /// No description provided for @gotIt.
  ///
  /// In en, this message translates to:
  /// **'Got it'**
  String get gotIt;

  /// No description provided for @mediaYourPicture.
  ///
  /// In en, this message translates to:
  /// **'YOUR PICTURE'**
  String get mediaYourPicture;

  /// No description provided for @mediaEarlierCopy.
  ///
  /// In en, this message translates to:
  /// **'EARLIER COPY'**
  String get mediaEarlierCopy;

  /// No description provided for @mediaSharedToday.
  ///
  /// In en, this message translates to:
  /// **'Shared today'**
  String get mediaSharedToday;

  /// No description provided for @mediaPublished.
  ///
  /// In en, this message translates to:
  /// **'Published {date}'**
  String mediaPublished(String date);

  /// No description provided for @mediaMatchedBy.
  ///
  /// In en, this message translates to:
  /// **'{publisher} · earlier copy'**
  String mediaMatchedBy(String publisher);

  /// No description provided for @mediaMatchesEarlier.
  ///
  /// In en, this message translates to:
  /// **'Matches a picture published earlier'**
  String get mediaMatchesEarlier;

  /// No description provided for @verdictSemantics.
  ///
  /// In en, this message translates to:
  /// **'{verdict}, {value}% confidence'**
  String verdictSemantics(String verdict, int value);

  /// No description provided for @textInPicture.
  ///
  /// In en, this message translates to:
  /// **'Text in the picture'**
  String get textInPicture;

  /// No description provided for @saidInVideo.
  ///
  /// In en, this message translates to:
  /// **'Said in the video'**
  String get saidInVideo;

  /// No description provided for @saidInVideoCutOff.
  ///
  /// In en, this message translates to:
  /// **'Only the first three minutes were read.'**
  String get saidInVideoCutOff;

  /// No description provided for @shows.
  ///
  /// In en, this message translates to:
  /// **'Shows: {publisher}'**
  String shows(String publisher);

  /// No description provided for @compTier.
  ///
  /// In en, this message translates to:
  /// **'{tier, select, A{{count, plural, =1{1 signed credential} other{{count} signed credentials}}} B{{count, plural, =1{1 dated source} other{{count} dated sources}}} C{{count, plural, =1{1 fact-check} other{{count} fact-checks}}} other{{count, plural, =1{1 news report} other{{count} news reports}}}}'**
  String compTier(String tier, int count);

  /// No description provided for @compNoEvidence.
  ///
  /// In en, this message translates to:
  /// **'No evidence'**
  String get compNoEvidence;

  /// No description provided for @compOrigins.
  ///
  /// In en, this message translates to:
  /// **'{origins, plural, =1{1 independent publisher} other{{origins} independent publishers}}, {documents, plural, =1{1 page} other{{documents} pages}}'**
  String compOrigins(int origins, int documents);

  /// No description provided for @compNoDated.
  ///
  /// In en, this message translates to:
  /// **'No source carries a date'**
  String get compNoDated;

  /// No description provided for @compDated.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 dated finding} other{{count} dated findings}}'**
  String compDated(int count);

  /// No description provided for @compRisk.
  ///
  /// In en, this message translates to:
  /// **'{risk, select, LOW{Publishers with a clean record} MEDIUM{Some publisher risk} HIGH{High publisher risk} other{Publisher record not assessed}}'**
  String compRisk(String risk);

  /// No description provided for @compNoConflict.
  ///
  /// In en, this message translates to:
  /// **'No source disagrees'**
  String get compNoConflict;

  /// No description provided for @compConflict.
  ///
  /// In en, this message translates to:
  /// **'{supports} supporting, {contradicts} contradicting'**
  String compConflict(int supports, int contradicts);

  /// No description provided for @stepOf.
  ///
  /// In en, this message translates to:
  /// **'Step {step} of {total}'**
  String stepOf(int step, int total);

  /// No description provided for @sourcesRead.
  ///
  /// In en, this message translates to:
  /// **'{read} of {total} read'**
  String sourcesRead(int read, int total);

  /// No description provided for @sourcesWaiting.
  ///
  /// In en, this message translates to:
  /// **'Sources appear here as they are opened'**
  String get sourcesWaiting;

  /// No description provided for @sourceReading.
  ///
  /// In en, this message translates to:
  /// **'Reading…'**
  String get sourceReading;

  /// No description provided for @sourceEvidence.
  ///
  /// In en, this message translates to:
  /// **'Evidence found'**
  String get sourceEvidence;

  /// No description provided for @sourceNotRelevant.
  ///
  /// In en, this message translates to:
  /// **'Not relevant'**
  String get sourceNotRelevant;

  /// No description provided for @evidenceCollected.
  ///
  /// In en, this message translates to:
  /// **'Evidence collected'**
  String get evidenceCollected;

  /// No description provided for @notifyMe.
  ///
  /// In en, this message translates to:
  /// **'Notify me when ready'**
  String get notifyMe;

  /// No description provided for @notifyOn.
  ///
  /// In en, this message translates to:
  /// **'We\'ll notify you when it\'s ready'**
  String get notifyOn;

  /// No description provided for @notifyDenied.
  ///
  /// In en, this message translates to:
  /// **'Notifications are off for Factify. Turn them on in your phone\'s settings to be told.'**
  String get notifyDenied;

  /// No description provided for @notifyReadyTitle.
  ///
  /// In en, this message translates to:
  /// **'Your check is ready'**
  String get notifyReadyTitle;

  /// No description provided for @notifyReadyChannel.
  ///
  /// In en, this message translates to:
  /// **'Finished checks'**
  String get notifyReadyChannel;

  /// No description provided for @notifyWorkingTitle.
  ///
  /// In en, this message translates to:
  /// **'Checking…'**
  String get notifyWorkingTitle;

  /// No description provided for @notifyWorkingBody.
  ///
  /// In en, this message translates to:
  /// **'We\'ll tell you when the answer is ready.'**
  String get notifyWorkingBody;

  /// No description provided for @notifyWorkingChannel.
  ///
  /// In en, this message translates to:
  /// **'Checks in progress'**
  String get notifyWorkingChannel;

  /// No description provided for @notifyOpenResult.
  ///
  /// In en, this message translates to:
  /// **'Open result'**
  String get notifyOpenResult;

  /// No description provided for @nothingToCheckShort.
  ///
  /// In en, this message translates to:
  /// **'Nothing to check'**
  String get nothingToCheckShort;

  /// No description provided for @pcTitle.
  ///
  /// In en, this message translates to:
  /// **'Picture checks'**
  String get pcTitle;

  /// No description provided for @pcTitleVideo.
  ///
  /// In en, this message translates to:
  /// **'Video checks'**
  String get pcTitleVideo;

  /// No description provided for @pcFrames.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 still frame} other{{count} still frames}}'**
  String pcFrames(int count);

  /// No description provided for @pcNote.
  ///
  /// In en, this message translates to:
  /// **'Not part of the verdict'**
  String get pcNote;

  /// Section title: what is known about the website a submitted link comes from.
  ///
  /// In en, this message translates to:
  /// **'About this website'**
  String get sourceProfileTitle;

  /// Badge: the site is on the trusted list, with its level as the server words it.
  ///
  /// In en, this message translates to:
  /// **'Trusted · {level}'**
  String sourceProfileTrusted(String level);

  /// No description provided for @sourceProfileFactChecker.
  ///
  /// In en, this message translates to:
  /// **'Fact-checker'**
  String get sourceProfileFactChecker;

  /// No description provided for @sourceProfileUnlisted.
  ///
  /// In en, this message translates to:
  /// **'Not on our trusted list'**
  String get sourceProfileUnlisted;

  /// No description provided for @sourceProfileNote.
  ///
  /// In en, this message translates to:
  /// **'What we know about the site itself. It never makes a claim true or false.'**
  String get sourceProfileNote;

  /// No description provided for @pcCredentials.
  ///
  /// In en, this message translates to:
  /// **'Content credentials'**
  String get pcCredentials;

  /// No description provided for @pcCredAi.
  ///
  /// In en, this message translates to:
  /// **'The file says it was made with an AI tool'**
  String get pcCredAi;

  /// No description provided for @pcCredAiTool.
  ///
  /// In en, this message translates to:
  /// **'The file says it was made with an AI tool ({tool})'**
  String pcCredAiTool(String tool);

  /// No description provided for @pcCredValid.
  ///
  /// In en, this message translates to:
  /// **'Signed by {signer}'**
  String pcCredValid(String signer);

  /// No description provided for @pcCredUntrusted.
  ///
  /// In en, this message translates to:
  /// **'Present, but the signer isn\'t verified'**
  String get pcCredUntrusted;

  /// No description provided for @pcCredInvalid.
  ///
  /// In en, this message translates to:
  /// **'Present, but they don\'t check out'**
  String get pcCredInvalid;

  /// No description provided for @pcCredNone.
  ///
  /// In en, this message translates to:
  /// **'None. That\'s normal: most pictures carry none.'**
  String get pcCredNone;

  /// No description provided for @pcNotChecked.
  ///
  /// In en, this message translates to:
  /// **'Not checked'**
  String get pcNotChecked;

  /// No description provided for @pcWhyTextCard.
  ///
  /// In en, this message translates to:
  /// **'Not needed: this is a text card or a screenshot, so the words in it are checked instead.'**
  String get pcWhyTextCard;

  /// No description provided for @pcWhyTooSmall.
  ///
  /// In en, this message translates to:
  /// **'The picture is too small to judge.'**
  String get pcWhyTooSmall;

  /// No description provided for @pcWhyUnreadable.
  ///
  /// In en, this message translates to:
  /// **'The picture could not be read.'**
  String get pcWhyUnreadable;

  /// No description provided for @pcWhyDetectorOff.
  ///
  /// In en, this message translates to:
  /// **'The AI-picture check is not set up on this server.'**
  String get pcWhyDetectorOff;

  /// No description provided for @pcWhyHistoryOff.
  ///
  /// In en, this message translates to:
  /// **'Searching for earlier copies is not set up on this server.'**
  String get pcWhyHistoryOff;

  /// No description provided for @pcWhyFailed.
  ///
  /// In en, this message translates to:
  /// **'It could not be checked this time. Try again later.'**
  String get pcWhyFailed;

  /// No description provided for @pcHistory.
  ///
  /// In en, this message translates to:
  /// **'Earlier copies online'**
  String get pcHistory;

  /// No description provided for @pcHistorySince.
  ///
  /// In en, this message translates to:
  /// **'Online since {date} · {source}'**
  String pcHistorySince(String date, String source);

  /// No description provided for @pcHistoryOld.
  ///
  /// In en, this message translates to:
  /// **'Not a new picture: it was online {age} before this check.'**
  String pcHistoryOld(String age);

  /// No description provided for @pcAgeYears.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 year} other{{count} years}}'**
  String pcAgeYears(int count);

  /// No description provided for @pcAgeMonths.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 month} other{{count} months}}'**
  String pcAgeMonths(int count);

  /// No description provided for @pcAgeDays.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 day} other{{count} days}}'**
  String pcAgeDays(int count);

  /// No description provided for @pcHistoryUndated.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Found on 1 page, with no date} other{Found on {count} pages, none dated}}'**
  String pcHistoryUndated(int count);

  /// No description provided for @pcHistoryNone.
  ///
  /// In en, this message translates to:
  /// **'No earlier copies found online'**
  String get pcHistoryNone;

  /// No description provided for @pcOpenPage.
  ///
  /// In en, this message translates to:
  /// **'Opens the page where it appeared'**
  String get pcOpenPage;

  /// No description provided for @pcYourPicture.
  ///
  /// In en, this message translates to:
  /// **'Your picture'**
  String get pcYourPicture;

  /// No description provided for @pcEarlierCopy.
  ///
  /// In en, this message translates to:
  /// **'Earlier copy'**
  String get pcEarlierCopy;

  /// No description provided for @pcDetector.
  ///
  /// In en, this message translates to:
  /// **'AI-made picture signal'**
  String get pcDetector;

  /// No description provided for @pcGenerated.
  ///
  /// In en, this message translates to:
  /// **'{percent}% likely made by an AI image generator'**
  String pcGenerated(int percent);

  /// No description provided for @pcFaceSwap.
  ///
  /// In en, this message translates to:
  /// **'{percent}% likely a face was swapped or changed by AI'**
  String pcFaceSwap(int percent);

  /// No description provided for @pcDetectorNote.
  ///
  /// In en, this message translates to:
  /// **'A detector\'s estimate, not a finding.'**
  String get pcDetectorNote;

  /// No description provided for @pcAgreeLikelyAi.
  ///
  /// In en, this message translates to:
  /// **'Both detectors say this is likely AI-made'**
  String get pcAgreeLikelyAi;

  /// No description provided for @pcAgreeUnclear.
  ///
  /// In en, this message translates to:
  /// **'The detectors disagree, so it\'s unclear'**
  String get pcAgreeUnclear;

  /// No description provided for @pcAgreeNoSign.
  ///
  /// In en, this message translates to:
  /// **'No sign that an AI generator made it. That doesn\'t prove it\'s real.'**
  String get pcAgreeNoSign;

  /// No description provided for @pcOneLikelyAi.
  ///
  /// In en, this message translates to:
  /// **'The detector says this is likely AI-made'**
  String get pcOneLikelyAi;

  /// No description provided for @pcSecondOpinion.
  ///
  /// In en, this message translates to:
  /// **'Second detector: {percent}% likely AI-made'**
  String pcSecondOpinion(int percent);

  /// No description provided for @pcNoFace.
  ///
  /// In en, this message translates to:
  /// **'No face to check for a swap'**
  String get pcNoFace;

  /// No description provided for @pcFacesChecked.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 face checked} other{{count} faces checked}}'**
  String pcFacesChecked(int count);

  /// No description provided for @pcVoice.
  ///
  /// In en, this message translates to:
  /// **'{percent}% likely a machine-made voice (experimental)'**
  String pcVoice(int percent);

  /// No description provided for @pcOnServer.
  ///
  /// In en, this message translates to:
  /// **'This check ran on Factify\'s own server.'**
  String get pcOnServer;

  /// No description provided for @pcEditing.
  ///
  /// In en, this message translates to:
  /// **'Editing signals'**
  String get pcEditing;

  /// No description provided for @pcEditNoise.
  ///
  /// In en, this message translates to:
  /// **'Parts of the picture have uneven noise, which editing can cause'**
  String get pcEditNoise;

  /// No description provided for @pcEditSpectrum.
  ///
  /// In en, this message translates to:
  /// **'Unusual patterns in the fine detail, which generators and heavy compression can cause'**
  String get pcEditSpectrum;

  /// No description provided for @pcEditClean.
  ///
  /// In en, this message translates to:
  /// **'No uneven noise or unusual patterns found'**
  String get pcEditClean;

  /// No description provided for @pcFooter.
  ///
  /// In en, this message translates to:
  /// **'These are checks of the picture itself. They never change the verdict, which rests only on cited sources, and a clean result doesn\'t prove a picture is real.'**
  String get pcFooter;

  /// No description provided for @kindVideo.
  ///
  /// In en, this message translates to:
  /// **'Video'**
  String get kindVideo;

  /// No description provided for @yourVideo.
  ///
  /// In en, this message translates to:
  /// **'Your video'**
  String get yourVideo;

  /// No description provided for @srDirection.
  ///
  /// In en, this message translates to:
  /// **'{direction, select, supports{Supports the claim} contradicts{Refutes the claim} other{Adds context}}'**
  String srDirection(String direction);

  /// No description provided for @srQuoted.
  ///
  /// In en, this message translates to:
  /// **'Quoted in your result'**
  String get srQuoted;

  /// No description provided for @srParagraph.
  ///
  /// In en, this message translates to:
  /// **'Paragraph {number}'**
  String srParagraph(int number);

  /// No description provided for @srMatch.
  ///
  /// In en, this message translates to:
  /// **'match {score}'**
  String srMatch(String score);

  /// No description provided for @srPublished.
  ///
  /// In en, this message translates to:
  /// **'Published {date}'**
  String srPublished(String date);

  /// No description provided for @srReadMinutes.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 min read} other{{count} min read}}'**
  String srReadMinutes(int count);

  /// No description provided for @srBack.
  ///
  /// In en, this message translates to:
  /// **'Back to result'**
  String get srBack;

  /// No description provided for @srOpenSite.
  ///
  /// In en, this message translates to:
  /// **'Open site'**
  String get srOpenSite;

  /// No description provided for @srLoading.
  ///
  /// In en, this message translates to:
  /// **'Opening the source…'**
  String get srLoading;

  /// No description provided for @srOnlyPassage.
  ///
  /// In en, this message translates to:
  /// **'Only the passage around the quote is shown here. Open the site to read the whole article.'**
  String get srOnlyPassage;

  /// No description provided for @srUnavailable.
  ///
  /// In en, this message translates to:
  /// **'We couldn\'t open this page just now, so this is the passage our result quoted. Open the site to read it.'**
  String get srUnavailable;

  /// No description provided for @srMoved.
  ///
  /// In en, this message translates to:
  /// **'This page no longer carries the passage as we quoted it. It may have been edited since.'**
  String get srMoved;

  /// No description provided for @onbSkip.
  ///
  /// In en, this message translates to:
  /// **'Skip'**
  String get onbSkip;

  /// No description provided for @onbNext.
  ///
  /// In en, this message translates to:
  /// **'Next'**
  String get onbNext;

  /// Read out for the page dots.
  ///
  /// In en, this message translates to:
  /// **'Page {page} of {total}'**
  String onbPage(int page, int total);

  /// No description provided for @onbForwarded.
  ///
  /// In en, this message translates to:
  /// **'Forwarded many times'**
  String get onbForwarded;

  /// An invented example of a forward, on the first welcome page.
  ///
  /// In en, this message translates to:
  /// **'Govt to pay ₹5,000 a month to every woman from 1 July. Register at the link…'**
  String get onbSampleForward;

  /// An example headline, on the first welcome page.
  ///
  /// In en, this message translates to:
  /// **'RBI keeps repo rate unchanged in September review'**
  String get onbSampleLink;

  /// Overline on the sample result on the second welcome page, in capitals. The sample is invented, so it says so.
  ///
  /// In en, this message translates to:
  /// **'An example'**
  String get onbExample;

  /// No description provided for @onbSampleClaim.
  ///
  /// In en, this message translates to:
  /// **'Govt to pay ₹5,000 a month to every woman from 1 July.'**
  String get onbSampleClaim;

  /// No description provided for @onbSourcesBody.
  ///
  /// In en, this message translates to:
  /// **'When the sources don\'t settle it, Factify says Unconfirmed rather than guess.'**
  String get onbSourcesBody;

  /// No description provided for @onbPrivacy.
  ///
  /// In en, this message translates to:
  /// **'Your list of checks stays on your phone. What you check is stored on our server without your name.'**
  String get onbPrivacy;

  /// No description provided for @confirmPasswordHint.
  ///
  /// In en, this message translates to:
  /// **'Repeat it'**
  String get confirmPasswordHint;

  /// Beside the balance, which is shown large on its own.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{credit left} other{credits left}}'**
  String profileCreditsLabel(int count);

  /// No description provided for @planBetaShort.
  ///
  /// In en, this message translates to:
  /// **'Free · beta'**
  String get planBetaShort;

  /// Under the number of checks, which is shown large on its own.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{check so far} other{checks so far}}'**
  String profileChecksLabel(int count);

  /// No description provided for @settingDarkMode.
  ///
  /// In en, this message translates to:
  /// **'Dark mode'**
  String get settingDarkMode;

  /// No description provided for @settingDarkFollowsPhone.
  ///
  /// In en, this message translates to:
  /// **'Following your phone'**
  String get settingDarkFollowsPhone;

  /// No description provided for @themeBody.
  ///
  /// In en, this message translates to:
  /// **'Factify can follow your phone\'s setting, or stay light or dark.'**
  String get themeBody;

  /// No description provided for @themePhone.
  ///
  /// In en, this message translates to:
  /// **'Same as your phone'**
  String get themePhone;

  /// No description provided for @themeLight.
  ///
  /// In en, this message translates to:
  /// **'Always light'**
  String get themeLight;

  /// No description provided for @themeDark.
  ///
  /// In en, this message translates to:
  /// **'Always dark'**
  String get themeDark;

  /// No description provided for @settingNotify.
  ///
  /// In en, this message translates to:
  /// **'Notify when ready'**
  String get settingNotify;

  /// No description provided for @settingNotifyBody.
  ///
  /// In en, this message translates to:
  /// **'For checks that take longer'**
  String get settingNotifyBody;

  /// No description provided for @settingService.
  ///
  /// In en, this message translates to:
  /// **'Service'**
  String get settingService;

  /// Overline, in capitals.
  ///
  /// In en, this message translates to:
  /// **'The check didn\'t finish'**
  String get errUnfinished;

  /// Overline, in capitals.
  ///
  /// In en, this message translates to:
  /// **'No connection'**
  String get errNoConnection;

  /// Overline, in capitals.
  ///
  /// In en, this message translates to:
  /// **'Too many at once'**
  String get errRateLimited;

  /// Overline, in capitals.
  ///
  /// In en, this message translates to:
  /// **'Your account'**
  String get errYourAccount;

  /// No description provided for @errLinkTitle.
  ///
  /// In en, this message translates to:
  /// **'We couldn\'t read that page'**
  String get errLinkTitle;

  /// No description provided for @errLinkBody.
  ///
  /// In en, this message translates to:
  /// **'Some sites block automatic reading. Copy the article\'s text and paste it here instead.'**
  String get errLinkBody;

  /// No description provided for @errLinkNote.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t be read automatically'**
  String get errLinkNote;

  /// No description provided for @errLinkAction.
  ///
  /// In en, this message translates to:
  /// **'Paste the article text'**
  String get errLinkAction;

  /// No description provided for @errOfflineTitle.
  ///
  /// In en, this message translates to:
  /// **'You\'re offline'**
  String get errOfflineTitle;

  /// Under what was being checked: the check box still holds it.
  ///
  /// In en, this message translates to:
  /// **'Kept on this phone, so you won\'t need to paste it again'**
  String get errKept;

  /// No description provided for @tryAgain.
  ///
  /// In en, this message translates to:
  /// **'Try again'**
  String get tryAgain;

  /// No description provided for @errSlowTitle.
  ///
  /// In en, this message translates to:
  /// **'This is taking too long'**
  String get errSlowTitle;

  /// No description provided for @errRateLimitTitle.
  ///
  /// In en, this message translates to:
  /// **'Wait a minute, then try again'**
  String get errRateLimitTitle;

  /// No description provided for @errCreditsTitle.
  ///
  /// In en, this message translates to:
  /// **'You\'re out of credits'**
  String get errCreditsTitle;

  /// No description provided for @errCreditsAction.
  ///
  /// In en, this message translates to:
  /// **'See your credits'**
  String get errCreditsAction;

  /// No description provided for @errSignedOutTitle.
  ///
  /// In en, this message translates to:
  /// **'Please sign in again'**
  String get errSignedOutTitle;

  /// No description provided for @errTooLargeTitle.
  ///
  /// In en, this message translates to:
  /// **'That file is too big'**
  String get errTooLargeTitle;

  /// No description provided for @errTooLargeAction.
  ///
  /// In en, this message translates to:
  /// **'Choose another file'**
  String get errTooLargeAction;

  /// No description provided for @errPausedTitle.
  ///
  /// In en, this message translates to:
  /// **'Checking is paused for now'**
  String get errPausedTitle;

  /// Tooltip on the close button.
  ///
  /// In en, this message translates to:
  /// **'Close'**
  String get errClose;

  /// Under the file that was being checked: the check box still holds it.
  ///
  /// In en, this message translates to:
  /// **'Still attached, so you won\'t need to choose it again'**
  String get errKeptFile;

  /// Profile, beside Saved checks.
  ///
  /// In en, this message translates to:
  /// **'{count} on this phone'**
  String settingSavedShort(int count);

  /// Beside the Factify name on the quick verdict.
  ///
  /// In en, this message translates to:
  /// **'checked in {seconds} s'**
  String quickCheckedIn(int seconds);

  /// No description provided for @quickCopyCorrection.
  ///
  /// In en, this message translates to:
  /// **'Copy correction'**
  String get quickCopyCorrection;

  /// No description provided for @quickCopyContext.
  ///
  /// In en, this message translates to:
  /// **'Copy context'**
  String get quickCopyContext;

  /// No description provided for @quickCopyResult.
  ///
  /// In en, this message translates to:
  /// **'Copy result'**
  String get quickCopyResult;

  /// For an Unconfirmed result: a polite note that it could not be confirmed yet.
  ///
  /// In en, this message translates to:
  /// **'Copy a note'**
  String get quickCopyNote;

  /// No description provided for @quickCopied.
  ///
  /// In en, this message translates to:
  /// **'Copied — paste it in the chat'**
  String get quickCopied;

  /// No description provided for @quickOpenResult.
  ///
  /// In en, this message translates to:
  /// **'Open full result'**
  String get quickOpenResult;

  /// No description provided for @quickOpenApp.
  ///
  /// In en, this message translates to:
  /// **'Open Factify'**
  String get quickOpenApp;

  /// No description provided for @quickSignIn.
  ///
  /// In en, this message translates to:
  /// **'Sign in to Factify to check this.'**
  String get quickSignIn;

  /// No description provided for @settingQuick.
  ///
  /// In en, this message translates to:
  /// **'Answer over the chat'**
  String get settingQuick;

  /// No description provided for @settingQuickBody.
  ///
  /// In en, this message translates to:
  /// **'Text you share opens its answer over the chat'**
  String get settingQuickBody;

  /// No description provided for @profileLoadFailed.
  ///
  /// In en, this message translates to:
  /// **'Your account couldn\'t be loaded just now.'**
  String get profileLoadFailed;

  /// Under the earlier copy of a picture: who published it, and how closely it matches.
  ///
  /// In en, this message translates to:
  /// **'{publisher} · {percent}% visual match'**
  String mediaVisualMatch(String publisher, int percent);

  /// Fact-checks already published elsewhere, compared with the claim in bulk.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Compared with 1 published fact-check} other{Compared with {count} published fact-checks}}'**
  String sourcesFactChecks(int count);

  /// A source read as speaking to the claim, then found by the source check to be about something else.
  ///
  /// In en, this message translates to:
  /// **'Set aside'**
  String get sourceSetAside;

  /// No description provided for @evidenceFoundSoFar.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =0{Nothing yet, still reading} =1{1 source speaks to this claim - checking it next} other{{count} sources speak to this claim - checking them next}}'**
  String evidenceFoundSoFar(int count);

  /// No description provided for @evidenceHeldUp.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =0{None held up when checked against the claim} =1{1 source held up when checked against the claim} other{{count} sources held up when checked against the claim}}'**
  String evidenceHeldUp(int count);

  /// No description provided for @onb3Title.
  ///
  /// In en, this message translates to:
  /// **'Pictures and videos too'**
  String get onb3Title;

  /// No description provided for @onb3Body.
  ///
  /// In en, this message translates to:
  /// **'Factify spots AI-made pictures, face swaps and machine voices, and checks what\'s said in a video.'**
  String get onb3Body;

  /// No description provided for @onbMediaMessages.
  ///
  /// In en, this message translates to:
  /// **'Messages'**
  String get onbMediaMessages;

  /// No description provided for @onbMediaLinks.
  ///
  /// In en, this message translates to:
  /// **'Links'**
  String get onbMediaLinks;

  /// No description provided for @onbMediaPictures.
  ///
  /// In en, this message translates to:
  /// **'Pictures'**
  String get onbMediaPictures;

  /// No description provided for @onbMediaVideos.
  ///
  /// In en, this message translates to:
  /// **'Videos'**
  String get onbMediaVideos;

  /// No description provided for @onbMediaVoice.
  ///
  /// In en, this message translates to:
  /// **'Voices in videos'**
  String get onbMediaVoice;

  /// No description provided for @onbMediaPdfs.
  ///
  /// In en, this message translates to:
  /// **'PDFs'**
  String get onbMediaPdfs;

  /// No description provided for @onbHaveAccount.
  ///
  /// In en, this message translates to:
  /// **'I have an account'**
  String get onbHaveAccount;

  /// No description provided for @authHaveAccount.
  ///
  /// In en, this message translates to:
  /// **'Have an account?'**
  String get authHaveAccount;

  /// No description provided for @authNewHere.
  ///
  /// In en, this message translates to:
  /// **'New to Factify?'**
  String get authNewHere;

  /// No description provided for @authCreateLink.
  ///
  /// In en, this message translates to:
  /// **'Create one'**
  String get authCreateLink;

  /// No description provided for @nameOptionalLabel.
  ///
  /// In en, this message translates to:
  /// **'Your name (optional)'**
  String get nameOptionalLabel;

  /// No description provided for @nameOptionalHint.
  ///
  /// In en, this message translates to:
  /// **'What should we call you?'**
  String get nameOptionalHint;

  /// No description provided for @signUpTitle.
  ///
  /// In en, this message translates to:
  /// **'Create your account'**
  String get signUpTitle;

  /// No description provided for @signUpBody.
  ///
  /// In en, this message translates to:
  /// **'30 free checks every month. It takes a minute.'**
  String get signUpBody;

  /// No description provided for @surveyStep.
  ///
  /// In en, this message translates to:
  /// **'{step} of {total}'**
  String surveyStep(int step, int total);

  /// No description provided for @surveySkipAll.
  ///
  /// In en, this message translates to:
  /// **'Skip all'**
  String get surveySkipAll;

  /// No description provided for @surveyNext.
  ///
  /// In en, this message translates to:
  /// **'Next'**
  String get surveyNext;

  /// No description provided for @surveyFinish.
  ///
  /// In en, this message translates to:
  /// **'Finish'**
  String get surveyFinish;

  /// No description provided for @surveyPickAny.
  ///
  /// In en, this message translates to:
  /// **'Pick any that fit'**
  String get surveyPickAny;

  /// No description provided for @surveyWhy.
  ///
  /// In en, this message translates to:
  /// **'Four quick questions help us build Factify for you. Skip any you like.'**
  String get surveyWhy;

  /// No description provided for @surveyRoleQ.
  ///
  /// In en, this message translates to:
  /// **'What brings you to Factify?'**
  String get surveyRoleQ;

  /// No description provided for @surveyRoleJournalist.
  ///
  /// In en, this message translates to:
  /// **'Journalist or fact-checker'**
  String get surveyRoleJournalist;

  /// No description provided for @surveyRoleStudent.
  ///
  /// In en, this message translates to:
  /// **'Student or researcher'**
  String get surveyRoleStudent;

  /// No description provided for @surveyRoleTeacher.
  ///
  /// In en, this message translates to:
  /// **'Teacher'**
  String get surveyRoleTeacher;

  /// No description provided for @surveyRoleFamily.
  ///
  /// In en, this message translates to:
  /// **'Checking forwards for family and friends'**
  String get surveyRoleFamily;

  /// No description provided for @surveyRoleCurious.
  ///
  /// In en, this message translates to:
  /// **'Just curious'**
  String get surveyRoleCurious;

  /// No description provided for @surveyPlacesQ.
  ///
  /// In en, this message translates to:
  /// **'Where do you see things you\'d like to check?'**
  String get surveyPlacesQ;

  /// No description provided for @surveyPlaceNews.
  ///
  /// In en, this message translates to:
  /// **'News sites'**
  String get surveyPlaceNews;

  /// No description provided for @surveyWantsQ.
  ///
  /// In en, this message translates to:
  /// **'What do you want to check most?'**
  String get surveyWantsQ;

  /// No description provided for @surveyWantForwards.
  ///
  /// In en, this message translates to:
  /// **'Forwards and messages'**
  String get surveyWantForwards;

  /// No description provided for @surveyWantLinks.
  ///
  /// In en, this message translates to:
  /// **'News links'**
  String get surveyWantLinks;

  /// No description provided for @surveyWantPictures.
  ///
  /// In en, this message translates to:
  /// **'Pictures'**
  String get surveyWantPictures;

  /// No description provided for @surveyWantVideos.
  ///
  /// In en, this message translates to:
  /// **'Videos'**
  String get surveyWantVideos;

  /// No description provided for @surveyWantVoice.
  ///
  /// In en, this message translates to:
  /// **'Voice notes'**
  String get surveyWantVoice;

  /// No description provided for @surveyHeardQ.
  ///
  /// In en, this message translates to:
  /// **'How did you hear about Factify?'**
  String get surveyHeardQ;

  /// No description provided for @surveyHeardFriend.
  ///
  /// In en, this message translates to:
  /// **'From a friend'**
  String get surveyHeardFriend;

  /// No description provided for @surveyHeardSocial.
  ///
  /// In en, this message translates to:
  /// **'On social media'**
  String get surveyHeardSocial;

  /// No description provided for @surveyHeardCollege.
  ///
  /// In en, this message translates to:
  /// **'At college or an event'**
  String get surveyHeardCollege;

  /// No description provided for @surveyHeardOther.
  ///
  /// In en, this message translates to:
  /// **'Somewhere else'**
  String get surveyHeardOther;

  /// No description provided for @surveySaveFailed.
  ///
  /// In en, this message translates to:
  /// **'Your answers couldn\'t be saved. You can carry on anyway.'**
  String get surveySaveFailed;

  /// No description provided for @creditsTitleNamed.
  ///
  /// In en, this message translates to:
  /// **'You\'re in, {name}'**
  String creditsTitleNamed(String name);

  /// No description provided for @creditsWelcomeTitle.
  ///
  /// In en, this message translates to:
  /// **'You\'re in'**
  String get creditsWelcomeTitle;

  /// No description provided for @creditsLabel.
  ///
  /// In en, this message translates to:
  /// **'free checks'**
  String get creditsLabel;

  /// No description provided for @creditsBody.
  ///
  /// In en, this message translates to:
  /// **'They\'re on us. Each check uses one, and your balance is always in Profile.'**
  String get creditsBody;

  /// No description provided for @creditsStart.
  ///
  /// In en, this message translates to:
  /// **'Start checking'**
  String get creditsStart;

  /// No description provided for @buyCredits.
  ///
  /// In en, this message translates to:
  /// **'Buy credits'**
  String get buyCredits;

  /// No description provided for @payTitle.
  ///
  /// In en, this message translates to:
  /// **'Finish in your browser'**
  String get payTitle;

  /// No description provided for @payOpening.
  ///
  /// In en, this message translates to:
  /// **'Opening the payment page…'**
  String get payOpening;

  /// No description provided for @payWaiting.
  ///
  /// In en, this message translates to:
  /// **'Choose a pack and pay in the browser. This screen moves on by itself when the payment goes through.'**
  String get payWaiting;

  /// No description provided for @payOpened.
  ///
  /// In en, this message translates to:
  /// **'Payment page open. Waiting for your payment…'**
  String get payOpened;

  /// No description provided for @payReopen.
  ///
  /// In en, this message translates to:
  /// **'Open the payment page again'**
  String get payReopen;

  /// No description provided for @payCancel.
  ///
  /// In en, this message translates to:
  /// **'Cancel'**
  String get payCancel;

  /// No description provided for @payPaidTitle.
  ///
  /// In en, this message translates to:
  /// **'Payment complete'**
  String get payPaidTitle;

  /// No description provided for @payPaidBody.
  ///
  /// In en, this message translates to:
  /// **'{credits} credits were added.'**
  String payPaidBody(int credits);

  /// No description provided for @payFailedTitle.
  ///
  /// In en, this message translates to:
  /// **'Payment didn\'t go through'**
  String get payFailedTitle;

  /// No description provided for @payFailedBody.
  ///
  /// In en, this message translates to:
  /// **'Nothing was charged. Try again, or choose another way to pay.'**
  String get payFailedBody;

  /// No description provided for @payCancelledTitle.
  ///
  /// In en, this message translates to:
  /// **'Payment cancelled'**
  String get payCancelledTitle;

  /// No description provided for @payCancelledBody.
  ///
  /// In en, this message translates to:
  /// **'Nothing was charged.'**
  String get payCancelledBody;

  /// No description provided for @payExpiredTitle.
  ///
  /// In en, this message translates to:
  /// **'The payment link expired'**
  String get payExpiredTitle;

  /// No description provided for @payExpiredBody.
  ///
  /// In en, this message translates to:
  /// **'It\'s only valid for 10 minutes. Start again to get a new one.'**
  String get payExpiredBody;

  /// No description provided for @payTryAgain.
  ///
  /// In en, this message translates to:
  /// **'Start again'**
  String get payTryAgain;

  /// No description provided for @payDone.
  ///
  /// In en, this message translates to:
  /// **'Done'**
  String get payDone;

  /// No description provided for @payCouldNotStart.
  ///
  /// In en, this message translates to:
  /// **'The payment couldn\'t be started. Check your connection and try again.'**
  String get payCouldNotStart;

  /// No description provided for @planChecksTitle.
  ///
  /// In en, this message translates to:
  /// **'Checks this month'**
  String get planChecksTitle;

  /// No description provided for @planName.
  ///
  /// In en, this message translates to:
  /// **'{name} plan'**
  String planName(String name);

  /// No description provided for @planChecksLeft.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 check left this month} other{{count} checks left this month}}'**
  String planChecksLeft(int count);

  /// No description provided for @planChecksLabel.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{check left} other{checks left}}'**
  String planChecksLabel(int count);

  /// No description provided for @planUsed.
  ///
  /// In en, this message translates to:
  /// **'{used} of {total} plan checks used'**
  String planUsed(int used, int total);

  /// No description provided for @planResets.
  ///
  /// In en, this message translates to:
  /// **'Resets {date}'**
  String planResets(String date);

  /// No description provided for @planCredits.
  ///
  /// In en, this message translates to:
  /// **'+{count} credits'**
  String planCredits(int count);

  /// No description provided for @upgradePlan.
  ///
  /// In en, this message translates to:
  /// **'Upgrade plan'**
  String get upgradePlan;

  /// No description provided for @changePlan.
  ///
  /// In en, this message translates to:
  /// **'Change plan'**
  String get changePlan;

  /// No description provided for @payPlanPaidBody.
  ///
  /// In en, this message translates to:
  /// **'Your new plan is active. Its checks are yours from now.'**
  String get payPlanPaidBody;

  /// No description provided for @privacyPolicy.
  ///
  /// In en, this message translates to:
  /// **'Privacy policy'**
  String get privacyPolicy;

  /// No description provided for @deleteAccount.
  ///
  /// In en, this message translates to:
  /// **'Delete account'**
  String get deleteAccount;

  /// No description provided for @deleteAccountTitle.
  ///
  /// In en, this message translates to:
  /// **'Delete your account?'**
  String get deleteAccountTitle;

  /// No description provided for @deleteAccountBody.
  ///
  /// In en, this message translates to:
  /// **'This deletes your account for good: your sign-in, any plan and credits you have left, your payment records and your survey answers. The checks saved on this phone are cleared too.'**
  String get deleteAccountBody;

  /// No description provided for @deleteAccountContinue.
  ///
  /// In en, this message translates to:
  /// **'Continue'**
  String get deleteAccountContinue;

  /// No description provided for @deleteAccountConfirmTitle.
  ///
  /// In en, this message translates to:
  /// **'Delete for good?'**
  String get deleteAccountConfirmTitle;

  /// No description provided for @deleteAccountConfirmBody.
  ///
  /// In en, this message translates to:
  /// **'The account {email} will be deleted now. This can\'t be undone.'**
  String deleteAccountConfirmBody(String email);

  /// No description provided for @deleteAccountConfirm.
  ///
  /// In en, this message translates to:
  /// **'Delete for good'**
  String get deleteAccountConfirm;

  /// No description provided for @deleteAccountDeleting.
  ///
  /// In en, this message translates to:
  /// **'Deleting…'**
  String get deleteAccountDeleting;

  /// No description provided for @deleteAccountDone.
  ///
  /// In en, this message translates to:
  /// **'Your account has been deleted.'**
  String get deleteAccountDone;

  /// No description provided for @deleteAccountFailed.
  ///
  /// In en, this message translates to:
  /// **'Your account wasn\'t deleted. {reason}'**
  String deleteAccountFailed(String reason);

  /// No description provided for @planEnds.
  ///
  /// In en, this message translates to:
  /// **'Ends {date}'**
  String planEnds(String date);

  /// No description provided for @planRenews.
  ///
  /// In en, this message translates to:
  /// **'Renews {date}'**
  String planRenews(String date);

  /// No description provided for @planExtraCapped.
  ///
  /// In en, this message translates to:
  /// **'Extra checks on, {price} each: {used} of {cap} used'**
  String planExtraCapped(String price, String used, String cap);

  /// No description provided for @planExtraUncapped.
  ///
  /// In en, this message translates to:
  /// **'Extra checks on, {price} each: {used} used'**
  String planExtraUncapped(String price, String used);

  /// No description provided for @planExtraBlocked.
  ///
  /// In en, this message translates to:
  /// **'Extra checks are paused until your unpaid extra-usage bill is paid.'**
  String get planExtraBlocked;

  /// No description provided for @planPreviewNote.
  ///
  /// In en, this message translates to:
  /// **'During the preview you can keep checking after your plan\'s checks run out.'**
  String get planPreviewNote;

  /// No description provided for @creditsPreviewNote.
  ///
  /// In en, this message translates to:
  /// **'During the preview you can keep checking after your credits run out.'**
  String get creditsPreviewNote;

  /// No description provided for @creditCostsVideo.
  ///
  /// In en, this message translates to:
  /// **'A check costs {check}, a video {video}'**
  String creditCostsVideo(int check, int video);

  /// No description provided for @planVideoCost.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{A video uses 1 check} other{A video uses {count} checks}}'**
  String planVideoCost(int count);

  /// No description provided for @sourceVideo.
  ///
  /// In en, this message translates to:
  /// **'Video'**
  String get sourceVideo;

  /// No description provided for @videoTooLarge.
  ///
  /// In en, this message translates to:
  /// **'That video is over {mb} MB. Choose a shorter one, or trim it first.'**
  String videoTooLarge(int mb);

  /// No description provided for @notAVideo.
  ///
  /// In en, this message translates to:
  /// **'That file isn\'t a video Factify can read. Choose an MP4, MOV or WebM video.'**
  String get notAVideo;

  /// No description provided for @videoFirstSeconds.
  ///
  /// In en, this message translates to:
  /// **'{seconds, plural, other{We look at the first {seconds} seconds of a video and listen to its first 3 minutes.}}'**
  String videoFirstSeconds(int seconds);
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en', 'hi'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return AppLocalizationsEn();
    case 'hi':
      return AppLocalizationsHi();
  }

  throw FlutterError(
    'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
