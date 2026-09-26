/// The Checking screen's scanner (v5, 176px): three pulsing rings, a rotating
/// sweep, the magnifier at the centre, and up to ten sources in orbit.
///
/// The motion says only that work is going on. The sources are the ones the server
/// reported opening, in the order it opened them: dim while waiting, raised while
/// being read, filled when they had something to say about the claim. A slot with
/// no source in it stays an empty dot - the orbit is never filled with names that
/// were not read.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../checks/check_job.dart';
import '../theme/icons.dart';
import '../theme/tokens.dart';

class Scanner extends StatefulWidget {
  const Scanner({required this.sources, super.key});

  /// In the order they were opened; the first ten are shown.
  final List<WatchedSource> sources;

  static const double size = 176;
  static const int slots = 10;

  @override
  State<Scanner> createState() => _ScannerState();
}

class _ScannerState extends State<Scanner> with SingleTickerProviderStateMixin {
  // One clock for every motion: 24 s holds a whole number of pulses (2.4 s) and of
  // sweeps (2 s), so the loop joins without a jump.
  late final AnimationController _clock = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 24),
  );

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Reduced motion: the rings and the sweep hold still; the sources still change.
    if (MediaQuery.disableAnimationsOf(context)) {
      _clock.stop();
    } else if (!_clock.isAnimating) {
      _clock.repeat();
    }
  }

  @override
  void dispose() {
    _clock.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    const size = Scanner.size;
    const centre = size / 2;
    const orbit = centre - 14;
    const core = 60.0;
    final shown = widget.sources.take(Scanner.slots).toList();

    return Semantics(
      container: true,
      excludeSemantics: true,
      child: SizedBox.square(
        dimension: size,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            Positioned.fill(
              child: RepaintBoundary(
                child: CustomPaint(
                  painter: _Sweep(clock: _clock, tokens: k),
                ),
              ),
            ),
            Positioned(
              left: centre - core / 2,
              top: centre - core / 2,
              child: Container(
                width: core,
                height: core,
                decoration: BoxDecoration(
                  color: k.acc,
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: k.acc.withValues(alpha: 0.45),
                      offset: const Offset(0, 8),
                      blurRadius: 20,
                      spreadRadius: -6,
                    ),
                  ],
                ),
                child: Icon(FxIcons.search, size: 26, color: k.onAcc),
              ),
            ),
            for (var i = 0; i < Scanner.slots; i++)
              _slot(k, i, i < shown.length ? shown[i] : null, centre: centre, orbit: orbit),
          ],
        ),
      ),
    );
  }

  Widget _slot(
    FactifyTokens k,
    int index,
    WatchedSource? source, {
    required double centre,
    required double orbit,
  }) {
    const dot = 24.0;
    final angle = index / Scanner.slots * 2 * math.pi - math.pi / 2;
    final x = centre + orbit * math.cos(angle) - dot / 2;
    final y = centre + orbit * math.sin(angle) - dot / 2;
    final state = source?.state;
    final found = state == SourceState.evidence;
    final reading = state == SourceState.reading;

    return Positioned(
      left: x,
      top: y,
      child: AnimatedScale(
        scale: reading ? 1.2 : 1,
        duration: const Duration(milliseconds: 300),
        child: AnimatedOpacity(
          opacity: source == null ? 0.35 : 1,
          duration: const Duration(milliseconds: 300),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            width: dot,
            height: dot,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: found ? k.acc : k.sf,
              shape: BoxShape.circle,
              boxShadow: reading
                  ? [BoxShadow(color: k.accS, spreadRadius: 3)]
                  : source == null
                  ? null
                  : k.shadow,
            ),
            child: source == null
                ? null
                : Text(
                    source.initials,
                    maxLines: 1,
                    overflow: TextOverflow.clip,
                    style: TextStyle(
                      fontFamily: 'Geist',
                      fontSize: 7.5,
                      fontWeight: FontWeight.w700,
                      height: 1,
                      color: found ? k.onAcc : k.ink2,
                    ),
                  ),
          ),
        ),
      ),
    );
  }
}

/// The rings, the dashed orbit and the sweep, driven by one clock.
class _Sweep extends CustomPainter {
  _Sweep({required this.clock, required this.tokens}) : super(repaint: clock);

  final Animation<double> clock;
  final FactifyTokens tokens;

  @override
  void paint(Canvas canvas, Size size) {
    final centre = size.center(Offset.zero);
    final radius = size.width / 2;
    final seconds = clock.value * 24;

    // Three rings, 0.8 s apart, each growing from 42% to 108% and fading out.
    for (var i = 0; i < 3; i++) {
      final phase = ((seconds - i * 0.8) % 2.4) / 2.4;
      final eased = Curves.easeOut.transform(phase);
      final scale = 0.42 + (1.08 - 0.42) * eased;
      final opacity = 0.7 * (1 - eased);
      if (opacity <= 0) continue;
      canvas.drawCircle(
        centre,
        radius * scale - 0.75,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.5
          ..color = tokens.acc.withValues(alpha: opacity),
      );
    }

    final inner = radius - 12;

    // The dashed orbit.
    final dash = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..color = tokens.line;
    const dashes = 60;
    for (var i = 0; i < dashes; i++) {
      final start = i / dashes * 2 * math.pi;
      canvas.drawArc(
        Rect.fromCircle(center: centre, radius: inner),
        start,
        math.pi / dashes,
        false,
        dash,
      );
    }

    // The sweep: a tail of tint trailing a leading edge, round every two seconds -
    // the design's conic gradient, as a fan of slices growing more opaque towards
    // the edge. A sweep-gradient shader repainted every frame brought the Android
    // emulator's software renderer down (2026-09-27); plain slices draw the same
    // thing more cheaply on any GPU.
    final lead = (seconds % 2) / 2 * 2 * math.pi - math.pi / 2;
    const slices = 18;
    const tail = 0.3 * 2 * math.pi;
    final disc = Rect.fromCircle(center: centre, radius: inner);
    for (var i = 0; i < slices; i++) {
      canvas.drawArc(
        disc,
        lead - tail + tail * i / slices,
        tail / slices,
        true,
        Paint()..color = tokens.accS.withValues(alpha: (i + 1) / slices),
      );
    }
  }

  @override
  bool shouldRepaint(_Sweep old) => old.tokens != tokens;
}
