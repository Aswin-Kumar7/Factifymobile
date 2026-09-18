"""Ledger persistence — writing down what was decided, and on what.

The orchestrator's fixed order names "persist ledger → write back" and neither step
existed. `claim`, `evidence` and `verdict` all held zero rows against a corpus of
2,064 items, so `/v1/cases/{id}` and `/v1/cases/{id}/evidence` could only ever answer
404, and a receipt signed over an evidence digest pointed at nothing retrievable.

The ordering is forced by foreign keys and is also the honest order: a case exists
before its claims, a claim before the evidence attached to it, evidence before the
verdict that rests on it. Nothing here decides anything — it records decisions the
verdict engine already made.

**Persistence never changes an answer.** A write failure is logged and swallowed, and
the caller still gets the verdict it computed. Losing the audit trail is bad; refusing
to answer a user because the audit trail could not be written is worse, and turning a
storage error into a verdict change would be worst of all.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any
from uuid import UUID

from app.db.repositories import (
    CaseRepository,
    ClaimRepository,
    EvidenceRepository,
    ReceiptRepository,
    SourceRepository,
    VerdictRepository,
)
from app.domain.evidence import Evidence
from app.observability.logging import event
from app.orchestration.pipeline import ClaimOutcome, VerificationResult
from app.orchestration.receipt import ReceiptSigner, evidence_from_rows

logger = logging.getLogger("facify.ledger")


class Ledger:
    """Writes one completed verification to the database."""

    def __init__(self, conn: Any, *, signer: ReceiptSigner | None = None) -> None:
        # Optional: without a signing key configured no receipt is issued, and the
        # endpoint says so rather than handing out something unverifiable.
        self._signer = signer
        self._receipts = ReceiptRepository(conn)
        self._cases = CaseRepository(conn)
        self._claims = ClaimRepository(conn)
        self._evidence = EvidenceRepository(conn)
        self._sources = SourceRepository(conn)
        self._verdicts = VerdictRepository(conn)

    async def persist(
        self,
        result: VerificationResult,
        *,
        request_id: str,
        input_type: str,
        language: str | None = None,
        consent_to_process_media: bool = False,
    ) -> bool:
        """Record the case, its claims, their evidence and their verdicts.

        Returns whether the write completed, so the caller can report the gap rather
        than assume a silent success.
        """
        try:
            await self._cases.create(
                request_id=request_id,
                input_type=input_type,
                language=language,
                consent_to_process_media=consent_to_process_media,
                case_id=result.case_id,
            )

            for outcome in result.claims:
                await self._persist_claim(
                    outcome,
                    case_id=result.case_id,
                    language=language,
                    action=result.action.value,
                )

            await self._issue_receipt(result)

        except Exception as error:
            # Deliberately swallowed. See the module docstring: the verdict stands.
            event(
                logger,
                "ledger write failed; verdict returned unpersisted",
                module="orchestration.ledger",
                outcome="degraded",
                failure_reason=f"{type(error).__name__}: {error}",
                case_id=str(result.case_id),
            )
            return False

        event(
            logger,
            "ledger written",
            module="orchestration.ledger",
            outcome="ok",
            case_id=str(result.case_id),
            claims=len(result.claims),
            evidence=len(result.evidence),
        )
        return True

    async def _issue_receipt(self, result: VerificationResult) -> None:
        """Sign this verdict's evidence, here, where that evidence is final.

        Issued at write time rather than at read time on purpose. A receipt computed
        when someone asks for it would sign whatever evidence is present at that
        moment, so it would always verify — and a receipt that always verifies attests
        to nothing. The gap between what was signed and what is stored now is the
        entire mechanism.
        """
        if self._signer is None:
            return

        # Signed over the evidence **as stored**, read back after the write, rather
        # than over the in-memory objects that produced it.
        #
        # Those are not the same values. In memory a citation carries the domain id the
        # resolver gave it (`ev_1`); in the ledger it carries the identifier the
        # database assigned. `canonicalise` includes the id and sorts by it, so a
        # receipt signed before the write can never match a check made after it — the
        # first version of this reported every receipt as tampered.
        #
        # Reading back is also the more honest attestation: what a receipt should
        # certify is what a later reader will actually find.
        rows = await self._evidence.for_case(result.case_id)
        receipt = self._signer.issue(
            case_id=result.case_id,
            evidence=evidence_from_rows(rows),
            action=result.action.value,
            rule_version=result.rule_version,
        )
        await self._receipts.store(
            receipt_id=receipt.id,
            case_id=receipt.case_id,
            evidence_digest=receipt.evidence_digest,
            signature=receipt.signature,
            issued_at=receipt.issued_at,
            rule_version=receipt.rule_version,
            action=receipt.action,
            evidence_count=receipt.evidence_count,
            receipt_version=receipt.version,
        )

    async def _persist_claim(
        self, outcome: ClaimOutcome, *, case_id: UUID, language: str | None, action: str
    ) -> None:
        claim = outcome.claim
        claim_id = await self._claims.create(
            case_id=case_id,
            text=claim.text,
            normalized_text=claim.normalized_text or claim.text.lower(),
            claim_type=claim.claim_type.value,
            severity=claim.severity.value,
            importance=claim.importance.value,
            anchor=claim.anchor.model_dump(mode="json"),
            language=claim.language or language,
            coverage_expectation=(
                claim.coverage_expectation.value if claim.coverage_expectation else None
            ),
            entities=list(claim.entities),
            location=claim.location,
        )

        for item in outcome.evidence:
            await self._persist_evidence(item, claim_id=claim_id)

        await self._verdicts.record(
            claim_id=claim_id,
            status=outcome.decision.status.value,
            # The case-level action, not the claim's status. `Decision` carries no
            # action of its own — the rollup produces one for the whole case — and
            # the column's CHECK constraint accepts only the six action values, so
            # storing a status here fails the write outright.
            action=action,
            reason=outcome.decision.reason,
            rule_id=outcome.decision.rule_id,
            rule_version=outcome.decision.rule_version,
            strength=asdict(outcome.strength),
        )

    async def _persist_evidence(self, item: Evidence, *, claim_id: UUID) -> None:
        """Record the snapshot behind a citation, then the citation itself.

        The snapshot row is written from the evidence rather than from the live
        `SourceSnapshot`, which no longer exists by this point. Everything stored is
        something the fetch produced: the URL it landed on, the hash of what came
        back, and the excerpt that was located inside it.
        """
        snapshot_id = await self._sources.record_snapshot(
            url=item.citation_url,
            final_url=item.citation_url,
            content_hash=item.snapshot_id,
            excerpt=item.source_excerpt,
            title=None,
            published_at=item.observed_at,
        )

        await self._evidence.add_evidence(
            claim_id=claim_id,
            tier=item.tier.value,
            kind=item.kind.value,
            direction=item.direction.value,
            finding=item.finding,
            citation_url=item.citation_url,
            snapshot_id=snapshot_id,
            source_excerpt=item.source_excerpt,
            source_anchor=item.source_anchor.model_dump(mode="json"),
            method=item.method.value,
            match_quality=item.match_quality.value,
            match_basis=item.match_basis.model_dump(mode="json"),
            # Persisted so the case reads back with its publisher and input anchor —
            # a cited source with neither reads as anonymous and unplaceable.
            publisher=item.publisher,
            input_anchor=(item.input_anchor.model_dump(mode="json") if item.input_anchor else None),
        )


class CaseReader:
    """Reads a persisted case back out as the API contract shape.

    `/v1/cases/{id}` and `/v1/cases/{id}/evidence` both resolve through this: the
    evidence endpoint reads `.claims[].evidence` off the same object, so one reader
    serves both and the two can never disagree about what a case contains.

    Everything returned came out of the ledger. Nothing is recomputed — re-deciding a
    stored case at read time would let today's rules silently restate yesterday's
    verdict, and the `rule_version` recorded on the row is what makes an old answer
    interpretable.
    """

    def __init__(self, database: Any) -> None:
        self._database = database

    async def get(self, case_id: UUID) -> Any:
        from app.api.schemas import (
            ClaimResponse,
            ComponentResponse,
            EvidenceResponse,
            InputAnchorResponse,
            MatchBasisResponse,
            SourceAnchorResponse,
            StrengthResponse,
            VerifyResponse,
        )

        async with self._database.connection() as conn:
            case = await CaseRepository(conn).get(case_id)
            if case is None:
                return None

            claim_rows = await ClaimRepository(conn).for_case(case_id)

            claims = []
            action = "SEND_TO_REVIEW"
            rule_version = ""

            for row in claim_rows:
                claim_id = UUID(str(row["id"]))
                verdict = await VerdictRepository(conn).for_claim(claim_id)
                if verdict is None:
                    # A claim with no verdict row is an incomplete write, not a
                    # claim that abstained. Skipped rather than shown as UNVERIFIED,
                    # which would present a storage gap as a finding.
                    continue

                action = str(verdict["action"])
                rule_version = str(verdict["rule_version"])
                strength = verdict["strength_json"] or {}

                evidence_rows = await EvidenceRepository(conn).for_claim(claim_id)
                claims.append(
                    ClaimResponse(
                        id=str(claim_id),
                        text=str(row["text"]),
                        claim_type=str(row["claim_type"]),
                        status=str(verdict["status"]),
                        severity=str(row["severity"]),
                        importance=str(row["importance"]),
                        reason=str(verdict["reason"]),
                        rule_id=str(verdict["rule_id"]),
                        rule_version=rule_version,
                        # The stored strength carries its components and excluded
                        # signals; reading back only score and band dropped the
                        # explanation the evidence screen is built to show, and turned
                        # a repeat check (served from cache through this reader) into a
                        # verdict with an empty breakdown.
                        strength=StrengthResponse(
                            score=float(strength.get("score", 0.0)),
                            band=str(strength.get("band", "none")),
                            version=str(strength.get("version", "")),
                            components=tuple(
                                ComponentResponse(
                                    name=str(component.get("name", "")),
                                    value=float(component.get("value", 0.0)),
                                    explanation=str(
                                        component.get("detail")
                                        or component.get("explanation")
                                        or ""
                                    ),
                                    citations=tuple(component.get("citations", ())),
                                )
                                for component in strength.get("components", ())
                            ),
                            # Stored as full signal dicts (asdict of the Strength
                            # dataclass); the wire form is the provider name only.
                            advisory_excluded=tuple(
                                signal.get("provider", "")
                                if isinstance(signal, dict)
                                else str(signal)
                                for signal in strength.get("advisory_excluded", ())
                            ),
                        ),
                        evidence=tuple(
                            EvidenceResponse(
                                id=str(e["id"]),
                                tier=str(e["tier"]),
                                kind=str(e["kind"]),
                                direction=str(e["direction"]),
                                method=str(e["method"]),
                                finding=str(e["finding"]),
                                citation_url=str(e["citation_url"]),
                                snapshot_id=str(e["snapshot_id"]),
                                source_excerpt=str(e["source_excerpt"]),
                                source_anchor=SourceAnchorResponse(**(e["source_anchor"] or {})),
                                match_basis=MatchBasisResponse(**(e["match_basis"] or {})),
                                match_quality=str(e["match_quality"]),
                                # Publisher, date and input anchor are stored on the
                                # row; dropping them made a cited source read as an
                                # anonymous, undated one.
                                publisher=e["publisher"],
                                observed_at=e["observed_at"],
                                input_anchor=(
                                    InputAnchorResponse(**e["input_anchor"])
                                    if e["input_anchor"]
                                    else None
                                ),
                            )
                            for e in evidence_rows
                        ),
                    )
                )

        return VerifyResponse(
            case_id=str(case_id),
            action=action,
            action_reason="Retrieved from the ledger as recorded.",
            rule_version=rule_version,
            claims=tuple(claims),
            retrieved_at=case["created_at"],
        )
