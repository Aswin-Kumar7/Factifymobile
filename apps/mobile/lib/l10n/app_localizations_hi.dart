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
  String get heroTitle => 'निर्णय उद्धृत स्रोतों से,\nमॉडल स्कोर से कभी नहीं';

  @override
  String get heroSubtitle =>
      'फ़ॉरवर्ड चिपकाएँ, लिंक डालें, या कोई तस्वीर जाँचें।';

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
      'कोई फ़ॉरवर्ड सीधे Facify में साझा करें, ऊपर चिपकाएँ, या कोई तस्वीर जाँचें। हर निर्णय के साथ उसके स्रोत दिखते हैं — और जब कोई स्रोत नहीं होता, तो यह साफ़ बताया जाता है।';

  @override
  String get working => 'इस बारे में स्रोत खोजे जा रहे हैं';

  @override
  String get videoAcceptedTitle => 'वीडियो स्वीकार किया गया';

  @override
  String get videoAcceptedBody =>
      'इसमें एक अनुरोध की समय-सीमा से ज़्यादा समय लगता है। जाँच जारी है।';

  @override
  String get retry => 'फिर कोशिश करें';

  @override
  String get reportedNote => 'रिपोर्ट किया गया। एक समीक्षक यह मामला देखेगा।';

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
      'इस बिल्ड में सर्वर का पता नहीं है। इसे --dart-define=FACIFY_API=https://your-server के साथ दोबारा बनाएँ।';

  @override
  String get errorShareUnreadable => 'साझा की गई चीज़ पढ़ी नहीं जा सकी।';

  @override
  String get errorShareFileUnopenable =>
      'वह फ़ाइल खोली नहीं जा सकी। उसे फिर से साझा करें, या Facify में गैलरी बटन इस्तेमाल करें।';

  @override
  String errorVideoSlow(String caseId) {
    return 'उस वीडियो में उम्मीद से ज़्यादा समय लग रहा है। मामला $caseId अभी भी प्रोसेस हो रहा है।';
  }

  @override
  String get errorCameraDenied =>
      'आपकी खींची तस्वीर जाँचने के लिए Facify को कैमरे की अनुमति चाहिए।';

  @override
  String get errorFileUnopenable => 'वह फ़ाइल खोली नहीं जा सकी।';

  @override
  String get reportSent => 'मानवीय समीक्षा के लिए भेजा गया';

  @override
  String reportFailed(String reason) {
    return 'रिपोर्ट नहीं हो सका: $reason';
  }

  @override
  String get correctionCopied => 'सुधार कॉपी हो गया — इसे चैट में वापस चिपकाएँ';

  @override
  String get correctionHeader => 'Facify से जाँचा गया:';

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
      'Facify को सामान्य से ज़्यादा समय लग रहा है। थोड़ी देर में फिर कोशिश करें।';

  @override
  String get failureUnreachable =>
      'Facify तक पहुँचा नहीं जा सका। अपना कनेक्शन जाँचें और फिर कोशिश करें।';

  @override
  String get failureInterrupted => 'Facify से कनेक्शन टूट गया। फिर कोशिश करें।';

  @override
  String get failureUnreadableFile => 'वह फ़ाइल इस फ़ोन से पढ़ी नहीं जा सकी।';

  @override
  String get failureBadReply =>
      'Facify से ऐसा जवाब आया जिसे यह ऐप पढ़ नहीं सका।';

  @override
  String get failureInvalidInput => 'वह इनपुट पढ़ा नहीं जा सका।';

  @override
  String get failureTooLarge => 'वह फ़ाइल जाँचने के लिए बहुत बड़ी है।';

  @override
  String get failureDailyLimit =>
      'Facify आज की सीमा तक पहुँच गया है। कृपया कल फिर कोशिश करें।';

  @override
  String get failureUnavailable => 'जाँच अभी उपलब्ध नहीं है।';

  @override
  String get failureGeneric => 'Facify वह जाँच पूरी नहीं कर सका।';

  @override
  String get headlineSafeToShare => 'इसका कोई खंडन नहीं मिला';

  @override
  String get subheadSafeToShare => 'स्वतंत्र स्रोत सहमत हैं';

  @override
  String get headlineShareWithContext => 'सही, पर संदर्भ अधूरा है';

  @override
  String get subheadShareWithContext => 'इसके साथ संदर्भ भी साझा करें';

  @override
  String get headlineShareWithCorrection => 'इसमें एक बात ग़लत है';

  @override
  String get subheadShareWithCorrection => 'केवल सुधार के साथ साझा करें';

  @override
  String get headlineDoNotShare => 'स्रोतों ने इसका खंडन किया है';

  @override
  String get subheadDoNotShare => 'प्रकाशित स्रोत कुछ और कहते हैं';

  @override
  String get headlineWaitAndRecheck => 'मामला अभी ताज़ा है';

  @override
  String get subheadWaitAndRecheck => 'शुरुआती ख़बरें अक्सर बदल जाती हैं';

  @override
  String get headlineSendToReview => 'निर्णय के लिए पर्याप्त साक्ष्य नहीं';

  @override
  String get subheadSendToReview => 'मानवीय समीक्षा के लिए भेजा गया';

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
  String get whyNoVerdict => 'निर्णय क्यों नहीं?';

  @override
  String seeEvidence(int count) {
    return 'साक्ष्य देखें ($count)';
  }

  @override
  String get shareCorrection => 'सुधार साझा करें';

  @override
  String get report => 'रिपोर्ट करें';

  @override
  String get reporting => 'रिपोर्ट हो रहा है…';

  @override
  String get evidenceTitle => 'साक्ष्य';

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
      'इसका मतलब यह नहीं कि सामग्री झूठी है। इसका मतलब है कि ऐसा कोई स्रोत नहीं मिला जिसका हवाला देकर इसका समर्थन या खंडन किया जा सके, इसलिए Facify ने निर्णय नहीं दिया।';

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
  String get limitsTitle => 'Facify क्या स्थापित नहीं कर सकता';

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
  String get techniqueDistortedEventTitle => 'बदली हुई घटना';

  @override
  String get techniqueDistortedEventBody =>
      'किसी घटना को प्रकाशित स्रोतों की रिपोर्ट से अलग ढंग से बताया जाता है। एक से ज़्यादा समाचार स्रोतों की रिपोर्ट देखें।';

  @override
  String get timelineTitle => 'समय-रेखा';

  @override
  String get timelineFirstChecked => 'Facify ने पहली बार जाँचा';

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
}
