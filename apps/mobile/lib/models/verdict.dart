/// Wire models for the Factify contract (M41), contract_version 1.4 (read back to 1.0).
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

/// What a person is told, in the words they would use.
///
/// Sent by the server from contract 1.1 and always derived there from [VerdictAction],
/// so the two can never disagree. Parsed from the action when an older response has
/// no verdict field.
enum FactVerdict {
  trueClaim,
  falseClaim,

  /// Some of it is right and some of it is not (contract 1.4): one claim confirmed
  /// and another contradicted, or sources confirming only a smaller version.
  partlyTrue,
  misleading,
  unconfirmed;

  static FactVerdict parse(String? raw, VerdictAction action) => switch (raw) {
    'TRUE' => FactVerdict.trueClaim,
    'FALSE' => FactVerdict.falseClaim,
    'PARTLY_TRUE' => FactVerdict.partlyTrue,
    'MISLEADING' => FactVerdict.misleading,
    'UNCONFIRMED' => FactVerdict.unconfirmed,
    _ => fromAction(action),
  };

  /// A result kept from before 1.4 carries its verdict, so it reads as it did then;
  /// only a response with no verdict at all is read from its action.
  static FactVerdict fromAction(VerdictAction action) => switch (action) {
    VerdictAction.safeToShare => FactVerdict.trueClaim,
    VerdictAction.doNotShare => FactVerdict.falseClaim,
    VerdictAction.shareWithCorrection => FactVerdict.partlyTrue,
    VerdictAction.shareWithContext => FactVerdict.misleading,
    VerdictAction.waitAndRecheck || VerdictAction.sendToReview => FactVerdict.unconfirmed,
  };

  /// Whether the sources settled it one way or the other.
  bool get isDecided => this != FactVerdict.unconfirmed;
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

/// How one claim is shown: right, wrong, partly right, missing context or not
/// confirmed. Its status, with "partly true" told apart from "missing context" -
/// both arrive as MISLEADING_CONTEXT, and the rule that decided it says which
/// (contract 1.4).
enum ClaimMark {
  right,
  wrong,
  partly,
  missingContext,
  unconfirmed;

  static ClaimMark of(Claim claim) => switch (claim.status) {
    ClaimStatus.supported => ClaimMark.right,
    ClaimStatus.contradicted => ClaimMark.wrong,
    ClaimStatus.misleadingContext when claim.isPartlyTrue => ClaimMark.partly,
    ClaimStatus.misleadingContext => ClaimMark.missingContext,
    ClaimStatus.unverified => ClaimMark.unconfirmed,
  };
}

/// The earlier copy a media match points at (contract 1.3).
class EarlierMedia {
  const EarlierMedia({this.thumbnailUrl, this.publishedAt, this.publisher, this.similarity});

  /// Relative to our own server; never the third party's image.
  final String? thumbnailUrl;
  final DateTime? publishedAt;
  final String? publisher;

  /// 0-1: how closely the two pictures match.
  final double? similarity;

  static EarlierMedia? tryParse(Object? json) {
    if (json is! Map) return null;
    final map = json.cast<String, dynamic>();
    return EarlierMedia(
      thumbnailUrl: map['thumbnail_url'] as String?,
      publishedAt: DateTime.tryParse(map['published_at'] as String? ?? ''),
      publisher: map['publisher'] as String?,
      similarity: (map['similarity'] as num?)?.toDouble(),
    );
  }
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
    this.publishedOn,
    this.title,
    this.inputAnchor,
    this.credibility,
    this.earlierMedia,
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

  /// When we fetched the page - never shown as the article's date.
  final DateTime? observedAt;

  /// When the page itself says it was published (contract 1.3), and its headline.
  /// A source card showed [observedAt] here, dating a 2024 article to the day we
  /// read it.
  final DateTime? publishedOn;
  final String? title;

  /// A media match's earlier copy, for the side-by-side (contract 1.3). Its
  /// thumbnail, when there is one, is on our own server.
  final EarlierMedia? earlierMedia;
  final InputAnchor? inputAnchor;

  /// HIGH, MEDIUM or LOW, from the server's curated publisher list. Absent on a
  /// source that predates the relevance check.
  final String? credibility;

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
    publishedOn: DateTime.tryParse(json['published_on'] as String? ?? ''),
    earlierMedia: EarlierMedia.tryParse(json['earlier_media']),
    title: json['title'] as String?,
    inputAnchor: json['input_anchor'] == null
        ? null
        : InputAnchor.fromJson((json['input_anchor'] as Map).cast<String, dynamic>()),
    credibility: json['credibility'] as String?,
  );

  /// The publisher's name, or the site it was published on.
  String get sourceName {
    final name = publisher;
    if (name != null && name.trim().isNotEmpty) return name;
    return Uri.tryParse(citationUrl)?.host.replaceFirst('www.', '') ?? citationUrl;
  }

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
    this.confidence,
    this.explanation,
    this.search,
    this.sourcesLookedAt,
    this.ownAnchor,
    this.technique,
    this.language,
    this.ruleId,
    this.inFull,
  });

  final String id;
  final String text;
  final String claimType;

  /// A claim not made in English, as one self-contained English sentence (1.4):
  /// "NASA launched Chandrayaan-3" for a claim whose words say "NASA launched it".
  final String? inFull;

  /// The rule that decided this claim. `rule.narrower_scope` is a claim sources
  /// confirm only in a smaller version: partly true (contract 1.4).
  final String? ruleId;

  /// The language the claim was made in: en, hi, or bn mr te ta gu ur kn or ml pa.
  final String? language;
  final ClaimStatus status;
  final String severity;
  final String importance;
  final String reason;
  final Strength strength;
  final List<Evidence> evidence;

  /// 50-97 when this claim was decided, null when it was not.
  final int? confidence;

  /// One or two plain sentences on what the sources show. Only sent for a
  /// decided claim, so it can never disagree with the badge beside it.
  final String? explanation;

  /// Whether the web was searched for this claim: "searched", "timed_out" or
  /// "unavailable" (the news search could not be reached). "not_searched" only on a
  /// result kept from before 1.4, when a quick check searched three claims. Null on
  /// results stored before the server recorded it.
  final String? search;

  /// How many pages were read for this claim, whatever they said.
  final int? sourcesLookedAt;

  bool get wasNotSearched => search == 'not_searched';

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
    confidence: (json['confidence'] as num?)?.toInt(),
    explanation: json['explanation'] as String?,
    search: json['search'] as String?,
    sourcesLookedAt: (json['sources_looked_at'] as num?)?.toInt(),
    ownAnchor: json['input_anchor'] == null
        ? null
        : InputAnchor.fromJson((json['input_anchor'] as Map).cast<String, dynamic>()),
    technique: json['technique'] as String?,
    language: json['language'] as String?,
    ruleId: json['rule_id'] as String?,
    inFull: json['in_full'] as String?,
  );

  bool get isDecisive => status.isDecisive;

  /// How this claim is shown: right, wrong, partly right, missing context, unconfirmed.
  ClaimMark get mark => ClaimMark.of(this);

  /// Sources confirm only a smaller version of this claim: one state's scheme for
  /// the government's, a one-time payment for a monthly one. Partly true.
  bool get isPartlyTrue =>
      status == ClaimStatus.misleadingContext && ruleId == 'rule.narrower_scope';

  /// What the sources actually report, for a claim that is partly true: the
  /// citations that show the smaller version.
  List<Evidence> get smallerVersion => evidence
      .where(
        (e) =>
            e.direction == 'contextualizes' && e.matchBasis.metric.startsWith('passage_narrower'),
      )
      .toList();
  List<Evidence> get contradicting => evidence.where((e) => e.contradicts).toList();
  List<Evidence> get supporting => evidence.where((e) => e.supports).toList();

  /// Where the claim sits in the submission, as the server located it (contract
  /// 1.3). Null from an older server.
  final InputAnchor? ownAnchor;

  /// The manipulation technique the server named for a contradicted or
  /// recontextualised claim (contract 1.3): RECYCLED_MEDIA, MISSING_CONTEXT,
  /// MISATTRIBUTED_QUOTE, TWISTED_NUMBER or WRONG_IDENTITY. Null otherwise.
  final String? technique;

  /// Where the claim sits in the submission: its own anchor, else the first
  /// evidence item's (contracts before 1.3 carried it per citation only).
  InputAnchor? get inputAnchor {
    final own = ownAnchor;
    if (own != null && !own.isEmpty) return own;
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

/// What was read from an uploaded picture: its text, and what it shows.
///
/// The claims were extracted from [text], so showing it lets a person see exactly
/// what was checked, and catch a misread before trusting the verdict built on it.
/// [description] is context, never evidence.
/// The picture checks: what can be said about an uploaded picture or video itself
/// (contract 1.3, app/media/report.py). Four answers, each able to say "not checked".
///
/// None of it is a verdict. The detector and editing values are signals - a
/// classifier's estimate, a forensic description - shown as such and never scored.
class MediaReport {
  const MediaReport({
    required this.kind,
    required this.credentials,
    required this.history,
    required this.detector,
    required this.editing,
    this.frames,
  });

  /// image or video.
  final String kind;
  final MediaCredentials credentials;
  final MediaHistory history;
  final MediaDetector detector;
  final MediaEditing editing;

  /// For a video, how many still frames were checked.
  final int? frames;

  bool get isVideo => kind == 'video';

  static MediaReport? tryParse(Object? json) {
    if (json is! Map) return null;
    final map = json.cast<String, dynamic>();
    Map<String, dynamic> part(String key) =>
        (map[key] is Map ? (map[key] as Map).cast<String, dynamic>() : const <String, dynamic>{});
    return MediaReport(
      kind: map['kind'] as String? ?? 'image',
      credentials: MediaCredentials.fromJson(part('credentials')),
      history: MediaHistory.fromJson(part('history')),
      detector: MediaDetector.fromJson(part('detector')),
      editing: MediaEditing.fromJson(part('editing')),
      frames: (map['frames'] as num?)?.toInt(),
    );
  }
}

class MediaCredentials {
  const MediaCredentials({
    required this.status,
    this.signer,
    this.declaresAi = false,
    this.generator,
  });

  /// valid, untrusted, invalid, none or unavailable.
  final String status;
  final String? signer;

  /// The file itself says an AI tool made it - what the file says, not our finding.
  final bool declaresAi;
  final String? generator;

  factory MediaCredentials.fromJson(Map<String, dynamic> json) => MediaCredentials(
    status: json['status'] as String? ?? 'unavailable',
    signer: json['signer'] as String?,
    declaresAi: json['declares_ai'] as bool? ?? false,
    generator: json['generator'] as String?,
  );
}

class MediaHistory {
  const MediaHistory({
    required this.status,
    this.pages = 0,
    this.dated = 0,
    this.earliest,
    this.why,
  });

  /// found, none or not_checked.
  final String status;
  final int pages;
  final int dated;
  final EarlierCopy? earliest;

  /// Why it was not checked (contract 1.5): off (not set up on this server) or
  /// failed. Null when it was checked, or from an older server.
  final String? why;

  factory MediaHistory.fromJson(Map<String, dynamic> json) => MediaHistory(
    status: json['status'] as String? ?? 'not_checked',
    why: json['why'] as String?,
    pages: (json['pages'] as num?)?.toInt() ?? 0,
    dated: (json['dated'] as num?)?.toInt() ?? 0,
    earliest: json['earliest'] is Map
        ? EarlierCopy.fromJson((json['earliest'] as Map).cast<String, dynamic>())
        : null,
  );
}

class EarlierCopy {
  const EarlierCopy({
    required this.url,
    required this.publishedAt,
    this.publisher,
    this.daysBefore,
    this.thumbnailUrl,
  });

  final String url;
  final DateTime publishedAt;
  final String? publisher;
  final int? daysBefore;

  /// On our own server, relative to it; never the third party's copy.
  final String? thumbnailUrl;

  /// Online a month or more before the check: not a new picture.
  bool get isOld => (daysBefore ?? 0) >= 30;

  factory EarlierCopy.fromJson(Map<String, dynamic> json) => EarlierCopy(
    url: json['url'] as String? ?? '',
    publishedAt: DateTime.tryParse(json['published_at'] as String? ?? '') ?? DateTime(1970),
    publisher: json['publisher'] as String?,
    daysBefore: (json['days_before'] as num?)?.toInt(),
    thumbnailUrl: json['thumbnail_url'] as String?,
  );
}

class MediaDetector {
  const MediaDetector({
    required this.status,
    this.generated,
    this.faceSwap,
    this.secondOpinion,
    this.agreement,
    this.faces,
    this.voice,
    this.onServer = false,
    this.why,
  });

  /// checked or not_checked.
  final String status;

  /// Why it was not checked (contract 1.5): text_card, too_small, unreadable, off
  /// or failed. Null when it was checked, or from an older server.
  final String? why;

  /// 0-1 likelihoods from an AI-image detector: an estimate, never a finding.
  final double? generated;
  final double? faceSwap;

  /// A second AI-picture model; both must agree before "likely AI-made".
  final double? secondOpinion;

  /// likely_ai, unclear or no_sign - never "real".
  final String? agreement;

  /// Faces the face-swap model judged; null when it did not run.
  final int? faces;

  /// A video's sound: likelihood of a machine-made voice. Experimental.
  final double? voice;

  /// These detectors ran on Factify's own server (other checks may use providers).
  final bool onServer;

  bool get checked => status == 'checked';

  factory MediaDetector.fromJson(Map<String, dynamic> json) => MediaDetector(
    status: json['status'] as String? ?? 'not_checked',
    why: json['why'] as String?,
    generated: (json['generated'] as num?)?.toDouble(),
    faceSwap: (json['face_swap'] as num?)?.toDouble(),
    secondOpinion: (json['second_opinion'] as num?)?.toDouble(),
    agreement: json['agreement'] as String?,
    faces: (json['faces'] as num?)?.toInt(),
    voice: (json['voice'] as num?)?.toDouble(),
    onServer: json['on_server'] as bool? ?? false,
  );
}

class MediaEditing {
  const MediaEditing({required this.status, this.unevenNoise = false, this.spectralPeaks = false});

  /// checked or not_checked.
  final String status;
  final bool unevenNoise;
  final bool spectralPeaks;

  bool get checked => status == 'checked';

  factory MediaEditing.fromJson(Map<String, dynamic> json) => MediaEditing(
    status: json['status'] as String? ?? 'not_checked',
    unevenNoise: json['uneven_noise'] as bool? ?? false,
    spectralPeaks: json['spectral_peaks'] as bool? ?? false,
  );
}

class ImageReading {
  const ImageReading({
    required this.text,
    this.description,
    this.kind,
    this.publisher,
    this.language,
  });

  factory ImageReading.fromJson(Map<String, dynamic> json) => ImageReading(
    text: json['text'] as String? ?? '',
    description: json['description'] as String?,
    kind: json['kind'] as String?,
    publisher: json['publisher'] as String?,
    language: json['language'] as String?,
  );

  final String text;
  final String? description;

  /// NEWS_ARTICLE, SOCIAL_POST, CHAT_MESSAGE, TV_GRAPHIC, POSTER, DOCUMENT, PHOTO,
  /// MEME or OTHER.
  final String? kind;

  /// The outlet, channel or account the picture carries, as written on it.
  final String? publisher;
  final String? language;

  bool get hasText => text.trim().isNotEmpty;
}

/// A complete verification result.
class Verdict {
  const Verdict({
    required this.caseId,
    required this.action,
    required this.actionReason,
    this.verdict,
    this.confidence,
    this.summary,
    required this.claims,
    required this.advisories,
    required this.skipped,
    required this.retrievedAt,
    required this.fromCache,
    required this.elapsedMs,
    this.completenessNote,
    this.receiptUrl,
    this.receipt,
    this.recurrence,
    this.mediaProvenance,
    this.sourceRisk = 'UNKNOWN',
    this.imageReading,
    this.mediaReport,
    this.raw = const {},
  });

  final String caseId;
  final VerdictAction action;
  final String actionReason;

  final FactVerdict? verdict;

  /// 50-97 for a decided verdict, null for [FactVerdict.unconfirmed].
  final int? confidence;

  /// One plain sentence for the whole result, from the claim that decided it.
  final String? summary;

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

  /// The receipt, checked by the server as it sent this result (contract 1.3). Null
  /// from older servers and when no receipt was issued.
  final ReceiptSummary? receipt;
  final Recurrence? recurrence;
  final MediaProvenance? mediaProvenance;
  final String sourceRisk;

  /// For an uploaded picture: what was read in it. Null for text and links.
  final ImageReading? imageReading;

  /// For an uploaded picture or video: the checks of the upload itself (contract
  /// 1.3). Beside the verdict, never inside it.
  final MediaReport? mediaReport;

  /// The claim the checked thing is mainly about: the headline claim, else the
  /// first. Null when nothing checkable was found.
  ///
  /// A picture's MEDIA claim is never it: that sentence is the server's own
  /// question ("This image has been published before...") and not something the
  /// picture says, yet it titled a landscape in History and on Home.
  String? get headline {
    final said = claims.where((c) => c.claimType != 'MEDIA');
    for (final claim in said) {
      if (claim.importance == 'HEADLINE') return claim.text;
    }
    return said.isEmpty ? null : said.first.text;
  }

  /// The response exactly as the server sent it, so a check kept in history on this
  /// phone is shown again from the same data, citations and all.
  final Map<String, dynamic> raw;

  factory Verdict.fromJson(Map<String, dynamic> json) {
    final action = VerdictAction.parse(json['action'] as String);
    return Verdict._fromJson(json, action);
  }

  factory Verdict._fromJson(Map<String, dynamic> json, VerdictAction action) => Verdict(
    caseId: json['case_id'] as String,
    action: action,
    actionReason: json['action_reason'] as String? ?? '',
    verdict: FactVerdict.parse(json['verdict'] as String?, action),
    confidence: (json['confidence'] as num?)?.toInt(),
    summary: json['summary'] as String?,
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
    receipt: ReceiptSummary.tryParse(json['receipt']),
    recurrence: json['recurrence'] == null
        ? null
        : Recurrence.fromJson((json['recurrence'] as Map).cast<String, dynamic>()),
    mediaProvenance: json['media_provenance'] == null
        ? null
        : MediaProvenance.fromJson((json['media_provenance'] as Map).cast<String, dynamic>()),
    sourceRisk: json['source_risk'] as String? ?? 'UNKNOWN',
    imageReading: json['image_reading'] == null
        ? null
        : ImageReading.fromJson((json['image_reading'] as Map).cast<String, dynamic>()),
    mediaReport: MediaReport.tryParse(json['media_report']),
    raw: json,
  );

  List<Evidence> get allEvidence => [for (final c in claims) ...c.evidence];

  /// The verdict, derived from the action when the response predates the field.
  FactVerdict get factVerdict => verdict ?? FactVerdict.fromAction(action);

  bool get isComplete => skipped.isEmpty;

  /// True when nothing could be established.
  ///
  /// Distinct from "found to be false", and the interface must never merge the
  /// two: abstaining is the designed answer, not a failed one.
  bool get abstained => claims.isEmpty || claims.every((c) => !c.isDecisive);

  /// Nothing in what was checked says anything a source could settle: no claim was
  /// found in it, or the only question asked was a picture's own history and no
  /// earlier copy of it turned up. Not "unconfirmed" - there is nothing to confirm,
  /// and a sunset photo or a joke must not be told to "treat it with caution".
  ///
  /// Never when reading or extraction failed: no claims then means nothing was
  /// read, not that nothing was said.
  bool get nothingToCheck =>
      factVerdict == FactVerdict.unconfirmed &&
      claims.every((c) => c.claimType == 'MEDIA' && !c.isDecisive && c.evidence.isEmpty) &&
      !skipped.any((s) => _readingChecks.contains(s.check));

  static const _readingChecks = {'claim_extraction', 'image_text', 'document_text'};

  /// The news search could not be reached for some claim, so the answer rests on
  /// less than a check normally reads.
  bool get searchUnavailable => claims.any((c) => c.search == 'unavailable');
}

/// The receipt a result carries inline (contract 1.3): enough for the seal.
class ReceiptSummary {
  const ReceiptSummary({required this.receiptId, required this.verified, this.issuedAt});

  final String receiptId;

  /// Whether it verified against the stored evidence when the result was sent.
  final bool verified;
  final DateTime? issuedAt;

  static ReceiptSummary? tryParse(Object? json) {
    if (json is! Map) return null;
    final id = json['receipt_id'];
    if (id is! String || id.isEmpty) return null;
    return ReceiptSummary(
      receiptId: id,
      verified: json['verified'] == true,
      issuedAt: DateTime.tryParse(json['issued_at'] as String? ?? ''),
    );
  }
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
