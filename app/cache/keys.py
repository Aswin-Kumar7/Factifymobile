"""Cache key derivation (M13). Pure, so the rules can be tested without a database.

A cache key is a claim that two requests deserve the same answer. Getting it wrong in
the lenient direction is the worst kind of bug this system can have: a rule change
ships, and every cached verdict keeps serving the old logic under the new version
number, invisibly, until someone notices a contradiction on stage.

So the key incorporates **everything that would change the answer** — not just the
content. Anything omitted here is something we are asserting cannot affect a verdict.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# Bumped when the corpus changes in a way that could change corroboration counts.
# Ingestion advances this; a verdict computed against a thinner corpus should not be
# served once the corpus has grown.
DEFAULT_CORPUS_VERSION = "0"

# Named policy profiles. A tenant demanding three independent origins must not be
# served a verdict computed under a two-origin rule.
DEFAULT_POLICY_PROFILE = "default"


@dataclass(frozen=True, slots=True)
class CacheKeyParts:
    """Everything that participates in a verdict cache key.

    Written as a record rather than positional arguments so adding a dimension is a
    visible change at every construction site, instead of a silently-defaulted
    parameter that quietly widens what counts as "the same request".
    """

    content_hash: str
    rule_version: str
    extractor_version: str
    corpus_version: str = DEFAULT_CORPUS_VERSION
    policy_profile: str = DEFAULT_POLICY_PROFILE
    language: str | None = None

    # The model that produced the extraction, because it changes the answer.
    #
    # `extractor_version` covers our prompt and parsing; it does not move when Google
    # changes what a model id resolves to. Pointing at a moving alias like
    # `gemini-flash-latest` without this would keep serving extractions computed by
    # the previous model under a key asserting the current one — and worse, new
    # extractions from the new model would be stored under that same key. Including
    # it means a model change simply misses and recomputes.
    model_id: str = ""

    def derive(self) -> str:
        """A stable, opaque key.

        Fields are joined with a separator that cannot appear inside a hash or a
        version string, so two different tuples cannot collide by concatenation —
        ("ab", "c") and ("a", "bc") must not produce the same key.
        """
        material = "\x1f".join(
            (
                self.content_hash,
                self.rule_version,
                self.extractor_version,
                self.corpus_version,
                self.policy_profile,
                self.language or "-",
                self.model_id or "-",
            )
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


def content_hash(data: bytes) -> str:
    """Content addressing for bytes — the identity a cache probe starts from."""
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def text_hash(text: str) -> str:
    """Content addressing for text, normalised so trivial whitespace is not a miss."""
    normalised = " ".join(text.split())
    return f"sha256:{hashlib.sha256(normalised.encode('utf-8')).hexdigest()}"


def url_key(canonical_url: str) -> str:
    """Cache identity for a resolved URL's extracted text."""
    return f"url:{hashlib.sha256(canonical_url.encode('utf-8')).hexdigest()}"
