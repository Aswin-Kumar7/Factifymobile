"""What is known about the website a submitted link comes from.

The checks behind every claim read only publishers on the trusted list, but the page
a person shares can be from anywhere - and "is this site even a real news outlet?"
is half of what they are asking. The source-risk profiler (`app/sources/risk.py`)
was built for this and was never connected: a link's own site was never assessed
(2026-10-01).

Now, for a submitted link (or a link inside a forward):

  - whether the site is on Factify's trusted-source list, and at what level, or is
    a fact-checker;
  - for a site that is not: whether its name imitates a trusted one (ndtv-news.in),
    how long ago it was registered (RDAP, the public registry record), whether it
    has a contact or about page and named authors;
  - whether the page carries hidden instructions aimed at automated checkers.

Every finding is itemised, never fused into a score, and none of them can make a
claim false. A high-risk site can only hold a verdict back from "True" (the
verdict engine caps it at review), which is what source risk is for.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

from app.domain.enums import Credibility, SourceRisk
from app.domain.publishers import registrable_domain
from app.security.fetcher import DEFAULT_ACCEPTED_TYPES, FetchResult, SecureFetcher
from app.security.injection import detect
from app.sources.credibility import SourceCredibility
from app.sources.risk import RiskSignal, SourceRiskProfiler

logger = logging.getLogger("factify.sources.source_profile")

_TRUST = {
    Credibility.HIGH: "highly credible",
    Credibility.MEDIUM: "credible",
    Credibility.LOW: "listed",
}

_RDAP = "https://rdap.org/domain/{domain}"


@dataclass(frozen=True, slots=True)
class SourceReport:
    """One link's website: on the list or not, and what was observed about it."""

    domain: str
    trusted: bool
    trust: str | None = None
    fact_checker: bool = False
    level: SourceRisk = SourceRisk.UNKNOWN
    findings: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    domain_age_days: int | None = None


async def registered_on(fetcher: SecureFetcher | None, domain: str) -> datetime | None:
    """When a domain was first registered, from its public RDAP record, or None."""
    if fetcher is None or not domain:
        return None
    try:
        result = await fetcher.fetch(_RDAP.format(domain=domain), provider="rdap")
    except Exception:
        return None
    if not isinstance(result, FetchResult):
        return None
    try:
        events = json.loads(result.text).get("events") or []
    except (json.JSONDecodeError, AttributeError):
        return None
    for item in events:
        if isinstance(item, dict) and item.get("eventAction") == "registration":
            try:
                when = datetime.fromisoformat(str(item.get("eventDate", "")).replace("Z", "+00:00"))
            except ValueError:
                return None
            return when if when.tzinfo else when.replace(tzinfo=UTC)
    return None


def rdap_fetcher() -> SecureFetcher:
    """A fetcher that reads RDAP's JSON, which the default one does not parse."""
    return SecureFetcher(
        timeout_seconds=6.0,
        accepted_types=(*DEFAULT_ACCEPTED_TYPES, "application/rdap+json", "application/json"),
    )


async def profile_link(
    url: str,
    *,
    html: str = "",
    text: str = "",
    credibility: SourceCredibility,
    rdap: SecureFetcher | None = None,
    now: datetime | None = None,
) -> SourceReport:
    """Everything observable about the website `url` is on."""
    host = urlsplit(url).netloc.lower().removeprefix("www.")
    domain = registrable_domain(url) or host
    trusted = credibility.is_credible(url)
    fact_checker = credibility.is_fact_checker(url)
    injection = tuple(f.excerpt for f in detect(text or html)) if (text or html) else ()

    if trusted:
        trust = _TRUST[credibility.credibility(url)]
        findings = [
            f"{domain} is a fact-checker on Factify's trusted-source list."
            if fact_checker
            else f"{domain} is on Factify's trusted-source list ({trust})."
        ]
        signals: tuple[RiskSignal, ...] = ()
        if injection:
            profile = SourceRiskProfiler(credible_domains=frozenset()).profile(
                url, injection_attempts=injection, now=now
            )
            signals = profile.signals
        return SourceReport(
            domain=domain,
            trusted=True,
            trust=trust,
            fact_checker=fact_checker,
            level=SourceRisk.HIGH if signals else SourceRisk.LOW,
            findings=tuple(findings),
            warnings=tuple(s.finding for s in signals),
        )

    registered = await registered_on(rdap, domain)
    profile = SourceRiskProfiler(credible_domains=credibility.trusted_hosts).profile(
        url, html=html, registered_at=registered, injection_attempts=injection, now=now
    )
    findings = [f"{domain} is not on Factify's trusted-source list."]
    if profile.domain_age_days is not None and profile.domain_age_days >= 180:
        years = profile.domain_age_days // 365
        findings.append(
            f"Registered {years} year{'s' if years != 1 else ''} ago."
            if years
            else f"Registered {profile.domain_age_days // 30} months ago."
        )
    level = profile.level if profile.signals else SourceRisk.UNKNOWN
    return SourceReport(
        domain=domain,
        trusted=False,
        level=level,
        findings=tuple(findings),
        warnings=profile.findings,
        domain_age_days=profile.domain_age_days,
    )
