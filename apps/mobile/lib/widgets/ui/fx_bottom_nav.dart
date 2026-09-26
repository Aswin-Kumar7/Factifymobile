/// The bottom navigation (v5): Check, History, Profile.
///
/// A 58x30 pill in the accent tint behind the current tab's icon, which switches
/// to its fill weight; labels 11/600, emerald when current, ink3 otherwise.
library;

import 'package:flutter/material.dart';

import '../../theme/tokens.dart';
import '../../theme/typography.dart';

class FxNavItem {
  const FxNavItem({required this.label, required this.icon, required this.selectedIcon});

  final String label;
  final IconData icon;
  final IconData selectedIcon;
}

class FxBottomNav extends StatelessWidget {
  const FxBottomNav({
    required this.items,
    required this.selected,
    required this.onSelected,
    super.key,
  });

  final List<FxNavItem> items;
  final int selected;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Container(
      decoration: BoxDecoration(
        color: k.nav,
        border: Border(top: BorderSide(color: k.line)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(22, 8, 22, 6),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              for (final (index, item) in items.indexed)
                _NavButton(
                  item: item,
                  current: index == selected,
                  onTap: () => onSelected(index),
                  tokens: k,
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _NavButton extends StatelessWidget {
  const _NavButton({
    required this.item,
    required this.current,
    required this.onTap,
    required this.tokens,
  });

  final FxNavItem item;
  final bool current;
  final VoidCallback onTap;
  final FactifyTokens tokens;

  @override
  Widget build(BuildContext context) {
    final k = tokens;
    final fg = current ? k.acc : k.ink3;
    return Semantics(
      button: true,
      selected: current,
      label: item.label,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: SizedBox(
          width: 88,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                width: 58,
                height: 30,
                decoration: BoxDecoration(
                  color: current ? k.accS : Colors.transparent,
                  borderRadius: BorderRadius.circular(15),
                ),
                child: Icon(current ? item.selectedIcon : item.icon, size: 22, color: fg),
              ),
              const SizedBox(height: 3),
              Text(
                item.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: FactifyText.sans(11, weight: FontWeight.w600, color: fg),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
