"""Reading a social post in full: its words, who posted it and when, its pictures, its video.

A link to a post on X, Instagram or YouTube used to be read as if it were a news
page: our own fetch of the page, then the search vendor's extract, then the page's
headline. What came back was the post's words at best, mixed in with replies and
comments the extractor then checked as the author's; at worst the platform's login
wall. The pictures and the video, where the claim usually is, were never read at all
(the reading audit, 2026-10-02: 19 of 45 right, and no picture or video in a link
ever seen).

This module reads the post itself, through the addresses each platform publishes for
showing a post on another site:

  * **X** - the syndication endpoint behind X's embedded posts (`cdn.syndication.
    twimg.com/tweet-result`), which gives the text, the author, the date, a quoted
    post, and every picture and video with its addresses; the oEmbed endpoint when it
    does not answer; and the post's own page for the rest of a long post, which both
    of those cut short.
  * **Instagram** - the captioned embed (`/p/<code>/embed/captioned/`), which gives the
    caption without the comments, the author, every picture of an album and a reel's
    video address; and Instagram's own fact-check label when the post carries one.
  * **YouTube** - the oEmbed endpoint, for the title, the channel and the thumbnail.
    The video itself is read by Gemini at its address (`app/extraction/video_reader`):
    YouTube lets nobody download it from a server.

Everything is fetched as FactifyBot, through `SecureFetcher`, from the platforms' public
embed addresses: never as a browser, never signed in. A post one of them will not show
to that is a gap said out loud (`app/extraction/reading.py`), never a guess.

Pictures and videos are downloaded only from the platforms' own media hosts
(`MEDIA_HOSTS`), checked on every redirect, and a video is never handed on cut short:
it fits under the byte cap whole, at the best quality that does, or it is not
downloaded (`SocialReader.download`).

`read` never raises: whatever goes wrong comes back as the post's `gaps`. Nothing a
post holds is dropped without one: a picture or video the platform gives no address
for, or gives only as a stream, is a gap said out loud, as is one in a quoted post.

A short link (t.co, an Instagram or Facebook share link) is followed to where it
leads. When that is a post, the post is read; when it is an ordinary page - most
t.co links lead to an article - `read` says so (`SocialPost.not_a_post_url`) and the
page is left to be read as any other link is.
"""

from __future__ import annotations

import html
import json
import logging
import math
import re
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import quote, urlsplit

from lxml import html as lxml_html

from app.config import ProviderSettings, Settings, SocialSettings
from app.extraction.reading import (
    TITLE,
    Gap,
    GapCode,
    PartKind,
    ReadPart,
    gap,
)
from app.governor.governor import pace
from app.intake.social_urls import Platform, PostRef, is_platform_host, recognise
from app.observability.logging import event
from app.security.fetcher import FetchFailure, FetchResult, SecureFetcher
from app.security.ratelimit import SlidingWindowLimiter

logger = logging.getLogger("factify.social")

# What the reader's own fetcher parses: the platforms' pages and JSON. Pictures and
# videos are fetched by `download`, with their own types.
ACCEPTED_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "application/json",
    "text/javascript",
    "application/javascript",
    "text/plain",
)
IMAGE_TYPES = ("image/",)
VIDEO_TYPES = ("video/",)

# Where each platform keeps a post's pictures and videos. A media address read from a
# platform's answer is downloaded only from these hosts and their subdomains.
X_MEDIA_HOSTS = ("pbs.twimg.com", "video.twimg.com")
INSTAGRAM_MEDIA_HOSTS = ("cdninstagram.com", "fbcdn.net")
YOUTUBE_MEDIA_HOSTS = ("i.ytimg.com",)
MEDIA_HOSTS = X_MEDIA_HOSTS + INSTAGRAM_MEDIA_HOSTS + YOUTUBE_MEDIA_HOSTS

# How each part was read, for `ReadPart.route`.
ROUTE_X_SYNDICATION = "x.syndication"
ROUTE_X_OEMBED = "x.oembed"
ROUTE_X_PAGE = "x.page"
ROUTE_INSTAGRAM = "instagram.embed"
ROUTE_YOUTUBE = "youtube.oembed"

# The label lines heading a post's words in what claims are found in. Factify's, not
# the author's, and the same words the extraction prompt is told about.
POST_TEXT_LABEL = "Post text"
QUOTED_POST_LABEL = "Quoted post"

# A post read is kept this long, so "Check what was read" on the same post does not
# fetch it again a minute later.
_CACHE_SECONDS = 600.0
_CACHE_ENTRIES = 256

# A video's size is estimated as bitrate x length, and the container and audio add
# to that: this much room is left for them when choosing a quality that fits.
_SIZE_HEADROOM = 1.1

MediaKind = Literal["image", "video", "gif"]


# ------------------------------------------------------------------------- what is read


@dataclass(frozen=True, slots=True)
class PostMedia:
    """One picture or video of a post, as the platform gives it.

    `url` is the address to download: the largest picture, or the video's best
    single-file version. `variants` are a video's single-file versions as (address,
    bitrate in bits a second), lowest first, when the platform offers several.
    """

    kind: MediaKind
    url: str
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    variants: tuple[tuple[str, int | None], ...] = ()
    # The still the platform shows for a video before it plays.
    poster_url: str | None = None
    # The post this picture or video was first posted in, when it is another one: X
    # shows a video re-posted from someone else's post with that post's address.
    source_post_url: str | None = None
    # In the post this one quotes, not in this post's own: "This is fake!" above a
    # quoted post with the viral video in it.
    in_quoted_post: bool = False


@dataclass(frozen=True, slots=True)
class SocialPost:
    """A post as read: its words, its author, its media, and what could not be read.

    `text` is the post's own words with nothing of the platform's around them: no
    "on X:" prefix, no comments, no replies, the link X adds for its own media taken
    out and shortened links written in full. `text_complete` is False when the
    platform gave only the start of it (a long X post, a caption cut at "more"); the
    gap that says so is in `gaps`.
    """

    ref: PostRef
    author_name: str | None = None
    handle: str | None = None
    published_at: datetime | None = None
    text: str = ""
    text_route: str = ""
    text_complete: bool = True
    language: str | None = None
    quoted: SocialPost | None = None
    links: tuple[str, ...] = ()
    media: tuple[PostMedia, ...] = ()
    gaps: tuple[Gap, ...] = ()
    # How long the video is, when the platform says (an Instagram reel, an X video).
    duration_seconds: float | None = None
    # YouTube: the video's title and the address of its thumbnail.
    title: str | None = None
    thumbnail_url: str | None = None
    # A label the platform itself put on the post: Instagram's "Altered photo/video.
    # Reviewed by third-party fact checkers." Shown beside the answer; not evidence.
    platform_label: str | None = None
    # A short link that led to an ordinary page, not to a post: where it led. Not a
    # gap - nothing of a post went unread - but the page is still to be read, as
    # any other link is.
    not_a_post_url: str | None = None

    @property
    def found(self) -> bool:
        """The platform showed the post: some words, a title or a picture came back."""
        return bool(self.text.strip() or self.title or self.media)

    @property
    def every_media(self) -> tuple[PostMedia, ...]:
        """This post's own pictures and videos, then those of the post it quotes."""
        quoted = self.quoted.media if self.quoted is not None else ()
        return (*self.media, *quoted)

    @property
    def pictures(self) -> tuple[PostMedia, ...]:
        """Every picture to read: the post's own, then its quoted post's."""
        return tuple(item for item in self.every_media if item.kind == "image")

    @property
    def videos(self) -> tuple[PostMedia, ...]:
        """Every video to read: the post's own, then its quoted post's."""
        return tuple(item for item in self.every_media if item.kind in ("video", "gif"))

    def parts(self) -> tuple[ReadPart, ...]:
        """The post's words as parts of a `Reading`: its title, its text, a quoted post.

        Pictures and videos are not here: they are read by their own readers once
        downloaded, and their parts come from those.
        """
        found: list[ReadPart] = []
        if self.title and self.title.strip():
            found.append(
                ReadPart(kind=PartKind.TITLE, text=self.title, route=self.text_route, label=TITLE)
            )
        if self.text.strip():
            found.append(
                ReadPart(
                    kind=PartKind.POST_TEXT,
                    text=self.text,
                    route=self.text_route,
                    label=POST_TEXT_LABEL,
                    complete=self.text_complete,
                    language=self.language,
                )
            )
        quoted = self.quoted
        if quoted is not None and quoted.text.strip():
            found.append(
                ReadPart(
                    kind=PartKind.QUOTED_POST,
                    text=quoted.text,
                    route=quoted.text_route,
                    label=QUOTED_POST_LABEL,
                    complete=quoted.text_complete,
                    language=quoted.language,
                )
            )
        return tuple(found)


@dataclass(frozen=True, slots=True)
class Downloaded:
    """A picture or video, downloaded whole.

    `cut_off` is True for a video longer than the `max_seconds` it was downloaded
    for: it is whole, but only its start will be read, and `gap()` says so.
    """

    data: bytes
    mime: str
    url: str
    cut_off: bool = False
    max_seconds: int | None = None

    def gap(self) -> Gap | None:
        if not self.cut_off or self.max_seconds is None:
            return None
        return gap(
            "video",
            GapCode.CUT_OFF,
            f"The video is longer than Factify reads; only its first "
            f"{_duration(self.max_seconds)} were read.",
        )


# ------------------------------------------------------------------------------ addresses


# The embed widget's token. Not a credential: X's own widget sends a value worked out
# from the post id, and the endpoint has taken any value for most posts.
_ANY_TOKEN = "a"  # noqa: S105 - the widget's placeholder, not a secret


def x_syndication_url(post_id: str, token: str = _ANY_TOKEN) -> str:
    return f"https://cdn.syndication.twimg.com/tweet-result?id={post_id}&token={token}&lang=en"


def x_oembed_url(canonical_url: str) -> str:
    # publish.twitter.com answers every request with a redirect here.
    return (
        f"https://publish.x.com/oembed?url={quote(canonical_url, safe='')}&omit_script=1&dnt=true"
    )


def x_page_url(handle: str, post_id: str) -> str:
    return f"https://x.com/{handle}/status/{post_id}"


def instagram_embed_url(ref: PostRef) -> str:
    return f"{ref.canonical_url.rstrip('/')}/embed/captioned/"


def youtube_oembed_url(canonical_url: str) -> str:
    return f"https://www.youtube.com/oembed?url={quote(canonical_url, safe='')}&format=json"


def youtube_thumbnail_url(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


_RADIX_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def _to_radix(value: float, base: int) -> str:
    """`Number.prototype.toString(base)` for a non-negative double, as V8 writes it."""
    integer = math.floor(value)
    fraction = value - integer
    delta = max(0.5 * (math.nextafter(value, math.inf) - value), math.nextafter(0.0, 1.0))
    tail: list[str] = []
    if fraction >= delta:
        tail.append(".")
        while True:
            fraction *= base
            delta *= base
            digit = int(fraction)
            tail.append(_RADIX_DIGITS[digit])
            fraction -= digit
            if (fraction > 0.5 or (fraction == 0.5 and digit & 1)) and fraction + delta > 1:
                while True:
                    last = tail.pop()
                    if last == ".":
                        integer += 1
                        break
                    value_of = _RADIX_DIGITS.index(last)
                    if value_of + 1 < base:
                        tail.append(_RADIX_DIGITS[value_of + 1])
                        break
                break
            if fraction < delta:
                break
    head: list[str] = []
    whole = float(integer)
    while True:
        remainder = math.fmod(whole, base)
        head.append(_RADIX_DIGITS[int(remainder)])
        whole = (whole - remainder) / base
        if whole <= 0:
            break
    return "".join(reversed(head)) + "".join(tail)


def embed_token(post_id: str) -> str:
    """The token X's embed widget sends with a post id: ((id / 1e15) * π) in base 36.

    The endpoint takes any token for most posts today; this is the fallback for when
    it holds to the widget's own, and it is pinned against the widget's output.
    """
    return re.sub(r"(0+|\.)", "", _to_radix(int(post_id) / 1e15 * math.pi, 36))


@dataclass(frozen=True, slots=True)
class Resolved:
    """Where a short link leads: a post, an ordinary page, or nowhere that was found.

    `ref` is the post when it leads to one. `url` is where it ended when that is not
    a post and not one of the platforms' own pages either: an article, a shortener.
    Both None when the link could not be followed, or ended on a platform's login
    wall or home page, which is a post that was not shown.
    """

    ref: PostRef | None = None
    url: str | None = None


# --------------------------------------------------------------------------------- reader


class SocialReader:
    """Reads posts from X, Instagram and YouTube, and downloads their media."""

    def __init__(
        self,
        *,
        fetcher: SecureFetcher,
        settings: SocialSettings,
        clock: Any = time.monotonic,
    ) -> None:
        self._fetcher = fetcher
        self._settings = settings
        self._clock = clock
        self._burst = SlidingWindowLimiter()
        self._cache: dict[str, tuple[float, SocialPost]] = {}

    @property
    def settings(self) -> SocialSettings:
        return self._settings

    def handles(self, ref: PostRef) -> bool:
        """Whether this reader reads posts from this platform on this server."""
        return self._settings.enabled and ref.platform.value in self._settings.platforms

    async def resolve(self, ref: PostRef) -> Resolved:
        """Where a short link (t.co, an Instagram share link) leads: a post, or a page.

        Followed with the fetcher, every hop checked, until the first address that is
        not itself a short link, which is never fetched here: a post is read through
        its platform's embed addresses, and a page by whoever reads pages. Most t.co
        links lead to an article, and that address is handed back rather than lost.
        """
        if not ref.needs_resolving:
            return Resolved(ref=ref)
        if not await self._paced(ref.platform):
            return Resolved()
        chain = await self._fetcher.locate(
            ref.canonical_url, provider=_provider(ref.platform), stop=_past_short_links
        )
        if isinstance(chain, FetchFailure) or len(chain) < 2:
            return Resolved()
        end = chain[-1]
        found = recognise(end)
        if found is not None and not found.needs_resolving:
            return Resolved(ref=found)
        if found is None and not is_platform_host(end) and _is_web_address(end):
            return Resolved(url=end)
        return Resolved()

    async def read(self, ref: PostRef) -> SocialPost:
        """Read a post. Never raises: what could not be read is in the post's `gaps`."""
        try:
            return await self._read(ref)
        except Exception as exc:  # a reader failure must never fail the check
            logger.exception("social post read failed")
            return SocialPost(
                ref=ref,
                gaps=(
                    gap(
                        "post",
                        GapCode.READER_UNAVAILABLE,
                        f"Factify could not read this post ({type(exc).__name__}).",
                    ),
                ),
            )

    async def _read(self, ref: PostRef) -> SocialPost:
        # Said before anything is fetched: a Facebook link, or a platform switched off
        # on this server, is not followed only to be turned away.
        if not self._reads(ref):
            return _not_supported(ref)
        if ref.needs_resolving:
            resolved = await self.resolve(ref)
            if resolved.url is not None:
                # Not a post: an ordinary page, read as any other link is.
                event(
                    logger,
                    "short link is not a post",
                    module="extraction.social",
                    outcome="ok",
                    platform=ref.platform.value,
                )
                return SocialPost(ref=ref, not_a_post_url=resolved.url)
            if resolved.ref is None:
                return SocialPost(
                    ref=ref,
                    gaps=(
                        gap(
                            "post",
                            GapCode.POST_UNAVAILABLE,
                            "Factify could not follow this short link to the post.",
                        ),
                    ),
                )
            ref = resolved.ref
            if not self._reads(ref):
                return _not_supported(ref)
        if ref.kind == "story":
            return SocialPost(
                ref=ref,
                gaps=(
                    gap(
                        "post",
                        GapCode.LOGIN_REQUIRED,
                        "Instagram shows stories only to people signed in, and only "
                        "for a day. Upload a screenshot or the video instead.",
                    ),
                ),
            )

        cached = self._cache.get(ref.canonical_url)
        if cached is not None and self._clock() - cached[0] < _CACHE_SECONDS:
            return cached[1]

        started = time.perf_counter()
        if ref.platform is Platform.X:
            post = await self._read_x(ref)
        elif ref.platform is Platform.INSTAGRAM:
            post = await self._read_instagram(ref)
        else:
            post = await self._read_youtube(ref)
        post = _capped(post, self._settings.max_pictures)

        if post.found:
            self._remember(ref.canonical_url, post)
        event(
            logger,
            "social post read",
            module="extraction.social",
            outcome="ok" if post.found else "failed",
            platform=ref.platform.value,
            kind=ref.kind,
            route=post.text_route,
            character_count=len(post.text),
            text_complete=post.text_complete,
            pictures=len(post.pictures),
            videos=len(post.videos),
            gaps=[item.code.value for item in post.gaps],
            latency_ms=(time.perf_counter() - started) * 1000,
        )
        return post

    def _reads(self, ref: PostRef) -> bool:
        return self.handles(ref) and ref.platform is not Platform.FACEBOOK

    def _remember(self, key: str, post: SocialPost) -> None:
        if len(self._cache) >= _CACHE_ENTRIES:
            oldest = min(self._cache, key=lambda item: self._cache[item][0])
            del self._cache[oldest]
        self._cache[key] = (self._clock(), post)

    async def _paced(self, platform: Platform) -> bool:
        """Room under this platform's per-minute ceiling, waited for if need be."""
        cap = ProviderSettings(per_minute_cap=self._settings.per_minute_cap)
        return await pace(_provider(platform), cap, self._burst)

    async def _get(self, url: str, platform: Platform) -> FetchResult | FetchFailure:
        if not await self._paced(platform):
            return FetchFailure(url=url, reason="too many reads a minute", kind="paced")
        return await self._fetcher.fetch(url, provider=_provider(platform))

    # ----------------------------------------------------------------------------- X

    async def _read_x(self, ref: PostRef) -> SocialPost:
        post_id = ref.post_id or ""
        data = _json_object(await self._get(x_syndication_url(post_id), Platform.X))
        if data is None:
            # The plain token is refused now and then; the widget's own is not. A 404
            # is not taken as "deleted" here: it may be the token that was refused.
            token = embed_token(post_id)
            data = _json_object(await self._get(x_syndication_url(post_id, token), Platform.X))
        if data is None:
            # oEmbed decides whether the post is gone.
            return await self._read_x_oembed(ref)
        if data.get("__typename") == "TweetTombstone" or (
            not data.get("text") and not data.get("mediaDetails")
        ):
            return _unavailable(ref, "X")

        post = x_post(ref, data)
        if not post.text_complete and post.handle:
            post = await self._x_long_text(post)
        return post

    async def _x_long_text(self, post: SocialPost) -> SocialPost:
        """The rest of a long post, from the post's own page; the start otherwise.

        Syndication and oEmbed both stop a long post at about 275 characters. X's own
        page for the post still carries all of it, for a reader without a browser.
        """
        assert post.handle is not None and post.ref.post_id is not None
        page = await self._get(x_page_url(post.handle, post.ref.post_id), Platform.X)
        full = None
        if isinstance(page, FetchResult) and page.status_code < 400:
            full = x_page_text(page.text, start=post.text)
        if full is None:
            return post
        written = [link for link in _LINK.findall(full) if not _TCO.fullmatch(link)]
        return replace(
            post,
            text=full,
            text_route=ROUTE_X_PAGE,
            text_complete=True,
            links=tuple(dict.fromkeys([*post.links, *written])),
            gaps=tuple(
                item
                for item in post.gaps
                if not (item.code is GapCode.TEXT_TRUNCATED and item.part == "post_text")
            ),
        )

    async def _read_x_oembed(self, ref: PostRef) -> SocialPost:
        answer = await self._get(x_oembed_url(ref.canonical_url), Platform.X)
        if _is_missing(answer):
            return _unavailable(ref, "X")
        data = _json_object(answer)
        if data is None:
            return SocialPost(
                ref=ref,
                gaps=(
                    gap("post", GapCode.POST_UNAVAILABLE, "X did not show this post to Factify."),
                ),
            )
        return x_oembed_post(ref, data)

    # ---------------------------------------------------------------------- Instagram

    async def _read_instagram(self, ref: PostRef) -> SocialPost:
        answer = await self._get(instagram_embed_url(ref), Platform.INSTAGRAM)
        if _is_missing(answer):
            return _unavailable(ref, "Instagram")
        if isinstance(answer, FetchFailure) or answer.status_code >= 400:
            return SocialPost(
                ref=ref,
                gaps=(
                    gap(
                        "post",
                        GapCode.POST_UNAVAILABLE,
                        "Instagram did not answer Factify for this post.",
                    ),
                ),
            )
        return instagram_post(ref, answer.text)

    # ------------------------------------------------------------------------ YouTube

    async def _read_youtube(self, ref: PostRef) -> SocialPost:
        answer = await self._get(youtube_oembed_url(ref.canonical_url), Platform.YOUTUBE)
        if _is_missing(answer):
            return _unavailable(ref, "YouTube")
        thumbnail = youtube_thumbnail_url(ref.post_id) if ref.post_id else None
        data = _json_object(answer)
        if data is None:
            # Embedding switched off (401) or a moment's failure: who posted it is
            # unknown, but the video itself may still be read at its address.
            return SocialPost(ref=ref, text_route=ROUTE_YOUTUBE, thumbnail_url=thumbnail)
        return youtube_post(ref, data, thumbnail=thumbnail)

    # ----------------------------------------------------------------------- download

    async def download(
        self, media: PostMedia, *, max_bytes: int, max_seconds: int | None = None
    ) -> Downloaded | Gap:
        """Download one picture or video whole, or say why it could not be. Never raises.

        A video is fetched at the best quality whose estimated size fits under
        `max_bytes`, and at the next lower one if it turns out larger than estimated;
        one that fits at no quality is TOO_LARGE, never a truncated file. A video
        longer than `max_seconds` is still downloaded whole - an mp4 cut short does
        not play - and comes back `cut_off`, since only its start will be read.
        """
        try:
            return await self._download(media, max_bytes=max_bytes, max_seconds=max_seconds)
        except Exception:  # a download failure must never fail the check
            logger.exception("social media download failed")
            if media.kind == "image":
                return gap(
                    "picture_text",
                    GapCode.PICTURE_UNREAD,
                    "A picture in the post could not be downloaded.",
                )
            return gap("video", GapCode.VIDEO_UNREAD, "The post's video could not be downloaded.")

    async def _download(
        self, media: PostMedia, *, max_bytes: int, max_seconds: int | None
    ) -> Downloaded | Gap:
        if media.kind == "image":
            result = await self._fetcher.download(
                media.url,
                provider="social.media",
                max_bytes=max_bytes,
                accepted_types=IMAGE_TYPES,
                allowed_hosts=MEDIA_HOSTS,
            )
            if isinstance(result, FetchFailure):
                return gap(
                    "picture_text",
                    GapCode.PICTURE_UNREAD,
                    "A picture in the post could not be downloaded.",
                )
            return Downloaded(
                data=result.body, mime=result.content_type or "image/jpeg", url=media.url
            )

        candidates = video_candidates(media, max_bytes)
        if not candidates:
            return gap(
                "video",
                GapCode.TOO_LARGE,
                "The video is too large for Factify to download, even at its lowest quality.",
            )
        too_large = False
        for url in candidates:
            result = await self._fetcher.download(
                url,
                provider="social.media",
                max_bytes=max_bytes,
                accepted_types=VIDEO_TYPES,
                allowed_hosts=MEDIA_HOSTS,
            )
            if isinstance(result, FetchResult):
                longer = (
                    max_seconds is not None
                    and media.duration_seconds is not None
                    and media.duration_seconds > max_seconds
                )
                return Downloaded(
                    data=result.body,
                    mime=result.content_type or "video/mp4",
                    url=url,
                    cut_off=longer,
                    max_seconds=max_seconds,
                )
            too_large = result.kind == "too_large"
            if not too_large:
                break
        if too_large:
            return gap(
                "video",
                GapCode.TOO_LARGE,
                "The video is too large for Factify to download, even at its lowest quality.",
            )
        return gap("video", GapCode.VIDEO_UNREAD, "The post's video could not be downloaded.")


def build(settings: Settings) -> SocialReader | None:
    """The reader, or None when reading posts is switched off."""
    if not settings.social.enabled:
        return None
    return SocialReader(
        fetcher=SecureFetcher(
            timeout_seconds=settings.social.timeout_seconds,
            max_bytes=settings.limits.max_upload_bytes,
            accepted_types=ACCEPTED_TYPES,
        ),
        settings=settings.social,
    )


# ----------------------------------------------------------------------- choosing a video


def video_candidates(media: PostMedia, max_bytes: int) -> tuple[str, ...]:
    """The video addresses to try, best first: those that should fit under the cap.

    The highest bitrate whose estimated size (bitrate x length, plus room for the
    container) fits, then the lower ones in turn, in case an estimate was short. With
    no bitrates or no length to estimate from, the platform's own choice. Empty when
    even the lowest is estimated over the cap.
    """
    variants = [item for item in media.variants if item[0]]
    if not variants:
        return (media.url,) if media.url else ()
    duration = media.duration_seconds
    known = [item for item in variants if item[1]]
    if not duration or not known:
        best_first = sorted(variants, key=lambda item: item[1] or 0, reverse=True)
        return tuple(dict.fromkeys([media.url, *(url for url, _ in best_first)]))

    def size(bitrate: int) -> float:
        return bitrate * duration / 8 * _SIZE_HEADROOM

    ranked = sorted(known, key=lambda item: item[1] or 0, reverse=True)
    fitting = [url for url, bitrate in ranked if bitrate and size(bitrate) <= max_bytes]
    return tuple(fitting)


# ---------------------------------------------------------------------- reading answers

_PLATFORM_NAMES = {
    Platform.X: "X",
    Platform.INSTAGRAM: "Instagram",
    Platform.YOUTUBE: "YouTube",
    Platform.FACEBOOK: "Facebook",
}


def _provider(platform: Platform) -> str:
    return f"social.{platform.value}"


def _past_short_links(url: str) -> bool:
    """Whether following a short link has reached an address that is not one."""
    found = recognise(url)
    return found is None or not found.needs_resolving


def _is_web_address(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme.lower() in ("http", "https") and bool(parts.hostname)


def _not_supported(ref: PostRef) -> SocialPost:
    return SocialPost(
        ref=ref,
        gaps=(
            gap(
                "post",
                GapCode.NOT_SUPPORTED,
                f"Factify does not read posts from "
                f"{_PLATFORM_NAMES.get(ref.platform, 'this platform')}. Paste the "
                "post's text or upload a screenshot instead.",
            ),
        ),
    )


def _is_missing(answer: FetchResult | FetchFailure) -> bool:
    """The platform said there is no such post."""
    return isinstance(answer, FetchResult) and answer.status_code in (404, 410)


def _json_object(answer: FetchResult | FetchFailure) -> dict[str, Any] | None:
    if isinstance(answer, FetchFailure) or answer.status_code >= 400 or not answer.body.strip():
        return None
    try:
        data = json.loads(answer.text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _unavailable(ref: PostRef, platform: str) -> SocialPost:
    return SocialPost(
        ref=ref,
        gaps=(
            gap(
                "post",
                GapCode.POST_UNAVAILABLE,
                f"{platform} says this post does not exist: it was deleted, made "
                "private, or the link is wrong.",
            ),
        ),
    )


def _capped(post: SocialPost, max_pictures: int) -> SocialPost:
    """At most `max_pictures` pictures, the rest said to be unread (not blocking).

    Counted across the post and the post it quotes, the post's own first.
    """
    pictures = post.pictures
    if len(pictures) <= max_pictures:
        return post
    kept = {id(item) for item in pictures[:max_pictures]}

    def keep(media: tuple[PostMedia, ...]) -> tuple[PostMedia, ...]:
        return tuple(item for item in media if item.kind != "image" or id(item) in kept)

    quoted = post.quoted
    if quoted is not None:
        quoted = replace(quoted, media=keep(quoted.media))
    note = gap(
        "picture_text",
        GapCode.PICTURE_UNREAD,
        f"The post has {len(pictures)} pictures; Factify read the first {max_pictures}.",
        blocking=False,
    )
    return replace(post, media=keep(post.media), quoted=quoted, gaps=(*post.gaps, note))


def _duration(seconds: int) -> str:
    if seconds >= 120 and seconds % 60 == 0:
        return f"{seconds // 60} minutes"
    return f"{seconds} seconds"


def _clean(text: str) -> str:
    """Trailing spaces off each line, runs of blank lines to one, ends trimmed."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    joined = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", joined).strip()


def _date(value: Any) -> datetime | None:
    if isinstance(value, int | float) and not isinstance(value, bool) and value > 0:
        return datetime.fromtimestamp(value, UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


# ------------------------------------------------------------------------------------ X

_STATUS_IN_URL = re.compile(r"/status(?:es)?/(\d+)")
_TCO = re.compile(r"https?://t\.co/[A-Za-z0-9]+")
_LINK = re.compile(r"https?://[^\s<>\"']+[^\s<>\"'.,;:!?)\]]")


def x_post(ref: PostRef, data: dict[str, Any], *, quoted: bool = False) -> SocialPost:
    """A post from X's syndication answer. Pure."""
    user = data.get("user") or {}
    entities = data.get("entities") or {}
    text = str(data.get("text") or "")

    # A reply's leading @names are outside what X shows as the post.
    shown = data.get("display_text_range")
    if isinstance(shown, list) and shown and isinstance(shown[0], int) and shown[0] > 0:
        lead = text[: shown[0]]
        if re.fullmatch(r"(\s*@\w+)+\s*", lead):
            text = text[shown[0] :]

    # The link X adds for its own picture or video is not part of what was said.
    for item in entities.get("media") or []:
        if isinstance(item, dict) and item.get("url"):
            text = text.replace(str(item["url"]), "")
    links: list[str] = []
    for item in entities.get("urls") or []:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        expanded = str(item.get("expanded_url") or item["url"])
        text = text.replace(str(item["url"]), expanded)
        links.append(expanded)
    card = data.get("card") or {}
    card_url = _card_value(card, "card_url") or str(card.get("url") or "")
    if card_url and card_url not in links and not _TCO.fullmatch(card_url):
        links.append(card_url)
    text = _clean(html.unescape(text))

    post_id = ref.post_id or str(data.get("id_str") or "")
    found_media, unread_media = _x_media(data, post_id, quoted=quoted)
    media = tuple(found_media)

    quoted_post: SocialPost | None = None
    quoted_data = data.get("quoted_tweet")
    if (
        not quoted
        and isinstance(quoted_data, dict)
        and (quoted_data.get("text") or quoted_data.get("mediaDetails"))
    ):
        quoted_id = str(quoted_data.get("id_str") or "")
        quoted_ref = recognise(f"https://x.com/i/status/{quoted_id}") if quoted_id else None
        quoted_post = x_post(quoted_ref or ref, quoted_data, quoted=True)
        # The quoted post's own address is how it is cited, not a link the author shared.
        links = [link for link in links if not _same_status(link, quoted_id)]

    truncated = "note_tweet" in data
    gaps: list[Gap] = []
    if truncated:
        gaps.append(
            gap(
                "quoted_post" if quoted else "post_text",
                GapCode.TEXT_TRUNCATED,
                "The quoted post is a long one, and X gave Factify only its start."
                if quoted
                else "This is a long post, and X gave Factify only its start.",
            )
        )
    whose = "the quoted post's" if quoted else "the post's"
    for item in data.get("mediaDetails") or []:
        status = ((item or {}).get("ext_media_availability") or {}).get("status")
        if status and str(status).casefold() != "available":
            kind = "video" if item.get("type") in ("video", "animated_gif") else "picture"
            gaps.append(
                gap(
                    "video" if kind == "video" else "picture_text",
                    GapCode.VIDEO_UNREAD if kind == "video" else GapCode.PICTURE_UNREAD,
                    f"X no longer shows {whose} {kind}.",
                )
            )
    gaps.extend(unread_media)
    if quoted_post is not None:
        # What could not be read of the quoted post is unread in this one too.
        gaps.extend(quoted_post.gaps)

    duration = next((item.duration_seconds for item in media if item.duration_seconds), None)
    return SocialPost(
        ref=ref,
        author_name=str(user.get("name") or "") or None,
        handle=str(user.get("screen_name") or "") or None,
        published_at=_date(data.get("created_at")),
        text=text,
        text_route=ROUTE_X_SYNDICATION,
        text_complete=not truncated,
        language=_language(data.get("lang")),
        quoted=quoted_post,
        links=tuple(dict.fromkeys(links)),
        media=media,
        gaps=tuple(gaps),
        duration_seconds=duration,
    )


def _x_media(
    data: dict[str, Any], post_id: str, *, quoted: bool = False
) -> tuple[list[PostMedia], list[Gap]]:
    """A post's pictures and videos, and a gap for each one there is no way to read.

    A picture with no address, or a video X gives only as a stream (a broadcast's
    replay has no mp4), is said to be unread rather than left out: a post read
    without its video reads exactly like a post that has none.
    """
    found: list[PostMedia] = []
    unread: list[Gap] = []
    whose = "the quoted post" if quoted else "the post"
    for item in data.get("mediaDetails") or []:
        if not isinstance(item, dict):
            continue
        status = (item.get("ext_media_availability") or {}).get("status")
        if status and str(status).casefold() != "available":
            continue
        info = item.get("original_info") or {}
        width = _int(info.get("width"))
        height = _int(info.get("height"))
        source = str(item.get("expanded_url") or "")
        from_elsewhere = _status_of(source)
        source_post = source if from_elsewhere and from_elsewhere != post_id else None
        picture = str(item.get("media_url_https") or "")
        kind = item.get("type")
        if kind == "photo" and not picture:
            unread.append(
                gap(
                    "picture_text",
                    GapCode.PICTURE_UNREAD,
                    f"X gave Factify no address for a picture in {whose}.",
                )
            )
        elif kind == "photo":
            found.append(
                PostMedia(
                    kind="image",
                    url=_large(picture),
                    width=width,
                    height=height,
                    source_post_url=source_post,
                    in_quoted_post=quoted,
                )
            )
        elif kind in ("video", "animated_gif"):
            video = item.get("video_info") or {}
            variants = _mp4_variants(video.get("variants"), url_key="url", type_key="content_type")
            if not variants:
                top = data.get("video") or {}
                variants = _mp4_variants(top.get("variants"), url_key="src", type_key="type")
            if not variants:
                unread.append(
                    gap(
                        "video",
                        GapCode.VIDEO_UNREAD,
                        f"X gives the video in {whose} only as a stream, which Factify "
                        "cannot download. Upload the video to check it.",
                    )
                )
                continue
            millis = _int(
                video.get("duration_millis") or (data.get("video") or {}).get("durationMs")
            )
            best = max(variants, key=lambda pair: pair[1] or 0)[0]
            found.append(
                PostMedia(
                    kind="gif" if kind == "animated_gif" else "video",
                    url=best,
                    width=width,
                    height=height,
                    duration_seconds=millis / 1000 if millis else None,
                    variants=variants,
                    poster_url=picture or None,
                    source_post_url=source_post,
                    in_quoted_post=quoted,
                )
            )
    return found, unread


def _mp4_variants(raw: Any, *, url_key: str, type_key: str) -> tuple[tuple[str, int | None], ...]:
    """A video's single-file (mp4) versions, lowest bitrate first."""
    found: list[tuple[str, int | None]] = []
    for item in raw or []:
        if not isinstance(item, dict) or item.get(type_key) != "video/mp4":
            continue
        url = str(item.get(url_key) or "")
        if url:
            found.append((url, _int(item.get("bitrate"))))
    unique = list(dict.fromkeys(found))
    return tuple(sorted(unique, key=lambda pair: pair[1] or 0))


def _large(picture: str) -> str:
    """X's picture address at its largest size."""
    joiner = "&" if "?" in picture else "?"
    return f"{picture}{joiner}name=large"


def _card_value(card: dict[str, Any], key: str) -> str:
    values = card.get("binding_values") or {}
    value = values.get(key) if isinstance(values, dict) else None
    if isinstance(value, dict):
        return str(value.get("string_value") or "")
    return ""


def _status_of(url: str) -> str | None:
    found = _STATUS_IN_URL.search(url)
    return found.group(1) if found else None


def _same_status(url: str, post_id: str) -> bool:
    return bool(post_id) and _status_of(url) == post_id


def _language(value: Any) -> str | None:
    code = str(value or "").strip().casefold()
    # X's "und" (undetermined), "qme" (media only), "zxx" (no words) and the like.
    if not re.fullmatch(r"[a-z]{2,3}", code) or code in {"und", "qme", "qam", "qht", "qst", "zxx"}:
        return None
    return code


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


_X_PAGE_HEADING = re.compile(r'<h1 class="sr-only">(.*?)</h1>', re.DOTALL)
_X_EXTERNAL_LINK = re.compile(
    r'<a [^>]*href="(https?://[^"]+)"[^>]*rel="noopener noreferrer"[^>]*target="_blank"'
)


def x_page_text(page: str, *, start: str) -> str | None:
    """A post's whole text from its X page, or None when it is not there.

    X writes the post for screen readers as `<h1 class="sr-only">{name} on X:
    "{text}"</h1>`. Taken only when it begins as the syndication's start of it does,
    so a page that shows something else (a login wall, another post) is never read
    as this one.
    """
    heading = _X_PAGE_HEADING.search(page)
    if heading is None:
        return None
    said = html.unescape(re.sub(r"<[^>]+>", "", heading.group(1)))
    opening = said.find(' on X: "')
    if opening < 0 or not said.rstrip().endswith('"'):
        return None
    text = said[opening + len(' on X: "') :].rstrip()[:-1]
    # Shortened links written in full where the page gives them in the same order.
    shortened = _TCO.findall(text)
    full = [url for url in _X_EXTERNAL_LINK.findall(page) if "x.com" not in urlsplit(url).netloc]
    full = list(dict.fromkeys(html.unescape(url) for url in full))
    if shortened and len(full) == len(shortened):
        for short, long in zip(shortened, full, strict=True):
            text = text.replace(short, long, 1)
    text = _clean(text)
    if not _starts_alike(text, start) or len(text) <= len(start):
        return None
    return text


def _starts_alike(full: str, start: str) -> bool:
    def squeeze(value: str) -> str:
        return re.sub(r"\s+", " ", _TCO.sub("", value)).strip()

    head = squeeze(start).rstrip("…. ")[:80]
    return bool(head) and squeeze(full).startswith(head)


_OEMBED_DATE = re.compile(r"([A-Z][a-z]+) (\d{1,2}), (\d{4})$")
_MONTHS = {
    name: index
    for index, name in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        start=1,
    )
}


def x_oembed_post(ref: PostRef, data: dict[str, Any]) -> SocialPost:
    """A post from X's oEmbed answer, the fallback when syndication does not answer.

    It gives the words and the author, and no media: a picture or video it points
    at is a gap, since nothing here can download it.
    """
    markup = str(data.get("html") or "")
    text = ""
    published: datetime | None = None
    has_media = False
    links: list[str] = []
    if markup.strip():
        root = lxml_html.fragment_fromstring(markup, create_parent="div")
        paragraph = root.find(".//blockquote/p")
        if paragraph is not None:
            for anchor in paragraph.findall(".//a"):
                shown = anchor.text_content().strip()
                if shown.startswith(("pic.twitter.com", "pic.x.com")):
                    has_media = True
                    _drop(anchor)
                elif anchor.get("href", "").startswith("https://t.co/") and "." in shown:
                    links.append(anchor.get("href", ""))
            for br in paragraph.findall(".//br"):
                br.tail = "\n" + (br.tail or "")
            text = _clean(paragraph.text_content())
        anchors = root.findall(".//blockquote/a")
        if anchors:
            when = _OEMBED_DATE.search(anchors[-1].text_content().strip())
            if when and when.group(1) in _MONTHS:
                published = datetime(
                    int(when.group(3)), _MONTHS[when.group(1)], int(when.group(2)), tzinfo=UTC
                )
    author_url = str(data.get("author_url") or "")
    handle = urlsplit(author_url).path.strip("/").split("/")[0] if author_url else ""
    gaps: list[Gap] = []
    truncated = text.endswith("…")
    if truncated:
        gaps.append(
            gap(
                "post_text",
                GapCode.TEXT_TRUNCATED,
                "This is a long post, and X gave Factify only its start.",
            )
        )
    if has_media:
        gaps.append(
            gap(
                "picture_text",
                GapCode.PICTURE_UNREAD,
                "The post has a picture or video that X did not let Factify download.",
            )
        )
    return SocialPost(
        ref=ref,
        author_name=str(data.get("author_name") or "") or None,
        handle=handle or None,
        published_at=published,
        text=text,
        text_route=ROUTE_X_OEMBED,
        text_complete=not truncated,
        links=tuple(dict.fromkeys(links)),
        gaps=tuple(gaps),
    )


def _drop(element: Any) -> None:
    """Remove an element and keep the text that followed it."""
    parent = element.getparent()
    if parent is None:
        return
    tail = element.tail or ""
    previous = element.getprevious()
    if previous is not None:
        previous.tail = (previous.tail or "") + tail
    else:
        parent.text = (parent.text or "") + tail
    parent.remove(element)


# ---------------------------------------------------------------------------- Instagram

_CONTEXT_JSON = re.compile(r'"contextJSON":("(?:[^"\\]|\\.)*")')
_SIDECAR = re.compile(r'"isSidecar":true')
_MORE = re.compile(r"(?:…|\.\.\.)\s*more\s*$", re.IGNORECASE)


def instagram_post(ref: PostRef, page: str) -> SocialPost:
    """A post from Instagram's captioned embed page. Pure.

    The page carries the post twice: as data for the embed's script (`contextJSON`,
    with every picture of an album and a reel's video address), and as the HTML a
    browser shows before the script runs. The data is used when the page carries it;
    the HTML otherwise, which has the caption and the first picture only.
    """
    media_data = _instagram_data(page)
    root = lxml_html.fromstring(page) if page.strip() else None
    label = _instagram_label(root) if root is not None else None
    if media_data is not None:
        post = _instagram_from_data(ref, media_data)
    else:
        post = _instagram_from_html(ref, page, root)
    if label:
        post = replace(post, platform_label=label)
    if not post.found:
        return SocialPost(
            ref=ref,
            text_route=ROUTE_INSTAGRAM,
            gaps=(
                gap(
                    "post",
                    GapCode.POST_UNAVAILABLE,
                    "Instagram did not show this post to Factify: it may be private, "
                    "deleted, or shown only to people signed in.",
                ),
            ),
        )
    return post


def _instagram_data(page: str) -> dict[str, Any] | None:
    found = _CONTEXT_JSON.search(page)
    if found is None:
        return None
    try:
        context = json.loads(json.loads(found.group(1)))
    except (ValueError, TypeError):
        return None
    media = ((context or {}).get("gql_data") or {}).get("shortcode_media")
    return media if isinstance(media, dict) else None


def _instagram_from_data(ref: PostRef, data: dict[str, Any]) -> SocialPost:
    edges = (data.get("edge_media_to_caption") or {}).get("edges") or []
    caption = ""
    if edges and isinstance(edges[0], dict):
        caption = str((edges[0].get("node") or {}).get("text") or "")
    owner = data.get("owner") or {}
    children = [
        (edge or {}).get("node") or {}
        for edge in (data.get("edge_sidecar_to_children") or {}).get("edges") or []
    ]
    items = [child for child in children if isinstance(child, dict)] or [data]
    found: list[PostMedia] = []
    videos_unread = pictures_unread = 0
    for child in items:
        item = _instagram_item(child)
        if item is not None:
            found.append(item)
        elif child.get("is_video"):
            videos_unread += 1
        else:
            pictures_unread += 1
    media = tuple(found)
    # Nothing the post holds is left out unsaid: a video with no address in an album
    # is as unread as a reel's.
    gaps: list[Gap] = []
    if videos_unread:
        gaps.append(_video_unread(album=len(items) > 1))
    if pictures_unread:
        gaps.append(
            gap(
                "picture_text",
                GapCode.PICTURE_UNREAD,
                "Instagram gave Factify no address for a picture in this post.",
            )
        )
    text = _clean(caption)
    truncated = bool(_MORE.search(text))
    if truncated:
        gaps.append(_caption_cut())
    duration = next((item.duration_seconds for item in media if item.duration_seconds), None)
    return SocialPost(
        ref=ref,
        author_name=str(owner.get("full_name") or "") or None,
        handle=str(owner.get("username") or "") or None,
        published_at=_date(data.get("taken_at_timestamp")),
        text=text,
        text_route=ROUTE_INSTAGRAM,
        text_complete=not truncated,
        media=media,
        gaps=tuple(gaps),
        duration_seconds=duration,
    )


def _instagram_item(node: dict[str, Any]) -> PostMedia | None:
    dimensions = node.get("dimensions") or {}
    width = _int(dimensions.get("width"))
    height = _int(dimensions.get("height"))
    picture = _largest_resource(node) or str(node.get("display_url") or "")
    if node.get("is_video"):
        video = str(node.get("video_url") or "")
        if not video:
            return None
        duration = node.get("video_duration")
        return PostMedia(
            kind="video",
            url=video,
            width=width,
            height=height,
            duration_seconds=float(duration) if isinstance(duration, int | float) else None,
            variants=((video, None),),
            poster_url=picture or None,
        )
    if not picture:
        return None
    return PostMedia(kind="image", url=picture, width=width, height=height)


def _largest_resource(node: dict[str, Any]) -> str | None:
    resources = [item for item in node.get("display_resources") or [] if isinstance(item, dict)]
    if not resources:
        return None
    best = max(resources, key=lambda item: _int(item.get("config_width")) or 0)
    return str(best.get("src") or "") or None


def _instagram_from_html(ref: PostRef, page: str, root: Any) -> SocialPost:
    if root is None:
        return SocialPost(ref=ref, text_route=ROUTE_INSTAGRAM)
    caption = root.find_class("Caption")
    handle = None
    text = ""
    if caption:
        node = caption[0]
        for name in ("CaptionUsername", "UsernameText"):
            found = node.find_class(name)
            if found:
                handle = found[0].text_content().strip() or None
                for element in found:
                    _drop(element)
        for comments in node.find_class("CaptionComments"):
            _drop(comments)
        for br in node.findall(".//br"):
            br.tail = "\n" + (br.tail or "")
        text = _clean(node.text_content())
    if handle is None:
        username = root.find_class("UsernameText")
        handle = username[0].text_content().strip() or None if username else None
    pictures: list[PostMedia] = []
    for name in ("EmbeddedMediaImage", "EmbeddedMediaImageOverlay"):
        for image in root.find_class(name):
            url = _largest_srcset(image.get("srcset", "")) or image.get("src", "")
            if url:
                pictures.append(PostMedia(kind="image", url=html.unescape(url)))
                break
        if pictures:
            break
    # What the post is, from the embed's own marker, not from its address: a reel is
    # shared under /p/ as often as under /reel/, and a labelled one comes this way.
    media_type = _instagram_media_type(root)
    gaps: list[Gap] = []
    if ref.kind in ("reel", "video") or media_type == "GraphVideo":
        gaps.append(_video_unread())
    elif media_type == "GraphSidecar" or _SIDECAR.search(page):
        gaps.append(
            gap(
                "picture_text",
                GapCode.FIRST_PICTURE_ONLY,
                "This post has several pictures; Instagram showed Factify only the first.",
            )
        )
    elif media_type is None:
        gaps.append(
            gap(
                "video",
                GapCode.VIDEO_UNREAD,
                "Instagram did not say whether this post is a picture or a video; if it "
                "holds a video, Factify did not read it.",
                blocking=False,
            )
        )
    truncated = bool(_MORE.search(text))
    if truncated:
        gaps.append(_caption_cut())
    return SocialPost(
        ref=ref,
        handle=handle,
        text=text,
        text_route=ROUTE_INSTAGRAM,
        text_complete=not truncated,
        media=tuple(pictures[:1]),
        gaps=tuple(gaps),
    )


def _largest_srcset(srcset: str) -> str | None:
    best: tuple[int, str] | None = None
    for entry in srcset.split(","):
        pieces = entry.strip().split()
        if not pieces:
            continue
        width = 0
        if len(pieces) > 1 and pieces[1].endswith("w") and pieces[1][:-1].isdigit():
            width = int(pieces[1][:-1])
        if best is None or width > best[0]:
            best = (width, pieces[0])
    return best[1] if best else None


def _instagram_media_type(root: Any) -> str | None:
    """The embed's own word for the post: GraphImage, GraphVideo or GraphSidecar."""
    for embed in root.find_class("Embed"):
        said = str(embed.get("data-media-type") or "").strip()
        if said:
            return said
    return None


def _instagram_label(root: Any) -> str | None:
    """Instagram's own label on the post: "Altered photo/video. Reviewed by ..."."""
    titles = root.find_class("MediaOverlayInfoTitle")
    if not titles:
        return None
    said = [titles[0].text_content().strip()]
    descriptions = root.find_class("MediaOverlayInfoDescription")
    if descriptions:
        said.append(descriptions[0].text_content().strip())
    return " ".join(part for part in said if part) or None


def _video_unread(*, album: bool = False) -> Gap:
    which = "a video in this post" if album else "this post's video"
    return gap(
        "video",
        GapCode.VIDEO_UNREAD,
        f"Instagram did not give Factify {which}. Upload the video to check it.",
    )


def _caption_cut() -> Gap:
    return gap(
        "post_text",
        GapCode.TEXT_TRUNCATED,
        "Instagram gave Factify only the start of this caption.",
    )


# ------------------------------------------------------------------------------ YouTube


def youtube_post(ref: PostRef, data: dict[str, Any], *, thumbnail: str | None) -> SocialPost:
    """A video's title and channel from YouTube's oEmbed answer. Pure."""
    author_url = str(data.get("author_url") or "")
    path = urlsplit(author_url).path.strip("/") if author_url else ""
    handle = path[1:] if path.startswith("@") else None
    offered = str(data.get("thumbnail_url") or "")
    if offered and (urlsplit(offered).hostname or "") in YOUTUBE_MEDIA_HOSTS:
        thumbnail = offered
    return SocialPost(
        ref=ref,
        author_name=str(data.get("author_name") or "") or None,
        handle=handle,
        title=_clean(str(data.get("title") or "")) or None,
        text_route=ROUTE_YOUTUBE,
        thumbnail_url=thumbnail,
    )
