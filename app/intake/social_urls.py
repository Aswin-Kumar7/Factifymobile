"""Which links are social posts, and the one address each post is known by.

A post on X, Instagram, YouTube or Facebook is shared under many addresses: the
twitter.com and x.com forms, a mobile host, a username in the path or none, a fixer
domain that makes previews work in chat apps, and share parameters (`s`, `t`, `si`,
`igsh`, `feature`) that identify the person who shared it rather than the post. Read
as an ordinary web page, every one of those was a separate cache entry and a separate
fetch of a page that, for a post, holds almost nothing a reader can use.

`recognise` turns any of them into a `PostRef`: the platform, the post's own id, what
kind of post the address says it is, and the one canonical address the post is
cached and read under. It recognises the shape of an address and nothing more; it
never fetches, so a short link (t.co, fb.watch, an Instagram share link) is only
marked `needs_resolving` for the reader to follow.

Pure: no input or output of any kind.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Bumped on any change to how a post is read (this module, app/extraction/social.py,
# or how /v1/verify puts a post's reading together). It is folded into a post's cache
# identity, so a post read under the old reader is read again rather than answered
# from what that reader saw.
READER_VERSION = "2026.10.02.2"
# Bumped on any change to the video reader's prompt, schema or how its answer is read
# (app/extraction/video_reader.py, which takes its VERSION from here). Kept here,
# beside READER_VERSION, so the one identity holds both and a post's video is watched
# again after either changes.
VIDEO_READER_VERSION = "2026.10.02.1"


class Platform(StrEnum):
    X = "x"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    FACEBOOK = "facebook"


@dataclass(frozen=True, slots=True)
class PostRef:
    """A social post, as its address identifies it.

    `kind` is what the address says the post is: post, reel, video, short, live,
    story or share (a short link whose post is not known until it is followed).
    `post_id` is None only for an address that has to be followed first.
    """

    platform: Platform
    post_id: str | None
    kind: str
    canonical_url: str
    needs_resolving: bool = False


# ------------------------------------------------------------------------------- hosts

_X_HOSTS = frozenset(
    {
        "x.com",
        "www.x.com",
        "mobile.x.com",
        "twitter.com",
        "www.twitter.com",
        "mobile.twitter.com",
        # Preview fixers people paste because their chat app shows a card for them.
        # Same post ids, same paths.
        "fxtwitter.com",
        "www.fxtwitter.com",
        "vxtwitter.com",
        "www.vxtwitter.com",
        "fixupx.com",
        "www.fixupx.com",
    }
)
_X_SHORT_HOSTS = frozenset({"t.co"})
_INSTAGRAM_HOSTS = frozenset(
    {"instagram.com", "www.instagram.com", "m.instagram.com", "instagr.am", "www.instagr.am"}
)
_YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"})
_YOUTUBE_EMBED_HOSTS = frozenset({"youtube-nocookie.com", "www.youtube-nocookie.com"})
_YOUTUBE_SHORT_HOSTS = frozenset({"youtu.be", "www.youtu.be"})
_FACEBOOK_HOSTS = frozenset(
    {
        "facebook.com",
        "www.facebook.com",
        "m.facebook.com",
        "mbasic.facebook.com",
        "web.facebook.com",
        "fb.com",
        "www.fb.com",
    }
)
_FACEBOOK_SHORT_HOSTS = frozenset({"fb.watch", "www.fb.watch"})
_PLATFORM_HOSTS = (
    _X_HOSTS
    | _X_SHORT_HOSTS
    | _INSTAGRAM_HOSTS
    | _YOUTUBE_HOSTS
    | _YOUTUBE_EMBED_HOSTS
    | _YOUTUBE_SHORT_HOSTS
    | _FACEBOOK_HOSTS
    | _FACEBOOK_SHORT_HOSTS
)

# ---------------------------------------------------------------------------- ids

# A snowflake id: the 19 digits of today's posts, fewer for the oldest. Anything
# else in that place is not a post id, and a link with one is not read as a post.
_X_ID = re.compile(r"\d{1,20}")
# An X username: letters, digits and underscores, at most 15.
_X_USER = re.compile(r"[A-Za-z0-9_]{1,15}")
# An Instagram shortcode. Public posts' are 11 characters; private accounts' are
# longer, so the bound is loose, but the alphabet is exact.
_INSTAGRAM_CODE = re.compile(r"[A-Za-z0-9_-]{5,64}")
_INSTAGRAM_USER = re.compile(r"[A-Za-z0-9_.]{1,30}")
# A YouTube video id is exactly eleven characters of this alphabet.
_YOUTUBE_ID = re.compile(r"[A-Za-z0-9_-]{11}")
# Facebook's numeric ids, and the opaque `pfbid…` form that replaced them in links.
_FACEBOOK_ID = re.compile(r"(?:\d{1,25}|pfbid[A-Za-z0-9]{10,80})")
_SHORT_CODE = re.compile(r"[A-Za-z0-9_-]{1,64}")

# Query parameters that say which post a Facebook address is; everything else on it
# (`mibextid`, `rdid`, `__cft__`, `ref`, `sfnsn`) identifies the click.
_FACEBOOK_KEPT_PARAMETERS = ("story_fbid", "fbid", "id", "v", "set")


def recognise(url: str) -> PostRef | None:
    """The post this address points at, or None when it is not a recognised post.

    A profile, a hashtag, a search or a home page is not a post and returns None, as
    does a post address whose id is not a well-formed id: it is then read as an
    ordinary web page, as any other link is.
    """
    try:
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower().rstrip(".")
    except ValueError:
        return None
    if parts.scheme.lower() not in {"http", "https"} or not host:
        return None
    segments = [segment for segment in parts.path.split("/") if segment]
    query = dict(parse_qsl(parts.query, keep_blank_values=True))

    if host in _X_HOSTS:
        return _x(segments)
    if host in _X_SHORT_HOSTS:
        return _short(Platform.X, "t.co", segments, kind="share")
    if host in _INSTAGRAM_HOSTS:
        return _instagram(segments)
    if host in _YOUTUBE_HOSTS:
        return _youtube(segments, query)
    if host in _YOUTUBE_EMBED_HOSTS:
        return _youtube_embed(segments)
    if host in _YOUTUBE_SHORT_HOSTS:
        return _youtube_id(segments[0] if segments else "", kind="video")
    if host in _FACEBOOK_HOSTS:
        return _facebook(parts.path, segments, query)
    if host in _FACEBOOK_SHORT_HOSTS:
        # fb.watch is always a video.
        return _short(Platform.FACEBOOK, "fb.watch", segments, kind="video")
    return None


def is_platform_host(url: str) -> bool:
    """Whether an address is on one of the platforms' own hosts, a post or not.

    A short link that ends on one of these without reaching a post has ended on a
    login wall, a profile or a home page: the post was not shown. One that ends
    anywhere else led to an ordinary page, which is read as one.
    """
    try:
        host = (urlsplit(url.strip()).hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    return host in _PLATFORM_HOSTS


def is_video_route(ref: PostRef) -> bool:
    """Whether the address alone says this post is a video.

    YouTube always; Instagram reels and the old IGTV; Facebook videos, reels and
    watch links. An X post may hold a video too, but its address does not say so:
    that is known only once the post is read.
    """
    if ref.platform is Platform.YOUTUBE:
        return True
    if ref.platform in (Platform.INSTAGRAM, Platform.FACEBOOK):
        return ref.kind in {"reel", "video"}
    return False


# ---------------------------------------------------------------------------- X


def _x(segments: list[str]) -> PostRef | None:
    # /<user>/status/<id>[/photo/1|/video/1|/analytics…], /i/status/<id>,
    # /i/web/status/<id>, and the old /<user>/statuses/<id>.
    lowered = [segment.lower() for segment in segments]
    if lowered[:3] == ["i", "web", "status"] and len(segments) >= 4:
        post_id = segments[3]
    elif (
        len(segments) >= 3
        and lowered[1] in {"status", "statuses"}
        and (lowered[0] == "i" or _X_USER.fullmatch(segments[0]))
    ):
        post_id = segments[2]
    else:
        return None
    if not _X_ID.fullmatch(post_id):
        return None
    # Without the username: the post is the same whoever's name is in the path, and
    # an account that changes its name keeps its posts.
    return PostRef(
        platform=Platform.X,
        post_id=post_id,
        kind="post",
        canonical_url=f"https://x.com/i/status/{post_id}",
    )


# ------------------------------------------------------------------------- Instagram

_INSTAGRAM_KINDS = {"p": "post", "reel": "reel", "reels": "reel", "tv": "video"}


def _instagram(segments: list[str]) -> PostRef | None:
    if not segments:
        return None
    first = segments[0].lower()
    if first == "stories":
        # /stories/<user>/<id>: gone within a day, and shown only to people signed
        # in. Recognised so the reader can say that, rather than read the login page
        # as if it were the post.
        if len(segments) >= 3 and _X_ID.fullmatch(segments[2]):
            user = segments[1]
            return PostRef(
                platform=Platform.INSTAGRAM,
                post_id=segments[2],
                kind="story",
                canonical_url=f"https://www.instagram.com/stories/{user}/{segments[2]}/",
            )
        return None
    if first == "share":
        # /share/<token>, /share/p/<token>, /share/reel/<token>: a redirect to the
        # post, known only once followed.
        rest = segments[1:]
        kind = "share"
        if len(rest) >= 2 and rest[0].lower() in _INSTAGRAM_KINDS:
            kind = _INSTAGRAM_KINDS[rest[0].lower()]
            if kind == "post":
                kind = "share"
            rest = rest[1:]
        if not rest or not _SHORT_CODE.fullmatch(rest[0]):
            return None
        path = "/".join(segments[: len(segments) - len(rest) + 1])
        return PostRef(
            platform=Platform.INSTAGRAM,
            post_id=None,
            kind=kind,
            canonical_url=f"https://www.instagram.com/{path}/",
            needs_resolving=True,
        )
    # /<kind>/<code> or /<user>/<kind>/<code>.
    if first in _INSTAGRAM_KINDS and len(segments) >= 2:
        marker, code = first, segments[1]
    elif (
        len(segments) >= 3
        and segments[1].lower() in _INSTAGRAM_KINDS
        and _INSTAGRAM_USER.fullmatch(segments[0])
    ):
        marker, code = segments[1].lower(), segments[2]
    else:
        return None
    if not _INSTAGRAM_CODE.fullmatch(code):
        return None
    kind = _INSTAGRAM_KINDS[marker]
    # /p/ works for every kind of post, a reel's address only for a video. The old
    # IGTV address is read through /p/ for that reason.
    path = "reel" if kind == "reel" else "p"
    return PostRef(
        platform=Platform.INSTAGRAM,
        post_id=code,
        kind=kind,
        canonical_url=f"https://www.instagram.com/{path}/{code}/",
    )


# --------------------------------------------------------------------------- YouTube


def _youtube_id(candidate: str, *, kind: str) -> PostRef | None:
    if not _YOUTUBE_ID.fullmatch(candidate):
        return None
    return PostRef(
        platform=Platform.YOUTUBE,
        post_id=candidate,
        kind=kind,
        canonical_url=f"https://www.youtube.com/watch?v={candidate}",
    )


def _youtube(segments: list[str], query: dict[str, str]) -> PostRef | None:
    if not segments:
        return None
    first = segments[0].lower()
    if first == "watch":
        return _youtube_id(query.get("v", ""), kind="video")
    if len(segments) >= 2 and first in {"shorts", "live", "embed", "v"}:
        kind = {"shorts": "short", "live": "live"}.get(first, "video")
        return _youtube_id(segments[1], kind=kind)
    return None


def _youtube_embed(segments: list[str]) -> PostRef | None:
    if len(segments) >= 2 and segments[0].lower() == "embed":
        return _youtube_id(segments[1], kind="video")
    return None


# -------------------------------------------------------------------------- Facebook


def _facebook(path: str, segments: list[str], query: dict[str, str]) -> PostRef | None:
    lowered = [segment.lower() for segment in segments]
    if not segments:
        return None
    post_id: str | None = None
    kind = "post"
    needs_resolving = False

    if lowered[0] == "share" and len(segments) >= 2:
        # /share/p/<code>, /share/v/<code>, /share/r/<code>, /share/<code>.
        letter = lowered[1] if len(segments) >= 3 else ""
        code = segments[2] if letter else segments[1]
        if not _SHORT_CODE.fullmatch(code):
            return None
        kind = {"v": "video", "r": "reel"}.get(letter, "share")
        needs_resolving = True
    elif lowered[0] in {"permalink.php", "story.php"}:
        post_id = query.get("story_fbid")
    elif lowered[0] == "photo.php" or (lowered[0] == "photo" and len(segments) == 1):
        post_id = query.get("fbid")
    elif lowered[0] == "watch":
        post_id = query.get("v")
        kind = "video"
    elif lowered[0] == "reel" and len(segments) >= 2:
        post_id = segments[1]
        kind = "reel"
    elif len(segments) >= 3 and lowered[1] in {"posts", "videos", "photos"}:
        # /<page>/posts/<id>, /<page>/videos/<id> or /<page>/videos/<slug>/<id>,
        # /<page>/photos/<album>/<id>.
        kind = "video" if lowered[1] == "videos" else "post"
        post_id = next(
            (segment for segment in reversed(segments[2:]) if _FACEBOOK_ID.fullmatch(segment)),
            None,
        )
    else:
        return None
    if not needs_resolving and (post_id is None or not _FACEBOOK_ID.fullmatch(post_id)):
        return None
    kept = [(key, query[key]) for key in _FACEBOOK_KEPT_PARAMETERS if key in query]
    canonical = urlunsplit(
        ("https", "www.facebook.com", path.rstrip("/") or "/", urlencode(kept), "")
    )
    return PostRef(
        platform=Platform.FACEBOOK,
        post_id=post_id,
        kind=kind,
        canonical_url=canonical,
        needs_resolving=needs_resolving,
    )


# -------------------------------------------------------------------------- short links


def _short(platform: Platform, host: str, segments: list[str], *, kind: str) -> PostRef | None:
    if len(segments) != 1 or not _SHORT_CODE.fullmatch(segments[0]):
        return None
    return PostRef(
        platform=platform,
        post_id=None,
        kind=kind,
        canonical_url=f"https://{host}/{segments[0]}",
        needs_resolving=True,
    )
