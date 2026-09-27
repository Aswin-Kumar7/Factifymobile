/// A touch area of at least 44 by 44 around something drawn smaller (v5, 2.13).
///
/// The design draws some controls small - a 36-tall language pill, a status dot and
/// its word, a 28-tall segment - and a thumb needs 44. This keeps the drawing as
/// designed and makes the space around it answer the tap too.
library;

import 'package:flutter/material.dart';

class FxTapArea extends StatelessWidget {
  const FxTapArea({
    required this.onTap,
    required this.child,
    this.label,
    this.selected,
    this.minSize = 44,
    super.key,
  });

  final VoidCallback? onTap;
  final Widget child;

  /// Read out instead of the child's own text, when given.
  final String? label;

  /// For a choice among several: whether this one is chosen.
  final bool? selected;
  final double minSize;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    enabled: onTap != null,
    selected: selected,
    label: label,
    excludeSemantics: label != null,
    child: GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: ConstrainedBox(
        constraints: BoxConstraints(minWidth: minSize, minHeight: minSize),
        child: Center(widthFactor: 1, heightFactor: 1, child: child),
      ),
    ),
  );
}
