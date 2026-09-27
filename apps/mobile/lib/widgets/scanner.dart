/// The Checking screen's scanner (v5, 176px): this check's sources, and what they
/// said.
///
/// Searching goes out, evidence comes in. A soft pulse leaves the magnifier at the
/// centre, and a comet runs round the ring: the search. The pages the server reports
/// opening take their place on the ring, in the order it opened them, and each shows
/// what it said - in the result's own colours: green where it supports the claim,
/// red where it refutes it, amber where it adds context. While a page is read it has
/// a turning arc; once read it is outlined in its colour, because the source check
/// has not yet said whether it is really about this claim; when the check keeps it,
/// it fills in and a dot carries it into the centre, which counts what the answer
/// will cite. A page set aside fades. So two checks never look alike: each ring is
/// that check's own sources and findings.
///
/// Published fact-checks compared in bulk are not on the ring (the screen counts
/// them); one that speaks to the claim joins it like any page.
///
/// Nothing on the ring is invented: before the server names a source, the ring is
/// empty. (An earlier version drew ten empty placeholder dots; in dark mode they read
/// as holes, and the design's filled wedge smeared across them.)
///
/// Plain paints only. A sweep-gradient shader repainted every frame brought the
/// Android emulator's software renderer down (2026-09-27).
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../checks/check_job.dart';
import '../models/verdict.dart';
import '../theme/icons.dart';
import '../theme/tokens.dart';
import 'action_style.dart';

class Scanner extends StatefulWidget {
  const Scanner({required this.sources, this.collected, this.checked = false, super.key});

  /// In the order they were opened; the first ten are shown.
  final List<WatchedSource> sources;

  /// The evidence count as the server keeps it; counted from [sources] if absent.
  final int? collected;

  /// The source check has run: the count is what the answer cites.
  final bool checked;

  static const double size = 176;
  static const int slots = 10;

  @override
  State<Scanner> createState() => _ScannerState();
}

class _ScannerState extends State<Scanner> with SingleTickerProviderStateMixin {
  // One clock for the search: 12 s holds whole pulses (2.4 s) and turns (3 s).
  late final AnimationController _clock = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 12),
  );

  bool _still = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Reduced motion: no pulse, no comet, no flight; the sources still change.
    _still = MediaQuery.disableAnimationsOf(context);
    if (_still) {
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

  static Offset _at(int index) {
    const centre = Scanner.size / 2;
    const orbit = centre - 16;
    final angle = index / Scanner.slots * 2 * math.pi - math.pi / 2;
    return Offset(centre + orbit * math.cos(angle), centre + orbit * math.sin(angle));
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    const size = Scanner.size;
    const centre = size / 2;
    const core = 56.0;
    final shown = widget.sources.take(Scanner.slots).toList();
    final collected =
        widget.collected ?? shown.where((s) => s.state == SourceState.evidence).length;
    Color colour(WatchedSource s) => stanceColour(s.stance, k);

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
                  painter: _Search(clock: _clock, tokens: k),
                ),
              ),
            ),
            // A dot flies in, in its colour, from every source the check keeps.
            for (final (i, source) in shown.indexed)
              if (source.state == SourceState.evidence && source.kept && !_still)
                _Arrival(
                  key: ValueKey('arrival-${source.domain}'),
                  from: _at(i),
                  to: const Offset(centre, centre),
                  colour: colour(source),
                ),
            Positioned(
              left: centre - core / 2,
              top: centre - core / 2,
              child: _Core(collected: collected, checked: widget.checked, size: core),
            ),
            for (final (i, source) in shown.indexed)
              _Slot(
                key: ValueKey('slot-${source.domain}'),
                source: source,
                at: _at(i),
                clock: _clock,
                still: _still,
              ),
          ],
        ),
      ),
    );
  }
}

/// The magnifier, and once evidence is in, how much has been collected: outlined
/// while the sources are still to be checked, filled once they have been.
class _Core extends StatelessWidget {
  const _Core({required this.collected, required this.checked, required this.size});

  final int collected;
  final bool checked;
  final double size;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return SizedBox.square(
      dimension: size,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Container(
            width: size,
            height: size,
            decoration: BoxDecoration(
              color: k.acc,
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: k.acc.withValues(alpha: 0.4),
                  offset: const Offset(0, 6),
                  blurRadius: 18,
                  spreadRadius: -6,
                ),
              ],
            ),
            child: Icon(FxIcons.search, size: 24, color: k.onAcc),
          ),
          if (collected > 0)
            Positioned(
              right: -4,
              top: -4,
              child: TweenAnimationBuilder<double>(
                // Grows in, and again with each new piece of evidence.
                key: ValueKey(collected),
                tween: Tween(begin: 0.6, end: 1),
                duration: const Duration(milliseconds: 360),
                curve: Curves.easeOutBack,
                builder: (context, scale, child) => Transform.scale(scale: scale, child: child),
                child: Container(
                  constraints: const BoxConstraints(minWidth: 22),
                  height: 22,
                  padding: const EdgeInsets.symmetric(horizontal: 6),
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: checked ? k.acc : k.bg,
                    borderRadius: BorderRadius.circular(11),
                    border: Border.all(color: k.acc, width: 1.5),
                  ),
                  child: Text(
                    '$collected',
                    style: TextStyle(
                      fontFamily: 'Geist',
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      height: 1,
                      color: checked ? k.onAcc : k.acc,
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// One source on the ring.
class _Slot extends StatelessWidget {
  const _Slot({
    required this.source,
    required this.at,
    required this.clock,
    required this.still,
    super.key,
  });

  final WatchedSource source;
  final Offset at;
  final Animation<double> clock;
  final bool still;

  static const double dot = 26;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final state = source.state;
    final found = state == SourceState.evidence;
    final reading = state == SourceState.reading;
    final idle = state == SourceState.notRelevant;
    // Kept by the source check: filled. Read and speaking to the claim but not yet
    // checked: outlined, in the colour of what it said.
    final filled = found && source.kept;
    final tone = found ? stanceColour(source.stance, k) : k.acc;

    final chip = AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      width: dot,
      height: dot,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: filled ? tone : k.sf,
        shape: BoxShape.circle,
        border: filled
            ? null
            : Border.all(color: found ? tone : (reading ? k.acc : k.line), width: found ? 2 : 1),
      ),
      child: Text(
        source.initials,
        maxLines: 1,
        overflow: TextOverflow.clip,
        style: TextStyle(
          fontFamily: 'Geist',
          fontSize: 8,
          fontWeight: FontWeight.w700,
          height: 1,
          color: filled
              ? (k.isDark ? k.bg : Colors.white)
              : found
              ? tone
              : (idle ? k.ink3 : k.ink2),
        ),
      ),
    );

    return Positioned(
      left: at.dx - dot / 2,
      top: at.dy - dot / 2,
      child: TweenAnimationBuilder<double>(
        // Arrives on the ring when the server names it.
        tween: Tween(begin: still ? 1 : 0, end: 1),
        duration: const Duration(milliseconds: 320),
        curve: Curves.easeOutBack,
        builder: (context, scale, child) => Transform.scale(scale: scale, child: child),
        child: AnimatedOpacity(
          opacity: idle ? 0.45 : 1,
          duration: const Duration(milliseconds: 300),
          child: SizedBox.square(
            dimension: dot,
            child: Stack(
              clipBehavior: Clip.none,
              alignment: Alignment.center,
              children: [
                chip,
                // Being read: a short arc turning round it.
                if (reading && !still)
                  Positioned(
                    left: -3,
                    top: -3,
                    right: -3,
                    bottom: -3,
                    child: CustomPaint(
                      painter: _Reading(clock: clock, colour: k.acc),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Reading extends CustomPainter {
  _Reading({required this.clock, required this.colour}) : super(repaint: clock);

  final Animation<double> clock;
  final Color colour;

  @override
  void paint(Canvas canvas, Size size) {
    // A turn every 0.8 s: 15 turns in the 12 s clock.
    final turn = (clock.value * 15) % 1;
    canvas.drawArc(
      Offset.zero & size,
      turn * 2 * math.pi - math.pi / 2,
      math.pi * 0.6,
      false,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2
        ..strokeCap = StrokeCap.round
        ..color = colour,
    );
  }

  @override
  bool shouldRepaint(_Reading old) => old.colour != colour;
}

/// A dot carried from a source into the centre: evidence collected.
class _Arrival extends StatefulWidget {
  const _Arrival({required this.from, required this.to, required this.colour, super.key});

  final Offset from;
  final Offset to;
  final Color colour;

  @override
  State<_Arrival> createState() => _ArrivalState();
}

class _ArrivalState extends State<_Arrival> with SingleTickerProviderStateMixin {
  late final AnimationController _flight = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 750),
  )..forward();

  @override
  void dispose() {
    _flight.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: _flight,
    builder: (context, _) {
      if (_flight.isCompleted) return const SizedBox.shrink();
      final t = Curves.easeInCubic.transform(_flight.value);
      final at = Offset.lerp(widget.from, widget.to, t)!;
      const size = 8.0;
      return Positioned(
        left: at.dx - size / 2,
        top: at.dy - size / 2,
        child: Opacity(
          opacity: 1 - t * 0.6,
          child: Container(
            width: size,
            height: size,
            decoration: BoxDecoration(
              color: widget.colour,
              shape: BoxShape.circle,
              boxShadow: [BoxShadow(color: widget.colour.withValues(alpha: 0.5), blurRadius: 6)],
            ),
          ),
        ),
      );
    },
  );
}

/// The ring, the pulse out from the centre, and the comet round the ring.
class _Search extends CustomPainter {
  _Search({required this.clock, required this.tokens}) : super(repaint: clock);

  final Animation<double> clock;
  final FactifyTokens tokens;

  @override
  void paint(Canvas canvas, Size size) {
    final centre = size.center(Offset.zero);
    final orbit = size.width / 2 - 16;
    final seconds = clock.value * 12;
    final acc = tokens.acc;

    // A faint fill inside the ring, so it reads as one instrument.
    canvas.drawCircle(centre, orbit, Paint()..color = acc.withValues(alpha: 0.05));

    // The ring the sources sit on.
    canvas.drawCircle(
      centre,
      orbit,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1
        ..color = tokens.line,
    );

    // The search going out: one soft pulse from the centre every 2.4 s.
    final phase = (seconds % 2.4) / 2.4;
    final eased = Curves.easeOut.transform(phase);
    final radius = 30 + (orbit - 30) * eased;
    final fade = 0.45 * (1 - eased);
    if (fade > 0) {
      canvas.drawCircle(
        centre,
        radius,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.5
          ..color = acc.withValues(alpha: fade),
      );
    }

    // The comet: a bright head running round the ring every 3 s, trailing a line of
    // dots that shrink and fade behind it. Dots rather than a stroked arc: pieces of a
    // translucent arc leave seams where they meet.
    final head = (seconds % 3) / 3 * 2 * math.pi - math.pi / 2;
    const trail = 12;
    const step = math.pi / 40;
    for (var i = trail; i >= 1; i--) {
      final angle = head - i * step;
      final left = 1 - i / (trail + 1);
      canvas.drawCircle(
        Offset(centre.dx + orbit * math.cos(angle), centre.dy + orbit * math.sin(angle)),
        0.8 + 2 * left,
        Paint()..color = acc.withValues(alpha: 0.85 * left * left),
      );
    }
    canvas.drawCircle(
      Offset(centre.dx + orbit * math.cos(head), centre.dy + orbit * math.sin(head)),
      3.5,
      Paint()..color = acc,
    );
  }

  @override
  bool shouldRepaint(_Search old) => old.tokens != tokens;
}

/// A source's colour for what it said: the result's own verdict colours, so green
/// always means "supports", red "refutes" and amber "adds context".
Color stanceColour(Stance? stance, FactifyTokens k) => switch (stance) {
  Stance.supports => ActionStyle.colours(FactVerdict.trueClaim, k).$1,
  Stance.contradicts => ActionStyle.colours(FactVerdict.falseClaim, k).$1,
  Stance.context => ActionStyle.colours(FactVerdict.misleading, k).$1,
  null => k.acc,
};
