"""A social post, checked from everything it holds (contract 1.8, 2026-10-02).

A link to a post on X, Instagram or YouTube used to be read as a web page: the
post's words at best, never its pictures or its video, where the claim usually is
(the reading audit: 19 of 45 right, and no picture or video in a link ever seen).
Here a post is read through the platform's own embed addresses
(`app/extraction/social.py`) and checked on all of it, the same way an upload is:

  * its words, and the words of a post it quotes;
  * each picture (up to `social.max_pictures`), downloaded and read like an uploaded
    picture - the words on it and what it shows - and put through the picture checks;
  * its video (the first `MAX_VIDEOS` of an album), downloaded and read like an
    uploaded video - what is said, the words on its frames, what it shows - with its
    keyframes put through the picture and face checks;
  * for YouTube, which lets no server download a video: its title and channel, its
    description and captions as the search vendor reads the page, and its thumbnail
    read as a picture. The video itself is watched only when a video reader is set up
    (`app/extraction/video_reader.py`); when it is not, the answer says the video was
    not watched, and is never held back for that alone;
  * the article a post links to, read as part of it - and never counted as
    independent confirmation of the post that shares it.

What could not be read is said, part by part (`input_read`, `skipped[].kind`). An
answer is held back only when no claim was found and what was missed could hold one
(`answer_without_claims`); a post read in part is checked on what was read and is
never TRUE (`served_policy`). A post its platform would not show at all, and never
said is gone, is read as a web page, as every post link was before (`_falls_back`).

A repeated post is answered from the verdict cache by the post's own identity before
anything of it is downloaded.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field, replace
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import Request

from app.api import verify as checks
from app.api.schemas import (
    AdvisoryResponse,
    MediaReportResponse,
    SkippedCheckResponse,
    SpeechResponse,
    VerifyRequest,
    VerifyResponse,
    advisory_to_response,
    media_report_to_response,
)
from app.extraction.reading import (
    DESCRIPTION,
    THUMBNAIL_DESCRIBED,
    THUMBNAIL_TEXT,
    Gap,
    GapCode,
    PartKind,
    Reading,
    ReadingPolicy,
    ReadPart,
    gap,
    linked_article_label,
    picture_description_label,
    picture_text_label,
    platform_name,
    served_policy,
)
from app.extraction.social import PostMedia, SocialPost
from app.intake.normalizer import (
    InputType,
    IntakeRejected,
    NormalisedIntake,
    normalise_upload,
    normalise_url,
)
from app.intake.social_urls import Platform, PostRef, is_platform_host, recognise
from app.media.composed import compose
from app.observability.logging import event
from app.orchestration.background import set_phase
from app.orchestration.pipeline import BACKGROUND_CEILING_SECONDS, BACKGROUND_MIN_READING_SECONDS
from app.sources.base import check_seconds, current_reference_date
from app.sources.verification import page_key

logger = logging.getLogger("factify.api.post_checks")

# How many of a post's videos are read: an album of five reels would take most of a
# check's time to hear and read. The rest are said to be unread.
MAX_VIDEOS = 2

# How far into a check a post's next video may still be started. Each video can take
# `SPEECH_SECONDS` to hear after its download, and the search keeps
# `BACKGROUND_MIN_READING_SECONDS` after all of it; a second video started later than
# this took a two-clip post past `BACKGROUND_CEILING_SECONDS` and the app's wait
# (2026-10-02 review). Ninety seconds, with half a minute for downloading and finding
# claims.
NEXT_VIDEO_BY = (
    BACKGROUND_CEILING_SECONDS - BACKGROUND_MIN_READING_SECONDS - checks.SPEECH_SECONDS - 30.0
)

# Said beside the answer for a YouTube video: what could not be checked of it.
YOUTUBE_LIMIT = (
    "YouTube does not let Factify download the video, so it was not watched: its voice "
    "and face-swap checks did not run, and the picture checks looked at its thumbnail only."
)


@dataclass(slots=True)
class _Picture:
    """One picture of the post, read, with its picture checks started beside it.

    `thumbnail`: a YouTube video's thumbnail, YouTube's picture of the video and not
    the video itself. Its checks are shown, and never decide the answer: an AI-looking
    thumbnail on a real video is not an AI-made post (`_made_by_ai`).
    """

    intake: NormalisedIntake
    read: Any  # verify._Read
    inspection: asyncio.Task[Any] | None
    seen: Any  # verify._Seen
    thumbnail: bool = False


@dataclass(slots=True)
class _Video:
    """One video of the post, read whole, and the frame its answer is checked through."""

    intake: NormalisedIntake
    video: checks.VideoRead


@dataclass(slots=True)
class PostRead:
    """A post as read: the reading, and the pictures and videos it was read from."""

    reading: Reading
    post: SocialPost
    pictures: list[_Picture] = field(default_factory=list)
    videos: list[_Video] = field(default_factory=list)
    # The pages the post is: its own address, and the article it links to.
    own_pages: set[str] = field(default_factory=set)


def post_identity(intake: NormalisedIntake, ref: PostRef, *, watched: bool) -> NormalisedIntake:
    """A post as its verdict is cached: its own one address and the readers' versions
    (`normalise_url`), and for YouTube whether the video itself could be watched - an
    answer from the title and thumbnail is not served once the video can be."""
    if ref.platform is not Platform.YOUTUBE:
        return intake
    seen = "watched" if watched else "not_watched"
    return replace(intake, cache_identity=f"{intake.cache_identity}|video:{seen}")


async def checked_post(
    request: Request,
    payload: VerifyRequest,
    intake: NormalisedIntake,
    ref: PostRef,
    *,
    case_id: UUID,
    arrived: float,
) -> VerifyResponse:
    """A social post: read whole, its claims found in all of it, and checked."""
    orchestrator = checks.get_orchestrator(request)
    reader = request.app.state.social_reader
    keyed = post_identity(
        intake, ref, watched=getattr(request.app.state, "video_reader", None) is not None
    )
    set_phase("reading_post")

    # A repeat is answered before anything of the post is downloaded or read.
    hit = (
        None if payload.recheck else await orchestrator.cached(keyed, case_id=case_id)  # type: ignore[attr-defined]
    )
    if hit is not None:
        event(
            logger,
            "verify request served",
            module="api.post_checks",
            outcome="ok",
            action=hit.action.value,
            claims=0,
            from_cache=True,
            platform=ref.platform.value,
            elapsed_ms=hit.elapsed_ms,
        )
        served = await checks.cached_full_response(request, hit) or checks._thin(hit)
        return checks.recalled(request, keyed.cache_identity, served)

    post: SocialPost = await reader.read(ref)
    if _falls_back(post):
        # The platform would not show the post - a login page for this server, a
        # refusal, a moment's failure - and never said it is gone. Read as a web page,
        # the way every post link was before 1.8 (its words from the page, its
        # publisher's summary, or the search vendor's copy), and said: what is in its
        # pictures and video was not read, and the answer is not kept for the post.
        name = platform_name(ref.platform.value) or "The platform"
        missed = gap(
            "post",
            GapCode.POST_UNAVAILABLE,
            f"{name} did not show Factify the post itself, so any picture or video in it "
            "was not read; its web page was read instead.",
            blocking=False,
        )
        event(
            logger,
            "post read as a web page",
            module="api.post_checks",
            outcome="degraded",
            platform=ref.platform.value,
            gaps=[item.code.value for item in post.gaps],
        )
        return await checks.checked_input(
            request, payload, intake, case_id=case_id, arrived=arrived, unread=(missed,)
        )
    if post.not_a_post_url:
        # A short link that led to an article, not a post: read as any link is, with
        # nothing of a post missed.
        try:
            page = normalise_url(post.not_a_post_url, consent=payload.consent_to_process_media)
        except IntakeRejected:
            page = None
        if page is not None:
            return await checks.checked_input(
                request, payload, page, case_id=case_id, arrived=arrived
            )
        post = replace(
            post,
            gaps=(
                *post.gaps,
                gap(
                    "post", GapCode.POST_UNAVAILABLE, "The short link led nowhere Factify can read."
                ),
            ),
        )

    read = await read_post(
        request, post, background=check_seconds.get() is not None, arrived=arrived
    )
    reading = read.reading
    if post.published_at is not None:
        # What "today" and "on Monday" in the post mean (`current_reference_date`).
        current_reference_date.set(post.published_at.date())
    chosen = served_policy(reading, accept_partial=payload.accept_partial)
    # A YouTube video's thumbnail is checked for what it shows even when its title and
    # description hold few words of their own (a "#shorts #leopard" Short): it is the
    # only picture of the video there is, and is never asked a picture's own questions
    # instead (`media_intake`). A post's wordless photograph is, as an upload's is.
    composed = compose(reading) if ref.platform is Platform.YOUTUBE else checks._to_check(reading)

    # The picture the answer's own picture questions are asked of - has it been
    # published before - when the post has no claim in its words: its first picture,
    # or the frame its first video is checked through. A YouTube thumbnail is not
    # asked them: it is YouTube's picture of the video, not the post's.
    media_intake: NormalisedIntake | None = None
    if read.pictures and ref.platform is not Platform.YOUTUBE:
        media_intake = read.pictures[0].intake
    elif read.videos:
        media_intake = read.videos[0].intake

    claims: list[Any] = []
    reason: str | None = None
    if chosen is not ReadingPolicy.WITHHOLD and composed.text.strip():
        set_phase("finding_claims")
        extracted = await checks._extract_from_document(
            request, keyed, composed.text, authored=checks._authored(reading)
        )
        claims = list(extracted.claims)
        reason = extracted.reason
    if not claims and media_intake is None:
        # Nothing to check: held back when what was missed could hold the claim, said
        # to have nothing to check otherwise (`withheld_without_claims`). Neither is
        # charged, and the thumbnail's picture checks, with no answer to stand
        # beside, are stopped.
        for picture in read.pictures:
            if picture.inspection is not None:
                picture.inspection.cancel()
        return await checks.answer_without_claims(
            request,
            keyed,
            reading,
            case_id=case_id,
            reason=reason,
            composed=composed,
        )

    # Checked through the post's own address when its words hold claims, and through
    # its picture when they do not - in both cases kept under the post's identity, so
    # the next person to share it is answered from the cache.
    checked_as = keyed
    if not claims and media_intake is not None:
        checked_as = replace(
            media_intake, cache_identity=keyed.cache_identity, language=keyed.language
        )

    set_phase("checking")
    # A video's reading takes a minute or more; the search keeps its own time after
    # it, within the whole check's ceiling, as for an uploaded video.
    searching = checks._searching_seconds(time.perf_counter() - arrived) if read.videos else None
    budget = check_seconds.set(searching) if searching is not None else None
    try:
        result = await orchestrator.verify(  # type: ignore[attr-defined]
            checked_as,
            case_id=case_id,
            claims=claims,
            started_at=time.perf_counter() if read.videos else arrived,
            fresh=payload.recheck,
            own_pages=frozenset(read.own_pages),
            synthetic=_made_by_ai(read) if _inspected(read) else None,
            noted=checks.gaps_as_skips(checks.noted_gaps(reading)),
            partial_input=chosen is ReadingPolicy.CHECK_PARTIALLY,
        )
    finally:
        if budget is not None:
            check_seconds.reset(budget)

    response = await checks._from_cache(request, result) or checks.to_response(result)
    if result.from_cache:
        return checks.recalled(request, keyed.cache_identity, response)
    if reason:
        response = response.model_copy(
            update={
                "skipped": (
                    *response.skipped,
                    SkippedCheckResponse(check="claim_extraction", reason=reason),
                )
            }
        )
    response = checks.with_reading(
        response, reading, composed, partially=chosen is ReadingPolicy.CHECK_PARTIALLY
    )
    response = await _with_media_checks(response, read)
    event(
        logger,
        "verify request served",
        module="api.post_checks",
        outcome="ok",
        action=result.action.value,
        claims=len(claims),
        from_cache=False,
        platform=ref.platform.value,
        pictures=len(read.pictures),
        videos=len(read.videos),
        read_parts=len(reading.parts),
        read_gaps=[item.code.value for item in reading.gaps],
        checked_partially=chosen is ReadingPolicy.CHECK_PARTIALLY,
        document_chars=len(composed.text),
        elapsed_ms=result.elapsed_ms,
    )
    checks.remember_reading(request, keyed.cache_identity, response)
    return response


# What the social reader says of a post its platform says is gone (`social._unavailable`):
# deleted, made private, or a wrong link. Such a post is not read as a web page.
_GONE = "does not exist"


def _falls_back(post: SocialPost) -> bool:
    """Whether a post the platform would not show is read as a web page instead.

    Yes when nothing of it came back and the platform never said it is gone: a login
    page or a refusal for this server, a reader that failed, the per-minute pacing.
    The embed addresses were tried from a desk, never from the server's own address,
    and the web page read most posts' words before 1.8 (2026-10-02 review). Not a
    post its platform says does not exist, a story (seen only signed in), a platform
    Factify does not read, or a short link that led to an ordinary page, which is read
    as that page. A YouTube video its oEmbed did not describe is still read from its
    page and thumbnail (`_read_youtube`).
    """
    if post.found or post.not_a_post_url:
        return False
    if not post.gaps:
        return post.ref.platform is not Platform.YOUTUBE
    return not any(
        item.code in (GapCode.LOGIN_REQUIRED, GapCode.NOT_SUPPORTED)
        or (item.code is GapCode.POST_UNAVAILABLE and _GONE in item.detail)
        for item in post.gaps
    )


# ------------------------------------------------------------------------- reading


async def read_post(
    request: Request, post: SocialPost, *, background: bool, arrived: float | None = None
) -> PostRead:
    """Everything a post holds, read: its words, pictures, video and linked article.

    Never raises for a picture or a video that could not be read: each is a gap.
    Videos are read only in a background check (`background`); a quick check says so.
    `arrived`, when the check began: a second video is not started past
    `NEXT_VIDEO_BY` seconds of it.
    """
    ref = post.ref
    read = PostRead(
        reading=Reading(
            kind="social_post",
            platform=ref.platform.value,
            url=ref.canonical_url,
            author=post.author_name,
            handle=post.handle,
            published_at=post.published_at,
            parts=_post_parts(post),
            gaps=post.gaps,
        ),
        post=post,
        own_pages=_post_pages(post),
    )
    unavailable = any(
        item.code in (GapCode.POST_UNAVAILABLE, GapCode.LOGIN_REQUIRED, GapCode.NOT_SUPPORTED)
        for item in post.gaps
    )
    if unavailable and not post.found:
        return read
    if not post.found and not post.gaps and ref.platform is not Platform.YOUTUBE:
        # Nothing came back and nothing was said: never "nothing to check".
        read.reading = read.reading.plus(
            gaps=(
                gap(
                    "post",
                    GapCode.POST_UNAVAILABLE,
                    f"{platform_name(ref.platform.value)} did not show this post to Factify.",
                ),
            )
        )
        return read

    if ref.platform is Platform.YOUTUBE:
        await _read_youtube(request, read)
    else:
        if post.pictures:
            set_phase("reading_pictures")
            await _read_pictures(request, read, post.pictures)
        if post.videos:
            set_phase("reading_video")
            await _read_videos(request, read, post.videos, background=background, arrived=arrived)
    try:
        await _read_linked(request, read)
    except Exception:  # the article a post links to is a help, never a dependency
        logger.exception("the article a post links to could not be read")
    return read


def _post_pages(post: SocialPost) -> set[str]:
    """Every address the post itself is found under, none of which may be evidence for
    it: its canonical one, and for X the author's own address of it on both hosts - the
    form a search result for the post gives."""
    ref = post.ref
    pages = {page_key(ref.canonical_url)}
    if ref.platform is Platform.X and ref.post_id and post.handle:
        for host in ("x.com", "twitter.com"):
            pages.add(page_key(f"https://{host}/{post.handle}/status/{ref.post_id}"))
    if ref.platform is Platform.YOUTUBE and ref.post_id:
        for form in ("watch?v=", "shorts/"):
            pages.add(page_key(f"https://www.youtube.com/{form}{ref.post_id}"))
    return pages


def _post_parts(post: SocialPost) -> tuple[ReadPart, ...]:
    """The post's words; the platform's own label on it, when it has one, as a note."""
    parts = post.parts()
    if not post.platform_label:
        return parts
    label = f"Instagram's own label on this post: {post.platform_label}"
    return tuple(
        replace(part, note=label) if part.kind is PartKind.POST_TEXT else part for part in parts
    )


async def _read_pictures(request: Request, read: PostRead, pictures: tuple[PostMedia, ...]) -> None:
    """Each picture downloaded and read like an uploaded picture, all at once."""
    total = len(pictures)
    found = await asyncio.gather(
        *(
            _read_picture(request, read.post, item, index=index, total=total)
            for index, item in enumerate(pictures, start=1)
        )
    )
    for picture, parts, gaps in found:
        read.reading = read.reading.plus(parts=parts, gaps=gaps)
        if picture is not None:
            read.pictures.append(picture)


async def _read_picture(
    request: Request,
    post: SocialPost,
    item: PostMedia,
    *,
    index: int,
    total: int,
    thumbnail: bool = False,
) -> tuple[_Picture | None, tuple[ReadPart, ...], tuple[Gap, ...]]:
    """One picture: downloaded from the platform's own media host, read - its words and
    what it shows - and put through the picture checks. Never raises: a picture whose
    reading broke is one picture unread, never a failed check."""
    if thumbnail:
        subject = "The video's thumbnail"
    elif total <= 1:
        subject = "The post's picture"
    else:
        subject = f"Picture {index} of {total}"
    if item.in_quoted_post:
        subject += " in the quoted post"
    try:
        return await _picture(
            request, item, index=index, total=total, thumbnail=thumbnail, subject=subject
        )
    except Exception as error:
        logger.exception("a post's picture could not be read")
        return (
            None,
            (),
            (
                gap(
                    "thumbnail" if thumbnail else "picture_text",
                    GapCode.PICTURE_UNREAD,
                    f"{subject} could not be read ({type(error).__name__}).",
                ),
            ),
        )


async def _picture(
    request: Request,
    item: PostMedia,
    *,
    index: int,
    total: int,
    thumbnail: bool,
    subject: str,
) -> tuple[_Picture | None, tuple[ReadPart, ...], tuple[Gap, ...]]:
    settings = request.app.state.settings
    max_bytes = settings.limits.max_upload_bytes
    got = await request.app.state.social_reader.download(item, max_bytes=max_bytes)
    if isinstance(got, Gap):
        return None, (), (replace(got, detail=f"{subject} could not be downloaded."),)
    intake: NormalisedIntake | None
    try:
        intake = normalise_upload(
            got.data, max_bytes=max_bytes, declared_type=got.mime, consent=True
        )
    except IntakeRejected as rejected:
        intake = None
        why = str(rejected)
    else:
        why = f"it is not a picture ({intake.input_type.value})"
    if intake is None or intake.input_type is not InputType.IMAGE:
        return (
            None,
            (),
            (
                gap(
                    "picture_text",
                    GapCode.PICTURE_UNREAD,
                    f"{subject} could not be read: {why}.",
                ),
            ),
        )

    inspection = checks._inspect_picture(request, intake)
    picture_read = await checks._read_document(request, intake)
    key = await _kept(request, intake.primary.data)
    shown = picture_read.shown
    seen = checks._Seen(
        kind=shown.kind if shown is not None else None,
        text_area=shown.text_area if shown is not None else None,
    )
    text_label, described_label = _picture_labels(
        index, total, quoted=item.in_quoted_post, thumbnail=thumbnail
    )
    labels = {
        PartKind.PICTURE_TEXT: text_label,
        PartKind.PICTURE_DESCRIPTION: described_label,
    }
    parts = tuple(
        replace(part, label=labels.get(part.kind, part.label), media_key=key)
        for part in picture_read.reading.parts
    )
    gaps = tuple(
        replace(
            item_gap,
            part="thumbnail" if thumbnail else item_gap.part,
            detail=f"{subject}: {item_gap.detail}",
        )
        for item_gap in picture_read.reading.gaps
    )
    found = _Picture(
        intake=intake, read=picture_read, inspection=inspection, seen=seen, thumbnail=thumbnail
    )
    return found, parts, gaps


async def _kept(request: Request, data: bytes | None) -> str | None:
    """The picture kept on our own address, for the answer to show it from there and
    never from the platform's; None when it could not be. Never raises."""
    inspector = getattr(request.app.state, "media_inspector", None)
    keep = getattr(inspector, "keep_picture", None)
    if keep is None or data is None:
        return None
    try:
        key: str | None = await asyncio.to_thread(keep, data)
    except Exception:
        logger.exception("a post's picture could not be kept for the answer")
        return None
    return key


def _picture_labels(index: int, total: int, *, quoted: bool, thumbnail: bool) -> tuple[str, str]:
    """The labels of a picture's words and of what it shows, as extraction reads them."""
    if thumbnail:
        return THUMBNAIL_TEXT, THUMBNAIL_DESCRIBED
    text = picture_text_label(index, total)
    described = picture_description_label(index, total)
    if quoted:
        text += ", in the quoted post"
        described = described.replace(" (described", ", in the quoted post (described")
    return text, described


async def _read_videos(
    request: Request,
    read: PostRead,
    videos: tuple[PostMedia, ...],
    *,
    background: bool,
    arrived: float | None = None,
) -> None:
    """The post's videos, downloaded and read like an uploaded video, one at a time:
    each is heard and read on the server's own processors.

    The first `MAX_VIDEOS` of them, and a later one only while there is time for it
    (`NEXT_VIDEO_BY`); those not read are said to be, without holding the answer back.
    """
    if not background:
        read.reading = read.reading.plus(
            gaps=(
                gap(
                    "video",
                    GapCode.NEEDS_BACKGROUND,
                    "Factify reads a post's video only in a background check; this check "
                    "read the post's words and pictures.",
                ),
            )
        )
        return
    total = min(len(videos), MAX_VIDEOS)
    window = checks._video_window(request)
    looked_at = 0
    for index, item in enumerate(videos[:MAX_VIDEOS], start=1):
        if index > 1 and arrived is not None and time.perf_counter() - arrived > NEXT_VIDEO_BY:
            # Another video would take the check past the person's wait.
            break
        looked_at = index
        await _read_video(request, read, item, index=index, total=total, window=window)
    if looked_at < len(videos):
        read.reading = read.reading.plus(
            gaps=(
                gap(
                    "video",
                    GapCode.VIDEO_UNREAD,
                    f"The post has {len(videos)} videos; Factify read the first {looked_at}.",
                    blocking=False,
                ),
            )
        )


async def _read_video(
    request: Request, read: PostRead, item: PostMedia, *, index: int, total: int, window: int
) -> None:
    """One of the post's videos, downloaded and read like an uploaded video; a gap
    when it could not be. Never raises for a video that breaks the reader."""
    settings = request.app.state.settings
    subject = "The post's video" if total <= 1 else f"Video {index} of {total}"
    if item.in_quoted_post:
        subject += " in the quoted post"
    got = await request.app.state.social_reader.download(
        item, max_bytes=settings.limits.max_upload_bytes, max_seconds=window
    )
    if isinstance(got, Gap):
        read.reading = read.reading.plus(gaps=(_not_downloaded(got, subject),))
        return
    why: str | None = None
    video: checks.VideoRead | None = None
    try:
        extracted, video = await checks.read_video(request, got.data, window=window)
        why = extracted.reason
    except Exception as error:  # a video that breaks the reader is one video unread
        logger.exception("a post's video could not be read")
        why = type(error).__name__
    middle: NormalisedIntake | None = None
    if video is not None:
        try:
            middle = normalise_upload(
                video.middle,
                max_bytes=settings.limits.max_upload_bytes,
                declared_type="image/jpeg",
                consent=True,
            )
        except IntakeRejected as rejected:
            why = str(rejected)
            if video.inspection is not None:
                video.inspection.cancel()
    if video is None or middle is None:
        read.reading = read.reading.plus(
            gaps=(
                gap(
                    "video",
                    GapCode.VIDEO_UNREAD,
                    f"{subject} could not be read" + (f" ({why})." if why else "."),
                ),
            )
        )
        return
    labels = _video_labels(index, total, quoted=item.in_quoted_post)
    numbered = total > 1 or item.in_quoted_post
    read.reading = read.reading.plus(
        parts=tuple(
            replace(part, label=labels.get(part.kind, part.label))
            for part in video.read.reading.parts
        ),
        gaps=tuple(
            replace(found, detail=f"{subject}: {found.detail}") if numbered else found
            for found in video.read.reading.gaps
        ),
    )
    read.videos.append(_Video(intake=middle, video=video))


def _video_labels(index: int, total: int, *, quoted: bool) -> dict[PartKind, str]:
    """A video's labels: the upload's own for a post's one video, numbered for more."""
    if total <= 1 and not quoted:
        return {}
    which = f"video {index} of {total}" if total > 1 else "the video"
    where = ", in the quoted post" if quoted else ""
    return {
        PartKind.TRANSCRIPT: f"Said in {which}{where}",
        PartKind.ON_SCREEN_TEXT: f"Text shown in {which}{where}",
        PartKind.VIDEO_DESCRIPTION: f"What {which} shows{where} (described by Factify)",
    }


def _not_downloaded(found: Gap, subject: str) -> Gap:
    """A video the reader could not download, said of which video it is."""
    if found.code is GapCode.TOO_LARGE:
        detail = f"{subject} is too large for Factify to download, even at its lowest quality."
    else:
        detail = f"{subject} could not be downloaded."
    return replace(found, detail=detail)


async def _read_youtube(request: Request, read: PostRead) -> None:
    """A YouTube video: what its page says, the video when it can be watched, and its
    thumbnail read as a picture.

    YouTube lets no server download a video. With a video reader set up, the video is
    watched at its address; without one, it is not, and that is said - and the answer
    is still given on the title, the description and captions, and the thumbnail.
    """
    post = read.post
    # Its description and captions, as the search vendor reads its page: the route
    # every YouTube link took before, and the one that reads what is said in it.
    page = await checks._vendor_read(request, post.ref.canonical_url)
    if page and page.strip():
        text = page.strip()
        limit = checks._MAX_ARTICLE_CHARS
        read.reading = read.reading.plus(
            parts=(
                ReadPart(
                    kind=PartKind.DESCRIPTION,
                    text=text[:limit],
                    route="vendor_extract",
                    label=DESCRIPTION,
                    complete=len(text) <= limit,
                    note="the video's description and captions, as its YouTube page gives them",
                ),
            ),
            gaps=(
                (
                    gap(
                        "description",
                        GapCode.CUT_OFF,
                        f"The video's page holds more text than Factify reads; its first "
                        f"{limit:,} characters were read.",
                        blocking=False,
                    ),
                )
                if len(text) > limit
                else ()
            ),
        )
    else:
        read.reading = read.reading.plus(
            gaps=(
                gap(
                    "description",
                    GapCode.DESCRIPTION_UNREAD,
                    "The video's description and captions could not be read.",
                ),
            )
        )

    watched = await _watched(request, post)
    if watched is not None and watched.succeeded:
        # Every gap of the watching is said and none holds the answer back: without a
        # video reader the video is not watched at all, and the answer is given.
        read.reading = read.reading.plus(
            parts=watched.parts(),
            gaps=tuple(replace(item, blocking=False) for item in watched.gaps()),
        )
        return
    read.reading = read.reading.plus(
        gaps=(
            gap(
                "video",
                GapCode.VIDEO_UNREAD,
                "Factify did not watch the video itself: YouTube does not let it be "
                "downloaded. Its title, description, captions and thumbnail were read "
                "instead.",
                blocking=False,
            ),
        ),
        limits=(YOUTUBE_LIMIT,),
    )
    if post.thumbnail_url:
        set_phase("reading_pictures")
        picture, parts, gaps = await _read_picture(
            request,
            post,
            PostMedia(kind="image", url=post.thumbnail_url),
            index=1,
            total=1,
            thumbnail=True,
        )
        read.reading = read.reading.plus(parts=parts, gaps=_not_blocking(gaps))
        if picture is not None:
            read.pictures.append(picture)


def _not_blocking(gaps: tuple[Gap, ...]) -> tuple[Gap, ...]:
    """A thumbnail's gaps: said, never holding the answer back - it is YouTube's
    picture of the video, not the claim."""
    return tuple(replace(item, blocking=False) for item in gaps)


async def _watched(request: Request, post: SocialPost) -> Any | None:
    """The video watched by the video reader, or None when there is none set up."""
    reader = getattr(request.app.state, "video_reader", None)
    if reader is None or not post.ref.post_id:
        return None
    set_phase("reading_video")
    settings = request.app.state.settings
    try:
        return await reader.read_youtube(
            post.ref.post_id, max_seconds=settings.social.youtube_max_seconds
        )
    except Exception:  # the reader never raises; a failure here is a video unwatched
        logger.exception("the YouTube video could not be watched")
        return None


def _outbound(post: SocialPost) -> str | None:
    """The article a post links to: its first link that is not to a post or a
    platform's own page."""
    for link in post.links:
        try:
            scheme = urlsplit(link).scheme.lower()
        except ValueError:
            continue
        if scheme in ("http", "https") and recognise(link) is None and not is_platform_host(link):
            return link
    return None


async def _read_linked(request: Request, read: PostRead) -> None:
    """The article the post links to, read as part of the post.

    Never evidence for the post that shares it (`own_pages`): a newspaper's post of
    its own story was confirmed by the story (x-1, 2026-10-02). An article that gave
    only its headline is left out, and said to be unread: the post's own words carry
    its claim.
    """
    link = _outbound(read.post)
    if link is None:
        return
    read.own_pages.add(page_key(link))
    page = await checks._read_linked_article(request, link)
    if page is None:
        read.reading = read.reading.plus(
            gaps=(
                gap(
                    "linked_page",
                    GapCode.LINKED_PAGE_UNREAD,
                    "The article the post links to could not be read; the post was "
                    "checked on its own words.",
                ),
            )
        )
        return
    if page.partial:
        read.reading = read.reading.plus(
            gaps=(
                gap(
                    "linked_page",
                    GapCode.LINKED_PAGE_UNREAD,
                    "The article the post links to gave only its headline; it was left "
                    "out of what was checked.",
                ),
            )
        )
        return
    read.reading = read.reading.plus(
        parts=(
            ReadPart(
                kind=PartKind.LINKED_ARTICLE,
                text=page.text,
                route=page.route,
                label=linked_article_label(urlsplit(link).hostname),
                complete=not page.truncated,
                note=f"read from {link}",
            ),
        ),
        gaps=checks._page_gaps(page, part="linked_article"),
    )


# ------------------------------------------------------------------- picture checks


def _inspected(read: PostRead) -> bool:
    """Whether any of the post's own pictures or videos is being checked: a YouTube
    thumbnail is not the post's own (`_Picture.thumbnail`)."""
    return any(item.inspection is not None and not item.thumbnail for item in read.pictures) or any(
        item.video.inspection is not None for item in read.videos
    )


def _made_by_ai(read: PostRead) -> Any:
    """Whether the post's own picture or video checks found any of it AI-made: asked
    by the pipeline only when it could decide the case (`Orchestrator._fabricated`).
    Never a YouTube thumbnail's: it could turn an unreported video FALSE on a picture
    Factify never compared with the video."""

    async def asked() -> bool:
        for picture in read.pictures:
            if picture.inspection is None or picture.thumbnail:
                continue
            try:
                media, _ = await picture.inspection
            except Exception:
                logger.exception("a post's picture checks failed")
                continue
            if checks.ai_made(media, designed=picture.seen.designed):
                return True
        for item in read.videos:
            if item.video.inspection is None:
                continue
            try:
                report = await item.video.inspection
            except Exception:
                logger.exception("a post's video checks failed")
                continue
            shown = media_report_to_response(report, thumbnails=checks._THUMBNAILS)
            if checks.ai_made(shown):
                return True
        return False

    return asked


async def _with_media_checks(response: VerifyResponse, read: PostRead) -> VerifyResponse:
    """The answer with the post's picture and video checks beside it: the first in
    `media_report`, the rest in `media_reports`; what its pictures say in
    `image_reading`, and what is said in its video in `speech`."""
    reports: list[MediaReportResponse] = []
    advisories: list[AdvisoryResponse] = []
    for picture in read.pictures:
        if picture.inspection is None:
            continue
        try:
            media, said = await picture.inspection
        except Exception:
            logger.exception("a post's picture checks failed; the answer is sent without them")
            continue
        if picture.seen.designed:
            media, said = checks._as_designed(media, said)
        reports.append(media)
        advisories.extend(said)
    notes: list[SkippedCheckResponse] = []
    speech: SpeechResponse | None = None
    for item in read.videos:
        video = item.video
        notes.append(SkippedCheckResponse(check="video_frames", reason=video.note()))
        heard = video.heard.transcript
        if speech is None and heard is not None:
            speech = SpeechResponse(text=heard.text, language=heard.language, cut_off=heard.cut_off)
        if video.inspection is None:
            continue
        try:
            report = await video.inspection
        except Exception:
            logger.exception("a post's video checks failed; the answer is sent without them")
            continue
        reports.append(media_report_to_response(report, thumbnails=checks._THUMBNAILS))
        advisories.extend(advisory_to_response(advisory) for advisory in report.advisories)

    update: dict[str, Any] = {"skipped": (*response.skipped, *notes)}
    if reports:
        update["media_report"] = reports[0]
        update["media_reports"] = tuple(reports[1:])
        update["advisories"] = (*response.advisories, *advisories)
    first = next((p.read.shown for p in read.pictures if p.read.shown is not None), None)
    if first is not None:
        update["image_reading"] = checks._reading_response(first)
    if speech is not None:
        update["speech"] = speech
    return checks.with_earlier_copy(response.model_copy(update=update))
