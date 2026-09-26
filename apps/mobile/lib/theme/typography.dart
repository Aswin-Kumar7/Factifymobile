/// The v5 type scale (Factify App v5, build spec).
///
/// Newsreader (serif) carries what is read as content - titles, the verdict word,
/// quotes and the text being checked; Geist carries the interface; Geist Mono the
/// small uppercase overlines ("STEP 2 OF 3", "VERDICT") and case ids. Each Latin face
/// falls back to a Devanagari one - Tiro Devanagari Hindi under Newsreader, Noto Sans
/// Devanagari under Geist - so a Hindi screen keeps the same serif/sans contrast. All
/// of them are bundled in assets/fonts and none is fetched at runtime.
library;

import 'package:flutter/material.dart';

import 'tokens.dart';

abstract final class FxFonts {
  static const serif = 'Newsreader';
  static const sans = 'Geist';
  static const mono = 'GeistMono';
  static const serifFallback = ['TiroDevanagariHindi'];
  static const sansFallback = ['NotoSansDevanagari'];
}

TextStyle _serif(double size, FontWeight weight, {double? height, double spacing = 0}) => TextStyle(
  fontFamily: FxFonts.serif,
  fontFamilyFallback: FxFonts.serifFallback,
  fontSize: size,
  fontWeight: weight,
  height: height,
  letterSpacing: spacing,
);

TextStyle _sans(double size, FontWeight weight, {double? height, double spacing = 0}) => TextStyle(
  fontFamily: FxFonts.sans,
  fontFamilyFallback: FxFonts.sansFallback,
  fontSize: size,
  fontWeight: weight,
  height: height,
  letterSpacing: spacing,
);

@immutable
class FactifyText extends ThemeExtension<FactifyText> {
  const FactifyText({
    required this.display,
    required this.title,
    required this.section,
    required this.body,
    required this.label,
    required this.caption,
    required this.overline,
    required this.input,
    required this.quote,
  });

  /// Newsreader 34/36, 500, -1.0: "What would you like to check?"
  final TextStyle display;

  /// Newsreader 22-26, 500.
  final TextStyle title;

  /// Newsreader 20, 500: "Recent", "3 claims", "Sources".
  final TextStyle section;

  /// Geist 15/22, 400.
  final TextStyle body;

  /// Geist 13/18, 600.
  final TextStyle label;

  /// Geist 12/16.
  final TextStyle caption;

  /// Geist Mono 10.5, 500, +1.2, uppercase.
  final TextStyle overline;

  /// Newsreader 21/1.36: the text box on Check.
  final TextStyle input;

  /// Newsreader 17/1.55: a quoted passage and an article body.
  final TextStyle quote;

  /// The verdict word: Newsreader 600, -2; 68 for True and False, 44 for
  /// Misleading, 38 for Unconfirmed.
  static TextStyle verdict(double size, Color color) =>
      _serif(size, FontWeight.w600, height: 0.95, spacing: -2).copyWith(color: color);

  static TextStyle serif(double size, {FontWeight weight = FontWeight.w500, Color? color}) =>
      _serif(size, weight).copyWith(color: color);

  static TextStyle sans(double size, {FontWeight weight = FontWeight.w400, Color? color}) =>
      _sans(size, weight).copyWith(color: color);

  static TextStyle mono(
    double size, {
    FontWeight weight = FontWeight.w500,
    Color? color,
    double spacing = 1.2,
  }) => TextStyle(
    fontFamily: FxFonts.mono,
    fontSize: size,
    fontWeight: weight,
    letterSpacing: spacing,
    color: color,
  );

  factory FactifyText.fromTokens(FactifyTokens k) => FactifyText(
    display: _serif(34, FontWeight.w500, height: 1.08, spacing: -1).copyWith(color: k.ink),
    title: _serif(24, FontWeight.w500, height: 1.15, spacing: -0.3).copyWith(color: k.ink),
    section: _serif(20, FontWeight.w500, height: 1.2).copyWith(color: k.ink),
    body: _sans(15, FontWeight.w400, height: 22 / 15).copyWith(color: k.ink),
    label: _sans(13, FontWeight.w600, height: 18 / 13).copyWith(color: k.ink),
    caption: _sans(12, FontWeight.w400, height: 16 / 12).copyWith(color: k.ink3),
    overline: mono(10.5, color: k.ink3),
    input: _serif(21, FontWeight.w400, height: 1.36).copyWith(color: k.ink),
    quote: _serif(17, FontWeight.w400, height: 1.55).copyWith(color: k.ink),
  );

  static FactifyText of(BuildContext context) =>
      Theme.of(context).extension<FactifyText>() ?? FactifyText.fromTokens(FactifyTokens.of(context));

  @override
  FactifyText copyWith() => this;

  @override
  FactifyText lerp(covariant FactifyText? other, double t) {
    if (other == null) return this;
    TextStyle l(TextStyle a, TextStyle b) => TextStyle.lerp(a, b, t)!;
    return FactifyText(
      display: l(display, other.display),
      title: l(title, other.title),
      section: l(section, other.section),
      body: l(body, other.body),
      label: l(label, other.label),
      caption: l(caption, other.caption),
      overline: l(overline, other.overline),
      input: l(input, other.input),
      quote: l(quote, other.quote),
    );
  }
}

/// The same scale as a Material [TextTheme], so plain widgets pick it up too.
TextTheme factifyTextTheme(FactifyTokens k) {
  final t = FactifyText.fromTokens(k);
  return TextTheme(
    displayLarge: t.display.copyWith(fontSize: 44),
    displayMedium: t.display,
    displaySmall: t.title.copyWith(fontSize: 26),
    headlineLarge: t.title.copyWith(fontSize: 26),
    headlineMedium: t.title,
    headlineSmall: t.title.copyWith(fontSize: 22),
    titleLarge: t.section,
    titleMedium: _sans(16, FontWeight.w600, height: 1.3).copyWith(color: k.ink),
    titleSmall: t.label.copyWith(fontSize: 14),
    bodyLarge: t.body.copyWith(fontSize: 16),
    bodyMedium: t.body,
    bodySmall: _sans(13, FontWeight.w400, height: 1.45).copyWith(color: k.ink2),
    labelLarge: _sans(14, FontWeight.w600, height: 1.3).copyWith(color: k.ink),
    labelMedium: t.label.copyWith(fontSize: 12.5),
    labelSmall: t.caption.copyWith(fontSize: 11.5),
  );
}
