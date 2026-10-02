"""Record the social reader's fixtures from the real platforms, as FactifyBot.

    docker run --rm --network host -e PYTHONPATH=/rec -v /tmp/rec:/rec --entrypoint \
        python deploy-app /rec/scripts/record_social_fixtures.py --out /rec/social --media

with this checkout's `app/` and `scripts/` copied to /tmp/rec on the server, then the
output copied back to tests/fixtures/social/.

Run on the server. The point of the recording is to know that the platforms' public
embed, oEmbed and syndication addresses answer *us*: FactifyBot's user agent, through
the reader's own `SecureFetcher`, from the server's address. A probe from a
developer's browser, or from a script with a browser's user agent, proves nothing
about that, and some of the earlier probes were exactly that. On a development
machine whose network inspects TLS, `--system-certificates` uses the operating
system's certificate store (as the live tests do).

Every answer is written as it came (`<name>.json` or `<name>.html`), with what was
asked and what came back in `manifest.json`. Pictures and videos are downloaded only
to see that they can be (`--media`), through the reader's own `download`, and only
their size and type are kept.

Few fetches, paced a second apart: a platform that sees a burst from FactifyBot may
stop answering it, and the reader itself depends on that not happening.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import Settings
from app.extraction import social
from app.intake.social_urls import recognise
from app.security.fetcher import USER_AGENT, FetchFailure, FetchResult, SecureFetcher

# The posts recorded: real public posts from the reading audit's test set (2026-10-02),
# named for the case each one is.
X_POSTS = {
    # A video re-posted from another account's post (easyJet footage passed off as
    # flydubai).
    "x4_oneobjective_video": "2105264647691440217",
    # A Hindi post with one photo (a morphed picture of a breakfast meeting).
    "x5_ocjain4_photo": "2100143601443557471",
    # A Telugu news video with four mp4 qualities.
    "x6_zeetelugu_video": "2100138377060532502",
    # A long post that syndication and oEmbed both cut short.
    "x1_httweets_long": "2105365875310354576",
}
# Recorded through oEmbed too: the fallback.
X_OEMBED = ("x4_oneobjective_video", "x1_httweets_long")
# Recorded with their own page: the rest of a long post.
X_PAGES = {"x1_httweets_long": "htTweets"}
# An id no post has: what the syndication endpoint and oEmbed say for a missing post.
X_MISSING = "1"

INSTAGRAM_POSTS = {
    # The Hindu's seven-picture album; the first is a headline card.
    "ig1_the_hindu_album": "https://www.instagram.com/p/Dd-ghgbkrzL/",
    # BBC News's 44-second reel.
    "ig3_bbcnews_reel": "https://www.instagram.com/reel/Dd90zQtDzon/",
    # One AI-made photo, under Instagram's own fact-check label.
    "ig5_venukolangara_labelled": "https://www.instagram.com/p/DcAsngdyjQ0/",
    # A well-formed shortcode with no post behind it.
    "instagram_missing": "https://www.instagram.com/p/AAAAAAAAAAA/",
}

YOUTUBE_VIDEOS = {
    # An AI-made Short of a leopard attacking a train.
    "yt5_leopard_short": "https://www.youtube.com/shorts/ikPJlAdAuaE",
}

_PAUSE_SECONDS = 1.0


class Recorder:
    def __init__(self, out: Path, fetcher: SecureFetcher, reader: social.SocialReader) -> None:
        self.out = out
        self.fetcher = fetcher
        self.reader = reader
        self.manifest: list[dict[str, Any]] = []

    async def get(self, name: str, url: str) -> FetchResult | None:
        """Fetch one address and record it; None when nothing came back."""
        result = await self.fetcher.fetch(url, provider="social")
        await asyncio.sleep(_PAUSE_SECONDS)
        entry: dict[str, Any] = {"name": name, "url": url, "user_agent": USER_AGENT}
        if isinstance(result, FetchFailure):
            entry.update(failure=result.reason, kind=result.kind)
            self.manifest.append(entry)
            return None
        suffix = ".json" if "json" in (result.content_type or "") else ".html"
        entry.update(
            status=result.status_code,
            content_type=result.content_type,
            byte_count=result.byte_count,
            final_url=result.final_url,
            redirect_chain=list(result.redirect_chain),
            fetched_at=result.fetched_at.isoformat(),
        )
        if result.body:
            entry["file"] = f"{name}{suffix}"
            (self.out / entry["file"]).write_bytes(result.body)
        self.manifest.append(entry)
        return result

    async def media(self, name: str, item: social.PostMedia) -> None:
        """Download a picture or video to see that it can be; keep its size only."""
        result = await self.reader.download(item, max_bytes=25 * 1024 * 1024, max_seconds=600)
        await asyncio.sleep(_PAUSE_SECONDS)
        entry: dict[str, Any] = {"name": name, "url": item.url, "user_agent": USER_AGENT}
        if isinstance(result, social.Downloaded):
            entry.update(mime=result.mime, byte_count=len(result.data), downloaded=result.url)
        else:
            entry.update(failure=result.detail, code=result.code.value)
        self.manifest.append(entry)

    def note(self, name: str, **fields: Any) -> None:
        self.manifest.append({"name": name, **fields})


async def record_x(recorder: Recorder, *, media: bool) -> None:
    for name, post_id in X_POSTS.items():
        canonical = f"https://x.com/i/status/{post_id}"
        await recorder.get(f"{name}.syndication", social.x_syndication_url(post_id))
        if name in X_OEMBED:
            await recorder.get(f"{name}.oembed", social.x_oembed_url(canonical))
        if name in X_PAGES:
            await recorder.get(f"{name}.page", social.x_page_url(X_PAGES[name], post_id))
    await recorder.get("x_missing.syndication", social.x_syndication_url(X_MISSING))
    await recorder.get(
        "x_missing.oembed", social.x_oembed_url(f"https://x.com/i/status/{X_MISSING}")
    )
    if not media:
        return
    for name in ("x5_ocjain4_photo", "x6_zeetelugu_video"):
        ref = recognise(f"https://x.com/i/status/{X_POSTS[name]}")
        assert ref is not None
        post = await recorder.reader.read(ref)
        for index, item in enumerate(post.media):
            await recorder.media(f"{name}.media{index + 1}", item)


async def record_instagram(recorder: Recorder, *, media: bool) -> None:
    for name, url in INSTAGRAM_POSTS.items():
        ref = recognise(url)
        assert ref is not None, url
        await recorder.get(f"{name}.embed", social.instagram_embed_url(ref))
        if media and name != "instagram_missing":
            post = await recorder.reader.read(ref)
            # The first picture and any video: enough to know the addresses download.
            items = [*post.pictures[:1], *post.videos[:1]]
            for index, item in enumerate(items):
                await recorder.media(f"{name}.media{index + 1}", item)


async def record_ytdlp(recorder: Recorder) -> None:
    """Whether yt-dlp reads a reel from here without signing in (not used by the reader)."""
    try:
        import yt_dlp  # type: ignore[import-untyped, import-not-found, unused-ignore]
    except ImportError:
        recorder.note("ytdlp", failure="yt-dlp is not installed")
        return
    recorder.note("ytdlp", version=yt_dlp.version.__version__)
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 15,
        "cachedir": False,
        "http_headers": {"User-Agent": USER_AGENT},
    }
    for name in ("ig3_bbcnews_reel", "ig5_venukolangara_labelled"):
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = await asyncio.wait_for(
                    asyncio.to_thread(downloader.extract_info, INSTAGRAM_POSTS[name], False), 60
                )
        except Exception as exc:  # recording what failed is the point
            recorder.note(f"{name}.ytdlp", failure=f"{type(exc).__name__}: {exc}"[:500])
            continue
        formats = (info or {}).get("formats") or []
        recorder.note(f"{name}.ytdlp", formats=len(formats), duration=(info or {}).get("duration"))


async def record_youtube(recorder: Recorder, *, media: bool) -> None:
    for name, url in YOUTUBE_VIDEOS.items():
        ref = recognise(url)
        assert ref is not None and ref.post_id
        await recorder.get(f"{name}.oembed", social.youtube_oembed_url(ref.canonical_url))
        if media:
            thumbnail = social.PostMedia(
                kind="image", url=social.youtube_thumbnail_url(ref.post_id)
            )
            await recorder.media(f"{name}.thumbnail", thumbnail)


async def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("tests/fixtures/social"))
    parser.add_argument("--only", default="x,instagram,youtube", help="comma-separated platforms")
    parser.add_argument("--media", action="store_true", help="also download media once")
    parser.add_argument("--ytdlp", action="store_true", help="also ask yt-dlp for reels")
    parser.add_argument(
        "--system-certificates",
        action="store_true",
        help="trust the operating system's certificates (a network that inspects TLS)",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    only = set(args.only.split(","))
    if args.system_certificates:
        import truststore

        truststore.inject_into_ssl()

    # No .env: nothing here needs a credential, and the defaults are what the server
    # runs with.
    settings = Settings(_env_file=None)
    reader = social.build(settings)
    assert reader is not None
    fetcher = SecureFetcher(
        timeout_seconds=settings.social.timeout_seconds,
        max_bytes=settings.limits.max_upload_bytes,
        accepted_types=social.ACCEPTED_TYPES,
    )
    recorder = Recorder(args.out, fetcher, reader)
    try:
        if "x" in only:
            await record_x(recorder, media=args.media)
        if "instagram" in only:
            await record_instagram(recorder, media=args.media)
            if args.ytdlp:
                await record_ytdlp(recorder)
        if "youtube" in only:
            await record_youtube(recorder, media=args.media)
    finally:
        await fetcher.aclose()

    manifest = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "user_agent": USER_AGENT,
        "entries": recorder.manifest,
    }
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    for entry in recorder.manifest:
        said = entry.get("failure") or f"{entry.get('status', '')} {entry.get('byte_count', '')}"
        print(f"{entry['name']:<48} {said}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
