/// How sure a verdict is, as a ring (v5): 74 across, an arc in the verdict colour.
///
/// Shown only with a decided verdict. The number is arithmetic on the cited sources
/// - how many, how credible, whether any disagree - and runs from 50 to 97: never
/// certain, and never less than even, because below that it is not a verdict. The
/// arc is drawn clockwise from the top over the line colour; the centre is the
/// verdict's tint laid over the page, as in the design.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../l10n/app_localizations.dart';
import '../../theme/tokens.dart';
import '../../theme/typography.dart';

class FxConfidenceRing extends StatelessWidget {
  const FxConfidenceRing({
    required this.value,
    required this.colour,
    required this.tint,
    this.size = 74,
    super.key,
  });

  final int value;
  final Color colour;
  final Color tint;
  final double size;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final inner = size * 62 / 74;
    return Semantics(
      label: l10n.confidence(value),
      excludeSemantics: true,
      child: SizedBox(
        width: size,
        height: size,
        child: CustomPaint(
          painter: _RingPainter(fraction: value / 100, colour: colour, track: k.line),
          child: Center(
            child: Container(
              width: inner,
              height: inner,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Color.alphaBlend(tint, k.bg),
              ),
              alignment: Alignment.center,
              child: Text(
                '$value%',
                style: FactifyText.sans(
                  size * 19 / 74,
                  weight: FontWeight.w700,
                  color: k.ink,
                ).copyWith(letterSpacing: -0.5),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _RingPainter extends CustomPainter {
  _RingPainter({required this.fraction, required this.colour, required this.track});

  final double fraction;
  final Color colour;
  final Color track;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    canvas.drawOval(rect, Paint()..color = track);
    canvas.drawArc(
      rect,
      -math.pi / 2,
      2 * math.pi * fraction.clamp(0, 1),
      true,
      Paint()..color = colour,
    );
  }

  @override
  bool shouldRepaint(_RingPainter old) =>
      old.fraction != fraction || old.colour != colour || old.track != track;
}
