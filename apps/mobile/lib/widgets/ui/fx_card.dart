/// A card (v5): the surface colour, radius 20-24, the card shadow or a 1px line.
library;

import 'package:flutter/material.dart';

import '../../theme/tokens.dart';

class FxCard extends StatelessWidget {
  const FxCard({
    required this.child,
    this.padding = const EdgeInsets.all(14),
    this.radius = 20,
    this.bordered = false,
    this.shadow = true,
    this.color,
    this.onTap,
    this.clip = false,
    super.key,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final double radius;

  /// A 1px line border instead of, or as well as, the shadow.
  final bool bordered;
  final bool shadow;
  final Color? color;
  final VoidCallback? onTap;

  /// Clip the children to the rounded corners (lists with dividers).
  final bool clip;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final shape = BorderRadius.circular(radius);
    Widget body = Padding(padding: padding, child: child);
    if (onTap != null) {
      body = Material(
        type: MaterialType.transparency,
        child: InkWell(onTap: onTap, borderRadius: shape, child: body),
      );
    }
    return Container(
      clipBehavior: clip || onTap != null ? Clip.antiAlias : Clip.none,
      decoration: BoxDecoration(
        color: color ?? k.sf,
        borderRadius: shape,
        border: bordered ? Border.all(color: k.line) : null,
        boxShadow: shadow && !bordered ? k.shadow : null,
      ),
      child: body,
    );
  }
}

/// Rows in one card, divided by hairlines: the claims list, Recent, Settings.
class FxListCard extends StatelessWidget {
  const FxListCard({required this.children, this.bordered = false, this.radius = 20, super.key});

  final List<Widget> children;
  final bool bordered;
  final double radius;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return FxCard(
      padding: EdgeInsets.zero,
      bordered: bordered,
      radius: radius,
      clip: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final (index, child) in children.indexed) ...[
            if (index > 0) Divider(height: 1, thickness: 1, color: k.line),
            child,
          ],
        ],
      ),
    );
  }
}
