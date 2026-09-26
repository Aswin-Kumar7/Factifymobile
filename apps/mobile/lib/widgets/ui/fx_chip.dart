/// Chips and pills (v5).
///
/// [FxChip]: a rounded chip, 30-32 tall, radius half its height, label 12-12.5/600 -
/// the "Paste copied text" offer, the Deep toggle, History's filters.
/// [FxVerdictPill]: the small coloured verdict label, 11/700 on its tint, radius 8,
/// always a word beside any icon so a verdict never rests on colour alone.
library;

import 'package:flutter/material.dart';

import '../../models/verdict.dart';
import '../../theme/tokens.dart';
import '../../theme/typography.dart';
import '../action_style.dart';

class FxChip extends StatelessWidget {
  const FxChip({
    required this.label,
    this.onTap,
    this.icon,
    this.dot,
    this.count,
    this.background,
    this.foreground,
    this.border,
    this.height = 32,
    this.fontSize = 12.5,
    this.iconSize = 15,
    this.selected,
    this.shadow = false,
    super.key,
  });

  final String label;
  final VoidCallback? onTap;
  final IconData? icon;

  /// A small coloured dot before the label (History's verdict filters).
  final Color? dot;

  /// A count after the label, in a lighter tone.
  final int? count;
  final Color? background;
  final Color? foreground;
  final Color? border;
  final double height;
  final double fontSize;
  final double iconSize;

  /// For assistive technology: whether this chip is the chosen one.
  final bool? selected;

  /// The card shadow, on the chip itself (History's filters).
  final bool shadow;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final fg = foreground ?? k.acc;
    final chip = Container(
      height: height,
      padding: EdgeInsets.symmetric(horizontal: height * 0.36),
      decoration: BoxDecoration(
        color: background ?? k.accS,
        borderRadius: BorderRadius.circular(height / 2),
        border: border == null ? null : Border.all(color: border!),
        boxShadow: shadow ? k.shadow : null,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (dot != null) ...[
            Container(
              width: 7,
              height: 7,
              decoration: BoxDecoration(color: dot, shape: BoxShape.circle),
            ),
            const SizedBox(width: 7),
          ],
          if (icon != null) ...[Icon(icon, size: iconSize, color: fg), const SizedBox(width: 6)],
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: FactifyText.sans(fontSize, weight: FontWeight.w600, color: fg),
            ),
          ),
          if (count != null) ...[
            const SizedBox(width: 6),
            Text(
              '$count',
              style: FactifyText.sans(
                fontSize,
                weight: FontWeight.w500,
                color: fg.withValues(alpha: 0.55),
              ),
            ),
          ],
        ],
      ),
    );
    if (onTap == null) return chip;
    return Semantics(
      button: true,
      selected: selected,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        // The chip draws at 30-32; the touch area reaches 44.
        child: Padding(
          padding: EdgeInsets.symmetric(vertical: height < 44 ? (44 - height) / 2 : 0),
          child: chip,
        ),
      ),
    );
  }
}

class FxVerdictPill extends StatelessWidget {
  const FxVerdictPill({
    required this.verdict,
    required this.label,
    this.icon,
    this.fontSize = 11,
    super.key,
  });

  final FactVerdict verdict;
  final String label;
  final IconData? icon;
  final double fontSize;

  @override
  Widget build(BuildContext context) {
    final (strong, soft) = ActionStyle.colours(verdict, FactifyTokens.of(context));
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: soft, borderRadius: BorderRadius.circular(8)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: fontSize + 2, color: strong),
            const SizedBox(width: 4),
          ],
          Text(
            label,
            maxLines: 1,
            style: FactifyText.sans(fontSize, weight: FontWeight.w700, color: strong),
          ),
        ],
      ),
    );
  }
}
