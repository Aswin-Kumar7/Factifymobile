/// Segmented tabs (v5): a sf2 track, radius 16, padding 3; items 36 tall, radius 13.
///
/// The chosen item sits on the surface colour with the card shadow, in ink; the
/// others are ink3 on the track. An item can be locked - shown at 40% and ignored -
/// which is how Check keeps one kind of input at a time.
library;

import 'package:flutter/material.dart';

import '../../theme/tokens.dart';
import '../../theme/typography.dart';

class FxSegment<T> {
  const FxSegment(this.value, this.label, {this.icon});

  final T value;
  final String label;
  final IconData? icon;
}

class FxSegmented<T> extends StatelessWidget {
  const FxSegmented({
    required this.segments,
    required this.selected,
    required this.onChanged,
    this.locked = const {},
    this.onLocked,
    this.height = 36,
    this.fontSize = 13,
    super.key,
  });

  final List<FxSegment<T>> segments;
  final T selected;
  final ValueChanged<T>? onChanged;

  /// Items shown but not choosable right now.
  final Set<T> locked;

  /// Told when a locked item is tapped, to say why it cannot be chosen.
  final ValueChanged<T>? onLocked;
  final double height;
  final double fontSize;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(color: k.sf2, borderRadius: BorderRadius.circular(16)),
      child: Row(
        children: [
          for (final (index, segment) in segments.indexed) ...[
            if (index > 0) const SizedBox(width: 2),
            Expanded(child: _item(context, k, segment)),
          ],
        ],
      ),
    );
  }

  Widget _item(BuildContext context, FactifyTokens k, FxSegment<T> segment) {
    final chosen = segment.value == selected;
    final isLocked = locked.contains(segment.value) && !chosen;
    final fg = chosen ? k.ink : k.ink3;
    return Semantics(
      button: true,
      selected: chosen,
      enabled: !isLocked,
      label: segment.label,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          if (isLocked) {
            onLocked?.call(segment.value);
          } else if (!chosen) {
            onChanged?.call(segment.value);
          }
        },
        child: AnimatedOpacity(
          duration: const Duration(milliseconds: 150),
          opacity: isLocked ? 0.4 : 1,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 150),
            constraints: BoxConstraints(minHeight: height),
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
            decoration: BoxDecoration(
              color: chosen ? k.sf : Colors.transparent,
              borderRadius: BorderRadius.circular(13),
              boxShadow: chosen ? k.shadow : null,
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (segment.icon != null) ...[
                  Icon(segment.icon, size: 16, color: fg),
                  const SizedBox(width: 6),
                ],
                Flexible(
                  child: Text(
                    segment.label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: FactifyText.sans(fontSize, weight: FontWeight.w600, color: fg),
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
