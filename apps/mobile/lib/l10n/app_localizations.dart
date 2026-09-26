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

  /// No description provided for @tabActivity.
  ///
  /// In en, this message translates to:
  /// **'Activity'**
  String get tabActivity;

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

  /// No description provided for @heroTitle.
  ///
  /// In en, this message translates to:
  /// **'Is it true?'**
  String get heroTitle;

  /// No description provided for @heroSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Paste a message or a link, or check a picture. We check it against reliable sources.'**
  String get heroSubtitle;

  /// No description provided for @inputLabel.
  ///
  /// In en, this message translates to:
  /// **'Paste a message or a link'**
  String get inputLabel;

  /// No description provided for @inputHint.
  ///
  /// In en, this message translates to:
  /// **'Or share straight from WhatsApp, a browser, or the gallery'**
  String get inputHint;

  /// No description provided for @clear.
  ///
  /// In en, this message translates to:
  /// **'Clear'**
  String get clear;

  /// No description provided for @checkThis.
  ///
  /// In en, this message translates to:
  /// **'Check this'**
  String get checkThis;

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

  /// No description provided for @sourceFile.
  ///
  /// In en, this message translates to:
  /// **'File'**
  String get sourceFile;

  /// Label above the preview of what was submitted. kind is text, link, image or document.
  ///
  /// In en, this message translates to:
  /// **'{kind, select, text{Checking this message} link{Checking this link} image{Checking this image} other{Checking this document}}'**
  String checkingSubmission(String kind);

  /// No description provided for @emptyTitle.
  ///
  /// In en, this message translates to:
  /// **'Nothing checked yet'**
  String get emptyTitle;

  /// No description provided for @emptyBody.
  ///
  /// In en, this message translates to:
  /// **'Share a forward straight into Factify, paste it above, or check a picture. Every verdict comes with the sources behind it — and when there are none, it says so.'**
  String get emptyBody;

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
  /// **'A check usually takes 20–50 seconds.'**
  String get usuallyTakes;

  /// No description provided for @statusNotChecked.
  ///
  /// In en, this message translates to:
  /// **'Not checked'**
  String get statusNotChecked;

  /// No description provided for @claimNotSearched.
  ///
  /// In en, this message translates to:
  /// **'Each check searches its five most important claims, and this wasn\'t one of them.'**
  String get claimNotSearched;

  /// No description provided for @claimTimedOut.
  ///
  /// In en, this message translates to:
  /// **'We ran out of time before any source for this could be read. Tap Check again.'**
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

  /// No description provided for @videoAcceptedTitle.
  ///
  /// In en, this message translates to:
  /// **'Video accepted'**
  String get videoAcceptedTitle;

  /// No description provided for @videoAcceptedBody.
  ///
  /// In en, this message translates to:
  /// **'Longer than a request can stay open. Checking now.'**
  String get videoAcceptedBody;

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

  /// No description provided for @activityEmptyTitle.
  ///
  /// In en, this message translates to:
  /// **'No checks this session'**
  String get activityEmptyTitle;

  /// No description provided for @activityEmptyBody.
  ///
  /// In en, this message translates to:
  /// **'Results stay on this device for the session and are gone when the app closes — what you check is nobody\'s record.'**
  String get activityEmptyBody;

  /// No description provided for @activityFooter.
  ///
  /// In en, this message translates to:
  /// **'Session only, by design: what you check is a record of what you were suspicious about, and this app does not keep one.'**
  String get activityFooter;

  /// No description provided for @historyTitle.
  ///
  /// In en, this message translates to:
  /// **'Earlier this session'**
  String get historyTitle;

  /// How many sources a past check quoted. A count of citations, never a confidence figure.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =0{No citable evidence} =1{1 citation} other{{count} citations}}'**
  String historyCitations(int count);

  /// No description provided for @errorNoServerAddress.
  ///
  /// In en, this message translates to:
  /// **'This build has no server address. Rebuild it with --dart-define=FACTIFY_API=https://your-server.'**
  String get errorNoServerAddress;

  /// No description provided for @errorShareUnreadable.
  ///
  /// In en, this message translates to:
  /// **'Could not read the shared item.'**
  String get errorShareUnreadable;

  /// No description provided for @errorShareFileUnopenable.
  ///
  /// In en, this message translates to:
  /// **'That file could not be opened. Share it again, or use the Gallery button in Factify.'**
  String get errorShareFileUnopenable;

  /// No description provided for @errorVideoSlow.
  ///
  /// In en, this message translates to:
  /// **'That video is taking longer than expected. Case {caseId} is still processing.'**
  String errorVideoSlow(String caseId);

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
  /// **'Correction copied - paste it back into the chat'**
  String get correctionCopied;

  /// No description provided for @correctionHeader.
  ///
  /// In en, this message translates to:
  /// **'Checked with Factify:'**
  String get correctionHeader;

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

  /// No description provided for @failureLinkUnchecked.
  ///
  /// In en, this message translates to:
  /// **'We couldn\'t find anything to check on that page. Some sites block automatic reading, so copy the article\'s text and paste it here instead.'**
  String get failureLinkUnchecked;

  /// No description provided for @failureTooLarge.
  ///
  /// In en, this message translates to:
  /// **'That file is too large to check.'**
  String get failureTooLarge;

  /// No description provided for @failureDailyLimit.
  ///
  /// In en, this message translates to:
  /// **'Factify is at its daily limit. Please try again tomorrow.'**
  String get failureDailyLimit;

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
  /// **'Misleading'**
  String get headlineShareWithCorrection;

  /// No description provided for @subheadShareWithCorrection.
  ///
  /// In en, this message translates to:
  /// **'Part of this is wrong'**
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

  /// No description provided for @citationCount.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =0{No citations} =1{1 citation} other{{count} citations}}'**
  String citationCount(int count);

  /// When the evidence behind a verdict was gathered. Always shown.
  ///
  /// In en, this message translates to:
  /// **'Evidence retrieved {time}'**
  String evidenceRetrievedAt(DateTime time);

  /// No description provided for @checkedEarlier.
  ///
  /// In en, this message translates to:
  /// **'Checked earlier'**
  String get checkedEarlier;

  /// No description provided for @reusedNote.
  ///
  /// In en, this message translates to:
  /// **'Reused from an earlier check of the same content. The evidence below is from that check.'**
  String get reusedNote;

  /// Shown only when the interface is not in English: verdict reasons still arrive from the server in English.
  ///
  /// In en, this message translates to:
  /// **'Some details below are shown in English for now.'**
  String get englishOnlyNote;

  /// No description provided for @whyNoVerdict.
  ///
  /// In en, this message translates to:
  /// **'Why unconfirmed?'**
  String get whyNoVerdict;

  /// No description provided for @seeEvidence.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{See the source} other{See all {count} sources}}'**
  String seeEvidence(int count);

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

  /// No description provided for @theClaim.
  ///
  /// In en, this message translates to:
  /// **'The claim'**
  String get theClaim;

  /// No description provided for @evidenceStrength.
  ///
  /// In en, this message translates to:
  /// **'Evidence strength: {band}'**
  String evidenceStrength(String band);

  /// No description provided for @strengthBand.
  ///
  /// In en, this message translates to:
  /// **'{band, select, none{none} weak{weak} moderate{moderate} strong{strong} conclusive{conclusive} other{{band}}}'**
  String strengthBand(String band);

  /// One term of the explainable strength score, named for a reader.
  ///
  /// In en, this message translates to:
  /// **'{name, select, tier_composition{Evidence tiers} independent_origins{Independent origins} temporal_confidence{Dating} source_transparency{Publisher transparency} conflict_penalty{Conflicting evidence} other{{name}}}'**
  String strengthComponent(String name);

  /// No description provided for @excludedFromScore.
  ///
  /// In en, this message translates to:
  /// **'Excluded from this score: {providers}'**
  String excludedFromScore(String providers);

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

  /// No description provided for @anchorPage.
  ///
  /// In en, this message translates to:
  /// **'Found at page {page}'**
  String anchorPage(int page);

  /// No description provided for @anchorParagraph.
  ///
  /// In en, this message translates to:
  /// **'Found at paragraph {paragraph}'**
  String anchorParagraph(int paragraph);

  /// No description provided for @anchorCharacters.
  ///
  /// In en, this message translates to:
  /// **'Found at characters {start} to {end}'**
  String anchorCharacters(int start, int end);

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

  /// No description provided for @noEvidenceTitle.
  ///
  /// In en, this message translates to:
  /// **'No citable source was found'**
  String get noEvidenceTitle;

  /// No description provided for @noEvidenceBody.
  ///
  /// In en, this message translates to:
  /// **'This does not mean the content is false. It means nothing we could cite either supports or contradicts it, so Factify did not decide.'**
  String get noEvidenceBody;

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

  /// No description provided for @sourceRiskTitle.
  ///
  /// In en, this message translates to:
  /// **'{risk, select, HIGH{Publisher has a high risk profile} MEDIUM{Publisher has a mixed record} LOW{Publisher has an established record} other{Publisher risk not assessed}}'**
  String sourceRiskTitle(String risk);

  /// A risky publisher is a reason to look harder, never a finding that the content is false.
  ///
  /// In en, this message translates to:
  /// **'{risk, select, HIGH{Recently registered, or with a record of unreliable material. This describes the publisher, not this claim.} MEDIUM{Some signals worth noting about the source. This describes the publisher, not this claim.} LOW{No adverse signals about the source. This is not evidence that the claim itself is true.} other{Nothing is known either way.}}'**
  String sourceRiskDetail(String risk);

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

  /// No description provided for @inputAnchorCharacters.
  ///
  /// In en, this message translates to:
  /// **'Characters {start}–{end}'**
  String inputAnchorCharacters(int start, int end);

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

  /// On a strength row that leads to the citations it was computed from.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 source} other{{count} sources}}'**
  String strengthComponentCitations(int count);

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

  /// No description provided for @clipboardPasteAndCheck.
  ///
  /// In en, this message translates to:
  /// **'Paste and check'**
  String get clipboardPasteAndCheck;

  /// No description provided for @clipboardDismiss.
  ///
  /// In en, this message translates to:
  /// **'Not now'**
  String get clipboardDismiss;

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

  /// No description provided for @signInTitle.
  ///
  /// In en, this message translates to:
  /// **'Sign in to Factify'**
  String get signInTitle;

  /// No description provided for @signInBody.
  ///
  /// In en, this message translates to:
  /// **'Keep your profile and credits on any phone. We never keep a record of what you check.'**
  String get signInBody;

  /// No description provided for @emailLabel.
  ///
  /// In en, this message translates to:
  /// **'Email'**
  String get emailLabel;

  /// No description provided for @sendCode.
  ///
  /// In en, this message translates to:
  /// **'Email me a code'**
  String get sendCode;

  /// No description provided for @codeSentTo.
  ///
  /// In en, this message translates to:
  /// **'We sent a 6-digit code to {email}.'**
  String codeSentTo(String email);

  /// No description provided for @codeLabel.
  ///
  /// In en, this message translates to:
  /// **'6-digit code'**
  String get codeLabel;

  /// No description provided for @verifyCode.
  ///
  /// In en, this message translates to:
  /// **'Sign in'**
  String get verifyCode;

  /// No description provided for @useDifferentEmail.
  ///
  /// In en, this message translates to:
  /// **'Use a different email'**
  String get useDifferentEmail;

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
  /// **'Sign-in isn\'t switched on for this server yet. You can keep checking without an account.'**
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
  /// **'A check costs {check} · a deep check costs {deep}'**
  String creditCosts(int check, int deep);

  /// No description provided for @checksSoFar.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 check so far} other{{count} checks so far}}'**
  String checksSoFar(int count);

  /// No description provided for @memberSince.
  ///
  /// In en, this message translates to:
  /// **'Member since {date}'**
  String memberSince(DateTime date);

  /// No description provided for @planBeta.
  ///
  /// In en, this message translates to:
  /// **'Free · beta, no limits yet'**
  String get planBeta;

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

  /// No description provided for @authWrongCode.
  ///
  /// In en, this message translates to:
  /// **'That code didn\'t work. Check the email and try again.'**
  String get authWrongCode;

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

  /// No description provided for @deepCheck.
  ///
  /// In en, this message translates to:
  /// **'Deep check'**
  String get deepCheck;

  /// No description provided for @deepCheckHint.
  ///
  /// In en, this message translates to:
  /// **'More claims and sources · takes 1–3 minutes'**
  String get deepCheckHint;

  /// No description provided for @deepChecking.
  ///
  /// In en, this message translates to:
  /// **'Deep check…'**
  String get deepChecking;

  /// No description provided for @deepProgress.
  ///
  /// In en, this message translates to:
  /// **'{done} of {total} claims checked'**
  String deepProgress(int done, int total);

  /// No description provided for @deepUsuallyTakes.
  ///
  /// In en, this message translates to:
  /// **'A deep check usually takes 1–3 minutes.'**
  String get deepUsuallyTakes;

  /// No description provided for @deepTooSlow.
  ///
  /// In en, this message translates to:
  /// **'The deep check is taking longer than expected. Try Check again in a minute.'**
  String get deepTooSlow;
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
