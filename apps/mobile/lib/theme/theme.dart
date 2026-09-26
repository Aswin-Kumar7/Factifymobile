/// The app's two themes, built from the v5 tokens (lib/theme/tokens.dart).
///
/// Kept deliberately quiet: the one loud thing on a result screen is the verdict,
/// in its own colour, and chrome that competed with it would blunt exactly the
/// signal that has to read at a glance. Emerald marks what acts; the ink greys carry
/// the text; the page is a warm off-white (near-black in dark mode).
library;

import 'package:flutter/material.dart';

import 'tokens.dart';
import 'typography.dart';

ThemeData buildFactifyTheme(Brightness brightness) {
  final k = brightness == Brightness.dark ? FactifyTokens.dark : FactifyTokens.light;
  final text = factifyTextTheme(k);
  final scheme = ColorScheme(
    brightness: brightness,
    primary: k.acc,
    onPrimary: k.onAcc,
    primaryContainer: k.accS,
    onPrimaryContainer: k.acc,
    secondary: k.acc,
    onSecondary: k.onAcc,
    error: k.fC,
    onError: Colors.white,
    surface: k.sf,
    onSurface: k.ink,
    onSurfaceVariant: k.ink3,
    outline: k.line,
    outlineVariant: k.line,
    surfaceContainerLowest: k.sf,
    surfaceContainerLow: k.bg,
    surfaceContainer: k.bg,
    surfaceContainerHigh: k.sf2,
    surfaceContainerHighest: k.sf2,
    inverseSurface: k.ink,
    onInverseSurface: k.bg,
  );
  final rounded16 = RoundedRectangleBorder(borderRadius: BorderRadius.circular(16));

  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    colorScheme: scheme,
    scaffoldBackgroundColor: k.bg,
    canvasColor: k.bg,
    fontFamily: FxFonts.sans,
    fontFamilyFallback: FxFonts.sansFallback,
    textTheme: text,
    extensions: [k, FactifyText.fromTokens(k)],
    splashFactory: InkRipple.splashFactory,
    appBarTheme: AppBarTheme(
      backgroundColor: k.bg,
      foregroundColor: k.ink,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: true,
      titleTextStyle: FactifyText.sans(15, weight: FontWeight.w600, color: k.ink2),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      margin: EdgeInsets.zero,
      color: k.sf,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: BorderSide(color: k.line),
      ),
    ),
    dividerTheme: DividerThemeData(color: k.line, thickness: 1, space: 1),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: k.ink,
      contentTextStyle: FactifyText.sans(14, weight: FontWeight.w500, color: k.bg),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
    ),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: k.sf,
      surfaceTintColor: Colors.transparent,
      modalBarrierColor: Colors.black.withValues(alpha: 0.42),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: k.sf,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: k.sf,
      hintStyle: FactifyText.sans(15, color: k.ink3),
      labelStyle: FactifyText.sans(12.5, weight: FontWeight.w600, color: k.ink3),
      floatingLabelStyle: FactifyText.sans(12.5, weight: FontWeight.w600, color: k.ink3),
      contentPadding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(18),
        borderSide: BorderSide(color: k.line),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(18),
        borderSide: BorderSide(color: k.line),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(18),
        borderSide: BorderSide(color: k.acc, width: 1.4),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(18),
        borderSide: BorderSide(color: k.fC),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: k.acc,
        foregroundColor: k.onAcc,
        disabledBackgroundColor: k.acc.withValues(alpha: 0.4),
        disabledForegroundColor: k.onAcc,
        minimumSize: const Size.fromHeight(56),
        textStyle: FactifyText.sans(16, weight: FontWeight.w600),
        shape: rounded16,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: k.ink,
        backgroundColor: k.sf,
        minimumSize: const Size.fromHeight(50),
        textStyle: FactifyText.sans(15, weight: FontWeight.w600),
        shape: rounded16,
        side: BorderSide(color: k.line),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: k.acc,
        textStyle: FactifyText.sans(13, weight: FontWeight.w600),
      ),
    ),
    iconTheme: IconThemeData(color: k.ink, size: 20),
    progressIndicatorTheme: ProgressIndicatorThemeData(color: k.acc, linearTrackColor: k.sf2),
    chipTheme: ChipThemeData(
      side: BorderSide(color: k.line),
      backgroundColor: k.sf,
      labelStyle: FactifyText.sans(12.5, weight: FontWeight.w600, color: k.ink2),
      shape: const StadiumBorder(),
    ),
    textSelectionTheme: TextSelectionThemeData(
      cursorColor: k.acc,
      selectionColor: k.accS,
      selectionHandleColor: k.acc,
    ),
  );
}
