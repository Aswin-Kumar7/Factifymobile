/// A signed-in person's account, and how the server says to sign in.
///
/// No display words live here (see lib/l10n). Every number comes from the server:
/// the app shows the balance it is given and never decides whether a check may run.
library;

class AuthConfig {
  const AuthConfig({
    required this.enabled,
    this.supabaseUrl,
    this.anonKey,
    this.required = false,
    this.providers = const [],
  });

  /// Sign-in is off: the server has no Supabase project key configured.
  static const AuthConfig off = AuthConfig(enabled: false);

  final bool enabled;
  final String? supabaseUrl;

  /// Supabase's public client key, made to ship in apps.
  final String? anonKey;
  final bool required;
  final List<String> providers;

  factory AuthConfig.fromJson(Map<String, dynamic> json) => AuthConfig(
    enabled: json['enabled'] as bool? ?? false,
    supabaseUrl: json['supabase_url'] as String?,
    anonKey: json['anon_key'] as String?,
    required: json['required'] as bool? ?? false,
    providers: ((json['providers'] as List?) ?? const []).map((e) => e as String).toList(),
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
    required this.deepCheckCost,
    required this.limited,
    this.name,
    this.avatarUrl,
    this.joinedAt,
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
  final int deepCheckCost;

  /// Whether the server refuses checks past the balance. False until plans exist.
  final bool limited;

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
      deepCheckCost: (credits['deep_check_cost'] as num).toInt(),
      limited: credits['limited'] as bool? ?? false,
    );
  }
}
