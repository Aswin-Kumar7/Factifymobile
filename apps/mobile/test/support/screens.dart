/// Screens built the same way for the golden images and the accessibility sweep.
///
/// Each builds one v5 screen from fixed data: a signed-in person, a week of checks
/// and the four verdicts, at 26 September 2026, 10:43 (a Saturday, as in the design
/// gallery), so an image drawn today matches one drawn next month.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:clock/clock.dart';
import 'package:factify_mobile/api/check_events.dart';
import 'package:factify_mobile/api/client.dart';
import 'package:factify_mobile/app_services.dart';
import 'package:factify_mobile/auth/auth_service.dart';
import 'package:factify_mobile/checks/check_job.dart';
import 'package:factify_mobile/history/history_store.dart';
import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/l10n/language_preference.dart';
import 'package:factify_mobile/models/submission.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:factify_mobile/theme/theme.dart';
import 'package:factify_mobile/theme/theme_mode_preference.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// Saturday, 26 September 2026, 10:43.
final DateTime galleryNow = DateTime(2026, 9, 26, 10, 43);

const String sampleClaim =
    'Govt to pay ₹5,000 a month to every woman from 1 July. Register now at the link before slots close.';

/// The app's own fonts, and the Material icon font, so images show real text
/// rather than the test font's boxes.
Future<void> loadAppFonts() async {
  const families = {
    'Newsreader': [
      'Newsreader-Regular',
      'Newsreader-Italic',
      'Newsreader-Medium',
      'Newsreader-SemiBold',
    ],
    'Geist': ['Geist-Regular', 'Geist-Medium', 'Geist-SemiBold', 'Geist-Bold'],
    'GeistMono': ['GeistMono-Regular', 'GeistMono-Medium'],
    'TiroDevanagariHindi': ['TiroDevanagariHindi-Regular', 'TiroDevanagariHindi-Italic'],
    'NotoSansDevanagari': [
      'NotoSansDevanagari-Regular',
      'NotoSansDevanagari-Medium',
      'NotoSansDevanagari-SemiBold',
      'NotoSansDevanagari-Bold',
    ],
    'PhosphorRegular': ['PhosphorRegular'],
    'PhosphorFill': ['PhosphorFill'],
  };
  for (final MapEntry(key: family, value: files) in families.entries) {
    final loader = FontLoader(family);
    for (final file in files) {
      loader.addFont(rootBundle.load('assets/fonts/$file.ttf'));
    }
    await loader.load();
  }
  final flutterRoot = Platform.environment['FLUTTER_ROOT'];
  final icons = File(
    '${flutterRoot ?? ''}/bin/cache/artifacts/material_fonts/materialicons-regular.otf',
  );
  if (flutterRoot != null && icons.existsSync()) {
    final bytes = icons.readAsBytesSync();
    await (FontLoader('MaterialIcons')..addFont(Future.value(ByteData.view(bytes.buffer)))).load();
  }
}

/// A 360-wide phone, as the design gallery draws them.
void galleryPhone(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2280);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
}

Map<String, dynamic> _evidence(
  String id,
  String publisher,
  String url,
  String direction,
  String tier,
) => {
  'id': id,
  'tier': tier,
  'kind': tier == 'C' ? 'fact_check' : 'dated_source',
  'direction': direction,
  'method': 'claim_review',
  'finding': 'f',
  'citation_url': url,
  'snapshot_id': 's',
  'source_excerpt': 'No such scheme has been announced by the Government of India.',
  'source_anchor': {'paragraph_index': 3},
  'match_basis': {'metric': 'claim_similarity', 'value': 0.86, 'threshold': 0.62},
  'match_quality': 'STRONG',
  'publisher': publisher,
  'credibility': 'HIGH',
  'published_on': '2026-09-24',
};

/// One of the four verdicts, as the server would send it.
Verdict sampleVerdict(FactVerdict kind) => Verdict.fromJson(sampleVerdictJson(kind));

/// The same, as JSON.
Map<String, dynamic> sampleVerdictJson(FactVerdict kind) {
  final (action, verdict, status, direction, confidence, summary) = switch (kind) {
    FactVerdict.falseClaim => (
      'DO_NOT_SHARE',
      'FALSE',
      'CONTRADICTED',
      'contradicts',
      91,
      'No such scheme has been announced. PIB Fact Check and Alt News traced it to a lookalike registration site.',
    ),
    FactVerdict.misleading => (
      'SHARE_WITH_CONTEXT',
      'MISLEADING',
      'MISLEADING_CONTEXT',
      'contextualizes',
      78,
      'The photo is real but was taken during the 2019 floods, not this morning.',
    ),
    FactVerdict.trueClaim => (
      'SAFE_TO_SHARE',
      'TRUE',
      'SUPPORTED',
      'supports',
      88,
      'The RBI kept the repo rate at 6.5% in its September review.',
    ),
    FactVerdict.unconfirmed => (
      'SEND_TO_REVIEW',
      'UNCONFIRMED',
      'UNVERIFIED',
      '',
      null,
      'We searched official sources and reliable news outlets and found nothing reporting this.',
    ),
  };
  final decided = kind != FactVerdict.unconfirmed;
  return {
    'case_id': 'case-${kind.name}',
    'contract_version': '1.3',
    'action': action,
    'action_reason': 'r',
    'verdict': verdict,
    'confidence': confidence,
    'summary': summary,
    'rule_version': 'v',
    'claims': [
      {
        'id': 'cl_1',
        'text': 'Govt to pay ₹5,000 a month to every woman from 1 July.',
        'claim_type': 'EVENT',
        'status': status,
        'severity': 'HIGH',
        'importance': 'HEADLINE',
        'reason': decided
            ? 'Two published fact-checks and a dated report address it directly.'
            : 'We read 10 sources and none addressed this directly.',
        'rule_id': 'r',
        'rule_version': 'v',
        'confidence': confidence,
        'input_anchor': {'char_start': 0, 'char_end': 54},
        'technique': kind == FactVerdict.falseClaim ? 'MISATTRIBUTED_QUOTE' : null,
        'strength': {
          'score': 0.9,
          'band': 'STRONG',
          'version': 'v',
          'components': [
            {
              'name': 'tier_composition',
              'value': 0.92,
              'explanation': '2 fact-checks, 1 dated news report',
            },
            {
              'name': 'independent_origins',
              'value': 0.86,
              'explanation': '3 publishers, no shared origin',
            },
          ],
        },
        'evidence': [
          if (decided) ...[
            _evidence('ev_1', 'PIB Fact Check', 'https://pib.gov.in/factcheck/1', direction, 'C'),
            _evidence('ev_2', 'Alt News', 'https://www.altnews.in/scheme', direction, 'C'),
            _evidence('ev_3', 'The Hindu', 'https://www.thehindu.com/news', direction, 'B'),
          ],
        ],
      },
    ],
    'advisories': <Object>[],
    'skipped': <Object>[],
    'retrieved_at': '2026-09-26T05:12:00Z',
    'from_cache': false,
    'elapsed_ms': 31000,
    'receipt_url': '/v1/receipts/r1',
    'receipt': {'receipt_id': 'DE98FB7A', 'verified': true, 'issued_at': '2026-09-26T05:12:00Z'},
  };
}

/// A server that knows a signed-in person, and answers a check with [sampleVerdict]'s
/// False - or, with [hold], never answers it (a check caught mid-way).
MockClient _server({bool hold = false}) => MockClient((request) async {
  final path = request.url.path;
  if (path == '/v1/verify') {
    if (hold) return Completer<http.Response>().future;
    // As bytes: the body carries ₹, which a plain string response refuses.
    return http.Response.bytes(
      utf8.encode(jsonEncode(sampleVerdictJson(FactVerdict.falseClaim))),
      200,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );
  }
  if (path == '/readyz') return http.Response('{"ready": true, "missing": []}', 200);
  if (path == '/v1/auth/config') {
    return http.Response('{"enabled": true, "required": true, "providers": ["password"]}', 200);
  }
  if (path == '/v1/auth/login') {
    return http.Response(
      jsonEncode({
        'access_token': 't',
        'expires_at': DateTime.now().add(const Duration(days: 30)).toIso8601String(),
        'method': 'google',
        'email': 'aarav.mehta@gmail.com',
      }),
      200,
    );
  }
  if (path == '/v1/me') {
    return http.Response(
      jsonEncode({
        'id': 'u-1',
        'email': 'aarav.mehta@gmail.com',
        'name': 'Aarav Mehta',
        'plan': 'free',
        'joined_at': '2026-08-02T10:00:00Z',
        'credits': {
          'balance': 42,
          'used': 8,
          'checks': 11,
          'check_cost': 1,
          'deep_check_cost': 3,
          'limited': false,
        },
      }),
      200,
    );
  }
  return http.Response('{}', 404);
});

/// A signed-in person with a week of checks kept on the phone.
Future<AppServices> galleryServices({
  ThemeMode theme = ThemeMode.light,
  Locale? locale,
  bool holdChecks = false,
}) async {
  final server = _server(hold: holdChecks);
  final client = FactifyClient(baseUrl: 'http://factify.test', httpClient: server);
  final auth = AuthService(client: client, httpClient: server, persist: false);
  client.tokenProvider = auth.accessToken;
  await auth.start();
  await auth.signIn(email: 'aarav.mehta@gmail.com', password: 'long enough');
  await auth.refreshAccount();
  final history = HistoryStore();
  // Mon 1 True; Tue 2 Unconfirmed; Thu 1 False, 1 Misleading; Fri 3; Sat (today) 2.
  final week = <(int, FactVerdict)>[
    (21, FactVerdict.trueClaim),
    (22, FactVerdict.unconfirmed),
    (22, FactVerdict.unconfirmed),
    (24, FactVerdict.falseClaim),
    (24, FactVerdict.misleading),
    (25, FactVerdict.unconfirmed),
    (25, FactVerdict.trueClaim),
    (25, FactVerdict.falseClaim),
    (26, FactVerdict.unconfirmed),
    (26, FactVerdict.falseClaim),
  ];
  for (final (i, (day, kind)) in week.indexed) {
    await withClock(
      Clock.fixed(DateTime(2026, 9, day, 9 + i % 8, 10 + i)),
      () => history.add(Submission.text(sampleClaim), sampleVerdict(kind)),
    );
  }
  return AppServices(
    client: client,
    auth: auth,
    language: LanguagePreference.inMemory(locale),
    history: history,
    themeMode: ThemeModePreference.inMemory(theme),
  );
}

/// A screen in the app's own theme and language.
Widget galleryApp(AppServices services, Widget home) => MaterialApp(
  debugShowCheckedModeBanner: false,
  theme: buildFactifyTheme(Brightness.light),
  darkTheme: buildFactifyTheme(Brightness.dark),
  themeMode: services.themeMode.value,
  locale: services.language.value,
  supportedLocales: AppLocalizations.supportedLocales,
  localizationsDelegates: AppLocalizations.localizationsDelegates,
  home: home,
);

/// A check that reports its progress from [events] and never finishes.
CheckJob Function(String) mid(AppServices services, StreamController<CheckEvent> events) =>
    (language) => CheckJob(
      services: services,
      submission: Submission.text(sampleClaim),
      language: language,
      follow: (_) => events.stream,
    );

/// The Checking screen's events for "step 2, four pages open, one read as refuting
/// the claim and one not about it, two published fact-checks compared".
void sendMidCheck(StreamController<CheckEvent> events) {
  var seq = 0;
  void send(Map<String, dynamic> json) =>
      events.add(CheckEvent.fromJson({...json, 'seq': ++seq}));
  send({'type': 'step', 'step': 'search'});
  for (final (initials, publisher, domain, title) in [
    ('PIB', 'PIB Fact Check', 'pib.gov.in', 'Claim of Rs 5,000 a month for every woman is fake'),
    ('AN', 'Alt News', 'altnews.in', 'Old scheme video shared with a false caption'),
    ('BO', 'BOOM', 'boomlive.in', 'No, the government is not paying every woman'),
    ('TH', 'The Hindu', 'thehindu.com', 'Tamil Nadu credits Rs 5,000 to 1.31 crore women'),
  ]) {
    send({
      'type': 'source_started',
      'publisher': publisher,
      'domain': domain,
      'initials': initials,
      'title': title,
      'via': 'page',
    });
  }
  for (final domain in ['factly.in', 'newschecker.in']) {
    send({
      'type': 'source_started',
      'publisher': domain,
      'domain': domain,
      'initials': 'FC',
      'via': 'fact_check',
    });
    send({'type': 'source_done', 'domain': domain, 'outcome': 'not_relevant'});
  }
  send({
    'type': 'source_done',
    'domain': 'pib.gov.in',
    'outcome': 'evidence',
    'stance': 'contradicts',
    'quote': 'No such scheme has been announced by the Government of India.',
  });
  send({'type': 'source_done', 'domain': 'altnews.in', 'outcome': 'not_relevant'});
  // The server counts after every source it finishes (progress.py, _count_changed).
  send({'type': 'evidence_count', 'n': 1, 'checked': false});
}
