/// Buying credits: the app hands off to the browser, as Spotify does.
///
/// The server gives a one-time link (new for every purchase, single-use, valid ten
/// minutes). The browser opens it, which signs the person in there once, and shows
/// the packs, a summary and Razorpay. Meanwhile this screen waits, asking the server
/// every few seconds - and at once when the app comes back to the front - until the
/// payment is paid, failed, cancelled, or the link expires unused.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../app_services.dart';
import '../l10n/app_localizations.dart';
import '../models/account.dart';
import '../theme/icons.dart';
import '../theme/tokens.dart';
import '../theme/typography.dart';
import '../widgets/brand.dart';
import '../widgets/ui/fx_button.dart';

class PaymentScreen extends StatefulWidget {
  const PaymentScreen({
    required this.services,
    this.orgId,
    this.opener,
    this.plans = false,
    super.key,
  });

  final AppServices services;

  /// An organisation the person owns; null buys their own credits.
  final String? orgId;

  /// Opens the payment page; the browser by default (tests replace it).
  final Future<bool> Function(Uri url)? opener;

  /// Choose a monthly plan on the website, rather than buy a pack of credits.
  final bool plans;

  @override
  State<PaymentScreen> createState() => _PaymentScreenState();
}

class _PaymentScreenState extends State<PaymentScreen> with WidgetsBindingObserver {
  PaymentHandoff? _handoff;
  String? _problem;
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_start());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _poll?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Back from the browser: ask now rather than at the next tick.
    if (state == AppLifecycleState.resumed) unawaited(_check());
  }

  Future<bool> _open(Uri url) =>
      widget.opener?.call(url) ?? launchUrl(url, mode: LaunchMode.externalApplication);

  Future<void> _start() async {
    _poll?.cancel();
    setState(() {
      _handoff = null;
      _problem = null;
    });
    try {
      final handoff = await widget.services.client.startPayment(orgId: widget.orgId);
      if (!mounted) return;
      setState(() => _handoff = handoff);
      final url = handoff.url;
      if (url != null) {
        final page = Uri.parse(url);
        await _open(
          widget.plans
              ? page.replace(queryParameters: {...page.queryParameters, 'then': 'plans'})
              : page,
        );
      }
      if (!mounted) return;
      _poll = Timer.periodic(const Duration(seconds: 3), (_) => unawaited(_check()));
    } catch (_) {
      if (mounted) setState(() => _problem = AppLocalizations.of(context).payCouldNotStart);
    }
  }

  Future<void> _check() async {
    final current = _handoff;
    if (current == null || current.finished) return;
    try {
      final next = await widget.services.client.paymentStatus(current.id);
      if (!mounted) return;
      setState(() => _handoff = next);
      if (next.finished) {
        _poll?.cancel();
        if (next.status == 'paid') unawaited(widget.services.auth.refreshAccount());
      }
    } catch (_) {
      // A missed poll is retried at the next tick.
    }
  }

  Future<void> _cancel() async {
    final current = _handoff;
    _poll?.cancel();
    if (current != null && !current.finished) {
      try {
        await widget.services.client.cancelPayment(current.id);
      } catch (_) {}
    }
    if (mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final handoff = _handoff;
    final status = _problem != null ? 'problem' : (handoff?.status ?? 'starting');

    final (String title, String body, IconData? icon, Color tone) = switch (status) {
      'paid' => (
        l10n.payPaidTitle,
        widget.plans ? l10n.payPlanPaidBody : l10n.payPaidBody(handoff?.credits ?? 0),
        FxIcons.checkFill,
        k.tC,
      ),
      'failed' => (l10n.payFailedTitle, l10n.payFailedBody, FxIcons.info, k.fC),
      'cancelled' => (l10n.payCancelledTitle, l10n.payCancelledBody, FxIcons.info, k.ink2),
      'expired' => (l10n.payExpiredTitle, l10n.payExpiredBody, FxIcons.info, k.ink2),
      'problem' => (l10n.payFailedTitle, _problem ?? '', FxIcons.offline, k.fC),
      'opened' => (l10n.payTitle, l10n.payOpened, null, k.acc),
      _ => (l10n.payTitle, handoff == null ? l10n.payOpening : l10n.payWaiting, null, k.acc),
    };
    final waiting = icon == null;

    return PopScope(
      canPop: !waiting,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) unawaited(_cancel());
      },
      child: Scaffold(
        backgroundColor: k.bg,
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 16, 24, 24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Spacer(),
                Center(
                  child: waiting
                      ? SizedBox(
                          width: 96,
                          height: 96,
                          child: Stack(
                            alignment: Alignment.center,
                            children: [
                              SizedBox.expand(child: CircularProgressIndicator(strokeWidth: 3, color: tone)),
                              const FactifyMark(size: 64),
                            ],
                          ),
                        )
                      : Container(
                          width: 88,
                          height: 88,
                          decoration: BoxDecoration(color: tone.withValues(alpha: 0.12), shape: BoxShape.circle),
                          child: Icon(icon, size: 44, color: tone),
                        ),
                ),
                const SizedBox(height: 28),
                Semantics(
                  header: true,
                  liveRegion: true,
                  child: Text(
                    title,
                    textAlign: TextAlign.center,
                    style: FactifyText.serif(32, color: k.ink).copyWith(height: 1.1, letterSpacing: -0.8),
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  body,
                  textAlign: TextAlign.center,
                  style: FactifyText.sans(15, color: k.ink2).copyWith(height: 1.5),
                ),
                const Spacer(),
                if (waiting) ...[
                  if (handoff?.url != null && status == 'waiting')
                    FxButton(
                      label: l10n.payReopen,
                      icon: FxIcons.openExternal,
                      variant: FxButtonVariant.outline,
                      onPressed: () => unawaited(_open(Uri.parse(handoff!.url!))),
                    ),
                  const SizedBox(height: 10),
                  FxButton(
                    label: l10n.payCancel,
                    variant: FxButtonVariant.outline,
                    onPressed: () => unawaited(_cancel()),
                  ),
                ] else if (status == 'paid')
                  FxButton(label: l10n.payDone, onPressed: () => Navigator.of(context).pop(true))
                else ...[
                  FxButton(label: l10n.payTryAgain, icon: FxIcons.retry, onPressed: () => unawaited(_start())),
                  const SizedBox(height: 10),
                  FxButton(
                    label: l10n.payDone,
                    variant: FxButtonVariant.outline,
                    onPressed: () => Navigator.of(context).pop(false),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
