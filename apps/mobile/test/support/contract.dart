/// The server's sample 1.8 responses, read from where the server keeps them
/// (tests/fixtures/contract at the root of the repository), so the app is built
/// against what the server sends rather than a copy that could drift from it.
///
/// link_complete, link_withheld, x_photo_post, instagram_reel_partial, youtube_video
/// and video_upload.
library;

import 'dart:convert';
import 'dart:io';

import 'package:factify_mobile/models/verdict.dart';

/// Every sample the server publishes.
const List<String> contractSamples = [
  'link_complete',
  'link_withheld',
  'x_photo_post',
  'instagram_reel_partial',
  'youtube_video',
  'video_upload',
];

/// `flutter test` runs from apps/mobile; the fixtures are two levels up.
File _fixture(String name) => File('../../tests/fixtures/contract/$name.json');

/// One sample response, as JSON.
Map<String, dynamic> contractJson(String name) =>
    jsonDecode(_fixture(name).readAsStringSync()) as Map<String, dynamic>;

/// One sample response, as the bytes a server would send.
List<int> contractBytes(String name) => _fixture(name).readAsBytesSync();

/// One sample response, parsed.
Verdict contractVerdict(String name) => Verdict.fromJson(contractJson(name));
