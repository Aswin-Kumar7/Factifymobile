/// The language toggle (M44): the phone's language, English, or Hindi.
///
/// Each language is named in its own script and never translated. Someone looking
/// for Hindi in an English interface is scanning for "हिन्दी", and a menu that
/// offers "Hindi" in a script they may not read hides the one option they came for.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../l10n/language_preference.dart';

class LanguageMenu extends StatelessWidget {
  const LanguageMenu({required this.preference, super.key});

  final LanguagePreference preference;

  /// Endonyms, deliberately outside the ARB files: they read the same in every
  /// interface language.
  static const Map<String, String> _names = {'en': 'English', 'hi': 'हिन्दी'};
  static const Map<String, String> _badges = {'en': 'EN', 'hi': 'हि'};

  /// The menu value for "follow the phone", which has no locale of its own.
  static const String _phone = 'phone';

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final muted = theme.colorScheme.onSurfaceVariant;
    // What is on screen, which is not always what was chosen: "phone language"
    // on a Tamil phone shows English.
    final showing = Localizations.localeOf(context).languageCode;

    return ValueListenableBuilder<Locale?>(
      valueListenable: preference,
      builder: (context, chosen, _) => PopupMenuButton<String>(
        tooltip: l10n.languageMenuTooltip,
        position: PopupMenuPosition.under,
        onSelected: (value) =>
            unawaited(preference.choose(value == _phone ? null : Locale(value))),
        itemBuilder: (context) => [
          _option(_phone, l10n.languagePhone, selected: chosen == null),
          for (final locale in AppLocalizations.supportedLocales)
            _option(
              locale.languageCode,
              _names[locale.languageCode] ?? locale.languageCode,
              selected: chosen?.languageCode == locale.languageCode,
            ),
        ],
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
          decoration: BoxDecoration(
            color: theme.colorScheme.surfaceContainerHighest,
            borderRadius: BorderRadius.circular(999),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.translate, size: 14, color: muted),
              const SizedBox(width: 5),
              Text(
                _badges[showing] ?? showing.toUpperCase(),
                style: theme.textTheme.labelSmall?.copyWith(
                  color: muted,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  PopupMenuItem<String> _option(String value, String label, {required bool selected}) =>
      PopupMenuItem<String>(
        value: value,
        child: Row(
          children: [
            SizedBox(width: 24, child: selected ? const Icon(Icons.check, size: 18) : null),
            const SizedBox(width: 8),
            Text(label),
          ],
        ),
      );
}
