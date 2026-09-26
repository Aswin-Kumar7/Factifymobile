/// "Why 91% confidence" (v5): what the confidence is made of, or why there is none.
///
/// The number is arithmetic on the cited sources - how many, how credible, whether
/// any disagree - never a model's score, and it runs from 50 to 97: never certain,
/// and never less than even. The sheet shows it on that scale and lists the parts
/// it is computed from, taken from the claim that decided the verdict. Forensic
/// signals are named as excluded, because they are: advisories never enter a score.
/// For an Unconfirmed result it says why nothing was decided instead.
library;

import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/verdict.dart';
import 'action_style.dart';
import 'claim_words.dart';
import 'ui/ui.dart';

/// The claim whose finding the verdict rests on: the most confident one with the
/// verdict's own status.
Claim? decidingClaim(Verdict verdict) {
  final wanted = switch (verdict.factVerdict) {
    FactVerdict.trueClaim => {ClaimStatus.supported},
    FactVerdict.falseClaim => {ClaimStatus.contradicted},
    FactVerdict.misleading => {ClaimStatus.misleadingContext, ClaimStatus.contradicted},
    FactVerdict.unconfirmed => const <ClaimStatus>{},
  };
  final candidates = verdict.claims.where((c) => wanted.contains(c.status)).toList()
    ..sort((a, b) => (b.confidence ?? 0).compareTo(a.confidence ?? 0));
  return candidates.firstOrNull;
}

/// A strength component's note in plain words. The server writes them for the
/// audit trail ("2×C, 3×D", "5 distinct origin(s) across 5 document(s)"); the
/// reader gets "2 fact-checks, 3 news reports". A note in no known form is shown as
/// it came.
String componentNote(StrengthComponent component, AppLocalizations l10n) {
  final note = component.explanation.trim();
  RegExpMatch? m(String pattern) => RegExp(pattern).firstMatch(note);
  switch (component.name) {
    case 'tier_composition':
      if (note == 'no evidence') return l10n.compNoEvidence;
      final tiers = RegExp(r'(\d+)×([A-E])').allMatches(note).toList();
      if (tiers.isNotEmpty) {
        return tiers.map((t) => l10n.compTier(t.group(2)!, int.parse(t.group(1)!))).join(', ');
      }
    case 'independent_origins':
      final found = m(r'^(\d+) distinct origin\(s\) across (\d+) document\(s\)$');
      if (found != null) {
        return l10n.compOrigins(int.parse(found.group(1)!), int.parse(found.group(2)!));
      }
    case 'temporal_confidence':
      if (note == 'no dated evidence') return l10n.compNoDated;
      final found = m(r'^(\d+) dated finding\(s\)$');
      if (found != null) return l10n.compDated(int.parse(found.group(1)!));
    case 'source_transparency':
      final found = m(r'^publisher risk (\w+)$');
      if (found != null) return l10n.compRisk(found.group(1)!);
    case 'conflict_penalty':
      if (note == 'no conflict') return l10n.compNoConflict;
      final found = m(r'^(\d+) supporting and (\d+) contradicting finding\(s\)$');
      if (found != null) {
        return l10n.compConflict(int.parse(found.group(1)!), int.parse(found.group(2)!));
      }
  }
  return note;
}

Future<void> showWhySheet(BuildContext context, Verdict verdict) =>
    showFxSheet<void>(context, builder: (context) => WhySheet(verdict: verdict));

class WhySheet extends StatelessWidget {
  const WhySheet({required this.verdict, super.key});

  final Verdict verdict;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final confidence = verdict.factVerdict.isDecided ? verdict.confidence : null;
    final (colour, _) = ActionStyle.colours(verdict.factVerdict, k);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    confidence != null ? l10n.whyOverline : l10n.whyNoVerdictOverline,
                    style: FactifyText.mono(10.5, color: k.ink3, spacing: 1),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    confidence != null ? l10n.whyTitle(confidence) : l10n.whyNoVerdict,
                    style: FactifyText.serif(26, color: k.ink).copyWith(letterSpacing: -0.5),
                  ),
                ],
              ),
            ),
            FxCircleButton(
              icon: FxIcons.close,
              tooltip: l10n.gotIt,
              onPressed: () => Navigator.of(context).pop(),
              size: 34,
              iconSize: 18,
              background: k.sf2,
            ),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          confidence != null ? l10n.whyBody : l10n.subheadSendToReview,
          style: FactifyText.sans(13, color: k.ink2).copyWith(height: 1.5),
        ),
        if (confidence != null) ..._scale(context, k, l10n, confidence, colour),
        if (confidence == null) ..._undecided(context, k, l10n),
        const SizedBox(height: 14),
        FxButton(
          label: l10n.gotIt,
          variant: FxButtonVariant.dark,
          height: 50,
          fontSize: 14.5,
          onPressed: () => Navigator.of(context).pop(),
        ),
      ],
    );
  }

  List<Widget> _scale(
    BuildContext context,
    FactifyTokens k,
    AppLocalizations l10n,
    int confidence,
    Color colour,
  ) {
    final share = ((confidence - 50) / 47).clamp(0.0, 1.0);
    final components = decidingClaim(verdict)?.strength.components ?? const <StrengthComponent>[];
    return [
      const SizedBox(height: 16),
      SizedBox(
        height: 16,
        child: LayoutBuilder(
          builder: (context, box) => Stack(
            clipBehavior: Clip.none,
            alignment: Alignment.centerLeft,
            children: [
              Container(
                height: 8,
                decoration: BoxDecoration(color: k.sf2, borderRadius: BorderRadius.circular(4)),
              ),
              Container(
                height: 8,
                width: box.maxWidth * share,
                decoration: BoxDecoration(color: colour, borderRadius: BorderRadius.circular(4)),
              ),
              Positioned(
                left: (box.maxWidth * share - 2).clamp(0.0, box.maxWidth - 4),
                child: Container(
                  width: 4,
                  height: 16,
                  decoration: BoxDecoration(color: k.ink, borderRadius: BorderRadius.circular(2)),
                ),
              ),
            ],
          ),
        ),
      ),
      const SizedBox(height: 5),
      Row(
        children: [
          Expanded(
            child: Text(l10n.whyScaleLow, style: FactifyText.sans(10.5, color: k.ink3)),
          ),
          Text(l10n.whyScaleHigh, style: FactifyText.sans(10.5, color: k.ink3)),
        ],
      ),
      const SizedBox(height: 8),
      for (final component in components)
        Container(
          padding: const EdgeInsets.symmetric(vertical: 9),
          decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: k.line)),
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      l10n.strengthComponent(component.name),
                      style: FactifyText.sans(13, weight: FontWeight.w600, color: k.ink),
                    ),
                    if (component.explanation.isNotEmpty) ...[
                      const SizedBox(height: 1),
                      Text(
                        componentNote(component, l10n),
                        style: FactifyText.sans(11.5, color: k.ink3),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 10),
              SizedBox(
                width: 64,
                child: Stack(
                  children: [
                    Container(
                      height: 5,
                      decoration: BoxDecoration(
                        color: k.sf2,
                        borderRadius: BorderRadius.circular(3),
                      ),
                    ),
                    FractionallySizedBox(
                      widthFactor: component.value.clamp(0.0, 1.0),
                      child: Container(
                        height: 5,
                        decoration: BoxDecoration(
                          color: k.acc,
                          borderRadius: BorderRadius.circular(3),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              SizedBox(
                width: 34,
                child: Text(
                  component.value.toStringAsFixed(2),
                  textAlign: TextAlign.right,
                  style: FactifyText.mono(12, color: k.ink, spacing: 0),
                ),
              ),
            ],
          ),
        ),
      const SizedBox(height: 10),
      Text(l10n.whyExcluded, style: FactifyText.sans(11.5, color: k.ink3)),
    ];
  }

  List<Widget> _undecided(BuildContext context, FactifyTokens k, AppLocalizations l10n) {
    final first = verdict.claims.where((c) => c.claimType != 'MEDIA').firstOrNull;
    final reasons = [
      (FxIcons.search, first == null ? l10n.claimNothingFound : claimReason(first, l10n)),
      (FxIcons.scales, l10n.whyUncNotFalse),
      (FxIcons.history, l10n.whyUncLater),
    ];
    return [
      const SizedBox(height: 14),
      for (final (index, (icon, text)) in reasons.indexed) ...[
        if (index > 0) const SizedBox(height: 8),
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: k.sf2, borderRadius: BorderRadius.circular(14)),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, size: 17, color: k.ink2),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  text,
                  style: FactifyText.sans(12.5, color: k.ink).copyWith(height: 1.5),
                ),
              ),
            ],
          ),
        ),
      ],
    ];
  }
}
