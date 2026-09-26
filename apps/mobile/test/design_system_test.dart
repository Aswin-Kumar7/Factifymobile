/// The v5 design system: tokens, themes and the shared widgets.
///
/// The token values are the build spec's (Factify App v5), and one rule is held for
/// both sets: Unconfirmed is grey, never red.
library;

import 'package:factify_mobile/l10n/app_localizations.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:factify_mobile/theme/theme.dart';
import 'package:factify_mobile/theme/theme_mode_preference.dart';
import 'package:factify_mobile/widgets/action_style.dart';
import 'package:factify_mobile/widgets/ui/ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Widget _host(Widget child, {Brightness brightness = Brightness.light}) => MaterialApp(
  theme: buildFactifyTheme(brightness),
  supportedLocales: AppLocalizations.supportedLocales,
  localizationsDelegates: AppLocalizations.localizationsDelegates,
  home: Scaffold(body: Center(child: child)),
);

void main() {
  group('tokens', () {
    test('match the build spec, light and dark', () {
      expect(FactifyTokens.light.bg, const Color(0xFFF4F3EF));
      expect(FactifyTokens.light.acc, const Color(0xFF0E6B4F));
      expect(FactifyTokens.light.fC, const Color(0xFFC23A2E));
      expect(FactifyTokens.dark.bg, const Color(0xFF0B0E0D));
      expect(FactifyTokens.dark.acc, const Color(0xFF52C99D));
      expect(FactifyTokens.dark.onAcc, const Color(0xFF04130D));
    });

    for (final (name, k) in [('light', FactifyTokens.light), ('dark', FactifyTokens.dark)]) {
      test('Unconfirmed is grey in $name, never red', () {
        final c = k.uC;
        final channels = [c.r, c.g, c.b];
        final spread =
            channels.reduce((a, b) => a > b ? a : b) - channels.reduce((a, b) => a < b ? a : b);
        expect(spread, lessThan(0.08), reason: 'uC must be a neutral grey');
        final (strong, _) = ActionStyle.colours(FactVerdict.unconfirmed, k);
        expect(strong, isNot(k.fC));
      });
    }

    test('both themes carry the tokens and the type scale', () {
      for (final b in Brightness.values) {
        final theme = buildFactifyTheme(b);
        expect(theme.extension<FactifyTokens>()?.brightness, b);
        expect(theme.extension<FactifyText>(), isNotNull);
        expect(theme.scaffoldBackgroundColor, theme.extension<FactifyTokens>()!.bg);
      }
    });
  });

  test('the theme choice is remembered for the session', () async {
    final pref = ThemeModePreference.inMemory();
    expect(pref.value, ThemeMode.system);
    await pref.choose(ThemeMode.dark);
    expect(pref.value, ThemeMode.dark);
  });

  testWidgets('a locked segment says why instead of switching', (tester) async {
    String? chosen;
    String? refused;
    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 340,
          child: FxSegmented<String>(
            segments: const [FxSegment('text', 'Text'), FxSegment('image', 'Image')],
            selected: 'text',
            locked: const {'image'},
            onChanged: (v) => chosen = v,
            onLocked: (v) => refused = v,
          ),
        ),
      ),
    );

    await tester.tap(find.text('Image'));

    expect(chosen, isNull);
    expect(refused, 'image');
  });

  testWidgets('the switch turns on and off', (tester) async {
    var value = false;
    await tester.pumpWidget(
      _host(
        StatefulBuilder(
          builder: (context, set) =>
              FxSwitch(value: value, onChanged: (v) => set(() => value = v), label: 'Dark mode'),
        ),
      ),
    );

    await tester.tap(find.byType(FxSwitch));
    await tester.pumpAndSettle();

    expect(value, isTrue);
  });

  testWidgets('the confidence ring reads out its number', (tester) async {
    await tester.pumpWidget(
      _host(
        FxConfidenceRing(value: 91, colour: FactifyTokens.light.fC, tint: FactifyTokens.light.fS),
      ),
    );

    expect(find.text('91%'), findsOneWidget);
    expect(find.bySemanticsLabel('91% confidence'), findsOneWidget);
  });

  test('initials name a publisher in up to three letters', () {
    expect(FxSourceAvatar.initialsOf('PIB Fact Check'), 'PIB');
    expect(FxSourceAvatar.initialsOf('Ministry of WCD'), 'WCD');
    expect(FxSourceAvatar.initialsOf('The Hindu'), 'TH');
    expect(FxSourceAvatar.initialsOf('Alt News'), 'AN');
    expect(FxSourceAvatar.initialsOf('Reserve Bank of India'), 'RBI');
    expect(FxSourceAvatar.initialsOf('reuters.com'), 'R');
    expect(FxSourceAvatar.initialsOf('www.thehindu.com'), 'T');
  });
}
