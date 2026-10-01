/// The v5 colour tokens: one set for light, one for dark (Factify App v5, build spec).
///
/// Every colour on a screen comes from here, read through the theme, so a screen
/// never decides a colour for itself and dark mode is the same layout with the
/// other set. The five verdict pairs are the strong colour (tC, fC, pC, mC, uC) and
/// its soft tint (tS, fS, pS, mS, uS). Partly true is yellow, set apart from the
/// amber of Misleading. Unconfirmed is grey in both sets and never red: it means the
/// sources did not settle the claim, not that something bad was found.
library;

import 'package:flutter/material.dart';

@immutable
class FactifyTokens extends ThemeExtension<FactifyTokens> {
  const FactifyTokens({
    required this.brightness,
    required this.bg,
    required this.sf,
    required this.sf2,
    required this.ink,
    required this.ink2,
    required this.ink3,
    required this.line,
    required this.acc,
    required this.accS,
    required this.onAcc,
    required this.hero,
    required this.heroInk,
    required this.hiBg,
    required this.hiInk,
    required this.hiEmpty,
    required this.hiLine,
    required this.hiRecap,
    required this.nav,
    required this.tC,
    required this.tS,
    required this.fC,
    required this.fS,
    required this.pC,
    required this.pS,
    required this.mC,
    required this.mS,
    required this.uC,
    required this.uS,
    required this.shadow,
  });

  final Brightness brightness;

  /// Page background.
  final Color bg;

  /// Cards and surfaces.
  final Color sf;

  /// Muted fill: tracks, icon tiles.
  final Color sf2;

  /// Primary, secondary and tertiary text.
  final Color ink;
  final Color ink2;
  final Color ink3;

  /// Hairlines and borders.
  final Color line;

  /// Brand emerald, for what acts; its tint; text on it.
  final Color acc;
  final Color accS;
  final Color onAcc;

  /// The dark feature card (credits) and its text.
  final Color hero;
  final Color heroInk;

  /// History's "This week" card: background, text, an empty day, its rule, the recap.
  final Color hiBg;
  final Color hiInk;
  final Color hiEmpty;
  final Color hiLine;
  final Color hiRecap;

  /// The bottom navigation bar, slightly translucent.
  final Color nav;

  /// True, False, Partly true, Misleading and Unconfirmed: strong colour, soft tint.
  final Color tC;
  final Color tS;
  final Color fC;
  final Color fS;
  final Color pC;
  final Color pS;
  final Color mC;
  final Color mS;
  final Color uC;
  final Color uS;

  /// The card shadow. In dark mode a 1px ring stands in for it.
  final List<BoxShadow> shadow;

  bool get isDark => brightness == Brightness.dark;

  static const light = FactifyTokens(
    brightness: Brightness.light,
    bg: Color(0xFFF4F3EF),
    sf: Color(0xFFFFFFFF),
    sf2: Color(0xFFEEEDE8),
    ink: Color(0xFF111513),
    ink2: Color(0xFF474D49),
    ink3: Color(0xFF7B817D),
    line: Color(0xFFE5E3DD),
    acc: Color(0xFF0E6B4F),
    accS: Color(0xFFDCEEE4),
    onAcc: Color(0xFFFFFFFF),
    hero: Color(0xFF0F2A20),
    heroInk: Color(0xFFEAF4EE),
    hiBg: Color(0xFFE3EFE7),
    hiInk: Color(0xFF0F2A20),
    hiEmpty: Color.fromRGBO(15, 42, 32, .09),
    hiLine: Color.fromRGBO(15, 42, 32, .10),
    hiRecap: Color.fromRGBO(255, 255, 255, .72),
    nav: Color.fromRGBO(255, 255, 255, .94),
    tC: Color(0xFF0F7A58),
    tS: Color(0xFFE0F1E7),
    fC: Color(0xFFC23A2E),
    fS: Color(0xFFFAE8E4),
    // 4.5:1 on its own tint, like the others.
    pC: Color(0xFF856A00),
    pS: Color(0xFFFAF0C4),
    mC: Color(0xFFAA650B),
    mS: Color(0xFFF8EDD9),
    uC: Color(0xFF5F6763),
    uS: Color(0xFFEAECE9),
    // 0 1px 2px rgba(30,30,20,.05), 0 6px 18px -8px rgba(30,30,20,.10)
    shadow: [
      BoxShadow(offset: Offset(0, 1), blurRadius: 2, color: Color.fromRGBO(30, 30, 20, .05)),
      BoxShadow(
        offset: Offset(0, 6),
        blurRadius: 18,
        spreadRadius: -8,
        color: Color.fromRGBO(30, 30, 20, .10),
      ),
    ],
  );

  static const dark = FactifyTokens(
    brightness: Brightness.dark,
    bg: Color(0xFF0B0E0D),
    sf: Color(0xFF151A18),
    sf2: Color(0xFF1E2421),
    ink: Color(0xFFEDEFEB),
    ink2: Color(0xFFB5BBB7),
    ink3: Color(0xFF848C88),
    line: Color(0xFF252B28),
    acc: Color(0xFF52C99D),
    accS: Color.fromRGBO(82, 201, 157, .14),
    onAcc: Color(0xFF04130D),
    hero: Color(0xFF12291F),
    heroInk: Color(0xFFE3F2EA),
    hiBg: Color(0xFF12291F),
    hiInk: Color(0xFFE3F2EA),
    hiEmpty: Color.fromRGBO(255, 255, 255, .14),
    hiLine: Color.fromRGBO(255, 255, 255, .12),
    hiRecap: Color.fromRGBO(255, 255, 255, .06),
    nav: Color.fromRGBO(21, 26, 24, .96),
    tC: Color(0xFF52C99D),
    tS: Color.fromRGBO(82, 201, 157, .14),
    fC: Color(0xFFF2735F),
    fS: Color.fromRGBO(242, 115, 95, .13),
    pC: Color(0xFFE3C84A),
    pS: Color.fromRGBO(227, 200, 74, .14),
    mC: Color(0xFFE9AB4C),
    mS: Color.fromRGBO(233, 171, 76, .14),
    uC: Color(0xFFA2AAA6),
    uS: Color.fromRGBO(162, 170, 166, .14),
    // 0 0 0 1px #202623: a ring rather than a shadow, which dark surfaces swallow.
    shadow: [BoxShadow(spreadRadius: 1, color: Color(0xFF202623))],
  );

  static FactifyTokens of(BuildContext context) =>
      Theme.of(context).extension<FactifyTokens>() ?? light;

  @override
  FactifyTokens copyWith({Brightness? brightness}) =>
      brightness == null ? this : (brightness == Brightness.dark ? dark : light);

  @override
  FactifyTokens lerp(covariant FactifyTokens? other, double t) {
    if (other == null) return this;
    Color c(Color a, Color b) => Color.lerp(a, b, t)!;
    return FactifyTokens(
      brightness: t < 0.5 ? brightness : other.brightness,
      bg: c(bg, other.bg),
      sf: c(sf, other.sf),
      sf2: c(sf2, other.sf2),
      ink: c(ink, other.ink),
      ink2: c(ink2, other.ink2),
      ink3: c(ink3, other.ink3),
      line: c(line, other.line),
      acc: c(acc, other.acc),
      accS: c(accS, other.accS),
      onAcc: c(onAcc, other.onAcc),
      hero: c(hero, other.hero),
      heroInk: c(heroInk, other.heroInk),
      hiBg: c(hiBg, other.hiBg),
      hiInk: c(hiInk, other.hiInk),
      hiEmpty: c(hiEmpty, other.hiEmpty),
      hiLine: c(hiLine, other.hiLine),
      hiRecap: c(hiRecap, other.hiRecap),
      nav: c(nav, other.nav),
      tC: c(tC, other.tC),
      tS: c(tS, other.tS),
      fC: c(fC, other.fC),
      fS: c(fS, other.fS),
      pC: c(pC, other.pC),
      pS: c(pS, other.pS),
      mC: c(mC, other.mC),
      mS: c(mS, other.mS),
      uC: c(uC, other.uC),
      uS: c(uS, other.uS),
      shadow: t < 0.5 ? shadow : other.shadow,
    );
  }
}
