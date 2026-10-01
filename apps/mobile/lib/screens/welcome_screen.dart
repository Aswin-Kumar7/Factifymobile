/// Welcome, in three pages, then sign up or sign in.
///
/// 1. The seal, the name, and an example forward stamped False: what Factify does.
/// 2. That every answer comes with its sources - an example claim and the three
///    sources that refute it - and that the sources not settling it is an answer too.
/// 3. That pictures and videos are checked too, and the way in:
///    Create account, or I have an account.
///
/// Either button opens the sign-up screen ([AuthScreen]); it opens on creating an
/// account or on signing in, and switches between them with a line at its foot.
/// A new account then meets the four-question survey and its free credits
/// (`survey_screen.dart`); anyone else goes straight into the app.
///
/// Shown after the splash to anyone not signed in. An account is compulsory: there
/// is no way past this screen without creating one or signing in, with an email and
/// a password or with Google - and the server refuses a check from anyone who has
/// not, whatever the app does.
///
/// Also opened from Profile when a guest decides to sign in: it then opens straight
/// on signing in and returns there, instead of opening the app afresh.
///
/// The examples are invented, and the second page says so: a product whose one
/// claim is that it does not make things up does not show a made-up result as real.
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../app_services.dart';
import '../l10n/app_localizations.dart';
import '../models/verdict.dart';
import '../theme/icons.dart';
import '../theme/tokens.dart';
import '../theme/typography.dart';
import '../widgets/action_style.dart';
import '../widgets/auth_form.dart';
import '../widgets/brand.dart';
import '../widgets/ui/fx_button.dart';
import '../widgets/ui/fx_tap_area.dart';
import 'survey_screen.dart';

const int _pages = 3;

class WelcomeScreen extends StatefulWidget {
  const WelcomeScreen({required this.services, this.fromProfile = false, super.key});

  final AppServices services;

  /// Opened from the profile: open on signing in, and close on sign-in rather than
  /// opening the app.
  final bool fromProfile;

  @override
  State<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends State<WelcomeScreen> {
  final PageController _pager = PageController();
  bool _left = false;

  @override
  void initState() {
    super.initState();
    widget.services.auth.addListener(_onAuth);
  }

  @override
  void dispose() {
    widget.services.auth.removeListener(_onAuth);
    _pager.dispose();
    super.dispose();
  }

  /// Signed in, here or on the sign-up screen above: into the app, by way of the
  /// survey for a new account.
  void _onAuth() {
    if (!mounted || _left || !widget.services.auth.signedIn) return;
    _left = true;
    if (widget.fromProfile) {
      Navigator.of(context).pop();
      return;
    }
    unawaited(_enter());
  }

  Future<void> _enter() async {
    final services = widget.services;
    // Whether the survey is due is the server's answer; if it cannot be had in
    // time the app opens, and the survey is offered on a later sign-in.
    await services.auth
        .refreshAccount()
        .timeout(const Duration(seconds: 8), onTimeout: () => null)
        .catchError((Object _) => null);
    if (!mounted) return;
    unawaited(
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute<void>(builder: (_) => signedInHome(services)),
        (_) => false,
      ),
    );
  }

  void _go(int page) {
    FocusManager.instance.primaryFocus?.unfocus();
    if (MediaQuery.of(context).disableAnimations) {
      _pager.jumpToPage(page);
    } else {
      unawaited(
        _pager.animateToPage(
          page,
          duration: const Duration(milliseconds: 320),
          curve: Curves.easeOutCubic,
        ),
      );
    }
  }

  void _openAuth({required bool creating}) => unawaited(
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => AuthScreen(services: widget.services, creating: creating),
      ),
    ),
  );

  @override
  Widget build(BuildContext context) {
    if (widget.fromProfile) {
      return AuthScreen(services: widget.services, creating: false);
    }
    final k = FactifyTokens.of(context);
    return Scaffold(
      backgroundColor: k.bg,
      body: SafeArea(
        child: ListenableBuilder(
          listenable: widget.services.auth,
          builder: (context, _) => PageView(
            controller: _pager,
            children: [
              _Page(
                page: 0,
                header: _Header(services: widget.services, onSkip: () => _go(2)),
                onNext: () => _go(1),
                child: const _WhatItDoes(),
              ),
              _Page(
                page: 1,
                header: _Header(onBack: () => _go(0), onSkip: () => _go(2)),
                onNext: () => _go(2),
                child: const _WithSources(),
              ),
              _Page(
                page: 2,
                header: _Header(onBack: () => _go(1)),
                onCreate: () => _openAuth(creating: true),
                onSignIn: () => _openAuth(creating: false),
                child: const _AllKinds(),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Creating an account or signing in: Google, or an email and a password.
class AuthScreen extends StatefulWidget {
  const AuthScreen({required this.services, this.creating = true, super.key});

  final AppServices services;
  final bool creating;

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  late bool _creating = widget.creating;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      backgroundColor: k.bg,
      body: SafeArea(
        child: ListenableBuilder(
          listenable: widget.services.auth,
          builder: (context, _) => CustomScrollView(
            slivers: [
              SliverFillRemaining(
                hasScrollBody: false,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(24, 6, 24, 22),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      SizedBox(
                        height: 44,
                        child: Row(
                          children: [
                            FxCircleButton(
                              icon: FxIcons.back,
                              tooltip: MaterialLocalizations.of(context).backButtonTooltip,
                              onPressed: () => Navigator.of(context).maybePop(),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 18),
                      const Align(
                        alignment: AlignmentDirectional.centerStart,
                        child: FactifyMark(size: 52),
                      ),
                      const SizedBox(height: 18),
                      Semantics(
                        header: true,
                        child: Text(
                          _creating ? l10n.signUpTitle : l10n.welcomeBackTitle,
                          style: FactifyText.serif(
                            34,
                            color: k.ink,
                          ).copyWith(height: 1.04, letterSpacing: -1),
                        ),
                      ),
                      const SizedBox(height: 10),
                      Text(
                        _creating ? l10n.signUpBody : l10n.welcomeBackBody,
                        style: FactifyText.sans(14, color: k.ink2).copyWith(height: 1.5),
                      ),
                      AuthForm(
                        auth: widget.services.auth,
                        creating: _creating,
                        onModeChanged: (creating) => setState(() => _creating = creating),
                      ),
                      const Spacer(),
                      const SizedBox(height: 18),
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(FxIcons.privacy, size: 16, color: k.ink3),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              l10n.onbPrivacy,
                              style: FactifyText.sans(12, color: k.ink3).copyWith(height: 1.5),
                            ),
                          ),
                        ],
                      ),
                      Align(
                        alignment: AlignmentDirectional.centerStart,
                        child: FxTapArea(
                          onTap: () => unawaited(
                            launchUrl(
                              widget.services.client.privacyPolicy,
                              mode: LaunchMode.externalApplication,
                            ),
                          ),
                          child: Padding(
                            padding: const EdgeInsetsDirectional.only(start: 24, end: 6),
                            child: Text(
                              l10n.privacyPolicy,
                              style: FactifyText.sans(12, weight: FontWeight.w600, color: k.acc)
                                  .copyWith(
                                    decoration: TextDecoration.underline,
                                    decorationColor: k.acc,
                                  ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// One welcome page: a header, the page, and at the foot the page dots with Next -
/// or, on the last page, the two ways in. Scrolls when the text is large.
class _Page extends StatelessWidget {
  const _Page({
    required this.page,
    required this.header,
    required this.child,
    this.onNext,
    this.onCreate,
    this.onSignIn,
  });

  final int page;
  final Widget header;
  final Widget child;
  final VoidCallback? onNext;
  final VoidCallback? onCreate;
  final VoidCallback? onSignIn;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final onNext = this.onNext;
    final onCreate = this.onCreate;
    final onSignIn = this.onSignIn;
    return CustomScrollView(
      slivers: [
        SliverFillRemaining(
          hasScrollBody: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 6, 24, 22),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                header,
                child,
                const Spacer(),
                const SizedBox(height: 20),
                if (onNext != null)
                  Row(
                    children: [
                      _Dots(page: page),
                      const Spacer(),
                      Material(
                        color: k.acc,
                        shape: const StadiumBorder(),
                        clipBehavior: Clip.antiAlias,
                        child: InkWell(
                          onTap: onNext,
                          child: Container(
                            height: 54,
                            padding: const EdgeInsetsDirectional.fromSTEB(26, 0, 22, 0),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  l10n.onbNext,
                                  style: FactifyText.sans(
                                    15,
                                    weight: FontWeight.w600,
                                    color: k.onAcc,
                                  ),
                                ),
                                const SizedBox(width: 8),
                                Icon(
                                  FxIcons.forward,
                                  size: 20,
                                  color: k.onAcc,
                                  textDirection: Directionality.of(context),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ],
                  )
                else ...[
                  Center(child: _Dots(page: page)),
                  const SizedBox(height: 18),
                  FxButton(
                    label: l10n.createAccountButton,
                    onPressed: onCreate,
                    height: 54,
                    radius: 18,
                    fontSize: 15,
                  ),
                  const SizedBox(height: 10),
                  FxButton(
                    label: l10n.onbHaveAccount,
                    variant: FxButtonVariant.outline,
                    onPressed: onSignIn,
                    height: 54,
                    radius: 18,
                    fontSize: 15,
                  ),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _Dots extends StatelessWidget {
  const _Dots({required this.page});

  final int page;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    return Semantics(
      label: l10n.onbPage(page + 1, _pages),
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < _pages; i++) ...[
            if (i > 0) const SizedBox(width: 6),
            AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              width: i == page ? 22 : 6,
              height: 6,
              decoration: BoxDecoration(
                color: i == page ? k.ink : k.line,
                borderRadius: BorderRadius.circular(3),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Back (after the first page), the language switch (on the first), and Skip.
class _Header extends StatelessWidget {
  const _Header({this.services, this.onBack, this.onSkip});

  final AppServices? services;
  final VoidCallback? onBack;
  final VoidCallback? onSkip;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final services = this.services;
    final onBack = this.onBack;
    final onSkip = this.onSkip;
    final showing = Localizations.localeOf(context).languageCode;
    TextStyle style(bool on) =>
        FactifyText.sans(13, weight: FontWeight.w600, color: on ? k.ink : k.ink3);
    return SizedBox(
      height: 44,
      child: Row(
        children: [
          if (onBack != null)
            FxCircleButton(
              icon: FxIcons.back,
              tooltip: MaterialLocalizations.of(context).backButtonTooltip,
              onPressed: onBack,
            ),
          // English or Hindi, each named in itself; the one on screen is darker.
          if (services != null)
            FxTapArea(
              label: l10n.languageMenuTooltip,
              onTap: () =>
                  unawaited(services.language.choose(Locale(showing == 'hi' ? 'en' : 'hi'))),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 6),
                child: Text.rich(
                  TextSpan(
                    children: [
                      TextSpan(text: 'EN', style: style(showing == 'en')),
                      TextSpan(text: ' · ', style: style(false)),
                      TextSpan(text: 'हि', style: style(showing == 'hi')),
                    ],
                  ),
                ),
              ),
            ),
          const Spacer(),
          if (onSkip != null)
            FxTapArea(
              onTap: onSkip,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 6),
                child: Text(
                  l10n.onbSkip,
                  style: FactifyText.sans(13, weight: FontWeight.w600, color: k.ink),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Page 1: the seal and the name, an example forward stamped False, and what
/// Factify does.
class _WhatItDoes extends StatelessWidget {
  const _WhatItDoes();

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 14),
        Row(
          children: [
            const FactifyMark(size: 46),
            const SizedBox(width: 12),
            // The product name, the same in every language; scaled down rather
            // than cut when the text is large.
            Flexible(
              child: FittedBox(
                fit: BoxFit.scaleDown,
                alignment: AlignmentDirectional.centerStart,
                child: Text(
                  'Factify',
                  style: FactifyText.serif(
                    30,
                    weight: FontWeight.w600,
                    color: k.ink,
                  ).copyWith(letterSpacing: -0.6),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 26),
        // Decorative: an invented forward and an invented headline, each stamped
        // with its verdict as a news desk would stamp it.
        ExcludeSemantics(
          child: MediaQuery.withClampedTextScaling(
            maxScaleFactor: 1.15,
            child: Column(
              children: [
                _StampedCard(
                  icon: FxIcons.forwarded,
                  source: l10n.onbForwarded,
                  italic: true,
                  text: l10n.onbSampleForward,
                  verdict: FactVerdict.falseClaim,
                  degrees: -1.5,
                ),
                const SizedBox(height: 26),
                _StampedCard(
                  icon: FxIcons.link,
                  // A web address, the same in every language.
                  source: 'rbi.org.in',
                  text: l10n.onbSampleLink,
                  serif: true,
                  verdict: FactVerdict.trueClaim,
                  degrees: 1.5,
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 34),
        Semantics(
          header: true,
          child: Text(
            l10n.welcomeTitle,
            style: FactifyText.serif(34, color: k.ink).copyWith(height: 1.04, letterSpacing: -1),
          ),
        ),
        const SizedBox(height: 12),
        Text(l10n.welcomeBody, style: FactifyText.sans(14, color: k.ink2).copyWith(height: 1.55)),
      ],
    );
  }
}

/// An example card - where it came from and what it says - with its verdict
/// stamped over its lower edge.
class _StampedCard extends StatelessWidget {
  const _StampedCard({
    required this.icon,
    required this.source,
    required this.text,
    required this.verdict,
    required this.degrees,
    this.italic = false,
    this.serif = false,
  });

  final IconData icon;
  final String source;
  final String text;
  final FactVerdict verdict;
  final double degrees;
  final bool italic;
  final bool serif;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Transform.rotate(
      angle: degrees * math.pi / 180,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 26),
            decoration: BoxDecoration(
              color: k.sf,
              borderRadius: BorderRadius.circular(20),
              border: k.isDark ? Border.all(color: k.line) : null,
              boxShadow: k.isDark ? null : k.shadow,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(icon, size: 14, color: k.ink3),
                    const SizedBox(width: 5),
                    Flexible(
                      child: Text(
                        source,
                        style: FactifyText.sans(
                          11.5,
                          color: k.ink3,
                        ).copyWith(fontStyle: italic ? FontStyle.italic : null),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 7),
                Text(
                  text,
                  style: serif
                      ? FactifyText.serif(
                          17,
                          weight: FontWeight.w400,
                          color: k.ink,
                        ).copyWith(height: 1.3)
                      : FactifyText.sans(14, color: k.ink).copyWith(height: 1.45),
                ),
              ],
            ),
          ),
          PositionedDirectional(
            end: 14,
            bottom: -16,
            child: Transform.rotate(
              angle: (degrees < 0 ? -9 : 7) * math.pi / 180,
              child: _Stamp(verdict: verdict),
            ),
          ),
        ],
      ),
    );
  }
}

/// A verdict as an ink stamp: a double ring and the word, in the verdict's colour.
class _Stamp extends StatelessWidget {
  const _Stamp({required this.verdict});

  final FactVerdict verdict;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final (strong, _) = ActionStyle.colours(verdict, k);
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(
        color: k.bg,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: strong, width: 2),
      ),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(7),
          border: Border.all(color: strong.withValues(alpha: 0.55)),
        ),
        child: Text(
          ActionStyle.word(verdict, l10n).toUpperCase(),
          style: FactifyText.serif(
            17,
            weight: FontWeight.w600,
            color: strong,
          ).copyWith(letterSpacing: 1.5, height: 1.1),
        ),
      ),
    );
  }
}

/// A verdict word on its tint, with its icon: never colour alone.
class _Pill extends StatelessWidget {
  const _Pill({required this.verdict, this.suffix = ''});

  final FactVerdict verdict;
  final String suffix;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final (strong, soft) = ActionStyle.colours(verdict, k);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(color: soft, borderRadius: BorderRadius.circular(9)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(ActionStyle.iconFor(verdict), size: 14, color: strong),
          const SizedBox(width: 4),
          Text(
            '${ActionStyle.word(verdict, l10n)}$suffix',
            style: FactifyText.sans(11.5, weight: FontWeight.w700, color: strong),
          ),
        ],
      ),
    );
  }
}

/// Page 2: an example claim and the sources that refute it.
class _WithSources extends StatelessWidget {
  const _WithSources();

  /// Publisher names are names: the same in every language.
  static const _sources = [
    ('PIB', 'PIB Fact Check', 'HIGH', 'C'),
    ('AN', 'Alt News', 'HIGH', 'C'),
    ('TH', 'The Hindu', 'MEDIUM', 'B'),
  ];

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 20),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: k.sf,
            borderRadius: BorderRadius.circular(24),
            border: k.isDark ? Border.all(color: k.line) : null,
            boxShadow: k.isDark ? null : k.shadow,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      l10n.onbExample.toUpperCase(),
                      style: FactifyText.mono(10.5, color: k.ink3, spacing: 1),
                    ),
                  ),
                  const _Pill(verdict: FactVerdict.falseClaim, suffix: ' · 91%'),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                '“${l10n.onbSampleClaim}”',
                style: FactifyText.serif(
                  18,
                  weight: FontWeight.w400,
                  color: k.ink,
                ).copyWith(height: 1.3),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(0, 14, 0, 4),
                child: SizedBox(
                  height: 1,
                  width: double.infinity,
                  child: ColoredBox(color: k.line),
                ),
              ),
              for (final (initials, publisher, credibility, tier) in _sources)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Row(
                    children: [
                      Container(
                        width: 30,
                        height: 30,
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          color: k.sf2,
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Text(
                          initials,
                          style: FactifyText.sans(10, weight: FontWeight.w700, color: k.ink2),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              publisher,
                              style: FactifyText.sans(13.5, weight: FontWeight.w600, color: k.ink),
                            ),
                            Text(
                              '${l10n.credibility(credibility)} · ${l10n.tierLabel(tier)}',
                              style: FactifyText.sans(11.5, color: k.ink3),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        l10n.sourceRefutes,
                        style: FactifyText.sans(11.5, weight: FontWeight.w700, color: k.fC),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 26),
        Semantics(
          header: true,
          child: Text(
            l10n.welcomePointSources,
            style: FactifyText.serif(34, color: k.ink).copyWith(height: 1.04, letterSpacing: -1),
          ),
        ),
        const SizedBox(height: 12),
        Text(
          l10n.onbSourcesBody,
          style: FactifyText.sans(14, color: k.ink2).copyWith(height: 1.55),
        ),
      ],
    );
  }
}

/// Page 3: every kind of thing that can be checked.
class _AllKinds extends StatelessWidget {
  const _AllKinds();

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final kinds = [
      (FxIcons.message, l10n.onbMediaMessages),
      (FxIcons.link, l10n.onbMediaLinks),
      (FxIcons.image, l10n.onbMediaPictures),
      (FxIcons.video, l10n.onbMediaVideos),
      (FxIcons.voice, l10n.onbMediaVoice),
      (FxIcons.pdf, l10n.onbMediaPdfs),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 20),
        // Two rows of three. Not a GridView: a shrink-wrapped grid cannot size itself
        // inside the page's fill-the-screen scroll view.
        for (final row in [kinds.sublist(0, 3), kinds.sublist(3)]) ...[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (final (i, (icon, label)) in row.indexed) ...[
                if (i > 0) const SizedBox(width: 10),
                Expanded(
                  child: _Kind(icon: icon, label: label),
                ),
              ],
            ],
          ),
          const SizedBox(height: 10),
        ],
        const SizedBox(height: 26),
        Semantics(
          header: true,
          child: Text(
            l10n.onb3Title,
            style: FactifyText.serif(34, color: k.ink).copyWith(height: 1.04, letterSpacing: -1),
          ),
        ),
        const SizedBox(height: 12),
        Text(l10n.onb3Body, style: FactifyText.sans(14, color: k.ink2).copyWith(height: 1.55)),
      ],
    );
  }
}

class _Kind extends StatelessWidget {
  const _Kind({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Container(
      constraints: const BoxConstraints(minHeight: 104),
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 12),
      decoration: BoxDecoration(
        color: k.sf,
        borderRadius: BorderRadius.circular(20),
        border: k.isDark ? Border.all(color: k.line) : null,
        boxShadow: k.isDark ? null : k.shadow,
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(color: k.accS, shape: BoxShape.circle),
            child: Icon(icon, size: 22, color: k.acc),
          ),
          const SizedBox(height: 8),
          Text(
            label,
            textAlign: TextAlign.center,
            style: FactifyText.sans(12.5, weight: FontWeight.w600, color: k.ink),
          ),
        ],
      ),
    );
  }
}
