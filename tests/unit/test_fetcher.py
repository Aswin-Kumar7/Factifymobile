"""M09 — the fetcher, including the mid-redirect pivot that is the gate.

Runs against an in-memory transport, so no test here touches the network.
"""

from __future__ import annotations

import httpx
import pytest

from app.security.fetcher import FetchFailure, FetchResult, SecureFetcher

pytestmark = pytest.mark.unit

PUBLIC = "93.184.216.34"
INTERNAL = "169.254.169.254"


def _resolver(mapping: dict[str, str]) -> None:
    """Patch resolution so hostnames map to chosen addresses, with no DNS."""
    import app.security.ssrf as ssrf

    def resolve(host: str, port: int) -> list[str]:
        return [mapping.get(host, PUBLIC)]

    ssrf._default_resolver = resolve  # type: ignore[assignment]


@pytest.fixture(autouse=True)
def _restore_resolver() -> object:
    import app.security.ssrf as ssrf

    original = ssrf._default_resolver
    yield
    ssrf._default_resolver = original  # type: ignore[assignment]


def _fetcher(handler: object, **kwargs: object) -> SecureFetcher:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    client = httpx.AsyncClient(transport=transport, follow_redirects=False)
    return SecureFetcher(client=client, **kwargs)  # type: ignore[arg-type]


class TestSuccessfulFetch:
    async def test_records_the_chain_of_custody(self) -> None:
        """Every citation points back at this record."""
        _resolver({"example.org": PUBLIC})

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, headers={"content-type": "text/html; charset=utf-8"}, text="<h1>hi</h1>"
            )

        result = await _fetcher(handler).fetch("https://example.org/story")

        assert isinstance(result, FetchResult)
        assert result.status_code == 200
        assert result.final_url == "https://example.org/story"
        assert result.content_type == "text/html"
        assert result.byte_count == len(b"<h1>hi</h1>")
        assert result.fetched_at is not None
        assert "hi" in result.text


class TestRedirectValidation:
    async def test_a_redirect_pivoting_to_an_internal_address_is_blocked(self) -> None:
        """**The gate.** Public on hop one, internal on hop two.

        A client library that followed redirects for us would take this hop before we
        ever saw it, which is why redirects are followed manually.
        """
        _resolver({"public.example": PUBLIC, "metadata.example": INTERNAL})

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "public.example":
                return httpx.Response(
                    302, headers={"location": "https://metadata.example/latest/meta-data/"}
                )
            return httpx.Response(200, text="SECRET CREDENTIALS")

        result = await _fetcher(handler).fetch("https://public.example/start")

        assert isinstance(result, FetchFailure)
        assert result.kind == "blocked"
        assert "link-local" in result.reason

    async def test_a_redirect_to_a_bare_metadata_ip_is_blocked(self) -> None:
        _resolver({"public.example": PUBLIC})

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "public.example":
                return httpx.Response(
                    302, headers={"location": "http://169.254.169.254/latest/meta-data/"}
                )
            return httpx.Response(200, text="leaked")

        result = await _fetcher(handler).fetch("https://public.example/start")

        assert isinstance(result, FetchFailure)
        assert result.kind == "blocked"

    async def test_a_redirect_to_a_scheme_change_is_blocked(self) -> None:
        _resolver({"public.example": PUBLIC})

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "file:///etc/passwd"})

        result = await _fetcher(handler).fetch("https://public.example/start")

        assert isinstance(result, FetchFailure)
        assert result.kind == "blocked"

    async def test_legitimate_redirects_are_followed_and_recorded(self) -> None:
        _resolver({"example.org": PUBLIC, "www.example.org": PUBLIC})

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "example.org":
                return httpx.Response(301, headers={"location": "https://www.example.org/story"})
            return httpx.Response(200, headers={"content-type": "text/html"}, text="ok")

        result = await _fetcher(handler).fetch("https://example.org/story")

        assert isinstance(result, FetchResult)
        assert result.final_url == "https://www.example.org/story"
        assert result.redirect_chain == ("https://example.org/story",)

    async def test_a_redirect_loop_terminates(self) -> None:
        _resolver({"loop.example": PUBLIC})

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "https://loop.example/next"})

        result = await _fetcher(handler, max_redirects=3).fetch("https://loop.example/start")

        assert isinstance(result, FetchFailure)
        assert result.kind == "redirect_limit"


class TestResourceCaps:
    async def test_a_declared_oversize_body_is_refused_before_reading(self) -> None:
        _resolver({"example.org": PUBLIC})

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/html", "content-length": "999999999"},
                text="x",
            )

        result = await _fetcher(handler, max_bytes=1024).fetch("https://example.org/big")

        assert isinstance(result, FetchFailure)
        assert result.kind == "too_large"

    async def test_an_undeclared_oversize_body_is_truncated(self) -> None:
        """The content-length header is attacker-supplied and may simply be absent.

        A chunked response declares no length, so only the streaming cap stands
        between us and an unbounded body.
        """
        _resolver({"example.org": PUBLIC})

        async def chunks() -> object:
            yield b"x" * 2500
            yield b"x" * 2500

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "text/html"}, content=chunks())

        result = await _fetcher(handler, max_bytes=1000).fetch("https://example.org/big")

        assert isinstance(result, FetchResult)
        assert result.truncated
        assert result.byte_count == 1000

    async def test_uninteresting_content_types_are_not_parsed(self) -> None:
        _resolver({"example.org": PUBLIC})

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "video/mp4"}, content=b"\x00")

        result = await _fetcher(handler).fetch("https://example.org/movie")

        assert isinstance(result, FetchFailure)
        assert result.kind == "content_type"

    async def test_a_timeout_is_an_outcome_not_an_exception(self) -> None:
        _resolver({"slow.example": PUBLIC})

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("too slow", request=request)

        result = await _fetcher(handler).fetch("https://slow.example/a")

        assert isinstance(result, FetchFailure)
        assert result.kind == "timeout"


class TestRequestHygiene:
    async def test_no_cookies_are_sent(self) -> None:
        _resolver({"example.org": PUBLIC})
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(request.headers)
            return httpx.Response(200, headers={"content-type": "text/html"}, text="ok")

        await _fetcher(handler).fetch("https://example.org/a")

        assert "cookie" not in {key.lower() for key in seen}

    async def test_an_honest_user_agent_is_sent(self) -> None:
        _resolver({"example.org": PUBLIC})
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(request.headers)
            return httpx.Response(200, headers={"content-type": "text/html"}, text="ok")

        fetcher = SecureFetcher(
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                follow_redirects=False,
                headers={"User-Agent": "FactifyBot/1.0 (+https://factify.example/bot)"},
            )
        )
        await fetcher.fetch("https://example.org/a")

        assert "FactifyBot" in seen["user-agent"]


class TestSingleClientDiscipline:
    def test_no_other_module_constructs_an_http_client(self) -> None:
        """The guard is only a guarantee if there is no second path around it."""
        import pathlib

        app_root = pathlib.Path(__file__).resolve().parents[2] / "app"
        offenders: list[str] = []

        for path in app_root.rglob("*.py"):
            if path.name == "fetcher.py":
                continue
            source = path.read_text(encoding="utf-8")
            for marker in ("httpx.AsyncClient(", "httpx.Client(", "urllib.request", "requests."):
                if marker in source:
                    offenders.append(f"{path.name}: {marker}")

        assert not offenders, f"HTTP clients outside the secure fetcher: {offenders}"


class TestAProviderAskingForAMomentGetsOne:
    """A 429 or 503 from a model or search provider used to drop the call outright."""

    @pytest.mark.anyio
    async def test_a_busy_provider_is_retried_and_the_call_recovers(
        self, _restore_resolver: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import app.security.fetcher as fetcher_module

        _resolver({"api.example.org": PUBLIC})
        waits: list[float] = []

        async def _sleep(seconds: float) -> None:
            waits.append(seconds)

        monkeypatch.setattr(fetcher_module.asyncio, "sleep", _sleep)
        answers = iter(
            [
                httpx.Response(429, headers={"retry-after": "2"}),
                httpx.Response(503),
                httpx.Response(200, json={"ok": True}),
            ]
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return next(answers)

        result = await _fetcher(handler).post_json(
            "https://api.example.org/v1/chat", {"q": 1}, provider="llm"
        )

        assert isinstance(result, FetchResult)
        assert waits == [2.0, 3.0]  # the provider's Retry-After, then the backoff

    @pytest.mark.anyio
    async def test_a_plan_limit_is_not_retried(
        self, _restore_resolver: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Tavily's 432 means the plan is spent; waiting does not refill it."""
        import app.security.fetcher as fetcher_module

        _resolver({"api.example.org": PUBLIC})
        calls: list[int] = []

        async def _sleep(seconds: float) -> None:
            raise AssertionError("a plan limit must not be waited on")

        monkeypatch.setattr(fetcher_module.asyncio, "sleep", _sleep)

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(432)

        result = await _fetcher(handler).post_json(
            "https://api.example.org/search", {"q": 1}, provider="web_search"
        )

        assert isinstance(result, FetchFailure)
        assert calls == [1]
