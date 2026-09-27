/// Welcome, in three pages, then sign up or sign in (v5, 2.1).
///
/// 1. What Factify does, with three example cards: a forward marked False, a news
///    link marked True and a video marked Misleading.
/// 2. That every answer comes with its sources - an example claim and the three
///    sources that refute it - and that the sources not settling it is an answer too.
/// 3. Create an account or sign in.
///
/// Shown after the splash to anyone not signed in. An account is compulsory: there
/// is no way past this screen without creating one or signing in, with an email and
/// a password or with Google - and the server refuses a check from anyone who has
/// not, whatever the app does.
///
/// Also opened from Profile when a guest decides to sign in: it then starts on the
/// sign-in page and returns there, instead of opening the app afresh.
///
/// The examples are invented, and the second page says so: a product whose one
/// claim is that it does not make things up does not show a made-up result as real.
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../app_services.dart';
import '../l10n/app_localizations.dart';
import '../models/verdict.dart';
import '../theme/icons.dart';
import '../theme/tokens.dart';
import '../theme/typography.dart';
import '../widgets/action_style.dart';
import '../widgets/auth_form.dart';
import '../widgets/ui/fx_button.dart';
import 'main_shell.dart';

const int _pages = 3;

class WelcomeScreen extends StatefulWidget {
  const WelcomeScreen({required this.services, this.fromProfile = false, super.key});

  final AppServices services;

  /// Opened from the profile: start on sign-in, and close on sign-in rather than
  /// opening the app.
  final bool fromProfile;

  @override
  State<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends State<WelcomeScreen> {
  late final PageController _pager = PageController(initialPage: widget.fromProfile ? 2 : 0);
  late int _page = widget.fromProfile ? 2 : 0;
  bool _left = false;
  bool _creating = true;

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

  void _onAuth() {
    if (!mounted || _left || !widget.services.auth.signedIn) return;
    _left = true;
    if (widget.fromProfile) {
      Navigator.of(context).pop();
    } else {
      unawaited(
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute<void>(builder: (_) => MainShell(services: widget.services)),
          (_) => false,
        ),
      );
    }
  }

  void _go(int page) {
    FocusManager.instance.primaryFocus?.unfocus();
    final reduce = MediaQuery.of(context).disableAnimations;
    if (reduce) {
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

  void _back() {
    if (_page == 0 || (widget.fromProfile && _page == 2)) {
      Navigator.of(context).maybePop();
    } else {
      _go(_page - 1);
    }
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Scaffold(
      backgroundColor: k.bg,
      body: SafeArea(
        child: ListenableBuilder(
          listenable: widget.services.auth,
          builder: (context, _) => PageView(
            controller: _pager,
            onPageChanged: (page) => setState(() => _page = page),
            children: [
              _Page(
                page: 0,
                header: _FirstHeader(services: widget.services, onSkip: () => _go(2)),
                onNext: () => _go(1),
                child: const _WhatItDoes(),
              ),
              _Page(
                page: 1,
                header: _BackHeader(onBack: _back, onSkip: () => _go(2)),
                onNext: () => _go(2),
                child: const _WithSources(),
              ),
              _SignUp(
                services: widget.services,
                creating: _creating,
                onBack: _page == 2 && widget.fromProfile
                    ? () => Navigator.of(context).pop()
                    : _back,
                onModeChanged: (creating) => setState(() => _creating = creating),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// One of the two introduction pages: a header, the page, and at the foot the page
/// dots and the button onward. Scrolls when the text is large.
class _Page extends StatelessWidget {
  const _Page({
    required this.page,
    required this.header,
    required this.onNext,
    required this.child,
  });

  final int page;
  final Widget header;
  final VoidCallback onNext;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final last = page == _pages - 2;
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
                                last ? l10n.onbGetStarted : l10n.onbNext,
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
                ),
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

/// The mark and name, the language switch and Skip.
class _FirstHeader extends StatelessWidget {
  const _FirstHeader({required this.services, required this.onSkip});

  final AppServices services;
  final VoidCallback onSkip;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final showing = Localizations.localeOf(context).languageCode;
    TextStyle style(bool on) =>
        FactifyText.sans(13, weight: FontWeight.w600, color: on ? k.ink : k.ink3);
    return SizedBox(
      height: 44,
      child: Row(
        children: [
          Container(
            width: 26,
            height: 26,
            decoration: BoxDecoration(color: k.acc, borderRadius: BorderRadius.circular(8)),
            child: Icon(Icons.check_rounded, size: 17, color: k.onAcc),
          ),
          const SizedBox(width: 8),
          // The product name, the same in every language. It gives way to the
          // language switch and Skip when the text is large.
          Expanded(
            child: Text(
              'Factify',
              maxLines: 1,
              overflow: TextOverflow.fade,
              softWrap: false,
              style: FactifyText.serif(
                21,
                weight: FontWeight.w600,
                color: k.ink,
              ).copyWith(letterSpacing: -0.3),
            ),
          ),
          // English or Hindi, each named in itself; the one on screen is darker.
          Semantics(
            button: true,
            label: l10n.languageMenuTooltip,
            child: InkWell(
              borderRadius: BorderRadius.circular(10),
              onTap: () =>
                  unawaited(services.language.choose(Locale(showing == 'hi' ? 'en' : 'hi'))),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 12),
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
          ),
          const SizedBox(width: 8),
          _SkipButton(onSkip: onSkip),
        ],
      ),
    );
  }
}

class _SkipButton extends StatelessWidget {
  const _SkipButton({required this.onSkip});

  final VoidCallback onSkip;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      onTap: onSkip,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 12),
        child: Text(
          l10n.onbSkip,
          style: FactifyText.sans(13, weight: FontWeight.w600, color: k.ink),
        ),
      ),
    );
  }
}

class _BackHeader extends StatelessWidget {
  const _BackHeader({required this.onBack, this.onSkip});

  final VoidCallback onBack;
  final VoidCallback? onSkip;

  @override
  Widget build(BuildContext context) {
    final onSkip = this.onSkip;
    return SizedBox(
      height: 44,
      child: Row(
        children: [
          FxCircleButton(
            icon: FxIcons.back,
            tooltip: MaterialLocalizations.of(context).backButtonTooltip,
            onPressed: onBack,
          ),
          const Spacer(),
          if (onSkip != null) _SkipButton(onSkip: onSkip),
        ],
      ),
    );
  }
}

/// Page 1: three example cards, and what Factify does.
class _WhatItDoes extends StatelessWidget {
  const _WhatItDoes();

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 18),
        // Decorative: the cards are drawn at a fixed size and scaled to fit, and
        // their text is held near its normal size so the cards keep their shape.
        ExcludeSemantics(
          child: MediaQuery.withClampedTextScaling(
            maxScaleFactor: 1.1,
            child: FittedBox(
              fit: BoxFit.scaleDown,
              child: SizedBox(width: 324, height: 340, child: _ExampleCards(l10n: l10n)),
            ),
          ),
        ),
        const SizedBox(height: 18),
        Text(
          l10n.welcomeTitle,
          style: FactifyText.serif(34, color: k.ink).copyWith(height: 1.04, letterSpacing: -1),
        ),
        const SizedBox(height: 12),
        Text(l10n.welcomeBody, style: FactifyText.sans(14, color: k.ink2).copyWith(height: 1.55)),
      ],
    );
  }
}

class _ExampleCards extends StatelessWidget {
  const _ExampleCards({required this.l10n});

  final AppLocalizations l10n;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Stack(
      children: [
        Positioned(
          left: 20,
          right: 20,
          top: 30,
          bottom: 10,
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: RadialGradient(colors: [k.accS, k.accS.withValues(alpha: 0)]),
            ),
          ),
        ),
        Positioned(
          left: 10,
          top: 14,
          width: 232,
          child: _Tilted(
            degrees: -5,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(FxIcons.forwarded, size: 14, color: k.ink3),
                    const SizedBox(width: 5),
                    Flexible(
                      child: Text(
                        l10n.onbForwarded,
                        style: FactifyText.sans(
                          11,
                          color: k.ink3,
                        ).copyWith(fontStyle: FontStyle.italic),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 5),
                Text(
                  l10n.onbSampleForward,
                  style: FactifyText.sans(13, color: k.ink).copyWith(height: 1.4),
                ),
                const SizedBox(height: 9),
                _Pill(verdict: FactVerdict.falseClaim),
              ],
            ),
          ),
        ),
        Positioned(
          right: 6,
          top: 118,
          width: 210,
          child: _Tilted(
            degrees: 4,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(FxIcons.link, size: 14, color: k.ink3),
                    const SizedBox(width: 5),
                    // A web address, the same in every language.
                    Text('rbi.org.in', style: FactifyText.sans(11, color: k.ink3)),
                  ],
                ),
                const SizedBox(height: 5),
                Text(
                  l10n.onbSampleLink,
                  style: FactifyText.serif(
                    16,
                    weight: FontWeight.w400,
                    color: k.ink,
                  ).copyWith(height: 1.25),
                ),
                const SizedBox(height: 9),
                _Pill(verdict: FactVerdict.trueClaim),
              ],
            ),
          ),
        ),
        Positioned(
          // Lower than the design's 222: the headline above wraps to three lines
          // in Newsreader here, and its True pill must not hide under this card.
          left: 30,
          top: 246,
          width: 236,
          child: _Tilted(
            degrees: -2,
            padding: const EdgeInsets.all(10),
            child: Row(
              children: [
                Container(
                  width: 58,
                  height: 58,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(color: k.sf2, borderRadius: BorderRadius.circular(12)),
                  child: Text(
                    l10n.onbVideo.toUpperCase(),
                    style: FactifyText.mono(8, color: k.ink3, spacing: 0.4),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        l10n.onbSampleVideo,
                        style: FactifyText.sans(12.5, color: k.ink).copyWith(height: 1.35),
                      ),
                      const SizedBox(height: 6),
                      _Pill(verdict: FactVerdict.misleading, small: true),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _Tilted extends StatelessWidget {
  const _Tilted({
    required this.degrees,
    required this.child,
    this.padding = const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
  });

  final double degrees;
  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Transform.rotate(
      angle: degrees * math.pi / 180,
      child: Container(
        padding: padding,
        decoration: BoxDecoration(
          color: k.sf,
          borderRadius: BorderRadius.circular(18),
          border: k.isDark ? Border.all(color: k.line) : null,
          boxShadow: [
            ...k.shadow,
            const BoxShadow(
              offset: Offset(0, 12),
              blurRadius: 30,
              spreadRadius: -12,
              color: Color.fromRGBO(0, 0, 0, .18),
            ),
          ],
        ),
        child: child,
      ),
    );
  }
}

/// A verdict word on its tint, with its icon: never colour alone.
class _Pill extends StatelessWidget {
  const _Pill({required this.verdict, this.small = false, this.suffix = ''});

  final FactVerdict verdict;
  final bool small;
  final String suffix;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final (strong, soft) = ActionStyle.colours(verdict, k);
    return Container(
      padding: EdgeInsets.symmetric(horizontal: small ? 8 : 9, vertical: small ? 3 : 4),
      decoration: BoxDecoration(color: soft, borderRadius: BorderRadius.circular(small ? 8 : 9)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(ActionStyle.iconFor(verdict), size: small ? 13 : 14, color: strong),
          const SizedBox(width: 4),
          Text(
            '${ActionStyle.word(verdict, l10n)}$suffix',
            style: FactifyText.sans(small ? 11 : 11.5, weight: FontWeight.w700, color: strong),
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
        Text(
          l10n.welcomePointSources,
          style: FactifyText.serif(34, color: k.ink).copyWith(height: 1.04, letterSpacing: -1),
        ),
        const SizedBox(height: 12),
        Text(
          l10n.onbSourcesBody,
          style: FactifyText.sans(14, color: k.ink2).copyWith(height: 1.55),
        ),
        const SizedBox(height: 16),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _Feature(icon: FxIcons.document, text: l10n.welcomePointInputs),
            _Feature(icon: FxIcons.language, text: l10n.welcomePointLanguages),
          ],
        ),
      ],
    );
  }
}

class _Feature extends StatelessWidget {
  const _Feature({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Container(
      constraints: const BoxConstraints(minHeight: 32),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(color: k.sf, borderRadius: BorderRadius.circular(16)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 16, color: k.acc),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              text,
              style: FactifyText.sans(12.5, weight: FontWeight.w500, color: k.ink),
            ),
          ),
        ],
      ),
    );
  }
}

/// Page 3: create an account or sign in.
class _SignUp extends StatelessWidget {
  const _SignUp({
    required this.services,
    required this.creating,
    required this.onBack,
    required this.onModeChanged,
  });

  final AppServices services;
  final bool creating;
  final VoidCallback onBack;
  final ValueChanged<bool> onModeChanged;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    return CustomScrollView(
      slivers: [
        SliverFillRemaining(
          hasScrollBody: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 6, 24, 22),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _BackHeader(onBack: onBack),
                const SizedBox(height: 22),
                Text(
                  creating ? l10n.welcomeSignInTitle : l10n.welcomeBackTitle,
                  style: FactifyText.serif(
                    34,
                    color: k.ink,
                  ).copyWith(height: 1.04, letterSpacing: -1),
                ),
                const SizedBox(height: 10),
                Text(
                  creating ? l10n.welcomeSignInBody : l10n.welcomeBackBody,
                  style: FactifyText.sans(14, color: k.ink2).copyWith(height: 1.5),
                ),
                AuthForm(auth: services.auth, onModeChanged: onModeChanged),
                const Spacer(),
                const SizedBox(height: 16),
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
              ],
            ),
          ),
        ),
      ],
    );
  }
}
