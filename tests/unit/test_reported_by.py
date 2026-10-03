"""An undecided claim from a trusted publisher's own page says who reports it, instead
of being held back as "too recent" (2026-10-03, an Al Jazeera post a day old)."""

from __future__ import annotations

import pytest

from app.domain import ClaimType
from app.orchestration.pipeline import _reported_by_note
from tests.unit.factories import claim

pytestmark = pytest.mark.unit


def test_a_trusted_publisher_s_claim_says_who_reports_it() -> None:
    note = _reported_by_note(claim(claim_type=ClaimType.EVENT), "Al Jazeera")

    assert note == "Reported by Al Jazeera; not yet confirmed by a second independent outlet."


def test_nothing_is_said_without_a_trusted_publisher() -> None:
    assert _reported_by_note(claim(claim_type=ClaimType.EVENT), None) is None


def test_an_opinion_is_not_said_to_be_reported() -> None:
    assert _reported_by_note(claim(claim_type=ClaimType.OPINION), "Al Jazeera") is None


def test_it_is_said_in_hindi_for_a_hindi_claim() -> None:
    note = _reported_by_note(claim(claim_type=ClaimType.EVENT, language="hi"), "NDTV")

    assert note is not None and note.startswith("यह NDTV")
