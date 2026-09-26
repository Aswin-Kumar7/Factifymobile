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
            return SignInPanel(auth: auth);
          },
        ),
      ),
    );
  }
}

/// Sign in, or create an account: an email and a password, or Google. Used by the
/// welcome screen and the account screen alike; [showHeader] is off where the page
/// has its own heading.
class SignInPanel extends StatefulWidget {
  const SignInPanel({
    required this.auth,
    this.showHeader = true,
    this.padded = true,
    this.startInCreate = true,
    this.onModeChanged,
    super.key,
  });

  final AuthService auth;
  final bool showHeader;
  final bool padded;

  /// Whether the form opens on "Create account" rather than "Sign in".
  final bool startInCreate;

  /// Told when the person switches between signing in and creating an account.
  final ValueChanged<bool>? onModeChanged;

  @override
  State<SignInPanel> createState() => _SignInState();
}

class _SignInState extends State<SignInPanel> {
  final TextEditingController _name = TextEditingController();
  final TextEditingController _email = TextEditingController();
  final TextEditingController _password = TextEditingController();
  final TextEditingController _confirm = TextEditingController();

  /// "Next" on the password goes here, not to the show-password button beside it.
  final FocusNode _confirmFocus = FocusNode();
  late bool _creating = widget.startInCreate;
  bool _hidden = true;
  bool _busy = false;
  AuthProblem? _problem;
  bool _mismatch = false;

  @override
  void initState() {
    super.initState();
    widget.auth.addListener(_onAuth);
  }

  @override
  void dispose() {
    widget.auth.removeListener(_onAuth);
    _name.dispose();
    _email.dispose();
    _password.dispose();
    _confirm.dispose();
    _confirmFocus.dispose();
    super.dispose();
  }

  /// A Google sign-in that came back failed says so here.
  void _onAuth() {
    final problem = widget.auth.lastLinkProblem;
    if (mounted && problem != null && problem != _problem) setState(() => _problem = problem);
  }

  void _setMode(bool creating) {
    if (creating == _creating) return;
    setState(() {
      _creating = creating;
      _problem = null;
      _mismatch = false;
    });
    widget.onModeChanged?.call(creating);
  }

  Future<void> _run(Future<void> Function() step) async {
    FocusManager.instance.primaryFocus?.unfocus();
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

  void _submit() {
    final auth = widget.auth;
    if (_creating) {
      if (_password.text != _confirm.text) {
        setState(() => _mismatch = true);
        return;
      }
      setState(() => _mismatch = false);
      unawaited(
        _run(() => auth.register(email: _email.text, password: _password.text, name: _name.text)),
      );
    } else {
      unawaited(_run(() => auth.signIn(email: _email.text, password: _password.text)));
    }
  }

  String _describe(AppLocalizations l10n, AuthProblem problem) => switch (problem) {
    AuthProblem.invalidEmail => l10n.authInvalidEmail,
    AuthProblem.weakPassword => l10n.authWeakPassword(widget.auth.minPasswordLength),
    AuthProblem.emailTaken => l10n.authEmailTaken,
    AuthProblem.wrongCredentials => l10n.authWrongCredentials,
    AuthProblem.useGoogle => l10n.authUseGoogle,
    AuthProblem.googleFailed => l10n.authGoogleFailed,
    AuthProblem.googleUnavailable => l10n.authGoogleUnavailable,
    AuthProblem.tooMany => l10n.authTooMany,
    AuthProblem.network => l10n.authNetwork,
    AuthProblem.unavailable => l10n.signInUnavailable,
    AuthProblem.generic => l10n.authGeneric,
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final auth = widget.auth;
    final problem = _problem;
    final ready =
        _email.text.trim().isNotEmpty &&
        _password.text.isNotEmpty &&
        (!_creating || _confirm.text.isNotEmpty);

    InputDecoration field(String label, {IconData? icon, Widget? suffix, String? helper}) =>
        InputDecoration(
          labelText: label,
          helperText: helper,
          prefixIcon: icon == null ? null : Icon(icon),
          suffixIcon: suffix,
        );

    final visibility = IconButton(
      tooltip: _hidden ? l10n.showPassword : l10n.hidePassword,
      onPressed: () => setState(() => _hidden = !_hidden),
      icon: Icon(_hidden ? Icons.visibility_outlined : Icons.visibility_off_outlined),
    );

    return ListView(
      shrinkWrap: !widget.padded,
      physics: widget.padded ? null : const NeverScrollableScrollPhysics(),
      padding: widget.padded ? const EdgeInsets.fromLTRB(20, 12, 20, 28) : EdgeInsets.zero,
      children: [
        if (widget.showHeader) ...[
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
        ],
        if (!auth.available) ...[
          _Note(text: l10n.signInUnavailable),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: _busy ? null : () => _run(auth.reloadConfig),
            icon: const Icon(Icons.refresh_rounded),
            label: Text(l10n.retry),
          ),
        ] else ...[
          SegmentedButton<bool>(
            segments: [
              ButtonSegment(value: true, label: Text(l10n.modeCreateAccount)),
              ButtonSegment(value: false, label: Text(l10n.modeSignIn)),
            ],
            selected: {_creating},
            showSelectedIcon: false,
            onSelectionChanged: _busy ? null : (value) => _setMode(value.first),
          ),
          const SizedBox(height: 16),
          AutofillGroup(
            child: Column(
              children: [
                if (_creating) ...[
                  TextField(
                    controller: _name,
                    enabled: !_busy,
                    textCapitalization: TextCapitalization.words,
                    textInputAction: TextInputAction.next,
                    autofillHints: const [AutofillHints.name],
                    decoration: field(l10n.nameLabel, icon: Icons.person_outline_rounded),
                  ),
                  const SizedBox(height: 12),
                ],
                TextField(
                  controller: _email,
                  enabled: !_busy,
                  keyboardType: TextInputType.emailAddress,
                  textInputAction: TextInputAction.next,
                  autofillHints: const [AutofillHints.email],
                  onChanged: (_) => setState(() {}),
                  decoration: field(l10n.emailLabel, icon: Icons.mail_outline_rounded),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _password,
                  enabled: !_busy,
                  obscureText: _hidden,
                  textInputAction: _creating ? TextInputAction.next : TextInputAction.done,
                  autofillHints: [
                    if (_creating) AutofillHints.newPassword else AutofillHints.password,
                  ],
                  onChanged: (_) => setState(() {}),
                  onEditingComplete: _creating ? _confirmFocus.requestFocus : null,
                  onSubmitted: (_) {
                    if (!_creating && ready) _submit();
                  },
                  decoration: field(
                    l10n.passwordLabel,
                    icon: Icons.lock_outline_rounded,
                    suffix: visibility,
                    helper: _creating ? l10n.passwordHint(auth.minPasswordLength) : null,
                  ),
                ),
                if (_creating) ...[
                  const SizedBox(height: 12),
                  TextField(
                    controller: _confirm,
                    focusNode: _confirmFocus,
                    enabled: !_busy,
                    obscureText: _hidden,
                    textInputAction: TextInputAction.done,
                    autofillHints: const [AutofillHints.newPassword],
                    onChanged: (_) => setState(() => _mismatch = false),
                    onSubmitted: (_) {
                      if (ready) _submit();
                    },
                    decoration: field(
                      l10n.confirmPasswordLabel,
                      icon: Icons.lock_outline_rounded,
                    ).copyWith(errorText: _mismatch ? l10n.passwordsDontMatch : null),
                  ),
                ],
              ],
            ),
          ),
          if (problem != null) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: theme.colorScheme.errorContainer,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                children: [
                  Icon(Icons.error_outline_rounded, color: theme.colorScheme.error, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _describe(l10n, problem),
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onErrorContainer,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _busy || !ready ? null : _submit,
            child: _busy
                ? const SizedBox(
                    width: 22,
                    height: 22,
                    child: CircularProgressIndicator(strokeWidth: 2.4, color: Colors.white),
                  )
                : Text(_creating ? l10n.createAccountButton : l10n.signInButton),
          ),
          const SizedBox(height: 18),
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
          const SizedBox(height: 18),
          OutlinedButton.icon(
            onPressed: _busy || !auth.googleAvailable ? null : () => _run(auth.startGoogle),
            icon: const _GoogleG(),
            label: Text(l10n.continueWithGoogle),
            style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(50)),
          ),
          if (!auth.googleAvailable) ...[
            const SizedBox(height: 8),
            Text(
              l10n.authGoogleUnavailable,
              textAlign: TextAlign.center,
              style: theme.textTheme.bodySmall?.copyWith(color: FactifyColors.inkMuted),
            ),
          ],
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
          Center(child: AvatarCircle(name: account.displayName, size: 72)),
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
            : AvatarCircle(name: account.displayName, size: 30),
      );
    },
  );
}

/// A person's initial in an emerald circle.
class AvatarCircle extends StatelessWidget {
  const AvatarCircle({required this.name, required this.size, super.key});

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
