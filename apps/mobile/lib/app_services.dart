/// What every screen needs, passed down as one thing.
///
/// The app has a few long-lived pieces - the server client, sign-in, the interface
/// language, light or dark, the history kept on this phone, and the "your check is
/// ready" notifications - and every screen
/// needs some of them. Handing them down together keeps each screen's constructor short and makes
/// a test able to build any screen against stand-ins.
library;

import 'api/client.dart';
import 'auth/auth_service.dart';
import 'history/history_store.dart';
import 'l10n/language_preference.dart';
import 'notify/notify_preference.dart';
import 'notify/ready_notifier.dart';
import 'quick/bubble.dart';
import 'quick/quick_preference.dart';
import 'theme/theme_mode_preference.dart';

class AppServices {
  AppServices({
    required this.client,
    required this.auth,
    required this.language,
    required this.history,
    ThemeModePreference? themeMode,
    ReadyNotifier? notifier,
    NotifyPreference? notifyByDefault,
    QuickVerdictPreference? quickVerdict,
    BubbleController? bubble,
  }) : themeMode = themeMode ?? ThemeModePreference.inMemory(),
       notifier = notifier ?? SilentNotifier(),
       notifyByDefault = notifyByDefault ?? NotifyPreference.inMemory(),
       quickVerdict = quickVerdict ?? QuickVerdictPreference.inMemory(),
       bubble = bubble ?? BubbleController.inMemory();

  final FactifyClient client;
  final AuthService auth;
  final LanguagePreference language;
  final HistoryStore history;
  final ThemeModePreference themeMode;

  /// Tests get one that notifies nobody.
  final ReadyNotifier notifier;
  final NotifyPreference notifyByDefault;

  /// Whether text shared to Factify is answered over the chat, or opens the app.
  final QuickVerdictPreference quickVerdict;

  /// The floating Factify button: copy anywhere, tap it, answer over the chat.
  final BubbleController bubble;
}
