"""Which links are social posts, and the one address each is known and cached by.

A post is shared under many addresses, and every one of them used to be a separate
cache entry and a separate fetch of a page that, for a post, holds almost nothing a
reader can use. These tests pin the forms people actually paste, what each folds to,
and that a link that is not a post is left to be read as a web page.
"""

from __future__ import annotations

import pytest

from app.intake import normalizer
from app.intake.normalizer import normalise_url
from app.intake.social_urls import (
    READER_VERSION,
    VIDEO_READER_VERSION,
    Platform,
    PostRef,
    is_platform_host,
    is_video_route,
    recognise,
)

pytestmark = pytest.mark.unit


def _ref(url: str) -> PostRef:
    ref = recognise(url)
    assert ref is not None, url
    return ref


class TestX:
    @pytest.mark.parametrize(
        "url",
        [
            "https://x.com/OneObjective_/status/2105264647691440217",
            "https://twitter.com/OneObjective_/status/2105264647691440217?s=46&t=AbCdEf",
            "https://mobile.twitter.com/OneObjective_/status/2105264647691440217",
            "https://www.x.com/OneObjective_/status/2105264647691440217/video/1",
            "https://x.com/i/status/2105264647691440217",
            "https://x.com/i/web/status/2105264647691440217",
            "https://fxtwitter.com/OneObjective_/status/2105264647691440217",
            "https://vxtwitter.com/OneObjective_/status/2105264647691440217",
            "https://fixupx.com/OneObjective_/status/2105264647691440217",
            "https://twitter.com/OneObjective_/statuses/2105264647691440217",
        ],
    )
    def test_every_form_of_a_post_folds_to_one_address(self, url: str) -> None:
        ref = _ref(url)

        assert ref.platform is Platform.X
        assert ref.post_id == "2105264647691440217"
        assert ref.kind == "post"
        assert ref.canonical_url == "https://x.com/i/status/2105264647691440217"
        assert not ref.needs_resolving

    def test_a_short_link_is_followed_by_the_reader(self) -> None:
        ref = _ref("https://t.co/2jTzXCmlWQ")

        assert ref.platform is Platform.X and ref.needs_resolving and ref.post_id is None

    @pytest.mark.parametrize(
        "url",
        [
            "https://x.com/OneObjective_",  # a profile
            "https://x.com/search?q=flydubai",
            "https://x.com/OneObjective_/status/not-a-number",
            "https://x.com/home",
        ],
    )
    def test_what_is_not_a_post_is_left_to_the_web_reader(self, url: str) -> None:
        assert recognise(url) is None

    def test_an_x_post_is_not_known_to_be_a_video_from_its_address(self) -> None:
        assert not is_video_route(_ref("https://x.com/a/status/2105264647691440217/video/1"))


class TestInstagram:
    @pytest.mark.parametrize(
        ("url", "kind", "canonical"),
        [
            (
                "https://www.instagram.com/p/Dd-ghgbkrzL/?igsh=MTc4MmM1YmI2Ng==",
                "post",
                "https://www.instagram.com/p/Dd-ghgbkrzL/",
            ),
            (
                "https://instagram.com/the_hindu/p/Dd-ghgbkrzL",
                "post",
                "https://www.instagram.com/p/Dd-ghgbkrzL/",
            ),
            (
                "https://www.instagram.com/reel/Dd90zQtDzon/?utm_source=ig_web_copy_link",
                "reel",
                "https://www.instagram.com/reel/Dd90zQtDzon/",
            ),
            (
                "https://www.instagram.com/reels/Dd90zQtDzon/",
                "reel",
                "https://www.instagram.com/reel/Dd90zQtDzon/",
            ),
            (
                "https://www.instagram.com/tv/Dd90zQtDzon/",
                "video",
                "https://www.instagram.com/p/Dd90zQtDzon/",
            ),
            (
                "https://instagr.am/p/DcAsngdyjQ0/",
                "post",
                "https://www.instagram.com/p/DcAsngdyjQ0/",
            ),
        ],
    )
    def test_posts_reels_and_videos(self, url: str, kind: str, canonical: str) -> None:
        ref = _ref(url)

        assert ref.platform is Platform.INSTAGRAM
        assert ref.kind == kind
        assert ref.canonical_url == canonical

    def test_a_reel_is_a_video_route_and_a_picture_post_is_not(self) -> None:
        assert is_video_route(_ref("https://www.instagram.com/reel/Dd90zQtDzon/"))
        assert not is_video_route(_ref("https://www.instagram.com/p/Dd-ghgbkrzL/"))

    def test_a_story_is_recognised_so_it_can_be_said_to_need_a_login(self) -> None:
        ref = _ref("https://www.instagram.com/stories/bbcnews/3998584265222601255/")

        assert ref.kind == "story"

    def test_a_share_link_is_followed_by_the_reader(self) -> None:
        ref = _ref("https://www.instagram.com/share/reel/BAQ1abcDEF/")

        assert ref.needs_resolving and ref.kind == "reel" and ref.post_id is None

    @pytest.mark.parametrize(
        "url", ["https://www.instagram.com/bbcnews/", "https://www.instagram.com/explore/tags/x/"]
    )
    def test_a_profile_is_not_a_post(self, url: str) -> None:
        assert recognise(url) is None


class TestYouTube:
    @pytest.mark.parametrize(
        ("url", "kind"),
        [
            ("https://www.youtube.com/watch?v=4FiZyEb7Hh4&t=30s&si=abc", "video"),
            ("https://m.youtube.com/watch?v=4FiZyEb7Hh4", "video"),
            ("https://youtu.be/4FiZyEb7Hh4?si=abc", "video"),
            ("https://www.youtube.com/shorts/4FiZyEb7Hh4?feature=share", "short"),
            ("https://www.youtube.com/live/4FiZyEb7Hh4", "live"),
            ("https://www.youtube.com/embed/4FiZyEb7Hh4", "video"),
            ("https://www.youtube-nocookie.com/embed/4FiZyEb7Hh4", "video"),
            ("https://music.youtube.com/watch?v=4FiZyEb7Hh4", "video"),
        ],
    )
    def test_every_form_folds_to_the_watch_address(self, url: str, kind: str) -> None:
        ref = _ref(url)

        assert ref.platform is Platform.YOUTUBE
        assert ref.post_id == "4FiZyEb7Hh4"
        assert ref.kind == kind
        assert ref.canonical_url == "https://www.youtube.com/watch?v=4FiZyEb7Hh4"
        assert is_video_route(ref)

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/@ndtv",
            "https://www.youtube.com/watch?v=tooshort",
            "https://www.youtube.com/results?search_query=archery",
        ],
    )
    def test_a_channel_or_a_bad_id_is_not_a_video(self, url: str) -> None:
        assert recognise(url) is None


class TestFacebook:
    @pytest.mark.parametrize(
        ("url", "kind"),
        [
            ("https://www.facebook.com/ndtv/posts/pfbid0abcdefghijkLMNOP123", "post"),
            ("https://www.facebook.com/permalink.php?story_fbid=123456789&id=987", "post"),
            ("https://www.facebook.com/watch/?v=10153231379946729", "video"),
            ("https://www.facebook.com/reel/1234567890", "reel"),
            ("https://www.facebook.com/facebook/videos/10153231379946729/", "video"),
        ],
    )
    def test_posts_are_recognised_so_they_can_be_said_to_be_unsupported(
        self, url: str, kind: str
    ) -> None:
        ref = _ref(url)

        assert ref.platform is Platform.FACEBOOK and ref.kind == kind

    def test_tracking_is_dropped_from_a_facebook_address(self) -> None:
        ref = _ref("https://m.facebook.com/watch/?v=10153231379946729&mibextid=abc&rdid=xyz")

        assert ref.canonical_url == "https://www.facebook.com/watch?v=10153231379946729"


class TestNotALink:
    @pytest.mark.parametrize(
        "url", ["ftp://x.com/a/status/1", "not a url", "https://[::1/x", "https://example.org/a"]
    )
    def test_anything_else_is_none(self, url: str) -> None:
        assert recognise(url) is None


class TestThePlatformsOwnHosts:
    """Where a short link ended that is not a post: a platform's page, or anywhere else."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.instagram.com/accounts/login/?next=/reel/Dd90zQtDzon/",
            "https://x.com/OneObjective_",
            "https://twitter.com/home",
            "https://www.facebook.com/login/",
            "https://www.youtube.com/@ndtv",
        ],
    )
    def test_a_platforms_page_that_is_not_a_post(self, url: str) -> None:
        assert is_platform_host(url)
        assert recognise(url) is None

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.ndtv.com/india-news/story-123",
            "https://bit.ly/abc",
            # A look-alike is not the platform.
            "https://x.com.example.org/a",
            "https://evilinstagram.com/p/Dd90zQtDzon/",
            "not a url",
        ],
    )
    def test_anywhere_else_is_not_the_platform(self, url: str) -> None:
        assert not is_platform_host(url)


class TestTheCacheIdentity:
    """Shares of one post collapse; the reader's version is part of the key."""

    def test_shares_of_one_post_are_one_cache_entry(self) -> None:
        first = normalise_url("https://twitter.com/OneObjective_/status/2105264647691440217?s=46")
        second = normalise_url("https://x.com/i/status/2105264647691440217")

        assert first.cache_identity == second.cache_identity
        assert first.primary.source_url == "https://x.com/i/status/2105264647691440217"
        assert first.extraction_route == "url.social"

    def test_share_parameters_fold_for_youtube_and_instagram(self) -> None:
        assert (
            normalise_url(
                "https://youtube.com/shorts/ikPJlAdAuaE?si=abc&feature=share"
            ).cache_identity
            == normalise_url("https://youtu.be/ikPJlAdAuaE").cache_identity
        )
        assert (
            normalise_url("https://www.instagram.com/reel/Dd90zQtDzon/?igsh=abc").cache_identity
            == normalise_url("https://instagram.com/reel/Dd90zQtDzon").cache_identity
        )

    def test_the_readers_version_is_part_of_a_posts_identity(self) -> None:
        import hashlib

        intake = normalise_url("https://x.com/i/status/2105264647691440217")
        keyed = (
            "https://x.com/i/status/2105264647691440217"
            f"|social:{READER_VERSION}:{VIDEO_READER_VERSION}"
        )

        assert intake.cache_identity == f"sha256:{hashlib.sha256(keyed.encode()).hexdigest()}"

    def test_a_new_video_reader_is_a_new_identity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A YouTube verdict made by the old video reader is not served after it changes.
        before = normalise_url("https://youtu.be/ikPJlAdAuaE").cache_identity
        monkeypatch.setattr(normalizer, "VIDEO_READER_VERSION", "2099.01.01.1")

        assert normalise_url("https://youtu.be/ikPJlAdAuaE").cache_identity != before

    def test_an_ordinary_link_keeps_its_identity_and_route(self) -> None:
        import hashlib

        intake = normalise_url("https://example.org/story?utm_source=x")

        assert intake.extraction_route == "url.canonicalised"
        expected = hashlib.sha256(b"https://example.org/story").hexdigest()
        assert intake.cache_identity == f"sha256:{expected}"
