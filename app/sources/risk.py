"""Source risk (M32).

Says what is known about a publisher. Runs in parallel with the claim track and is
kept strictly separate from it, because the two answer different questions and
conflating them is how a verification system acquires a defamation problem.

**Source risk never makes a claim false.** A three-week-old domain with no named
authors publishing an accurate report is publishing an accurate report. What risk
signals justify is *looking harder* — and, at their strongest, routing a case to a
human. Their ceiling is abstention plus review, enforced here and again in the
verdict engine and once more in the case rollup.

Every signal is itemised rather than fused into a number, so a reader sees "registered
three weeks ago, no contact page, no named authors" rather than "risk: 0.82". The
first is checkable; the second is a score with no author, which is the thing this
whole system exists not to produce.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

from app.domain.enums import SourceRisk
from app.observability.logging import event

logger = logging.getLogger("factify.risk")

NAME = "source_risk"
VERSION = "2026.08.1"

# A domain younger than this covering an established beat is worth noting. Not
# damning — new outlets are founded — but a "news portal since 2005" registered last
# month is a citable contradiction.
YOUNG_DOMAIN_DAYS = 180

# Levenshtein distance at or below which a domain is a plausible typosquat of a
# credible one. One or two edits is a deliberate near-miss; three is a different name.
TYPOSQUAT_DISTANCE = 2


@dataclass(frozen=True, slots=True)
class RiskSignal:
    """One itemised observation about a publisher.

    `finding` is written to be read aloud to a user, because it will be.
    """

    kind: str
    finding: str
    severity: str = "low"

    @property
    def is_strong(self) -> bool:
        return self.severity == "high"


@dataclass(frozen=True, slots=True)
class SourceProfile:
    """Everything known about a publisher, and the level it adds up to."""

    domain: str
    signals: tuple[RiskSignal, ...] = field(default_factory=tuple)
    domain_age_days: int | None = None
    assessed_at: datetime | None = None

    @property
    def level(self) -> SourceRisk:
        """Derived from the signals, and never from anything else.

        No model contributes here. The level is a count of observations a reader can
        verify independently.
        """
        if not self.signals:
            return SourceRisk.UNKNOWN

        strong = sum(1 for signal in self.signals if signal.is_strong)
        if strong >= 2:
            return SourceRisk.HIGH
        if strong == 1 or len(self.signals) >= 3:
            return SourceRisk.MEDIUM
        return SourceRisk.LOW

    @property
    def findings(self) -> tuple[str, ...]:
        """The itemised list the interface shows instead of a score."""
        return tuple(signal.finding for signal in self.signals)


def _levenshtein(left: str, right: str) -> int:
    """Edit distance. Small inputs, so the simple implementation is the right one."""
    if len(left) < len(right):
        left, right = right, left

    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, start=1):
        current = [i]
        for j, b in enumerate(right, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a != b)))
        previous = current

    return previous[-1]


def _registrable(domain: str) -> str:
    """Strip the subdomain and suffix down to the name that is being imitated."""
    parts = domain.lower().removeprefix("www.").split(".")
    return parts[0] if parts else domain


def detect_typosquat(domain: str, credible_domains: frozenset[str]) -> RiskSignal | None:
    """Whether this domain is a near-miss of a credible one.

    `thehindu.co.in` against `thehindu.com` is the canonical Indian example: not a
    typo anyone makes, and not a coincidence either.
    """
    candidate = _registrable(domain)
    if not candidate:
        return None

    for credible in credible_domains:
        target = _registrable(credible)
        if candidate == target and domain.lower().removeprefix("www.") != credible:
            return RiskSignal(
                kind="typosquat",
                finding=f"{domain} closely imitates {credible}",
                severity="high",
            )
        distance = _levenshtein(candidate, target)
        if 0 < distance <= TYPOSQUAT_DISTANCE and len(target) > 5:
            return RiskSignal(
                kind="typosquat",
                finding=f"{domain} is {distance} character(s) from {credible}",
                severity="high",
            )

    return None


def assess_domain_age(
    registered_at: datetime | None, *, now: datetime | None = None
) -> RiskSignal | None:
    """Flag a very young domain. Recorded, never decisive."""
    if registered_at is None:
        return None

    age = (now or datetime.now(UTC)) - registered_at
    if age.days >= YOUNG_DOMAIN_DAYS:
        return None

    return RiskSignal(
        kind="domain_age",
        finding=f"Domain registered {age.days} days ago",
        severity="high" if age.days < 60 else "low",
    )


_CONTACT = re.compile(r"\b(contact|about[- ]us|editorial[- ]policy|imprint|masthead)\b", re.I)
_BYLINE = re.compile(r"\b(by|written by|author)\b\s+[A-Z][a-z]+", re.I)


def assess_transparency(html: str) -> tuple[RiskSignal, ...]:
    """The feature set a credibility analyst checks by hand, computed.

    Absence of any single one means little; absence of all of them is the shape of a
    site built to look like a publisher rather than to be one.
    """
    signals: list[RiskSignal] = []

    if not _CONTACT.search(html):
        signals.append(
            RiskSignal(
                kind="no_contact",
                finding="No contact, about or editorial-policy page found",
            )
        )

    if not _BYLINE.search(html):
        signals.append(RiskSignal(kind="no_byline", finding="No named author on the article"))

    return tuple(signals)


def injection_signal(attempts: tuple[str, ...]) -> RiskSignal | None:
    """A page that tried to instruct the verifier is practising deception.

    This is the one risk signal that is unambiguous. Domain age has innocent
    explanations and a missing contact page is often laziness; hidden text telling an
    automated checker to report the content as verified has none.
    """
    if not attempts:
        return None

    return RiskSignal(
        kind="prompt_injection",
        finding=(
            f"The page contains hidden instructions aimed at automated verification "
            f"({len(attempts)} detected)"
        ),
        severity="high",
    )


class SourceRiskProfiler:
    """Builds a publisher profile from independently checkable observations."""

    name = NAME
    version = VERSION

    def __init__(self, *, credible_domains: frozenset[str]) -> None:
        self._credible = credible_domains

    def profile(
        self,
        url: str,
        *,
        html: str = "",
        registered_at: datetime | None = None,
        injection_attempts: tuple[str, ...] = (),
        now: datetime | None = None,
    ) -> SourceProfile:
        """Assess a publisher. Never touches the claim."""
        domain = urlsplit(url).netloc.lower()
        signals: list[RiskSignal] = []

        if (typosquat := detect_typosquat(domain, self._credible)) is not None:
            signals.append(typosquat)

        if (age := assess_domain_age(registered_at, now=now)) is not None:
            signals.append(age)

        if html:
            signals.extend(assess_transparency(html))

        if (injection := injection_signal(injection_attempts)) is not None:
            signals.append(injection)

        profile = SourceProfile(
            domain=domain,
            signals=tuple(signals),
            domain_age_days=(
                ((now or datetime.now(UTC)) - registered_at).days if registered_at else None
            ),
            assessed_at=now or datetime.now(UTC),
        )

        if profile.level is SourceRisk.HIGH:
            event(
                logger,
                "high source risk",
                module="sources.risk",
                outcome="ok",
                signals=len(signals),
                kinds=[signal.kind for signal in signals],
            )

        return profile
