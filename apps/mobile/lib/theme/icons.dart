/// Every icon in the app, by what it means (Phosphor, as in the v5 design).
///
/// The Phosphor fonts are bundled (assets/fonts, MIT) and used directly:
/// phosphor_flutter 2.1.0, the latest, extends IconData, which this Flutter made
/// final, so it no longer compiles. The code points are the package's own.
///
/// Regular weight by default; the fill weight marks an active or selected state -
/// the current tab, a bell that is on, a verified receipt. Screens name an icon by
/// meaning here rather than picking a glyph, so one change moves it everywhere.
library;

import 'package:flutter/widgets.dart';

import '../models/submission.dart';

abstract final class FxIcons {
  // What was submitted.
  /// Phosphor textAlignLeft.
  static const IconData text = IconData(0xe484, fontFamily: 'PhosphorRegular');

  /// Phosphor linkSimple.
  static const IconData link = IconData(0xe2e6, fontFamily: 'PhosphorRegular');

  /// Phosphor image.
  static const IconData image = IconData(0xe2ca, fontFamily: 'PhosphorRegular');

  /// Phosphor filePdf.
  static const IconData pdf = IconData(0xe702, fontFamily: 'PhosphorRegular');

  // Check.
  /// Phosphor clipboardText.
  static const IconData paste = IconData(0xe198, fontFamily: 'PhosphorRegular');

  /// Phosphor binoculars.
  static const IconData deep = IconData(0xea64, fontFamily: 'PhosphorRegular');

  /// Phosphor chatCircleDots.
  static const IconData chat = IconData(0xe16c, fontFamily: 'PhosphorRegular');

  /// Phosphor imageSquare.
  static const IconData addImage = IconData(0xe2cc, fontFamily: 'PhosphorRegular');

  /// Phosphor fileArrowUp.
  static const IconData addFile = IconData(0xe61e, fontFamily: 'PhosphorRegular');

  /// Phosphor images.
  static const IconData gallery = IconData(0xe836, fontFamily: 'PhosphorRegular');

  /// Phosphor camera.
  static const IconData camera = IconData(0xe10e, fontFamily: 'PhosphorRegular');

  /// Phosphor folderOpen.
  static const IconData folder = IconData(0xe256, fontFamily: 'PhosphorRegular');

  // Navigation.
  /// Phosphor sealCheck.
  static const IconData check = IconData(0xe606, fontFamily: 'PhosphorRegular');

  /// Phosphor sealCheck.
  static const IconData checkFill = IconData(0xe606, fontFamily: 'PhosphorFill');

  /// Phosphor clockCounterClockwise.
  static const IconData history = IconData(0xe1a0, fontFamily: 'PhosphorRegular');

  /// Phosphor clockCounterClockwise.
  static const IconData historyFill = IconData(0xe1a0, fontFamily: 'PhosphorFill');

  /// Phosphor user.
  static const IconData profile = IconData(0xe4c2, fontFamily: 'PhosphorRegular');

  /// Phosphor user.
  static const IconData profileFill = IconData(0xe4c2, fontFamily: 'PhosphorFill');

  // Verdicts: the fill weight inside a coloured disc or pill.
  /// Phosphor checkCircle.
  static const IconData trueV = IconData(0xe184, fontFamily: 'PhosphorFill');

  /// Phosphor xCircle.
  static const IconData falseV = IconData(0xe4f8, fontFamily: 'PhosphorFill');

  /// Phosphor warningCircle.
  static const IconData misleadingV = IconData(0xe4e2, fontFamily: 'PhosphorFill');

  /// Phosphor question.
  static const IconData unconfirmedV = IconData(0xe3e8, fontFamily: 'PhosphorFill');

  // Actions and chrome.
  /// Phosphor info.
  static const IconData info = IconData(0xe2ce, fontFamily: 'PhosphorRegular');

  /// Phosphor export.
  static const IconData share = IconData(0xeaf0, fontFamily: 'PhosphorRegular');

  /// Phosphor arrowBendUpLeft.
  static const IconData correction = IconData(0xe024, fontFamily: 'PhosphorRegular');

  /// Phosphor arrowBendUpRight.
  static const IconData forwarded = IconData(0xe026, fontFamily: 'PhosphorRegular');

  /// Phosphor flag.
  static const IconData report = IconData(0xe244, fontFamily: 'PhosphorRegular');

  /// Phosphor arrowClockwise.
  static const IconData recheck = IconData(0xe036, fontFamily: 'PhosphorRegular');

  /// Phosphor arrowCounterClockwise.
  static const IconData retry = IconData(0xe038, fontFamily: 'PhosphorRegular');

  /// Phosphor bell.
  static const IconData bell = IconData(0xe0ce, fontFamily: 'PhosphorRegular');

  /// Phosphor bellRinging.
  static const IconData bellRinging = IconData(0xe5e8, fontFamily: 'PhosphorFill');

  /// Phosphor wifiSlash.
  static const IconData offline = IconData(0xe4f2, fontFamily: 'PhosphorRegular');

  /// Phosphor linkBreak.
  static const IconData brokenLink = IconData(0xe2e4, fontFamily: 'PhosphorRegular');

  /// Phosphor sealCheck.
  static const IconData receipt = IconData(0xe606, fontFamily: 'PhosphorFill');

  /// Phosphor arrowLeft.
  static const IconData back = IconData(0xe058, fontFamily: 'PhosphorRegular');

  /// Phosphor arrowRight.
  static const IconData forward = IconData(0xe06c, fontFamily: 'PhosphorRegular');

  /// Phosphor arrowUpRight.
  static const IconData external = IconData(0xe092, fontFamily: 'PhosphorRegular');

  /// Phosphor arrowSquareOut.
  static const IconData openExternal = IconData(0xe5de, fontFamily: 'PhosphorRegular');

  /// Phosphor x.
  static const IconData close = IconData(0xe4f6, fontFamily: 'PhosphorRegular');

  /// Phosphor translate.
  static const IconData language = IconData(0xe4a2, fontFamily: 'PhosphorRegular');

  /// Phosphor eye.
  static const IconData eye = IconData(0xe220, fontFamily: 'PhosphorRegular');

  /// Phosphor eyeSlash.
  static const IconData eyeSlash = IconData(0xe224, fontFamily: 'PhosphorRegular');

  /// Phosphor shieldCheck.
  static const IconData privacy = IconData(0xe40c, fontFamily: 'PhosphorRegular');

  /// Phosphor magnifyingGlass.
  static const IconData search = IconData(0xe30c, fontFamily: 'PhosphorRegular');

  /// Phosphor trash.
  static const IconData trash = IconData(0xe4a6, fontFamily: 'PhosphorRegular');

  /// Phosphor caretRight.
  static const IconData chevron = IconData(0xe13a, fontFamily: 'PhosphorRegular');

  /// Phosphor pencilSimple.
  static const IconData edit = IconData(0xe3b4, fontFamily: 'PhosphorRegular');

  /// Phosphor moon.
  static const IconData moon = IconData(0xe330, fontFamily: 'PhosphorRegular');

  /// Phosphor sun.
  static const IconData sun = IconData(0xe472, fontFamily: 'PhosphorRegular');

  /// Phosphor cloudCheck.
  static const IconData service = IconData(0xe1b0, fontFamily: 'PhosphorRegular');

  /// Phosphor signOut.
  static const IconData signOut = IconData(0xe42a, fontFamily: 'PhosphorRegular');

  /// Phosphor minus.
  static const IconData minus = IconData(0xe32a, fontFamily: 'PhosphorRegular');

  /// Phosphor lockSimple.
  static const IconData lock = IconData(0xe308, fontFamily: 'PhosphorRegular');

  /// Phosphor copy.
  static const IconData copy = IconData(0xe1ca, fontFamily: 'PhosphorRegular');

  /// Phosphor shareNetwork.
  static const IconData shareNetwork = IconData(0xe408, fontFamily: 'PhosphorRegular');

  /// Phosphor scales.
  static const IconData scales = IconData(0xe750, fontFamily: 'PhosphorRegular');

  /// Phosphor lightbulb.
  static const IconData lightbulb = IconData(0xe2dc, fontFamily: 'PhosphorRegular');

  /// Phosphor quotes.
  static const IconData quotes = IconData(0xe660, fontFamily: 'PhosphorRegular');

  /// Phosphor fileText.
  static const IconData document = IconData(0xe23a, fontFamily: 'PhosphorRegular');

  /// Phosphor images.
  static const IconData recycled = IconData(0xe836, fontFamily: 'PhosphorRegular');

  /// Phosphor user.
  static const IconData person = IconData(0xe4c2, fontFamily: 'PhosphorRegular');

  /// Phosphor eyeSlash.
  static const IconData hidden = IconData(0xe224, fontFamily: 'PhosphorRegular');

  /// Phosphor arrowUp.
  static const IconData arrowUp = IconData(0xe08e, fontFamily: 'PhosphorRegular');

  static IconData forKind(SubmissionKind kind) => switch (kind) {
    SubmissionKind.text => text,
    SubmissionKind.link => link,
    SubmissionKind.image => image,
    SubmissionKind.document => pdf,
  };
}
