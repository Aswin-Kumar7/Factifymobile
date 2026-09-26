/// Your account: sign in, or see your profile and credits.
///
/// Every number here is the server's. The credits bar shows the balance `/v1/me`
/// returns; whether a check may run is decided by the server from its ledger, never
/// by this screen.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../auth/auth_service.dart';
import '../l10n/app_localizations.dart';
import '../models/account.dart';
import '../theme/colors.dart';

class AccountScreen extends StatelessWidget {
  const AccountScreen({super.key, required this.auth});

  final AuthService auth;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.account)),
      body: SafeArea(
        child: ListenableBuilder(
          listenable: auth,
          builder: (context, _) {
            final account = auth.account;
            if (auth.signedIn && account != null) {
              return _Profile(auth: auth, account: account);
            }
            if (auth.signedIn) return const Center(child: CircularProgressIndicator());
            return _SignIn(auth: auth);
          },
        ),
      ),
    );
  }
}

class _SignIn extends StatefulWidget {
  const _SignIn({required this.auth});

  final AuthService auth;

  @override
  State<_SignIn> createState() => _SignInState();
}

class _SignInState extends State<_SignIn> {
  final TextEditingController _email = TextEditingController();
  final TextEditingController _code = TextEditingController();
  bool _codeSent = false;
  bool _busy = false;
  AuthProblem? _problem;

  @override
  void dispose() {
    _email.dispose();
    _code.dispose();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() step) async {
    setState(() {
      _busy = true;
      _problem = null;
    });
    try {
      await step();
    } on AuthFailure catch (failure) {
      if (mounted) setState(() => _problem = failure.problem);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final auth = widget.auth;
    final problem = _problem;

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
      children: [
        const Center(child: _Mark()),
        const SizedBox(height: 16),
        Text(
          l10n.signInTitle,
          textAlign: TextAlign.center,
          style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 8),
        Text(
          l10n.signInBody,
          textAlign: TextAlign.center,
          style: theme.textTheme.bodyMedium?.copyWith(color: FactifyColors.inkMuted),
        ),
        const SizedBox(height: 24),
        if (!auth.available)
          _Note(text: l10n.signInUnavailable)
        else ...[
          TextField(
            controller: _email,
            enabled: !_codeSent && !_busy,
            keyboardType: TextInputType.emailAddress,
            autofillHints: const [AutofillHints.email],
            decoration: InputDecoration(
              labelText: l10n.emailLabel,
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          if (_codeSent) ...[
            Text(l10n.codeSentTo(_email.text.trim()), style: theme.textTheme.bodySmall),
            const SizedBox(height: 8),
            TextField(
              controller: _code,
              enabled: !_busy,
              keyboardType: TextInputType.number,
              maxLength: 6,
              autofillHints: const [AutofillHints.oneTimeCode],
              decoration: InputDecoration(
                labelText: l10n.codeLabel,
                border: const OutlineInputBorder(),
                counterText: '',
              ),
            ),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: _busy ? null : () => _run(() => auth.verifyCode(_email.text, _code.text)),
              style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48)),
              child: Text(l10n.verifyCode),
            ),
            TextButton(
              onPressed: _busy
                  ? null
                  : () => setState(() {
                      _codeSent = false;
                      _code.clear();
                    }),
              child: Text(l10n.useDifferentEmail),
            ),
          ] else
            FilledButton(
              onPressed: _busy
                  ? null
                  : () => _run(() async {
                      await auth.sendCode(_email.text);
                      if (mounted) setState(() => _codeSent = true);
                    }),
              style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48)),
              child: Text(l10n.sendCode),
            ),
          if (problem != null) ...[
            const SizedBox(height: 10),
            Text(switch (problem) {
              AuthProblem.wrongCode => l10n.authWrongCode,
              AuthProblem.network => l10n.authNetwork,
              AuthProblem.tooMany => l10n.authTooMany,
              AuthProblem.unavailable => l10n.signInUnavailable,
              AuthProblem.generic => l10n.authGeneric,
            }, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.error)),
          ],
          const SizedBox(height: 20),
          Row(
            children: [
              const Expanded(child: Divider()),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: Text(l10n.orDivider, style: theme.textTheme.labelMedium),
              ),
              const Expanded(child: Divider()),
            ],
          ),
          const SizedBox(height: 20),
          OutlinedButton.icon(
            onPressed: _busy ? null : () => _run(auth.startGoogle),
            icon: const _GoogleG(),
            label: Text(l10n.continueWithGoogle),
            style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(48)),
          ),
        ],
      ],
    );
  }
}

class _Profile extends StatelessWidget {
  const _Profile({required this.auth, required this.account});

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
            child: Text(l10n.save),
          ),
        ],
      ),
    );
    if (name != null && name.isNotEmpty) await auth.rename(name);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final joined = account.joinedAt;
    // How much of what this account has had is spent. Grants minus spend is the
    // balance, so the total is the two together; a balance below zero (possible
    // while nothing is enforced) reads as fully used.
    final total = account.used + (account.balance > 0 ? account.balance : 0);
    final spent = total == 0 ? 0.0 : (account.used / total).clamp(0.0, 1.0);

    return RefreshIndicator(
      onRefresh: auth.refreshAccount,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
        children: [
          Center(child: _Avatar(name: account.displayName, size: 72)),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Flexible(
                child: Text(
                  account.displayName,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
                ),
              ),
              IconButton(
                onPressed: () => unawaited(_rename(context)),
                icon: const Icon(Icons.edit_outlined, size: 18),
                tooltip: l10n.editName,
              ),
            ],
          ),
          Text(
            account.email,
            textAlign: TextAlign.center,
            style: theme.textTheme.bodyMedium?.copyWith(color: FactifyColors.inkMuted),
          ),
          const SizedBox(height: 10),
          Center(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
              decoration: BoxDecoration(
                color: FactifyColors.emeraldTint,
                borderRadius: BorderRadius.circular(999),
              ),
              child: Text(
                l10n.planBeta,
                style: const TextStyle(
                  color: FactifyColors.emeraldDeep,
                  fontWeight: FontWeight.w700,
                  fontSize: 12,
                ),
              ),
            ),
          ),
          const SizedBox(height: 24),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    l10n.creditsTitle,
                    style: theme.textTheme.labelLarge?.copyWith(
                      color: FactifyColors.inkMuted,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Expanded(
                        child: Text(
                          l10n.creditsLeft(account.balance),
                          style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
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
                  const SizedBox(height: 2),
                  Text(
                    l10n.checksSoFar(account.checks),
                    style: theme.textTheme.bodySmall?.copyWith(color: FactifyColors.inkMuted),
                  ),
                ],
              ),
            ),
          ),
          if (joined != null) ...[
            const SizedBox(height: 12),
            Text(
              l10n.memberSince(joined.toLocal()),
              textAlign: TextAlign.center,
              style: theme.textTheme.labelMedium?.copyWith(color: FactifyColors.inkMuted),
            ),
          ],
          const SizedBox(height: 24),
          OutlinedButton.icon(
            onPressed: () => unawaited(auth.signOut()),
            icon: const Icon(Icons.logout_rounded, size: 18),
            label: Text(l10n.signOut),
            style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(48)),
          ),
        ],
      ),
    );
  }
}

/// The person's initial on an emerald disc. Also the account button on the home bar.
class AccountAvatar extends StatelessWidget {
  const AccountAvatar({super.key, required this.auth, required this.onTap});

  final AuthService auth;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: auth,
    builder: (context, _) {
      final account = auth.account;
      return IconButton(
        onPressed: onTap,
        tooltip: AppLocalizations.of(context).account,
        icon: account == null
            ? const Icon(Icons.account_circle_outlined, color: FactifyColors.inkMuted)
            : _Avatar(name: account.displayName, size: 30),
      );
    },
  );
}

class _Avatar extends StatelessWidget {
  const _Avatar({required this.name, required this.size});

  final String name;
  final double size;

  @override
  Widget build(BuildContext context) => Container(
    width: size,
    height: size,
    alignment: Alignment.center,
    decoration: const BoxDecoration(color: FactifyColors.emerald, shape: BoxShape.circle),
    child: Text(
      name.isEmpty ? '?' : name.characters.first.toUpperCase(),
      style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: size * 0.42),
    ),
  );
}

class _Mark extends StatelessWidget {
  const _Mark();

  @override
  Widget build(BuildContext context) => Container(
    width: 64,
    height: 64,
    decoration: BoxDecoration(
      color: FactifyColors.emerald,
      borderRadius: BorderRadius.circular(18),
    ),
    child: const Icon(Icons.fact_check_outlined, color: Colors.white, size: 34),
  );
}

/// Google's "G", drawn as text rather than shipped as a brand asset.
class _GoogleG extends StatelessWidget {
  const _GoogleG();

  @override
  Widget build(BuildContext context) => const Text(
    'G',
    style: TextStyle(fontWeight: FontWeight.w900, fontSize: 18, color: Color(0xFF4285F4)),
  );
}

class _Note extends StatelessWidget {
  const _Note({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(color: FactifyColors.ground, borderRadius: BorderRadius.circular(14)),
    child: Text(text, style: Theme.of(context).textTheme.bodyMedium),
  );
}
