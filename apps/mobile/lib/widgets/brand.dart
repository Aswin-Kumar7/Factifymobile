/// The Factify mark - the newsroom seal - and the brand colours it is drawn in.
///
/// The seal: a stamped ring of dashes, a white disc with a serif F, and a mint badge
/// with a tick at its lower right. The same numbers, on a 96-unit square, draw the
/// Android icons (`tool/render_brand_icons.py`), so the launcher icon, the native
/// launch screen and this widget are one mark.
///
/// The splash is the one screen drawn in the brand's own colours in both light and
/// dark mode - it matches the native launch screen shown before Flutter starts -
/// so its greens are named here rather than read from the theme tokens, whose
/// dark accent is a lighter emerald meant for text on a dark page.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme/typography.dart';

abstract final class FactifyBrand {
  /// The light theme's accent (tokens `acc`).
  static const emerald = Color(0xFF0E6B4F);

  /// A shade deeper, for the splash gradient and the mark's shadow.
  static const emeraldDeep = Color(0xFF0B5A42);

  /// The seal's approval badge.
  static const mint = Color(0xFF7FE0B8);
}

/// The newsroom seal.
///
/// On its own emerald square by default; with [onDark] the square is left out, for
/// a page that is already emerald (the splash), where the seal sits as it does on
/// the native launch screen.
class FactifyMark extends StatelessWidget {
  const FactifyMark({this.size = 56, this.onDark = false, super.key});

  final double size;

  /// Drawn straight onto an emerald page, without its own square.
  final bool onDark;

  @override
  Widget build(BuildContext context) => Semantics(
    label: 'Factify',
    image: true,
    excludeSemantics: true,
    child: Container(
      width: size,
      height: size,
      decoration: onDark
          ? null
          : BoxDecoration(
              color: FactifyBrand.emerald,
              borderRadius: BorderRadius.circular(size * 26 / 96),
              boxShadow: [
                BoxShadow(
                  color: FactifyBrand.emeraldDeep.withValues(alpha: 0.18),
                  blurRadius: size * 0.3,
                  offset: Offset(0, size * 0.1),
                ),
              ],
            ),
      child: CustomPaint(painter: _SealPainter()),
    ),
  );
}

class _SealPainter extends CustomPainter {
  // tool/render_brand_icons.py, in units of a 96 square.
  static const _centre = 48.0;
  static const _ringR = 31.0;
  static const _ringW = 3.2;
  static const _dashes = 28;
  static const _discR = 23.5;
  static const _fSize = 36.0;
  static const _badge = Offset(67, 67);
  static const _badgeR = 10.0;

  @override
  void paint(Canvas canvas, Size size) {
    final u = size.width / 96;
    canvas.scale(u);
    const centre = Offset(_centre, _centre);

    final ring = Paint()
      ..color = Colors.white
      ..style = PaintingStyle.stroke
      ..strokeWidth = _ringW;
    const step = 2 * math.pi / _dashes;
    for (var i = 0; i < _dashes; i++) {
      canvas.drawArc(
        Rect.fromCircle(center: centre, radius: _ringR),
        step * i,
        step * 0.55,
        false,
        ring,
      );
    }

    canvas.drawCircle(centre, _discR, Paint()..color = Colors.white);

    // The F, in the app's own serif. A name, the same in every language.
    final f = TextPainter(
      text: TextSpan(
        text: 'F',
        style: TextStyle(
          fontFamily: FxFonts.serif,
          fontSize: _fSize,
          fontWeight: FontWeight.w600,
          height: 1,
          color: FactifyBrand.emerald,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    f.paint(canvas, centre - Offset(f.width / 2, f.height / 2 - 0.5));
    f.dispose();

    // The approval: a mint badge with an emerald tick, over the ring.
    canvas
      ..drawCircle(_badge, _badgeR + 2.4, Paint()..color = FactifyBrand.emerald)
      ..drawCircle(_badge, _badgeR, Paint()..color = FactifyBrand.mint)
      ..drawPath(
        Path()
          ..moveTo(_badge.dx - 4.6, _badge.dy + 0.2)
          ..lineTo(_badge.dx - 1.4, _badge.dy + 3.4)
          ..lineTo(_badge.dx + 4.8, _badge.dy - 3.4),
        Paint()
          ..color = FactifyBrand.emerald
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.6
          ..strokeCap = StrokeCap.round
          ..strokeJoin = StrokeJoin.round,
      );
  }

  @override
  bool shouldRepaint(_SealPainter oldDelegate) => false;
}
