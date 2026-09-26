"""M40-M43 — the orchestrator, the contract, the receipt and the review queue.

Three gates are asserted here:

  - M40: a run with every optional provider disabled still produces a complete,
    honest, abstaining response.
  - M42: a receipt verifies, and altering any stored evidence row makes it fail.
  - M43: an abstaining case reaches the queue with its reason, and a human label is
    recorded beside the machine verdict rather than over it.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.api.schemas import (
    AdvisoryResponse,
    ClaimResponse,
    EvidenceResponse,
    StrengthResponse,
    VerifyRequest,
    VerifyResponse,
)
from app.cache.keys import CacheKeyParts
from app.domain.enums import Action, ClaimStatus, ClaimType, Direction, Importance, Severity
from app.intake.normalizer import normalise_text
from app.orchestration.pipeline import (
    Orchestrator,
    SkippedCheck,
    VerificationResult,
    _distinct_citations,
    abstained,
    cacheable,
)
from app.orchestration.receipt import (
    DISCLAIMER,
    ReceiptSigner,
    canonicalise,
    digest,
    parse_receipt,
)
from app.orchestration.review import HumanLabel, ReviewQueue, ReviewReason, reason_for
from app.sources.corpus import CorpusCorroboration, CorroborationSignal
from app.verdict.engine import CaseDecision, Decision
from app.verdict.strength import evidence_strength
from tests.unit import factories
from tests.unit.factories import claim, evidence

pytestmark = pytest.mark.unit


class NullCache:
    """A cache that never hits. The pipeline must work without one."""

    def __init__(self) -> None:
        self.probes = 0

    async def get_verdict(self, parts: Any) -> None:
        self.probes += 1
        return None


class RecordingGovernor:
    """Refuses everything, recording what was asked for."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def try_acquire(self, provider: str) -> Any:
        from app.governor.governor import Skip, SkipReason

        self.asked.append(provider)
        return Skip(provider=provider, reason=SkipReason.NOT_CONFIGURED)


def _claim(**overrides: Any):
    return factories.claim(**overrides)


def _result(**overrides: Any) -> VerificationResult:
    base: dict[str, Any] = {
        "case_id": uuid4(),
        "content_hash": "sha256:demo",
        "action": Action.SAFE_TO_SHARE,
        "case_decision": CaseDecision(action=Action.SAFE_TO_SHARE, rule_id="r", reason="because"),
    }
    base.update(overrides)
    return VerificationResult(**base)


# ------------------------------------------------------------------ M40 · pipeline


class TestTheDegradedRunGate:
    """M40's gate: everything disabled still produces a complete honest response."""

    @pytest.mark.anyio
    async def test_no_resolvers_produces_an_abstaining_response(self) -> None:
        cache = NullCache()
        orchestrator = Orchestrator(
            cache=cache,  # type: ignore[arg-type]
            governor=RecordingGovernor(),  # type: ignore[arg-type]
            resolvers=[],
            extractor_version="test",
        )

        intake = normalise_text("The government announced a relief scheme on Friday.")
        result = await orchestrator.verify(intake, case_id=uuid4(), claims=[_claim()])

        assert result.claims
        assert all(o.decision.status is ClaimStatus.UNVERIFIED for o in result.claims)
        assert result.evidence == []
        # Nothing was skipped: there was nothing configured to skip. The run is
        # complete and the answer is an honest abstention, which is the distinction
        # the gate is about.
        assert result.is_complete
        assert result.completeness_note() is None

    @pytest.mark.anyio
    async def test_the_cache_is_probed_before_any_provider(self) -> None:
        """M13's ordering, asserted at the pipeline level."""
        cache = NullCache()
        governor = RecordingGovernor()
        orchestrator = Orchestrator(
            cache=cache,  # type: ignore[arg-type]
            governor=governor,  # type: ignore[arg-type]
            resolvers=[],
            extractor_version="test",
        )

        await orchestrator.verify(normalise_text("some text"), case_id=uuid4(), claims=[])

        assert cache.probes == 1
        assert governor.asked == []

    @pytest.mark.anyio
    async def test_no_claims_still_returns_a_result(self) -> None:
        orchestrator = Orchestrator(
            cache=NullCache(),  # type: ignore[arg-type]
            governor=RecordingGovernor(),  # type: ignore[arg-type]
            resolvers=[],
            extractor_version="test",
        )

        result = await orchestrator.verify(
            normalise_text("nothing checkable here"), case_id=uuid4(), claims=[]
        )

        assert result.claims == []
        assert result.action is not None


class TestHonestyAboutGaps:
    def test_a_skipped_check_is_named_in_the_note(self) -> None:
        result = _result(skipped=[SkippedCheck(check="factcheck", reason="not configured")])

        assert not result.is_complete
        note = result.completeness_note()
        assert note is not None
        assert "factcheck" in note
        assert "not configured" in note

    def test_a_complete_run_has_no_note(self) -> None:
        assert _result().completeness_note() is None

    def test_an_incomplete_run_is_not_cached(self) -> None:
        """Caching one would freeze a provider outage into a 30-day stored verdict."""
        incomplete = _result(skipped=[SkippedCheck(check="x", reason="down")])
        complete = _result()

        assert not cacheable(incomplete)
        assert cacheable(complete)

    def test_a_cached_result_is_not_re_cached(self) -> None:
        assert not cacheable(_result(from_cache=True))


# ------------------------------------------------------------------- M42 · receipt


def _evidence(**overrides: Any):
    return factories.evidence(**overrides)


class TestTheReceiptGate:
    """M42's gate: a receipt verifies, and altered evidence makes it fail."""

    def test_a_receipt_verifies_against_its_own_evidence(self) -> None:
        signer = ReceiptSigner(key="development-key")
        evidence = [_evidence()]

        receipt = signer.issue(
            case_id=uuid4(), evidence=evidence, action="SAFE_TO_SHARE", rule_version="2026.08.1"
        )

        assert signer.verify(receipt, evidence).valid

    def test_altering_an_evidence_row_breaks_verification(self) -> None:
        signer = ReceiptSigner(key="development-key")
        original = [_evidence(source_excerpt="the minister said the scheme opens in September")]

        receipt = signer.issue(
            case_id=uuid4(), evidence=original, action="SAFE_TO_SHARE", rule_version="2026.08.1"
        )

        tampered = [_evidence(source_excerpt="the minister said the scheme was cancelled")]
        verification = signer.verify(receipt, tampered)

        assert not verification.valid
        assert verification.failed_because_evidence_changed
        assert "changed since" in verification.reason

    def test_altering_the_citation_url_breaks_verification(self) -> None:
        signer = ReceiptSigner(key="development-key")
        original = [_evidence(citation_url="https://real.example/story")]
        receipt = signer.issue(
            case_id=uuid4(), evidence=original, action="SAFE_TO_SHARE", rule_version="2026.08.1"
        )

        swapped = [_evidence(citation_url="https://attacker.example/story")]

        assert not signer.verify(receipt, swapped).valid

    def test_removing_an_evidence_row_breaks_verification(self) -> None:
        signer = ReceiptSigner(key="development-key")
        evidence = [_evidence(id="ev:1"), _evidence(id="ev:2")]
        receipt = signer.issue(
            case_id=uuid4(), evidence=evidence, action="SAFE_TO_SHARE", rule_version="2026.08.1"
        )

        assert not signer.verify(receipt, evidence[:1]).valid

    def test_a_receipt_from_another_key_does_not_verify(self) -> None:
        evidence = [_evidence()]
        issued = ReceiptSigner(key="key-one").issue(
            case_id=uuid4(), evidence=evidence, action="SAFE_TO_SHARE", rule_version="2026.08.1"
        )

        verification = ReceiptSigner(key="key-two").verify(issued, evidence)

        assert not verification.valid
        assert "not issued here" in verification.reason

    def test_editing_the_action_breaks_verification(self) -> None:
        """The verdict is inside the signature, not merely alongside it."""
        from dataclasses import replace

        signer = ReceiptSigner(key="development-key")
        evidence = [_evidence()]
        receipt = signer.issue(
            case_id=uuid4(), evidence=evidence, action="SAFE_TO_SHARE", rule_version="2026.08.1"
        )

        assert not signer.verify(replace(receipt, action="DO_NOT_SHARE"), evidence).valid


class TestReceiptConstruction:
    def test_the_digest_is_order_independent(self) -> None:
        """Two runs finding the same evidence in a different order must agree."""
        a, b = _evidence(id="ev:a"), _evidence(id="ev:b")

        assert digest([a, b]) == digest([b, a])

    def test_the_digest_changes_when_the_metric_changes(self) -> None:
        strong = _evidence(basis=factories.strong_basis())
        weak = _evidence(basis=factories.weak_basis())

        assert digest([strong]) != digest([weak])

    def test_canonicalisation_uses_delimiters_content_cannot_contain(self) -> None:
        """Otherwise an excerpt could be chosen to forge a colliding digest."""
        canonical = canonicalise([_evidence()])

        assert "\x1f" in canonical
        assert "\x1e" not in canonical  # only one record

    def test_an_empty_key_is_refused(self) -> None:
        with pytest.raises(ValueError, match="refusing to sign"):
            ReceiptSigner(key="")

    def test_the_identifier_is_content_addressed(self) -> None:
        signer = ReceiptSigner(key="k")
        case_id = uuid4()
        evidence = [_evidence()]

        first = signer.issue(
            case_id=case_id, evidence=evidence, action="SAFE_TO_SHARE", rule_version="v"
        )
        second = signer.issue(
            case_id=case_id, evidence=evidence, action="SAFE_TO_SHARE", rule_version="v"
        )

        assert first.id == second.id

    def test_the_payload_carries_the_disclaimer(self) -> None:
        """It must never be described as a legal certificate."""
        signer = ReceiptSigner(key="k")
        receipt = signer.issue(
            case_id=uuid4(), evidence=[_evidence()], action="SAFE_TO_SHARE", rule_version="v"
        )

        payload = receipt.to_payload()
        assert payload["disclaimer"] == DISCLAIMER
        assert "not a legal certificate" in str(payload["disclaimer"])
        assert "tamper-evident" in str(payload["disclaimer"])

    def test_a_receipt_round_trips_through_its_payload(self) -> None:
        signer = ReceiptSigner(key="k")
        evidence = [_evidence()]
        receipt = signer.issue(
            case_id=uuid4(), evidence=evidence, action="SAFE_TO_SHARE", rule_version="v"
        )

        assert signer.verify(parse_receipt(receipt.to_payload()), evidence).valid


# -------------------------------------------------------------------- M43 · review


class RecordingReviewRepository:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, Any]] = []
        self.labels: list[dict[str, Any]] = []

    async def enqueue(
        self, *, case_id: UUID, reason: str, machine_status: str | None = None
    ) -> UUID:
        item_id = uuid4()
        self.enqueued.append(
            {"id": item_id, "case_id": case_id, "reason": reason, "machine_status": machine_status}
        )
        return item_id

    async def record_human_label(
        self, *, item_id: UUID, human_label: str, reviewer: str, notes: str | None = None
    ) -> None:
        self.labels.append(
            {"item_id": item_id, "human_label": human_label, "reviewer": reviewer, "notes": notes}
        )

    async def pending(self, limit: int = 50) -> list[dict[str, Any]]:
        return [
            {
                **row,
                "created_at": datetime.now(UTC),
            }
            for row in self.enqueued[:limit]
        ]


class TestReviewRouting:
    def test_a_resolved_case_is_not_routed(self) -> None:
        assert reason_for(_result(action=Action.SAFE_TO_SHARE)) is None

    def test_an_incomplete_run_is_routed_as_incomplete(self) -> None:
        """Most actionable reason wins: a reviewer can re-run this one."""
        result = _result(
            action=Action.SEND_TO_REVIEW,
            skipped=[SkippedCheck(check="factcheck", reason="down")],
        )

        assert reason_for(result) is ReviewReason.INCOMPLETE_RUN

    def test_an_abstaining_case_is_routed_as_no_evidence(self) -> None:
        assert reason_for(_result(action=Action.SEND_TO_REVIEW)) is ReviewReason.NO_EVIDENCE

    @pytest.mark.anyio
    async def test_an_abstaining_case_reaches_the_queue_with_its_reason(self) -> None:
        repository = RecordingReviewRepository()
        queue = ReviewQueue(repository=repository)  # type: ignore[arg-type]

        item_id = await queue.route(_result(action=Action.SEND_TO_REVIEW))

        assert item_id is not None
        assert repository.enqueued[0]["reason"] == ReviewReason.NO_EVIDENCE.value

    @pytest.mark.anyio
    async def test_a_resolved_case_is_not_enqueued(self) -> None:
        repository = RecordingReviewRepository()
        queue = ReviewQueue(repository=repository)  # type: ignore[arg-type]

        assert await queue.route(_result(action=Action.SAFE_TO_SHARE)) is None
        assert repository.enqueued == []

    @pytest.mark.anyio
    async def test_a_human_label_never_touches_the_machine_status(self) -> None:
        """M43's rule. The repository has no path that writes machine_status."""
        repository = RecordingReviewRepository()
        queue = ReviewQueue(repository=repository)  # type: ignore[arg-type]

        item_id = await queue.route(_result(action=Action.SEND_TO_REVIEW))
        assert item_id is not None
        before = dict(repository.enqueued[0])

        await queue.record(item_id=item_id, label=HumanLabel.CONTRADICTED, reviewer="asha")

        assert repository.enqueued[0] == before
        assert repository.labels[0]["human_label"] == "CONTRADICTED"
        assert repository.labels[0]["reviewer"] == "asha"

    @pytest.mark.anyio
    async def test_an_anonymous_review_is_refused(self) -> None:
        queue = ReviewQueue(repository=RecordingReviewRepository())  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="unaccountable"):
            await queue.record(item_id=uuid4(), label=HumanLabel.SUPPORTED, reviewer="")

    def test_every_reason_has_reviewer_context(self) -> None:
        from app.orchestration.review import QueuedCase

        for reason in ReviewReason:
            case = QueuedCase(
                item_id=uuid4(),
                case_id=uuid4(),
                reason=reason,
                machine_status=None,
                created_at=datetime.now(UTC),
            )
            assert case.context


class TestReviewedCase:
    def _reviewed(self, machine: str | None, human: HumanLabel):
        from app.orchestration.review import ReviewedCase

        return ReviewedCase(
            item_id=uuid4(),
            case_id=uuid4(),
            machine_status=machine,
            human_label=human,
            reviewer="asha",
            reviewed_at=datetime.now(UTC),
        )

    def test_disagreement_is_visible(self) -> None:
        assert self._reviewed("UNVERIFIED", HumanLabel.CONTRADICTED).disagrees
        assert not self._reviewed("CONTRADICTED", HumanLabel.CONTRADICTED).disagrees

    def test_only_decisive_labels_are_promotable(self) -> None:
        """Confirming 'still unverified' is a record, not a new fact about the world."""
        assert self._reviewed(None, HumanLabel.CONTRADICTED).is_promotable
        assert not self._reviewed(None, HumanLabel.UNVERIFIED).is_promotable
        assert not self._reviewed(None, HumanLabel.OUT_OF_SCOPE).is_promotable


# ------------------------------------------------------------------ M41 · contract


class TestTheContract:
    def test_a_request_must_carry_exactly_one_input(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            VerifyRequest(url="https://a.example", text="also this")
        with pytest.raises(ValueError, match="exactly one"):
            VerifyRequest()

        assert VerifyRequest(url="https://a.example").url
        assert VerifyRequest(text="a claim").text

    def test_a_decisive_claim_without_evidence_cannot_be_serialised(self) -> None:
        """The contract half of the ledger-completeness invariant."""
        with pytest.raises(ValueError, match="must never emit"):
            ClaimResponse(
                id="c1",
                text="a claim",
                claim_type=ClaimType.EVENT,
                status=ClaimStatus.CONTRADICTED,
                severity=Severity.HIGH,
                importance=Importance.HEADLINE,
                reason="because",
                rule_id="r",
                rule_version="v",
                strength=StrengthResponse(score=0.9, band="STRONG", version="v"),
                evidence=(),
            )

    def test_an_unverified_claim_without_evidence_is_fine(self) -> None:
        """Abstention is the designed answer and must serialise cleanly."""
        response = ClaimResponse(
            id="c1",
            text="a claim",
            claim_type=ClaimType.EVENT,
            status=ClaimStatus.UNVERIFIED,
            severity=Severity.HIGH,
            importance=Importance.HEADLINE,
            reason="No citable evidence was found.",
            rule_id="r",
            rule_version="v",
            strength=StrengthResponse(score=0.0, band="NONE", version="v"),
        )

        assert response.evidence == ()

    def test_an_advisory_cannot_be_placed_in_the_evidence_list(self) -> None:
        """Different models, no shared base — the isolation is structural."""
        advisory = AdvisoryResponse(
            id="adv:1", provider="local", signal="ADVISORY_SUSPICION", note="a signal"
        )

        assert not isinstance(advisory, EvidenceResponse)
        assert "evidence" not in AdvisoryResponse.model_fields

    def test_every_advisory_carries_its_exclusion_note(self) -> None:
        advisory = AdvisoryResponse(
            id="adv:1", provider="local", signal="NO_SIGNAL", note="a signal"
        )

        assert "not used in this verdict" in advisory.excluded_note

    def test_the_response_requires_a_retrieval_time(self) -> None:
        with pytest.raises(ValueError):
            VerifyResponse(
                case_id="c",
                action=Action.SAFE_TO_SHARE,
                action_reason="because",
                rule_version="v",
            )  # type: ignore[call-arg]

    def test_the_response_separates_advisories_from_evidence(self) -> None:
        response = VerifyResponse(
            case_id="c",
            action=Action.SAFE_TO_SHARE,
            action_reason="because",
            rule_version="v",
            retrieved_at=datetime.now(UTC),
            advisories=(
                AdvisoryResponse(id="adv:1", provider="local", signal="NO_SIGNAL", note="a signal"),
            ),
        )

        assert response.advisories
        assert all(not claim.evidence for claim in response.claims)


class TestAbstentionHelpers:
    def test_a_review_action_counts_as_abstained(self) -> None:
        assert abstained(_result(action=Action.SEND_TO_REVIEW))

    def test_an_informing_case_with_evidence_is_not_abstained(self) -> None:
        from app.orchestration.pipeline import ClaimOutcome

        claim = _claim()
        evidence = [factories.evidence(claim_id=claim.id)]
        outcome = ClaimOutcome(
            claim=claim,
            decision=Decision(
                status=ClaimStatus.SUPPORTED,
                rule_id="r",
                reason="because",
                supporting_evidence_ids=(evidence[0].id,),
            ),
            strength=evidence_strength(evidence),
            evidence=evidence,
        )

        assert not abstained(_result(action=Action.SAFE_TO_SHARE, claims=[outcome]))


class TestTheHttpSurface:
    """M41: the contract a client is built against, exercised through the app."""

    @staticmethod
    def _client():
        from fastapi.testclient import TestClient

        from app.main import create_app

        return TestClient(create_app())

    def test_the_full_endpoint_set_is_published(self) -> None:
        """Frozen means complete. A client cannot be built against a partial one."""
        spec = self._client().get("/openapi.json").json()

        assert set(spec["paths"]) >= {
            "/healthz",
            "/v1/verify",
            "/v1/verify/file",
            "/v1/cases/{case_id}",
            "/v1/cases/{case_id}/evidence",
            "/v1/receipts/{receipt_id}",
        }

    def test_the_internal_trigger_is_not_in_the_published_contract(self) -> None:
        spec = self._client().get("/openapi.json").json()

        assert not any("internal" in path for path in spec["paths"])

    def test_an_unauthenticated_trigger_gets_404_not_401(self) -> None:
        """Confirming the path exists is information an unauthenticated caller has
        no use for."""
        assert self._client().post("/internal/ingest-tick").status_code == 404

    def test_a_wrong_secret_is_also_404(self) -> None:
        response = self._client().post(
            "/internal/ingest-tick", headers={"x-factify-trigger": "guessed"}
        )
        assert response.status_code == 404

    def test_a_malformed_body_is_422_not_503(self) -> None:
        """A dependency raising 503 before validation would tell a client the service
        was down when the request was its own fault."""
        client = self._client()

        assert client.post("/v1/verify", json={}).status_code == 422
        assert (
            client.post("/v1/verify", json={"text": "a", "url": "https://x.example"}).status_code
            == 422
        )
        assert client.post("/v1/verify", json={"text": "a", "bogus": 1}).status_code == 422

    def test_a_valid_body_reaches_the_pipeline(self) -> None:
        """503 here means the request was fine and nothing is wired — which is the
        correct answer for an unconfigured service."""
        assert self._client().post("/v1/verify", json={"text": "a claim"}).status_code == 503

    def test_the_openapi_description_states_the_design_law(self) -> None:
        spec = self._client().get("/openapi.json").json()
        description = spec["info"]["description"]

        assert "UNVERIFIED" in description
        assert "never inside" in description


class TestTriggerAuthentication:
    """M24's shared secret. A security boundary, so both directions are asserted.

    The wrong-shape case is here because it really happened: `Settings` holds a
    `SecretStr`, `hmac.compare_digest` raises `TypeError` on one, and the endpoint
    returned 500 with a stack trace instead of denying. mypy could not catch it
    because `request.app.state` is `Any`.
    """

    def test_the_correct_secret_authenticates(self) -> None:
        from pydantic import SecretStr

        from app.knowledge.registry import authenticate_trigger

        assert authenticate_trigger("s3cret", SecretStr("s3cret"))
        assert authenticate_trigger("s3cret", "s3cret")

    def test_a_wrong_secret_denies_rather_than_raising(self) -> None:
        from pydantic import SecretStr

        from app.knowledge.registry import authenticate_trigger

        assert not authenticate_trigger("guessed", SecretStr("s3cret"))
        assert not authenticate_trigger("guessed", "s3cret")

    def test_an_unconfigured_deployment_denies_everything(self) -> None:
        from app.knowledge.registry import authenticate_trigger

        assert not authenticate_trigger("anything", None)
        assert not authenticate_trigger("anything", "")
        assert not authenticate_trigger(None, "s3cret")

    def test_a_non_ascii_secret_does_not_raise(self) -> None:
        from pydantic import SecretStr

        from app.knowledge.registry import authenticate_trigger

        assert authenticate_trigger("गुप्त", SecretStr("गुप्त"))
        assert not authenticate_trigger("गुप्त", SecretStr("other"))


class RecordingCache:
    """Misses on read, records what write-back stores."""

    def __init__(self) -> None:
        self.written: dict[str, Any] | None = None
        self.written_negative: bool | None = None

    async def get_verdict(self, parts: Any) -> None:
        return None

    async def put_verdict(
        self,
        parts: Any,
        payload: dict[str, Any],
        *,
        case_id: Any = None,
        is_negative: bool = False,
        developing: bool = False,
    ) -> None:
        self.written = payload
        self.written_negative = is_negative


class HittingCache:
    """Serves one stored payload, the way a warm cache row would."""

    def __init__(self, payload: dict[str, Any]) -> None:
        from datetime import UTC, datetime

        from app.cache.service import CachedVerdict

        self._cached = CachedVerdict(
            payload=payload,
            retrieved_at=datetime.now(UTC),
            rule_version="test",
            is_negative=False,
        )

    async def get_verdict(self, parts: Any) -> Any:
        return self._cached

    async def put_verdict(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("a hit must not be re-written")


class TestCacheRoundTrip:
    """M13 write-back: what the payload stores, and what a hit rebuilds.

    The write existed for one day with two silent failure modes — no caller, then a
    foreign-key violation — so this class pins the contract: a complete run stores
    the action, the rollup reason and the original case id; a hit carries all three
    back out; and rows written before the fields existed still serve.
    """

    @pytest.mark.anyio
    async def test_a_complete_run_writes_action_reason_and_case_id(self) -> None:
        cache = RecordingCache()
        orchestrator = Orchestrator(
            cache=cache,  # type: ignore[arg-type]
            governor=RecordingGovernor(),  # type: ignore[arg-type]
            resolvers=[],
            extractor_version="test",
        )

        case_id = uuid4()
        intake = normalise_text("The government announced a relief scheme on Friday.")
        result = await orchestrator.verify(intake, case_id=case_id, claims=[_claim()])

        assert cache.written is not None
        assert cache.written["action"] == result.action.value
        assert cache.written["action_reason"] == result.case_decision.reason
        # The id under which the ledger will record this run — the payload copy is
        # what lets a later hit serve the full stored case instead of a bare action.
        assert cache.written["case_id"] == str(case_id)
        # An abstention is cached with the shorter negative TTL.
        assert cache.written_negative is (result.action is Action.SEND_TO_REVIEW)

    @pytest.mark.anyio
    async def test_a_run_with_no_claims_writes_nothing(self) -> None:
        """An empty run is not an answer, and caching it would serve the emptiness."""
        cache = RecordingCache()
        orchestrator = Orchestrator(
            cache=cache,  # type: ignore[arg-type]
            governor=RecordingGovernor(),  # type: ignore[arg-type]
            resolvers=[],
            extractor_version="test",
        )

        intake = normalise_text("The government announced a relief scheme on Friday.")
        await orchestrator.verify(intake, case_id=uuid4(), claims=[])

        assert cache.written is None

    @pytest.mark.anyio
    async def test_a_hit_carries_the_source_case_and_the_original_reason(self) -> None:
        original = uuid4()
        orchestrator = Orchestrator(
            cache=HittingCache(  # type: ignore[arg-type]
                {
                    "action": "SEND_TO_REVIEW",
                    "action_reason": "Not enough citable evidence to decide.",
                    "case_id": str(original),
                }
            ),
            governor=RecordingGovernor(),  # type: ignore[arg-type]
            resolvers=[],
            extractor_version="test",
        )

        intake = normalise_text("The government announced a relief scheme on Friday.")
        result = await orchestrator.verify(intake, case_id=uuid4(), claims=[])

        assert result.from_cache
        assert result.source_case_id == original
        assert result.case_decision.reason == "Not enough citable evidence to decide."

    @pytest.mark.anyio
    async def test_a_legacy_action_only_row_still_serves(self) -> None:
        """Rows written before the payload carried a case id parse to a thin hit,
        which is exactly what they hold — never an error, never a fabricated id."""
        orchestrator = Orchestrator(
            cache=HittingCache({"action": "SAFE_TO_SHARE"}),  # type: ignore[arg-type]
            governor=RecordingGovernor(),  # type: ignore[arg-type]
            resolvers=[],
            extractor_version="test",
        )

        intake = normalise_text("The government announced a relief scheme on Friday.")
        result = await orchestrator.verify(intake, case_id=uuid4(), claims=[])

        assert result.from_cache
        assert result.source_case_id is None
        assert result.action is Action.SAFE_TO_SHARE


# ------------------------------------------------------------ call economy


class _StubResolver:
    """A resolver that yields one citation per claim — or none — and records calls."""

    name = "stub"
    version = "v"
    allowed_domains: frozenset[str] = frozenset()

    def __init__(
        self,
        *,
        name: str,
        tier: Any,
        kind: Any,
        method: Any,
        relation: Any | None,
        fallback: bool = False,
    ) -> None:
        self.name = name
        self.tier = tier
        self.kind = kind
        self.method = method
        self.fallback = fallback
        self._relation = relation
        self.asked: list[str] = []

    async def candidates(self, claim: Any) -> list[Any]:
        from app.sources.base import SourceCandidate

        self.asked.append(claim.id)
        if self._relation is None:
            return []
        return [SourceCandidate(url=f"https://{self.name}.example/{claim.id}", publisher=self.name)]

    async def snapshot(self, candidate: Any) -> Any:
        from app.sources.base import SourceSnapshot

        return SourceSnapshot(
            id=f"snap:{candidate.url}",
            url=candidate.url,
            final_url=candidate.url,
            content_hash=f"sha256:{candidate.url}",
            fetched_at=datetime.now(UTC),
            text="A published fact-check rated this claim false.",
        )

    async def relate(self, claim: Any, snapshot: Any) -> Any:
        from app.sources.base import SourceRelation

        return SourceRelation(
            relation=self._relation,
            validator=self.name,
            validator_version="v",
            excerpt="rated this claim false",
            anchor={"char_start": 20, "char_end": 42},
            metric="claim_similarity",
            value=0.9,
            threshold=0.62,
        )


def _fact_check(relation: Any | None) -> _StubResolver:
    from app.domain.enums import EvidenceKind, Method, Tier

    return _StubResolver(
        name="factcheck",
        tier=Tier.C,
        kind=EvidenceKind.FACT_CHECK,
        method=Method.CLAIM_REVIEW,
        relation=relation,
    )


def _web_search() -> _StubResolver:
    from app.domain.enums import EvidenceKind, Method, Relation, Tier

    return _StubResolver(
        name="web_search",
        tier=Tier.D,
        kind=EvidenceKind.CORROBORATION,
        method=Method.SEARCH_SNIPPET,
        relation=Relation.CONTRADICTS,
        fallback=True,
    )


def _economy_orchestrator(resolvers: list[Any]) -> Orchestrator:
    return Orchestrator(
        cache=NullCache(),  # type: ignore[arg-type]
        governor=RecordingGovernor(),  # type: ignore[arg-type]
        resolvers=resolvers,
        extractor_version="test",
    )


class TestTheFallbackStage:
    """The costly open-web resolver runs only when the cheap evidence cannot decide."""

    @pytest.mark.anyio
    async def test_a_published_contradiction_means_the_web_is_never_searched(self) -> None:
        from app.domain.enums import Relation

        fact_check, web = _fact_check(Relation.CONTRADICTS), _web_search()
        intake = normalise_text("Drinking bleach cures COVID-19.")

        result = await _economy_orchestrator([fact_check, web]).verify(
            intake, case_id=uuid4(), claims=[_claim()]
        )

        assert result.claims[0].decision.status.is_decisive
        assert fact_check.asked == ["cl_1"]
        assert web.asked == []  # no search call, no model reads

    @pytest.mark.anyio
    async def test_the_web_is_searched_when_nothing_cheaper_decided(self) -> None:
        fact_check, web = _fact_check(None), _web_search()
        intake = normalise_text("A claim no fact-checker has covered.")

        result = await _economy_orchestrator([fact_check, web]).verify(
            intake, case_id=uuid4(), claims=[_claim()]
        )

        assert web.asked == ["cl_1"]
        # and what it found is part of the decision, like any other citation
        assert any(e.kind.value == "corroboration" for e in result.evidence)

    @pytest.mark.anyio
    async def test_only_the_most_important_claims_reach_the_web(self) -> None:
        from app.orchestration.pipeline import MAX_FALLBACK_CLAIMS

        web = _web_search()
        claims = [
            _claim(claim_id="background", importance=Importance.BACKGROUND),
            _claim(claim_id="detail_1", importance=Importance.SUPPORTING_DETAIL),
            _claim(claim_id="headline", importance=Importance.HEADLINE),
            _claim(claim_id="detail_2", importance=Importance.SUPPORTING_DETAIL),
            _claim(claim_id="thesis", importance=Importance.MAIN_THESIS),
        ]

        await _economy_orchestrator([_fact_check(None), web]).verify(
            normalise_text("A long article with five claims."), case_id=uuid4(), claims=claims
        )

        assert len(web.asked) == MAX_FALLBACK_CLAIMS == 3
        # the top three by importance; the tie between details keeps extraction order
        assert set(web.asked) == {"headline", "thesis", "detail_1"}


class TestTheCacheIsAskedFirst:
    """A repeat is answered before extraction or media work is paid for."""

    @pytest.mark.anyio
    async def test_cached_is_none_on_a_miss(self) -> None:
        orchestrator = _economy_orchestrator([])

        assert await orchestrator.cached(normalise_text("new text"), case_id=uuid4()) is None

    @pytest.mark.anyio
    async def test_cached_serves_a_stored_verdict(self) -> None:
        orchestrator = Orchestrator(
            cache=HittingCache({"action": "DO_NOT_SHARE"}),  # type: ignore[arg-type]
            governor=RecordingGovernor(),  # type: ignore[arg-type]
            resolvers=[],
            extractor_version="test",
        )

        hit = await orchestrator.cached(normalise_text("a viral forward"), case_id=uuid4())

        assert hit is not None and hit.from_cache
        assert hit.action is Action.DO_NOT_SHARE

    def test_a_repeat_check_never_calls_the_extractor(self) -> None:
        from fastapi.testclient import TestClient

        from app.main import create_app

        class CachedOrchestrator:
            async def cached(self, intake: Any, *, case_id: UUID) -> VerificationResult:
                return _result(case_id=case_id, from_cache=True)

            async def verify(self, *args: Any, **kwargs: Any) -> VerificationResult:
                raise AssertionError("a cache hit must not run the pipeline")

        class ExplodingPipeline:
            async def extract(self, *args: Any, **kwargs: Any) -> Any:
                raise AssertionError("a cache hit must not pay for extraction")

        app = create_app()
        app.state.orchestrator = CachedOrchestrator()
        app.state.claim_pipeline = ExplodingPipeline()

        response = TestClient(app).post("/v1/verify", json={"text": "A repeated viral forward."})

        assert response.status_code == 200
        assert response.json()["from_cache"] is True


class TestCountingOriginsBeyondTheCorpus:
    """Rule 4 asks for independent origins, and the count has to see all of them.

    A claim carried by the BBC, Wikipedia, the Press Information Bureau and Cornell
    came back as "1 distinct origin across 4 documents" and abstained under
    `rule.insufficient_origins`. `count_origins` reads stored minhash signatures, so
    it can only speak for citations that matched a corpus row — and nothing found on
    the open web ever does.
    """

    @staticmethod
    def _signal(rows: list[dict[str, object]], urls: list[str]) -> CorroborationSignal:
        class _Corpus:
            async def _rows_for(self, _urls: list[str]) -> list[dict[str, object]]:
                return rows

            async def _corpus_size(self) -> int:
                return 2064

        corroboration = CorpusCorroboration.__new__(CorpusCorroboration)
        corroboration._rows_for = _Corpus()._rows_for  # type: ignore[method-assign]
        corroboration._corpus_size = _Corpus()._corpus_size  # type: ignore[method-assign]
        return asyncio.run(corroboration.signal(claim(), citation_urls=urls))

    def test_four_publishers_the_corpus_has_never_seen_are_four_origins(self) -> None:
        signal = self._signal(
            [],
            [
                "https://www.bbc.com/news/world-asia-india-1",
                "https://en.wikipedia.org/wiki/Unified_Payments_Interface",
                "https://pib.gov.in/PressRelease.aspx?PRID=1",
                "https://business.cornell.edu/article/upi",
            ],
        )

        assert signal.independent_origin_count == 4

    def test_two_pages_from_one_outlet_are_one_origin(self) -> None:
        """Counted by publisher, not by URL: one masthead twice is one origin."""
        signal = self._signal(
            [],
            [
                "https://indianexpress.com/article/one",
                "https://indianexpress.com/article/two",
            ],
        )

        assert signal.independent_origin_count == 1

    def test_a_publisher_already_counted_in_the_corpus_is_not_counted_twice(self) -> None:
        signal = self._signal(
            [{"id": "1", "canonical_url": "https://www.bbc.com/news/a", "minhash_signature": None}],
            ["https://www.bbc.com/news/a", "https://www.bbc.com/news/b"],
        )

        assert signal.independent_origin_count == 1


class TestSyndicationIsNotIndependence:
    """Twenty outlets running one wire story are one origin, however many mastheads.

    The corpus settles this with stored signatures. A page from the open web has
    none, so the verified quote stands in for one: two citations whose excerpt is the
    same text are the same reporting.
    """

    def test_the_same_quote_from_two_outlets_is_counted_once(self) -> None:
        wire = (
            "The Reserve Bank of India said on Tuesday that the new rules would take "
            "effect from the first of next month, and that banks had been informed of "
            "the change in a circular issued earlier this year."
        )
        citations = _distinct_citations(
            [
                evidence(
                    direction=Direction.SUPPORTS,
                    citation_url="https://timesofindia.indiatimes.com/a",
                    source_excerpt=wire,
                ),
                evidence(
                    direction=Direction.SUPPORTS,
                    citation_url="https://www.deccanherald.com/b",
                    source_excerpt=wire,
                ),
            ]
        )

        assert len(citations) == 1

    def test_different_reporting_from_two_outlets_is_counted_twice(self) -> None:
        citations = _distinct_citations(
            [
                evidence(
                    direction=Direction.SUPPORTS,
                    citation_url="https://timesofindia.indiatimes.com/a",
                    source_excerpt="The central bank confirmed the change in a circular. " * 3,
                ),
                evidence(
                    direction=Direction.SUPPORTS,
                    citation_url="https://www.deccanherald.com/b",
                    source_excerpt="Branch managers described a rush of customers. " * 3,
                ),
            ]
        )

        assert len(citations) == 2

    def test_a_short_quote_never_merges_two_sources(self) -> None:
        """Below the length where identical text means anything, keep both."""
        citations = _distinct_citations(
            [
                evidence(
                    direction=Direction.SUPPORTS,
                    citation_url="https://www.bbc.com/a",
                    source_excerpt="It landed near the south pole.",
                ),
                evidence(
                    direction=Direction.SUPPORTS,
                    citation_url="https://www.nasa.gov/b",
                    source_excerpt="It landed near the south pole.",
                ),
            ]
        )

        assert len(citations) == 2

    def test_contradicting_evidence_is_not_counted_at_all(self) -> None:
        """Only supporting citations corroborate; contradiction has its own rule."""
        assert (
            _distinct_citations(
                [evidence(direction=Direction.CONTRADICTS, citation_url="https://www.bbc.com/a")]
            )
            == set()
        )


class TestAGapIsReportedNotAbsorbed:
    """ "We could not ask" and "nobody has checked this" are different answers.

    The fact-check resolver returned an empty candidate list when the governor
    refused it, which made the two identical: the run counted as complete, so
    `cacheable` stored an abstention caused by an exhausted daily budget and served
    it for thirty days as though it were the finding. Observed live — a morning of
    testing exhausted a 100-call budget and five claims a fact-checker had already
    settled came back as review.
    """

    @staticmethod
    def _result(*skipped: SkippedCheck) -> VerificationResult:
        return VerificationResult(
            case_id=uuid4(),
            content_hash="sha256:abc",
            action=Action.SEND_TO_REVIEW,
            case_decision=CaseDecision(action=Action.SEND_TO_REVIEW, reason="r", rule_id="rule.x"),
            skipped=list(skipped),
        )

    def test_a_run_missing_a_check_is_not_written_to_the_cache(self) -> None:
        starved = self._result(SkippedCheck(check="factcheck", reason="capacity limited"))

        assert not cacheable(starved)

    def test_a_complete_run_still_is(self) -> None:
        assert cacheable(self._result())

    def test_the_reason_survives_into_the_response(self) -> None:
        """ "capacity limited" tells a reader the budget ran out; the exception's name
        would only say something went wrong."""
        starved = self._result(SkippedCheck(check="factcheck", reason="capacity limited"))

        assert starved.skipped[0].describe() == "factcheck was not checked: capacity limited"


class TestStrengthCountsTheEvidenceThatCarriesTheVerdict:
    """A contradicted claim's strength must describe its contradictors.

    `_count_origins` counts supporting citations only, and rightly: rule 4 asks
    whether enough independent outlets *carry* a claim, and a source that refutes it
    is not corroboration for it. Strength was handed that same supporting-only count,
    so every contradicted claim reported "0 distinct origin(s) across 0 document(s)"
    — on the same evidence card that said "3 independent sources contradict this
    claim: dw.com, jansatta.com, ndtv.com". One set of citations, two statements
    about it, visibly disagreeing on the screen built to explain the verdict.

    It cost the score as well as the explanation: a quarter of the weight sat on a
    component measuring the wrong direction, so a well-sourced debunk scored 0.36.
    """

    @staticmethod
    def _resolver(name: str) -> Any:
        from app.domain.enums import EvidenceKind, Method, Relation, Tier

        return _StubResolver(
            name=name,
            tier=Tier.C,
            kind=EvidenceKind.FACT_CHECK,
            method=Method.CLAIM_REVIEW,
            relation=Relation.CONTRADICTS,
        )

    @pytest.mark.anyio
    async def test_a_contradicted_claim_counts_the_sources_that_contradict_it(self) -> None:
        asked: list[list[str]] = []

        class _Corroboration:
            async def signal(self, _claim: Any, *, citation_urls: list[str]) -> Any:
                asked.append(sorted(citation_urls))
                return CorroborationSignal(
                    document_count=len(citation_urls),
                    independent_origin_count=len(citation_urls),
                    corpus_size=2064,
                )

        orchestrator = Orchestrator(
            cache=NullCache(),  # type: ignore[arg-type]
            governor=RecordingGovernor(),  # type: ignore[arg-type]
            resolvers=[self._resolver("alpha"), self._resolver("beta")],
            corroboration=_Corroboration(),  # type: ignore[arg-type]
            extractor_version="test",
        )

        result = await orchestrator.verify(
            normalise_text("A claim two outlets have debunked."),
            case_id=uuid4(),
            claims=[_claim()],
        )

        outcome = result.claims[0]
        assert outcome.decision.status is ClaimStatus.CONTRADICTED

        origins = next(c for c in outcome.strength.components if c.name == "independent_origins")
        assert origins.value > 0, "the contradictors were not counted"
        assert origins.detail == "2 distinct origin(s) across 2 document(s)"

        # The count was taken over the contradicting citations, which is the whole
        # point: asking about the supporting ones would have returned an empty set
        # and the component would read zero again.
        assert asked == [["https://alpha.example/cl_1", "https://beta.example/cl_1"]], (
            "corroboration was asked about the wrong citations"
        )

    @pytest.mark.anyio
    async def test_the_decision_still_sees_only_supporting_origins(self) -> None:
        """Rule 4 must not start accepting contradictors as corroboration."""

        class _Corroboration:
            async def signal(self, _claim: Any, *, citation_urls: list[str]) -> Any:
                return CorroborationSignal(
                    document_count=len(citation_urls),
                    independent_origin_count=len(citation_urls),
                    corpus_size=2064,
                )

        orchestrator = Orchestrator(
            cache=NullCache(),  # type: ignore[arg-type]
            governor=RecordingGovernor(),  # type: ignore[arg-type]
            resolvers=[self._resolver("alpha"), self._resolver("beta")],
            corroboration=_Corroboration(),  # type: ignore[arg-type]
            extractor_version="test",
        )

        result = await orchestrator.verify(
            normalise_text("A claim two outlets have debunked."),
            case_id=uuid4(),
            claims=[_claim()],
        )

        # The claim the engine decided on carries no corroboration count: nothing
        # supported it, and two refutations do not add up to support.
        assert result.claims[0].claim.independent_origin_count == 0


class TestRetrievalChangesRetireTheCache:
    """A change to what sources are gathered must not be served from the old answer.

    Fanning the web search across the claim's own questions, and capping what a
    search snippet may conclude, both changed the evidence a claim gathers. Neither
    was in the cache key, so every repeat returned the verdict built from the
    narrower search in four tenths of a second — indistinguishable, from the
    outside, from a change that did nothing.
    """

    @staticmethod
    def _parts(**overrides: Any) -> CacheKeyParts:
        base = {
            "content_hash": "sha256:abc",
            "rule_version": "2026.09.9",
            "extractor_version": "2026.09.2",
            "reader_version": "2026.09.8",
            "retrieval_version": "web_search:2026.09.4",
        }
        return CacheKeyParts(**{**base, **overrides})

    def test_a_bumped_resolver_misses_the_old_entry(self) -> None:
        assert (
            self._parts().derive() != self._parts(retrieval_version="web_search:2026.09.5").derive()
        )

    def test_a_new_resolver_misses_it_too(self) -> None:
        """Adding a source of evidence changes what a claim can be answered on."""
        assert (
            self._parts().derive()
            != self._parts(retrieval_version="corpus:2026.08.1,web_search:2026.09.4").derive()
        )

    def test_the_same_setup_still_hits(self) -> None:
        """The point is to retire stale answers, not to stop caching."""
        assert self._parts().derive() == self._parts().derive()


class TestOneSlowPageDoesNotLoseTheRest:
    """The deadline cuts off the pages still being read, not the ones already read.

    It used to wrap the whole resolver. "India won the ICC Men's T20 World Cup in
    2024" was read from three outlets, all answered, and came back with no sources
    because a fourth page's fetch hung and the timeout cancelled everything.
    """

    class _ThreePages:
        name = "web_search"

        async def candidates(self, _: Any) -> list[str]:
            return ["fast-1", "fast-2", "hangs"]

    @pytest.mark.anyio
    async def test_what_was_read_is_kept_and_the_straggler_is_reported(self) -> None:
        import time

        orchestrator = Orchestrator(
            cache=NullCache(),  # type: ignore[arg-type]
            governor=RecordingGovernor(),  # type: ignore[arg-type]
            resolvers=[],
            extractor_version="test",
        )
        cancelled: list[str] = []

        async def _resolve(_resolver: Any, _claim: Any, candidate: str) -> Any:
            if candidate == "hangs":
                try:
                    await asyncio.sleep(30)
                except asyncio.CancelledError:
                    cancelled.append(candidate)
                    raise
            return evidence(citation_url=f"https://example.org/{candidate}")

        orchestrator._resolve_candidate = _resolve  # type: ignore[method-assign]

        found, skip, read = await orchestrator._run_resolver(
            self._ThreePages(),  # type: ignore[arg-type]
            claim(),
            read_by=time.perf_counter() + 0.2,
        )

        assert sorted(e.citation_url for e in found) == [
            "https://example.org/fast-1",
            "https://example.org/fast-2",
        ]
        assert skip == "1 of 3 sources not read before the deadline"
        assert read == 2
        # Abandoned, not left running past the request that asked for it.
        assert cancelled == ["hangs"]


class TestASubmittedPageIsNotItsOwnEvidence:
    """A Times of India report was the only "source" for its own headline claim."""

    def test_the_submitted_page_is_removed_however_the_address_is_written(self) -> None:
        from app.orchestration.pipeline import _not_own
        from app.sources.verification import page_key

        own = frozenset({page_key("https://timesofindia.indiatimes.com/sports/x/134497880.cms")})
        itself = evidence(
            citation_url="http://www.timesofindia.indiatimes.com/sports/x/134497880.cms/"
        )
        other = evidence(citation_url="https://www.thehindu.com/sport/y.ece")

        assert _not_own([itself, other], own) == [other]

    def test_nothing_is_removed_when_nothing_was_submitted(self) -> None:
        from app.orchestration.pipeline import _not_own

        items = [evidence(citation_url="https://a.com/1")]

        assert _not_own(items, frozenset()) == items


class TestCheckAgainIsAFreshCheck:
    """ "Check again" replaces the stored answer; serving it back would do nothing."""

    @pytest.mark.anyio
    async def test_a_fresh_check_skips_the_stored_verdict(self) -> None:
        orchestrator = Orchestrator(
            cache=HittingCache({"action": "SEND_TO_REVIEW"}),  # type: ignore[arg-type]
            governor=RecordingGovernor(),  # type: ignore[arg-type]
            resolvers=[],
            extractor_version="test",
        )
        intake = normalise_text("The government announced a relief scheme on Friday.")

        stored = await orchestrator.verify(intake, case_id=uuid4(), claims=[])
        fresh = await orchestrator.verify(intake, case_id=uuid4(), claims=[], fresh=True)

        assert stored.from_cache
        assert not fresh.from_cache


class TestEveryClaimSaysWhetherItWasSearched:
    """An unconfirmed claim that was never searched read "we couldn't find sources".

    On a Hindu article of four claims, three were searched and the fourth sat below
    the per-check cap; the app told the reader no reliable source addressed it.
    """

    class _Search:
        name = "web_search"
        fallback = True

        def __init__(self) -> None:
            self.asked: list[str] = []

        async def candidates(self, claim: Any) -> list[Any]:
            self.asked.append(claim.id)
            return []

    @pytest.mark.anyio
    async def test_a_claim_below_the_cap_is_marked_not_searched(self) -> None:
        from app.orchestration.pipeline import MAX_FALLBACK_CLAIMS

        search = self._Search()
        orchestrator = Orchestrator(
            cache=NullCache(),  # type: ignore[arg-type]
            governor=RecordingGovernor(),  # type: ignore[arg-type]
            resolvers=[search],  # type: ignore[list-item]
            extractor_version="test",
        )
        claims = [
            claim(claim_id=f"cl_{n}", importance=Importance.SUPPORTING_DETAIL)
            for n in range(MAX_FALLBACK_CLAIMS + 1)
        ]
        intake = normalise_text("Four claims, one more than the search cap.")

        result = await orchestrator.verify(intake, case_id=uuid4(), claims=claims)

        statuses = {outcome.claim.id: outcome.search for outcome in result.claims}
        assert sorted(search.asked) == sorted(statuses)[:MAX_FALLBACK_CLAIMS]
        assert list(statuses.values()).count("searched") == MAX_FALLBACK_CLAIMS
        assert list(statuses.values()).count("not_searched") == 1
