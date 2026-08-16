"""Observability and audit (M04).

Every verdict must be reconstructable from logs alone: what was fetched, what was
skipped and why, which model served each call, and which rule fired.
"""

from app.observability.context import (
    bind_case,
    current_request_id,
    new_request_id,
    request_context,
)
from app.observability.logging import configure, event
from app.observability.metrics import metrics
from app.observability.middleware import REQUEST_ID_HEADER, RequestContextMiddleware

__all__ = [
    "REQUEST_ID_HEADER",
    "RequestContextMiddleware",
    "bind_case",
    "configure",
    "current_request_id",
    "event",
    "metrics",
    "new_request_id",
    "request_context",
]
