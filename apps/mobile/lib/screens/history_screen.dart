/// History (v5): past checks on this phone, this week at a glance, and each check
/// opening its full answer - sources and all - exactly as it was shown.
///
/// Nothing here is on the server: the history is the phone's own
/// (history/history_store.dart), searched and filtered here, and cleared in one tap
/// or a check at a time by swiping it left.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart' hide TextDirection;

import '../app_services.dart';
import '../history/history_store.dart';
import '../l10n/app_localizations.dart';
import '../models/submission.dart';
import '../models/verdict.dart';
import '../widgets/action_style.dart';
import '../widgets/ui/ui.dart';
import 'result_screen.dart';

/// Opens a kept check's answer. Shared with Check's "Recent" list.
void openHistoryRecord(
  BuildContext context,
  AppServices services,
  HistoryRecord record, {
  bool openShare = false,
}) {
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
          services: services,
          verdict: record.verdict,
          submission: submission,
          kind: record.kind,
          summary: record.summary,
          thumbnail: record.thumbnail,
          openShare: openShare,
        ),
      ),
    ),
  );
}

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({required this.services, this.onStartChecking, super.key});

  final AppServices services;

  /// Takes the person to Check, from the empty state.
  final VoidCallback? onStartChecking;

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  final TextEditingController _query = TextEditingController();
  FactVerdict? _filter;

  /// The one row swiped open, if any.
  String? _revealed;

  HistoryStore get _history => widget.services.history;

  @override
  void initState() {
    super.initState();
    _query.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  Future<void> _confirmClear() async {
    final l10n = AppLocalizations.of(context);
    final k = FactifyTokens.of(context);
    final sure = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(l10n.historyClear, style: FactifyText.of(context).title),
        content: Text(l10n.historyClearConfirm, style: FactifyText.of(context).body),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: Text(l10n.cancel)),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(foregroundColor: k.fC),
            child: Text(l10n.historyDelete),
          ),
        ],
      ),
    );
    if (sure ?? false) await _history.clear();
  }

  String _dayLabel(DateTime day, AppLocalizations l10n, String locale) {
    final today = DateUtils.dateOnly(DateTime.now());
    if (DateUtils.isSameDay(day, today)) return l10n.historyToday;
    if (DateUtils.isSameDay(day, today.subtract(const Duration(days: 1)))) {
      return l10n.historyYesterday;
    }
    return DateFormat('EEE, d MMM', locale).format(day);
  }

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final locale = Localizations.localeOf(context).toLanguageTag();

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: ListenableBuilder(
          listenable: _history,
          builder: (context, _) {
            final all = _history.records;
            final q = _query.text.trim().toLowerCase();
            final shown = [
              for (final r in all)
                if ((_filter == null || r.factVerdict == _filter) &&
                    (q.isEmpty || r.summary.toLowerCase().contains(q)))
                  r,
            ];
            final groups = <(DateTime, List<HistoryRecord>)>[];
            for (final record in shown) {
              if (groups.isEmpty || !DateUtils.isSameDay(groups.last.$1, record.day)) {
                groups.add((record.day, [record]));
              } else {
                groups.last.$2.add(record);
              }
            }

            return ListView(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 20),
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          l10n.tabHistory,
                          style: FactifyText.of(
                            context,
                          ).display.copyWith(fontSize: 35, letterSpacing: -1.1),
                        ),
                      ),
                      if (all.isNotEmpty)
                        FxCircleButton(
                          icon: FxIcons.trash,
                          tooltip: l10n.historyClear,
                          onPressed: _confirmClear,
                          shadow: true,
                        ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                _SearchField(controller: _query),
                if (all.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  _WeekCard(summary: _history.weekSummary()),
                  _Filters(
                    records: all,
                    selected: _filter,
                    onSelect: (value) => setState(() => _filter = value),
                  ),
                ],
                if (all.isEmpty)
                  _Empty(onStart: widget.onStartChecking)
                else if (shown.isEmpty)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(6, 28, 6, 8),
                    child: Text(
                      l10n.historyNoResults,
                      textAlign: TextAlign.center,
                      style: FactifyText.sans(13, color: k.ink3),
                    ),
                  ),
                for (final (day, records) in groups) ...[
                  Padding(
                    padding: const EdgeInsets.fromLTRB(6, 18, 6, 8),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.baseline,
                      textBaseline: TextBaseline.alphabetic,
                      children: [
                        Expanded(
                          child: Text(
                            _dayLabel(day, l10n, locale),
                            style: FactifyText.sans(13, weight: FontWeight.w600, color: k.ink),
                          ),
                        ),
                        Text(
                          l10n.historyChecksCount(records.length),
                          style: FactifyText.sans(12, color: k.ink3),
                        ),
                      ],
                    ),
                  ),
                  Container(
                    clipBehavior: Clip.antiAlias,
                    decoration: BoxDecoration(
                      // Red under the rows: what a swipe to the left uncovers.
                      color: k.fC,
                      borderRadius: BorderRadius.circular(22),
                      boxShadow: k.shadow,
                    ),
                    child: Column(
                      children: [
                        for (final (index, record) in records.indexed) ...[
                          if (index > 0) Container(height: 1, color: k.line),
                          _SwipeRow(
                            key: ValueKey(record.id),
                            revealed: _revealed == record.id,
                            onReveal: (open) => setState(() => _revealed = open ? record.id : null),
                            onDelete: () {
                              setState(() => _revealed = null);
                              unawaited(_history.remove(record.id));
                            },
                            onOpen: () => openHistoryRecord(context, widget.services, record),
                            child: _HistoryRow(record: record, locale: locale),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
                Padding(
                  padding: const EdgeInsets.fromLTRB(6, 16, 6, 0),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(FxIcons.lock, size: 15, color: k.ink3),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          l10n.historyStoredNote,
                          style: FactifyText.sans(12, color: k.ink3).copyWith(height: 1.5),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _SearchField extends StatelessWidget {
  const _SearchField({required this.controller});

  final TextEditingController controller;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    return Container(
      height: 46,
      padding: const EdgeInsets.symmetric(horizontal: 14),
      decoration: BoxDecoration(
        color: k.sf,
        borderRadius: BorderRadius.circular(16),
        boxShadow: k.shadow,
      ),
      child: Row(
        children: [
          Icon(FxIcons.search, size: 20, color: k.ink3),
          const SizedBox(width: 8),
          Expanded(
            child: TextField(
              controller: controller,
              style: FactifyText.sans(15, color: k.ink),
              textInputAction: TextInputAction.search,
              decoration: InputDecoration(
                hintText: l10n.historySearchHint,
                hintStyle: FactifyText.sans(15, color: k.ink3),
                filled: false,
                isDense: true,
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
                contentPadding: EdgeInsets.zero,
              ),
            ),
          ),
          if (controller.text.isNotEmpty)
            GestureDetector(
              onTap: controller.clear,
              child: Icon(FxIcons.close, size: 18, color: k.ink3),
            ),
        ],
      ),
    );
  }
}

/// This week: the total, a Monday-to-Sunday chart - one 20-tall block per check,
/// stacked in its verdict's colour - the counts, and the positive recap.
class _WeekCard extends StatelessWidget {
  const _WeekCard({required this.summary});

  final WeekSummary summary;

  static const double _chartHeight = 84;
  static const double _gap = 3;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final locale = Localizations.localeOf(context).toLanguageTag();
    final ink = k.hiInk;

    final start = summary.start;
    final end = summary.end;
    final range = start.month == end.month
        ? '${DateFormat.d(locale).format(start)}–${DateFormat('d MMM', locale).format(end)}'
        : '${DateFormat('d MMM', locale).format(start)} – ${DateFormat('d MMM', locale).format(end)}';
    final busiest = summary.busiest.map((d) => DateFormat.E(locale).format(d)).toList();
    final stopped = summary.stopped;
    final stoppedText = l10n.historyStopped(stopped);
    final number = NumberFormat.decimalPattern(locale).format(stopped);
    final at = stoppedText.indexOf(number);

    Color colourOf(FactVerdict v) => ActionStyle.colours(v, k).$1;

    return Container(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 14),
      decoration: BoxDecoration(color: k.hiBg, borderRadius: BorderRadius.circular(24)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      l10n.historyWeekRange(range),
                      style: FactifyText.sans(
                        12,
                        weight: FontWeight.w600,
                        color: ink.withValues(alpha: 0.7),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.baseline,
                      textBaseline: TextBaseline.alphabetic,
                      children: [
                        Text(
                          '${summary.total}',
                          style: FactifyText.serif(
                            42,
                            weight: FontWeight.w400,
                            color: ink,
                          ).copyWith(height: 1, letterSpacing: -1),
                        ),
                        const SizedBox(width: 6),
                        Text(
                          l10n.historyChecksUnit(summary.total),
                          style: FactifyText.sans(13, color: ink.withValues(alpha: 0.75)),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              if (busiest.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text(
                    l10n.historyBusiest(
                      busiest.length == 1
                          ? busiest.first
                          : l10n.historyDaysJoin(busiest[0], busiest[1]),
                    ),
                    style: FactifyText.sans(
                      11,
                      weight: FontWeight.w600,
                      color: ink.withValues(alpha: 0.7),
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 14),
          SizedBox(
            height: _chartHeight,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                for (final (i, verdicts) in summary.byDay.indexed) ...[
                  if (i > 0) const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        if (verdicts.isEmpty)
                          Container(
                            height: 6,
                            decoration: BoxDecoration(
                              color: k.hiEmpty,
                              borderRadius: BorderRadius.circular(3),
                            ),
                          )
                        else
                          for (final (j, block) in _blocks(verdicts).indexed) ...[
                            if (j > 0) const SizedBox(height: _gap),
                            Container(
                              height: block.$2,
                              decoration: BoxDecoration(
                                color: colourOf(block.$1),
                                borderRadius: BorderRadius.circular(6),
                              ),
                            ),
                          ],
                      ],
                    ),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              for (final (i, day) in summary.days.indexed) ...[
                if (i > 0) const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    DateFormat.E(locale).format(day).characters.first,
                    textAlign: TextAlign.center,
                    style: FactifyText.sans(
                      11,
                      weight: DateUtils.isSameDay(day, summary.today)
                          ? FontWeight.w700
                          : FontWeight.w500,
                      color: ink.withValues(
                        alpha: day.isAfter(summary.today)
                            ? 0.4
                            : DateUtils.isSameDay(day, summary.today)
                            ? 1
                            : 0.7,
                      ),
                    ),
                  ),
                ),
              ],
            ],
          ),
          Container(
            margin: const EdgeInsets.only(top: 14),
            padding: const EdgeInsets.only(top: 12),
            decoration: BoxDecoration(
              border: Border(top: BorderSide(color: k.hiLine)),
            ),
            child: Row(
              children: [
                for (final v in WeekSummary.order)
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Container(
                              width: 8,
                              height: 8,
                              decoration: BoxDecoration(
                                color: colourOf(v),
                                borderRadius: BorderRadius.circular(3),
                              ),
                            ),
                            const SizedBox(width: 5),
                            Text(
                              '${summary.count(v)}',
                              style: FactifyText.sans(15, weight: FontWeight.w600, color: ink),
                            ),
                          ],
                        ),
                        const SizedBox(height: 3),
                        Text(
                          ActionStyle.word(v, l10n),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: FactifyText.sans(10.5, color: ink.withValues(alpha: 0.7)),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
          Container(
            margin: const EdgeInsets.only(top: 12),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(color: k.hiRecap, borderRadius: BorderRadius.circular(14)),
            child: Row(
              children: [
                Icon(FxIcons.receipt, size: 20, color: k.acc),
                const SizedBox(width: 10),
                Expanded(
                  child: Text.rich(
                    at < 0
                        ? TextSpan(text: stoppedText)
                        : TextSpan(
                            children: [
                              TextSpan(text: stoppedText.substring(0, at)),
                              TextSpan(
                                text: number,
                                style: const TextStyle(fontWeight: FontWeight.w700),
                              ),
                              TextSpan(text: stoppedText.substring(at + number.length)),
                            ],
                          ),
                    style: FactifyText.sans(12.5, color: ink).copyWith(height: 1.4),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// A day's blocks, top first (so False sits at the base): one 20-tall block per
  /// check while three fit, as in the design; on a busier day one block per verdict,
  /// its height its share of the day, so the column stays readable.
  static List<(FactVerdict, double)> _blocks(List<FactVerdict> verdicts) {
    if (verdicts.length * 20 + (verdicts.length - 1) * _gap <= _chartHeight) {
      return [for (final v in verdicts.reversed) (v, 20.0)];
    }
    final groups = [
      for (final v in WeekSummary.order)
        if (verdicts.contains(v)) (v, verdicts.where((x) => x == v).length),
    ];
    final room = _chartHeight - (groups.length - 1) * _gap;
    return [
      for (final (v, n) in groups.reversed) (v, (room * n / verdicts.length).clamp(6.0, room)),
    ];
  }
}

class _Filters extends StatelessWidget {
  const _Filters({required this.records, required this.selected, required this.onSelect});

  final List<HistoryRecord> records;
  final FactVerdict? selected;
  final ValueChanged<FactVerdict?> onSelect;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final options = <FactVerdict?>[null, ...WeekSummary.order];
    return SizedBox(
      height: 64,
      child: ListView(
        scrollDirection: Axis.horizontal,
        clipBehavior: Clip.none,
        padding: const EdgeInsets.only(top: 14, bottom: 6),
        children: [
          for (final (i, option) in options.indexed) ...[
            if (i > 0) const SizedBox(width: 6),
            FxChip(
              label: option == null ? l10n.historyFilterAll : ActionStyle.word(option, l10n),
              count: option == null
                  ? records.length
                  : records.where((r) => r.factVerdict == option).length,
              dot: option == null ? null : ActionStyle.colours(option, k).$1,
              height: 34,
              fontSize: 13,
              selected: selected == option,
              background: selected == option ? k.ink : k.sf,
              foreground: selected == option ? k.bg : k.ink2,
              shadow: true,
              onTap: () => onSelect(option),
            ),
          ],
        ],
      ),
    );
  }
}

class _HistoryRow extends StatelessWidget {
  const _HistoryRow({required this.record, required this.locale});

  final HistoryRecord record;
  final String locale;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    final verdict = record.factVerdict;
    final thumb = record.thumbnail;
    return Container(
      color: k.sf,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            clipBehavior: Clip.antiAlias,
            decoration: BoxDecoration(color: k.sf2, borderRadius: BorderRadius.circular(14)),
            child: thumb != null
                ? Image.memory(
                    thumb,
                    fit: BoxFit.cover,
                    errorBuilder: (_, _, _) =>
                        Icon(FxIcons.forKind(record.kind), size: 20, color: k.ink2),
                  )
                : Icon(FxIcons.forKind(record.kind), size: 20, color: k.ink2),
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
                  style: FactifyText.sans(
                    14,
                    weight: FontWeight.w500,
                    color: k.ink,
                  ).copyWith(height: 1.35),
                ),
                const SizedBox(height: 6),
                Wrap(
                  spacing: 6,
                  runSpacing: 4,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    FxVerdictPill(
                      verdict: verdict,
                      label: ActionStyle.label(record.verdict, l10n),
                      icon: ActionStyle.labelIcon(record.verdict),
                    ),
                    Text(
                      '${DateFormat.Hm(locale).format(record.checkedAt.toLocal())} · '
                      '${l10n.historySources(record.sourceCount)}',
                      style: FactifyText.sans(11.5, color: k.ink3),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(width: 6),
          Icon(FxIcons.chevron, size: 18, color: k.ink3),
        ],
      ),
    );
  }
}

/// A row that slides left to uncover Delete; a tap opens it, or closes it if open.
class _SwipeRow extends StatefulWidget {
  const _SwipeRow({
    required this.revealed,
    required this.onReveal,
    required this.onDelete,
    required this.onOpen,
    required this.child,
    super.key,
  });

  final bool revealed;
  final ValueChanged<bool> onReveal;
  final VoidCallback onDelete;
  final VoidCallback onOpen;
  final Widget child;

  @override
  State<_SwipeRow> createState() => _SwipeRowState();
}

class _SwipeRowState extends State<_SwipeRow> {
  static const double _width = 88;
  double? _drag;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final rtl = Directionality.of(context) == TextDirection.rtl;
    final sign = rtl ? -1.0 : 1.0;
    final offset = _drag ?? (widget.revealed ? -_width : 0.0);
    return Stack(
      children: [
        Positioned.fill(
          child: Align(
            alignment: AlignmentDirectional.centerEnd,
            child: Semantics(
              button: true,
              label: l10n.historyDelete,
              excludeSemantics: true,
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: widget.onDelete,
                child: SizedBox(
                  width: _width,
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(FxIcons.trash, size: 21, color: Colors.white),
                      const SizedBox(height: 3),
                      Text(
                        l10n.historyDelete,
                        style: FactifyText.sans(11, weight: FontWeight.w600, color: Colors.white),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
        // The row and its touch area move together, so the Delete it uncovers is
        // the Delete a tap reaches.
        AnimatedContainer(
          duration: _drag == null ? const Duration(milliseconds: 250) : Duration.zero,
          curve: Curves.easeOut,
          transform: Matrix4.translationValues(offset * sign, 0, 0),
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: widget.revealed ? () => widget.onReveal(false) : widget.onOpen,
            onHorizontalDragStart: (_) => setState(() => _drag = offset),
            onHorizontalDragUpdate: (d) =>
                setState(() => _drag = ((_drag ?? 0) + d.delta.dx * sign).clamp(-_width, 0.0)),
            onHorizontalDragEnd: (_) {
              final open = (_drag ?? 0) < -_width / 2;
              setState(() => _drag = null);
              widget.onReveal(open);
            },
            child: widget.child,
          ),
        ),
      ],
    );
  }
}

class _Empty extends StatelessWidget {
  const _Empty({this.onStart});

  final VoidCallback? onStart;

  @override
  Widget build(BuildContext context) {
    final k = FactifyTokens.of(context);
    final l10n = AppLocalizations.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 36, 20, 12),
      child: Column(
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(color: k.accS, shape: BoxShape.circle),
            child: Icon(FxIcons.history, size: 30, color: k.acc),
          ),
          const SizedBox(height: 12),
          Text(
            l10n.historyEmptyTitle,
            textAlign: TextAlign.center,
            style: FactifyText.serif(21, weight: FontWeight.w400, color: k.ink),
          ),
          const SizedBox(height: 4),
          Text(
            l10n.historyEmptyBody,
            textAlign: TextAlign.center,
            style: FactifyText.sans(13, color: k.ink3).copyWith(height: 1.5),
          ),
          if (onStart != null) ...[
            const SizedBox(height: 18),
            FxButton(
              label: l10n.checkNow,
              trailingIcon: FxIcons.forward,
              onPressed: onStart,
              expand: false,
              height: 48,
              fontSize: 15,
            ),
          ],
        ],
      ),
    );
  }
}
