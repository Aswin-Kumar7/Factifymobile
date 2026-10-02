/// What Factify read (contract 1.8): the input, part by part, and what could not be.
///
/// A verdict is only ever about what was read. A post whose caption stopped at
/// "… more", a video whose speech could not be heard, an article behind a sign-in
/// wall: each was once checked as if it were the whole thing, and the answer gave no
/// sign that half of it had never been seen. This panel replaces "What we checked"
/// in the same place on the result, and says it plainly:
///
///   * Who posted it, where and when, from what the platform said - not from the
///     link that was typed.
///   * When something could not be read, a warning first, a line for each thing not
///     read (said once, however many gaps share it), in the reader's language (the
///     server's English sentence only for a gap this version of the app does not
///     know).
///   * For an upload, the person's own picture and what kind of picture it was read
///     as, as "What we checked" showed them.
///   * Every part in the order a person meets it - the post, the text in each of its
///     pictures, what is said in its video - each labelled, with each claim
///     underlined in the part it was found in.
///   * Factify's own description of what a picture or video shows is muted and
///     never quoted as the input's words. It says whether it was checked beside the
///     input's own words or only shown ("description only, not checked").
///
/// Open by default when something could not be read or the answer was held back;
/// otherwise folded to its first lines, with "Show all".
library;

import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart' hide TextDirection;

import '../l10n/app_localizations.dart';
import '../models/verdict.dart';
import 'action_style.dart';
import 'claim_spans.dart';
import 'claim_words.dart';
import 'ui/ui.dart';

/// Platform names as the platforms write them, in every language.
const Map<String, String> _platformNames = {
  'x': 'X',
  'instagram': 'Instagram',
  'youtube': 'YouTube',
  'facebook': 'Facebook',
};

/// A platform as people write it: "x" is X. Null for none.
String? platformName(String? platform) {
  if (platform == null || platform.isEmpty) return null;
  return _platformNames[platform.toLowerCase()] ?? platform;
}

/// What the reading was of, as the warning and the chip name it: post, page, video,
/// picture, document or other (the `kind` of `readPartial` and `checkedPartially`).
String readThing(InputRead read) => switch (read.kind) {
  'social_post' => read.platform == 'youtube' ? 'video' : 'post',
  'link' => 'page',
  'video' => 'video',
  'image' => 'picture',
  'pdf' => 'document',
  _ => 'other',
};

/// What could not be read, in the reader's language. A code this app does not know
/// yet is said in the server's own English sentence rather than not at all.
String gapLine(ReadGap gap, AppLocalizations l10n) => switch (gap.code) {
  'headline_only' => l10n.gapHeadlineOnly,
  'text_truncated' => l10n.gapTextTruncated,
  'post_unavailable' => l10n.gapPostUnavailable,
  'login_required' => l10n.gapLoginRequired,
  'not_supported' => l10n.gapNotSupported,
  'picture_unread' => l10n.gapPictureUnread,
  'video_unread' => l10n.gapVideoUnread,
  'speech_unread' => l10n.gapSpeechUnread,
  // One video can be cut off three ways at once - its frames, its speech, the words
  // shown in it - and each is said for what it is (app/api/verify.py).
  'cut_off' => l10n.gapCutOff(_cutOffPart(gap.part)),
  'pages_unread' => l10n.gapPagesUnread,
  'too_large' => l10n.gapTooLarge,
  'needs_background' => l10n.gapNeedsBackground,
  'reader_unavailable' => l10n.gapReaderUnavailable,
  'first_picture_only' => l10n.gapFirstPictureOnly,
  'article_truncated' => l10n.gapArticleTruncated,
  'description_unread' => l10n.gapDescriptionUnread,
  'linked_page_unread' => l10n.gapLinkedPageUnread,
  _ => gap.detail,
};

/// What a cut-off gap was cut from, as `gapCutOff` selects on it: a part kind, or
/// "video" for the video as a whole. Anything else is said in general.
String _cutOffPart(String part) => switch (part) {
  'video' || 'transcript' || 'on_screen_text' || 'picture_text' || 'document_text' => part,
  _ => 'other',
};

/// What could not be read, a line each, in the order the server found it - and
/// each line once: two pictures of an album that could not be read are one
/// sentence, not the same sentence twice.
List<String> gapLines(Iterable<ReadGap> gaps, AppLocalizations l10n) =>
    {for (final gap in gaps) gapLine(gap, l10n)}.toList();

/// The line under the verdict word, wherever the verdict is shown. An answer
/// unconfirmed only because part of the input could not be read says so: the action
/// it shares with "too recent to confirm" (WAIT_AND_RECHECK) would otherwise word it
/// as a matter of time, and send the person to wait for nothing.
String verdictSubhead(Verdict verdict, ActionStyle style, AppLocalizations l10n) =>
    verdict.partlyRead || verdict.unreadNothingFound ? l10n.subheadPartlyRead : style.subhead;

/// A limit the server states in English, in the reader's language when it is one
/// this app knows.
String limitLine(String limit, AppLocalizations l10n) =>
    limit.startsWith('YouTube does not let Factify download') ? l10n.readYoutubeLimit : limit;

/// Seconds as a clock reads them: "1:32", "14:02", "1:05:00".
String clockTime(int seconds) {
  final s = math.max(0, seconds);
  final hours = s ~/ 3600;
  final minutes = (s % 3600) ~/ 60;
  final rest = (s % 60).toString().padLeft(2, '0');
  return hours > 0 ? '$hours:${minutes.toString().padLeft(2, '0')}:$rest' : '$minutes:$rest';
}

/// The heading of one part, in the reader's language.
///
/// Worded here from the part's kind, not taken from the server's English label,
/// except for what only the label knows: who a quoted post is by, and which site a
/// linked article is on - names, written the same in every language.
String partLabel(ReadPart part, InputRead read, AppLocalizations l10n) {
  final label = part.label ?? '';
  String described(String what) =>
      '$what · ${part.checked ? l10n.readDescribedByFactify : l10n.readNotChecked}';
  switch (part.kind) {
    case 'message':
      return l10n.partMessage;
    case 'post_text':
      return l10n.partPost;
    case 'quoted_post':
      // "Quoted post by Ravi Kumar (@ravik) on X, 30 Sep 2026" (reading.post_label).
      final who = RegExp(r'\bby (.+?)(?: on [A-Z]\w*)?(?:, \d.*)?$').firstMatch(label)?.group(1);
      return who == null ? l10n.partQuotedPost : l10n.partQuotedPostBy(who);
    case 'title':
      return l10n.partTitle;
    case 'description':
      return l10n.partDescription;
    case 'article':
      return l10n.partArticle;
    case 'linked_article':
      // "Linked article (thehindu.com)" (reading.linked_article_label).
      final host = RegExp(r'\(([^()\s]+)\)\s*$').firstMatch(label)?.group(1);
      return host == null ? l10n.partLinkedArticle : l10n.partLinkedArticleOn(host);
    case 'picture_text':
      final pictures = read.parts.where((p) => p.isPictureText).toList();
      final index = pictures.indexOf(part) + 1;
      return pictures.length <= 1
          ? l10n.textInPicture
          : l10n.partPictureText(index, pictures.length);
    case 'picture_description':
      return described(l10n.partPictureDescription);
    case 'transcript':
      return l10n.saidInVideo;
    case 'on_screen_text':
      return l10n.partOnScreenText;
    case 'video_description':
      return described(l10n.partVideoDescription);
    case 'document_text':
      return l10n.partDocumentText;
    default:
      // A kind added after this app was built: the server's label, which is English
      // but says what it is.
      return part.checked ? label : '$label · ${l10n.readNotChecked}';
  }
}

/// What the thing read was, for the panel's heading: "X post", "Link · thehindu.com".
String readKindLabel(InputRead read, AppLocalizations l10n) {
  switch (read.kind) {
    case 'social_post':
      final platform = platformName(read.platform);
      if (platform == null) return l10n.kindPost;
      return read.platform == 'youtube' ? l10n.kindVideoOn(platform) : l10n.kindPostOn(platform);
    case 'link':
      final host = read.host;
      return host == null ? l10n.kindLink : '${l10n.kindLink} · $host';
    case 'image':
      return l10n.kindImage;
    case 'video':
      return l10n.kindVideo;
    case 'pdf':
      return l10n.kindPdf;
    default:
      return l10n.kindText;
  }
}

IconData _iconFor(InputRead read) => switch (read.kind) {
  'social_post' => read.platform == 'youtube' ? FxIcons.video : FxIcons.chat,
  'link' => FxIcons.link,
  'image' => FxIcons.image,
  'video' => FxIcons.video,
  'pdf' => FxIcons.pdf,
  _ => FxIcons.text,
};

/// What was read, as one line for the quick verdict: "post · 2 pictures · video 1:32".
String readSummary(InputRead read, AppLocalizations l10n) {
  final parts = read.parts;
  bool has(String kind) => parts.any((p) => p.kind == kind);
  final pictures = math.max(
    parts.where((p) => p.isPictureText).length,
    parts.where((p) => p.kind == 'picture_description').length,
  );
  final heard = parts.where((p) => p.kind == 'transcript').firstOrNull;
  final length = heard?.secondsTotal ?? heard?.secondsRead;
  final video = heard != null || has('on_screen_text') || has('video_description');
  return [
    if (has('message')) l10n.quickReadMessage,
    if (has('post_text')) l10n.quickReadPost,
    if (has('quoted_post')) l10n.quickReadQuoted,
    // A YouTube video's title and description are the video's, not a page's.
    if (!read.isPost && (has('title') || has('description') || has('article')))
      l10n.quickReadPage,
    if (has('linked_article')) l10n.quickReadLinked,
    if (pictures > 0) l10n.quickReadPictures(pictures),
    if (video) length == null ? l10n.quickReadVideo : l10n.quickReadVideoLength(clockTime(length)),
    if (has('document_text')) l10n.quickReadDocument,
  ].join(' · ');
}

/// Where each claim found in [part] sits in its text, for the underlines.
///
/// A claim's anchor is into the whole text claims were found in, of which this part
/// is one span; it is underlined here only if it falls in this part, at the same
/// words, and the offsets are moved into the part. The server counts characters as
/// Unicode code points and Dart as UTF-16 units, so an emoji before a claim would
/// otherwise push the underline off by one per emoji. A claim with no anchor is
/// looked for by its words, as on a result from before 1.3. Nothing is ever
/// underlined in a part that was not checked.
List<ClaimSpan> claimsInPart(ReadPart part, Iterable<Claim> claims) {
  if (!part.checked || part.text.isEmpty) return const [];
  final start = part.charStart;
  final end = part.charEnd;
  final placed = <Claim>[];
  for (final claim in claims) {
    if (claim.claimType == 'MEDIA') continue;
    final anchor = claim.inputAnchor;
    final from = anchor?.charStart;
    if (from == null || start == null || end == null) {
      placed.add(_placed(claim, null));
      continue;
    }
    // Said in another part of the input.
    if (from < start || from >= end) continue;
    final to = math.min(anchor?.charEnd ?? end, end);
    placed.add(
      _placed(
        claim,
        InputAnchor(
          charStart: _units(part.text, from - start),
          charEnd: _units(part.text, to - start),
        ),
      ),
    );
  }
  return locateClaims(part.text, placed);
}

/// Where a claim's [anchor] falls in what was read: the part it is in, and its span
/// in that part's own text, in Dart's UTF-16 offsets. Null when it falls in no part
/// - an older server's anchor, or one into text this reading does not hold.
({ReadPart part, int start, int end})? anchorInPart(InputRead read, InputAnchor anchor) {
  final at = anchor.charStart;
  final until = anchor.charEnd;
  if (at == null || until == null || until <= at) return null;
  final part = read.partAt(at);
  final start = part?.charStart;
  final end = part?.charEnd;
  if (part == null || start == null || end == null) return null;
  return (
    part: part,
    start: _units(part.text, at - start),
    end: _units(part.text, math.min(until, end) - start),
  );
}

/// [claim], anchored at [anchor] in one part's text (or nowhere, to be found by its
/// words). Its status and rule are kept, which is all its underline's colour needs.
Claim _placed(Claim claim, InputAnchor? anchor) => Claim(
  id: claim.id,
  text: claim.text,
  claimType: claim.claimType,
  status: claim.status,
  severity: claim.severity,
  importance: claim.importance,
  reason: claim.reason,
  strength: claim.strength,
  evidence: const [],
  ownAnchor: anchor,
  ruleId: claim.ruleId,
  language: claim.language,
);

/// The UTF-16 offset of the [codePoints]th character of [text].
int _units(String text, int codePoints) {
  if (codePoints <= 0) return 0;
  var units = 0;
  var seen = 0;
  for (final rune in text.runes) {
    if (seen == codePoints) break;
    units += rune > 0xFFFF ? 2 : 1;
    seen++;
  }
  return units;
}

/// A part's text cut at [limit] characters, never inside a surrogate pair.
String _cut(String text, int limit) {
  if (text.length <= limit) return text;
  final last = text.codeUnitAt(limit - 1);
  final inPair = last >= 0xD800 && last <= 0xDBFF;
  return text.substring(0, inPair ? limit - 1 : limit);
}

/// The panel. Shown by the result in place of "What we checked" whenever the server
/// says what it read ([Verdict.inputRead]).
class WhatWeRead extends StatefulWidget {
  const WhatWeRead({
    required this.verdict,
    required this.read,
    this.serverUrl,
    this.thumbnail,
    super.key,
  });

  final Verdict verdict;
  final InputRead read;

  /// Where a part's picture is served from. Without it no picture is shown.
  final String? serverUrl;

  /// The person's own upload, as picked on this phone: shown at the head of the
  /// panel, as "What we checked" showed it, for a picture, a video or a PDF.
  final Uint8List? thumbnail;

  @override
  State<WhatWeRead> createState() => _WhatWeReadState();
}

class _WhatWeReadState extends State<WhatWeRead> {
  /// Characters of a part shown before "Show all the text".
  static const _limit = 600;

  late bool _open = _opensAtFirst;
  bool _whole = false;

  InputRead get _read => widget.read;

  /// The parts worth a line: a picture read in full that has no words in it still
  /// is (it says so); any other part with nothing in it is not.
  List<ReadPart> get _shown =>
      _read.parts.where((p) => p.isPictureText || p.text.trim().isNotEmpty).toList();

  bool get _opensAtFirst {
    if (!_read.complete || _read.verdictWithheld) return true;
    final shown = _shown;
    // Nothing to fold: one short part is shown whole.
    return shown.length <= 1 && (shown.firstOrNull?.text.length ?? 0) <= 180;
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final read = _read;
    final verdict = widget.verdict;
    final shown = _shown;
    // Nothing is underlined in an answer that was held back, or had nothing in it to
    // check: no claim was found there to underline.
    final claims = verdict.withheld || verdict.nothingToCheck ? const <Claim>[] : verdict.claims;
    final visible = _open ? shown : shown.take(1).toList();
    final spans = {for (final part in visible) part: claimsInPart(part, claims)};
    final keys = {
      for (final list in spans.values)
        for (final span in list) span.mark,
    }.toList();
    final long = _open && shown.any((p) => p.text.length > _limit);
    final seenPictures = <String>{};
    final upload = _uploads.contains(read.kind);
    final thumbnail = upload ? widget.thumbnail : null;
    // What kind of picture it is and whose name it carries, as the picture's reading
    // says - the chips "What we checked" showed for an upload.
    final reading = upload ? verdict.imageReading : null;
    final publisher = (reading?.publisher ?? '').trim();

    return FxCard(
      key: const ValueKey('what-we-read'),
      padding: const EdgeInsets.fromLTRB(14, 13, 14, 13),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              if (thumbnail != null)
                ClipRRect(
                  key: const ValueKey('read-thumbnail'),
                  borderRadius: BorderRadius.circular(6),
                  child: Image.memory(
                    thumbnail,
                    width: 22,
                    height: 22,
                    fit: BoxFit.cover,
                    excludeFromSemantics: true,
                    errorBuilder: (_, _, _) => Icon(_iconFor(read), size: 14, color: k.ink3),
                  ),
                )
              else
                Icon(_iconFor(read), size: 14, color: k.ink3),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  l10n.whatWeReadKind(readKindLabel(read, l10n)),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: FactifyText.sans(11.5, weight: FontWeight.w600, color: k.ink3),
                ),
              ),
            ],
          ),
          if (_byline(context) case final byline?) ...[
            const SizedBox(height: 4),
            Text(byline, style: FactifyText.sans(12.5, weight: FontWeight.w600, color: k.ink2)),
          ],
          if (reading != null && (reading.kind != null || publisher.isNotEmpty)) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                if (reading.kind != null)
                  FxChip(label: l10n.imageKind(reading.kind!), height: 26, fontSize: 11.5),
                if (publisher.isNotEmpty)
                  FxChip(label: l10n.shows(publisher), height: 26, fontSize: 11.5),
              ],
            ),
          ],
          if (!read.complete) ...[const SizedBox(height: 10), _GapBanner(read: read)],
          if (shown.isEmpty) ...[
            const SizedBox(height: 10),
            Text(l10n.readNothing, style: FactifyText.sans(12.5, color: k.ink3)),
          ],
          for (final (index, part) in visible.indexed) ...[
            SizedBox(height: index == 0 ? 12 : 16),
            _Part(
              part: part,
              label: partLabel(part, read, l10n),
              spans: spans[part] ?? const [],
              folded: !_open,
              limit: _whole ? null : _limit,
              // A picture is shown once, beside the first part read from it.
              picture: part.mediaUrl != null && seenPictures.add(part.mediaUrl!)
                  ? _pictureUrl(part.mediaUrl!)
                  : null,
            ),
          ],
          if (!_open || long)
            _Toggle(
              label: !_open
                  ? l10n.readShowAll
                  : _whole
                  ? l10n.imageShowLessText
                  : l10n.imageShowAllText,
              onTap: () => setState(() {
                if (!_open) {
                  _open = true;
                } else {
                  _whole = !_whole;
                }
              }),
            ),
          // Shown folded or not: a check that did not run is part of the answer.
          for (final limit in read.limits) ...[
            const SizedBox(height: 10),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(FxIcons.info, size: 15, color: k.ink3),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    limitLine(limit, l10n),
                    style: FactifyText.sans(12, color: k.ink3).copyWith(height: 1.45),
                  ),
                ),
              ],
            ),
          ],
          if (keys.isNotEmpty) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 12,
              runSpacing: 4,
              children: [
                for (final mark in keys)
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 14,
                        height: 2,
                        decoration: BoxDecoration(
                          color: ActionStyle.forMark(mark, k.brightness),
                          borderRadius: BorderRadius.circular(1),
                        ),
                      ),
                      const SizedBox(width: 5),
                      Text(claimStateLabel(mark, l10n), style: FactifyText.sans(11, color: k.ink3)),
                    ],
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  /// Who posted it and when, as the platform says; for a page, when it was published.
  String? _byline(BuildContext context) {
    final read = _read;
    final l10n = AppLocalizations.of(context);
    final locale = Localizations.localeOf(context).toLanguageTag();
    final published = read.publishedAt;
    final date = published == null
        ? null
        : DateFormat('d MMM yyyy', locale).format(published.toLocal());
    if (read.isPost) {
      final author = (read.author ?? '').trim();
      final handle = (read.handle ?? '').trim().replaceFirst(RegExp('^@'), '');
      final line = [
        if (author.isNotEmpty) author,
        if (handle.isNotEmpty) '@$handle',
        ?date,
      ];
      return line.isEmpty ? null : line.join(' · ');
    }
    if (read.kind == 'link' && date != null) return l10n.mediaPublished(date);
    return null;
  }

  /// A part's picture, only ever from our own server: a path under /v1/media/,
  /// joined to it. A platform's own address (pbs.twimg.com, a cdninstagram link)
  /// would tell the platform who is looking, and is never loaded.
  String? _pictureUrl(String path) {
    final server = widget.serverUrl;
    if (server == null || !path.startsWith(_ownMedia) || path.contains('..')) return null;
    return '$server$path';
  }

  static const _ownMedia = '/v1/media/';

  /// The kinds of reading that are of the person's own upload.
  static const _uploads = {'image', 'video', 'pdf'};
}

/// "Factify could only read part of this post.", and a line for each gap.
class _GapBanner extends StatelessWidget {
  const _GapBanner({required this.read});

  final InputRead read;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    // Amber when what was missed could decide the answer; plain when it could not
    // (an album's later pictures, the tail of a long article).
    final blocked = read.blocked;
    return Container(
      key: const ValueKey('read-gaps'),
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
      decoration: BoxDecoration(
        color: blocked ? Color.alphaBlend(k.mS, k.bg) : k.sf2,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(FxIcons.hidden, size: 16, color: blocked ? k.mC : k.ink3),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  l10n.readPartial(readThing(read)),
                  style: FactifyText.sans(13, weight: FontWeight.w600, color: k.ink),
                ),
                for (final line in gapLines(read.gaps, l10n)) ...[
                  const SizedBox(height: 4),
                  Text(line, style: FactifyText.sans(12.5, color: k.ink2).copyWith(height: 1.45)),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// One part: its heading, the picture it was read from, and its words.
class _Part extends StatelessWidget {
  const _Part({
    required this.part,
    required this.label,
    required this.spans,
    required this.folded,
    required this.limit,
    this.picture,
  });

  final ReadPart part;
  final String label;
  final List<ClaimSpan> spans;

  /// Shown as the panel's first lines only.
  final bool folded;

  /// Characters shown before "Show all the text"; null for all of them.
  final int? limit;

  /// The address of the picture it was read from, on our own server.
  final String? picture;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final text = part.text.trim().isEmpty ? '' : part.text;
    final cut = limit == null || folded ? text : _cut(text, limit!);
    final shortened = cut.length < text.length;
    final heard = _heard(l10n);
    final english = l10n.localeName == 'en';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            if (picture != null) _Thumb(url: picture!),
            Expanded(
              flex: 3,
              child: Text(
                label,
                style: FactifyText.sans(11.5, weight: FontWeight.w600, color: k.ink3),
              ),
            ),
            // Beside the label, and wrapping under itself rather than off the
            // screen: "read only in part" in Hindi at 130% is wider than half a phone.
            if (!part.complete) ...[
              const SizedBox(width: 8),
              Flexible(
                flex: 2,
                child: Text(
                  l10n.readInPart,
                  textAlign: TextAlign.end,
                  style: FactifyText.sans(11, weight: FontWeight.w600, color: k.mC),
                ),
              ),
            ],
          ],
        ),
        const SizedBox(height: 6),
        if (text.isEmpty)
          // A picture read in full with no words in it: said, so its silence is not
          // taken for a failure to read it.
          Text(l10n.imageNoText, style: FactifyText.sans(12, color: k.ink3))
        else
          UnderlinedQuote(
            text: cut,
            spans: [
              for (final s in spans)
                if (s.start < cut.length) ClaimSpan(s.start, math.min(s.end, cut.length), s.mark),
            ],
            shortened: shortened,
            maxLines: folded ? 3 : null,
            // Factify's own words about what was shown: never quoted as the input's.
            description: part.isDescription,
          ),
        if (heard != null && !folded) ...[
          const SizedBox(height: 6),
          Text(heard, style: FactifyText.sans(12, color: k.ink3)),
        ],
        // The reader's own aside ("read from 24 frames") is English, and adds detail
        // rather than meaning: shown to an English reader only.
        if (english && !folded && (part.note ?? '').trim().isNotEmpty) ...[
          const SizedBox(height: 4),
          Text(part.note!, style: FactifyText.sans(11.5, color: k.ink3)),
        ],
      ],
    );
  }

  /// "10:00 of 14:02 heard", for speech.
  String? _heard(AppLocalizations l10n) {
    if (part.kind != 'transcript') return null;
    final read = part.secondsRead;
    final total = part.secondsTotal;
    if (total == null) return null;
    if (read == null || read >= total) return l10n.readHeardAll(clockTime(total));
    return l10n.readHeard(clockTime(read), clockTime(total));
  }
}

/// The picture a part was read from, small, from our own server. Hidden when it is
/// gone (kept an hour) or cannot be shown: the words beside it stand without it.
class _Thumb extends StatelessWidget {
  const _Thumb({required this.url});

  final String url;

  @override
  Widget build(BuildContext context) => Image.network(
    url,
    width: 28,
    height: 28,
    fit: BoxFit.cover,
    excludeFromSemantics: true,
    frameBuilder: (context, child, frame, sync) => Padding(
      padding: const EdgeInsetsDirectional.only(end: 8),
      child: ClipRRect(borderRadius: BorderRadius.circular(6), child: child),
    ),
    errorBuilder: (_, _, _) => const SizedBox.shrink(),
  );
}

/// "Show all", "Show all the text", "Show less": a link, 44 tall to the thumb.
class _Toggle extends StatelessWidget {
  const _Toggle({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Semantics(
      button: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 44, minWidth: 44),
          child: Align(
            alignment: AlignmentDirectional.centerStart,
            widthFactor: 1,
            child: Text(
              label,
              style: FactifyText.sans(12.5, weight: FontWeight.w600, color: k.acc),
            ),
          ),
        ),
      ),
    );
  }
}

/// Text as it was read, with each claim underlined in its colour.
///
/// The input's own words are quoted; Factify's [description] of what a picture or
/// video shows is not - it is set muted, in italics, and without quotation marks.
class UnderlinedQuote extends StatelessWidget {
  const UnderlinedQuote({
    required this.text,
    required this.spans,
    required this.shortened,
    this.maxLines,
    this.description = false,
    super.key,
  });

  final String text;
  final List<ClaimSpan> spans;

  /// Cut short: closed with an ellipsis.
  final bool shortened;

  /// Folded to its first lines.
  final int? maxLines;

  /// Factify's description of what was shown, not the input's own words.
  final bool description;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final base = description
        ? FactifyText.sans(
            13,
            color: k.ink3,
          ).copyWith(height: 1.5, fontStyle: FontStyle.italic)
        : FactifyText.serif(16.5, weight: FontWeight.w400, color: k.ink).copyWith(height: 1.5);
    final parts = <InlineSpan>[if (!description) const TextSpan(text: '“')];
    var at = 0;
    for (final span in spans) {
      if (span.start < at || span.end > text.length) continue;
      if (span.start > at) parts.add(TextSpan(text: text.substring(at, span.start)));
      parts.add(
        TextSpan(
          text: text.substring(span.start, span.end),
          style: TextStyle(
            decoration: TextDecoration.underline,
            decorationColor: ActionStyle.forMark(span.mark, k.brightness),
            decorationThickness: 2,
            backgroundColor: ActionStyle.tintForMark(span.mark, k.brightness),
          ),
        ),
      );
      at = span.end;
    }
    if (at < text.length) parts.add(TextSpan(text: text.substring(at)));
    if (description) {
      if (shortened) parts.add(const TextSpan(text: '…'));
    } else {
      parts.add(TextSpan(text: shortened ? '…”' : '”'));
    }
    return Text.rich(
      TextSpan(children: parts),
      style: base,
      maxLines: maxLines,
      overflow: maxLines == null ? null : TextOverflow.ellipsis,
    );
  }
}
