/// Golden images of the v5 screens, light and dark (v5 build brief, section 6).
///
/// Check, Checking mid-way, the four verdicts, a post checked from part of it and an
/// answer held back (contract 1.8), the Why sheet, History and Profile,
/// drawn at 360 wide with the app's own fonts and a fixed date (Saturday 26 September
/// 2026, as in the design gallery), so an image drawn today matches one drawn next
/// month. They are compared with a small tolerance: font rendering differs by a few
/// pixels between machines, and a real change to a screen moves far more than that.
///
/// After a deliberate change to a screen, redraw them:
///   flutter test --update-goldens test/golden_test.dart
library;

import 'dart:async';

import 'package:clock/clock.dart';
import 'package:factify_mobile/api/check_events.dart';
import 'package:factify_mobile/models/submission.dart';
import 'package:factify_mobile/models/verdict.dart';
import 'package:factify_mobile/screens/checking_screen.dart';
import 'package:factify_mobile/screens/history_screen.dart';
import 'package:factify_mobile/screens/main_shell.dart';
import 'package:factify_mobile/screens/profile_screen.dart';
import 'package:factify_mobile/screens/result_screen.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/contract.dart';
import 'support/screens.dart';

/// Passes an image that differs from its golden by at most [tolerance] of its pixels.
class _Tolerant extends LocalFileComparator {
  _Tolerant(super.testFile, this.tolerance);

  final double tolerance;

  @override
  Future<bool> compare(Uint8List imageBytes, Uri golden) async {
    final result = await GoldenFileComparator.compareLists(
      imageBytes,
      await getGoldenBytes(golden),
    );
    if (result.passed || result.diffPercent <= tolerance) {
      result.dispose();
      return true;
    }
    final error = await generateFailureOutput(result, golden, basedir);
    result.dispose();
    throw FlutterError(error);
  }
}

Future<void> _golden(
  WidgetTester tester,
  String name,
  ThemeMode theme,
  Widget Function(dynamic services) screen, {
  Future<void> Function()? then,
  bool settle = true,
}) async {
  await withClock(Clock.fixed(galleryNow), () async {
    galleryPhone(tester);
    final messenger = tester.binding.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.hasStrings') return {'value': false};
      return null;
    });
    addTearDown(() => messenger.setMockMethodCallHandler(SystemChannels.platform, null));
    final services = await galleryServices(theme: theme, holdChecks: true);
    await tester.pumpWidget(galleryApp(services, screen(services)));
    if (settle) await tester.pumpAndSettle();
    await then?.call();
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/${name}_${theme.name}.png'),
    );
  });
}

void main() {
  setUpAll(() async {
    await loadAppFonts();
    final local = goldenFileComparator as LocalFileComparator;
    goldenFileComparator = _Tolerant(Uri.parse('${local.basedir}golden_test.dart'), 0.5);
  });

  for (final theme in [ThemeMode.light, ThemeMode.dark]) {
    testWidgets('Check, ${theme.name}', (tester) async {
      await _golden(tester, 'check', theme, (s) => MainShell(services: s));
    });

    testWidgets('Checking mid-way, ${theme.name}', (tester) async {
      final events = StreamController<CheckEvent>();
      await _golden(
        tester,
        'checking',
        theme,
        (s) => CheckingScreen(
          services: s,
          submission: Submission.text(sampleClaim),
          job: mid(s, events),
        ),
        settle: false,
        then: () async {
          await tester.pump(const Duration(milliseconds: 300));
          sendMidCheck(events);
          // Frames, so the sources finish arriving on the ring.
          for (var i = 0; i < 6; i++) {
            await tester.pump(const Duration(milliseconds: 150));
          }
        },
      );
      await tester.pumpWidget(const SizedBox());
      await tester.pump(const Duration(minutes: 3));
      unawaited(events.close());
    });

    for (final kind in FactVerdict.values) {
      testWidgets('Verdict ${kind.name}, ${theme.name}', (tester) async {
        await _golden(
          tester,
          'verdict_${kind.name}',
          theme,
          (s) => ResultScreen(
            services: s,
            verdict: sampleVerdict(kind),
            submission: Submission.text(sampleClaim),
          ),
        );
      });
    }

    // What was read (contract 1.8): a post checked from part of it, and a link whose
    // answer was held back, from the server's own sample responses.
    for (final (name, sample) in [
      ('verdict_readInPart', 'instagram_reel_partial'),
      ('verdict_withheld', 'link_withheld'),
    ]) {
      testWidgets('${name.split('_').last}, ${theme.name}', (tester) async {
        await _golden(
          tester,
          name,
          theme,
          (s) => ResultScreen(
            services: s,
            verdict: contractVerdict(sample),
            submission: Submission.link(contractVerdict(sample).inputRead!.url!),
          ),
        );
      });
    }

    testWidgets('Why sheet, ${theme.name}', (tester) async {
      await _golden(
        tester,
        'why',
        theme,
        (s) => ResultScreen(
          services: s,
          verdict: sampleVerdict(FactVerdict.falseClaim),
          submission: Submission.text(sampleClaim),
        ),
        then: () async {
          await tester.tap(find.text('confidence'));
          await tester.pumpAndSettle();
        },
      );
    });

    testWidgets('History, ${theme.name}', (tester) async {
      await _golden(tester, 'history', theme, (s) => HistoryScreen(services: s));
    });

    testWidgets('Profile, ${theme.name}', (tester) async {
      await _golden(tester, 'profile', theme, (s) => ProfileScreen(services: s));
    });
  }
}
