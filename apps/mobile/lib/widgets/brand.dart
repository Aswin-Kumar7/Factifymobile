/// The Factify mark, and the brand emerald it sits on.
///
/// The splash is the one screen drawn in the brand's own colours in both light and
/// dark mode - it matches the native launch screen shown before Flutter starts -
/// so its greens are named here rather than read from the theme tokens, whose
/// dark accent is a lighter emerald meant for text on a dark page.
library;

import 'package:flutter/material.dart';

abstract final class FactifyBrand {
  /// The light theme's accent (tokens `acc`).
  static const emerald = Color(0xFF0E6B4F);

  /// A shade deeper, for the splash gradient and the mark's shadow.
  static const emeraldDeep = Color(0xFF0B5A42);
}

/// The rounded emerald square with the check-list mark.
class FactifyMark extends StatelessWidget {
  const FactifyMark({this.size = 56, this.onDark = false, super.key});

  final double size;

  /// On an emerald background the mark is drawn white, with an emerald glyph.
  final bool onDark;

  @override
  Widget build(BuildContext context) => Container(
    width: size,
    height: size,
    decoration: BoxDecoration(
      color: onDark ? Colors.white : null,
      gradient: onDark
          ? null
          : const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [FactifyBrand.emerald, FactifyBrand.emeraldDeep],
            ),
      borderRadius: BorderRadius.circular(size * 0.28),
      boxShadow: [
        BoxShadow(
          color: FactifyBrand.emeraldDeep.withValues(alpha: onDark ? 0.25 : 0.18),
          blurRadius: size * 0.35,
          offset: Offset(0, size * 0.12),
        ),
      ],
    ),
    child: Icon(
      Icons.fact_check_rounded,
      size: size * 0.56,
      color: onDark ? FactifyBrand.emerald : Colors.white,
    ),
  );
}
