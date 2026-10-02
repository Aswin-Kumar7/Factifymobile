"""Downloading a post's picture or video: whole, from the platform's own hosts, or not at all.

`SecureFetcher.download` exists because `fetch` suits an article and not a video: it
reads the whole body before its cap applies, and keeps a truncated body as a result.
A video cut short does not decode, and an address taken from a platform's answer must
not send the downloader anywhere but that platform's media hosts. Runs against an
in-memory transport; nothing here touches the network.
"""

from __future__ import annotations

import httpx
import pytest

from app.security.fetcher import FetchFailure, FetchResult, SecureFetcher

pytestmark = pytest.mark.unit

PUBLIC = "93.184.216.34"
INTERNAL = "169.254.169.254"
HOSTS = ("pbs.twimg.com", "video.twimg.com", "cdninstagram.com")
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x01" * 1000


@pytest.fixture(autouse=True)
def _dns(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.security.ssrf as ssrf

    table = {"internal.cdninstagram.com": INTERNAL}
    monkeypatch.setattr(ssrf, "_default_resolver", lambda host, port: [table.get(host, PUBLIC)])


def _fetcher(handler: object) -> SecureFetcher:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return SecureFetcher(client=httpx.AsyncClient(transport=transport, follow_redirects=False))


async def _download(
    handler: object, url: str = "https://video.twimg.com/v/a.mp4", max_bytes: int = 10_000
) -> FetchResult | FetchFailure:
    return await _fetcher(handler).download(
        url,
        provider="social.media",
        max_bytes=max_bytes,
        accepted_types=("video/", "image/"),
        allowed_hosts=HOSTS,
    )


def _ok(body: bytes = MP4, content_type: str = "video/mp4", **headers: str) -> httpx.Response:
    return httpx.Response(200, content=body, headers={"content-type": content_type, **headers})


class TestAWholeFile:
    async def test_it_comes_back_whole_with_its_type_and_custody(self) -> None:
        result = await _download(lambda request: _ok())

        assert isinstance(result, FetchResult)
        assert result.body == MP4 and result.byte_count == len(MP4)
        assert result.content_type == "video/mp4"
        assert not result.truncated

    async def test_it_is_asked_for_as_it_is(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers.get("accept-encoding", ""))
            return _ok()

        await _download(handler)

        assert seen == ["identity"]


class TestNeverTruncated:
    async def test_one_byte_past_the_cap_is_too_large_and_no_body(self) -> None:
        result = await _download(lambda request: _ok(b"x" * 10_001))

        assert isinstance(result, FetchFailure)
        assert result.kind == "too_large"

    async def test_exactly_the_cap_is_fine(self) -> None:
        result = await _download(lambda request: _ok(b"x" * 10_000))

        assert isinstance(result, FetchResult) and result.byte_count == 10_000

    async def test_a_declared_size_over_the_cap_is_refused_before_reading(self) -> None:
        result = await _download(lambda request: _ok(b"x", **{"content-length": "999999"}))

        assert isinstance(result, FetchFailure) and result.kind == "too_large"


class TestOnlyThePlatformsHosts:
    async def test_a_host_off_the_list_is_never_asked(self) -> None:
        asked: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            asked.append(str(request.url))
            return _ok()

        result = await _download(handler, url="https://evil.example/a.mp4")

        assert isinstance(result, FetchFailure) and result.kind == "blocked"
        assert asked == []

    async def test_a_lookalike_host_is_not_a_subdomain(self) -> None:
        result = await _download(lambda request: _ok(), url="https://evilcdninstagram.com/a.jpg")

        assert isinstance(result, FetchFailure) and result.kind == "blocked"

    async def test_a_subdomain_of_a_listed_host_is_allowed(self) -> None:
        result = await _download(
            lambda request: _ok(b"\xff\xd8", "image/jpeg"),
            url="https://scontent-sin6-2.cdninstagram.com/v/a.jpg",
        )

        assert isinstance(result, FetchResult)

    async def test_a_redirect_off_the_list_is_refused_at_that_hop(self) -> None:
        asked: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            asked.append(request.url.host)
            if request.url.host == "video.twimg.com":
                return httpx.Response(302, headers={"location": "https://evil.example/a.mp4"})
            return _ok()

        result = await _download(handler)

        assert isinstance(result, FetchFailure) and result.kind == "blocked"
        assert asked == ["video.twimg.com"]

    async def test_a_redirect_to_an_internal_address_is_refused(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "video.twimg.com":
                return httpx.Response(
                    302, headers={"location": "https://internal.cdninstagram.com/a.mp4"}
                )
            return _ok()

        result = await _download(handler)

        assert isinstance(result, FetchFailure) and result.kind == "blocked"

    async def test_a_redirect_within_the_list_is_followed_and_recorded(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v/a.mp4":
                return httpx.Response(302, headers={"location": "/v/b.mp4"})
            return _ok()

        result = await _download(handler)

        assert isinstance(result, FetchResult)
        assert result.final_url == "https://video.twimg.com/v/b.mp4"
        assert result.redirect_chain == ("https://video.twimg.com/v/a.mp4",)


class TestWhatIsNotAMediaFile:
    async def test_a_page_where_a_video_was_expected_is_refused(self) -> None:
        result = await _download(lambda request: _ok(b"<html>login</html>", "text/html"))

        assert isinstance(result, FetchFailure) and result.kind == "content_type"

    async def test_no_type_at_all_is_refused(self) -> None:
        result = await _download(lambda request: httpx.Response(200, content=MP4))

        assert isinstance(result, FetchFailure) and result.kind == "content_type"

    async def test_an_error_status_is_a_failure(self) -> None:
        result = await _download(lambda request: httpx.Response(403, text="expired"))

        assert isinstance(result, FetchFailure) and result.kind == "status"

    async def test_a_dropped_connection_is_a_transport_failure(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("reset", request=request)

        result = await _download(handler)

        assert isinstance(result, FetchFailure) and result.kind == "transport"

    async def test_a_malformed_redirect_is_a_failure_never_an_exception(self) -> None:
        # A Location no URL parser accepts ("Invalid port") is a failed download, as
        # data: httpx.InvalidURL is not an httpx.HTTPError, and nothing may escape.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "https://video.twimg.com:abc/x"})

        result = await _download(handler)

        assert isinstance(result, FetchFailure) and result.kind == "transport"


# ------------------------------------------------------------------- following a short link


def _not_short(url: str) -> bool:
    return not url.startswith("https://t.co/")


class TestLocatingWhereALinkLeads:
    """`locate` follows redirects, checks every hop, and reads no body."""

    async def test_it_stops_at_the_first_address_it_is_told_to_and_never_asks_it(self) -> None:
        asked: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            asked.append(str(request.url))
            return httpx.Response(301, headers={"location": "https://www.ndtv.com/story-1"})

        chain = await _fetcher(handler).locate(
            "https://t.co/abc", provider="social.x", stop=_not_short
        )

        assert chain == ("https://t.co/abc", "https://www.ndtv.com/story-1")
        assert asked == ["https://t.co/abc"]

    async def test_without_a_stop_it_ends_where_something_other_than_a_redirect_answers(
        self,
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "t.co":
                return httpx.Response(301, headers={"location": "https://bit.ly/next"})
            return httpx.Response(200, text="<html>" + "x" * 10_000)

        chain = await _fetcher(handler).locate("https://t.co/abc", provider="social.x")

        assert chain == ("https://t.co/abc", "https://bit.ly/next")

    async def test_a_link_that_does_not_lead_anywhere_is_a_failure(self) -> None:
        chain = await _fetcher(lambda request: httpx.Response(404)).locate(
            "https://t.co/gone", provider="social.x", stop=_not_short
        )

        assert isinstance(chain, FetchFailure) and chain.kind == "status"

    async def test_a_hop_to_an_internal_address_is_refused(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(301, headers={"location": "https://internal.cdninstagram.com/"})

        chain = await _fetcher(handler).locate("https://t.co/abc", provider="social.x")

        assert isinstance(chain, FetchFailure) and chain.kind == "blocked"

    async def test_a_malformed_redirect_is_a_failure(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(301, headers={"location": "http://[::1"})

        chain = await _fetcher(handler).locate("https://t.co/abc", provider="social.x")

        assert isinstance(chain, FetchFailure) and chain.kind == "transport"
