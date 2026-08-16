"""Structured logging with a fixed field set and mandatory redaction (M04).

Two things are non-negotiable here.

**The field set is fixed.** Ad-hoc keys make logs unqueryable exactly when they are
needed. Every event carries the same skeleton — request id, case id, module,
provider, model id, latency, outcome, failure reason — and anything else goes in a
`detail` object.

**Redaction is applied at the formatter, not at the call site.** A rule that depends
on every caller remembering it is not a rule. Article bodies, raw media, credentials
and EXIF location must never reach a log, so the formatter drops oversized strings
and known-sensitive keys regardless of who logged them.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from pythonjsonlogger import json as jsonlogger

from app.observability.context import current

# Keys whose values never appear in a log line, wherever they came from.
_REDACTED_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "credential",
        "gps",
        "gps_latitude",
        "gps_longitude",
        "latitude",
        "longitude",
        "password",
        "secret",
        "token",
    }
)

# Fields that carry content rather than metadata. Logs record that a body was
# extracted and how large it was — never the body.
_CONTENT_KEYS = frozenset({"body", "article_body", "raw_media", "content", "excerpt", "text"})

_MAX_VALUE_CHARS = 200

REDACTED = "[redacted]"

# Custom fields travel under this single key to stay clear of the reserved
# LogRecord attribute names, then are lifted to the top level by the formatter.
_PAYLOAD_KEY = "facify"


def _scrub(value: Any, key: str | None = None) -> Any:
    """Drop secrets, drop content, truncate anything unexpectedly large."""
    if key is not None:
        lowered = key.lower()
        if lowered in _REDACTED_KEYS:
            return REDACTED
        if lowered in _CONTENT_KEYS:
            return f"[content omitted: {len(str(value))} chars]"

    if isinstance(value, dict):
        return {k: _scrub(v, k) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_scrub(item) for item in value]
    if isinstance(value, str) and len(value) > _MAX_VALUE_CHARS:
        return f"{value[:_MAX_VALUE_CHARS]}… [{len(value)} chars]"
    return value


class ContextFormatter(jsonlogger.JsonFormatter):
    """Injects the request context and scrubs every record before emission."""

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)

        log_record["level"] = record.levelname
        log_record["logger"] = record.name

        # Custom fields arrive under one namespaced key and are lifted here.
        # `LogRecord` reserves a long list of attribute names — `module`, `filename`,
        # `process` among them — and passing any of those through `extra` raises.
        # Namespacing means adding a field can never collide with the standard set.
        payload = log_record.pop(_PAYLOAD_KEY, None)
        if isinstance(payload, dict):
            log_record.update(payload)

        ctx = current()
        if ctx is not None:
            log_record["request_id"] = ctx.request_id
            if ctx.case_id is not None:
                log_record["case_id"] = ctx.case_id
            log_record.update(ctx.extra)

        for key in list(log_record):
            log_record[key] = _scrub(log_record[key], key)


def configure(level: str = "INFO") -> None:
    """Install the JSON handler as the only root handler.

    Idempotent: repeated calls (tests, reload) replace rather than accumulate
    handlers, which otherwise produces duplicate lines that look like retries.
    """
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(ContextFormatter("%(asctime)s %(level)s %(name)s %(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def event(
    logger: logging.Logger,
    message: str,
    *,
    module: str,
    outcome: str,
    provider: str | None = None,
    model_id: str | None = None,
    latency_ms: float | None = None,
    failure_reason: str | None = None,
    level: int = logging.INFO,
    **detail: Any,
) -> None:
    """Emit one structured event with the fixed field set.

    `outcome` and `failure_reason` are what make a verdict reconstructable: every
    provider that was skipped says so and says why, so the response can honestly
    report what was not checked.
    """
    logger.log(
        level,
        message,
        extra={
            _PAYLOAD_KEY: {
                "module": module,
                "outcome": outcome,
                "provider": provider,
                "model_id": model_id,
                "latency_ms": latency_ms,
                "failure_reason": failure_reason,
                "detail": detail or None,
            }
        },
    )
