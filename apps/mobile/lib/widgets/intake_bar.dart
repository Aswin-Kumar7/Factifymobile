/// The intake surface: paste something, or hand over a picture.
///
/// Three separate affordances rather than one "Media" button, because they are
/// three different situations. A screenshot already on the phone, a photograph of
/// something in front of you, and a PDF someone forwarded are reached by
/// different routes, and collapsing them into a single file picker made the
/// commonest one — a forwarded screenshot — no easier to reach than the rarest.
library;

import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';

enum IntakeSource { gallery, camera, document }

class IntakeBar extends StatelessWidget {
  const IntakeBar({
    required this.controller,
    required this.onCheck,
    required this.onPick,
    required this.busy,
    this.recheckFor,
    this.onRecheck,
    this.deep = false,
    this.onDeepChanged,
    super.key,
  });

  /// Whether the next check of text or a link is a deep one.
  final bool deep;
  final ValueChanged<bool>? onDeepChanged;

  final TextEditingController controller;
  final VoidCallback onCheck;
  final void Function(IntakeSource) onPick;
  final bool busy;

  /// What the last finished check was of, as it sat in the box. While the box still
  /// holds exactly that, the button checks it again, fresh, instead of checking
  /// something new; edit it and the button goes back to "Check this". An empty
  /// string stands for a picture or document, which the box cannot show.
  final String? recheckFor;
  final VoidCallback? onRecheck;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: controller,
          // Locked while a check runs, so what is on screen stays what is being
          // checked.
          enabled: !busy,
          maxLines: 5,
          minLines: 3,
          textInputAction: TextInputAction.newline,
          decoration: InputDecoration(
            border: const OutlineInputBorder(),
            labelText: l10n.inputLabel,
            hintText: l10n.inputHint,
            filled: true,
            fillColor: theme.colorScheme.surface,
            suffixIcon: ValueListenableBuilder<TextEditingValue>(
              valueListenable: controller,
              builder: (context, value, _) => value.text.isEmpty || busy
                  ? const SizedBox.shrink()
                  : IconButton(
                      icon: const Icon(Icons.clear),
                      tooltip: l10n.clear,
                      onPressed: controller.clear,
                    ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        ValueListenableBuilder<TextEditingValue>(
          valueListenable: controller,
          builder: (context, value, _) {
            final again = onRecheck != null && recheckFor == value.text.trim();
            return FilledButton.icon(
              // Disabled on empty rather than accepting and failing: an empty
              // submission has no honest answer, and a 422 explaining that is a
              // worse experience than a button that plainly is not ready.
              onPressed: busy
                  ? null
                  : again
                  ? onRecheck
                  : value.text.trim().isEmpty
                  ? null
                  : onCheck,
              icon: Icon(again ? Icons.refresh_rounded : Icons.fact_check_outlined),
              label: Text(again ? l10n.checkAgain : l10n.checkThis),
              style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48)),
            );
          },
        ),
        if (onDeepChanged != null) ...[
          const SizedBox(height: 4),
          SwitchListTile.adaptive(
            value: deep,
            onChanged: busy ? null : onDeepChanged,
            contentPadding: const EdgeInsets.symmetric(horizontal: 4),
            dense: true,
            secondary: Icon(
              Icons.travel_explore_rounded,
              color: deep ? theme.colorScheme.primary : theme.colorScheme.onSurfaceVariant,
            ),
            title: Text(l10n.deepCheck, style: const TextStyle(fontWeight: FontWeight.w700)),
            subtitle: Text(l10n.deepCheckHint),
          ),
        ],
        const SizedBox(height: 12),
        Row(
          children: [
            _SourceButton(
              icon: Icons.photo_library_outlined,
              label: l10n.sourceGallery,
              onPressed: busy ? null : () => onPick(IntakeSource.gallery),
            ),
            const SizedBox(width: 8),
            _SourceButton(
              icon: Icons.photo_camera_outlined,
              label: l10n.sourceCamera,
              onPressed: busy ? null : () => onPick(IntakeSource.camera),
            ),
            const SizedBox(width: 8),
            _SourceButton(
              icon: Icons.description_outlined,
              label: l10n.sourceFile,
              onPressed: busy ? null : () => onPick(IntakeSource.document),
            ),
          ],
        ),
      ],
    );
  }
}

class _SourceButton extends StatelessWidget {
  const _SourceButton({required this.icon, required this.label, required this.onPressed});

  final IconData icon;
  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) => Expanded(
    child: OutlinedButton(
      onPressed: onPressed,
      style: OutlinedButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 12)),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 22),
          const SizedBox(height: 4),
          Text(label, style: Theme.of(context).textTheme.labelSmall),
        ],
      ),
    ),
  );
}
