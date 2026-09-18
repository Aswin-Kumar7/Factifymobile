/// Wire models for the Facify contract (M41), contract_version 1.0.
///
/// Mirrors app/api/schemas.py field for field. Two properties of the server
/// contract are load-bearing and are preserved deliberately:
///
///   * [Advisory] is a separate class from [Evidence] with no shared supertype,
///     so a list of one can never hold the other. That mirrors the server, where
///     advisories are a sibling of claims rather than an entry inside evidence.
///   * A decisive status always arrives with citations. The server refuses to
///     serialise otherwise, so the UI can rely on it rather than re-checking.
library;

/// The user-facing action, rolled up from every claim.
enum VerdictAction {
  safeToShare,
  shareWithContext,
  shareWithCorrection,
  doNotShare,
  waitAndRecheck,
  sendToReview;

  static VerdictAction parse(String raw) => switch (raw) {
    'SAFE_TO_SHARE' => VerdictAction.safeToShare,
    'SHARE_WITH_CONTEXT' => VerdictAction.shareWithContext,
    'SHARE_WITH_CORRECTION' => VerdictAction.shareWithCorrection,
    'DO_NOT_SHARE' => VerdictAction.doNotShare,
    'WAIT_AND_RECHECK' => VerdictAction.waitAndRecheck,
    _ => VerdictAction.sendToReview,
  };

  /// Whether this is a conclusion rather than a referral.
  ///
  /// `sendToReview` is the designed answer for cases the system correctly
  /// refuses to decide, so the interface must not style it as a failure.
  bool get isConclusion => this != VerdictAction.sendToReview;
}

enum ClaimStatus {
  supported,
  contradicted,
  misleadingContext,
  unverified;

  static ClaimStatus parse(String raw) => switch (raw) {
    'SUPPORTED' => ClaimStatus.supported,
    'CONTRADICTED' => ClaimStatus.contradicted,
    'MISLEADING_CONTEXT' => ClaimStatus.misleadingContext,
    _ => ClaimStatus.unverified,
  };

  /// Mirrors `ClaimStatus.is_decisive` on the server.
  bool get isDecisive => this != ClaimStatus.unverified;
}

class SourceAnchor {
  const SourceAnchor({this.charStart, this.charEnd, this.paragraphIndex, this.pageNumber});

  final int? charStart;
  final int? charEnd;
  final int? paragraphIndex;
  final int? pageNumber;

  factory SourceAnchor.fromJson(Map<String, dynamic> json) => SourceAnchor(
    charStart: json['char_start'] as int?,
    charEnd: json['char_end'] as int?,
    paragraphIndex: json['paragraph_index'] as int?,
    pageNumber: json['page_number'] as int?,
  );
}

/// Where in the submission a claim was made: a span of the message, a page of a
/// document, or a moment in a video.
///
/// Parsed so the evidence screen can show it. The server does not populate it yet
/// (B8 in docs/hackathon-workflow.md), and a claim without one shows no location
/// rather than a guessed one.
class InputAnchor {
  const InputAnchor({this.charStart, this.charEnd, this.pageNumber, this.frameStartMs});

  final int? charStart;
  final int? charEnd;
  final int? pageNumber;
  final int? frameStartMs;

  factory InputAnchor.fromJson(Map<String, dynamic> json) => InputAnchor(
    charStart: json['char_start'] as int?,
    charEnd: json['char_end'] as int?,
    pageNumber: json['page_number'] as int?,
    frameStartMs: json['frame_start_ms'] as int?,
  );

  bool get isEmpty => charStart == null && pageNumber == null && frameStartMs == null;
}

/// The metric behind a match and the threshold it was judged against.
///
/// Rendered rather than hidden: it is what lets a reader recompute the match
/// quality instead of trusting it.
class MatchBasis {
  const MatchBasis({required this.metric, required this.value, required this.threshold});

  final String metric;
  final double value;
  final double threshold;

  factory MatchBasis.fromJson(Map<String, dynamic> json) => MatchBasis(
    metric: json['metric'] as String? ?? 'unspecified',
    value: (json['value'] as num?)?.toDouble() ?? 0,
    threshold: (json['threshold'] as num?)?.toDouble() ?? 0,
  );

  double get margin => value - threshold;
}

/// One citable finding. Everything here points at something that was fetched.
class Evidence {
  const Evidence({
    required this.id,
    required this.tier,
    required this.kind,
    required this.direction,
    required this.method,
    required this.finding,
    required this.citationUrl,
    required this.sourceExcerpt,
    required this.sourceAnchor,
    required this.matchBasis,
    required this.matchQuality,
    this.publisher,
    this.observedAt,
    this.inputAnchor,
  });

  final String id;
  final String tier;
  final String kind;
  final String direction;
  final String method;
  final String finding;
  final String citationUrl;
  final String sourceExcerpt;
  final SourceAnchor sourceAnchor;
  final MatchBasis matchBasis;
  final String matchQuality;
  final String? publisher;
  final DateTime? observedAt;
  final InputAnchor? inputAnchor;

  factory Evidence.fromJson(Map<String, dynamic> json) => Evidence(
    id: json['id'] as String,
    tier: json['tier'] as String,
    kind: json['kind'] as String,
    direction: json['direction'] as String,
    method: json['method'] as String,
    finding: json['finding'] as String,
    citationUrl: json['citation_url'] as String,
    sourceExcerpt: json['source_excerpt'] as String,
    sourceAnchor: SourceAnchor.fromJson(
      (json['source_anchor'] as Map?)?.cast<String, dynamic>() ?? const {},
    ),
    matchBasis: MatchBasis.fromJson(
      (json['match_basis'] as Map?)?.cast<String, dynamic>() ?? const {},
    ),
    matchQuality: json['match_quality'] as String? ?? 'WEAK',
    publisher: json['publisher'] as String?,
    observedAt: DateTime.tryParse(json['observed_at'] as String? ?? ''),
    inputAnchor: json['input_anchor'] == null
        ? null
        : InputAnchor.fromJson((json['input_anchor'] as Map).cast<String, dynamic>()),
  );

  bool get contradicts => direction == 'contradicts';
  bool get supports => direction == 'supports';

  /// The submitted media matched an earlier publication of it.
  bool get isMediaMatch => kind == 'media_match';
}

/// A Tier E signal.
///
/// Deliberately not a subclass of [Evidence] and sharing no supertype with it,
/// so no list, widget or function can accept one where the other belongs. This
/// is the client half of the rule that model output never enters a verdict.
class Advisory {
  const Advisory({
    required this.id,
    required this.provider,
    required this.signal,
    required this.note,
    required this.excludedNote,
    this.score,
  });

  final String id;
  final String provider;
  final String signal;
  final String note;

  /// Travels with every item, so the caveat is data rather than something the
  /// client has to remember to draw.
  final String excludedNote;
  final double? score;

  factory Advisory.fromJson(Map<String, dynamic> json) => Advisory(
    id: json['id'] as String,
    provider: json['provider'] as String,
    signal: json['signal'] as String,
    note: json['note'] as String,
    excludedNote: json['excluded_note'] as String? ?? 'Forensic signal - not used in this verdict.',
    score: (json['score'] as num?)?.toDouble(),
  );
}

class StrengthComponent {
  const StrengthComponent({
    required this.name,
    required this.value,
    required this.explanation,
    this.citations = const [],
  });

  final String name;
  final double value;
  final String explanation;

  /// The citation URLs this component was computed from. The server records them
  /// but does not send them yet (B9); a component without them is not a link.
  final List<String> citations;

  factory StrengthComponent.fromJson(Map<String, dynamic> json) => StrengthComponent(
    name: json['name'] as String,
    value: (json['value'] as num?)?.toDouble() ?? 0,
    explanation: json['explanation'] as String? ?? '',
    citations: ((json['citations'] as List?) ?? const []).map((e) => e as String).toList(),
  );
}

/// The explainable score. Not a probability, and not a model confidence.
class Strength {
  const Strength({
    required this.score,
    required this.band,
    required this.components,
    required this.advisoryExcluded,
  });

  final double score;
  final String band;
  final List<StrengthComponent> components;

  /// Providers whose signals were reported but not counted.
  final List<String> advisoryExcluded;

  factory Strength.fromJson(Map<String, dynamic> json) => Strength(
    score: (json['score'] as num?)?.toDouble() ?? 0,
    band: json['band'] as String? ?? 'NONE',
    components: ((json['components'] as List?) ?? const [])
        .map((e) => StrengthComponent.fromJson((e as Map).cast<String, dynamic>()))
        .toList(),
    advisoryExcluded: ((json['advisory_excluded'] as List?) ?? const [])
        .map((e) => e as String)
        .toList(),
  );
}

class Claim {
  const Claim({
    required this.id,
    required this.text,
    required this.claimType,
    required this.status,
    required this.severity,
    required this.importance,
    required this.reason,
    required this.strength,
    required this.evidence,
  });

  final String id;
  final String text;
  final String claimType;
  final ClaimStatus status;
  final String severity;
  final String importance;
  final String reason;
  final Strength strength;
  final List<Evidence> evidence;

  factory Claim.fromJson(Map<String, dynamic> json) => Claim(
    id: json['id'] as String,
    text: json['text'] as String,
    claimType: json['claim_type'] as String,
    status: ClaimStatus.parse(json['status'] as String),
    severity: json['severity'] as String,
    importance: json['importance'] as String,
    reason: json['reason'] as String,
    strength: Strength.fromJson((json['strength'] as Map).cast<String, dynamic>()),
    evidence: ((json['evidence'] as List?) ?? const [])
        .map((e) => Evidence.fromJson((e as Map).cast<String, dynamic>()))
        .toList(),
  );

  bool get isDecisive => status.isDecisive;
  List<Evidence> get contradicting => evidence.where((e) => e.contradicts).toList();
  List<Evidence> get supporting => evidence.where((e) => e.supports).toList();

  /// Where the claim sits in the submission, from the first evidence item that
  /// recorded it. The contract carries the anchor per citation, not per claim.
  InputAnchor? get inputAnchor {
    for (final item in evidence) {
      final anchor = item.inputAnchor;
      if (anchor != null && !anchor.isEmpty) return anchor;
    }
    return null;
  }
}

/// Something the pipeline could not do, and why.
class SkippedCheck {
  const SkippedCheck({required this.check, required this.reason});

  final String check;
  final String reason;

  factory SkippedCheck.fromJson(Map<String, dynamic> json) =>
      SkippedCheck(check: json['check'] as String, reason: json['reason'] as String);
}

class Recurrence {
  const Recurrence({
    required this.timesSeen,
    required this.distinctCaptions,
    required this.languages,
    required this.summary,
    this.firstVerifiedAt,
  });

  final int timesSeen;
  final int distinctCaptions;
  final List<String> languages;
  final String summary;
  final DateTime? firstVerifiedAt;

  factory Recurrence.fromJson(Map<String, dynamic> json) => Recurrence(
    timesSeen: json['times_seen'] as int? ?? 0,
    distinctCaptions: json['distinct_captions'] as int? ?? 0,
    languages: ((json['languages'] as List?) ?? const []).map((e) => e as String).toList(),
    summary: json['summary'] as String? ?? '',
    firstVerifiedAt: DateTime.tryParse(json['first_verified_at'] as String? ?? ''),
  );

  bool get hasContradictoryCaptions => distinctCaptions >= 2;
}

class MediaProvenance {
  const MediaProvenance({
    required this.present,
    required this.valid,
    required this.summary,
    this.signer,
  });

  final bool present;
  final bool valid;
  final String summary;
  final String? signer;

  factory MediaProvenance.fromJson(Map<String, dynamic> json) => MediaProvenance(
    present: json['present'] as bool? ?? false,
    valid: json['valid'] as bool? ?? false,
    summary: json['summary'] as String? ?? '',
    signer: json['signer'] as String?,
  );
}

/// A complete verification result.
class Verdict {
  const Verdict({
    required this.caseId,
    required this.action,
    required this.actionReason,
    required this.claims,
    required this.advisories,
    required this.skipped,
    required this.retrievedAt,
    required this.fromCache,
    required this.elapsedMs,
    this.completenessNote,
    this.receiptUrl,
    this.recurrence,
    this.mediaProvenance,
    this.sourceRisk = 'UNKNOWN',
  });

  final String caseId;
  final VerdictAction action;
  final String actionReason;
  final List<Claim> claims;

  /// A sibling of [claims], never nested inside one.
  final List<Advisory> advisories;
  final List<SkippedCheck> skipped;

  /// When the evidence was gathered. Required by the contract and always shown:
  /// a verdict without it is a claim about the present made from evidence about
  /// the past.
  final DateTime retrievedAt;
  final bool fromCache;
  final int elapsedMs;
  final String? completenessNote;
  final String? receiptUrl;
  final Recurrence? recurrence;
  final MediaProvenance? mediaProvenance;
  final String sourceRisk;

  factory Verdict.fromJson(Map<String, dynamic> json) => Verdict(
    caseId: json['case_id'] as String,
    action: VerdictAction.parse(json['action'] as String),
    actionReason: json['action_reason'] as String? ?? '',
    claims: ((json['claims'] as List?) ?? const [])
        .map((e) => Claim.fromJson((e as Map).cast<String, dynamic>()))
        .toList(),
    advisories: ((json['advisories'] as List?) ?? const [])
        .map((e) => Advisory.fromJson((e as Map).cast<String, dynamic>()))
        .toList(),
    skipped: ((json['skipped'] as List?) ?? const [])
        .map((e) => SkippedCheck.fromJson((e as Map).cast<String, dynamic>()))
        .toList(),
    retrievedAt: DateTime.tryParse(json['retrieved_at'] as String? ?? '') ?? DateTime.now(),
    fromCache: json['from_cache'] as bool? ?? false,
    elapsedMs: json['elapsed_ms'] as int? ?? 0,
    completenessNote: json['completeness_note'] as String?,
    receiptUrl: json['receipt_url'] as String?,
    recurrence: json['recurrence'] == null
        ? null
        : Recurrence.fromJson((json['recurrence'] as Map).cast<String, dynamic>()),
    mediaProvenance: json['media_provenance'] == null
        ? null
        : MediaProvenance.fromJson((json['media_provenance'] as Map).cast<String, dynamic>()),
    sourceRisk: json['source_risk'] as String? ?? 'UNKNOWN',
  );

  List<Evidence> get allEvidence => [for (final c in claims) ...c.evidence];

  bool get isComplete => skipped.isEmpty;

  /// True when nothing could be established.
  ///
  /// Distinct from "found to be false", and the interface must never merge the
  /// two: abstaining is the designed answer, not a failed one.
  bool get abstained => claims.isEmpty || claims.every((c) => !c.isDecisive);
}

/// A tamper-evident receipt for a verdict, and the result of checking it (M42).
///
/// The value is entirely in [verified]. A receipt that verifies says the evidence
/// behind this verdict is byte-for-byte what was signed when the verdict was made;
/// one that fails says it has changed since. Showing the receipt without the check
/// would be showing a seal nobody looked at.
class Receipt {
  const Receipt({
    required this.receiptId,
    required this.caseId,
    required this.evidenceDigest,
    required this.issuedAt,
    required this.action,
    required this.evidenceCount,
    required this.verified,
    required this.verificationReason,
    required this.disclaimer,
  });

  final String receiptId;
  final String caseId;
  final String evidenceDigest;
  final DateTime issuedAt;
  final String action;
  final int evidenceCount;
  final bool verified;
  final String verificationReason;
  final String disclaimer;

  factory Receipt.fromJson(Map<String, dynamic> json) => Receipt(
    receiptId: json['receipt_id'] as String,
    caseId: json['case_id'] as String,
    evidenceDigest: json['evidence_digest'] as String,
    issuedAt: DateTime.parse(json['issued_at'] as String),
    action: json['action'] as String? ?? '',
    evidenceCount: (json['evidence_count'] as num?)?.toInt() ?? 0,
    verified: json['verified'] as bool? ?? false,
    verificationReason: json['verification_reason'] as String? ?? '',
    disclaimer: json['disclaimer'] as String? ?? '',
  );
}
