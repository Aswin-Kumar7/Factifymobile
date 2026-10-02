"""The one outbound HTTP client (M09).

Every request this service makes to the outside world goes through here. That is not
a style preference: the SSRF guard, the byte caps, the politeness layer and the
chain-of-custody record are only guarantees if there is no second path. A test
asserts no other module constructs an HTTP client.

Redirects are followed manually rather than by the client library, because the guard
has to run again on every hop. A destination that is public on the first request and
internal on the second is the standard bypass, and a library that follows redirects
for us would take that hop before we ever see it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.observability.logging import event
from app.observability.metrics import metrics
from app.security.patience import current_patience
from app.security.ssrf import BlockedDestination, resolve_and_validate

logger = logging.getLogger("factify.fetch")

# An honest user agent. Bulk ingestion identifies itself and respects robots; a
# single user-triggered fetch is the same request any link-preview bot makes and is
# not crawling, but we still say who we are.
USER_AGENT = "FactifyBot/1.0 (+https://factify.example/bot)"

# Content types worth parsing. Anything else is fetched no further than its headers —
# we are not going to stream a video through the article extractor.
DEFAULT_ACCEPTED_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "application/xml",
    "text/xml",
    "application/rss+xml",
    "application/atom+xml",
    "application/json",
    "application/ld+json",
    "application/pdf",
    "text/plain",
    "image/",
)


@dataclass(frozen=True, slots=True)
class FetchResult:
    """A completed fetch and its chain-of-custody record.

    This is what every downstream citation points back at: where we went, what came
    back, how big it was and exactly when. Without it an evidence object is an
    assertion about a page nobody can prove we read.
    """

    url: str
    final_url: str
    status_code: int
    content_type: str | None
    body: bytes
    byte_count: int
    fetched_at: datetime
    redirect_chain: tuple[str, ...] = ()
    elapsed_ms: float = 0.0
    truncated: bool = False

    @property
    def text(self) -> str:
        """Decoded body, replacing anything undecodable rather than raising."""
        return self.body.decode("utf-8", errors="replace")


@dataclass(frozen=True, slots=True)
class FetchFailure:
    """A fetch that did not complete, as data rather than an exception.

    A blocked or failed fetch is an ordinary outcome of verifying attacker-supplied
    URLs. It produces `INSUFFICIENT` upstream and the claim abstains — it must never
    surface to a user as a verdict, and it must never be silently swallowed either.
    """

    url: str
    reason: str
    kind: str


def _www_variant(url: str) -> str | None:
    """The `www.` form of a bare apex, or `None` if that is not what this URL is.

    A DNS convention, not a guessing loop: one alternative, upward only, and never for
    a name that already carries a subdomain.
    """
    from urllib.parse import urlsplit, urlunsplit

    from app.domain.publishers import registrable_domain

    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        return None
    # An apex is a host equal to its own registrable domain. Counting dots does not
    # work: `isro.gov.in` is an apex with two of them, because `gov.in` is a
    # multi-label suffix, and that is precisely the case this exists for.
    if not host or host.startswith("www.") or registrable_domain(host) != host:
        return None
    port = f":{parts.port}" if parts.port else ""
    return urlunsplit((parts.scheme, f"www.{host}{port}", parts.path, parts.query, parts.fragment))


def _host_of(url: str) -> str:
    from urllib.parse import urlsplit

    try:
        return (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def _host_allowed(host: str, allowed_hosts: tuple[str, ...]) -> bool:
    """Whether a host is one of these, or a subdomain of one.

    Matched on whole labels: `.fbcdn.net` admits `scontent.xx.fbcdn.net` and never
    `evilfbcdn.net`.
    """
    if not host:
        return False
    for allowed in allowed_hosts:
        suffix = allowed.lower().strip(".")
        if suffix and (host == suffix or host.endswith(f".{suffix}")):
            return True
    return False


# Provider answers that mean "try again in a moment". 432, Tavily's plan limit, is
# not one of them: waiting does not refill a plan.
_RETRYABLE = frozenset({429, 502, 503, 504})
_PROVIDER_RETRIES = 2
_BACKOFF_SECONDS = (1.0, 3.0)
_MAX_RETRY_AFTER_SECONDS = 10.0


def _retry_delay(response: httpx.Response, attempt: int, *, cap: float) -> float:
    """The provider's Retry-After when it gives one (capped), else a short backoff."""
    header = response.headers.get("retry-after", "")
    try:
        return min(max(float(header), 0.0), cap)
    except ValueError:
        return _BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)]


def _provider_error(body: bytes) -> str:
    """The provider's own error code and message, briefly, or "".

    "provider returned 400" said nothing of why: a model provider refusing a picture
    of a news graphic once, and accepting the same request four times after, left no
    trace of what it had objected to (2026-10-01). The code and the first words of
    the message are kept; nothing from the request is echoed.
    """
    try:
        error = json.loads(body.decode("utf-8", errors="replace")).get("error")
    except (ValueError, AttributeError):
        return ""
    if isinstance(error, dict):
        code = str(error.get("code") or error.get("status") or "").strip()
        message = " ".join(str(error.get("message") or "").split())[:120]
        said = ": ".join(part for part in (code, message) if part)
        return f" ({said})" if said else ""
    if isinstance(error, str):
        return f" ({' '.join(error.split())[:120]})"
    return ""


class SecureFetcher:
    """Guarded HTTP client. Construct one per process and share it."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        max_redirects: int = 5,
        max_bytes: int = 10 * 1024 * 1024,
        accepted_types: tuple[str, ...] = DEFAULT_ACCEPTED_TYPES,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._max_redirects = max_redirects
        self._max_bytes = max_bytes
        self._accepted_types = accepted_types
        self._client = client or httpx.AsyncClient(
            # Redirects are ours to follow, one validated hop at a time.
            follow_redirects=False,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": USER_AGENT},
            # No cookie jar: nothing this service fetches is behind a session, and a
            # jar would carry state between unrelated hosts.
            cookies=None,
            trust_env=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(self, url: str, *, provider: str = "web") -> FetchResult | FetchFailure:
        """Fetch a public URL, validating every hop.

        Returns a failure value rather than raising for the expected cases — blocked
        destination, timeout, oversized body, uninteresting content type — because
        those are outcomes to record, not errors to propagate.
        """
        started = time.perf_counter()
        chain: list[str] = []
        current = url

        for hop in range(self._max_redirects + 1):
            try:
                resolve_and_validate(current)
            except BlockedDestination as blocked:
                # A bare apex that does not resolve is often a site that publishes only
                # `www`. `isro.gov.in` is one: no address at the apex, `www.isro.gov.in`
                # answers over IPv6 — so we were reporting India's space agency as
                # unreachable while checking claims about Indian space missions.
                #
                # The retry rewrites the URL rather than resolving one host and
                # connecting to another, so the `www` form goes through every check
                # from the top and the citation records the address that actually
                # served. Tried once, only for a name with no subdomain of its own, and
                # only when DNS was what failed — a blocked address is a decision, not
                # a typo, and must never be retried around.
                retry = _www_variant(current) if "does not resolve" in blocked.reason else None
                if retry is None:
                    return self._failure(
                        url, blocked.reason, kind="blocked", provider=provider, hop=hop
                    )
                chain.append(current)
                current = retry
                try:
                    resolve_and_validate(current)
                except BlockedDestination as still_blocked:
                    return self._failure(
                        url, still_blocked.reason, kind="blocked", provider=provider, hop=hop
                    )

            try:
                response = await self._client.get(
                    current, headers={"Accept-Encoding": "gzip, deflate"}
                )
            except httpx.TimeoutException:
                return self._failure(url, "request timed out", kind="timeout", provider=provider)
            except httpx.HTTPError as exc:
                return self._failure(
                    url,
                    f"transport error: {type(exc).__name__}",
                    kind="transport",
                    provider=provider,
                )

            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    await response.aclose()
                    return self._failure(
                        url, "redirect without a location", kind="transport", provider=provider
                    )
                chain.append(current)
                current = str(httpx.URL(current).join(location))
                await response.aclose()
                continue

            return await self._complete(url, current, response, chain, started, provider=provider)

        return self._failure(
            url,
            f"more than {self._max_redirects} redirects",
            kind="redirect_limit",
            provider=provider,
        )

    async def download(
        self,
        url: str,
        *,
        provider: str,
        max_bytes: int,
        accepted_types: tuple[str, ...],
        allowed_hosts: tuple[str, ...],
        total_seconds: float = 120.0,
    ) -> FetchResult | FetchFailure:
        """Download a post's picture or video from the platform's own media hosts.

        Not `fetch`, for three reasons. `fetch` reads the whole body before its cap
        applies, which for a video means holding hundreds of megabytes to keep 25;
        this reads as it streams and stops one byte past `max_bytes`. `fetch` keeps a
        truncated body as a result, which suits an article (its opening is useful)
        and not a video (half an mp4 does not decode, and a picture cut short is not
        the picture): this returns `too_large` instead, never a truncated success.
        And the address came out of a platform's answer, so it is held to that
        platform's media hosts (`allowed_hosts`, each matching itself and its
        subdomains) on every hop, as well as to the SSRF guard: a post cannot send
        the downloader to an arbitrary host by naming it as its picture.

        `total_seconds` bounds the whole download. The client's timeout is per read,
        so a host dribbling a byte every few seconds would otherwise hold the check
        for as long as it liked.
        """
        started = time.perf_counter()
        chain: list[str] = []
        current = url
        try:
            async with asyncio.timeout(total_seconds):
                for hop in range(self._max_redirects + 1):
                    host = _host_of(current)
                    if not _host_allowed(host, allowed_hosts):
                        return self._failure(
                            url,
                            f"{host or 'the address'} is not one of this platform's media hosts",
                            kind="blocked",
                            provider=provider,
                            hop=hop,
                        )
                    try:
                        resolve_and_validate(current)
                    except BlockedDestination as blocked:
                        return self._failure(
                            url, blocked.reason, kind="blocked", provider=provider, hop=hop
                        )
                    # Media is compressed already; asking for it as it is saves the
                    # CDN recompressing it and keeps the byte count the file's own.
                    async with self._client.stream(
                        "GET", current, headers={"Accept-Encoding": "identity"}
                    ) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location:
                                return self._failure(
                                    url,
                                    "redirect without a location",
                                    kind="transport",
                                    provider=provider,
                                )
                            chain.append(current)
                            current = str(httpx.URL(current).join(location))
                            continue
                        return await self._streamed(
                            url,
                            current,
                            response,
                            chain,
                            started,
                            provider=provider,
                            max_bytes=max_bytes,
                            accepted_types=accepted_types,
                        )
        except TimeoutError:
            return self._failure(
                url,
                f"download took longer than {total_seconds:.0f}s",
                kind="timeout",
                provider=provider,
            )
        except httpx.TimeoutException:
            return self._failure(url, "request timed out", kind="timeout", provider=provider)
        except httpx.HTTPError as exc:
            return self._failure(
                url, f"transport error: {type(exc).__name__}", kind="transport", provider=provider
            )
        return self._failure(
            url,
            f"more than {self._max_redirects} redirects",
            kind="redirect_limit",
            provider=provider,
        )

    async def _streamed(
        self,
        original_url: str,
        final_url: str,
        response: httpx.Response,
        chain: list[str],
        started: float,
        *,
        provider: str,
        max_bytes: int,
        accepted_types: tuple[str, ...],
    ) -> FetchResult | FetchFailure:
        """Read a download's body as it arrives, refusing it whole past the cap."""
        if response.status_code >= 400:
            return self._failure(
                original_url,
                f"the media host returned {response.status_code}",
                kind="status",
                provider=provider,
            )
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        # Unlike a page, a download must say what it is: the bytes are about to be
        # handed to a picture or video decoder, and a CDN always names its type.
        if not content_type or not any(content_type.startswith(t) for t in accepted_types):
            return self._failure(
                original_url,
                f"content type {content_type or 'none'!r} is not a picture or video",
                kind="content_type",
                provider=provider,
            )
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            return self._failure(
                original_url,
                f"declared size {declared} exceeds the {max_bytes} byte cap",
                kind="too_large",
                provider=provider,
            )
        received = bytearray()
        # Decoded bytes are what is counted, so a compressed body cannot expand past
        # the cap in memory either.
        async for chunk in response.aiter_bytes():
            received.extend(chunk)
            if len(received) > max_bytes:
                return self._failure(
                    original_url,
                    f"more than the {max_bytes} byte cap",
                    kind="too_large",
                    provider=provider,
                )
        body = bytes(received)
        elapsed_ms = (time.perf_counter() - started) * 1000
        metrics.record_success(provider, elapsed_ms)
        event(
            logger,
            "download completed",
            module="security.fetcher",
            outcome="ok",
            provider=provider,
            latency_ms=elapsed_ms,
            status_code=response.status_code,
            redirects=len(chain),
            byte_count=len(body),
        )
        return FetchResult(
            url=original_url,
            final_url=final_url,
            status_code=response.status_code,
            content_type=content_type,
            body=body,
            byte_count=len(body),
            fetched_at=datetime.now(UTC),
            redirect_chain=tuple(chain),
            elapsed_ms=elapsed_ms,
        )

    async def get_json(
        self, url: str, *, provider: str, headers: dict[str, str] | None = None
    ) -> FetchResult | FetchFailure:
        """GET a configured provider endpoint with credentials, and keep its status.

        For calls whose answer is the status as much as the body — "is this sign-in
        token valid?" answers 401 when it is not, which is a result, not a failure.
        So any HTTP response comes back as a `FetchResult` carrying its status code;
        only a blocked destination, a timeout or a transport error is a failure. No
        redirects are followed: a credentialled request goes where it was sent.
        """
        started = time.perf_counter()
        try:
            resolve_and_validate(url)
        except BlockedDestination as blocked:
            return self._failure(url, blocked.reason, kind="blocked", provider=provider)
        try:
            response = await self._client.get(url, headers=headers or {})
        except httpx.TimeoutException:
            return self._failure(url, "request timed out", kind="timeout", provider=provider)
        except httpx.HTTPError as exc:
            return self._failure(
                url, f"transport error: {type(exc).__name__}", kind="transport", provider=provider
            )
        body = await response.aread()
        await response.aclose()
        return FetchResult(
            url=url,
            final_url=url,
            status_code=response.status_code,
            content_type=response.headers.get("content-type", "").split(";")[0] or None,
            body=body,
            byte_count=len(body),
            fetched_at=datetime.now(UTC),
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    async def post_form(
        self, url: str, form: dict[str, str], *, provider: str
    ) -> FetchResult | FetchFailure:
        """POST form fields to a configured endpoint, and keep its status.

        OAuth's token exchange is a form post, and its errors come back as 400s with
        a reason in the body, so like `get_json` any HTTP response is a result. SSRF-
        checked like every other call; no redirects are followed.
        """
        started = time.perf_counter()
        try:
            resolve_and_validate(url)
        except BlockedDestination as blocked:
            return self._failure(url, blocked.reason, kind="blocked", provider=provider)
        try:
            response = await self._client.post(url, data=form)
        except httpx.TimeoutException:
            return self._failure(url, "request timed out", kind="timeout", provider=provider)
        except httpx.HTTPError as exc:
            return self._failure(
                url, f"transport error: {type(exc).__name__}", kind="transport", provider=provider
            )
        body = await response.aread()
        await response.aclose()
        return FetchResult(
            url=url,
            final_url=url,
            status_code=response.status_code,
            content_type=response.headers.get("content-type", "").split(";")[0] or None,
            body=body,
            byte_count=len(body),
            fetched_at=datetime.now(UTC),
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    async def post_multipart(
        self,
        url: str,
        fields: dict[str, str],
        files: dict[str, tuple[str, bytes, str]],
        *,
        provider: str,
    ) -> FetchResult | FetchFailure:
        """POST a file to a configured provider endpoint, as a multipart form.

        For providers that take an upload rather than JSON (the AI-image detector).
        SSRF-checked like every other call; an HTTP error is a failure, as it is for
        `post_json`, because nothing in an error body is a result.
        """
        started = time.perf_counter()
        try:
            resolve_and_validate(url)
        except BlockedDestination as blocked:
            return self._failure(url, blocked.reason, kind="blocked", provider=provider)
        try:
            response = await self._client.post(url, data=fields, files=files)
        except httpx.TimeoutException:
            return self._failure(url, "request timed out", kind="timeout", provider=provider)
        except httpx.HTTPError as exc:
            return self._failure(
                url, f"transport error: {type(exc).__name__}", kind="transport", provider=provider
            )
        body = await response.aread()
        await response.aclose()
        if response.status_code >= 400:
            return self._failure(
                url,
                f"provider returned {response.status_code}",
                kind="provider_error",
                provider=provider,
            )
        return FetchResult(
            url=url,
            final_url=url,
            status_code=response.status_code,
            content_type=response.headers.get("content-type", "").split(";")[0] or None,
            body=body,
            byte_count=len(body),
            fetched_at=datetime.now(UTC),
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    async def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        provider: str,
        headers: dict[str, str] | None = None,
    ) -> FetchResult | FetchFailure:
        """POST to a configured provider endpoint.

        Deliberately the same client, and deliberately still SSRF-validated. A
        provider endpoint comes from configuration rather than from an attacker, but
        it resolves publicly like any other host, so the guard costs nothing and
        catches the case where a misconfigured or hijacked endpoint points somewhere
        internal. One HTTP client remains one HTTP client.
        """
        started = time.perf_counter()

        try:
            resolve_and_validate(url)
        except BlockedDestination as blocked:
            return self._failure(url, blocked.reason, kind="blocked", provider=provider)

        # A provider saying "too many requests" or "busy" is asking for a moment, not
        # refusing. That answer used to drop the call: a source read on a busy minute
        # simply vanished from the check. A short wait and another try, honouring the
        # provider's own Retry-After, recovers it. Anything else fails at once.
        # A check in the background waits longer and more often (app/security/patience).
        patience = current_patience.get()
        retries = max(_PROVIDER_RETRIES, patience.retries)
        cap = max(_MAX_RETRY_AFTER_SECONDS, patience.retry_after_cap)
        for attempt in range(retries + 1):
            try:
                response = await self._client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json", **(headers or {})},
                )
            except httpx.TimeoutException:
                return self._failure(url, "request timed out", kind="timeout", provider=provider)
            except httpx.HTTPError as exc:
                return self._failure(
                    url,
                    f"transport error: {type(exc).__name__}",
                    kind="transport",
                    provider=provider,
                )

            body = await response.aread()
            await response.aclose()
            if response.status_code not in _RETRYABLE or attempt == retries:
                break
            await asyncio.sleep(_retry_delay(response, attempt, cap=cap))

        elapsed_ms = (time.perf_counter() - started) * 1000

        if response.status_code >= 400:
            return self._failure(
                url,
                f"provider returned {response.status_code}{_provider_error(body)}",
                kind="provider_error",
                provider=provider,
            )

        return FetchResult(
            url=url,
            final_url=url,
            status_code=response.status_code,
            content_type=response.headers.get("content-type", "").split(";")[0] or None,
            body=body,
            byte_count=len(body),
            fetched_at=datetime.now(UTC),
            elapsed_ms=elapsed_ms,
        )

    async def _complete(
        self,
        original_url: str,
        final_url: str,
        response: httpx.Response,
        chain: list[str],
        started: float,
        *,
        provider: str,
    ) -> FetchResult | FetchFailure:
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()

        if content_type and not any(content_type.startswith(t) for t in self._accepted_types):
            await response.aclose()
            return self._failure(
                original_url,
                f"content type {content_type!r} is not parsed",
                kind="content_type",
                provider=provider,
            )

        # A declared length over the cap is refused before a byte is read. The
        # streaming cap below still applies, because the header is attacker-supplied
        # and may be absent or a lie.
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self._max_bytes:
            await response.aclose()
            return self._failure(
                original_url,
                f"declared size {declared} exceeds the {self._max_bytes} byte cap",
                kind="too_large",
                provider=provider,
            )

        body = await response.aread()
        await response.aclose()

        truncated = len(body) > self._max_bytes
        if truncated:
            body = body[: self._max_bytes]

        elapsed_ms = (time.perf_counter() - started) * 1000
        metrics.record_success(provider, elapsed_ms)
        event(
            logger,
            "fetch completed",
            module="security.fetcher",
            outcome="ok",
            provider=provider,
            latency_ms=elapsed_ms,
            status_code=response.status_code,
            redirects=len(chain),
            byte_count=len(body),
            truncated=truncated,
        )

        return FetchResult(
            url=original_url,
            final_url=final_url,
            status_code=response.status_code,
            content_type=content_type or None,
            body=body,
            byte_count=len(body),
            fetched_at=datetime.now(UTC),
            redirect_chain=tuple(chain),
            elapsed_ms=elapsed_ms,
            truncated=truncated,
        )

    def _failure(
        self, url: str, reason: str, *, kind: str, provider: str, hop: int = 0
    ) -> FetchFailure:
        metrics.record_failure(provider)
        event(
            logger,
            "fetch failed",
            module="security.fetcher",
            outcome="blocked" if kind == "blocked" else "error",
            provider=provider,
            failure_reason=reason,
            level=logging.WARNING,
            kind=kind,
            hop=hop,
        )
        return FetchFailure(url=url, reason=reason, kind=kind)
