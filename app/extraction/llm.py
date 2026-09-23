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
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.enums import ClaimType, CoverageExpectation, Importance, Severity
from app.extraction.model_wire import WireFormat, build_call, response_text, usage_of
from app.governor.governor import Governor, ProviderUnavailable
from app.observability.logging import event
from app.security.fetcher import FetchResult, SecureFetcher
from app.security.injection import FencedContent, fence

logger = logging.getLogger("facify.llm")

PROVIDER = "llm"

# Bumped whenever the prompt or the schema changes, because either changes what the
# same document extracts to — and the extraction cache is keyed on it.
EXTRACTOR_VERSION = "2026.09.3"

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
    "verifiable. For each claim, report where in the document it appeared. "
    "Each claim must be a COMPLETE, self-contained assertion that can be checked on its "
    "own — a full statement about who did what, when or where. Never emit a sentence "
    "fragment, a bare noun or place ('Odisha'), a date on its own ('after five days'), "
    "or a prepositional phrase ('in floodwaters') as a claim. If one sentence makes one "
    "assertion, extract ONE claim carrying the whole assertion, not several pieces of "
    "it. A fragment cannot be verified and must never be extracted. "
    "OPINION means a value judgement or preference that no evidence could settle — "
    "'the scheme is inadequate', 'the film is boring'. It does NOT mean a claim you "
    "think is false, implausible, fringe or already debunked. "
    "'Drinking hot water cures coronavirus' and 'EVMs can be hacked remotely' are "
    "FACTUAL claims that happen to be false: they assert something about the world "
    "that evidence can address, so classify them by what they assert — a health "
    "claim is an EVENT or STATISTIC, not an OPINION. "
    "Misfiling a false factual claim as OPINION removes it from checking entirely, "
    "which is the one outcome this extraction must never produce. "
    "A sentence reporting that someone said, announced, found, ruled or DEBUNKED "
    "something is an ATTRIBUTION claim, not an EVENT: what can be checked is that "
    "they said it. Keep the whole sentence, including what they said, so the claim "
    "stays self-contained - but classify it by the reporting. 'The government has "
    "debunked claims that a fire broke out at a defence facility' is an ATTRIBUTION "
    "about the government, not an EVENT about a fire. "
    "search_phrases: two or three short web queries that would find published "
    "sources ADDRESSING this claim, in either direction. The claim's own sentence "
    "is already searched, and on its own it retrieves the topic rather than any "
    "check of it: 'doctors confirm drinking cow urine daily cures cancer' returns "
    "reports of people doing it. Give the underlying question and the words a check "
    "would carry - 'does cow urine cure cancer', 'cow urine cancer treatment "
    "evidence', 'cow urine cancer fact check'. Keep each under eight words, use the "
    "claim's own entities and plain nouns, no quotation marks, and never phrase one "
    "so that it presumes an answer."
)


def _enum_values(enum_type: type[StrEnum]) -> list[str]:
    """The wire values of an enum, for the response schema.

    Derived rather than written out so a new member cannot be offered to the model
    without `ProposedClaim` also accepting it.
    """
    return [member.value for member in enum_type]


# The response shape, in the subset of JSON Schema the provider accepts.
#
# Derived from the enums rather than written out, so adding a ClaimType cannot
# leave the model offering a value `ProposedClaim` will then reject. Kept in step
# with that model by construction; EXTRACTOR_VERSION is bumped when either moves,
# because both change what the same document extracts to.
_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "maxItems": MAX_CLAIMS_PER_DOCUMENT,
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "claim_type": {"type": "string", "enum": _enum_values(ClaimType)},
                    "severity": {"type": "string", "enum": _enum_values(Severity)},
                    "importance": {"type": "string", "enum": _enum_values(Importance)},
                    "coverage_expectation": {
                        "type": "string",
                        "enum": _enum_values(CoverageExpectation),
                        "nullable": True,
                    },
                    "entities": {"type": "array", "items": {"type": "string"}},
                    "dates": {"type": "array", "items": {"type": "string"}},
                    "location": {"type": "string", "nullable": True},
                    "search_phrases": {"type": "array", "items": {"type": "string"}},
                    "needs_human_review": {"type": "boolean"},
                    "source_anchor": {
                        "type": "object",
                        "properties": {
                            "section": {"type": "string", "nullable": True},
                            "paragraph_index": {"type": "integer", "nullable": True},
                            "char_start": {"type": "integer", "nullable": True},
                            "char_end": {"type": "integer", "nullable": True},
                        },
                    },
                },
                "required": ["text", "claim_type", "severity", "importance"],
            },
        }
    },
    "required": ["claims"],
}


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
        api_format: WireFormat = WireFormat.GEMINI,
    ) -> None:
        self._fetcher = fetcher
        self._governor = governor
        self._endpoint = endpoint
        self._api_key = api_key
        self._model_id = model_id
        self._escalation_model_id = escalation_model_id
        self._api_format = api_format

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

        url, headers, body = build_call(
            fmt=self._api_format,
            endpoint=self._endpoint,
            model_id=model_id,
            api_key=self._api_key,
            system=_SYSTEM_INSTRUCTION,
            # The document in a data position only, inside its nonce fence. It never
            # touches the system instruction, and nothing is concatenated into it.
            user_block=fenced.prompt_block,
            response_schema=_RESPONSE_SCHEMA,
            temperature=0.0,
        )
        response = await self._fetcher.post_json(url, body, provider=PROVIDER, headers=headers)

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

    def _parse(self, response: FetchResult) -> dict[str, Any]:
        # The schema is transmitted with the request (via `build_call`), not merely
        # referred to: a model asked to match a shape it has never been shown answers
        # plausibly and differently every time, and fails validation here.
        envelope = json.loads(response.text)
        used = usage_of(self._api_format, envelope)
        if used.total:
            event(
                logger,
                "model call metered",
                module="extraction.llm",
                outcome="ok",
                provider=PROVIDER,
                model_id=self._model_id,
                call="extract",
                prompt_tokens=used.prompt,
                completion_tokens=used.completion,
            )
        text = response_text(self._api_format, envelope)
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
