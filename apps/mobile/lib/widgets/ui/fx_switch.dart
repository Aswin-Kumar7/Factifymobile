/// A switch (v5): 44x26, knob 20; the track is emerald when on, the line colour when off.
library;

import 'package:flutter/material.dart';

import '../../theme/tokens.dart';

class FxSwitch extends StatelessWidget {
  const FxSwitch({required this.value, required this.onChanged, this.label, super.key});

  final bool value;
  final ValueChanged<bool>? onChanged;

  /// Read out by assistive technology.
  final String? label;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Semantics(
      toggled: value,
      label: label,
      enabled: onChanged != null,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onChanged == null ? null : () => onChanged!(!value),
        child: SizedBox(
          width: 48,
          height: 44,
          child: Center(
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 180),
              width: 44,
              height: 26,
              decoration: BoxDecoration(
                color: value ? k.acc : k.line,
                borderRadius: BorderRadius.circular(13),
              ),
              child: AnimatedAlign(
                duration: const Duration(milliseconds: 180),
                curve: Curves.easeOut,
                alignment: value ? Alignment.centerRight : Alignment.centerLeft,
                child: Container(
                  width: 20,
                  height: 20,
                  margin: const EdgeInsets.symmetric(horizontal: 3),
                  decoration: const BoxDecoration(
                    color: Colors.white,
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(color: Color(0x33000000), blurRadius: 2, offset: Offset(0, 1)),
                    ],
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
