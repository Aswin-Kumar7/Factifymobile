/// Past checks, on their own tab: each with its verdict and how many sources it
/// cited, opening the full answer - sources and all - exactly as it was shown.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../app_services.dart';
import '../history/history_store.dart';
import '../l10n/app_localizations.dart';
import '../models/submission.dart';
import '../models/verdict.dart';
import '../theme/colors.dart';
import '../widgets/action_style.dart';
import '../widgets/checked_item_card.dart';
import 'result_screen.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({required this.services, this.onStartChecking, super.key});

  final AppServices services;

  /// Takes the person to Home, from the empty state.
  final VoidCallback? onStartChecking;

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  FactVerdict? _filter;

  HistoryStore get _history => widget.services.history;

  Future<void> _confirmClear() async {
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
    if (sure ?? false) await _history.clear();
  }

  void _open(HistoryRecord record) {
    final text = record.text;
    final submission = text == null
        ? null
        : record.kind == SubmissionKind.link
        ? Submission.link(text)
        : Submission.text(text);
    unawaited(
      Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => ResultScreen(
            services: widget.services,
            verdict: record.verdict,
            submission: submission,
            kind: record.kind,
            summary: record.summary,
            thumbnail: record.thumbnail,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.tabHistory),
        actions: [
          ListenableBuilder(
            listenable: _history,
            builder: (context, _) => _history.records.isEmpty
                ? const SizedBox.shrink()
                : IconButton(
                    tooltip: l10n.historyClear,
                    icon: const Icon(Icons.delete_sweep_outlined),
                    onPressed: _confirmClear,
                  ),
          ),
        ],
      ),
      body: SafeArea(
        child: ListenableBuilder(
          listenable: _history,
          builder: (context, _) {
            final all = _history.records;
            if (all.isEmpty) return _Empty(onStart: widget.onStartChecking);
            final shown = _filter == null
                ? all
                : all.where((r) => r.verdict.factVerdict == _filter).toList();
            return ListView(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
              children: [
                _Filters(selected: _filter, onSelect: (value) => setState(() => _filter = value)),
                const SizedBox(height: 8),
                ..._grouped(context, shown),
                const SizedBox(height: 16),
                Row(
                  children: [
                    const Icon(Icons.lock_outline_rounded, size: 16, color: FactifyColors.inkMuted),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        l10n.historyStoredNote,
                        style: Theme.of(
                          context,
                        ).textTheme.bodySmall?.copyWith(color: FactifyColors.inkMuted),
                      ),
                    ),
                  ],
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  List<Widget> _grouped(BuildContext context, List<HistoryRecord> records) {
    final l10n = AppLocalizations.of(context);
    final locale = Localizations.localeOf(context).toString();
    final today = DateUtils.dateOnly(DateTime.now());
    final widgets = <Widget>[];
    DateTime? current;
    for (final record in records) {
      final day = DateUtils.dateOnly(record.checkedAt);
      if (day != current) {
        current = day;
        final label = day == today
            ? l10n.historyToday
            : day == today.subtract(const Duration(days: 1))
            ? l10n.historyYesterday
            : DateFormat.yMMMd(locale).format(day);
        widgets.add(
          Padding(
            padding: const EdgeInsets.fromLTRB(4, 14, 4, 8),
            child: Text(
              label,
              style: Theme.of(context).textTheme.labelLarge?.copyWith(
                color: FactifyColors.inkMuted,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        );
      }
      widgets.add(
        Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: Dismissible(
            key: ValueKey(record.id),
            direction: DismissDirection.endToStart,
            background: Container(
              alignment: AlignmentDirectional.centerEnd,
              padding: const EdgeInsetsDirectional.only(end: 20),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.errorContainer,
                borderRadius: BorderRadius.circular(18),
              ),
              child: Icon(Icons.delete_outline_rounded, color: Theme.of(context).colorScheme.error),
            ),
            onDismissed: (_) => unawaited(_history.remove(record.id)),
            child: _HistoryTile(record: record, onTap: () => _open(record)),
          ),
        ),
      );
    }
    return widgets;
  }
}

class _Filters extends StatelessWidget {
  const _Filters({required this.selected, required this.onSelect});

  final FactVerdict? selected;
  final ValueChanged<FactVerdict?> onSelect;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final options = <(FactVerdict?, String)>[
      (null, l10n.historyFilterAll),
      (FactVerdict.trueClaim, l10n.headlineSafeToShare),
      (FactVerdict.falseClaim, l10n.headlineDoNotShare),
      (FactVerdict.misleading, l10n.headlineShareWithContext),
      (FactVerdict.unconfirmed, l10n.headlineSendToReview),
    ];
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (final (value, label) in options)
            Padding(
              padding: const EdgeInsetsDirectional.only(end: 8),
              child: ChoiceChip(
                label: Text(label),
                selected: selected == value,
                onSelected: (_) => onSelect(value),
                selectedColor: FactifyColors.emeraldSoft,
                labelStyle: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: selected == value ? FactifyColors.emeraldDeep : FactifyColors.inkSoft,
                ),
                showCheckmark: false,
              ),
            ),
        ],
      ),
    );
  }
}

class _HistoryTile extends StatelessWidget {
  const _HistoryTile({required this.record, required this.onTap});

  final HistoryRecord record;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final verdict = record.verdict;
    final style = ActionStyle.forVerdict(verdict, theme.brightness, l10n);
    final sources = {for (final e in verdict.allEvidence) e.citationUrl}.length;
    final time = TimeOfDay.fromDateTime(record.checkedAt).format(context);
    final thumb = record.thumbnail;

    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(10),
                child: thumb != null
                    ? Image.memory(thumb, width: 48, height: 48, fit: BoxFit.cover)
                    : Container(
                        width: 48,
                        height: 48,
                        color: FactifyColors.ground,
                        child: Icon(iconForKind(record.kind), color: FactifyColors.inkMuted),
                      ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      record.summary.isEmpty ? l10n.yourPicture : record.summary,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '$time  ·  ${l10n.historySources(sources)}',
                      style: theme.textTheme.bodySmall?.copyWith(color: FactifyColors.inkMuted),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: style.container,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(style.icon, size: 14, color: style.tone),
                    const SizedBox(width: 4),
                    Text(
                      style.headline,
                      style: TextStyle(
                        color: style.onContainer,
                        fontWeight: FontWeight.w700,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Empty extends StatelessWidget {
  const _Empty({this.onStart});

  final VoidCallback? onStart;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 84,
              height: 84,
              decoration: const BoxDecoration(
                color: FactifyColors.emeraldTint,
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.history_rounded, size: 40, color: FactifyColors.emerald),
            ),
            const SizedBox(height: 16),
            Text(
              l10n.historyEmptyTitle,
              style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 6),
            Text(
              l10n.historyEmptyBody,
              textAlign: TextAlign.center,
              style: theme.textTheme.bodyMedium?.copyWith(color: FactifyColors.inkMuted),
            ),
            if (onStart != null) ...[
              const SizedBox(height: 20),
              FilledButton.icon(
                onPressed: onStart,
                icon: const Icon(Icons.add_rounded),
                label: Text(l10n.newCheck),
                style: FilledButton.styleFrom(minimumSize: const Size(180, 48)),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
