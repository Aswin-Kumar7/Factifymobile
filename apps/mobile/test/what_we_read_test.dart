/// What Factify read (contract 1.8), built against the server's own sample answers.
///
/// Held here: the reading arrives from the response as sent, parts in the server's
/// order; every gap is worded in the reader's language; each claim is underlined in
/// the part it was found in, and an emoji before it does not move the underline;
/// Factify's description of what was shown is never quoted as the input's words and
/// says whether it was checked; an answer held back reads "Not checked yet" and
/// offers the ways on; an answer checked from part of a post says so beside the
/// verdict and never reads "Too recent to confirm"; "couldn't be checked in time" is
/// said only when the time ran out; and a result from before 1.8 shows what it did.
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/models/submission.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:factify_mobile/theme/theme.dart';
import 'package:factify_mobile/widgets/action_style.dart';
import 'package:factify_mobile/widgets/claim_spans.dart';
import 'package:factify_mobile/widgets/verdict_card.dart';
import 'package:factify_mobile/widgets/what_we_read.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/intl.dart';

import 'support/contract.dart';
import 'support/screens.dart';

final AppLocalizations _en = lookupAppLocalizations(const Locale('en'));
final AppLocalizations _hi = lookupAppLocalizations(const Locale('hi'));

Future<void> _card(
  WidgetTester tester,
  Verdict verdict, {
  Locale locale = const Locale('en'),
  SubmissionKind kind = SubmissionKind.link,
  Uint8List? thumbnail,
  VoidCallback? onCheckWhatWasRead,
  VoidCallback? onPasteText,
  VoidCallback? onUpload,
}) async {
  tester.view.physicalSize = const Size(1080, 9000);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: buildFactifyTheme(Brightness.light),
      locale: locale,
      supportedLocales: AppLocalizations.supportedLocales,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      home: Scaffold(
        body: SingleChildScrollView(
          child: VerdictCard(
            verdict: verdict,
            kind: kind,
            thumbnail: thumbnail,
            serverUrl: 'http://factify.test',
            onCheckWhatWasRead: onCheckWhatWasRead,
            onPasteText: onPasteText,
            onUpload: onUpload,
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

/// The words of [span] in [text].
String _said(String text, ClaimSpan span) => text.substring(span.start, span.end);

/// Within the panel only.
Finder _inPanel(Finder finder) =>
    find.descendant(of: find.byKey(const ValueKey('what-we-read')), matching: finder);

/// A response's JSON with [change] applied to its first part of [kind].
Map<String, dynamic> _withPart(String name, String kind, void Function(Map part) change) {
  final json = contractJson(name);
  final parts = (json['input_read'] as Map)['parts'] as List;
  change(parts.cast<Map>().firstWhere((p) => p['kind'] == kind));
  return json;
}

/// One gap as the server sends it, and the skipped check it also arrives as.
typedef _Gap = ({String check, String part, String code, bool blocking});

/// An uploaded video with no claim in it, whose picture checks found it
/// [agreement], with [gaps] as a 1.8 server sends them: in the reading, and again
/// as skipped checks of kind "reading" - every one of them, blocking or not
/// (app/api/verify.py, `_with_reading_gaps`) - beside the `video_frames` note
/// every uploaded video carries. The completeness note is the pipeline's, which
/// is told only of the blocking gaps.
Verdict _videoWithNoClaim(List<_Gap> gaps, {String agreement = 'likely_ai'}) {
  final json = contractJson('video_upload')
    ..['claims'] = <Object>[]
    ..['verdict'] = 'UNCONFIRMED'
    ..['action'] = 'SEND_TO_REVIEW'
    ..['confidence'] = null
    ..['summary'] = null
    ..['skipped'] = [
      for (final gap in gaps)
        {'check': gap.check, 'reason': 'DETAIL ${gap.part}', 'kind': 'reading'},
      {'check': 'video_frames', 'reason': 'read the words on 10 of 12 frames taken from 0:00'},
    ];
  if (gaps.any((g) => g.blocking)) {
    json['completeness_note'] = 'Not everything could be checked. speech: DETAIL transcript';
  }
  final read = json['input_read'] as Map;
  read['gaps'] = [
    for (final gap in gaps)
      {
        'part': gap.part,
        'code': gap.code,
        'detail': 'DETAIL ${gap.part}',
        'blocking': gap.blocking,
      },
  ];
  read['complete'] = gaps.isEmpty;
  ((json['media_report'] as Map)['detector'] as Map)['agreement'] = agreement;
  return Verdict.fromJson(json);
}

/// The frames' words, read in part for time: a gap that could not decide the answer.
const _Gap _framesCut = (
  check: 'video_text',
  part: 'on_screen_text',
  code: 'cut_off',
  blocking: false,
);

/// What is said, heard only up to the reading's limit: a gap that could.
const _Gap _speechCut = (check: 'speech', part: 'transcript', code: 'cut_off', blocking: true);

/// The AI note at the top of an AI-made video with no claim in it.
const _aiVideo = 'But our checks say this video was likely made by AI. See the video checks below.';

/// A 1x1 picture, as the person's own upload.
final Uint8List _pixel = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAMAASsJTYQAAAAASUVORK5CYII=',
);

void main() {
  group('the reading arrives from the 1.8 response', () {
    test('every sample parses, its parts in the order the server sent them', () {
      for (final name in contractSamples) {
        final json = contractJson(name);
        final read = Verdict.fromJson(json).inputRead!;
        final parts = (json['input_read'] as Map)['parts'] as List;
        expect(read.parts.map((p) => p.kind), [for (final p in parts) (p as Map)['kind']]);
        expect(read.complete, read.gaps.isEmpty, reason: name);
      }

      final post = contractVerdict('x_photo_post').inputRead!;
      expect(post.kind, 'social_post');
      expect(post.platform, 'x');
      expect(post.author, 'Daily Bharat Updates');
      expect(post.handle, 'dailybharatupd');
      expect(post.publishedAt, DateTime.utc(2026, 10, 1, 14, 12));
      final picture = post.parts[1];
      expect(picture.isPictureText, isTrue);
      expect(picture.mediaUrl, '/v1/media/thumbnails/9b2f0c6e1a7d4e3fb8c5a2d1e0f9c8b7');
      expect((picture.charStart, picture.charEnd), (227, 385));
      expect(post.parts[2].checked, isTrue, reason: "fed to the claims, as Factify's words");
      expect(post.parts[2].isDescription, isTrue);

      final reel = contractVerdict('instagram_reel_partial').inputRead!;
      expect(reel.checkedPartially, isTrue);
      expect(reel.blocked, isTrue);
      expect(reel.gaps.single.code, 'cut_off');
      expect((reel.parts[1].secondsRead, reel.parts[1].secondsTotal), (600, 842));

      expect(contractVerdict('link_withheld').inputRead!.verdictWithheld, isTrue);
      expect(contractVerdict('youtube_video').inputRead!.limits, hasLength(1));
      expect(contractVerdict('link_complete').inputRead!.host, 'thehindu.com');
    });

    test("a post's other pictures have their own checks; the first stays where it was", () {
      final verdict = contractVerdict('x_photo_post');
      expect(verdict.mediaReport, isNotNull);
      expect(verdict.mediaReports, hasLength(1));
    });

    test('a skipped check says what kind of gap it is; an older one is "other"', () {
      final reel = contractVerdict('instagram_reel_partial');
      expect(reel.skipped.single.kind, 'reading');
      expect(reel.skipped.single.isReading, isTrue);
      expect(sampleVerdict(FactVerdict.unconfirmed).inputRead, isNull);
      expect(SkippedCheck.fromJson({'check': 'factcheck', 'reason': 'x'}).kind, 'other');
    });

    test('a response with an input_read it cannot use reads as one without', () {
      final json = contractJson('link_complete')..['input_read'] = {'parts': 'nonsense'};
      expect(Verdict.fromJson(json).inputRead, isNull);
      final odd = contractJson('link_complete')
        ..['input_read'] = {
          'kind': 'link',
          'parts': [
            'not a part',
            {'text': 'no kind'},
            {'kind': 'article', 'text': 'Kept.'},
          ],
          'gaps': [
            {'detail': 'no code'},
          ],
        };
      final read = Verdict.fromJson(odd).inputRead!;
      expect(read.parts.single.text, 'Kept.');
      expect(read.gaps, isEmpty);
      expect(read.complete, isTrue);
    });

    test('enough was read to check, as the server counts it', () {
      expect(contractVerdict('link_withheld').inputRead!.substantive, isTrue);
      expect(
        InputRead.tryParse({
          'kind': 'social_post',
          'parts': [
            {'kind': 'post_text', 'text': 'Wow', 'checked': true, 'route': 'x.oembed'},
            {
              'kind': 'video_description',
              'text': 'A crowd at a rally waving flags.',
              'checked': true,
              'route': 'ocr.hosted',
            },
          ],
        })!.substantive,
        isFalse,
        reason: "one word of the post's own, and Factify's description does not count",
      );
      expect(
        InputRead.tryParse({
          'kind': 'image',
          'parts': [
            {'kind': 'picture_text', 'text': '', 'checked': true, 'route': 'ocr.local'},
          ],
        })!.substantive,
        isTrue,
        reason: 'a picture read in full can still be checked for where it appeared',
      );
    });
  });

  group('words', () {
    test('every gap the server names is worded in both languages', () {
      const codes = [
        'headline_only',
        'text_truncated',
        'post_unavailable',
        'login_required',
        'not_supported',
        'picture_unread',
        'video_unread',
        'speech_unread',
        'cut_off',
        'pages_unread',
        'too_large',
        'needs_background',
        'reader_unavailable',
        'first_picture_only',
        'article_truncated',
        'description_unread',
        'linked_page_unread',
      ];
      for (final code in codes) {
        final gap = ReadGap(part: 'post', code: code, detail: 'DETAIL', blocking: true);
        expect(gapLine(gap, _en), isNot('DETAIL'), reason: code);
        expect(gapLine(gap, _hi), isNot(gapLine(gap, _en)), reason: code);
      }
      // A gap added after this app was built is said in the server's own sentence.
      const later = ReadGap(
        part: 'post',
        code: 'poll_unread',
        detail: "The post's poll could not be read.",
        blocking: false,
      );
      expect(gapLine(later, _hi), "The post's poll could not be read.");
    });

    test('a part is headed by its kind; a quoted post by who it is by', () {
      final post = contractVerdict('x_photo_post').inputRead!;
      expect(partLabel(post.parts[0], post, _en), 'Post');
      expect(partLabel(post.parts[1], post, _en), 'Text in picture 1 of 2');
      expect(partLabel(post.parts[3], post, _en), 'Text in picture 2 of 2');
      expect(
        partLabel(post.parts[2], post, _en),
        'What the picture shows · Described by Factify',
      );
      expect(partLabel(post.parts[1], post, _hi), 'तस्वीर 1/2 में लिखा पाठ');

      ReadPart part(String kind, String label, {bool checked = true}) =>
          ReadPart(kind: kind, text: 'x', checked: checked, route: 'x.syndication', label: label);
      final quoted = part('quoted_post', 'Quoted post by Ravi Kumar (@ravik) on X, 30 Sep 2026');
      expect(partLabel(quoted, post, _en), 'Quoted post by Ravi Kumar (@ravik)');
      expect(partLabel(quoted, post, _hi), 'Ravi Kumar (@ravik) की उद्धृत पोस्ट');
      expect(partLabel(part('quoted_post', 'Quoted post on X'), post, _en), 'Quoted post');
      expect(
        partLabel(part('linked_article', 'Linked article (thehindu.com)'), post, _en),
        'Linked article · thehindu.com',
      );
      // A description checked beside the input's own words says it is Factify's.
      expect(
        partLabel(part('video_description', 'What the video shows'), post, _en),
        'What the video shows · Described by Factify',
      );
    });

    test('times read as a clock does', () {
      expect(clockTime(92), '1:32');
      expect(clockTime(842), '14:02');
      expect(clockTime(3900), '1:05:00');
    });

    test('what was read, in one line', () {
      expect(readSummary(contractVerdict('x_photo_post').inputRead!, _en), 'post · 2 pictures');
      expect(
        readSummary(contractVerdict('instagram_reel_partial').inputRead!, _en),
        'post · video 14:02',
      );
      expect(readSummary(contractVerdict('youtube_video').inputRead!, _en), 'video 6:52');
      expect(readSummary(contractVerdict('link_complete').inputRead!, _en), 'page');
      expect(readSummary(contractVerdict('video_upload').inputRead!, _en), 'video 0:48');
      expect(readSummary(contractVerdict('x_photo_post').inputRead!, _hi), 'पोस्ट · 2 तस्वीरें');
    });

    test('an answer held back is labelled "Not checked" in History, never "Unconfirmed"', () {
      final withheld = contractVerdict('link_withheld');
      expect(ActionStyle.label(withheld, _en), 'Not checked');
      expect(ActionStyle.label(withheld, _hi), 'जाँचा नहीं गया');
      expect(ActionStyle.label(contractVerdict('instagram_reel_partial'), _en), 'Unconfirmed');
    });
  });

  group('each claim is underlined in the part it was found in', () {
    test('the post, and the picture, each with its own claim', () {
      final verdict = contractVerdict('x_photo_post');
      final parts = verdict.inputRead!.parts;
      final inPost = claimsInPart(parts[0], verdict.claims);
      expect(_said(parts[0].text, inPost.single), 'RBI to withdraw all ₹500 notes from 1 November');
      expect(inPost.single.mark, ClaimMark.wrong);
      final inPicture = claimsInPart(parts[1], verdict.claims);
      expect(
        _said(parts[1].text, inPicture.single),
        'Notes may be exchanged at any bank branch till 31 October',
      );
      expect(inPicture.single.mark, ClaimMark.unconfirmed);
      // A claim found in one part is not underlined again in another that repeats
      // its words, and never in a description that was not checked.
      expect(claimsInPart(parts[3], verdict.claims), isEmpty);
      expect(claimsInPart(parts[2], verdict.claims), isEmpty);
    });

    test('Hindi speech, by its anchor', () {
      final verdict = contractVerdict('youtube_video');
      final heard = verdict.inputRead!.parts[2];
      final spans = claimsInPart(heard, verdict.claims);
      expect(spans, hasLength(2));
      expect(_said(heard.text, spans[1]), startsWith('आज से पूरे देश में पेट्रोल 20 रुपये'));
      expect(spans[1].mark, ClaimMark.wrong);
    });

    test('an emoji before a claim does not move its underline', () {
      // The server counts characters as code points; Dart counts 🚨 as two.
      const text = '🚨🚨 BIG NEWS: RBI to withdraw all ₹500 notes from 1 November.';
      const label = 'Post:\n';
      final part = ReadPart(
        kind: 'post_text',
        text: text,
        checked: true,
        route: 'x.syndication',
        charStart: label.length,
        charEnd: label.length + text.runes.length,
      );
      final start = label.length + text.runes.toList().indexOf('R'.runes.first);
      final claim = Claim.fromJson({
        'id': 'cl_1',
        'text': 'RBI will withdraw all ₹500 notes from 1 November.',
        'claim_type': 'EVENT',
        'status': 'CONTRADICTED',
        'severity': 'HIGH',
        'importance': 'HEADLINE',
        'reason': 'r',
        'strength': {'score': 0.9, 'band': 'strong', 'components': <Object>[], 'version': 'v'},
        'evidence': <Object>[],
        'input_anchor': {'char_start': start, 'char_end': start + 46},
      });
      final span = claimsInPart(part, [claim]).single;
      expect(_said(text, span), 'RBI to withdraw all ₹500 notes from 1 November');
    });

    test('an anchor is traced to its part, in the part\'s own offsets', () {
      final verdict = contractVerdict('instagram_reel_partial');
      final read = verdict.inputRead!;
      final found = anchorInPart(read, verdict.claims[1].inputAnchor!)!;
      expect(found.part.kind, 'transcript');
      expect(found.part.text.substring(found.start, found.end), contains('2 सितंबर 2023'));
      expect(anchorInPart(read, const InputAnchor(charStart: 0, charEnd: 10)), isNull);
    });
  });

  group('what the answer says about itself', () {
    test('held back: not "nothing to check", and not "unconfirmed" in its words', () {
      final withheld = contractVerdict('link_withheld');
      expect(withheld.withheld, isTrue);
      expect(withheld.nothingToCheck, isFalse);
      expect(withheld.partlyRead, isFalse);
    });

    test('read in full and nothing in it to check is nothing to check', () {
      final json = contractJson('link_complete')
        ..['claims'] = <Object>[]
        ..['verdict'] = 'UNCONFIRMED'
        ..['action'] = 'SEND_TO_REVIEW';
      expect(Verdict.fromJson(json).nothingToCheck, isTrue);
      // But not when part of it could not be read.
      final reel = contractJson('instagram_reel_partial')..['claims'] = <Object>[];
      expect(Verdict.fromJson(reel).nothingToCheck, isFalse);
    });

    test('partly read is told apart from too recent, by the reading or by the rule', () {
      expect(contractVerdict('instagram_reel_partial').partlyRead, isTrue);
      final byReason = contractJson('instagram_reel_partial')..remove('input_read');
      expect(Verdict.fromJson(byReason).partlyRead, isTrue);
      final tooRecent = contractJson('instagram_reel_partial')
        ..remove('input_read')
        ..['action_reason'] = 'The event is too recent for sources to have reported it.';
      expect(Verdict.fromJson(tooRecent).partlyRead, isFalse);
    });

    test('"ran out of time" only when it did; another missed check is said as one', () {
      Verdict with_(List<Map<String, dynamic>> skipped, {bool read = true}) {
        final json = contractJson('link_complete')
          ..['skipped'] = skipped
          ..['completeness_note'] = 'Not everything could be checked.';
        if (!read) json.remove('input_read');
        return Verdict.fromJson(json);
      }

      final reel = contractVerdict('instagram_reel_partial');
      expect((reel.ranOutOfTime, reel.missedChecks), (false, false));
      final timedOut = with_([
        {'check': 'web_search', 'reason': 'deadline of 300s exceeded', 'kind': 'deadline'},
      ]);
      expect((timedOut.ranOutOfTime, timedOut.missedChecks), (true, false));
      expect(
        with_([
          {'check': 'web_search', 'reason': 'deadline of 300s exceeded'},
        ]).ranOutOfTime,
        isTrue,
        reason: 'a server that does not yet mark its timeouts names them in the reason',
      );
      final provider = with_([
        {'check': 'source_verification', 'reason': 'model provider unavailable'},
      ]);
      expect((provider.ranOutOfTime, provider.missedChecks), (false, true));
      final reading = with_([
        {'check': 'linked_page', 'reason': 'only the headline could be read'},
      ]);
      expect((reading.ranOutOfTime, reading.missedChecks), (false, false));
      expect(
        with_([
          {'check': 'factcheck', 'reason': 'not configured'},
        ], read: false).ranOutOfTime,
        isTrue,
        reason: 'a result from before 1.8 reads as it always did',
      );
    });
  });

  group('the panel', () {
    testWidgets('a post read in full is folded to its first lines, and opens in full', (
      tester,
    ) async {
      await _card(tester, contractVerdict('x_photo_post'));

      expect(find.text('What Factify read · X post'), findsOneWidget);
      expect(
        find.textContaining('Daily Bharat Updates · @dailybharatupd · '),
        findsOneWidget,
      );
      expect(find.textContaining('What we checked'), findsNothing);
      expect(find.byKey(const ValueKey('read-gaps')), findsNothing);
      expect(_inPanel(find.text('Post')), findsOneWidget);
      expect(find.text('Text in picture 1 of 2'), findsNothing);

      await tester.tap(find.text('Show all'));
      await tester.pumpAndSettle();

      expect(find.text('Text in picture 1 of 2'), findsOneWidget);
      expect(find.text('Text in picture 2 of 2'), findsOneWidget);
      expect(find.textContaining('Notes may be exchanged at any bank branch'), findsOneWidget);
      expect(
        find.text('What the picture shows · Described by Factify'),
        findsNWidgets(2),
      );
      // Factify's description is not quoted as if the post had said it.
      expect(
        find.text('A document styled as an RBI press release, with the bank\'s emblem at the '
            'top and a signature at the bottom.'),
        findsOneWidget,
      );
      // Every picture's checks, each named.
      expect(find.text('Picture 1 checks'), findsOneWidget);
      expect(find.text('Picture 2 checks'), findsOneWidget);
    });

    testWidgets("a part's picture is asked of our own server, never the platform's", (
      tester,
    ) async {
      await _card(tester, contractVerdict('x_photo_post'));
      await tester.tap(find.text('Show all'));
      await tester.pumpAndSettle();

      final urls = tester
          .widgetList<Image>(_inPanel(find.byType(Image)))
          .map((i) => i.image)
          .whereType<NetworkImage>()
          .map((i) => i.url)
          .toList();
      expect(urls, [
        'http://factify.test/v1/media/thumbnails/9b2f0c6e1a7d4e3fb8c5a2d1e0f9c8b7',
        'http://factify.test/v1/media/thumbnails/4e7a1c9d2b3f4a5e8d6c7b0a1f2e3d4c',
      ], reason: 'once per picture, beside its text and not again beside its description');
    });

    testWidgets('a post read in part opens with the warning, gap by gap', (tester) async {
      await _card(tester, contractVerdict('instagram_reel_partial'));

      expect(find.byKey(const ValueKey('read-gaps')), findsOneWidget);
      expect(find.text('Factify could only read part of this post.'), findsOneWidget);
      expect(
        find.text(
          "Only the start of what is said in the video was heard, so the rest wasn't checked.",
        ),
        findsOneWidget,
      );
      // Open from the start: every part, and how much of the speech was heard.
      expect(find.text('Said in the video'), findsOneWidget);
      expect(find.text('10:00 of 14:02 heard'), findsOneWidget);
      expect(find.text('Read only in part'), findsNWidgets(2));
      expect(find.text('Show all'), findsNothing);
      expect(find.text('What the video shows · Described by Factify'), findsOneWidget);
      expect(find.text('Only the first three minutes were read.'), findsNothing);
    });

    testWidgets('checked from part of a post: said beside the verdict, never "too recent"', (
      tester,
    ) async {
      await _card(tester, contractVerdict('instagram_reel_partial'));

      expect(find.text('Unconfirmed'), findsOneWidget);
      expect(find.text('Too recent to confirm yet'), findsNothing);
      expect(find.text('Part of it could not be read'), findsOneWidget);
      expect(find.byKey(const ValueKey('checked-partially')), findsOneWidget);
      expect(find.text('Checked from part of the post'), findsOneWidget);
      expect(find.textContaining('What Factify could read is supported'), findsOneWidget);
      expect(find.textContaining("couldn't find enough reliable sources"), findsNothing);
      // A reading gap is not the clock running out.
      expect(find.textContaining("couldn't be checked in time"), findsNothing);
      expect(find.textContaining("Some checks couldn't run"), findsNothing);
    });

    testWidgets('held back: "Not checked yet", the ways on, and no verdict word', (
      tester,
    ) async {
      var checks = 0;
      var pastes = 0;
      var uploads = 0;
      await _card(
        tester,
        contractVerdict('link_withheld'),
        onCheckWhatWasRead: () => checks++,
        onPasteText: () => pastes++,
        onUpload: () => uploads++,
      );

      expect(find.text('Not checked yet'), findsOneWidget);
      expect(
        find.text('Factify could not read all of this, so it has not given a verdict.'),
        findsOneWidget,
      );
      expect(find.text('Unconfirmed'), findsNothing);
      expect(find.text('No citable source was found'), findsNothing);
      expect(find.text('Factify could only read part of this page.'), findsOneWidget);
      expect(
        find.text("Only the page's headline and summary could be read, not the article itself."),
        findsOneWidget,
      );
      expect(find.text('What Factify read · Link · example-news.in'), findsOneWidget);
      expect(find.textContaining('New rule for UPI payments'), findsOneWidget);

      await tester.tap(find.text('Check what was read'));
      await tester.tap(find.text('Paste the text'));
      await tester.tap(find.text('Upload the picture or video'));
      expect((checks, pastes, uploads), (1, 1, 1));
    });

    testWidgets('held back with nothing to offer shows no buttons', (tester) async {
      await _card(tester, contractVerdict('link_withheld'));
      expect(find.text('Not checked yet'), findsOneWidget);
      expect(find.text('Check what was read'), findsNothing);
      expect(find.text('Paste the text'), findsNothing);
    });

    testWidgets("a post's website is not described; a link's still is", (tester) async {
      final post = contractJson('x_photo_post')
        ..['source_profile'] = {'domain': 'x.com', 'trusted': false, 'level': 'UNKNOWN'};
      await _card(tester, Verdict.fromJson(post));
      expect(find.text('About this website'), findsNothing);

      await _card(tester, contractVerdict('link_complete'));
      expect(find.text('About this website'), findsOneWidget);
      expect(find.text('What Factify read · Link · thehindu.com'), findsOneWidget);
      final published = DateFormat('d MMM yyyy').format(DateTime.utc(2025, 8, 23, 6, 30).toLocal());
      expect(find.text('Published $published'), findsOneWidget);
    });

    testWidgets("a YouTube video's limit is said in the reader's language", (tester) async {
      await _card(tester, contractVerdict('youtube_video'), locale: const Locale('hi'));

      expect(find.text('Factify ने क्या पढ़ा · YouTube वीडियो'), findsOneWidget);
      expect(
        find.textContaining('YouTube, Factify को वीडियो डाउनलोड नहीं करने देता'),
        findsOneWidget,
      );
      expect(find.textContaining('YouTube does not let'), findsNothing);
    });

    testWidgets('in Hindi, the warning, the gaps and the headings are Hindi', (tester) async {
      await _card(tester, contractVerdict('instagram_reel_partial'), locale: const Locale('hi'));

      expect(find.text('Factify इस पोस्ट का सिर्फ़ कुछ हिस्सा पढ़ पाया।'), findsOneWidget);
      expect(find.text('पोस्ट के कुछ हिस्से से जाँचा गया'), findsOneWidget);
      expect(find.text('इसका कुछ हिस्सा पढ़ा नहीं जा सका'), findsOneWidget);
      expect(find.text('14:02 में से 10:00 सुना गया'), findsOneWidget);
      // The reader's English aside is for an English reader.
      expect(find.textContaining('read from 24 frames'), findsNothing);
    });

    testWidgets('an uploaded video read in full: what was said, and the frames', (tester) async {
      await _card(tester, contractVerdict('video_upload'));

      expect(find.text('What Factify read · Video'), findsOneWidget);
      await tester.tap(find.text('Show all'));
      await tester.pumpAndSettle();
      expect(find.text('All 0:48 heard'), findsOneWidget);
      expect(find.text('Text shown in the video'), findsOneWidget);
      expect(find.text('read from 12 frames'), findsOneWidget);
    });

    testWidgets('a description checked beside the words says so, and is still not quoted', (
      tester,
    ) async {
      // What the server sends for an upload with words of its own: its description
      // is in the text claims were found in (app/api/verify.py, `_to_check`).
      final json = _withPart('video_upload', 'video_description', (part) {
        part['checked'] = true;
        part['char_start'] = 230;
        part['char_end'] = 299;
      });
      await _card(tester, Verdict.fromJson(json));
      await tester.tap(find.text('Show all'));
      await tester.pumpAndSettle();

      expect(find.text('What the video shows · Described by Factify'), findsOneWidget);
      expect(
        find.text('A flooded residential street with cars submerged up to their windows.'),
        findsOneWidget,
      );
    });

    testWidgets('a result from before 1.8 still shows what was checked, as it did', (
      tester,
    ) async {
      await _card(tester, sampleVerdict(FactVerdict.falseClaim));
      expect(find.textContaining('What we checked'), findsOneWidget);
      expect(find.textContaining('What Factify read'), findsNothing);
    });
  });

  group('a gap that could not decide the answer', () {
    test('leaves an upload with no claim in it nothing to check', () {
      final verdict = _videoWithNoClaim([_framesCut]);
      expect(verdict.skipped.where((s) => s.isReading), hasLength(1));
      expect(verdict.readingFailed, isFalse);
      expect(verdict.nothingToCheck, isTrue);
      expect(verdict.unreadNothingFound, isFalse);
      expect(ActionStyle.label(verdict, _en), 'Nothing to check');
    });

    test('one that could is not "nothing to check", and is said for what it is', () {
      final verdict = _videoWithNoClaim([_framesCut, _speechCut]);
      expect(verdict.readingFailed, isTrue);
      expect(verdict.nothingToCheck, isFalse);
      expect(verdict.unreadNothingFound, isTrue);
      expect(verdict.noClaimFound, isTrue);
      // The note every video carries is what was read, not a check that did not run.
      expect((verdict.ranOutOfTime, verdict.missedChecks), (false, false));
    });

    test('claims that could not be found always count, read in full or not', () {
      final json = contractJson('video_upload')
        ..['claims'] = <Object>[]
        ..['verdict'] = 'UNCONFIRMED'
        ..['action'] = 'SEND_TO_REVIEW'
        ..['skipped'] = [
          {'check': 'claim_extraction', 'reason': 'model provider unavailable'},
        ];
      final verdict = Verdict.fromJson(json);
      expect(verdict.nothingToCheck, isFalse);
      expect(verdict.unreadNothingFound, isFalse);
    });

    test('a result with no reading counts every reading gap, as it did', () {
      final json = contractJson('video_upload')
        ..remove('input_read')
        ..['claims'] = <Object>[]
        ..['verdict'] = 'UNCONFIRMED'
        ..['action'] = 'SEND_TO_REVIEW'
        ..['skipped'] = [
          {'check': 'video_text', 'reason': 'words on 10 of 12 frames', 'kind': 'reading'},
        ];
      expect(Verdict.fromJson(json).nothingToCheck, isFalse);
    });

    testWidgets('an AI video with no claim, read in part for time: nothing to check, AI note', (
      tester,
    ) async {
      await _card(tester, _videoWithNoClaim([_framesCut]), kind: SubmissionKind.image);

      expect(find.text('Nothing to fact-check'), findsOneWidget);
      expect(find.text(_aiVideo), findsOneWidget);
      expect(find.textContaining('Treat it with caution'), findsNothing);
      expect(find.text('No citable source was found'), findsNothing);
      // Said where what was read is shown, in its own words.
      expect(find.text('Only some of the words shown in the video were read.'), findsOneWidget);
    });

    testWidgets('one that could: what was not read is said, never "no sources found"', (
      tester,
    ) async {
      await _card(tester, _videoWithNoClaim([_framesCut, _speechCut]), kind: SubmissionKind.image);

      expect(find.text('Nothing to fact-check'), findsNothing);
      expect(find.text('Part of it could not be read'), findsOneWidget);
      expect(
        find.text(
          "Part of this couldn't be read, and we found no claim that can be checked in what "
          'could be read. See what was read below.',
        ),
        findsOneWidget,
      );
      expect(find.textContaining('Treat it with caution'), findsNothing);
      expect(find.text('No citable source was found'), findsNothing);
      expect(
        find.text("Some checks couldn't run, so this answer may be incomplete."),
        findsNothing,
      );
      // The AI note stays at the top: a clip heard in part is no less likely AI-made.
      expect(find.text(_aiVideo), findsOneWidget);
    });
  });

  group('gaps that share a code', () {
    ReadGap gap(String part, String code) =>
        ReadGap(part: part, code: code, detail: 'DETAIL', blocking: true);

    test('are each said for what was cut, and the same sentence only once', () {
      final lines = gapLines([
        gap('video', 'cut_off'),
        gap('transcript', 'cut_off'),
        gap('on_screen_text', 'cut_off'),
        gap('transcript', 'cut_off'),
        gap('picture_text', 'picture_unread'),
        gap('picture_text', 'picture_unread'),
      ], _en);
      expect(lines, [
        "Only the first part of the video was read, so what is shown or said after it wasn't "
            'checked.',
        "Only the start of what is said in the video was heard, so the rest wasn't checked.",
        'Only some of the words shown in the video were read.',
        "A picture in it couldn't be read.",
      ]);
      // In Hindi too, each its own sentence, and none of them English.
      final parts = ['video', 'transcript', 'on_screen_text', 'picture_text', 'document_text'];
      final every = [
        for (final part in [...parts, 'post']) gap(part, 'cut_off'),
      ];
      final hindi = gapLines(every, _hi);
      final english = gapLines(every, _en);
      expect(hindi, hasLength(6));
      expect(english, hasLength(6));
      expect(hindi.toSet().intersection(english.toSet()), isEmpty);
    });

    testWidgets('a long video cut three ways reads three lines, not one three times', (
      tester,
    ) async {
      await _card(
        tester,
        _videoWithNoClaim([
          (check: 'video', part: 'video', code: 'cut_off', blocking: true),
          _speechCut,
          _framesCut,
        ]),
        kind: SubmissionKind.image,
      );

      final banner = find.byKey(const ValueKey('read-gaps'));
      Finder line(String text) => find.descendant(of: banner, matching: find.text(text));
      expect(
        line(
          'Only the first part of the video was read, so what is shown or said after it '
          "wasn't checked.",
        ),
        findsOneWidget,
      );
      expect(
        line("Only the start of what is said in the video was heard, so the rest wasn't checked."),
        findsOneWidget,
      );
      expect(line('Only some of the words shown in the video were read.'), findsOneWidget);
      expect(line('It was too long to read to the end, so only the start was read.'), findsNothing);
    });
  });

  group('an upload', () {
    testWidgets('keeps its own picture and what it was read as at the head of the panel', (
      tester,
    ) async {
      await _card(
        tester,
        Verdict.fromJson(sampleImageUploadJson()),
        kind: SubmissionKind.image,
        thumbnail: _pixel,
      );

      expect(find.text('What Factify read · Image'), findsOneWidget);
      final thumbnail = find.byKey(const ValueKey('read-thumbnail'));
      expect(_inPanel(thumbnail), findsOneWidget);
      expect(
        tester.widget<Image>(find.descendant(of: thumbnail, matching: find.byType(Image))).image,
        isA<MemoryImage>(),
      );
      expect(_inPanel(find.text('Chat forward')), findsOneWidget);
      expect(_inPanel(find.text('Shows: Govt of India')), findsOneWidget);
      expect(_inPanel(find.text('Text in the picture')), findsOneWidget);
    });

    testWidgets("a post's pictures are not the person's: no thumbnail of theirs", (tester) async {
      await _card(tester, contractVerdict('x_photo_post'), thumbnail: _pixel);
      expect(find.byKey(const ValueKey('read-thumbnail')), findsNothing);
    });
  });

  testWidgets("a part's picture at the platform's own address is never loaded", (tester) async {
    final json = contractJson('x_photo_post');
    final parts = ((json['input_read'] as Map)['parts'] as List).cast<Map>();
    final first = parts.firstWhere((p) => p['media_url'] != null)['media_url'];
    for (final part in parts) {
      if (part['media_url'] == first) part['media_url'] = 'https://pbs.twimg.com/media/F1.jpg';
    }
    await _card(tester, Verdict.fromJson(json));
    await tester.tap(find.text('Show all'));
    await tester.pumpAndSettle();

    final urls = tester
        .widgetList<Image>(_inPanel(find.byType(Image)))
        .map((i) => i.image)
        .whereType<NetworkImage>()
        .map((i) => i.url)
        .toList();
    expect(urls, ['http://factify.test/v1/media/thumbnails/4e7a1c9d2b3f4a5e8d6c7b0a1f2e3d4c']);
  });
}
