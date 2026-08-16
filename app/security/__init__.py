"""Safety boundaries (M09-M12).

Every one of these exists because the service handles adversary-controlled input by
design: URLs an attacker chooses, files an attacker uploads, and page text an
attacker writes. None of them is defence in depth around a trusted core — they are
the boundary itself.
"""

from app.security.fetcher import FetchFailure, FetchResult, SecureFetcher
from app.security.injection import (
    FencedContent,
    InjectionFinding,
    InjectionPattern,
    SanitisedText,
    detect,
    fence,
    sanitise,
)
from app.security.ratelimit import (
    LimitPolicy,
    RateLimit,
    SlidingWindowLimiter,
    caller_key,
)
from app.security.ssrf import (
    BlockedDestination,
    Destination,
    is_blocked_address,
    resolve_and_validate,
    validate_url,
)
from app.security.uploads import (
    MediaKind,
    UploadRejected,
    ValidatedUpload,
    sniff,
    validate_upload,
)

__all__ = [
    "BlockedDestination",
    "Destination",
    "FencedContent",
    "FetchFailure",
    "FetchResult",
    "InjectionFinding",
    "InjectionPattern",
    "LimitPolicy",
    "MediaKind",
    "RateLimit",
    "SanitisedText",
    "SecureFetcher",
    "SlidingWindowLimiter",
    "UploadRejected",
    "ValidatedUpload",
    "caller_key",
    "detect",
    "fence",
    "is_blocked_address",
    "resolve_and_validate",
    "sanitise",
    "sniff",
    "validate_upload",
    "validate_url",
]
