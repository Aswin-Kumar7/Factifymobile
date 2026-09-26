// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Hindi (`hi`).
class AppLocalizationsHi extends AppLocalizations {
  AppLocalizationsHi([String locale = 'hi']) : super(locale);

  @override
  String get tabCheck => 'जाँचें';

  @override
  String get tabActivity => 'गतिविधि';

  @override
  String get statusOnline => 'ऑनलाइन';

  @override
  String get statusOffline => 'ऑफ़लाइन';

  @override
  String get statusChecking => 'जुड़ रहा है';

  @override
  String get languageMenuTooltip => 'भाषा';

  @override
  String get languagePhone => 'फ़ोन की भाषा';

  @override
  String get heroTitle => 'क्या यह सच है?';

  @override
  String get heroSubtitle =>
      'कोई संदेश या लिंक चिपकाएँ, या तस्वीर जाँचें। हम इसे विश्वसनीय स्रोतों से मिलाते हैं।';

  @override
  String get inputLabel => 'संदेश या लिंक चिपकाएँ';

  @override
  String get inputHint => 'या सीधे WhatsApp, ब्राउज़र या गैलरी से साझा करें';

  @override
  String get clear => 'साफ़ करें';

  @override
  String get checkThis => 'इसे जाँचें';

  @override
  String get sourceGallery => 'गैलरी';

  @override
  String get sourceCamera => 'कैमरा';

  @override
  String get sourceFile => 'फ़ाइल';

  @override
  String checkingSubmission(String kind) {
    String _temp0 = intl.Intl.selectLogic(kind, {
      'text': 'यह संदेश जाँचा जा रहा है',
      'link': 'यह लिंक जाँचा जा रहा है',
      'image': 'यह तस्वीर जाँची जा रही है',
      'other': 'यह दस्तावेज़ जाँचा जा रहा है',
    });
    return '$_temp0';
  }

  @override
  String get emptyTitle => 'अभी तक कुछ नहीं जाँचा गया';

  @override
  String get emptyBody =>
      'कोई फ़ॉरवर्ड सीधे Factify में साझा करें, ऊपर चिपकाएँ, या कोई तस्वीर जाँचें। हर निर्णय के साथ उसके स्रोत दिखते हैं — और जब कोई स्रोत नहीं होता, तो यह साफ़ बताया जाता है।';

  @override
  String get working => 'इस बारे में स्रोत खोजे जा रहे हैं';

  @override
  String get checkAgain => 'फिर से जाँचें';

  @override
  String get checkingTitle => 'जाँच हो रही है…';

  @override
  String get stepReading => 'आपने जो भेजा उसे पढ़ना';

  @override
  String get stepSearching => 'भरोसेमंद समाचार और फ़ैक्ट-चेकर खोजना';

  @override
  String get stepComparing => 'हर स्रोत को दावे से मिलाना';

  @override
  String get usuallyTakes => 'एक जाँच में आम तौर पर 20–50 सेकंड लगते हैं।';

  @override
  String get statusNotChecked => 'जाँचा नहीं गया';

  @override
  String get claimNotSearched =>
      'हर जाँच में सबसे अहम पाँच दावे खोजे जाते हैं, यह उनमें नहीं था।';

  @override
  String get claimTimedOut =>
      'इसका कोई स्रोत पढ़ने से पहले समय खत्म हो गया। फिर से जाँचें दबाएँ।';

  @override
  String get claimNothingFound =>
      'हमने भरोसेमंद समाचार और फ़ैक्ट-चेकर खोजे, पर इस बारे में कुछ नहीं मिला।';

  @override
  String claimNoSources(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other:
          'हमने $count स्रोत पढ़े, पर किसी ने सीधे इस बारे में कुछ नहीं कहा।',
      one: 'हमने 1 स्रोत पढ़ा, पर उसमें सीधे इस बारे में कुछ नहीं था।',
    );
    return '$_temp0';
  }

  @override
  String get claimOneSource =>
      'सिर्फ़ एक स्रोत ने इस बारे में बताया। सच कहने से पहले हमें दो स्वतंत्र स्रोत चाहिए।';

  @override
  String elapsedSeconds(int seconds) {
    return '$seconds से.';
  }

  @override
  String get videoAcceptedTitle => 'वीडियो स्वीकार किया गया';

  @override
  String get videoAcceptedBody =>
      'इसमें एक अनुरोध की समय-सीमा से ज़्यादा समय लगता है। जाँच जारी है।';

  @override
  String get retry => 'फिर कोशिश करें';

  @override
  String get reportedNote => 'रिपोर्ट किया गया। हम इस नतीजे को दोबारा देखेंगे।';

  @override
  String get activityEmptyTitle => 'इस सत्र में कोई जाँच नहीं';

  @override
  String get activityEmptyBody =>
      'नतीजे सिर्फ़ इस सत्र तक इसी फ़ोन पर रहते हैं और ऐप बंद होते ही मिट जाते हैं — आपने क्या जाँचा, इसका कोई रिकॉर्ड नहीं रहता।';

  @override
  String get activityFooter =>
      'जान-बूझकर सिर्फ़ इस सत्र तक: आपने क्या जाँचा, वह इस बात का रिकॉर्ड है कि आपको किस पर शक था, और यह ऐप ऐसा रिकॉर्ड नहीं रखता।';

  @override
  String get historyTitle => 'इस सत्र में पहले';

  @override
  String historyCitations(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count उद्धरण',
      one: '1 उद्धरण',
      zero: 'कोई उद्धरण-योग्य साक्ष्य नहीं',
    );
    return '$_temp0';
  }

  @override
  String get errorNoServerAddress =>
      'इस बिल्ड में सर्वर का पता नहीं है। इसे --dart-define=FACTIFY_API=https://your-server के साथ दोबारा बनाएँ।';

  @override
  String get errorShareUnreadable => 'साझा की गई चीज़ पढ़ी नहीं जा सकी।';

  @override
  String get errorShareFileUnopenable =>
      'वह फ़ाइल खोली नहीं जा सकी। उसे फिर से साझा करें, या Factify में गैलरी बटन इस्तेमाल करें।';

  @override
  String errorVideoSlow(String caseId) {
    return 'उस वीडियो में उम्मीद से ज़्यादा समय लग रहा है। मामला $caseId अभी भी प्रोसेस हो रहा है।';
  }

  @override
  String get errorCameraDenied =>
      'आपकी खींची तस्वीर जाँचने के लिए Factify को कैमरे की अनुमति चाहिए।';

  @override
  String get errorFileUnopenable => 'वह फ़ाइल खोली नहीं जा सकी।';

  @override
  String get reportSent => 'धन्यवाद। हम इस नतीजे की समीक्षा करेंगे।';

  @override
  String reportFailed(String reason) {
    return 'रिपोर्ट नहीं हो सका: $reason';
  }

  @override
  String get correctionCopied => 'सुधार कॉपी हो गया — इसे चैट में वापस चिपकाएँ';

  @override
  String get correctionHeader => 'Factify से जाँचा गया:';

  @override
  String get correctionSourceFallback => 'स्रोत';

  @override
  String get correctionNoSource =>
      'कोई भी प्रकाशित स्रोत न इसकी पुष्टि कर सका, न खंडन।';

  @override
  String get correctionSheetTitle => 'इसे चैट में वापस भेजें';

  @override
  String get shareContext => 'संदर्भ के साथ साझा करें';

  @override
  String get correctionSheetBody =>
      'यह तस्वीर चैट में जाएगी, और स्रोतों के लिंक उसके साथ टेक्स्ट में।';

  @override
  String get correctionShareImage => 'तस्वीर साझा करें';

  @override
  String get correctionCopyText => 'सिर्फ़ टेक्स्ट कॉपी करें';

  @override
  String get correctionShareFailed =>
      'साझा करने का विकल्प नहीं खुल सका। सुधार कॉपी कर लिया गया है — इसे चैट में चिपकाएँ।';

  @override
  String get correctionCardFooter =>
      'निर्णय उद्धृत स्रोतों से, कभी मॉडल स्कोर से नहीं।';

  @override
  String get failureTimeout =>
      'Factify को सामान्य से ज़्यादा समय लग रहा है। थोड़ी देर में फिर कोशिश करें।';

  @override
  String get failureUnreachable =>
      'Factify तक पहुँचा नहीं जा सका। अपना कनेक्शन जाँचें और फिर कोशिश करें।';

  @override
  String get failureInterrupted =>
      'Factify से कनेक्शन टूट गया। फिर कोशिश करें।';

  @override
  String get failureUnreadableFile => 'वह फ़ाइल इस फ़ोन से पढ़ी नहीं जा सकी।';

  @override
  String get failureBadReply =>
      'Factify से ऐसा जवाब आया जिसे यह ऐप पढ़ नहीं सका।';

  @override
  String get failureInvalidInput => 'वह इनपुट पढ़ा नहीं जा सका।';

  @override
  String get failureLinkUnchecked =>
      'उस पेज पर जाँचने लायक कुछ नहीं मिला। कुछ साइटें अपने-आप पढ़ने से रोकती हैं, इसलिए लेख का टेक्स्ट कॉपी करके यहाँ चिपकाएँ।';

  @override
  String get failureTooLarge => 'वह फ़ाइल जाँचने के लिए बहुत बड़ी है।';

  @override
  String get failureDailyLimit =>
      'Factify आज की सीमा तक पहुँच गया है। कृपया कल फिर कोशिश करें।';

  @override
  String get failureUnavailable => 'जाँच अभी उपलब्ध नहीं है।';

  @override
  String get failureGeneric => 'Factify वह जाँच पूरी नहीं कर सका।';

  @override
  String get headlineSafeToShare => 'सच';

  @override
  String get subheadSafeToShare => 'विश्वसनीय स्रोत इसकी पुष्टि करते हैं';

  @override
  String get headlineShareWithContext => 'भ्रामक';

  @override
  String get subheadShareWithContext =>
      'आंशिक रूप से सही, पर ज़रूरी संदर्भ छूटा है';

  @override
  String get headlineShareWithCorrection => 'भ्रामक';

  @override
  String get subheadShareWithCorrection => 'इसका एक हिस्सा गलत है';

  @override
  String get headlineDoNotShare => 'झूठ';

  @override
  String get subheadDoNotShare => 'विश्वसनीय स्रोत बताते हैं कि यह गलत है';

  @override
  String get headlineWaitAndRecheck => 'अपुष्ट';

  @override
  String get subheadWaitAndRecheck => 'पुष्टि के लिए अभी बहुत नया है';

  @override
  String get headlineSendToReview => 'अपुष्ट';

  @override
  String get subheadSendToReview => 'हम अभी इसकी पुष्टि या खंडन नहीं कर सके';

  @override
  String citationCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count उद्धरण',
      one: '1 उद्धरण',
      zero: 'कोई उद्धरण नहीं',
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

    return 'साक्ष्य जुटाए गए: $timeString';
  }

  @override
  String get checkedEarlier => 'पहले जाँचा गया';

  @override
  String get reusedNote =>
      'इसी सामग्री की पहले हुई जाँच से लिया गया। नीचे के साक्ष्य उसी जाँच के हैं।';

  @override
  String get englishOnlyNote =>
      'नीचे के कुछ विवरण अभी सिर्फ़ अंग्रेज़ी में हैं।';

  @override
  String get whyNoVerdict => 'अपुष्ट क्यों?';

  @override
  String seeEvidence(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'सभी $count स्रोत देखें',
      one: 'स्रोत देखें',
    );
    return '$_temp0';
  }

  @override
  String get shareCorrection => 'सुधार साझा करें';

  @override
  String get report => 'गलत नतीजे की रिपोर्ट करें';

  @override
  String get reporting => 'रिपोर्ट हो रहा है…';

  @override
  String get evidenceTitle => 'स्रोत';

  @override
  String get theClaim => 'दावा';

  @override
  String evidenceStrength(String band) {
    return 'साक्ष्य की मज़बूती: $band';
  }

  @override
  String strengthBand(String band) {
    String _temp0 = intl.Intl.selectLogic(band, {
      'none': 'कोई नहीं',
      'weak': 'कमज़ोर',
      'moderate': 'मध्यम',
      'strong': 'मज़बूत',
      'conclusive': 'निर्णायक',
      'other': '$band',
    });
    return '$_temp0';
  }

  @override
  String strengthComponent(String name) {
    String _temp0 = intl.Intl.selectLogic(name, {
      'tier_composition': 'साक्ष्य के स्तर',
      'independent_origins': 'स्वतंत्र स्रोत',
      'temporal_confidence': 'तारीख़ की पुष्टि',
      'source_transparency': 'प्रकाशक की पारदर्शिता',
      'conflict_penalty': 'विरोधी साक्ष्य',
      'other': '$name',
    });
    return '$_temp0';
  }

  @override
  String excludedFromScore(String providers) {
    return 'इस स्कोर में शामिल नहीं: $providers';
  }

  @override
  String tierLabel(String tier) {
    String _temp0 = intl.Intl.selectLogic(tier, {
      'A': 'हस्ताक्षरित कंटेंट क्रेडेंशियल',
      'B': 'तारीख़ वाला स्रोत',
      'C': 'प्रकाशित फ़ैक्ट-चेक',
      'other': 'पुष्टि करने वाला स्रोत',
    });
    return '$_temp0';
  }

  @override
  String directionLabel(String direction) {
    String _temp0 = intl.Intl.selectLogic(direction, {
      'supports': 'समर्थन',
      'contradicts': 'खंडन',
      'risk_signal': 'जोखिम संकेत',
      'other': 'संदर्भ',
    });
    return '$_temp0';
  }

  @override
  String anchorPage(int page) {
    return 'पेज $page पर मिला';
  }

  @override
  String anchorParagraph(int paragraph) {
    return 'पैराग्राफ़ $paragraph में मिला';
  }

  @override
  String anchorCharacters(int start, int end) {
    return 'अक्षर $start से $end तक में मिला';
  }

  @override
  String matchBasis(String metric, String value, String threshold) {
    return '$metric $value (सीमा $threshold)';
  }

  @override
  String get openSource => 'स्रोत खोलें';

  @override
  String get noEvidenceTitle => 'कोई उद्धरण-योग्य स्रोत नहीं मिला';

  @override
  String get noEvidenceBody =>
      'इसका मतलब यह नहीं कि सामग्री झूठी है। इसका मतलब है कि ऐसा कोई स्रोत नहीं मिला जिसका हवाला देकर इसका समर्थन या खंडन किया जा सके, इसलिए Factify ने निर्णय नहीं दिया।';

  @override
  String get historyCardTitle => 'इतिहास';

  @override
  String recurrenceCaptions(int count) {
    return 'यही मीडिया $count अलग-अलग कैप्शन के साथ घूम चुका है। असली तस्वीर के साथ आम तौर पर एक-दूसरे को काटने वाली कई कहानियाँ नहीं जुड़तीं।';
  }

  @override
  String get contentCredentials => 'कंटेंट क्रेडेंशियल';

  @override
  String get notCheckedTitle => 'क्या जाँचा नहीं जा सका';

  @override
  String get limitsTitle => 'Factify क्या स्थापित नहीं कर सकता';

  @override
  String get limitAi =>
      'कोई तस्वीर या वीडियो AI से बना है या नहीं। कोई भी डिटेक्टर इतना भरोसेमंद नहीं कि यह बता सके, और हम ऐसा दिखावा नहीं करते।';

  @override
  String get limitUnreported =>
      'जिस बात की कहीं रिपोर्ट नहीं हुई, वह झूठी है या नहीं। कवरेज का न होना किसी भी तरफ़ का साक्ष्य नहीं है।';

  @override
  String get limitPrivate =>
      'निजी सामग्री के बारे में कुछ भी, या ऐसे दावे जिन पर किसी प्रकाशित स्रोत ने बात नहीं की।';

  @override
  String get limitIntent =>
      'इरादा। हम दिखा सकते हैं कि किसी स्रोत ने क्या और कब कहा, यह नहीं कि किसी ने इसे क्यों साझा किया।';

  @override
  String caseLabel(String caseId) {
    return 'मामला $caseId';
  }

  @override
  String checkedIn(int ms) {
    return '$ms ms में जाँचा गया';
  }

  @override
  String get verifyResult => 'इस नतीजे की पुष्टि करें';

  @override
  String get receiptChecking => 'रसीद जाँची जा रही है';

  @override
  String get receiptVerified =>
      'रसीद सत्यापित। हस्ताक्षर के बाद से इस नतीजे के साक्ष्य में कोई बदलाव नहीं हुआ है।';

  @override
  String get receiptFailed =>
      'रसीद सत्यापित नहीं हुई। संग्रहीत साक्ष्य अब हस्ताक्षरित साक्ष्य से मेल नहीं खाता।';

  @override
  String get receiptMissing => 'इस नतीजे के लिए कोई रसीद जारी नहीं हुई।';

  @override
  String sourceRiskTitle(String risk) {
    String _temp0 = intl.Intl.selectLogic(risk, {
      'HIGH': 'प्रकाशक का जोखिम ऊँचा है',
      'MEDIUM': 'प्रकाशक का रिकॉर्ड मिला-जुला है',
      'LOW': 'प्रकाशक का रिकॉर्ड स्थापित है',
      'other': 'प्रकाशक के जोखिम का आकलन नहीं हुआ',
    });
    return '$_temp0';
  }

  @override
  String sourceRiskDetail(String risk) {
    String _temp0 = intl.Intl.selectLogic(risk, {
      'HIGH':
          'हाल ही में पंजीकृत, या अविश्वसनीय सामग्री के रिकॉर्ड वाला। यह प्रकाशक के बारे में है, इस दावे के बारे में नहीं।',
      'MEDIUM':
          'स्रोत के बारे में कुछ ध्यान देने लायक संकेत। यह प्रकाशक के बारे में है, इस दावे के बारे में नहीं।',
      'LOW':
          'स्रोत के बारे में कोई प्रतिकूल संकेत नहीं। यह इस बात का साक्ष्य नहीं कि दावा ख़ुद सही है।',
      'other': 'किसी भी तरफ़ कुछ ज्ञात नहीं।',
    });
    return '$_temp0';
  }

  @override
  String get advisoryHeader =>
      'फोरेंसिक संकेत — पारदर्शिता के लिए दिखाए गए। ये निर्णय में उपयोग नहीं किए जाते और इसे बदल नहीं सकते।';

  @override
  String advisoryCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count संकेत',
      one: '1 संकेत',
    );
    return '$_temp0';
  }

  @override
  String get advisoryFooter =>
      'इनमें से कोई भी यह स्थापित नहीं कर सकता कि सामग्री असली है या गढ़ी हुई। ऊपर का निर्णय केवल उद्धृत स्रोतों पर आधारित है।';

  @override
  String get advisoryRowExcluded =>
      'फोरेंसिक संकेत — इस निर्णय में उपयोग नहीं किए गए।';

  @override
  String get techniqueLabel => 'ऐसी पोस्ट कैसे गुमराह करती हैं';

  @override
  String get techniqueRecycledMediaTitle => 'पुरानी तस्वीर, नई कहानी';

  @override
  String get techniqueRecycledMediaBody =>
      'पहले प्रकाशित हो चुकी तस्वीर को फिर ऐसे फैलाया जाता है जैसे वह कुछ नया दिखा रही हो। किसी फ़ोटो पर भरोसा करने से पहले देखें कि वह पहली बार कब सामने आई।';

  @override
  String get techniqueMissingContextTitle => 'अधूरा संदर्भ';

  @override
  String get techniqueMissingContextBody =>
      'प्रकाशित सामग्री को ऐसे पेश किया जाता है कि वह कुछ ऐसा जताए जो उसके स्रोत नहीं कहते। सोचें कि पोस्ट क्या छोड़ रही है।';

  @override
  String get techniqueMisattributedQuoteTitle =>
      'किसी के मुँह में डाले गए शब्द';

  @override
  String get techniqueMisattributedQuoteBody =>
      'किसी के नाम से ऐसा बयान, जिसे कहते हुए प्रकाशित स्रोतों में उनका कोई रिकॉर्ड नहीं। मूल भाषण या बयान खोजें।';

  @override
  String get techniqueTwistedNumberTitle => 'तोड़ा-मरोड़ा आँकड़ा';

  @override
  String get techniqueTwistedNumberBody =>
      'कोई संख्या बदल दी जाती है, या ऐसे स्रोत से ली जाती है जो कुछ और कहता है। आँकड़े को उसके मूल स्रोत में खोजें।';

  @override
  String get techniqueWrongIdentityTitle => 'गलत पहचान';

  @override
  String get techniqueWrongIdentityBody =>
      'किसी व्यक्ति या जगह को कोई और बताया जाता है। नामों और जगहों को किसी तारीख वाले स्रोत से मिलाएँ।';

  @override
  String get timelineTitle => 'समय-रेखा';

  @override
  String get timelineFirstChecked => 'Factify ने पहली बार जाँचा';

  @override
  String get timelineRetrieved => 'इस नतीजे के लिए साक्ष्य जुटाए गए';

  @override
  String get inputAnchorLabel => 'आपकी भेजी सामग्री में यह कहाँ है';

  @override
  String inputAnchorCharacters(int start, int end) {
    return 'अक्षर $start–$end';
  }

  @override
  String inputAnchorPage(int page) {
    return 'पेज $page';
  }

  @override
  String inputAnchorMoment(int seconds) {
    return 'वीडियो में $seconds सेकंड पर';
  }

  @override
  String get mediaMatchYours => 'आपकी तस्वीर';

  @override
  String get mediaMatchEarlier => 'पहले प्रकाशित तस्वीर से मेल खाती है';

  @override
  String strengthComponentCitations(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count स्रोत',
      one: '1 स्रोत',
    );
    return '$_temp0';
  }

  @override
  String uploading(int percent) {
    return 'अपलोड हो रहा है $percent%';
  }

  @override
  String get clipboardOffer => 'आपने कुछ टेक्स्ट कॉपी किया है। उसे जाँचें?';

  @override
  String get clipboardPasteAndCheck => 'चिपकाएँ और जाँचें';

  @override
  String get clipboardDismiss => 'अभी नहीं';

  @override
  String confidence(int value) {
    return '$value% भरोसा';
  }

  @override
  String get unconfirmedBody =>
      'हमें ऐसे पर्याप्त विश्वसनीय स्रोत नहीं मिले जो सीधे इस बारे में बात करते हों। पुष्टि होने तक सावधानी बरतें।';

  @override
  String get sourcesTitle => 'स्रोत';

  @override
  String get sourceConfirms => 'पुष्टि करता है';

  @override
  String get sourceRefutes => 'खंडन करता है';

  @override
  String credibility(String level) {
    String _temp0 = intl.Intl.selectLogic(level, {
      'HIGH': 'अत्यधिक विश्वसनीय',
      'MEDIUM': 'विश्वसनीय',
      'other': 'स्रोत',
    });
    return '$_temp0';
  }

  @override
  String get howWeCheckedTitle => 'हमने कैसे जाँचा';

  @override
  String get howWeCheckedBody =>
      'हमने विश्वसनीय समाचार संस्थानों, फ़ैक्ट-चेकर्स और आधिकारिक स्रोतों में खोजा, हर एक को पढ़ा, और सिर्फ़ वही रखे जो सीधे इस दावे के बारे में हैं। नतीजा उन्हीं स्रोतों की बात पर आधारित है, उनकी विश्वसनीयता के हिसाब से।';

  @override
  String get whatWeCheckedTitle => 'हमने क्या जाँचा';

  @override
  String checkedAt(DateTime time) {
    final intl.DateFormat timeDateFormat = intl.DateFormat(
      'd MMM, HH:mm',
      localeName,
    );
    final String timeString = timeDateFormat.format(time);

    return '$timeString को जाँचा गया';
  }

  @override
  String get incompleteNote =>
      'कुछ स्रोत समय पर जाँचे नहीं जा सके, इसलिए यह नतीजा अधूरा हो सकता है।';

  @override
  String get account => 'खाता';

  @override
  String get signIn => 'साइन इन';

  @override
  String get signInTitle => 'Factify में साइन इन करें';

  @override
  String get signInBody =>
      'अपनी प्रोफ़ाइल और क्रेडिट किसी भी फ़ोन पर रखें। आप क्या जाँचते हैं, इसका हम कोई रिकॉर्ड नहीं रखते।';

  @override
  String get emailLabel => 'ईमेल';

  @override
  String get orDivider => 'या';

  @override
  String get continueWithGoogle => 'Google से जारी रखें';

  @override
  String get signInUnavailable =>
      'अभी साइन-इन तक नहीं पहुँचा जा सकता। अपना कनेक्शन जाँचें और फिर कोशिश करें।';

  @override
  String get signOut => 'साइन आउट';

  @override
  String get creditsTitle => 'क्रेडिट';

  @override
  String creditsLeft(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count क्रेडिट बाकी',
      one: '1 क्रेडिट बाकी',
    );
    return '$_temp0';
  }

  @override
  String creditsUsed(int count) {
    return '$count इस्तेमाल हुए';
  }

  @override
  String creditCosts(int check, int deep) {
    return 'एक जाँच: $check · गहरी जाँच: $deep';
  }

  @override
  String checksSoFar(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'अब तक $count जाँचें',
      one: 'अब तक 1 जाँच',
    );
    return '$_temp0';
  }

  @override
  String memberSince(DateTime date) {
    final intl.DateFormat dateDateFormat = intl.DateFormat.yMMMd(localeName);
    final String dateString = dateDateFormat.format(date);

    return '$dateString से सदस्य';
  }

  @override
  String get planBeta => 'मुफ़्त · बीटा, अभी कोई सीमा नहीं';

  @override
  String get editName => 'नाम बदलें';

  @override
  String get nameLabel => 'नाम';

  @override
  String get save => 'सहेजें';

  @override
  String get cancel => 'रद्द करें';

  @override
  String get failureSignedOut =>
      'आपका साइन-इन खत्म हो गया है। अपने खाते से फिर से साइन इन करें।';

  @override
  String get failureOutOfCredits => 'अभी आपके क्रेडिट खत्म हो गए हैं।';

  @override
  String get authNetwork => 'साइन-इन तक नहीं पहुँच सके। अपना कनेक्शन जाँचें।';

  @override
  String get authTooMany => 'बहुत सारी कोशिशें। एक मिनट रुककर फिर कोशिश करें।';

  @override
  String get authGeneric => 'साइन-इन नहीं हुआ। फिर कोशिश करें।';

  @override
  String get deepCheck => 'गहरी जाँच';

  @override
  String get deepCheckHint => 'ज़्यादा दावे और स्रोत · 1–3 मिनट लगते हैं';

  @override
  String get deepChecking => 'गहरी जाँच…';

  @override
  String deepProgress(int done, int total) {
    return '$total में से $done दावे जाँचे गए';
  }

  @override
  String get deepUsuallyTakes => 'गहरी जाँच में आम तौर पर 1–3 मिनट लगते हैं।';

  @override
  String get deepTooSlow =>
      'गहरी जाँच उम्मीद से ज़्यादा समय ले रही है। एक मिनट बाद फिर से जाँचें।';

  @override
  String get imageReadTitle => 'आपकी तस्वीर में हमने क्या पढ़ा';

  @override
  String imageKind(String kind) {
    String _temp0 = intl.Intl.selectLogic(kind, {
      'NEWS_ARTICLE': 'समाचार लेख',
      'SOCIAL_POST': 'सोशल मीडिया पोस्ट',
      'CHAT_MESSAGE': 'चैट फ़ॉरवर्ड',
      'TV_GRAPHIC': 'टीवी समाचार ग्राफ़िक',
      'POSTER': 'पोस्टर',
      'DOCUMENT': 'दस्तावेज़',
      'PHOTO': 'फ़ोटो',
      'MEME': 'मीम',
      'other': 'तस्वीर',
    });
    return '$_temp0';
  }

  @override
  String imageFrom(String publisher) {
    return 'दिखाता है: $publisher';
  }

  @override
  String get imageTextLabel => 'तस्वीर में लिखा पाठ';

  @override
  String get imageNoText =>
      'इस तस्वीर में हमें कोई पाठ नहीं मिला, इसलिए हमने तस्वीर की ही जाँच की।';

  @override
  String get imageShowAllText => 'पूरा पाठ दिखाएँ';

  @override
  String get imageShowLessText => 'कम दिखाएँ';

  @override
  String get splashTagline => 'साझा करने से पहले जाँचें';

  @override
  String get welcomeTitle => 'साझा करने से पहले जानें कि सच क्या है';

  @override
  String get welcomeBody =>
      'Factify समाचार, फ़ॉरवर्ड, तस्वीरें और दस्तावेज़ भरोसेमंद स्रोतों से जाँचता है, और इस्तेमाल किया गया हर स्रोत दिखाता है।';

  @override
  String get welcomePointSources => 'हर जवाब के साथ उसके स्रोत';

  @override
  String get welcomePointInputs => 'पाठ, लिंक, तस्वीरें और PDF';

  @override
  String get welcomePointLanguages => 'अंग्रेज़ी और हिंदी में';

  @override
  String get welcomeSignInTitle => 'अपना खाता बनाएँ';

  @override
  String get welcomeSignInBody =>
      'जाँच के लिए खाता ज़रूरी है। अपने ईमेल और पासवर्ड से, या Google से साइन अप या साइन इन करें।';

  @override
  String get tabHome => 'होम';

  @override
  String get tabHistory => 'इतिहास';

  @override
  String get tabProfile => 'प्रोफ़ाइल';

  @override
  String homeGreeting(String name) {
    return 'नमस्ते, $name';
  }

  @override
  String get homeGreetingGuest => 'नमस्ते';

  @override
  String get homeTitle => 'आप क्या जाँचना चाहते हैं?';

  @override
  String get inputTypeText => 'पाठ या लिंक';

  @override
  String get inputTypeImage => 'तस्वीर';

  @override
  String get inputTypePdf => 'PDF फ़ाइल';

  @override
  String get inputTextHint => 'कोई संदेश, दावा या समाचार लिंक चिपकाएँ';

  @override
  String get inputLinkDetected => 'लिंक मिला। हम पेज पढ़कर उसकी जाँच करेंगे।';

  @override
  String get inputLocked =>
      'दूसरा प्रकार चुनने के लिए पहले जोड़ी गई चीज़ हटाएँ।';

  @override
  String get removeInput => 'हटाएँ';

  @override
  String get pasteButton => 'चिपकाएँ';

  @override
  String get pickImageTitle => 'तस्वीर जोड़ें';

  @override
  String get pickImageBody =>
      'स्क्रीनशॉट, व्हाट्सऐप फ़ॉरवर्ड या फ़ोटो। हम इसमें लिखा पाठ पढ़कर उसकी जाँच करते हैं।';

  @override
  String get pickPdfTitle => 'PDF जोड़ें';

  @override
  String get pickPdfBody =>
      'कोई परिपत्र, सूचना या दस्तावेज़। हम इसे पढ़कर इसके दावों की जाँच करते हैं।';

  @override
  String get choosePdf => 'PDF चुनें';

  @override
  String get notAPdf => 'यह फ़ाइल PDF नहीं है। PDF चुनें, या तस्वीर पर जाएँ।';

  @override
  String get checkNow => 'अभी जाँचें';

  @override
  String get checkingOf => 'जाँच हो रही है';

  @override
  String get checkingCancel => 'इंतज़ार बंद करें';

  @override
  String get checkingFailedTitle => 'जाँच पूरी नहीं हुई';

  @override
  String get backToHome => 'होम पर लौटें';

  @override
  String get resultTitle => 'नतीजा';

  @override
  String get newCheck => 'नई जाँच';

  @override
  String get historyEmptyTitle => 'अभी कोई जाँच नहीं';

  @override
  String get historyEmptyBody =>
      'आप जो भी जाँचते हैं वह अपने स्रोतों के साथ यहाँ दिखता है, ताकि आप उस पर लौट सकें।';

  @override
  String get historyToday => 'आज';

  @override
  String get historyYesterday => 'कल';

  @override
  String get historyClear => 'इतिहास मिटाएँ';

  @override
  String get historyClearConfirm => 'इस फ़ोन से सभी सहेजी गई जाँचें मिटा दें?';

  @override
  String get historyDelete => 'मिटाएँ';

  @override
  String get historyFilterAll => 'सभी';

  @override
  String get historyStoredNote =>
      'सिर्फ़ इसी फ़ोन पर सहेजा गया। आप जो जाँचते हैं, वह हमारे सर्वर पर नहीं रखा जाता। किसी जाँच को मिटाने के लिए उसे बाईं ओर सरकाएँ।';

  @override
  String historySources(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count स्रोत',
      one: '1 स्रोत',
      zero: 'कोई स्रोत नहीं',
    );
    return '$_temp0';
  }

  @override
  String get profileTitle => 'प्रोफ़ाइल';

  @override
  String get guestTitle => 'आप साइन इन नहीं हैं';

  @override
  String get guestBody =>
      'समाचार जाँचने और अपने क्रेडिट रखने के लिए साइन इन करें।';

  @override
  String get signInOrCreate => 'साइन इन करें या खाता बनाएँ';

  @override
  String signedInWith(String method) {
    String _temp0 = intl.Intl.selectLogic(method, {
      'google': 'Google से साइन इन',
      'other': 'ईमेल से साइन इन',
    });
    return '$_temp0';
  }

  @override
  String get profileDetails => 'खाते की जानकारी';

  @override
  String get profileEmail => 'ईमेल';

  @override
  String get profileName => 'नाम';

  @override
  String get profilePlan => 'प्लान';

  @override
  String get profileJoined => 'सदस्य बने';

  @override
  String get settingsTitle => 'सेटिंग्स';

  @override
  String get settingLanguage => 'भाषा';

  @override
  String get settingHistory => 'सहेजी गई जाँचें';

  @override
  String settingHistoryCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'इस फ़ोन पर $count जाँचें',
      one: 'इस फ़ोन पर 1 जाँच',
      zero: 'कुछ सहेजा नहीं गया',
    );
    return '$_temp0';
  }

  @override
  String get aboutTitle => 'Factify के बारे में';

  @override
  String get aboutBody =>
      'Factify आपकी साझा की गई चीज़ों को भरोसेमंद स्रोतों से जाँचता है और हमेशा उन्हें दिखाता है। जब स्रोतों से बात तय न हो, तो वह अंदाज़ा लगाने के बजाय अपुष्ट कहता है।';

  @override
  String get serviceStatus => 'सेवा';

  @override
  String get done => 'हो गया';

  @override
  String get modeSignIn => 'साइन इन';

  @override
  String get modeCreateAccount => 'खाता बनाएँ';

  @override
  String get welcomeBackTitle => 'फिर से स्वागत है';

  @override
  String get welcomeBackBody =>
      'अपने ईमेल और पासवर्ड से, या Google से साइन इन करें।';

  @override
  String get passwordLabel => 'पासवर्ड';

  @override
  String get confirmPasswordLabel => 'पासवर्ड दोबारा लिखें';

  @override
  String passwordHint(int min) {
    return 'कम से कम $min अक्षर';
  }

  @override
  String get showPassword => 'पासवर्ड दिखाएँ';

  @override
  String get hidePassword => 'पासवर्ड छिपाएँ';

  @override
  String get passwordsDontMatch => 'दोनों पासवर्ड एक जैसे नहीं हैं।';

  @override
  String get createAccountButton => 'खाता बनाएँ';

  @override
  String get signInButton => 'साइन इन करें';

  @override
  String get authInvalidEmail => 'यह ईमेल पता सही नहीं लगता।';

  @override
  String authWeakPassword(int min) {
    return 'कम से कम $min अक्षरों का पासवर्ड रखें।';
  }

  @override
  String get authEmailTaken =>
      'इस ईमेल से पहले से एक खाता है। इसके बजाय साइन इन करें।';

  @override
  String get authWrongCredentials =>
      'यह ईमेल और पासवर्ड किसी खाते से मेल नहीं खाते।';

  @override
  String get authUseGoogle =>
      'यह खाता Google से बनाया गया था। Google से जारी रखें चुनें।';

  @override
  String get authGoogleFailed =>
      'Google साइन-इन पूरा नहीं हुआ। फिर से कोशिश करें।';

  @override
  String get authGoogleUnavailable =>
      'इस सर्वर पर Google साइन-इन अभी चालू नहीं है। अपने ईमेल और पासवर्ड का उपयोग करें।';

  @override
  String get yourPicture => 'आपकी तस्वीर';

  @override
  String get headlineNothingToCheck => 'जाँचने लायक कुछ नहीं';

  @override
  String get subheadNothingToCheck => 'इसमें कोई दावा नहीं मिला';

  @override
  String get nothingToCheckPicture =>
      'हमने यह तस्वीर पढ़ी, पर इसमें जाँचने लायक कोई दावा नहीं मिला - न कोई ख़बर, न आँकड़ा, न कोई घोषणा, बस एक तस्वीर। इसमें पुष्टि करने या नकारने को कुछ नहीं है।';

  @override
  String get nothingToCheckText =>
      'इसमें हमें कोई तथ्यात्मक दावा नहीं मिला - यह राय, मज़ाक या बातचीत जैसा है, इसलिए इसमें पुष्टि करने या नकारने को कुछ नहीं है।';

  @override
  String get searchUnavailableNote =>
      'हमारी समाचार खोज से संपर्क नहीं हो सका, इसलिए इसे समाचार रिपोर्टों से नहीं मिलाया गया। थोड़ी देर बाद फिर से जाँचें दबाएँ।';

  @override
  String get claimSearchUnavailable =>
      'हमारी समाचार खोज से संपर्क नहीं हो सका, इसलिए इसके लिए कोई समाचार रिपोर्ट नहीं देखी गई। इसका मतलब यह नहीं कि कुछ नहीं मिला।';

  @override
  String get documentReadTitle => 'आपके दस्तावेज़ में हमने क्या पढ़ा';

  @override
  String get pasteCopiedText => 'चिपकाएँ';

  @override
  String get deepChip => 'गहरी';

  @override
  String get deepChipOnHint => 'गहरी जाँच चालू है';

  @override
  String get shareFromWhatsApp => 'या WhatsApp से शेयर करें';

  @override
  String get checkTakes => 'आम तौर पर 20–50 सेकंड लगते हैं';

  @override
  String get checkTakesDeep => 'गहरी जाँच · 1–3 मिनट';

  @override
  String get recentTitle => 'हाल की जाँचें';

  @override
  String get seeAll => 'सभी देखें';

  @override
  String get historySearchHint => 'पिछली जाँचें खोजें';

  @override
  String historyWeekRange(String range) {
    return 'इस हफ़्ते · $range';
  }

  @override
  String historyChecksUnit(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'जाँचें',
      one: 'जाँच',
    );
    return '$_temp0';
  }

  @override
  String historyChecksCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count जाँचें',
      one: '1 जाँच',
    );
    return '$_temp0';
  }

  @override
  String historyBusiest(String days) {
    return 'सबसे ज़्यादा: $days';
  }

  @override
  String historyDaysJoin(String first, String second) {
    return '$first और $second';
  }

  @override
  String historyStopped(int count) {
    return 'इस हफ़्ते आपने $count झूठे या भ्रामक फ़ॉरवर्ड फैलने से रोके।';
  }

  @override
  String get historyNoResults => 'इस खोज से कोई जाँच नहीं मिली।';

  @override
  String get switchLanguage => 'भाषा बदलें';
}
