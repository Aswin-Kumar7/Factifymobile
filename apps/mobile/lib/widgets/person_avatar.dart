/// A person's picture, when their account has one (Google sign-in sends it), over
/// the [fallback] they are otherwise shown with - their initial.
///
/// The fallback is what is drawn while the picture loads, when it cannot be loaded
/// (offline, a link that has expired), and when there is none, so the avatar never
/// shows an empty circle or a broken-image icon. Only an https link is fetched.
/// The picture is held in Flutter's image cache like any other, and decoded at the
/// size it is shown.
library;

import 'package:flutter/material.dart';

class PersonAvatar extends StatelessWidget {
  const PersonAvatar({required this.url, required this.size, required this.fallback, super.key});

  final String? url;
  final double size;

  /// The initial, drawn the same size, as a circle.
  final Widget fallback;

  /// The link to fetch, or null when there is nothing safe to fetch.
  static Uri? usable(String? url) {
    if (url == null || url.trim().isEmpty) return null;
    final uri = Uri.tryParse(url.trim());
    return uri != null && uri.scheme == 'https' && uri.host.isNotEmpty ? uri : null;
  }

  @override
  Widget build(BuildContext context) {
    final uri = usable(url);
    if (uri == null) return fallback;
    final pixels = (size * MediaQuery.devicePixelRatioOf(context)).round();
    return SizedBox(
      width: size,
      height: size,
      child: ClipOval(
        child: Image.network(
          uri.toString(),
          width: size,
          height: size,
          fit: BoxFit.cover,
          cacheWidth: pixels,
          excludeFromSemantics: true,
          frameBuilder: (context, child, frame, synchronous) =>
              frame == null && !synchronous ? fallback : child,
          errorBuilder: (_, _, _) => fallback,
        ),
      ),
    );
  }
}
