/// A signed-in person's account, and how the server says to sign in.
///
/// No display words live here (see lib/l10n). Every number comes from the server:
/// the app shows the balance it is given and never decides whether a check may run.
library;

/// How this server signs people in. All of it is public by design.
class AuthConfig {
  const AuthConfig({
    required this.enabled,
    this.required = false,
    this.providers = const [],
    this.minPasswordLength = 8,
  });

  /// Before the server has answered, or when it cannot be reached.
  static const AuthConfig off = AuthConfig(enabled: false);

  final bool enabled;

  /// Whether a check needs an account. The server decides, and enforces it.
  final bool required;

  /// "password", and "google" once Google sign-in is set up on the server.
  final List<String> providers;
  final int minPasswordLength;

  factory AuthConfig.fromJson(Map<String, dynamic> json) => AuthConfig(
    enabled: json['enabled'] as bool? ?? false,
    required: json['required'] as bool? ?? false,
    providers: ((json['providers'] as List?) ?? const []).map((e) => e as String).toList(),
    minPasswordLength: (json['min_password_length'] as num?)?.toInt() ?? 8,
  );
}

class Account {
  const Account({
    required this.id,
    required this.email,
    required this.plan,
    required this.balance,
    required this.used,
    required this.checks,
    required this.checkCost,
    required this.limited,
    this.name,
    this.avatarUrl,
    this.joinedAt,
    this.surveyDue = false,
  });

  final String id;
  final String email;
  final String? name;
  final String? avatarUrl;
  final String plan;
  final DateTime? joinedAt;

  final int balance;
  final int used;
  final int checks;
  final int checkCost;

  /// Whether the server refuses checks past the balance. False until plans exist.
  final bool limited;

  /// A new account that has not answered or skipped the four-question survey. The
  /// server keeps this, so it is asked once, whichever phone the person uses.
  final bool surveyDue;

  /// What to call the person: their name, else the part of their email before @.
  String get displayName =>
      (name != null && name!.trim().isNotEmpty) ? name!.trim() : email.split('@').first;

  factory Account.fromJson(Map<String, dynamic> json) {
    final credits = (json['credits'] as Map).cast<String, dynamic>();
    return Account(
      id: json['id'] as String,
      email: json['email'] as String,
      name: json['name'] as String?,
      avatarUrl: json['avatar_url'] as String?,
      plan: json['plan'] as String? ?? 'free',
      joinedAt: DateTime.tryParse(json['joined_at'] as String? ?? ''),
      balance: (credits['balance'] as num).toInt(),
      used: (credits['used'] as num).toInt(),
      checks: (credits['checks'] as num).toInt(),
      checkCost: (credits['check_cost'] as num).toInt(),
      limited: credits['limited'] as bool? ?? false,
      surveyDue: json['survey_due'] as bool? ?? false,
    );
  }
}

/// The survey's answers, by the keys the server accepts (app/accounts/credits.py).
/// Blank means the question was skipped.
class SurveyAnswers {
  const SurveyAnswers({this.role, this.places = const {}, this.wants = const {}, this.heard});

  static const roles = ['journalist', 'student', 'teacher', 'family', 'curious'];
  static const placeKeys = ['whatsapp', 'instagram', 'youtube', 'facebook', 'x', 'telegram', 'news_sites'];
  static const wantKeys = ['forwards', 'links', 'pictures', 'videos', 'voice'];
  static const heardKeys = ['friend', 'social', 'college', 'other'];

  final String? role;
  final Set<String> places;
  final Set<String> wants;
  final String? heard;

  Map<String, dynamic> toJson() => {
    'role': role,
    'places': places.toList(),
    'wants': wants.toList(),
    'heard': heard,
  };
}

/// A purchase started in the app and finished in the browser.
class PaymentHandoff {
  const PaymentHandoff({required this.id, required this.status, this.url, this.credits});

  final String id;

  /// waiting, opened (the browser has it), paid, failed, cancelled or expired.
  final String status;

  /// The one-time page to open; only on the answer that created the handoff.
  final String? url;

  /// Credits added, once paid.
  final int? credits;

  bool get finished => const {'paid', 'failed', 'cancelled', 'expired'}.contains(status);

  factory PaymentHandoff.fromJson(Map<String, dynamic> json) => PaymentHandoff(
    id: json['id'] as String,
    status: json['status'] as String? ?? 'waiting',
    url: json['url'] as String?,
    credits: (json['credits'] as num?)?.toInt(),
  );
}
