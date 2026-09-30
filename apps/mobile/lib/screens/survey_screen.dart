/// Four short questions, asked once after a new account is made - with an email or
/// with Google - and then the welcome with the free credits.
///
/// 1. What brings you to Factify? (one)
/// 2. Where do you see things you'd like to check? (any)
/// 3. What do you want to check most? (any)
/// 4. How did you hear about Factify? (one)
///
/// Every question can be passed over with Next, and the whole survey with Skip all.
/// Whether it is due is the server's answer (`Account.surveyDue`), so a person who
/// signs in on a second phone is not asked again; an account made before the survey
/// existed is never asked. A failure to save never holds anyone here.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../app_services.dart';
import '../l10n/app_localizations.dart';
import '../models/account.dart';
import '../theme/icons.dart';
import '../theme/tokens.dart';
import '../theme/typography.dart';
import '../widgets/brand.dart';
import '../widgets/ui/fx_button.dart';
import '../widgets/ui/fx_tap_area.dart';
import 'main_shell.dart';

/// Where a signed-in person lands: the survey for a new account, else the app.
Widget signedInHome(AppServices services) {
  final account = services.auth.account;
  if (account != null && account.surveyDue) return SurveyScreen(services: services);
  return MainShell(services: services);
}

class SurveyScreen extends StatefulWidget {
  const SurveyScreen({required this.services, super.key});

  final AppServices services;

  @override
  State<SurveyScreen> createState() => _SurveyScreenState();
}

class _SurveyScreenState extends State<SurveyScreen> {
  static const _total = 4;

  final PageController _pager = PageController();
  int _step = 0;
  bool _busy = false;

  String? _role;
  final Set<String> _places = {};
  final Set<String> _wants = {};
  String? _heard;

  @override
  void dispose() {
    _pager.dispose();
    super.dispose();
  }

  void _next() {
    if (_step == _total - 1) {
      unawaited(_finish(skipped: false));
      return;
    }
    setState(() => _step++);
    if (MediaQuery.of(context).disableAnimations) {
      _pager.jumpToPage(_step);
    } else {
      unawaited(
        _pager.animateToPage(
          _step,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOutCubic,
        ),
      );
    }
  }

  void _back() {
    if (_step == 0) return;
    setState(() => _step--);
    _pager.jumpToPage(_step);
  }

  Future<void> _finish({required bool skipped}) async {
    setState(() => _busy = true);
    final answers = skipped
        ? null
        : SurveyAnswers(role: _role, places: _places, wants: _wants, heard: _heard);
    try {
      await widget.services.auth.answerSurvey(answers);
    } catch (_) {
      // Never held here: the answers are for us, not a gate. The server still has
      // the survey as due, so it is offered again on the next sign-in.
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(AppLocalizations.of(context).surveySaveFailed)),
        );
      }
    }
    if (!mounted) return;
    unawaited(
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute<void>(builder: (_) => CreditsWelcomeScreen(services: widget.services)),
        (_) => false,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final questions = <Widget>[
      _Question(
        title: l10n.surveyRoleQ,
        intro: l10n.surveyWhy,
        children: [
          for (final (key, icon, label) in [
            ('journalist', FxIcons.newspaper, l10n.surveyRoleJournalist),
            ('student', FxIcons.student, l10n.surveyRoleStudent),
            ('teacher', FxIcons.teacher, l10n.surveyRoleTeacher),
            ('family', FxIcons.family, l10n.surveyRoleFamily),
            ('curious', FxIcons.curious, l10n.surveyRoleCurious),
          ])
            _Choice(
              label: label,
              icon: icon,
              chosen: _role == key,
              single: true,
              onTap: () => setState(() => _role = _role == key ? null : key),
            ),
        ],
      ),
      _Question(
        title: l10n.surveyPlacesQ,
        intro: l10n.surveyPickAny,
        wrap: true,
        children: [
          // App names are names, the same in every language.
          for (final (key, label) in [
            ('whatsapp', 'WhatsApp'),
            ('instagram', 'Instagram'),
            ('youtube', 'YouTube'),
            ('facebook', 'Facebook'),
            ('x', 'X'),
            ('telegram', 'Telegram'),
            ('news_sites', l10n.surveyPlaceNews),
          ])
            _Chip(
              label: label,
              chosen: _places.contains(key),
              onTap: () => setState(() => _places.contains(key) ? _places.remove(key) : _places.add(key)),
            ),
        ],
      ),
      _Question(
        title: l10n.surveyWantsQ,
        intro: l10n.surveyPickAny,
        children: [
          for (final (key, icon, label) in [
            ('forwards', FxIcons.message, l10n.surveyWantForwards),
            ('links', FxIcons.link, l10n.surveyWantLinks),
            ('pictures', FxIcons.image, l10n.surveyWantPictures),
            ('videos', FxIcons.video, l10n.surveyWantVideos),
            ('voice', FxIcons.voice, l10n.surveyWantVoice),
          ])
            _Choice(
              label: label,
              icon: icon,
              chosen: _wants.contains(key),
              onTap: () => setState(() => _wants.contains(key) ? _wants.remove(key) : _wants.add(key)),
            ),
        ],
      ),
      _Question(
        title: l10n.surveyHeardQ,
        children: [
          for (final (key, label) in [
            ('friend', l10n.surveyHeardFriend),
            ('social', l10n.surveyHeardSocial),
            ('college', l10n.surveyHeardCollege),
            ('other', l10n.surveyHeardOther),
          ])
            _Choice(
              label: label,
              chosen: _heard == key,
              single: true,
              onTap: () => setState(() => _heard = _heard == key ? null : key),
            ),
        ],
      ),
    ];

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _back();
      },
      child: Scaffold(
        backgroundColor: k.bg,
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 8, 24, 20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                SizedBox(
                  height: 44,
                  child: Row(
                    children: [
                      if (_step > 0)
                        FxCircleButton(
                          icon: FxIcons.back,
                          tooltip: MaterialLocalizations.of(context).backButtonTooltip,
                          onPressed: _back,
                        )
                      else
                        const FactifyMark(size: 30),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          l10n.surveyStep(_step + 1, _total),
                          style: FactifyText.sans(13, weight: FontWeight.w600, color: k.ink3),
                        ),
                      ),
                      FxTapArea(
                        onTap: _busy ? null : () => unawaited(_finish(skipped: true)),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 6),
                          child: Text(
                            l10n.surveySkipAll,
                            style: FactifyText.sans(13, weight: FontWeight.w600, color: k.ink),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 10),
                ClipRRect(
                  borderRadius: BorderRadius.circular(3),
                  child: TweenAnimationBuilder<double>(
                    tween: Tween(end: (_step + 1) / _total),
                    duration: const Duration(milliseconds: 300),
                    builder: (_, value, _) => LinearProgressIndicator(
                      value: value,
                      minHeight: 5,
                      backgroundColor: k.line,
                      color: k.acc,
                    ),
                  ),
                ),
                Expanded(
                  child: PageView(
                    controller: _pager,
                    physics: const NeverScrollableScrollPhysics(),
                    children: questions,
                  ),
                ),
                const SizedBox(height: 12),
                FxButton(
                  label: _step == _total - 1 ? l10n.surveyFinish : l10n.surveyNext,
                  trailingIcon: _step == _total - 1 ? null : FxIcons.forward,
                  busy: _busy,
                  onPressed: _busy ? null : _next,
                  height: 54,
                  radius: 18,
                  fontSize: 15,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Question extends StatelessWidget {
  const _Question({required this.title, required this.children, this.intro, this.wrap = false});

  final String title;
  final String? intro;
  final bool wrap;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final intro = this.intro;
    return SingleChildScrollView(
      padding: const EdgeInsets.only(top: 26, bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Semantics(
            header: true,
            child: Text(
              title,
              style: FactifyText.serif(30, color: k.ink).copyWith(height: 1.08, letterSpacing: -0.8),
            ),
          ),
          if (intro != null) ...[
            const SizedBox(height: 10),
            Text(intro, style: FactifyText.sans(14, color: k.ink2).copyWith(height: 1.5)),
          ],
          const SizedBox(height: 22),
          if (wrap)
            Wrap(spacing: 8, runSpacing: 10, children: children)
          else
            for (final child in children)
              Padding(padding: const EdgeInsets.only(bottom: 10), child: child),
        ],
      ),
    );
  }
}

/// A full-width answer: a radio for one-answer questions, a box for pick-any.
class _Choice extends StatelessWidget {
  const _Choice({
    required this.label,
    required this.chosen,
    required this.onTap,
    this.icon,
    this.single = false,
  });

  final String label;
  final IconData? icon;
  final bool chosen;
  final bool single;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final icon = this.icon;
    return Semantics(
      selected: chosen,
      inMutuallyExclusiveGroup: single,
      button: true,
      child: Material(
        color: chosen ? k.accS : k.sf,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: chosen ? k.acc : k.line, width: chosen ? 1.6 : 1),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 56),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Row(
                children: [
                  if (icon != null) ...[
                    Icon(icon, size: 22, color: chosen ? k.acc : k.ink2),
                    const SizedBox(width: 12),
                  ],
                  Expanded(
                    child: Text(
                      label,
                      style: FactifyText.sans(15, weight: FontWeight.w500, color: k.ink),
                    ),
                  ),
                  const SizedBox(width: 8),
                  _Tick(chosen: chosen, round: single),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _Tick extends StatelessWidget {
  const _Tick({required this.chosen, required this.round});

  final bool chosen;
  final bool round;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      width: 22,
      height: 22,
      decoration: BoxDecoration(
        color: chosen ? k.acc : null,
        borderRadius: BorderRadius.circular(round ? 11 : 6),
        border: Border.all(color: chosen ? k.acc : k.ink3, width: 1.5),
      ),
      child: chosen ? Icon(Icons.check_rounded, size: 15, color: k.onAcc) : null,
    );
  }
}

/// A pick-any answer as a chip, for short names.
class _Chip extends StatelessWidget {
  const _Chip({required this.label, required this.chosen, required this.onTap});

  final String label;
  final bool chosen;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Semantics(
      selected: chosen,
      button: true,
      child: Material(
        color: chosen ? k.accS : k.sf,
        shape: StadiumBorder(side: BorderSide(color: chosen ? k.acc : k.line, width: chosen ? 1.6 : 1)),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 48),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (chosen) ...[
                    Icon(Icons.check_rounded, size: 17, color: k.acc),
                    const SizedBox(width: 6),
                  ],
                  Text(label, style: FactifyText.sans(14.5, weight: FontWeight.w500, color: k.ink)),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// After the survey: the seal, and the free checks the account starts with.
class CreditsWelcomeScreen extends StatelessWidget {
  const CreditsWelcomeScreen({required this.services, super.key});

  final AppServices services;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final account = services.auth.account;
    final name = account?.name?.trim();
    // The balance the server reports; 100 is what a new account is given.
    final balance = account?.balance ?? 100;
    return Scaffold(
      backgroundColor: k.bg,
      body: SafeArea(
        child: CustomScrollView(
          slivers: [
            SliverFillRemaining(
              hasScrollBody: false,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(24, 16, 24, 22),
                child: Column(
                  children: [
                    const Spacer(),
                    const FactifyMark(size: 104),
                    const SizedBox(height: 28),
                    Semantics(
                      header: true,
                      child: Text(
                        name == null || name.isEmpty
                            ? l10n.creditsWelcomeTitle
                            : l10n.creditsTitleNamed(name),
                        textAlign: TextAlign.center,
                        style: FactifyText.serif(34, color: k.ink).copyWith(height: 1.05, letterSpacing: -1),
                      ),
                    ),
                    const SizedBox(height: 26),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(vertical: 22, horizontal: 20),
                      decoration: BoxDecoration(
                        color: k.accS,
                        borderRadius: BorderRadius.circular(24),
                      ),
                      child: Column(
                        children: [
                          Icon(FxIcons.gift, size: 26, color: k.acc),
                          const SizedBox(height: 6),
                          Text(
                            '$balance',
                            style: FactifyText.serif(56, weight: FontWeight.w600, color: k.acc)
                                .copyWith(height: 1),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            l10n.creditsLabel,
                            style: FactifyText.sans(14, weight: FontWeight.w600, color: k.acc),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      l10n.creditsBody,
                      textAlign: TextAlign.center,
                      style: FactifyText.sans(14, color: k.ink2).copyWith(height: 1.5),
                    ),
                    const Spacer(),
                    const SizedBox(height: 20),
                    FxButton(
                      label: l10n.creditsStart,
                      trailingIcon: FxIcons.forward,
                      height: 54,
                      radius: 18,
                      fontSize: 15,
                      onPressed: () => unawaited(
                        Navigator.of(context).pushAndRemoveUntil(
                          MaterialPageRoute<void>(builder: (_) => MainShell(services: services)),
                          (_) => false,
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
    );
  }
}
