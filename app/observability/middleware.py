"""Request-context middleware (M04).

Establishes the request identifier before anything else runs and returns it on every
response, including error responses — support correlation matters most when
something went wrong.

An inbound `X-Request-ID` is honoured so a caller can correlate across a retry, but
it is length-capped and sanitised: it is attacker-controlled text that ends up in
every log line for that request.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.context import new_request_id, request_context
from app.observability.logging import event

REQUEST_ID_HEADER = "X-Request-ID"
_MAX_INBOUND_ID_CHARS = 64

logger = logging.getLogger("facify.request")


def _sanitise(raw: str | None) -> str:
    """Accept a caller-supplied id only if it is short and alphanumeric."""
    if not raw:
        return new_request_id()
    candidate = raw.strip()[:_MAX_INBOUND_ID_CHARS]
    if candidate and all(ch.isalnum() or ch in "-_" for ch in candidate):
        return candidate
    return new_request_id()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = _sanitise(request.headers.get(REQUEST_ID_HEADER))
        started = time.perf_counter()

        with request_context(request_id) as ctx:
            try:
                response = await call_next(request)
            except Exception:
                event(
                    logger,
                    "request failed",
                    module="api",
                    outcome="error",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    failure_reason="unhandled exception",
                    level=logging.ERROR,
                    path=request.url.path,
                    method=request.method,
                )
                raise

            latency_ms = (time.perf_counter() - started) * 1000
            response.headers[REQUEST_ID_HEADER] = ctx.request_id

            event(
                logger,
                "request completed",
                module="api",
                outcome="ok" if response.status_code < 500 else "error",
                latency_ms=latency_ms,
                path=request.url.path,
                method=request.method,
                status_code=response.status_code,
            )
            return response
