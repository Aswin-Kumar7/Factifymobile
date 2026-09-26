/// Where each claim sits in the text that was checked, for the underlines on the
/// result (v5, "What we checked").
///
/// The server's anchor wins when it has one (contract 1.3 sends it per claim). A
/// claim without one is looked for in the text itself: word for word first, then
/// its longest run of four or more words - extraction tidies punctuation and drops
/// a trailing clause, and a claim that shares no such run with the text is not
/// underlined at all rather than underlined in the wrong place.
library;

import '../models/verdict.dart';

class ClaimSpan {
  const ClaimSpan(this.start, this.end, this.status);

  final int start;
  final int end;
  final ClaimStatus status;
}

/// [useAnchors] is off when [text] is not the exact text the server anchored its
/// claims in - a picture's reading, tidied for display - so its offsets would point
/// at the wrong words.
List<ClaimSpan> locateClaims(String text, List<Claim> claims, {bool useAnchors = true}) {
  if (text.isEmpty) return const [];
  final lower = text.toLowerCase();
  final found = <ClaimSpan>[];

  for (final claim in claims) {
    if (claim.claimType == 'MEDIA') continue;
    final span =
        (useAnchors ? _anchored(text, claim) : null) ??
        _exact(lower, claim) ??
        _longestRun(lower, claim);
    if (span == null) continue;
    final overlaps = found.any((f) => span.$1 < f.end && f.start < span.$2);
    if (!overlaps) found.add(ClaimSpan(span.$1, span.$2, claim.status));
  }
  found.sort((a, b) => a.start.compareTo(b.start));
  return found;
}

(int, int)? _anchored(String text, Claim claim) {
  final anchor = claim.inputAnchor;
  final start = anchor?.charStart;
  final end = anchor?.charEnd;
  if (start == null || end == null || start < 0 || end > text.length || start >= end) {
    return null;
  }
  // Offsets into some other text - an older server's, or a copy tidied since - land
  // on words the claim does not contain. Those are not underlined.
  final claimWords = _words(claim.text);
  if (!_words(text.substring(start, end)).any(claimWords.contains)) return null;
  return (start, end);
}

// Letters with their combining marks, so a Hindi word is not cut at each vowel sign.
final _word = RegExp(r'[\p{L}\p{M}\p{N}]{3,}', unicode: true);

Set<String> _words(String value) =>
    _word.allMatches(value.toLowerCase()).map((m) => m.group(0)!).toSet();

String _plain(String value) =>
    value.toLowerCase().replaceAll(RegExp(r'\s+'), ' ').replaceAll(RegExp(r'[.!?।]+$'), '').trim();

(int, int)? _exact(String lower, Claim claim) {
  final needle = _plain(claim.text);
  if (needle.length < 8) return null;
  final at = lower.indexOf(needle);
  return at < 0 ? null : (at, at + needle.length);
}

(int, int)? _longestRun(String lower, Claim claim) {
  final words = _plain(claim.text).split(' ').where((w) => w.isNotEmpty).toList();
  for (var length = words.length - 1; length >= 4; length--) {
    for (var start = 0; start + length <= words.length; start++) {
      final fragment = words.sublist(start, start + length).join(' ');
      final at = lower.indexOf(fragment);
      if (at >= 0) return (at, at + fragment.length);
    }
  }
  return null;
}
