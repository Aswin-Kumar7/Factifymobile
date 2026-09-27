/// A cited passage in its article, as the source reader shows it (contract 1.3,
/// `GET /v1/cases/{id}/sources/{evidence_id}`).
///
/// Only the quoted paragraph and one either side ever arrive - the article itself
/// is read on the publisher's page - and [complete] says whether the page could be
/// read now at all.
library;

class SourceView {
  const SourceView({
    required this.url,
    required this.domain,
    required this.paragraphs,
    required this.quote,
    this.quoteParagraph,
    this.quoteStart,
    this.quoteEnd,
    this.publisher,
    this.headline,
    this.publishedAt,
    this.readMinutes,
    this.imageUrl,
    this.complete = false,
    this.limitations = const [],
  });

  final String url;
  final String domain;
  final List<String> paragraphs;
  final String quote;

  /// Which of [paragraphs] holds the quote, and where in it.
  final int? quoteParagraph;
  final int? quoteStart;
  final int? quoteEnd;
  final String? publisher;
  final String? headline;
  final DateTime? publishedAt;
  final int? readMinutes;

  /// On our own server, relative to it.
  final String? imageUrl;
  final bool complete;
  final List<String> limitations;

  factory SourceView.fromJson(Map<String, dynamic> json) {
    final quote = (json['quote'] as Map?)?.cast<String, dynamic>() ?? const {};
    return SourceView(
      url: json['url'] as String? ?? '',
      domain: json['domain'] as String? ?? '',
      paragraphs: [for (final p in (json['paragraphs'] as List? ?? const [])) '$p'],
      quote: quote['text'] as String? ?? '',
      quoteParagraph: (quote['paragraph_index'] as num?)?.toInt(),
      quoteStart: (quote['char_start'] as num?)?.toInt(),
      quoteEnd: (quote['char_end'] as num?)?.toInt(),
      publisher: json['publisher'] as String?,
      headline: json['headline'] as String?,
      publishedAt: DateTime.tryParse(json['published_at'] as String? ?? ''),
      readMinutes: (json['read_minutes'] as num?)?.toInt(),
      imageUrl: json['image_url'] as String?,
      complete: json['complete'] as bool? ?? false,
      limitations: [for (final l in (json['limitations'] as List? ?? const [])) '$l'],
    );
  }
}
