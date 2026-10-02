/// Honest partial readings (contract 1.8) on the result, the sources screen and the
/// way back to the server.
///
/// Held here: "Check what was read" goes back to the server as `accept_partial`, on
/// a link, a message and a file, and on nothing else; a background check is waited
/// for past the server's new ceiling; an answer held back offers its ways on and
/// each starts the check it says - the same input from what was read, the pasted
/// text, the chosen picture or video - and offers nothing it cannot do; and the
/// sources screen quotes a claim from the part it was found in.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:factify_mobile/api/client.dart';
import 'package:factify_mobile/app_services.dart';
import 'package:factify_mobile/auth/auth_service.dart';
import 'package:factify_mobile/checks/check_job.dart';
import 'package:factify_mobile/history/history_store.dart';
import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/l10n/language_preference.dart';
import 'package:factify_mobile/models/submission.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:factify_mobile/screens/checking_screen.dart';
import 'package:factify_mobile/screens/evidence_screen.dart';
import 'package:factify_mobile/screens/result_screen.dart';
import 'package:factify_mobile/theme/theme.dart';
import 'package:factify_mobile/widgets/ui/ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'support/contract.dart';

const _link = 'https://www.example-news.in/india/new-rule-for-upi-payments-from-november-1';

/// A signed-in person on a server that records what it is sent, accepts a check in
/// the background, and answers it with [answer] - or, with [hold], never does.
Future<(AppServices, List<http.BaseRequest>, List<String>)> _services({
  String answer = 'instagram_reel_partial',
  bool hold = false,
}) async {
  final sent = <http.BaseRequest>[];
  final bodies = <String>[];
  final server = MockClient((request) async {
    sent.add(request);
    bodies.add(request.body);
    final path = request.url.path;
    if (path == '/v1/auth/config') {
      return http.Response('{"enabled": true, "required": true, "providers": ["password"]}', 200);
    }
    if (path == '/v1/auth/login') {
      return http.Response(
        jsonEncode({
          'access_token': 't',
          'expires_at': DateTime.now().add(const Duration(days: 1)).toIso8601String(),
          'method': 'password',
          'email': 'asha@example.org',
        }),
        200,
      );
    }
    if (path == '/v1/verify' || path == '/v1/verify/file') {
      if (hold) return Completer<http.Response>().future;
      return http.Response('{"case_id": "case-1", "poll_url": "/v1/cases/case-1"}', 202);
    }
    if (path == '/v1/cases/case-1') {
      return http.Response.bytes(
        contractBytes(answer),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    }
    return http.Response('{}', 404);
  });
  final client = FactifyClient(baseUrl: 'http://factify.test', httpClient: server);
  final auth = AuthService(client: client, httpClient: server, persist: false);
  client.tokenProvider = auth.accessToken;
  await auth.start();
  await auth.signIn(email: 'asha@example.org', password: 'long enough');
  sent.clear();
  bodies.clear();
  return (
    AppServices(
      client: client,
      auth: auth,
      language: LanguagePreference.inMemory(),
      history: HistoryStore(),
    ),
    sent,
    bodies,
  );
}

Future<void> _show(WidgetTester tester, Widget child) async {
  tester.view.physicalSize = const Size(1080, 2340);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
  final messenger = tester.binding.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
    if (call.method == 'Clipboard.hasStrings') return {'value': false};
    return null;
  });
  addTearDown(() => messenger.setMockMethodCallHandler(SystemChannels.platform, null));
  await tester.pumpWidget(
    MaterialApp(
      theme: buildFactifyTheme(Brightness.light),
      supportedLocales: AppLocalizations.supportedLocales,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      home: child,
    ),
  );
  await tester.pumpAndSettle();
}

/// The check the result handed over to, once it has started.
Future<CheckingScreen> _handedTo(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  return tester.widget<CheckingScreen>(find.byType(CheckingScreen));
}

/// Lets a held check go, so nothing is left running when the test ends.
Future<void> _close(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox());
  await tester.pump(const Duration(minutes: 1));
}

Future<void> _tapVisible(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.tap(finder);
}

void main() {
  group('"Check what was read" goes back to the server', () {
    test('a link or a message, as accept_partial, and only when asked', () async {
      final bodies = <Map<String, dynamic>>[];
      final client = FactifyClient(
        baseUrl: 'http://factify.test',
        httpClient: MockClient((request) async {
          bodies.add(jsonDecode(request.body) as Map<String, dynamic>);
          return http.Response('{"case_id": "case-1"}', 202);
        }),
      );
      await client.startCheck(url: _link, acceptPartial: true);
      await client.startCheck(text: 'A claim.');
      expect(bodies[0]['accept_partial'], isTrue);
      expect(bodies[0]['url'], _link);
      expect(bodies[1].containsKey('accept_partial'), isFalse);
    });

    test('a file, as the same form field', () async {
      final folder = await Directory.systemTemp.createTemp('factify_partial_test');
      addTearDown(() => folder.delete(recursive: true));
      final file = File('${folder.path}/clip.mp4')..writeAsBytesSync(List<int>.filled(64, 1));
      final bodies = <String>[];
      final client = FactifyClient(
        baseUrl: 'http://factify.test',
        httpClient: MockClient((request) async {
          bodies.add(latin1.decode(request.bodyBytes));
          return http.Response('{"case_id": "case-1"}', 202);
        }),
      );
      await client.verifyFile(file, background: true, acceptPartial: true);
      await client.verifyFile(file, background: true);
      expect(bodies[0], contains('name="accept_partial"'));
      expect(bodies[1], isNot(contains('name="accept_partial"')));
    });

    testWidgets('a check job sends it, and the 1.8 answer arrives as sent', (tester) async {
      final (services, sent, bodies) = await _services();
      final job = CheckJob(
        services: services,
        submission: Submission.link(_link),
        language: 'en',
        acceptPartial: true,
        follow: (_) => const Stream.empty(),
      )..start();
      await tester.pump();
      await tester.pump(const Duration(seconds: 3));
      await tester.pump();
      final verdict = await job.result;

      final started = jsonDecode(bodies.first) as Map<String, dynamic>;
      expect(sent.first.url.path, '/v1/verify');
      expect(started['accept_partial'], isTrue);
      expect(verdict!.inputRead!.checkedPartially, isTrue);
    });

    test('a background check is waited for past the server\'s ceiling of 420 s', () {
      expect(CheckJob.polls * 3, greaterThan(420));
      expect(CheckJob.polls, 170);
    });
  });

  group('an answer held back', () {
    Future<AppServices> held(WidgetTester tester, {Submission? submission}) async {
      final (services, _, _) = await _services(hold: true);
      await _show(
        tester,
        ResultScreen(
          services: services,
          verdict: contractVerdict('link_withheld'),
          submission: submission ?? Submission.link(_link),
          pickMedia: () async {
            final folder = Directory.systemTemp.createTempSync('factify_pick_test');
            addTearDown(() => folder.deleteSync(recursive: true));
            return File('${folder.path}/the-reel.mp4')..writeAsBytesSync(List<int>.filled(64, 1));
          },
        ),
      );
      return services;
    }

    testWidgets('offers its ways on, and nothing to share', (tester) async {
      await held(tester);

      expect(find.text('Not checked yet'), findsOneWidget);
      expect(find.text('Check what was read'), findsOneWidget);
      expect(find.text('Paste the text'), findsOneWidget);
      expect(find.text('Upload the picture or video'), findsOneWidget);
      // The bar starts afresh; a correction of claims never checked is not offered.
      expect(find.text('New check'), findsOneWidget);
      expect(find.text('Share correction'), findsNothing);
      final share = tester.widget<FxCircleButton>(
        find.ancestor(of: find.byTooltip('Share correction'), matching: find.byType(FxCircleButton)),
      );
      expect(share.onPressed, isNull);
    });

    testWidgets('"Check what was read" checks the same link from what was read', (tester) async {
      await held(tester);
      await _tapVisible(tester, find.text('Check what was read'));
      final checking = await _handedTo(tester);

      expect(checking.acceptPartial, isTrue);
      expect(checking.recheck, isFalse);
      expect(checking.submission.kind, SubmissionKind.link);
      expect(checking.submission.text, _link);
      await _close(tester);
    });

    testWidgets('"Paste the text" checks the pasted words, as a message', (tester) async {
      await held(tester);
      await _tapVisible(tester, find.text('Paste the text'));
      await tester.pumpAndSettle();

      expect(find.text('Paste the text to check'), findsOneWidget);
      await tester.enterText(
        find.byKey(const ValueKey('paste-sheet-text')),
        '  NPCI says UPI payments above Rs 2,000 will carry a fee from 1 November.  ',
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Check now'));
      final checking = await _handedTo(tester);

      expect(checking.acceptPartial, isFalse);
      expect(checking.submission.kind, SubmissionKind.text);
      expect(
        checking.submission.text,
        'NPCI says UPI payments above Rs 2,000 will carry a fee from 1 November.',
      );
      await _close(tester);
    });

    testWidgets('"Upload the picture or video" checks the chosen file', (tester) async {
      await held(tester);
      await _tapVisible(tester, find.text('Upload the picture or video'));
      // The chosen file's size is read from the disk: real time, not the test's.
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 200)));
      final checking = await _handedTo(tester);

      expect(checking.submission.kind, SubmissionKind.image);
      expect(checking.submission.video, isTrue);
      expect(checking.submission.file!.path, endsWith('the-reel.mp4'));
      expect(checking.acceptPartial, isFalse);
      await _close(tester);
    });

    testWidgets('reopened with nothing to send again, offers no "check what was read"', (
      tester,
    ) async {
      final (services, _, _) = await _services(hold: true);
      await _show(
        tester,
        ResultScreen(
          services: services,
          verdict: contractVerdict('link_withheld'),
          kind: SubmissionKind.link,
        ),
      );
      expect(find.text('Not checked yet'), findsOneWidget);
      expect(find.text('Check what was read'), findsNothing);
      expect(find.text('Paste the text'), findsOneWidget);
    });

    testWidgets('an upload that could not be read is not asked to be uploaded again', (
      tester,
    ) async {
      final json = contractJson('link_withheld');
      (json['input_read'] as Map)['kind'] = 'video';
      final (services, _, _) = await _services(hold: true);
      await _show(
        tester,
        ResultScreen(
          services: services,
          verdict: Verdict.fromJson(json),
          kind: SubmissionKind.image,
        ),
      );
      expect(find.text('Upload the picture or video'), findsNothing);
      expect(find.text('Paste the text'), findsOneWidget);
    });
  });

  testWidgets('an answer checked from part of a post is checked again the same way', (
    tester,
  ) async {
    final (services, _, _) = await _services(hold: true);
    final verdict = contractVerdict('instagram_reel_partial');
    await _show(
      tester,
      ResultScreen(
        services: services,
        verdict: verdict,
        submission: Submission.link(verdict.inputRead!.url!),
      ),
    );
    await tester.tap(find.text('Check again'));
    final checking = await _handedTo(tester);

    expect((checking.recheck, checking.acceptPartial), (true, true));
    await _close(tester);
  });

  group('the sources screen', () {
    Future<void> sources(WidgetTester tester, Verdict verdict) async {
      tester.view.physicalSize = const Size(1080, 6000);
      tester.view.devicePixelRatio = 2.625;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(
          theme: buildFactifyTheme(Brightness.light),
          supportedLocales: AppLocalizations.supportedLocales,
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          home: EvidenceScreen(
            verdict: verdict,
            language: LanguagePreference.inMemory(),
            // What was typed: a link, never where the claim was said.
            submission: Submission.link('https://x.com/i/status/1973412345678901234'),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('quotes each claim from the part it was found in', (tester) async {
      await sources(tester, contractVerdict('x_photo_post'));

      expect(
        find.text('Where your submission says this · Text in picture 1 of 2'),
        findsOneWidget,
      );
      expect(find.text('Where your submission says this · Post'), findsOneWidget);
      final quoted = tester
          .widgetList<Text>(find.byType(Text))
          .map((t) => t.textSpan?.toPlainText() ?? t.data ?? '')
          .where((t) => t.contains('Notes may be exchanged at any bank branch till 31 October'));
      expect(quoted, isNotEmpty);
    });

    testWidgets('names no verdict for an answer held back, and says what was not read', (
      tester,
    ) async {
      await sources(tester, contractVerdict('link_withheld'));

      expect(find.text('Not checked yet'), findsOneWidget);
      expect(find.text('Unconfirmed'), findsNothing);
      await tester.tap(find.text('How we checked'));
      await tester.pumpAndSettle();
      expect(find.text('What could not be read'), findsOneWidget);
      expect(
        find.text(
          "•  Only the page's headline and summary could be read, not the article itself.",
        ),
        findsOneWidget,
      );
      // The same gaps, sent again as skipped checks in English, are not said twice.
      expect(find.textContaining('linked_page:'), findsNothing);
    });
  });
}
