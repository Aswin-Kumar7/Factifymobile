"""The earlier copy a media match points at (contract 1.3, build brief 4.5).

Held here: only a media match carries `earlier_media`, with its date, publisher and
how closely the pictures match; a fresh result whose picture checks fetched the same
page shows that copy's thumbnail - from our own address - and no other citation
gains one.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.api.schemas import (
    ClaimResponse,
    CredentialsResponse,
    DetectorResponse,
    EarlierCopyResponse,
    EditingResponse,
    EvidenceResponse,
    HistoryResponse,
    MatchBasisResponse,
    MediaReportResponse,
    SourceAnchorResponse,
    StrengthResponse,
    VerifyResponse,
    earlier_media_of,
)
from app.api.verify import with_earlier_copy

PAGE = "https://www.boomlive.in/fact-check/flood-photo/"


def _evidence(kind: str, url: str) -> EvidenceResponse:
    return EvidenceResponse(
        id=f"ev-{kind}",
        tier="B",
        kind=kind,
        direction="contradicts",
        method="near_duplicate_verified" if kind == "media_match" else "claim_review",
        finding="f",
        citation_url=url,
        snapshot_id="s",
        source_excerpt="This image was published by BOOM on 20 July 2024.",
        source_anchor=SourceAnchorResponse(),
        match_basis=MatchBasisResponse(metric="clip_cosine", value=0.9712, threshold=0.93),
        match_quality="STRONG",
        publisher="BOOM",
        published_on=date(2024, 7, 20),
        earlier_media=earlier_media_of(kind, 0.9712, date(2024, 7, 20), "BOOM"),
    )


def _case(*evidence: EvidenceResponse, earliest_url: str | None = PAGE) -> VerifyResponse:
    history = HistoryResponse(
        status="found" if earliest_url else "none",
        pages=1,
        dated=1,
        earliest=(
            EarlierCopyResponse(
                url=earliest_url,
                publisher="BOOM",
                published_at=datetime(2024, 7, 20, tzinfo=UTC),
                days_before=799,
                thumbnail_url="/v1/media/thumbnails/" + "a" * 32,
            )
            if earliest_url
            else None
        ),
    )
    return VerifyResponse(
        case_id="c",
        action="SHARE_WITH_CONTEXT",
        action_reason="r",
        rule_version="v",
        claims=(
            ClaimResponse(
                id="cl",
                text="Flooding inside Mumbai airport this morning.",
                claim_type="MEDIA",
                status="MISLEADING_CONTEXT",
                severity="HIGH",
                importance="HEADLINE",
                reason="r",
                rule_id="r",
                rule_version="v",
                strength=StrengthResponse(score=0.9, band="STRONG", version="v"),
                evidence=evidence,
            ),
        ),
        media_report=MediaReportResponse(
            kind="image",
            credentials=CredentialsResponse(status="none"),
            history=history,
            detector=DetectorResponse(status="not_checked"),
            editing=EditingResponse(status="not_checked"),
        ),
        retrieved_at=datetime.now(UTC),
    )


def test_only_a_media_match_carries_the_earlier_copy() -> None:
    match = _evidence("media_match", PAGE)
    assert match.earlier_media is not None
    assert match.earlier_media.similarity == 0.9712
    assert match.earlier_media.published_at == date(2024, 7, 20)
    assert match.earlier_media.publisher == "BOOM"
    assert _evidence("fact_check", PAGE).earlier_media is None


def test_the_same_page_shows_its_thumbnail_from_our_own_address() -> None:
    # The same page, written without "www." and without the trailing slash.
    case = with_earlier_copy(
        _case(_evidence("media_match", "https://boomlive.in/fact-check/flood-photo"))
    )
    shown = case.claims[0].evidence[0].earlier_media
    assert shown is not None
    assert shown.thumbnail_url == "/v1/media/thumbnails/" + "a" * 32


def test_another_page_or_another_kind_gains_no_thumbnail() -> None:
    elsewhere = with_earlier_copy(
        _case(_evidence("media_match", "https://www.altnews.in/some-other-photo"))
    )
    assert elsewhere.claims[0].evidence[0].earlier_media.thumbnail_url is None  # type: ignore[union-attr]

    fact_check = with_earlier_copy(_case(_evidence("fact_check", PAGE)))
    assert fact_check.claims[0].evidence[0].earlier_media is None

    nothing_found = _case(_evidence("media_match", PAGE), earliest_url=None)
    assert with_earlier_copy(nothing_found) is nothing_found
