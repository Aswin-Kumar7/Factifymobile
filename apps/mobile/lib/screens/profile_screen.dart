/// The person, their credits, and the app's settings, on their own tab.
///
/// Signed in: who they are (name, email, how they signed in), the credits the server
/// holds for them, and their account details. As a guest: a way to sign in. For
/// everyone: the interface language, the checks saved on this phone, and sign out.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../app_services.dart';
import '../auth/auth_service.dart';
import '../l10n/app_localizations.dart';
import '../models/account.dart';
import '../theme/colors.dart';
import '../widgets/language_menu.dart';
import 'account_screen.dart';
import 'welcome_screen.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({required this.services, super.key});

  final AppServices services;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final auth = services.auth;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.profileTitle)),
      body: SafeArea(
        child: ListenableBuilder(
          listenable: auth,
          builder: (context, _) {
            final account = auth.account;
            return RefreshIndicator(
              onRefresh: () async => auth.refreshAccount(),
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
                children: [
                  if (auth.signedIn && account != null) ...[
                    _Header(auth: auth, account: account),
                    const SizedBox(height: 14),
                    _Credits(account: account),
                    const SizedBox(height: 14),
                    _Details(account: account),
                  ] else if (auth.signedIn)
                    const Padding(
                      padding: EdgeInsets.all(32),
                      child: Center(child: CircularProgressIndicator()),
                    )
                  else
                    _GuestCard(services: services),
                  const SizedBox(height: 14),
                  _Settings(services: services),
                  if (auth.signedIn) ...[
                    const SizedBox(height: 18),
                    OutlinedButton.icon(
                      onPressed: () => unawaited(auth.signOut()),
                      icon: const Icon(Icons.logout_rounded),
                      label: Text(l10n.signOut),
                      style: OutlinedButton.styleFrom(
                        minimumSize: const Size.fromHeight(50),
                        foregroundColor: Theme.of(context).colorScheme.error,
                      ),
                    ),
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

class _Header extends StatelessWidget {
  const _Header({required this.auth, required this.account});

  final AuthService auth;
  final Account account;

  Future<void> _rename(BuildContext context) async {
    final l10n = AppLocalizations.of(context);
    final controller = TextEditingController(text: account.name ?? '');
    final name = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(l10n.editName),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLength: 60,
          decoration: InputDecoration(labelText: l10n.nameLabel),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: Text(l10n.cancel)),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            style: FilledButton.styleFrom(minimumSize: const Size(0, 44)),
            child: Text(l10n.save),
          ),
        ],
      ),
    );
    controller.dispose();
    if (name != null && name.isNotEmpty) await auth.rename(name);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final method = auth.session?.method ?? 'email';
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [FactifyColors.emerald, FactifyColors.emeraldDeep],
        ),
        borderRadius: BorderRadius.circular(22),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(3),
            decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
            child: AvatarCircle(name: account.displayName, size: 64),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(
                      child: Text(
                        account.displayName,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 20,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ),
                    IconButton(
                      onPressed: () => unawaited(_rename(context)),
                      tooltip: l10n.editName,
                      visualDensity: VisualDensity.compact,
                      icon: const Icon(Icons.edit_outlined, size: 18, color: Colors.white),
                    ),
                  ],
                ),
                Text(
                  account.email,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.9)),
                ),
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.18),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        method == 'google'
                            ? Icons.g_mobiledata_rounded
                            : Icons.mail_outline_rounded,
                        size: 16,
                        color: Colors.white,
                      ),
                      const SizedBox(width: 4),
                      Flexible(
                        child: Text(
                          l10n.signedInWith(method),
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
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

class _Credits extends StatelessWidget {
  const _Credits({required this.account});

  final Account account;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    // Grants minus spend is the balance, so the total is the two together; a
    // balance below zero (possible while nothing is enforced) reads as fully used.
    final total = account.used + (account.balance > 0 ? account.balance : 0);
    final spent = total == 0 ? 0.0 : (account.used / total).clamp(0.0, 1.0);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.toll_rounded, color: FactifyColors.emeraldDark),
                const SizedBox(width: 8),
                Text(
                  l10n.creditsTitle,
                  style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Expanded(
                  child: Text(
                    l10n.creditsLeft(account.balance),
                    style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
                  ),
                ),
                Text(
                  l10n.creditsUsed(account.used),
                  style: theme.textTheme.labelMedium?.copyWith(color: FactifyColors.inkMuted),
                ),
              ],
            ),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(999),
              child: LinearProgressIndicator(
                value: 1 - spent,
                minHeight: 10,
                color: FactifyColors.emerald,
                backgroundColor: FactifyColors.emeraldTint,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              l10n.creditCosts(account.checkCost, account.deepCheckCost),
              style: theme.textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _Details extends StatelessWidget {
  const _Details({required this.account});

  final Account account;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final joined = account.joinedAt;
    return _Section(
      title: l10n.profileDetails,
      children: [
        _Row(
          icon: Icons.person_outline_rounded,
          label: l10n.profileName,
          value: account.displayName,
        ),
        _Row(icon: Icons.mail_outline_rounded, label: l10n.profileEmail, value: account.email),
        _Row(icon: Icons.workspace_premium_outlined, label: l10n.profilePlan, value: l10n.planBeta),
        _Row(
          icon: Icons.fact_check_outlined,
          label: l10n.tabHistory,
          value: l10n.checksSoFar(account.checks),
        ),
        if (joined != null)
          _Row(
            icon: Icons.calendar_today_outlined,
            label: l10n.profileJoined,
            value: MaterialLocalizations.of(context).formatMediumDate(joined.toLocal()),
          ),
      ],
    );
  }
}

class _GuestCard extends StatelessWidget {
  const _GuestCard({required this.services});

  final AppServices services;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            Container(
              width: 64,
              height: 64,
              decoration: const BoxDecoration(
                color: FactifyColors.emeraldTint,
                shape: BoxShape.circle,
              ),
              child: const Icon(
                Icons.person_outline_rounded,
                size: 34,
                color: FactifyColors.emeraldDark,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              l10n.guestTitle,
              textAlign: TextAlign.center,
              style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 6),
            Text(
              l10n.guestBody,
              textAlign: TextAlign.center,
              style: theme.textTheme.bodyMedium?.copyWith(color: FactifyColors.inkMuted),
            ),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: () => unawaited(
                Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => WelcomeScreen(services: services, fromProfile: true),
                  ),
                ),
              ),
              icon: const Icon(Icons.login_rounded),
              label: Text(l10n.signInOrCreate),
            ),
          ],
        ),
      ),
    );
  }
}

class _Settings extends StatelessWidget {
  const _Settings({required this.services});

  final AppServices services;

  Future<void> _clearHistory(BuildContext context) async {
    final l10n = AppLocalizations.of(context);
    final sure = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(l10n.historyClear),
        content: Text(l10n.historyClearConfirm),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: Text(l10n.cancel)),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(context).colorScheme.error,
              minimumSize: const Size(0, 44),
            ),
            child: Text(l10n.historyDelete),
          ),
        ],
      ),
    );
    if (sure ?? false) await services.history.clear();
  }

  void _about(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    unawaited(
      showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(l10n.aboutTitle),
          content: Text(l10n.aboutBody),
          actions: [
            FilledButton(
              onPressed: () => Navigator.pop(context),
              style: FilledButton.styleFrom(minimumSize: const Size(0, 44)),
              child: Text(l10n.done),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return _Section(
      title: l10n.settingsTitle,
      children: [
        ListTile(
          leading: const Icon(Icons.translate_rounded, color: FactifyColors.inkSoft),
          title: Text(l10n.settingLanguage),
          trailing: LanguageMenu(preference: services.language),
        ),
        ListenableBuilder(
          listenable: services.history,
          builder: (context, _) {
            final count = services.history.records.length;
            return ListTile(
              leading: const Icon(Icons.history_rounded, color: FactifyColors.inkSoft),
              title: Text(l10n.settingHistory),
              subtitle: Text(l10n.settingHistoryCount(count)),
              trailing: count == 0
                  ? null
                  : TextButton(
                      onPressed: () => unawaited(_clearHistory(context)),
                      child: Text(l10n.historyClear),
                    ),
            );
          },
        ),
        ListTile(
          leading: const Icon(Icons.info_outline_rounded, color: FactifyColors.inkSoft),
          title: Text(l10n.aboutTitle),
          trailing: const Icon(Icons.chevron_right_rounded),
          onTap: () => _about(context),
        ),
      ],
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(4, 4, 4, 8),
        child: Text(
          title,
          style: Theme.of(context).textTheme.labelLarge?.copyWith(
            color: FactifyColors.inkMuted,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      Card(
        clipBehavior: Clip.antiAlias,
        child: Column(children: children),
      ),
    ],
  );
}

class _Row extends StatelessWidget {
  const _Row({required this.icon, required this.label, required this.value});

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => ListTile(
    leading: Icon(icon, color: FactifyColors.inkSoft),
    title: Text(
      label,
      style: Theme.of(context).textTheme.bodySmall?.copyWith(color: FactifyColors.inkMuted),
    ),
    subtitle: Text(
      value,
      style: Theme.of(
        context,
      ).textTheme.bodyMedium?.copyWith(color: FactifyColors.ink, fontWeight: FontWeight.w600),
    ),
  );
}
