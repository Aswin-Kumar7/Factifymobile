/// The Factify mark and wordmark, drawn the same everywhere they appear.
library;

import 'package:flutter/material.dart';

import '../theme/colors.dart';

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
              colors: [FactifyColors.emerald, FactifyColors.emeraldDeep],
            ),
      borderRadius: BorderRadius.circular(size * 0.28),
      boxShadow: [
        BoxShadow(
          color: FactifyColors.emeraldDeep.withValues(alpha: onDark ? 0.25 : 0.18),
          blurRadius: size * 0.35,
          offset: Offset(0, size * 0.12),
        ),
      ],
    ),
    child: Icon(
      Icons.fact_check_rounded,
      size: size * 0.56,
      color: onDark ? FactifyColors.emerald : Colors.white,
    ),
  );
}

/// The mark beside the name, for headers.
class FactifyWordmark extends StatelessWidget {
  const FactifyWordmark({this.size = 30, super.key});

  final double size;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      FactifyMark(size: size),
      SizedBox(width: size * 0.34),
      Text(
        'Factify',
        style: TextStyle(
          fontSize: size * 0.7,
          fontWeight: FontWeight.w800,
          letterSpacing: -0.4,
          color: FactifyColors.ink,
        ),
      ),
    ],
  );
}
