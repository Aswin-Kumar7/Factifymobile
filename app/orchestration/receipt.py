"""Result receipt (M42).

A verifiable record of what was attested, on what evidence, and when.

**What this is not, stated first because the temptation to oversell it is real:** it
is not a legal certificate, not a compliance artifact, and not a tamper-*proof*
archive. It is tamper-*evident*. It proves that the evidence rows behind a verdict
have not changed since the verdict was issued, signed with a development key held by
this service. Anyone who controls the key can issue a receipt saying anything. That
is a meaningful guarantee and a narrow one, and describing it as more would be the
same failure mode as a confident wrong verdict — authority-shaped language covering a
weaker fact.

The digest is built by canonicalising the evidence set: every citation, snapshot,
excerpt and anchor, in a fixed order, joined by separators that cannot occur inside
the values. Alter any stored evidence row and the recomputed digest stops matching,
which is exactly what the gate tests.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.domain.evidence import Evidence
from app.observability.logging import event

logger = logging.getLogger("factify.receipt")

RECEIPT_VERSION = "2026.08.1"

# Field separator for canonicalisation. A unit separator cannot appear in a URL, a
# hash or extracted text, so no combination of values can be made to collide by
# choosing content that contains the delimiter.
_FIELD = "\x1f"
_RECORD = "\x1e"

DISCLAIMER = (
    "This is a tamper-evident result receipt, not a legal certificate or a "
    "compliance artifact. It shows what was attested, on what evidence, and when."
)


@dataclass(frozen=True, slots=True)
class Receipt:
    """A signed statement about one case's evidence set."""

    id: str
    case_id: UUID
    evidence_digest: str
    signature: str
    issued_at: datetime
    rule_version: str
    action: str
    evidence_count: int
    version: str = RECEIPT_VERSION


@dataclass(frozen=True, slots=True)
class Verification:
    """The outcome of checking a receipt against stored evidence."""

    valid: bool
    reason: str = ""


def canonicalise(evidence: list[Evidence]) -> str:
    """Render an evidence set as one deterministic string.

    Sorted by evidence id so the digest does not depend on retrieval order — two runs
    that found the same evidence in a different sequence must produce the same
    receipt, or the receipt would be evidence about scheduling rather than content.

    Every field that would change the meaning of a citation is included. A field left
    out is a field an attacker may alter freely.
    """
    records = []
    for item in sorted(evidence, key=lambda e: e.id):
        records.append(
            _FIELD.join(
                (
                    item.id,
                    item.claim_id,
                    item.tier.value,
                    item.kind.value,
                    item.direction.value,
                    item.method.value,
                    item.citation_url,
                    item.snapshot_id,
                    item.source_excerpt,
                    str(item.source_anchor.char_start),
                    str(item.source_anchor.char_end),
                    item.match_basis.metric,
                    f"{item.match_basis.value:.6f}",
                    f"{item.match_basis.threshold:.6f}",
                    item.match_quality.value,
                )
            )
        )
    return _RECORD.join(records)


def digest(evidence: list[Evidence]) -> str:
    """The content address of an evidence set."""
    return "sha256:" + hashlib.sha256(canonicalise(evidence).encode("utf-8")).hexdigest()


class ReceiptSigner:
    """Issues and verifies receipts with a symmetric development key.

    Symmetric on purpose for now: the signing and verifying parties are the same
    service, so a keypair would add ceremony without adding a property. When a third
    party needs to verify independently this becomes asymmetric, and the receipt
    already carries a version field so that change is expressible.
    """

    def __init__(self, *, key: str, version: str = RECEIPT_VERSION) -> None:
        if not key:
            raise ValueError("a receipt signing key is required; refusing to sign with nothing")
        self._key = key.encode("utf-8")
        self._version = version

    def issue(
        self,
        *,
        case_id: UUID,
        evidence: list[Evidence],
        action: str,
        rule_version: str,
        issued_at: datetime | None = None,
    ) -> Receipt:
        """Sign the evidence digest for a case."""
        stamp = issued_at or datetime.now(UTC)
        evidence_digest = digest(evidence)

        signature = self._sign(
            case_id=case_id,
            evidence_digest=evidence_digest,
            action=action,
            rule_version=rule_version,
            issued_at=stamp,
        )

        receipt = Receipt(
            # Content-addressed: the identifier is derived from what was attested, so
            # a receipt cannot silently be made to point at different content.
            id="rcpt:" + hashlib.sha256(f"{case_id}{evidence_digest}".encode()).hexdigest()[:32],
            case_id=case_id,
            evidence_digest=evidence_digest,
            signature=signature,
            issued_at=stamp,
            rule_version=rule_version,
            action=action,
            evidence_count=len(evidence),
            version=self._version,
        )

        event(
            logger,
            "receipt issued",
            module="receipt",
            outcome="ok",
            evidence_count=len(evidence),
        )
        return receipt

    def verify(self, receipt: Receipt, evidence: list[Evidence]) -> Verification:
        """Check a receipt against the evidence currently stored.

        Two independent checks, and both must pass. The signature proves the receipt
        was issued by this service; the digest proves the evidence has not changed
        since. A receipt that passes the first and fails the second is precisely the
        tampering case this module exists to surface.
        """
        expected = self._sign(
            case_id=receipt.case_id,
            evidence_digest=receipt.evidence_digest,
            action=receipt.action,
            rule_version=receipt.rule_version,
            issued_at=receipt.issued_at,
        )

        if not hmac.compare_digest(expected, receipt.signature):
            return Verification(
                valid=False,
                reason="the signature does not match; this receipt was not issued here",
            )

        actual = digest(evidence)
        if not hmac.compare_digest(actual, receipt.evidence_digest):
            event(
                logger,
                "receipt verification failed",
                module="receipt",
                outcome="rejected",
                failure_reason="evidence_changed",
            )
            return Verification(
                valid=False,
                reason="the stored evidence has changed since this receipt was issued",
            )

        return Verification(valid=True)

    def _sign(
        self,
        *,
        case_id: UUID,
        evidence_digest: str,
        action: str,
        rule_version: str,
        issued_at: datetime,
    ) -> str:
        """HMAC over every field a verifier is asked to trust.

        The action and rule version are inside the signature, not merely alongside
        it: a receipt whose verdict could be edited while the evidence digest stayed
        valid would attest to the wrong thing.
        """
        message = _FIELD.join(
            (
                self._version,
                str(case_id),
                evidence_digest,
                action,
                rule_version,
                issued_at.isoformat(),
            )
        )
        return hmac.new(self._key, message.encode("utf-8"), hashlib.sha256).hexdigest()


class ReceiptReader:
    """Loads a stored receipt and checks it against the evidence held now (M42).

    The check runs on every read rather than being cached. A receipt that verified
    yesterday and fails today is exactly the signal this endpoint exists to give, and
    a cached answer would suppress it.
    """

    def __init__(self, *, database: Any, signer: ReceiptSigner) -> None:
        self._database = database
        self._signer = signer

    async def verify(self, receipt_id: str) -> dict[str, Any] | None:
        """The receipt, plus the outcome of checking it. `None` if there is no such id."""
        from app.db.repositories import EvidenceRepository, ReceiptRepository

        async with self._database.connection() as conn:
            row = await ReceiptRepository(conn).by_id(receipt_id)
            if row is None:
                return None
            case_id = UUID(str(row["case_id"]))
            rows = await EvidenceRepository(conn).for_case(case_id)
        evidence = evidence_from_rows(rows)

        receipt = Receipt(
            id=str(row["id"]),
            case_id=case_id,
            evidence_digest=str(row["evidence_digest"]),
            signature=str(row["signature"]),
            issued_at=row["issued_at"],
            rule_version=str(row["rule_version"]),
            action=str(row["action"]),
            evidence_count=int(row["evidence_count"]),
            version=str(row["receipt_version"]),
        )
        outcome = self._signer.verify(receipt, evidence)

        event(
            logger,
            "receipt checked",
            module="receipt",
            outcome="ok" if outcome.valid else "degraded",
            valid=outcome.valid,
            evidence_count=len(evidence),
        )

        return self._payload(receipt, outcome)

    async def for_case(self, case_id: UUID) -> dict[str, Any] | None:
        """The case's latest receipt, checked now. `None` if none was issued.

        What a result carries inline (contract 1.3), so the app shows the seal
        without asking for the receipt separately. Checked on every read, as
        `verify` is, for the same reason.
        """
        from app.db.repositories import ReceiptRepository

        async with self._database.connection() as conn:
            row = await ReceiptRepository(conn).latest_for_case(case_id)
        if row is None:
            return None
        return await self.verify(str(row["id"]))

    @staticmethod
    def _payload(receipt: Receipt, outcome: Verification) -> dict[str, Any]:
        return {
            "receipt_id": receipt.id,
            "case_id": str(receipt.case_id),
            "evidence_digest": receipt.evidence_digest,
            "signature": receipt.signature,
            "issued_at": receipt.issued_at,
            "rule_version": receipt.rule_version,
            "action": receipt.action,
            "evidence_count": receipt.evidence_count,
            "receipt_version": receipt.version,
            "verified": outcome.valid,
            "verification_reason": outcome.reason or "signature and evidence digest match",
            "disclaimer": DISCLAIMER,
        }


def evidence_from_rows(rows: list[Any]) -> list[Evidence]:
    """Rebuild evidence objects from stored rows, for re-checking a receipt.

    The digest is computed over domain values, so verifying one later means
    reconstructing those values exactly. Every field `canonicalise` reads is restored
    here; a field it does not read is left at its default, because including more than
    the digest covers would make this look stricter than it is.
    """
    from app.domain.enums import Direction, EvidenceKind, MatchQuality, Method, Tier
    from app.domain.evidence import MatchBasis, SourceAnchor

    restored: list[Evidence] = []
    for row in rows:
        anchor = row["source_anchor"] or {}
        basis = row["match_basis"] or {}
        restored.append(
            Evidence(
                id=str(row["id"]),
                claim_id=str(row["claim_id"]),
                tier=Tier(row["tier"]),
                kind=EvidenceKind(row["kind"]),
                direction=Direction(row["direction"]),
                method=Method(row["method"]),
                finding=str(row["finding"]),
                citation_url=str(row["citation_url"]),
                snapshot_id=str(row["snapshot_id"]),
                source_excerpt=str(row["source_excerpt"]),
                source_anchor=SourceAnchor(**anchor) if anchor else SourceAnchor(),
                match_basis=MatchBasis(**basis),
                match_quality=MatchQuality(row["match_quality"]),
            )
        )
    return restored
