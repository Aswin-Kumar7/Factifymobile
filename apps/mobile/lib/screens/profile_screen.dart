/// The person, their credits, and the app's settings, on their own tab (v5, 2.10).
///
/// Signed in: who they are (name, email, how they signed in), the credits the server
/// holds for them, and how long they have been here. As a guest: a way to sign in.
/// For everyone: the interface language, dark mode, whether a check that runs long
/// tells them when it is ready, the checks saved on this phone, whether the service
/// can be reached, the privacy policy, sign out, and deleting the account.
///
/// Every number about the account is the server's: the balance shown is the one
/// `/v1/me` returns, and whether a check may run is decided there, never here.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/client.dart';
import '../app_services.dart';
import '../auth/auth_service.dart';
import '../l10n/app_localizations.dart';
import '../l10n/phrases.dart';
import '../models/account.dart';
import '../theme/icons.dart';
import '../theme/tokens.dart';
import '../theme/typography.dart';
import '../widgets/brand.dart';
import '../widgets/person_avatar.dart';
import '../widgets/ui/fx_button.dart';
import '../widgets/ui/fx_card.dart';
import '../widgets/ui/fx_sheet.dart';
import '../widgets/ui/fx_switch.dart';
import 'payment_screen.dart';
import 'welcome_screen.dart';

/// Endonyms, deliberately outside the ARB files: each language reads the same in
/// every interface language, so someone looking for Hindi finds "हिन्दी".
const Map<String, String> _languageNames = {'en': 'English', 'hi': 'हिन्दी'};

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({required this.services, this.onOpenHistory, super.key});

  final AppServices services;

  /// "Saved checks" opens the History tab.
  final VoidCallback? onOpenHistory;

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  /// Whether the service answered: null while asking.
  bool? _online;

  /// Signed in, but the account could not be read: said, with "try again", rather
  /// than a spinner that never stops.
  bool _accountFailed = false;

  /// What each kind of check costs, from the server's price list; null until it
  /// answers, or when it cannot. `/v1/me` says only what an ordinary check costs.
  Map<String, int>? _costs;

  /// Deleting the account, between the second confirmation and the server's answer.
  bool _deleting = false;

  AppServices get _services => widget.services;

  @override
  void initState() {
    super.initState();
    unawaited(_probe());
    unawaited(_loadAccount());
    unawaited(_loadCosts());
  }

  Future<void> _loadCosts() async {
    try {
      final costs = await _services.client.checkCosts();
      if (mounted && costs.isNotEmpty) setState(() => _costs = costs);
    } on ApiFailure {
      // Without the price list the card says what an ordinary check costs, and no more.
    }
  }

  void _openPrivacy() =>
      unawaited(launchUrl(_services.client.privacyPolicy, mode: LaunchMode.externalApplication));

  /// Two steps: what deleting removes, then a last "for good". Only then is the
  /// server asked; on success the history kept on this phone is cleared and the
  /// app returns to the welcome screen (the shell follows the sign-out).
  Future<void> _deleteAccount(Account account) async {
    final l10n = AppLocalizations.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final first = await showFxSheet<bool>(context, builder: (_) => const _DeleteSheet());
    if (first != true || !mounted) return;
    final sure = await showDialog<bool>(
      context: context,
      builder: (context) {
        final k = FactifyTokens.of(context);
        return AlertDialog(
          title: Text(l10n.deleteAccountConfirmTitle),
          content: Text(l10n.deleteAccountConfirmBody(account.email)),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: Text(l10n.cancel)),
            TextButton(
              onPressed: () => Navigator.pop(context, true),
              style: TextButton.styleFrom(foregroundColor: k.fC),
              child: Text(l10n.deleteAccountConfirm),
            ),
          ],
        );
      },
    );
    if (sure != true || !mounted) return;
    setState(() => _deleting = true);
    final history = _services.history;
    try {
      await _services.auth.deleteAccount();
    } on ApiFailure catch (failure) {
      // 409 carries the server's own sentence naming the organisations to hand over.
      final detail = failure.detail;
      final reason = failure.kind == FailureKind.conflict && detail != null && detail.isNotEmpty
          ? detail
          : l10n.describeFailure(failure);
      messenger.showSnackBar(SnackBar(content: Text(l10n.deleteAccountFailed(reason))));
      if (mounted) setState(() => _deleting = false);
      return;
    }
    await history.clear();
    messenger.showSnackBar(SnackBar(content: Text(l10n.deleteAccountDone)));
    if (mounted) setState(() => _deleting = false);
  }

  Future<void> _loadAccount() async {
    final auth = _services.auth;
    if (!auth.signedIn || auth.account != null) return;
    if (mounted) setState(() => _accountFailed = false);
    final account = await auth.refreshAccount();
    if (mounted && auth.signedIn && account == null) setState(() => _accountFailed = true);
  }

  Future<void> _probe() async {
    if (mounted) setState(() => _online = null);
    final ready = await _services.client.ready();
    if (mounted) setState(() => _online = ready);
  }

  Future<void> _refresh() async {
    await Future.wait([_loadAccount(), _services.auth.refreshAccount(), _probe()]);
  }

  Future<void> _notify(bool on) async {
    final l10n = AppLocalizations.of(context);
    final messenger = ScaffoldMessenger.of(context);
    // Asked for once, when the person turns it on - never at launch.
    if (on && !await _services.notifier.askPermission()) {
      messenger.showSnackBar(SnackBar(content: Text(l10n.notifyDenied)));
      return;
    }
    await _services.notifyByDefault.choose(on);
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final auth = _services.auth;
    return Scaffold(
      backgroundColor: k.bg,
      body: SafeArea(
        child: ListenableBuilder(
          listenable: Listenable.merge([
            auth,
            _services.history,
            _services.language,
            _services.themeMode,
            _services.notifyByDefault,
            _services.quickVerdict,
            _services.bubble,
          ]),
          builder: (context, _) {
            final account = auth.account;
            return RefreshIndicator(
              color: k.acc,
              onRefresh: _refresh,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                children: [
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    child: Semantics(
                      header: true,
                      child: Text(
                        l10n.profileTitle,
                        style: FactifyText.serif(
                          35,
                          color: k.ink,
                        ).copyWith(letterSpacing: -1.1, height: 1.1),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  if (auth.signedIn && account != null) ...[
                    _Identity(auth: auth, account: account),
                    const SizedBox(height: 10),
                    _Credits(
                      account: account,
                      videoCost: account.videoCheckCost ?? _costs?['video'],
                      onBuy: () async {
                        await Navigator.of(context).push(
                          MaterialPageRoute<bool>(
                            builder: (_) => PaymentScreen(
                              services: _services,
                              // With plans on the server, the button chooses a plan.
                              plans: account.planUsage != null,
                            ),
                          ),
                        );
                        unawaited(auth.refreshAccount());
                      },
                    ),
                    const SizedBox(height: 10),
                    _Stats(account: account),
                  ] else if (auth.signedIn && _accountFailed)
                    FxCard(
                      radius: 22,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text(l10n.profileLoadFailed, style: FactifyText.sans(14, color: k.ink2)),
                          const SizedBox(height: 12),
                          FxButton(
                            label: l10n.tryAgain,
                            icon: FxIcons.retry,
                            variant: FxButtonVariant.outline,
                            height: 46,
                            fontSize: 14,
                            onPressed: () => unawaited(_loadAccount()),
                          ),
                        ],
                      ),
                    )
                  else if (auth.signedIn)
                    Padding(
                      padding: const EdgeInsets.all(32),
                      child: Center(child: CircularProgressIndicator(color: k.acc)),
                    )
                  else
                    _Guest(services: _services),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(6, 20, 6, 8),
                    child: Text(
                      l10n.settingsTitle,
                      style: FactifyText.sans(13, weight: FontWeight.w600, color: k.ink),
                    ),
                  ),
                  _Settings(
                    services: _services,
                    online: _online,
                    onProbe: () => unawaited(_probe()),
                    onNotify: (on) => unawaited(_notify(on)),
                    onOpenHistory: widget.onOpenHistory,
                    onOpenPrivacy: _openPrivacy,
                  ),
                  const SizedBox(height: 10),
                  FxCard(
                    radius: 22,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(l10n.aboutTitle, style: FactifyText.serif(18, color: k.ink)),
                        const SizedBox(height: 4),
                        Text(
                          l10n.aboutBody,
                          style: FactifyText.sans(12.5, color: k.ink2).copyWith(height: 1.5),
                        ),
                      ],
                    ),
                  ),
                  if (auth.signedIn) ...[
                    const SizedBox(height: 12),
                    FxButton(
                      label: l10n.signOut,
                      icon: FxIcons.signOut,
                      variant: FxButtonVariant.outline,
                      foreground: k.fC,
                      onPressed: () => unawaited(auth.signOut()),
                      height: 50,
                      radius: 18,
                      fontSize: 14,
                    ),
                    if (account != null) ...[
                      const SizedBox(height: 4),
                      FxButton(
                        label: _deleting ? l10n.deleteAccountDeleting : l10n.deleteAccount,
                        icon: FxIcons.trash,
                        variant: FxButtonVariant.ghost,
                        foreground: k.fC,
                        onPressed: _deleting ? null : () => unawaited(_deleteAccount(account)),
                        height: 46,
                        radius: 18,
                        fontSize: 13.5,
                      ),
                    ],
                  ],
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

/// The first letter of a name, on the accent colour.
class _Initial extends StatelessWidget {
  const _Initial({required this.name, required this.size});

  final String name;
  final double size;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: k.acc, shape: BoxShape.circle),
      child: Text(
        name.isEmpty ? '?' : name.characters.first.toUpperCase(),
        style: FactifyText.serif(size * 0.45, color: k.onAcc).copyWith(height: 1),
      ),
    );
  }
}

class _Identity extends StatelessWidget {
  const _Identity({required this.auth, required this.account});

  final AuthService auth;
  final Account account;

  Future<void> _rename(BuildContext context) async {
    final name = await showFxSheet<String>(
      context,
      builder: (context) => _RenameSheet(current: account.name ?? ''),
    );
    if (name != null && name.isNotEmpty) await auth.rename(name);
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final method = auth.session?.method ?? 'email';
    return FxCard(
      radius: 22,
      child: Row(
        children: [
          PersonAvatar(
            url: account.avatarUrl,
            size: 58,
            fallback: _Initial(name: account.displayName, size: 58),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  account.displayName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: FactifyText.sans(17, weight: FontWeight.w600, color: k.ink),
                ),
                const SizedBox(height: 1),
                Text(
                  account.email,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: FactifyText.sans(12.5, color: k.ink3),
                ),
                const SizedBox(height: 6),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(color: k.sf2, borderRadius: BorderRadius.circular(8)),
                  child: Text(
                    l10n.signedInWith(method),
                    style: FactifyText.sans(11, weight: FontWeight.w600, color: k.ink2),
                  ),
                ),
              ],
            ),
          ),
          IconButton(
            tooltip: l10n.editName,
            onPressed: () => unawaited(_rename(context)),
            icon: Icon(FxIcons.edit, size: 20, color: k.ink3),
          ),
        ],
      ),
    );
  }
}

class _RenameSheet extends StatefulWidget {
  const _RenameSheet({required this.current});

  final String current;

  @override
  State<_RenameSheet> createState() => _RenameSheetState();
}

class _RenameSheetState extends State<_RenameSheet> {
  late final TextEditingController _name = TextEditingController(text: widget.current);

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(l10n.editName, style: FactifyText.serif(22, color: k.ink)),
          const SizedBox(height: 14),
          TextField(
            controller: _name,
            autofocus: true,
            maxLength: 60,
            textCapitalization: TextCapitalization.words,
            decoration: InputDecoration(labelText: l10n.nameLabel),
            onSubmitted: (value) => Navigator.pop(context, value.trim()),
          ),
          const SizedBox(height: 8),
          FxButton(label: l10n.save, onPressed: () => Navigator.pop(context, _name.text.trim())),
        ],
      ),
    );
  }
}

class _Credits extends StatelessWidget {
  const _Credits({required this.account, required this.onBuy, this.videoCost});

  final Account account;

  /// What a video costs, when the server has said; a video costs more than a check.
  final int? videoCost;

  /// Opens the browser to buy credits (payment_screen.dart).
  final VoidCallback onBuy;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    // The checks left this month: the plan's, plus any credits (the server's sum).
    // A balance below zero (possible while nothing is enforced) reads as none left.
    final balance = account.balance > 0 ? account.balance : 0;
    final plan = account.planUsage;
    final double left;
    if (plan != null) {
      // The bar is the plan's month: what is left of its checks.
      left = plan.allowance == 0 ? 0.0 : (plan.left / plan.allowance).clamp(0.0, 1.0);
    } else {
      // Before plans, grants minus spend was the balance, so the total is the two.
      final total = account.used + balance;
      left = total == 0 ? 1.0 : (balance / total).clamp(0.0, 1.0);
    }
    final locale = Localizations.localeOf(context).toLanguageTag();
    final resets = plan?.resetsAt == null ? null : DateFormat.MMMd(locale).format(plan!.resetsAt!);
    // A paid plan's period: one paid for once ends on its date (it does not renew by
    // itself); only one the server says renews is called renewing.
    final periodEnd = plan == null || !plan.paid || plan.renewsAt == null
        ? null
        : DateFormat.yMMMd(locale).format(plan.renewsAt!);
    final money = NumberFormat.currency(locale: locale, symbol: '₹', decimalDigits: 0);
    String rupees(int paise) => money.format(paise / 100);
    final video = videoCost;
    final costs = video == null || video == account.checkCost
        ? l10n.creditCosts(account.checkCost)
        : l10n.creditCostsVideo(account.checkCost, video);
    // Notes under the numbers, each a full sentence on its own line.
    final notes = <String>[
      if (plan != null && plan.paid && plan.extraBlocked)
        l10n.planExtraBlocked
      else if (plan != null && plan.paid && plan.extraEnabled)
        plan.extraCapPaise == null
            ? l10n.planExtraUncapped(rupees(plan.extraPricePaise), rupees(plan.extraUsedPaise))
            : l10n.planExtraCapped(
                rupees(plan.extraPricePaise),
                rupees(plan.extraUsedPaise),
                rupees(plan.extraCapPaise!),
              ),
      // While nothing is enforced, the server refuses no check: said plainly, rather
      // than a count that reads like a wall.
      if (!account.limited) plan == null ? l10n.creditsPreviewNote : l10n.planPreviewNote,
    ];
    final ink = k.heroInk;
    final ring = Colors.white.withValues(alpha: 0.1);

    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(color: k.hero, borderRadius: BorderRadius.circular(24)),
      child: Stack(
        children: [
          // Two faint rings in the corner, as on the design's credits card.
          Positioned(right: -40, top: -40, child: _Ring(size: 150, colour: ring)),
          Positioned(right: -10, top: -10, child: _Ring(size: 90, colour: ring)),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        plan == null ? l10n.creditsTitle : l10n.planChecksTitle,
                        style: FactifyText.sans(12, color: ink.withValues(alpha: 0.75)),
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(9),
                      ),
                      child: Text(
                        plan == null ? l10n.planBetaShort : l10n.planName(plan.name),
                        style: FactifyText.sans(11, weight: FontWeight.w600, color: ink),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                Semantics(
                  // The clamped balance, as shown: TalkBack read "-106 credits left"
                  // while the screen said 0 (2026-09-29).
                  label: plan == null ? l10n.creditsLeft(balance) : l10n.planChecksLeft(balance),
                  excludeSemantics: true,
                  child: Wrap(
                    crossAxisAlignment: WrapCrossAlignment.end,
                    spacing: 6,
                    children: [
                      Text(
                        '$balance',
                        style: FactifyText.serif(
                          44,
                          weight: FontWeight.w400,
                          color: ink,
                        ).copyWith(height: 1, letterSpacing: -1),
                      ),
                      Padding(
                        padding: const EdgeInsets.only(bottom: 4),
                        child: Text(
                          plan == null
                              ? l10n.profileCreditsLabel(balance)
                              : l10n.planChecksLabel(balance),
                          style: FactifyText.sans(13, color: ink.withValues(alpha: 0.8)),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                ClipRRect(
                  borderRadius: BorderRadius.circular(3),
                  child: SizedBox(
                    height: 6,
                    child: Stack(
                      children: [
                        Positioned.fill(
                          child: ColoredBox(color: Colors.white.withValues(alpha: 0.14)),
                        ),
                        FractionallySizedBox(
                          widthFactor: left,
                          heightFactor: 1,
                          child: ColoredBox(color: k.acc),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                DefaultTextStyle(
                  style: FactifyText.sans(11.5, color: ink.withValues(alpha: 0.75)),
                  child: Wrap(
                    alignment: WrapAlignment.spaceBetween,
                    spacing: 12,
                    runSpacing: 2,
                    children: plan == null
                        ? [Text(l10n.creditsUsed(account.used)), Text(costs)]
                        : [
                            Text(l10n.planUsed(plan.used, plan.allowance)),
                            if (resets != null) Text(l10n.planResets(resets)),
                            if (periodEnd != null)
                              Text(
                                plan.cancelAtEnd
                                    ? l10n.planEnds(periodEnd)
                                    : l10n.planRenews(periodEnd),
                              ),
                            if (plan.credits > 0) Text(l10n.planCredits(plan.credits)),
                            if (video != null && video != account.checkCost)
                              Text(l10n.planVideoCost(video)),
                          ],
                  ),
                ),
                for (final note in notes) ...[
                  const SizedBox(height: 6),
                  Text(
                    note,
                    style: FactifyText.sans(
                      11.5,
                      color: ink.withValues(alpha: 0.85),
                    ).copyWith(height: 1.4),
                  ),
                ],
                const SizedBox(height: 14),
                Material(
                  color: Colors.white,
                  shape: const StadiumBorder(),
                  clipBehavior: Clip.antiAlias,
                  child: InkWell(
                    onTap: onBuy,
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(minHeight: 46),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(FxIcons.openExternal, size: 18, color: FactifyBrand.emerald),
                            const SizedBox(width: 8),
                            Flexible(
                              child: Text(
                                plan == null
                                    ? l10n.buyCredits
                                    : (plan.paid ? l10n.changePlan : l10n.upgradePlan),
                                style: FactifyText.sans(
                                  14.5,
                                  weight: FontWeight.w700,
                                  color: FactifyBrand.emerald,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Ring extends StatelessWidget {
  const _Ring({required this.size, required this.colour});

  final double size;
  final Color colour;

  @override
  Widget build(BuildContext context) => Container(
    width: size,
    height: size,
    decoration: BoxDecoration(
      shape: BoxShape.circle,
      border: Border.all(color: colour),
    ),
  );
}

class _Stats extends StatelessWidget {
  const _Stats({required this.account});

  final Account account;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final joined = account.joinedAt?.toLocal();
    final since = joined == null
        ? '—'
        : '${DateFormat('MMM', l10n.localeName).format(joined)} ’${DateFormat('yy').format(joined)}';
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: _Stat(value: '${account.checks}', label: l10n.profileChecksLabel(account.checks)),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: _Stat(value: since, label: l10n.profileJoined),
        ),
      ],
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.value, required this.label});

  final String value;
  final String label;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return FxCard(
      child: Semantics(
        label: '$value, $label',
        excludeSemantics: true,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              value,
              style: FactifyText.serif(26, weight: FontWeight.w400, color: k.ink),
            ),
            const SizedBox(height: 4),
            Text(label, style: FactifyText.sans(12, color: k.ink3)),
          ],
        ),
      ),
    );
  }
}

class _Guest extends StatelessWidget {
  const _Guest({required this.services});

  final AppServices services;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    return FxCard(
      radius: 22,
      padding: const EdgeInsets.all(18),
      child: Column(
        children: [
          Container(
            width: 58,
            height: 58,
            decoration: BoxDecoration(color: k.accS, shape: BoxShape.circle),
            child: Icon(FxIcons.person, size: 28, color: k.acc),
          ),
          const SizedBox(height: 12),
          Text(
            l10n.guestTitle,
            textAlign: TextAlign.center,
            style: FactifyText.serif(20, color: k.ink),
          ),
          const SizedBox(height: 6),
          Text(
            l10n.guestBody,
            textAlign: TextAlign.center,
            style: FactifyText.sans(13.5, color: k.ink2),
          ),
          const SizedBox(height: 14),
          FxButton(
            label: l10n.signInOrCreate,
            height: 50,
            fontSize: 14.5,
            onPressed: () => unawaited(
              Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => WelcomeScreen(services: services, fromProfile: true),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Settings extends StatelessWidget {
  const _Settings({
    required this.services,
    required this.online,
    required this.onProbe,
    required this.onNotify,
    required this.onOpenHistory,
    required this.onOpenPrivacy,
  });

  final AppServices services;
  final bool? online;
  final VoidCallback onProbe;
  final ValueChanged<bool> onNotify;
  final VoidCallback? onOpenHistory;

  /// Opens the privacy policy in the browser.
  final VoidCallback onOpenPrivacy;

  void _chooseLanguage(BuildContext context) {
    final chosen = services.language.value?.languageCode;
    unawaited(
      showFxSheet<void>(
        context,
        builder: (context) {
          final l10n = AppLocalizations.of(context);
          return _Choices(
            title: l10n.settingLanguage,
            options: [
              (l10n.languagePhone, chosen == null, () => services.language.choose(null)),
              for (final locale in AppLocalizations.supportedLocales)
                (
                  _languageNames[locale.languageCode] ?? locale.languageCode,
                  chosen == locale.languageCode,
                  () => services.language.choose(locale),
                ),
            ],
          );
        },
      ),
    );
  }

  void _chooseTheme(BuildContext context) {
    final mode = services.themeMode.value;
    unawaited(
      showFxSheet<void>(
        context,
        builder: (context) {
          final l10n = AppLocalizations.of(context);
          return _Choices(
            title: l10n.settingDarkMode,
            body: l10n.themeBody,
            options: [
              for (final (option, label) in [
                (ThemeMode.system, l10n.themePhone),
                (ThemeMode.light, l10n.themeLight),
                (ThemeMode.dark, l10n.themeDark),
              ])
                (label, mode == option, () => services.themeMode.choose(option)),
            ],
          );
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final chosen = services.language.value?.languageCode;
    final language = chosen == null ? l10n.languagePhone : _languageNames[chosen] ?? chosen;
    final mode = services.themeMode.value;
    // What is on screen: "same as the phone" on a dark phone is dark.
    final dark = Theme.of(context).brightness == Brightness.dark;
    final count = services.history.records.length;
    final (dot, status) = switch (online) {
      true => (k.tC, l10n.statusOnline),
      false => (k.fC, l10n.statusOffline),
      null => (k.ink3, l10n.statusChecking),
    };

    return FxCard(
      radius: 22,
      padding: EdgeInsets.zero,
      clip: true,
      child: Column(
        children: [
          _Row(
            icon: FxIcons.language,
            title: l10n.settingLanguage,
            trailing: _Value(language),
            onTap: () => _chooseLanguage(context),
            first: true,
          ),
          _Row(
            icon: FxIcons.moon,
            title: l10n.settingDarkMode,
            subtitle: mode == ThemeMode.system ? l10n.settingDarkFollowsPhone : null,
            // The row opens the three choices; the switch flips light and dark.
            onTap: () => _chooseTheme(context),
            trailing: FxSwitch(
              value: dark,
              label: l10n.settingDarkMode,
              onChanged: (on) =>
                  unawaited(services.themeMode.choose(on ? ThemeMode.dark : ThemeMode.light)),
            ),
          ),
          _Row(
            icon: FxIcons.bell,
            title: l10n.settingNotify,
            subtitle: l10n.settingNotifyBody,
            onTap: () => onNotify(!services.notifyByDefault.value),
            trailing: FxSwitch(
              value: services.notifyByDefault.value,
              label: l10n.settingNotify,
              onChanged: onNotify,
            ),
          ),
          _Row(
            icon: FxIcons.chat,
            title: l10n.settingQuick,
            subtitle: l10n.settingQuickBody,
            onTap: () => unawaited(services.quickVerdict.choose(!services.quickVerdict.value)),
            trailing: FxSwitch(
              value: services.quickVerdict.value,
              label: l10n.settingQuick,
              onChanged: (on) => unawaited(services.quickVerdict.choose(on)),
            ),
          ),
          _Row(
            icon: FxIcons.paste,
            title: l10n.settingBubble,
            subtitle: l10n.settingBubbleBody,
            onTap: () => unawaited(services.bubble.choose(!services.bubble.on)),
            trailing: FxSwitch(
              value: services.bubble.on,
              label: l10n.settingBubble,
              onChanged: (on) => unawaited(services.bubble.choose(on)),
            ),
          ),
          _Row(
            icon: FxIcons.history,
            title: l10n.settingHistory,
            trailing: _Value(l10n.settingSavedShort(count)),
            onTap: onOpenHistory,
          ),
          _Row(
            icon: FxIcons.service,
            title: l10n.settingService,
            onTap: onProbe,
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 7,
                  height: 7,
                  decoration: BoxDecoration(color: dot, shape: BoxShape.circle),
                ),
                const SizedBox(width: 6),
                Text(
                  status,
                  style: FactifyText.sans(13, weight: FontWeight.w600, color: dot),
                ),
              ],
            ),
          ),
          _Row(
            icon: FxIcons.privacy,
            title: l10n.privacyPolicy,
            onTap: onOpenPrivacy,
            trailing: Icon(FxIcons.openExternal, size: 18, color: k.ink3),
          ),
        ],
      ),
    );
  }
}

/// A current value and the chevron that says it opens.
class _Value extends StatelessWidget {
  const _Value(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        // Held to a width so a long value never squeezes the row's title.
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 140),
          child: Text(
            text,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: FactifyText.sans(13, color: k.ink3),
          ),
        ),
        Icon(FxIcons.chevron, size: 18, color: k.ink3),
      ],
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({
    required this.icon,
    required this.title,
    required this.trailing,
    this.subtitle,
    this.onTap,
    this.first = false,
  });

  /// The first row has no rule above it.
  final bool first;
  final IconData icon;
  final String title;
  final String? subtitle;
  final Widget trailing;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final subtitle = this.subtitle;
    return InkWell(
      onTap: onTap,
      child: Container(
        constraints: const BoxConstraints(minHeight: 58),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          border: first ? null : Border(top: BorderSide(color: k.line)),
        ),
        child: Row(
          children: [
            Container(
              width: 34,
              height: 34,
              decoration: BoxDecoration(color: k.sf2, borderRadius: BorderRadius.circular(11)),
              child: Icon(icon, size: 18, color: k.ink),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: FactifyText.sans(14, weight: FontWeight.w500, color: k.ink),
                  ),
                  if (subtitle != null) ...[
                    const SizedBox(height: 1),
                    Text(subtitle, style: FactifyText.sans(11.5, color: k.ink3)),
                  ],
                ],
              ),
            ),
            const SizedBox(width: 8),
            trailing,
          ],
        ),
      ),
    );
  }
}

/// A short list of choices in a sheet, the chosen one ticked.
class _Choices extends StatelessWidget {
  const _Choices({required this.title, required this.options, this.body});

  final String title;
  final String? body;
  final List<(String, bool, Future<void> Function())> options;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final body = this.body;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(title, style: FactifyText.serif(22, color: k.ink)),
        if (body != null) ...[
          const SizedBox(height: 6),
          Text(body, style: FactifyText.sans(13.5, color: k.ink2).copyWith(height: 1.45)),
        ],
        const SizedBox(height: 12),
        for (final (label, chosen, choose) in options)
          Semantics(
            selected: chosen,
            button: true,
            child: InkWell(
              borderRadius: BorderRadius.circular(14),
              onTap: () {
                unawaited(choose());
                Navigator.pop(context);
              },
              child: Container(
                height: 52,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                decoration: BoxDecoration(
                  color: chosen ? k.accS : null,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        label,
                        style: FactifyText.sans(
                          15,
                          weight: chosen ? FontWeight.w600 : FontWeight.w400,
                          color: k.ink,
                        ),
                      ),
                    ),
                    if (chosen) Icon(Icons.check_rounded, size: 20, color: k.acc),
                  ],
                ),
              ),
            ),
          ),
      ],
    );
  }
}

/// The first of the two steps: what deleting the account removes.
class _DeleteSheet extends StatelessWidget {
  const _DeleteSheet();

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(l10n.deleteAccountTitle, style: FactifyText.serif(22, color: k.ink)),
        const SizedBox(height: 8),
        Text(
          l10n.deleteAccountBody,
          style: FactifyText.sans(13.5, color: k.ink2).copyWith(height: 1.45),
        ),
        const SizedBox(height: 18),
        FxButton(
          label: l10n.deleteAccountContinue,
          icon: FxIcons.trash,
          variant: FxButtonVariant.outline,
          foreground: k.fC,
          height: 50,
          fontSize: 14.5,
          onPressed: () => Navigator.pop(context, true),
        ),
        const SizedBox(height: 8),
        FxButton(
          label: l10n.cancel,
          variant: FxButtonVariant.ghost,
          height: 46,
          fontSize: 14,
          onPressed: () => Navigator.pop(context, false),
        ),
      ],
    );
  }
}
