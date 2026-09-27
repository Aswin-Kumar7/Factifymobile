/// Create an account or sign in (v5, 2.1, third welcome page).
///
/// An email and a password, or Google. Creating an account asks for the password
/// twice and nothing else: a name is optional and can be added later from Profile,
/// so the first thing a new person meets is not a form longer than it needs to be.
///
/// The server's own sign-in (`lib/auth/auth_service.dart`). Every refusal it sends
/// is shown in the reader's language; nothing is decided here but whether the two
/// passwords match, which is checked before anything is sent.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../auth/auth_service.dart';
import '../l10n/app_localizations.dart';
import '../theme/icons.dart';
import '../theme/tokens.dart';
import '../theme/typography.dart';
import 'ui/fx_button.dart';
import 'ui/fx_segmented.dart';

class AuthForm extends StatefulWidget {
  const AuthForm({required this.auth, this.onModeChanged, super.key});

  final AuthService auth;

  /// Told when the person switches between creating an account and signing in.
  final ValueChanged<bool>? onModeChanged;

  @override
  State<AuthForm> createState() => _AuthFormState();
}

class _AuthFormState extends State<AuthForm> {
  final TextEditingController _email = TextEditingController();
  final TextEditingController _password = TextEditingController();
  final TextEditingController _confirm = TextEditingController();

  /// "Next" on the password goes here, not to the show-password button beside it.
  final FocusNode _confirmFocus = FocusNode();
  bool _creating = true;
  bool _hidden = true;
  bool _busy = false;
  AuthProblem? _problem;
  bool _mismatch = false;

  AuthService get _auth => widget.auth;

  @override
  void initState() {
    super.initState();
    _auth.addListener(_onAuth);
  }

  @override
  void dispose() {
    _auth.removeListener(_onAuth);
    _email.dispose();
    _password.dispose();
    _confirm.dispose();
    _confirmFocus.dispose();
    super.dispose();
  }

  /// A Google sign-in that came back failed says so here.
  void _onAuth() {
    final problem = _auth.lastLinkProblem;
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

  bool get _ready =>
      _email.text.trim().isNotEmpty &&
      _password.text.isNotEmpty &&
      (!_creating || _confirm.text.isNotEmpty);

  void _submit() {
    if (_creating) {
      if (_password.text != _confirm.text) {
        setState(() => _mismatch = true);
        return;
      }
      setState(() => _mismatch = false);
      unawaited(_run(() => _auth.register(email: _email.text, password: _password.text)));
    } else {
      unawaited(_run(() => _auth.signIn(email: _email.text, password: _password.text)));
    }
  }

  String _describe(AppLocalizations l10n, AuthProblem problem) => switch (problem) {
    AuthProblem.invalidEmail => l10n.authInvalidEmail,
    AuthProblem.weakPassword => l10n.authWeakPassword(_auth.minPasswordLength),
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
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final problem = _problem;

    if (!_auth.available) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: 20),
          _Notice(text: l10n.signInUnavailable),
          const SizedBox(height: 12),
          FxButton(
            label: l10n.tryAgain,
            icon: FxIcons.retry,
            variant: FxButtonVariant.outline,
            busy: _busy,
            onPressed: () => unawaited(_run(_auth.reloadConfig)),
          ),
        ],
      );
    }

    return AutofillGroup(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: 20),
          FxSegmented<bool>(
            segments: [FxSegment(true, l10n.modeCreateAccount), FxSegment(false, l10n.modeSignIn)],
            selected: _creating,
            onChanged: _busy ? null : _setMode,
          ),
          const SizedBox(height: 16),
          _Field(
            controller: _email,
            label: l10n.emailLabel,
            // An address, the same in every language.
            hint: 'you@example.com',
            enabled: !_busy,
            keyboardType: TextInputType.emailAddress,
            action: TextInputAction.next,
            autofill: AutofillHints.email,
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 10),
          _Field(
            controller: _password,
            label: l10n.passwordLabel,
            hint: l10n.passwordHint(_auth.minPasswordLength),
            enabled: !_busy,
            obscure: _hidden,
            action: _creating ? TextInputAction.next : TextInputAction.done,
            autofill: _creating ? AutofillHints.newPassword : AutofillHints.password,
            onChanged: (_) => setState(() {}),
            onEditingComplete: _creating ? _confirmFocus.requestFocus : null,
            onSubmitted: (_) {
              if (!_creating && _ready) _submit();
            },
            suffix: IconButton(
              tooltip: _hidden ? l10n.showPassword : l10n.hidePassword,
              onPressed: () => setState(() => _hidden = !_hidden),
              icon: Icon(_hidden ? FxIcons.eye : FxIcons.eyeSlash, size: 20, color: k.ink3),
            ),
          ),
          if (_creating) ...[
            const SizedBox(height: 10),
            _Field(
              controller: _confirm,
              focusNode: _confirmFocus,
              label: l10n.confirmPasswordLabel,
              hint: l10n.confirmPasswordHint,
              enabled: !_busy,
              obscure: _hidden,
              action: TextInputAction.done,
              autofill: AutofillHints.newPassword,
              onChanged: (_) => setState(() => _mismatch = false),
              onSubmitted: (_) {
                if (_ready) _submit();
              },
              error: _mismatch ? l10n.passwordsDontMatch : null,
            ),
          ],
          if (problem != null) ...[
            const SizedBox(height: 12),
            _Notice(text: _describe(l10n, problem), warning: true),
          ],
          const SizedBox(height: 16),
          FxButton(
            label: _creating ? l10n.createAccountButton : l10n.signInButton,
            onPressed: _ready ? _submit : null,
            busy: _busy,
            height: 54,
            radius: 18,
            fontSize: 15,
          ),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 14),
            child: Row(
              children: [
                Expanded(
                  child: SizedBox(height: 1, child: ColoredBox(color: k.line)),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: Text(l10n.orDivider, style: FactifyText.sans(12, color: k.ink3)),
                ),
                Expanded(
                  child: SizedBox(height: 1, child: ColoredBox(color: k.line)),
                ),
              ],
            ),
          ),
          OutlinedButton(
            onPressed: _busy || !_auth.googleAvailable ? null : () => _run(_auth.startGoogle),
            style: OutlinedButton.styleFrom(
              minimumSize: const Size.fromHeight(52),
              backgroundColor: k.sf,
              foregroundColor: k.ink,
              side: BorderSide(color: k.line),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
              textStyle: FactifyText.sans(14.5, weight: FontWeight.w600),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 22,
                  height: 22,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(color: k.ink2, width: 1.5),
                  ),
                  // Google's initial, the same in every language.
                  child: Text(
                    'G',
                    style: FactifyText.sans(12, weight: FontWeight.w700, color: k.ink2),
                  ),
                ),
                const SizedBox(width: 10),
                Flexible(child: Text(l10n.continueWithGoogle)),
              ],
            ),
          ),
          if (!_auth.googleAvailable) ...[
            const SizedBox(height: 8),
            Text(
              l10n.authGoogleUnavailable,
              textAlign: TextAlign.center,
              style: FactifyText.sans(12, color: k.ink3),
            ),
          ],
        ],
      ),
    );
  }
}

/// A field in a rounded box, its label small above the text (v5).
class _Field extends StatelessWidget {
  const _Field({
    required this.controller,
    required this.label,
    required this.hint,
    required this.enabled,
    required this.action,
    required this.autofill,
    this.focusNode,
    this.keyboardType,
    this.obscure = false,
    this.onChanged,
    this.onEditingComplete,
    this.onSubmitted,
    this.suffix,
    this.error,
  });

  final TextEditingController controller;
  final FocusNode? focusNode;
  final String label;
  final String hint;
  final bool enabled;
  final TextInputAction action;
  final String autofill;
  final TextInputType? keyboardType;
  final bool obscure;
  final ValueChanged<String>? onChanged;
  final VoidCallback? onEditingComplete;
  final ValueChanged<String>? onSubmitted;
  final Widget? suffix;
  final String? error;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final error = this.error;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          padding: const EdgeInsets.fromLTRB(14, 2, 4, 2),
          decoration: BoxDecoration(
            color: k.sf,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: error == null ? k.line : k.fC),
          ),
          child: TextField(
            controller: controller,
            focusNode: focusNode,
            enabled: enabled,
            obscureText: obscure,
            keyboardType: keyboardType,
            textInputAction: action,
            autofillHints: [autofill],
            onChanged: onChanged,
            onEditingComplete: onEditingComplete,
            onSubmitted: onSubmitted,
            style: FactifyText.sans(15, color: k.ink),
            cursorColor: k.acc,
            decoration: InputDecoration(
              labelText: label,
              hintText: hint,
              floatingLabelBehavior: FloatingLabelBehavior.always,
              labelStyle: FactifyText.sans(13, weight: FontWeight.w600, color: k.ink3),
              floatingLabelStyle: FactifyText.sans(13, weight: FontWeight.w600, color: k.ink3),
              hintStyle: FactifyText.sans(15, color: k.ink3.withValues(alpha: 0.7)),
              border: InputBorder.none,
              enabledBorder: InputBorder.none,
              focusedBorder: InputBorder.none,
              disabledBorder: InputBorder.none,
              filled: false,
              isDense: true,
              contentPadding: const EdgeInsets.fromLTRB(0, 14, 0, 8),
              suffixIcon: suffix,
            ),
          ),
        ),
        if (error != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 6, 14, 0),
            child: Text(error, style: FactifyText.sans(12, color: k.fC)),
          ),
      ],
    );
  }
}

/// A short message in a tinted box: a refusal from the server, or why sign-in is off.
class _Notice extends StatelessWidget {
  const _Notice({required this.text, this.warning = false});

  final String text;
  final bool warning;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: warning ? k.fS : k.sf2,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(FxIcons.info, size: 18, color: warning ? k.fC : k.ink2),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              text,
              style: FactifyText.sans(13, color: warning ? k.fC : k.ink2).copyWith(height: 1.4),
            ),
          ),
        ],
      ),
    );
  }
}
