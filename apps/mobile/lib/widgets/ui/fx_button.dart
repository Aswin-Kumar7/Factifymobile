/// Buttons (v5): primary emerald, dark ink, muted secondary, outlined and ghost.
///
/// Primary is 56 tall with a radius of 16, label Geist 16/600. The verdict screen's
/// bottom bar uses the dark variant at 52 (radius 18), with a square secondary
/// "check again" beside it.
library;

import 'package:flutter/material.dart';

import '../../theme/tokens.dart';
import '../../theme/typography.dart';

enum FxButtonVariant { primary, dark, secondary, outline, ghost }

class FxButton extends StatelessWidget {
  const FxButton({
    required this.label,
    required this.onPressed,
    this.variant = FxButtonVariant.primary,
    this.icon,
    this.trailingIcon,
    this.height = 56,
    this.radius = 16,
    this.fontSize = 16,
    this.foreground,
    this.expand = true,
    this.busy = false,
    super.key,
  });

  final String label;

  /// Null disables the button: it stays in place at 40% opacity.
  final VoidCallback? onPressed;
  final FxButtonVariant variant;
  final IconData? icon;
  final IconData? trailingIcon;
  final double height;
  final double radius;
  final double fontSize;

  /// Overrides the label colour: "Sign out" is set in the False colour.
  final Color? foreground;
  final bool expand;

  /// Shows a spinner in place of the label, and ignores taps.
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final (bg, fg, border) = switch (variant) {
      FxButtonVariant.primary => (k.acc, k.onAcc, null),
      FxButtonVariant.dark => (k.ink, k.bg, null),
      FxButtonVariant.secondary => (k.sf2, k.ink, null),
      FxButtonVariant.outline => (k.sf, k.ink, k.line),
      FxButtonVariant.ghost => (Colors.transparent, k.ink2, null),
    };
    final colour = foreground ?? fg;
    final enabled = onPressed != null && !busy;
    final content = busy
        ? SizedBox(
            width: 22,
            height: 22,
            child: CircularProgressIndicator(strokeWidth: 2.4, color: colour),
          )
        : Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (icon != null) ...[
                Icon(icon, size: fontSize + 3, color: colour),
                const SizedBox(width: 8),
              ],
              Flexible(
                child: Text(
                  label,
                  textAlign: TextAlign.center,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: FactifyText.sans(fontSize, weight: FontWeight.w600, color: colour),
                ),
              ),
              if (trailingIcon != null) ...[
                const SizedBox(width: 8),
                Icon(trailingIcon, size: fontSize + 2, color: colour),
              ],
            ],
          );
    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(radius),
      side: border == null ? BorderSide.none : BorderSide(color: border),
    );
    return Semantics(
      button: true,
      enabled: enabled,
      label: label,
      excludeSemantics: true,
      child: AnimatedOpacity(
        opacity: onPressed == null ? 0.4 : 1,
        duration: const Duration(milliseconds: 200),
        child: Material(
          color: bg,
          shape: shape,
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: enabled ? onPressed : null,
            child: ConstrainedBox(
              constraints: BoxConstraints(
                minHeight: height,
                minWidth: expand ? double.infinity : 0,
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 8),
                child: Center(widthFactor: expand ? null : 1, heightFactor: 1, child: content),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// A round icon button: back, share, close. 38 across on a surface fill.
class FxCircleButton extends StatelessWidget {
  const FxCircleButton({
    required this.icon,
    required this.onPressed,
    required this.tooltip,
    this.size = 38,
    this.iconSize = 20,
    this.background,
    this.bordered = false,
    this.shadow = false,
    super.key,
  });

  final IconData icon;
  final VoidCallback? onPressed;
  final String tooltip;
  final double size;
  final double iconSize;
  final Color? background;
  final bool bordered;

  /// The card shadow on the circle itself.
  final bool shadow;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    // At least 44 to touch, whatever it draws (v5 accessibility: 44x44 targets).
    return Tooltip(
      message: tooltip,
      child: Semantics(
        button: true,
        label: tooltip,
        excludeSemantics: true,
        child: SizedBox(
          width: size < 44 ? 44 : size,
          height: size < 44 ? 44 : size,
          child: Center(
            child: DecoratedBox(
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                boxShadow: shadow ? k.shadow : null,
              ),
              child: Material(
                color: background ?? k.sf,
                shape: CircleBorder(side: bordered ? BorderSide(color: k.line) : BorderSide.none),
                clipBehavior: Clip.antiAlias,
                child: InkWell(
                  onTap: onPressed,
                  child: SizedBox(
                    width: size,
                    height: size,
                    child: Icon(icon, size: iconSize, color: k.ink),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
