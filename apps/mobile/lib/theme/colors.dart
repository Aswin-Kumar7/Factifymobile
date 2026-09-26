/// The pre-v5 colour names, pointed at the v5 light palette.
///
/// Interim only: screens not yet rebuilt for v5 still name these, and now get the
/// v5 colours. New code reads [FactifyTokens] from the theme instead
/// (lib/theme/tokens.dart), which also carries the dark set; this file goes once
/// the last screen has moved over.
library;

import 'package:flutter/material.dart';

abstract final class FactifyColors {
  static const emerald = Color(0xFF0E6B4F);
  static const emeraldDark = Color(0xFF0E6B4F);
  static const emeraldDeep = Color(0xFF0B5A42);
  static const emeraldTint = Color(0xFFDCEEE4);
  static const emeraldSoft = Color(0xFFDCEEE4);
  static const ink = Color(0xFF111513);
  static const inkSoft = Color(0xFF474D49);
  static const inkMuted = Color(0xFF7B817D);
  static const line = Color(0xFFE5E3DD);
  static const ground = Color(0xFFF4F3EF);
}
