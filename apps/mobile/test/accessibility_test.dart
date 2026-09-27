/// Accessibility and Hindi (v5, 2.12-2.13), screen by screen.
///
/// Held here, for every main screen: everything that can be tapped is at least 44 by
/// 44 and says what it is; and the screen lays out in Hindi, in dark mode, at 130%
/// text, without anything overflowing (an overflow fails the test by itself).
library;

import 'dart:async';

import 'package:clock/clock.dart';
import 'package:factify_mobile/api/check_events.dart';
import 'package:factify_mobile/app_services.dart';
import 'package:factify_mobile/models/submission.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:factify_mobile/quick/quick_verdict.dart';
import 'package:factify_mobile/screens/checking_screen.dart';
import 'package:factify_mobile/screens/error_screen.dart';
import 'package:factify_mobile/screens/history_screen.dart';
import 'package:factify_mobile/screens/main_shell.dart';
import 'package:factify_mobile/screens/profile_screen.dart';
import 'package:factify_mobile/screens/result_screen.dart';
import 'package:factify_mobile/screens/source_reader_screen.dart';
import 'package:factify_mobile/screens/welcome_screen.dart';
import 'package:factify_mobile/widgets/correction_sheet.dart';
import 'package:factify_mobile/widgets/why_sheet.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:share_plus/share_plus.dart';

import 'support/screens.dart';

class _Host implements QuickHost {
  @override
  Future<SharedText?> share() async => null;
  @override
  Future<void> openFullApp(String text) async {}
  @override
  Future<void> openResult(String recordId) async {}
  @override
  Future<void> close() async {}
}

/// A screen, given the services it runs on.
typedef _Screen = Widget Function(AppServices services);

final Map<String, _Screen> _screens = {
  'Check': (s) => MainShell(services: s),
  'History': (s) => HistoryScreen(services: s),
  'Profile': (s) => ProfileScreen(services: s),
  for (final kind in FactVerdict.values)
    'Result, ${kind.name}': (s) => ResultScreen(
      services: s,
      verdict: sampleVerdict(kind),
      submission: Submission.text(sampleClaim),
    ),
  'Why sheet': (s) => Scaffold(
    body: SingleChildScrollView(child: WhySheet(verdict: sampleVerdict(FactVerdict.falseClaim))),
  ),
  'Source reader': (s) => SourceReaderScreen(
    services: s,
    caseId: 'case-falseClaim',
    evidence: sampleVerdict(FactVerdict.falseClaim).claims.first.evidence.first,
  ),
  'Correction': (s) => CorrectionSheet(
    verdict: sampleVerdict(FactVerdict.falseClaim),
    share: (_) async => ShareResultStatus.dismissed,
  ),
  'Welcome': (s) => WelcomeScreen(services: s),
  'Error': (s) => Scaffold(
    body: SafeArea(
      child: ErrorView(
        problem: CheckProblem.linkUnread,
        submission: Submission.link('https://newsdaily-updates.example/viral-scheme'),
        message: 'Some sites block automatic reading.',
        onRetry: null,
        onExit: (_) {},
        onClose: () {},
      ),
    ),
  ),
};

Future<void> _pump(WidgetTester tester, AppServices services, Widget screen) async {
  galleryPhone(tester);
  final messenger = tester.binding.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
    if (call.method == 'Clipboard.hasStrings') return {'value': false};
    return null;
  });
  addTearDown(() => messenger.setMockMethodCallHandler(SystemChannels.platform, null));
  await tester.pumpWidget(galleryApp(services, screen));
  await tester.pumpAndSettle();
}

const _tapTarget = MinimumTapTargetGuideline(
  size: Size(44, 44),
  link: 'v5 build brief 2.13: hit targets are at least 44x44',
);

void main() {
  for (final MapEntry(key: name, value: screen) in _screens.entries) {
    testWidgets('$name: 44-point targets, each labelled', (tester) async {
      final handle = tester.ensureSemantics();
      await withClock(Clock.fixed(galleryNow), () async {
        final services = await galleryServices();
        await _pump(tester, services, screen(services));
        await expectLater(tester, meetsGuideline(_tapTarget));
        await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      });
      handle.dispose();
    });

    testWidgets('$name: Hindi, dark, 130% text', (tester) async {
      tester.platformDispatcher.textScaleFactorTestValue = 1.3;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await withClock(Clock.fixed(galleryNow), () async {
        final services = await galleryServices(theme: ThemeMode.dark, locale: const Locale('hi'));
        await _pump(tester, services, screen(services));
      });
    });
  }

  testWidgets('Checking, mid-check: targets, and Hindi at 130%', (tester) async {
    final handle = tester.ensureSemantics();
    for (final hindi in [false, true]) {
      if (hindi) tester.platformDispatcher.textScaleFactorTestValue = 1.3;
      await withClock(Clock.fixed(galleryNow), () async {
        final services = await galleryServices(
          locale: hindi ? const Locale('hi') : null,
          holdChecks: true,
        );
        final events = StreamController<CheckEvent>();
        galleryPhone(tester);
        await tester.pumpWidget(
          galleryApp(
            services,
            CheckingScreen(
              services: services,
              submission: Submission.text(sampleClaim),
              job: mid(services, events),
            ),
          ),
        );
        await tester.pump(const Duration(milliseconds: 300));
        sendMidCheck(events);
        await tester.pump(const Duration(milliseconds: 600));
        if (!hindi) await expectLater(tester, meetsGuideline(_tapTarget));
        await tester.pumpWidget(const SizedBox());
        // The held check's request times out, and the stream is let go: awaiting
        // close() on a stream nobody listens to any more would never return.
        await tester.pump(const Duration(minutes: 3));
        unawaited(events.close());
      });
    }
    tester.platformDispatcher.clearTextScaleFactorTestValue();
    handle.dispose();
  });

  testWidgets('Quick verdict: targets, and Hindi at 130%', (tester) async {
    final handle = tester.ensureSemantics();
    for (final hindi in [false, true]) {
      if (hindi) tester.platformDispatcher.textScaleFactorTestValue = 1.3;
      await withClock(Clock.fixed(galleryNow), () async {
        final services = await galleryServices(locale: hindi ? const Locale('hi') : null);
        galleryPhone(tester);
        await tester.pumpWidget(
          QuickVerdictApp(
            services: services,
            shared: const SharedText(value: sampleClaim, link: false),
            host: _Host(),
            ready: true,
          ),
        );
        // Answered: the sheet as it looks with a False verdict and its buttons.
        await tester.pumpAndSettle();
        expect(find.text(hindi ? 'सुधार कॉपी करें' : 'Copy correction'), findsOneWidget);
      });
      if (!hindi) await expectLater(tester, meetsGuideline(_tapTarget));
    }
    tester.platformDispatcher.clearTextScaleFactorTestValue();
    handle.dispose();
  });
}
