"""M13 — cache key derivation.

A cache key is a claim that two requests deserve the same answer. Every test here is
about the lenient failure: a key that matches when it should not, silently serving
stale logic under a new version number.
"""

from __future__ import annotations

import pytest

from app.cache.keys import CacheKeyParts, content_hash, text_hash, url_key

pytestmark = pytest.mark.unit


def _parts(**overrides: object) -> CacheKeyParts:
    base: dict[str, object] = {
        "content_hash": "sha256:abc",
        "rule_version": "2026.08.1",
        "extractor_version": "1",
        "corpus_version": "7",
        "policy_profile": "default",
        "language": "en",
    }
    base.update(overrides)
    return CacheKeyParts(**base)  # type: ignore[arg-type]


class TestEveryDimensionParticipates:
    """Anything omitted from the key is an assertion that it cannot change a verdict."""

    @pytest.mark.parametrize(
        ("field", "changed"),
        [
            ("content_hash", "sha256:different"),
            ("rule_version", "2026.09.1"),
            ("extractor_version", "2"),
            ("corpus_version", "8"),
            ("policy_profile", "newsroom_three_origins"),
            ("language", "hi"),
        ],
    )
    def test_changing_any_dimension_changes_the_key(self, field: str, changed: str) -> None:
        assert _parts().derive() != _parts(**{field: changed}).derive()

    def test_identical_inputs_produce_an_identical_key(self) -> None:
        assert _parts().derive() == _parts().derive()

    def test_a_rule_change_cannot_hit_an_old_entry(self) -> None:
        """The failure that would be worst and least visible: new rules, old answers."""
        before = _parts(rule_version="2026.08.1").derive()
        after = _parts(rule_version="2026.08.2").derive()

        assert before != after

    def test_a_stricter_policy_profile_does_not_reuse_a_looser_verdict(self) -> None:
        """A newsroom demanding three origins must not receive a two-origin answer."""
        assert (
            _parts(policy_profile="default").derive()
            != _parts(policy_profile="three_origins").derive()
        )


class TestCollisionResistance:
    def test_field_boundaries_cannot_be_confused(self) -> None:
        """("ab","c") and ("a","bc") must not collide through concatenation."""
        left = _parts(content_hash="ab", rule_version="c").derive()
        right = _parts(content_hash="a", rule_version="bc").derive()

        assert left != right

    def test_absent_language_is_distinct_from_a_language(self) -> None:
        assert _parts(language=None).derive() != _parts(language="en").derive()


class TestContentAddressing:
    def test_identical_bytes_hash_identically(self) -> None:
        assert content_hash(b"hello") == content_hash(b"hello")

    def test_different_bytes_hash_differently(self) -> None:
        assert content_hash(b"hello") != content_hash(b"world")

    def test_trivial_whitespace_is_not_a_cache_miss(self) -> None:
        """The same forward pasted twice should not cost two extractions."""
        assert text_hash("a  claim\n") == text_hash("a claim")

    def test_meaningfully_different_text_still_misses(self) -> None:
        assert text_hash("a claim") != text_hash("another claim")

    def test_url_keys_are_stable_and_distinct(self) -> None:
        assert url_key("https://a.example/x") == url_key("https://a.example/x")
        assert url_key("https://a.example/x") != url_key("https://a.example/y")
