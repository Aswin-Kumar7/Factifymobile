"""Request context (M04).

A request identifier is generated at intake, carried through every log line, returned
on every response and stored on the case. That chain is what makes the M04 gate
achievable: reconstructing a single verdict from logs alone.

Context is held in a `ContextVar` so it survives across await points without being
threaded through every function signature, and so concurrent requests cannot read
each other's identifiers.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from types import TracebackType
from typing import Self
from uuid import uuid4


@dataclass(slots=True)
class RequestContext:
    request_id: str
    case_id: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


_context: ContextVar[RequestContext | None] = ContextVar("factify_request_context", default=None)


def new_request_id() -> str:
    return uuid4().hex


def current() -> RequestContext | None:
    return _context.get()


def current_request_id() -> str | None:
    ctx = _context.get()
    return ctx.request_id if ctx else None


def bind_case(case_id: str) -> None:
    """Attach the case to the active context once it exists.

    The request identifier is known before the case; the case is created a few steps
    later. From that point every log line carries both.
    """
    ctx = _context.get()
    if ctx is not None:
        ctx.case_id = case_id


class request_context:
    """Establish a request context for the duration of a block.

    Lower-cased deliberately: this is used as a context manager, never as a type.
    """

    __slots__ = ("_context", "_token")

    def __init__(self, request_id: str | None = None, **extra: str) -> None:
        self._context = RequestContext(request_id=request_id or new_request_id(), extra=extra)
        self._token: Token[RequestContext | None] | None = None

    def __enter__(self) -> Self:
        self._token = _context.set(self._context)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._token is not None:
            _context.reset(self._token)

    @property
    def request_id(self) -> str:
        return self._context.request_id
