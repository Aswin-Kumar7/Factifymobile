/// A publisher's initials in a tile (v5): "PIB", "AN", "TH".
///
/// A muted tile by default; filled emerald once that source is found to address the
/// claim. Initials, not logos: a logo would have to be fetched from the publisher,
/// and the app talks only to Factify's own server.
library;

import 'package:flutter/material.dart';

import '../../theme/tokens.dart';
import '../../theme/typography.dart';

class FxSourceAvatar extends StatelessWidget {
  const FxSourceAvatar({
    required this.initials,
    this.size = 30,
    this.radius,
    this.found = false,
    this.fontSize,
    super.key,
  });

  final String initials;
  final double size;

  /// Null for a circle.
  final double? radius;
  final bool found;
  final double? fontSize;

  /// Up to three letters for a publisher, as the design writes them: a short
  /// acronym it carries ("PIB Fact Check" -> PIB, "Ministry of WCD" -> WCD), else the
  /// first letters of its words ("The Hindu" -> TH, "Reserve Bank of India" -> RBI),
  /// else the first letter of its one word ("Reuters" -> R).
  static String initialsOf(String publisher) {
    final words = publisher
        .trim()
        .replaceFirst(RegExp(r'^www\.'), '')
        .replaceAll(RegExp(r'\.(com|in|org|net|co\.in|gov\.in|co\.uk)$'), '')
        .split(RegExp(r'[\s.\-_]+'))
        .where((w) => w.isNotEmpty)
        .toList();
    if (words.isEmpty) return '?';
    final acronym = words.firstWhere(
      (w) =>
          w.length >= 2 && w.length <= 3 && w.toUpperCase() == w && RegExp(r'^[A-Z]+$').hasMatch(w),
      orElse: () => '',
    );
    if (acronym.isNotEmpty) return acronym;
    final named = words.where((w) => !const {'of', 'and', 'for', '&'}.contains(w.toLowerCase()));
    if (named.length == 1) return named.first.characters.first.toUpperCase();
    return named.take(3).map((w) => w.characters.first.toUpperCase()).join();
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: found ? k.acc : k.sf2,
        shape: radius == null ? BoxShape.circle : BoxShape.rectangle,
        borderRadius: radius == null ? null : BorderRadius.circular(radius!),
      ),
      child: Text(
        initials,
        maxLines: 1,
        style: FactifyText.sans(
          fontSize ?? (size * 0.34).clamp(7.5, 14),
          weight: FontWeight.w700,
          color: found ? k.onAcc : k.ink2,
        ),
      ),
    );
  }
}
