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

  /// No description provided for @imageReadTitle.
  ///
  /// In en, this message translates to:
  /// **'What we read in your picture'**
  String get imageReadTitle;

  /// No description provided for @imageKind.
  ///
  /// In en, this message translates to:
  /// **'{kind, select, NEWS_ARTICLE{News article} SOCIAL_POST{Social media post} CHAT_MESSAGE{Chat forward} TV_GRAPHIC{TV news graphic} POSTER{Poster} DOCUMENT{Document} PHOTO{Photo} MEME{Meme} other{Picture}}'**
  String imageKind(String kind);

  /// No description provided for @imageFrom.
  ///
  /// In en, this message translates to:
  /// **'Shows: {publisher}'**
  String imageFrom(String publisher);

  /// No description provided for @imageTextLabel.
  ///
  /// In en, this message translates to:
  /// **'Text in the picture'**
  String get imageTextLabel;

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

  /// No description provided for @welcomePointInputs.
  ///
  /// In en, this message translates to:
  /// **'Text, links, pictures and PDFs'**
  String get welcomePointInputs;

  /// No description provided for @welcomePointLanguages.
  ///
  /// In en, this message translates to:
  /// **'In English and Hindi'**
  String get welcomePointLanguages;

  /// No description provided for @welcomeSignInTitle.
  ///
  /// In en, this message translates to:
  /// **'Create your account'**
  String get welcomeSignInTitle;

  /// No description provided for @welcomeSignInBody.
  ///
  /// In en, this message translates to:
  /// **'An account is needed to check. Sign up or sign in with your email and a password, or with Google.'**
  String get welcomeSignInBody;

  /// No description provided for @tabHome.
  ///
  /// In en, this message translates to:
  /// **'Home'**
  String get tabHome;

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

  /// No description provided for @pasteButton.
  ///
  /// In en, this message translates to:
  /// **'Paste'**
  String get pasteButton;

  /// No description provided for @pickImageTitle.
  ///
  /// In en, this message translates to:
  /// **'Add a picture'**
  String get pickImageTitle;

  /// No description provided for @pickImageBody.
  ///
  /// In en, this message translates to:
  /// **'A screenshot, a WhatsApp forward or a photo. We read the text in it and check it.'**
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
  /// **'Saved only on this phone. Nothing you check is kept on our servers. Swipe a check left to delete it.'**
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

  /// No description provided for @profileDetails.
  ///
  /// In en, this message translates to:
  /// **'Account details'**
  String get profileDetails;

  /// No description provided for @profileEmail.
  ///
  /// In en, this message translates to:
  /// **'Email'**
  String get profileEmail;

  /// No description provided for @profileName.
  ///
  /// In en, this message translates to:
  /// **'Name'**
  String get profileName;

  /// No description provided for @profilePlan.
  ///
  /// In en, this message translates to:
  /// **'Plan'**
  String get profilePlan;

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

  /// No description provided for @settingHistoryCount.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =0{None saved} =1{1 check on this phone} other{{count} checks on this phone}}'**
  String settingHistoryCount(int count);

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

  /// No description provided for @serviceStatus.
  ///
  /// In en, this message translates to:
  /// **'Service'**
  String get serviceStatus;

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

  /// No description provided for @modeCreateAccount.
  ///
  /// In en, this message translates to:
  /// **'Create account'**
  String get modeCreateAccount;

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

  /// No description provided for @nothingToCheckText.
  ///
  /// In en, this message translates to:
  /// **'We didn\'t find a factual claim in this - it reads as opinion, a joke or conversation, so there\'s nothing here to confirm or rule out.'**
  String get nothingToCheckText;

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

  /// No description provided for @documentReadTitle.
  ///
  /// In en, this message translates to:
  /// **'What we read in your document'**
  String get documentReadTitle;

  /// No description provided for @pasteCopiedText.
  ///
  /// In en, this message translates to:
  /// **'Paste copied text'**
  String get pasteCopiedText;

  /// No description provided for @deepChip.
  ///
  /// In en, this message translates to:
  /// **'Deep'**
  String get deepChip;

  /// No description provided for @deepChipOnHint.
  ///
  /// In en, this message translates to:
  /// **'Deep check is on'**
  String get deepChipOnHint;

  /// No description provided for @shareFromWhatsApp.
  ///
  /// In en, this message translates to:
  /// **'Or share from WhatsApp'**
  String get shareFromWhatsApp;

  /// No description provided for @checkTakes.
  ///
  /// In en, this message translates to:
  /// **'Usually takes 20–50 seconds'**
  String get checkTakes;

  /// No description provided for @checkTakesDeep.
  ///
  /// In en, this message translates to:
  /// **'Deep check · usually 1–3 minutes'**
  String get checkTakesDeep;

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
  /// **'You stopped {count} false or misleading forwards from spreading this week.'**
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

  /// No description provided for @claimStateUnconfirmed.
  ///
  /// In en, this message translates to:
  /// **'Unconfirmed'**
  String get claimStateUnconfirmed;

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

  /// No description provided for @evidenceNote.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =0{Nothing yet, still reading} =1{1 source addresses this claim} other{{count} sources address this claim}}'**
  String evidenceNote(int count);

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
