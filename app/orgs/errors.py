"""The errors the organisation and API-key paths answer with.

Each carries a machine-readable `error_code` beside the human message, as Anthropic,
OpenAI and Tavily do, so a program can tell "out of credits" from "too many
requests" without reading prose.
"""

from __future__ import annotations


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.headers = headers or {}


def invalid_key() -> ApiError:
    return ApiError(401, "invalid_api_key", "this API key is not valid, or has been revoked")


def not_allowed(message: str) -> ApiError:
    return ApiError(403, "key_not_allowed", message)


def forbidden(message: str = "you don't have permission to do that") -> ApiError:
    return ApiError(403, "forbidden", message)


def not_found(what: str = "not found") -> ApiError:
    return ApiError(404, "not_found", what)


def bad_request(message: str, code: str = "invalid_request") -> ApiError:
    return ApiError(400, code, message)
