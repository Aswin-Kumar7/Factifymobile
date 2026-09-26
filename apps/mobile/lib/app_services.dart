/// What every screen needs, passed down as one thing.
///
/// The app has four long-lived pieces - the server client, sign-in, the interface
/// language and the history kept on this phone - and every screen needs some of
/// them. Handing them down together keeps each screen's constructor short and makes
/// a test able to build any screen against stand-ins.
library;

import 'api/client.dart';
import 'auth/auth_service.dart';
import 'history/history_store.dart';
import 'l10n/language_preference.dart';

class AppServices {
  const AppServices({
    required this.client,
    required this.auth,
    required this.language,
    required this.history,
  });

  final FactifyClient client;
  final AuthService auth;
  final LanguagePreference language;
  final HistoryStore history;
}
