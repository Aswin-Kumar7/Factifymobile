"""Reading a post from X, Instagram or YouTube: its words, author, media and gaps.

A link to a post used to be read as a news page: the post's words mixed with replies
and comments, and its pictures and video never read at all. These tests hold the
reader to what it now promises, on the platforms' real answers:
`tests/fixtures/social/` was recorded on the server (2026-10-02, as FactifyBot,
through the reader's own fetcher, `scripts/record_social_fixtures.py`) for the posts
of the reading audit: x-4 (a video re-posted from another account), x-5 (a Hindi
photo post), x-6 (a Telugu news video), x-1 (a long post), ig-1 (The Hindu's
seven-picture album), ig-3 (BBC News's reel), ig-5 (a photo under Instagram's own
fact-check label) and yt-5 (a Short). They are replayed through the real
`SecureFetcher` over an in-memory transport; nothing here touches the network.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.config import Settings, SocialSettings
from app.extraction import social
from app.extraction.reading import GapCode, PartKind, Reading, ReadingPolicy, policy
from app.extraction.social import (
    Downloaded,
    PostMedia,
    SocialPost,
    SocialReader,
    embed_token,
    instagram_post,
    video_candidates,
    x_oembed_post,
    x_page_text,
    x_post,
    youtube_post,
)
from app.intake.social_urls import PostRef, recognise
from app.security.fetcher import SecureFetcher

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "social"

X4 = "2105264647691440217"
X5 = "2100143601443557471"
X6 = "2100138377060532502"
X1 = "2105365875310354576"


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every host resolves to a public address, with no DNS lookup."""
    import app.security.ssrf as ssrf

    monkeypatch.setattr(ssrf, "_default_resolver", lambda host, port: ["93.184.216.34"])


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _json(name: str) -> dict[str, Any]:
    return dict(json.loads(_text(name)))


def _ref(url: str) -> PostRef:
    ref = recognise(url)
    assert ref is not None
    return ref


def _x(post_id: str) -> PostRef:
    return _ref(f"https://x.com/i/status/{post_id}")


Handler = Callable[[httpx.Request], httpx.Response]


class _Platforms:
    """Answers each address from a table, and keeps what it was asked."""

    def __init__(self, routes: dict[str, httpx.Response | Handler]) -> None:
        self.routes = routes
        self.asked: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.asked.append(url)
        for prefix, answer in self.routes.items():
            if url.startswith(prefix):
                return answer(request) if callable(answer) else answer
        return httpx.Response(404, text="not routed")


def _reader(answers: _Platforms, **settings: Any) -> SocialReader:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(answers.handler), follow_redirects=False
    )
    return SocialReader(
        fetcher=SecureFetcher(client=client, accepted_types=social.ACCEPTED_TYPES),
        settings=SocialSettings(**settings),
    )


def _json_answer(name: str) -> httpx.Response:
    return httpx.Response(
        200, content=(FIXTURES / name).read_bytes(), headers={"content-type": "application/json"}
    )


def _html_answer(name: str, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status, content=(FIXTURES / name).read_bytes(), headers={"content-type": "text/html"}
    )


SYNDICATION = "https://cdn.syndication.twimg.com/tweet-result?id="


# ------------------------------------------------------------------------------------- X


class TestAnXPostFromSyndication:
    def test_the_words_are_the_posts_own_without_the_media_link(self) -> None:
        post = x_post(_x(X4), _json("x4_oneobjective_video.syndication.json"))

        assert post.text.startswith("Terror on Dubai flight flydubai with 180 passengers")
        assert post.text.endswith("Death to Trump - Allahu Akbar”🚨")
        assert "t.co" not in post.text
        assert post.text_complete and post.gaps == ()
        assert post.text_route == "x.syndication"

    def test_who_posted_it_and_when(self) -> None:
        post = x_post(_x(X4), _json("x4_oneobjective_video.syndication.json"))

        assert (post.author_name, post.handle) == ("One Objective", "OneObjective_")
        assert post.published_at is not None
        assert post.published_at.isoformat() == "2026-09-30T11:53:00+00:00"
        assert post.language == "en"

    def test_a_video_reposted_from_another_post_says_where_it_came_from(self) -> None:
        post = x_post(_x(X4), _json("x4_oneobjective_video.syndication.json"))

        (video,) = post.media
        assert video.kind == "video"
        assert video.url.startswith("https://video.twimg.com/amplify_video/")
        assert video.duration_seconds == pytest.approx(22.636)
        assert (
            video.source_post_url == "https://x.com/MAGAStorm47/status/2105021214188351535/video/1"
        )
        assert video.poster_url and video.poster_url.startswith("https://pbs.twimg.com/")
        assert post.duration_seconds == pytest.approx(22.636)

    def test_a_photo_is_asked_for_at_its_largest(self) -> None:
        post = x_post(_x(X5), _json("x5_ocjain4_photo.syndication.json"))

        (picture,) = post.pictures
        assert picture.url == "https://pbs.twimg.com/media/HSU1eHia8AA9jzl.jpg?name=large"
        assert (picture.width, picture.height) == (1474, 1066)
        assert picture.source_post_url is None  # posted here, not borrowed
        assert post.text.startswith("दिन-रात दलित-दलित चिल्लाने वाले राहुल गांधी")
        assert post.language == "hi"

    def test_every_mp4_quality_is_offered_lowest_first(self) -> None:
        post = x_post(_x(X6), _json("x6_zeetelugu_video.syndication.json"))

        (video,) = post.videos
        assert [bitrate for _, bitrate in video.variants] == [632000, 950000, 2176000]
        assert video.url == video.variants[-1][0]
        # The playlist is not a file and is never offered.
        assert all(".m3u8" not in url for url, _ in video.variants)
        # X's "und": no language worth naming.
        assert post.language is None

    def test_a_long_post_is_said_to_be_cut_short(self) -> None:
        post = x_post(_x(X1), _json("x1_httweets_long.syndication.json"))

        assert not post.text_complete
        (gap,) = post.gaps
        assert gap.code is GapCode.TEXT_TRUNCATED and gap.blocking

    def test_its_parts_are_labelled_as_factifys(self) -> None:
        post = x_post(_x(X5), _json("x5_ocjain4_photo.syndication.json"))

        (part,) = post.parts()
        assert part.kind is PartKind.POST_TEXT
        assert part.label == "Post text"
        document = Reading(kind="social_post", parts=post.parts()).document().text
        assert document.startswith("Post text:\n")

    def test_shortened_links_are_written_in_full_and_kept(self) -> None:
        data = {
            "text": "Read this https://t.co/abc and see https://t.co/pic",
            "entities": {
                "urls": [{"url": "https://t.co/abc", "expanded_url": "https://pib.gov.in/x"}],
                "media": [{"url": "https://t.co/pic"}],
            },
            "user": {"name": "PIB", "screen_name": "PIB_India"},
        }

        post = x_post(_x(X5), data)

        assert post.text == "Read this https://pib.gov.in/x and see"
        assert post.links == ("https://pib.gov.in/x",)

    def test_a_replys_leading_names_are_not_the_post(self) -> None:
        data = {
            "text": "@ANI @PIB_India This is false &amp; misleading",
            "display_text_range": [16, 46],
            "user": {"screen_name": "someone"},
        }

        assert x_post(_x(X5), data).text == "This is false & misleading"

    def test_a_quoted_post_is_read_one_level_down(self) -> None:
        inner = {
            "id_str": "1985291484896403735",
            "text": "GST rates cut on 375 items from 22 September",
            "user": {"name": "PIB India", "screen_name": "PIB_India"},
            "quoted_tweet": {"text": "not read", "user": {}},
        }
        data = {
            "text": "Is this true? https://t.co/q",
            "entities": {
                "urls": [
                    {
                        "url": "https://t.co/q",
                        "expanded_url": "https://twitter.com/PIB_India/status/1985291484896403735",
                    }
                ]
            },
            "user": {"screen_name": "asker"},
            "quoted_tweet": inner,
        }

        post = x_post(_x(X5), data)

        assert post.quoted is not None
        assert post.quoted.text == "GST rates cut on 375 items from 22 September"
        assert post.quoted.handle == "PIB_India"
        assert post.quoted.quoted is None
        # The quoted post's address is how it is cited, not a link the author shared.
        assert post.links == ()
        kinds = [part.kind for part in post.parts()]
        assert kinds == [PartKind.POST_TEXT, PartKind.QUOTED_POST]
        assert post.parts()[1].label == "Quoted post"

    def test_media_x_no_longer_shows_is_a_gap(self) -> None:
        data = _json("x5_ocjain4_photo.syndication.json")
        data["mediaDetails"][0]["ext_media_availability"] = {"status": "Unavailable"}

        post = x_post(_x(X5), data)

        assert post.media == ()
        assert [gap.code for gap in post.gaps] == [GapCode.PICTURE_UNREAD]


class TestTheRestOfALongPost:
    def test_the_posts_own_page_gives_all_of_it(self) -> None:
        start = x_post(_x(X1), _json("x1_httweets_long.syndication.json")).text

        full = x_page_text(_text("x1_httweets_long.page.html"), start=start)

        assert full is not None
        assert full.startswith(start)
        assert "The profile lists 9,750 flying hours on the 737-800" in full
        # Its shortened links written in full, from the same page.
        assert "https://www.hindustantimes.com/india-news/stabbed-flydubai-pilot" in full
        assert "t.co/" not in full

    def test_a_page_that_is_another_post_is_not_taken(self) -> None:
        page = _text("x1_httweets_long.page.html")

        assert x_page_text(page, start="Something else entirely was said here.") is None

    def test_a_page_without_the_post_is_not_taken(self) -> None:
        assert x_page_text("<html><h1>Log in to X</h1></html>", start="The pilot") is None

    async def test_the_reader_fetches_it_when_syndication_cuts_it(self) -> None:
        platforms = _Platforms(
            {
                SYNDICATION: _json_answer("x1_httweets_long.syndication.json"),
                "https://x.com/htTweets/status/": _html_answer("x1_httweets_long.page.html"),
            }
        )

        post = await _reader(platforms).read(_x(X1))

        assert post.text_complete and post.gaps == ()
        assert post.text_route == "x.page"
        assert "9,750 flying hours" in post.text
        assert any("hindustantimes.com/india-news/" in link for link in post.links)
        assert platforms.asked[1] == f"https://x.com/htTweets/status/{X1}"

    async def test_when_the_page_fails_the_start_is_kept_and_said_to_be_partial(self) -> None:
        platforms = _Platforms({SYNDICATION: _json_answer("x1_httweets_long.syndication.json")})

        post = await _reader(platforms).read(_x(X1))

        assert not post.text_complete
        assert [gap.code for gap in post.gaps] == [GapCode.TEXT_TRUNCATED]
        assert (
            policy(
                Reading(kind="social_post", parts=post.parts(), gaps=post.gaps),
                accept_partial=False,
            )
            is ReadingPolicy.WITHHOLD
        )


class TestXWhenSyndicationDoesNotAnswer:
    async def test_the_widgets_own_token_is_tried_next(self) -> None:
        def syndication(request: httpx.Request) -> httpx.Response:
            if request.url.params.get("token") == "a":
                return httpx.Response(404, text="refused")
            return _json_answer("x5_ocjain4_photo.syndication.json")

        platforms = _Platforms({SYNDICATION: syndication})

        post = await _reader(platforms).read(_x(X5))

        assert post.found and post.text_route == "x.syndication"
        assert f"token={embed_token(X5)}" in platforms.asked[1]

    async def test_oembed_gives_the_words_and_says_the_media_was_not_read(self) -> None:
        platforms = _Platforms(
            {
                SYNDICATION: httpx.Response(503, text="busy"),
                "https://publish.x.com/oembed": _json_answer("x4_oneobjective_video.oembed.json"),
            }
        )

        post = await _reader(platforms).read(_x(X4))

        assert post.text_route == "x.oembed"
        assert post.text.startswith("Terror on Dubai flight flydubai")
        assert "pic.twitter.com" not in post.text
        assert post.handle == "OneObjective_"
        assert post.published_at is not None and post.published_at.date().isoformat() == (
            "2026-09-30"
        )
        assert [gap.code for gap in post.gaps] == [GapCode.PICTURE_UNREAD]
        assert post.gaps[0].blocking

    def test_a_long_post_from_oembed_is_said_to_be_cut(self) -> None:
        post = x_oembed_post(_x(X1), _json("x1_httweets_long.oembed.json"))

        assert post.text.endswith("…")
        assert [gap.code for gap in post.gaps] == [
            GapCode.TEXT_TRUNCATED,
            GapCode.PICTURE_UNREAD,
        ]

    async def test_a_post_that_does_not_exist_is_said_to_be_gone(self) -> None:
        platforms = _Platforms(
            {
                SYNDICATION: _html_answer("x_missing.syndication.html", status=404),
                "https://publish.x.com/oembed": _html_answer("x_missing.oembed.html", 404),
            }
        )

        post = await _reader(platforms).read(_x("1"))

        assert not post.found
        (gap,) = post.gaps
        assert gap.code is GapCode.POST_UNAVAILABLE and gap.blocking

    async def test_a_tombstone_is_a_post_that_is_gone(self) -> None:
        platforms = _Platforms(
            {
                SYNDICATION: httpx.Response(
                    200, json={"__typename": "TweetTombstone", "tombstone": {}}
                )
            }
        )

        post = await _reader(platforms).read(_x(X5))

        assert [gap.code for gap in post.gaps] == [GapCode.POST_UNAVAILABLE]


def test_the_embed_token_is_the_widgets_own() -> None:
    # Pinned against X's widget formula run in Node:
    # ((Number(id) / 1e15) * Math.PI).toString(36).replace(/(0+|\.)/g, "")
    assert embed_token(X4) == "53pvtlmbqy"
    assert embed_token(X5) == "539sn8mviu5"
    assert embed_token(X6) == "539s1yvj8bi"
    assert embed_token("20") == "6dq1a2xwd93"
    assert embed_token("1628832338187636740") == "3y54libozsy"


# ----------------------------------------------------------------------------- Instagram

IG1 = "https://www.instagram.com/p/Dd-ghgbkrzL/"
IG3 = "https://www.instagram.com/reel/Dd90zQtDzon/"
IG5 = "https://www.instagram.com/p/DcAsngdyjQ0/"


class TestAnInstagramPost:
    def test_an_album_gives_every_picture_and_the_caption_without_comments(self) -> None:
        post = instagram_post(_ref(IG1), _text("ig1_the_hindu_album.embed.html"))

        assert post.handle == "the_hindu"
        assert post.text.startswith("The Indian women’s recurve archery team stormed into")
        assert post.text.endswith("Visuals: Reuters")
        assert "comments" not in post.text.casefold()
        assert len(post.pictures) == 7
        assert all("cdninstagram.com" in item.url for item in post.pictures)
        assert post.pictures[0].width == 1080
        assert post.gaps == ()
        assert post.text_route == "instagram.embed"

    def test_a_reel_gives_its_video_address_and_length(self) -> None:
        post = instagram_post(_ref(IG3), _text("ig3_bbcnews_reel.embed.html"))

        assert post.handle == "bbcnews"
        assert post.text.startswith("Do you vape?")
        (video,) = post.videos
        assert video.url.startswith("https://scontent-sin2-2.cdninstagram.com/o1/v/")
        assert ".mp4" in video.url
        assert video.duration_seconds == pytest.approx(43.816)
        assert video.poster_url and "cdninstagram.com" in video.poster_url
        assert post.gaps == ()

    def test_a_post_without_data_is_read_from_its_html_with_instagrams_label(self) -> None:
        post = instagram_post(_ref(IG5), _text("ig5_venukolangara_labelled.embed.html"))

        assert post.handle == "venukolangara"
        assert post.text.startswith(
            "An old photograph of our country's Prime Minister Ji and Home Minister Amit Shah Ji."
        )
        assert "venukolangara" not in post.text  # the username link is Instagram's
        (picture,) = post.pictures
        assert "cdninstagram.com" in picture.url and "&amp;" not in picture.url
        assert post.platform_label == (
            "Altered photo/video. Reviewed by third-party fact checkers."
        )
        assert post.gaps == ()

    def test_a_missing_post_is_said_to_be_unavailable(self) -> None:
        post = instagram_post(
            _ref("https://www.instagram.com/p/AAAAAAAAAAA/"), _text("instagram_missing.embed.html")
        )

        assert not post.found
        (gap,) = post.gaps
        assert gap.code is GapCode.POST_UNAVAILABLE and gap.blocking

    def test_a_reel_whose_page_has_no_video_address_says_the_video_was_not_read(self) -> None:
        # The same page as a picture post, asked for as a reel: no video in it.
        post = instagram_post(
            _ref(IG3.replace("Dd90zQtDzon", "DcAsngdyjQ0")),
            _text("ig5_venukolangara_labelled.embed.html"),
        )

        assert [gap.code for gap in post.gaps] == [GapCode.VIDEO_UNREAD]
        assert post.gaps[0].blocking

    def test_an_album_without_data_says_only_the_first_picture_was_read(self) -> None:
        page = _text("ig5_venukolangara_labelled.embed.html").replace(
            '"isSidecar":false', '"isSidecar":true'
        )

        post = instagram_post(_ref(IG5), page)

        assert [gap.code for gap in post.gaps] == [GapCode.FIRST_PICTURE_ONLY]
        assert not post.gaps[0].blocking

    async def test_the_reader_caps_an_album_at_the_pictures_it_reads(self) -> None:
        platforms = _Platforms(
            {"https://www.instagram.com/p/": _html_answer("ig1_the_hindu_album.embed.html")}
        )

        post = await _reader(platforms, max_pictures=4).read(_ref(IG1))

        assert len(post.pictures) == 4
        (gap,) = post.gaps
        assert gap.code is GapCode.PICTURE_UNREAD and not gap.blocking
        assert gap.detail == "The post has 7 pictures; Factify read the first 4."
        assert platforms.asked == [f"{IG1}embed/captioned/"]

    async def test_a_story_needs_a_login_and_is_not_fetched(self) -> None:
        platforms = _Platforms({})

        post = await _reader(platforms).read(
            _ref("https://www.instagram.com/stories/bbcnews/3998584265222601255/")
        )

        assert [gap.code for gap in post.gaps] == [GapCode.LOGIN_REQUIRED]
        assert platforms.asked == []


# ------------------------------------------------------------------------------- YouTube

YT5 = "https://www.youtube.com/shorts/ikPJlAdAuaE"


class TestAYouTubeVideo:
    def test_the_title_channel_and_thumbnail(self) -> None:
        post = youtube_post(_ref(YT5), _json("yt5_leopard_short.oembed.json"), thumbnail=None)

        assert post.title == "கவனமா இருங்க😭😭#trendingshorts #dangerous@rakshithrakshaanth"
        assert (post.author_name, post.handle) == ("Rakshith Rakshaanth", "rakshithrakshaanth")
        assert post.thumbnail_url == "https://i.ytimg.com/vi/ikPJlAdAuaE/hqdefault.jpg"
        (part,) = post.parts()
        assert part.kind is PartKind.TITLE and part.route == "youtube.oembed"

    async def test_the_reader_asks_oembed_for_the_watch_address(self) -> None:
        platforms = _Platforms(
            {"https://www.youtube.com/oembed": _json_answer("yt5_leopard_short.oembed.json")}
        )

        post = await _reader(platforms).read(_ref(YT5))

        assert post.found and post.title
        assert platforms.asked == [
            "https://www.youtube.com/oembed?url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3D"
            "ikPJlAdAuaE&format=json"
        ]

    async def test_embedding_switched_off_leaves_the_video_to_be_read(self) -> None:
        platforms = _Platforms({"https://www.youtube.com/oembed": httpx.Response(401)})

        post = await _reader(platforms).read(_ref(YT5))

        assert post.gaps == ()
        assert post.thumbnail_url == "https://i.ytimg.com/vi/ikPJlAdAuaE/hqdefault.jpg"

    async def test_a_video_that_does_not_exist_is_said_to_be_gone(self) -> None:
        platforms = _Platforms({"https://www.youtube.com/oembed": httpx.Response(404)})

        post = await _reader(platforms).read(_ref(YT5))

        assert [gap.code for gap in post.gaps] == [GapCode.POST_UNAVAILABLE]


# -------------------------------------------------------------------------- the reader


class TestTheReader:
    async def test_facebook_is_not_supported_and_not_fetched(self) -> None:
        platforms = _Platforms({})

        post = await _reader(platforms).read(_ref("https://www.facebook.com/watch/?v=1015323"))

        (gap,) = post.gaps
        assert gap.code is GapCode.NOT_SUPPORTED and gap.blocking
        assert "Paste the post's text or upload a screenshot" in gap.detail
        assert platforms.asked == []

    async def test_a_platform_switched_off_is_not_read(self) -> None:
        platforms = _Platforms({})
        reader = _reader(platforms, platforms=["x"])

        post = await reader.read(_ref(IG1))

        assert not reader.handles(_ref(IG1)) and reader.handles(_x(X5))
        assert [gap.code for gap in post.gaps] == [GapCode.NOT_SUPPORTED]
        assert platforms.asked == []

    async def test_a_post_read_is_not_fetched_again_for_ten_minutes(self) -> None:
        platforms = _Platforms({SYNDICATION: _json_answer("x5_ocjain4_photo.syndication.json")})
        reader = _reader(platforms)

        first = await reader.read(_x(X5))
        second = await reader.read(_x(X5))

        assert first == second
        assert len(platforms.asked) == 1

    async def test_a_failed_read_is_not_remembered(self) -> None:
        platforms = _Platforms({})
        reader = _reader(platforms)

        await reader.read(_x(X5))
        await reader.read(_x(X5))

        # Syndication twice and oEmbed once, both times.
        assert len(platforms.asked) == 6

    async def test_a_short_link_is_followed_to_the_post(self) -> None:
        platforms = _Platforms(
            {
                "https://t.co/": httpx.Response(
                    301, headers={"location": f"https://x.com/ocjain4/status/{X5}/photo/1"}
                ),
                f"https://x.com/ocjain4/status/{X5}": httpx.Response(
                    200, text="<html></html>", headers={"content-type": "text/html"}
                ),
                SYNDICATION: _json_answer("x5_ocjain4_photo.syndication.json"),
            }
        )

        post = await _reader(platforms).read(_ref("https://t.co/m6dlFQ2Aev"))

        assert post.ref.post_id == X5 and post.found

    async def test_a_reader_fault_is_a_gap_never_an_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(ref: PostRef, data: dict[str, Any], **_: Any) -> SocialPost:
            raise RuntimeError("a parser bug")

        monkeypatch.setattr(social, "x_post", broken)
        platforms = _Platforms({SYNDICATION: _json_answer("x5_ocjain4_photo.syndication.json")})

        post = await _reader(platforms).read(_x(X5))

        assert [gap.code for gap in post.gaps] == [GapCode.READER_UNAVAILABLE]


class TestBuild:
    def test_on_by_default(self) -> None:
        assert isinstance(social.build(Settings(_env_file=None)), SocialReader)

    def test_off_when_switched_off(self) -> None:
        settings = Settings(_env_file=None, social={"enabled": False})

        assert social.build(settings) is None


# ------------------------------------------------------------------------------ download

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def _video(**fields: Any) -> PostMedia:
    defaults: dict[str, Any] = {
        "kind": "video",
        "url": "https://video.twimg.com/v/high.mp4",
        "duration_seconds": 37.0,
        "variants": (
            ("https://video.twimg.com/v/low.mp4", 632_000),
            ("https://video.twimg.com/v/mid.mp4", 950_000),
            ("https://video.twimg.com/v/high.mp4", 2_176_000),
        ),
    }
    return PostMedia(**{**defaults, **fields})


class TestChoosingAVideoQuality:
    def test_the_best_quality_that_fits_comes_first(self) -> None:
        # 37 s at 2.18 Mbit/s is about 11 MB with room for the container.
        assert video_candidates(_video(), 25_000_000) == (
            "https://video.twimg.com/v/high.mp4",
            "https://video.twimg.com/v/mid.mp4",
            "https://video.twimg.com/v/low.mp4",
        )

    def test_a_smaller_cap_drops_the_qualities_that_would_not_fit(self) -> None:
        assert video_candidates(_video(), 4_000_000) == ("https://video.twimg.com/v/low.mp4",)

    def test_nothing_fits_is_nothing_to_try(self) -> None:
        assert video_candidates(_video(duration_seconds=3600.0), 25_000_000) == ()

    def test_without_a_length_the_platforms_choice_comes_first_then_best_to_worst(self) -> None:
        assert video_candidates(_video(duration_seconds=None), 25_000_000) == (
            "https://video.twimg.com/v/high.mp4",
            "https://video.twimg.com/v/mid.mp4",
            "https://video.twimg.com/v/low.mp4",
        )

    def test_without_bitrates_the_platforms_own_address_is_tried(self) -> None:
        media = PostMedia(
            kind="video",
            url="https://scontent.cdninstagram.com/o1/v/reel.mp4",
            duration_seconds=43.8,
            variants=(("https://scontent.cdninstagram.com/o1/v/reel.mp4", None),),
        )

        assert video_candidates(media, 25_000_000) == (
            "https://scontent.cdninstagram.com/o1/v/reel.mp4",
        )


class TestDownloadingMedia:
    async def test_a_picture_comes_back_whole_with_its_type(self) -> None:
        platforms = _Platforms(
            {
                "https://pbs.twimg.com/": httpx.Response(
                    200, content=b"\xff\xd8\xff jpeg", headers={"content-type": "image/jpeg"}
                )
            }
        )
        picture = PostMedia(kind="image", url="https://pbs.twimg.com/media/A.jpg?name=large")

        got = await _reader(platforms).download(picture, max_bytes=1_000_000)

        assert isinstance(got, Downloaded)
        assert (got.data, got.mime) == (b"\xff\xd8\xff jpeg", "image/jpeg")
        assert got.gap() is None

    async def test_a_picture_that_will_not_download_is_a_picture_gap(self) -> None:
        platforms = _Platforms({"https://pbs.twimg.com/": httpx.Response(403)})
        picture = PostMedia(kind="image", url="https://pbs.twimg.com/media/A.jpg")

        got = await _reader(platforms).download(picture, max_bytes=1_000_000)

        assert not isinstance(got, Downloaded)
        assert got.code is GapCode.PICTURE_UNREAD and got.blocking

    async def test_a_picture_on_another_host_is_never_fetched(self) -> None:
        platforms = _Platforms({})
        picture = PostMedia(kind="image", url="https://evil.example/a.jpg")

        got = await _reader(platforms).download(picture, max_bytes=1_000_000)

        assert not isinstance(got, Downloaded)
        assert platforms.asked == []

    async def test_a_video_falls_back_to_a_lower_quality_when_one_is_too_large(self) -> None:
        def cdn(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("high.mp4"):
                return httpx.Response(
                    200, content=MP4 * 1000, headers={"content-type": "video/mp4"}
                )
            return httpx.Response(200, content=MP4, headers={"content-type": "video/mp4"})

        platforms = _Platforms({"https://video.twimg.com/": cdn})

        # Estimated to fit at every quality; the best one turns out larger than that.
        got = await _reader(platforms).download(_video(duration_seconds=0.1), max_bytes=50_000)

        assert isinstance(got, Downloaded)
        assert got.data == MP4
        assert got.url == "https://video.twimg.com/v/mid.mp4"
        assert [url.rsplit("/", 1)[1] for url in platforms.asked] == ["high.mp4", "mid.mp4"]

    async def test_a_video_too_large_at_every_quality_is_too_large_not_truncated(self) -> None:
        platforms = _Platforms(
            {
                "https://video.twimg.com/": httpx.Response(
                    200, content=MP4 * 1000, headers={"content-type": "video/mp4"}
                )
            }
        )

        got = await _reader(platforms).download(_video(duration_seconds=None), max_bytes=1000)

        assert not isinstance(got, Downloaded)
        assert got.code is GapCode.TOO_LARGE and got.blocking

    async def test_a_video_longer_than_is_read_is_whole_and_said_to_be_cut_off(self) -> None:
        platforms = _Platforms(
            {
                "https://video.twimg.com/": httpx.Response(
                    200, content=MP4, headers={"content-type": "video/mp4"}
                )
            }
        )

        got = await _reader(platforms).download(
            _video(duration_seconds=900.0, variants=()), max_bytes=1_000_000, max_seconds=600
        )

        assert isinstance(got, Downloaded)
        assert got.cut_off
        gap = got.gap()
        assert gap is not None and gap.code is GapCode.CUT_OFF
        assert gap.detail.endswith("only its first 10 minutes were read.")

    async def test_a_video_that_will_not_download_is_a_video_gap(self) -> None:
        platforms = _Platforms({"https://video.twimg.com/": httpx.Response(410)})

        got = await _reader(platforms).download(_video(), max_bytes=25_000_000)

        assert not isinstance(got, Downloaded)
        assert got.code is GapCode.VIDEO_UNREAD
        # The first refusal is not retried at a lower quality: it was not about size.
        assert len(platforms.asked) == 1
