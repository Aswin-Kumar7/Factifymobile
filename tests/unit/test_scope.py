"""A narrower version of a claim is not the claim (2026-09-27).

"Govt to pay Rs 5000 a month to every woman" came back True 81% on two reports of a
Tamil Nadu payment of Rs 5,000 to 1.3 crore women - one state, not every woman, not
monthly. Held here: the reader's "narrower" is context, never support, and says so in
its metric; the source check keeps a narrower source instead of dropping it, and
turns a support it judges only partly true into one; the rules call a claim that
credible sources show only a narrower version of MISLEADING - on the bar a
contradiction meets, never on one ordinary source - and a claim established in full
by two independent origins is still SUPPORTED.
"""

from __future__ import annotations

import asyncio

from app.domain import ClaimStatus, Credibility, Direction, EvidenceKind, MatchBasis, Method, Tier
from app.domain.enums import Relation
from app.domain.evidence import NARROWER_SCOPE, is_narrower_scope
from app.sources.reasoning import (
    _CHECK_SOURCES_INSTRUCTION,
    _RESPONSE_SCHEMA,
    _SYSTEM_INSTRUCTION,
    Passage,
    PassageReasoner,
    SourceCheck,
    SourceReading,
    _ReasoningResponse,
)
from app.sources.verification import SourceVerification
from app.verdict.engine import decide
from tests.unit.factories import claim, evidence

PASSAGE = (
    "The Tamil Nadu government is paying Rs 5,000 each to about 1.3 crore women under "
    "its entitlement scheme, the Chief Minister said on Friday."
)
CLAIM = "Govt to pay Rs 5000 a month to every woman"


def _judge(scope: str, relation: str = "SUPPORTS") -> object:
    reasoner = PassageReasoner.__new__(PassageReasoner)
    reasoner._model_id = "test"
    response = _ReasoningResponse.model_validate(
        {
            "judgements": [
                {
                    "passage_index": 0,
                    "relation": relation,
                    "asserted_by": "THE_ARTICLE",
                    "scope": scope,
                    "quote": PASSAGE,
                    "reason": "one state's scheme, a one-time payment",
                    "relevance": 0.9,
                }
            ]
        }
    )
    passages = [Passage(index=0, text=PASSAGE, char_start=0, char_end=len(PASSAGE))]
    return reasoner._verify(response, passages)


class TestTheReader:
    def test_a_narrower_version_is_context_and_marked(self) -> None:
        outcome = _judge("NARROWER")
        judgement = outcome.judgements[0]  # type: ignore[attr-defined]
        assert judgement.relation is Relation.CONTEXTUALIZES
        assert judgement.narrower is True

    def test_the_whole_claim_is_still_support(self) -> None:
        judgement = _judge("FULL").judgements[0]  # type: ignore[attr-defined]
        assert judgement.relation is Relation.SUPPORTS
        assert judgement.narrower is False

    def test_the_reader_is_asked_scope_before_the_relation(self) -> None:
        item = _RESPONSE_SCHEMA["properties"]["judgements"]["items"]
        order = list(item["properties"])
        assert "scope" in item["required"]
        assert order.index("scope") < order.index("relation")
        assert "one state's scheme" in _SYSTEM_INSTRUCTION
        assert "PARTLY" in _CHECK_SOURCES_INSTRUCTION


def _narrower(publisher: str, credibility: Credibility | None = None) -> object:
    return evidence(
        kind=EvidenceKind.CORROBORATION,
        direction=Direction.CONTEXTUALIZES,
        tier=Tier.D,
        method=Method.PASSAGE_ENTAILMENT,
        basis=MatchBasis(metric=f"{NARROWER_SCOPE}: one state", value=0.9, threshold=0.0),
        citation_url=f"https://www.{publisher}/tn-women-scheme",
        publisher=publisher,
        credibility=credibility,
    )


def _support(publisher: str) -> object:
    return evidence(
        kind=EvidenceKind.CORROBORATION,
        direction=Direction.SUPPORTS,
        tier=Tier.D,
        method=Method.PASSAGE_ENTAILMENT,
        basis=MatchBasis(metric="passage_entailment: r", value=0.9, threshold=0.0),
        citation_url=f"https://www.{publisher}/scheme",
        publisher=publisher,
    )


class TestTheRules:
    def test_two_publishers_showing_a_narrower_version_make_it_misleading(self) -> None:
        decision = decide(
            claim(text=CLAIM),
            [_narrower("thenewsminute.com"), _narrower("indiatoday.in")],  # type: ignore[list-item]
        )
        assert decision.status is ClaimStatus.MISLEADING_CONTEXT
        assert decision.rule_id == "rule.narrower_scope"
        assert decision.confidence is not None

    def test_one_highly_credible_publisher_is_enough(self) -> None:
        decision = decide(
            claim(text=CLAIM),
            [_narrower("thehindu.com", Credibility.HIGH)],  # type: ignore[list-item]
        )
        assert decision.status is ClaimStatus.MISLEADING_CONTEXT

    def test_one_ordinary_source_is_not(self) -> None:
        decision = decide(
            claim(text=CLAIM),
            [_narrower("someblog.in", Credibility.MEDIUM)],  # type: ignore[list-item]
        )
        assert decision.status is ClaimStatus.UNVERIFIED

    def test_the_whole_claim_from_two_origins_is_still_true(self) -> None:
        decision = decide(
            claim(text=CLAIM, independent_origin_count=2, document_count=2),
            [
                _support("thehindu.com"),
                _support("indianexpress.com"),
                _narrower("thenewsminute.com"),
                _narrower("indiatoday.in"),
            ],  # type: ignore[list-item]
        )
        assert decision.status is ClaimStatus.SUPPORTED


class _Checker:
    def __init__(
        self,
        verdicts: list[str],
        *,
        smaller: bool = True,
        about: bool = True,
        differs: bool = True,
        other_group: bool = False,
    ) -> None:
        self.verdicts = verdicts
        self.smaller = smaller
        self.about = about
        self.differs = differs
        self.other_group = other_group
        self.sent: list[tuple[str, str]] = []

    async def check_sources(self, claim_text: str, sources: list[tuple[str, str]]) -> SourceCheck:
        self.sent = sources
        return SourceCheck(
            readings={
                i: SourceReading(
                    addresses_claim=self.about,
                    verdict=v,
                    reason="one state only",
                    smaller_version=self.smaller and v != "TRUE",
                    states_differently=self.differs and v != "TRUE",
                    other_group=self.other_group,
                )
                for i, v in enumerate(self.verdicts)
            },
            explanation="Tamil Nadu pays Rs 5,000 to eligible women; not every woman, monthly.",
        )


class _Ranker:
    def credibility(self, _url: str | None) -> Credibility:
        return Credibility.HIGH


class TestTheSourceCheck:
    def test_a_narrower_source_is_sent_and_kept(self) -> None:
        checker = _Checker(["PARTLY"])
        verified = asyncio.run(
            SourceVerification(checker=checker, ranker=_Ranker()).check(
                claim(text=CLAIM),
                [_narrower("thenewsminute.com")],  # type: ignore[list-item]
            )
        )
        assert len(checker.sent) == 1
        assert len(verified.evidence) == 1
        assert is_narrower_scope(verified.evidence[0].match_basis.metric)

    def test_a_support_it_reads_as_partly_true_becomes_narrower(self) -> None:
        verified = asyncio.run(
            SourceVerification(checker=_Checker(["PARTLY"]), ranker=_Ranker()).check(
                claim(text=CLAIM),
                [_support("thenewsminute.com")],  # type: ignore[list-item]
            )
        )
        kept = verified.evidence[0]
        assert kept.direction is Direction.CONTEXTUALIZES
        assert is_narrower_scope(kept.match_basis.metric)

    def test_a_smaller_version_is_partly_true_even_called_not_about_the_claim(self) -> None:
        """The check called a one-time Rs 5,000 payment "not about the claim", three
        runs of three, while its reason described a smaller version. Its own yes-or-no
        on "smaller version", with PARTLY, decides (2026-09-28)."""
        verified = asyncio.run(
            SourceVerification(checker=_Checker(["PARTLY"], about=False), ranker=_Ranker()).check(
                claim(text=CLAIM),
                [_support("timesofindia.indiatimes.com")],  # type: ignore[list-item]
            )
        )
        [kept] = verified.evidence
        assert kept.direction is Direction.CONTEXTUALIZES
        assert is_narrower_scope(kept.match_basis.metric)

    def test_a_report_that_only_says_less_is_support(self) -> None:
        """India Today on the Aditya-L1 launch, without naming the launch site: the
        check said PARTLY, but states nothing differently. It supports the claim, and
        the claim is not "partly true" for it (2026-09-28)."""
        verified = asyncio.run(
            SourceVerification(checker=_Checker(["PARTLY"], differs=False), ranker=_Ranker()).check(
                claim(text="ISRO launched Aditya-L1 on 2 September 2023 from Sriharikota."),
                [_support("indiatoday.in")],  # type: ignore[list-item]
            )
        )
        [kept] = verified.evidence
        assert kept.direction is Direction.SUPPORTS
        assert not is_narrower_scope(kept.match_basis.metric)

    def test_saying_less_is_not_a_smaller_version(self) -> None:
        """ "The photographs were also shared", for a claim naming Facebook and X: the
        check called it a smaller version, with UNCLEAR. Both answers are required."""
        verified = asyncio.run(
            SourceVerification(checker=_Checker(["UNCLEAR"]), ranker=_Ranker()).check(
                claim(text="She shared the photos on her official Facebook and X accounts"),
                [_support("newschecker.in")],  # type: ignore[list-item]
            )
        )
        assert verified.evidence == []

    def test_partly_without_a_smaller_version_is_not_kept(self) -> None:
        """ "Atal Free Pension Scheme" against the real Atal Pension Yojana: PARTLY, but
        not a smaller version - a scam's borrowed name, not a real thing inflated."""
        verified = asyncio.run(
            SourceVerification(checker=_Checker(["PARTLY"], smaller=False), ranker=_Ranker()).check(
                claim(text="Under the Atal Free Pension Scheme everyone over 60 gets Rs 5,000"),
                [_support("pfrda.org.in")],  # type: ignore[list-item]
            )
        )
        assert verified.evidence == []

    @staticmethod
    def _read_as_denial(host: str) -> object:
        return evidence(
            kind=EvidenceKind.CORROBORATION,
            direction=Direction.CONTRADICTS,
            tier=Tier.D,
            method=Method.PASSAGE_ENTAILMENT,
            basis=MatchBasis(metric="passage_entailment: r", value=0.9, threshold=0.0),
            citation_url=f"https://{host}/story",
            publisher=host,
        )

    def test_a_smaller_version_read_as_a_denial_is_a_smaller_version(self) -> None:
        """Tamil Nadu's Rs 1,000 a month for women heads of families, read as denying
        "every woman gets Rs 5,000 a month" while the check called it a smaller
        version: the user decided it makes the claim partly true (2026-09-28)."""
        verified = asyncio.run(
            SourceVerification(checker=_Checker(["PARTLY"]), ranker=_Ranker()).check(
                claim(text=CLAIM),
                [self._read_as_denial("timesofindia.indiatimes.com")],  # type: ignore[list-item]
            )
        )
        [kept] = verified.evidence
        assert kept.direction is Direction.CONTEXTUALIZES
        assert is_narrower_scope(kept.match_basis.metric)

    def test_a_denial_the_check_confirms_is_still_a_contradiction(self) -> None:
        verified = asyncio.run(
            SourceVerification(checker=_Checker(["FALSE"]), ranker=_Ranker()).check(
                claim(text=CLAIM),
                [self._read_as_denial("pib.gov.in")],  # type: ignore[list-item]
            )
        )
        [kept] = verified.evidence
        assert kept.direction is Direction.CONTRADICTS

    def test_the_same_amount_for_a_different_group_is_not_a_smaller_version(self) -> None:
        """The PM Internship Scheme's Rs 5,000 a month for interns was kept as a smaller
        version of "every woman gets Rs 5,000 a month" (2026-09-28)."""
        verified = asyncio.run(
            SourceVerification(
                checker=_Checker(["PARTLY"], other_group=True), ranker=_Ranker()
            ).check(
                claim(text=CLAIM),
                [_support("vishvasnews.com")],  # type: ignore[list-item]
            )
        )
        assert verified.evidence == []

    def test_other_context_is_still_not_sent(self) -> None:
        plain_context = evidence(
            kind=EvidenceKind.CORROBORATION,
            direction=Direction.CONTEXTUALIZES,
            tier=Tier.D,
            method=Method.PASSAGE_ENTAILMENT,
            basis=MatchBasis(metric="passage_entailment: r", value=0.9, threshold=0.0),
        )
        checker = _Checker([])
        verified = asyncio.run(
            SourceVerification(checker=checker, ranker=_Ranker()).check(
                claim(text=CLAIM), [plain_context]
            )
        )
        assert checker.sent == []
        assert verified.evidence == []


def test_the_versions_moved_so_old_answers_are_not_served() -> None:
    from app.sources.reasoning import REASONER_VERSION
    from app.verdict.engine import RULE_VERSION

    assert REASONER_VERSION >= "2026.09.27.1"
    assert RULE_VERSION >= "2026.09.27.1"
