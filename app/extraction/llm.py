"""The bounded model client (M18, M20 support).

The only place in the codebase that talks to a language model, and the narrowest one
it could be. Four rules from codexplan.md §11 are structural here rather than
advisory:

  1. **One extraction call per document.** Claims, entities, dates, severity,
     importance, coverage expectation and search phrases come back in a single
     structured response. A caller that wants three of those does not get three calls.
  2. **Cheapest model that satisfies the schema.** Escalation happens only on schema
     failure and is capped separately.
  3. **Cached by content hash**, so a re-run costs nothing.
  4. **No model call on the response path** — phrasing is templates (M21).

And the rule that outranks all four: **when the model is unavailable, this returns
nothing.** It does not guess, approximate, or emit a plausible-looking claim. A stub
that returns something reasonable is fabricated evidence, and the pipeline is built
to abstain rather than to be fed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.enums import ClaimType, CoverageExpectation, Importance, Severity
from app.governor.governor import Governor, ProviderUnavailable
from app.observability.logging import event
from app.security.fetcher import FetchResult, SecureFetcher
from app.security.injection import FencedContent, fence

logger = logging.getLogger("facify.llm")

PROVIDER = "llm"

# Bumped whenever the prompt or the schema changes, because either changes what the
# same document extracts to — and the extraction cache is keyed on it.
EXTRACTOR_VERSION = "2026.08.1"

MAX_CLAIMS_PER_DOCUMENT = 7


class ProposedAnchor(BaseModel):
    """Where the model says it found the claim. Verified before it is believed."""

    model_config = ConfigDict(extra="ignore")

    section: str | None = None
    paragraph_index: int | None = None
    char_start: int | None = None
    char_end: int | None = None


class ProposedClaim(BaseModel):
    """One claim as proposed by the model — a proposal, not a finding.

    Schema validation is the first gate and anchor verification is the second. The
    model may be wrong or may have been instructed by the document; neither can
    produce a stored claim that does not correspond to real text.
    """

    model_config = ConfigDict(extra="ignore")

    text: str = Field(min_length=1)
    claim_type: ClaimType
    severity: Severity
    importance: Importance
    coverage_expectation: CoverageExpectation | None = None
    entities: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    location: str | None = None
    search_phrases: list[str] = Field(default_factory=list)
    needs_human_review: bool = False
    source_anchor: ProposedAnchor = Field(default_factory=ProposedAnchor)


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    claims: list[ProposedClaim] = Field(default_factory=list, max_length=MAX_CLAIMS_PER_DOCUMENT)


@dataclass(frozen=True, slots=True)
class ExtractionOutcome:
    """What the model produced, or why nothing was produced.

    `claims` being empty with a `reason` set is a complete, correct result: the
    pipeline continues with whatever media evidence exists, or abstains.
    """

    claims: tuple[ProposedClaim, ...] = ()
    model_id: str | None = None
    reason: str | None = None
    injection_findings: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        return self.reason is None


_SYSTEM_INSTRUCTION = (
    "You extract checkable factual claims from a document. You never judge whether a "
    "claim is true, and you never assign a status, verdict or confidence. Return only "
    "the JSON described by the schema. Extract at most "
    f"{MAX_CLAIMS_PER_DOCUMENT} claims, choosing the ones that are consequential and "
    "verifiable. Label opinion as OPINION. For each claim, report where in the "
    "document it appeared."
)


class LLMExtractor:
    """Structured extraction over a governed, fenced, cached call."""

    def __init__(
        self,
        *,
        fetcher: SecureFetcher,
        governor: Governor,
        endpoint: str,
        api_key: str,
        model_id: str,
        escalation_model_id: str | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._governor = governor
        self._endpoint = endpoint
        self._api_key = api_key
        self._model_id = model_id
        self._escalation_model_id = escalation_model_id

    async def extract_claims(self, text: str) -> ExtractionOutcome:
        """One call. One document. Every field at once.

        Injection findings travel with the outcome so the source-risk track can
        record that this page tried to instruct its own verifier.
        """
        fenced = fence(text)

        outcome = await self._attempt(fenced, model_id=self._model_id)

        if outcome.succeeded or self._escalation_model_id is None:
            return outcome

        # Escalation is for a model that could not satisfy the schema, not for a
        # model that was never reachable — retrying a budget refusal on a more
        # expensive model would spend the escalation cap to learn the same thing.
        if outcome.reason and outcome.reason.startswith("unavailable"):
            return outcome

        event(
            logger,
            "escalating extraction",
            module="extraction.llm",
            outcome="retry",
            provider=PROVIDER,
            failure_reason=outcome.reason,
        )
        return await self._attempt(fenced, model_id=self._escalation_model_id)

    async def _attempt(self, fenced: FencedContent, *, model_id: str) -> ExtractionOutcome:
        findings = fenced.sanitised.risk_signals

        try:
            grant = await self._governor.acquire(PROVIDER)
        except ProviderUnavailable as unavailable:
            # No credentials, no budget, or a burst ceiling. Nothing is invented.
            return ExtractionOutcome(
                reason=f"unavailable: {unavailable.reason.value}", injection_findings=findings
            )

        del grant

        response = await self._fetcher.post_json(
            self._endpoint.format(model=model_id),
            self._build_request(fenced),
            provider=PROVIDER,
            headers={"x-goog-api-key": self._api_key},
        )

        if not isinstance(response, FetchResult):
            return ExtractionOutcome(
                reason=f"provider failed: {response.reason}", injection_findings=findings
            )

        try:
            payload = self._parse(response)
            validated = ExtractionResponse.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, KeyError, TypeError) as exc:
            event(
                logger,
                "extraction did not satisfy the schema",
                module="extraction.llm",
                outcome="error",
                provider=PROVIDER,
                model_id=model_id,
                failure_reason=type(exc).__name__,
                level=logging.WARNING,
            )
            return ExtractionOutcome(
                reason=f"schema validation failed: {type(exc).__name__}",
                injection_findings=findings,
            )

        return ExtractionOutcome(
            claims=tuple(validated.claims), model_id=model_id, injection_findings=findings
        )

    def _build_request(self, fenced: FencedContent) -> dict[str, Any]:
        """Assemble the request with external text in a data position only.

        The document goes in a user part, inside its nonce fence. It never touches
        the system instruction, and nothing is concatenated into it.
        """
        return {
            "systemInstruction": {"parts": [{"text": _SYSTEM_INSTRUCTION}]},
            "contents": [{"role": "user", "parts": [{"text": fenced.prompt_block}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.0,
            },
        }

    def _parse(self, response: FetchResult) -> dict[str, Any]:
        envelope = json.loads(response.text)
        text = envelope["candidates"][0]["content"]["parts"][0]["text"]
        parsed: dict[str, Any] = json.loads(text)
        return parsed


class UnavailableExtractor:
    """The extractor used when no model is configured.

    Returns nothing, always. This exists so the pipeline has something to call
    without any branch anywhere producing a plausible-looking claim from thin air.
    """

    async def extract_claims(self, text: str) -> ExtractionOutcome:
        del text
        return ExtractionOutcome(reason="unavailable: no model configured")
