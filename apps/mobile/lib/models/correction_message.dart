/// The polite note sent back to the chat with the correction picture (contract 1.3,
/// `POST /v1/cases/{id}/correction-text`).
library;

class CorrectionMessage {
  const CorrectionMessage({required this.message, this.links = const []});

  final String message;

  /// The deciding sources' pages, best first. The first is already in [message].
  final List<String> links;

  factory CorrectionMessage.fromJson(Map<String, dynamic> json) => CorrectionMessage(
    message: json['message'] as String? ?? '',
    links: ((json['links'] as List?) ?? const []).whereType<String>().toList(),
  );
}
