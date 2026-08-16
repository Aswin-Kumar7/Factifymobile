"""MinHash over text shingles (M26 support). Pure, no dependencies.

Implemented here rather than taken from a library because the signature has to
serialise into a `bytea` column in a stable, documented layout, and because this is
the machinery two separate correctness rules depend on — near-duplicate detection and
independent-origin counting. It is worth being able to read.

The idea in one paragraph: hash every k-word window of a document, keep the minimum
hash under each of N independent hash functions, and the fraction of positions where
two signatures agree estimates their Jaccard similarity. Two articles that share most
of their word windows agree on most positions; two that merely share a topic do not.
"""

from __future__ import annotations

import hashlib
import re
import struct
from dataclasses import dataclass

# Word windows rather than characters. A 5-word shingle survives the light editing a
# wire copy receives — a changed headline, a localised first line — while still
# diverging completely for independently written coverage of the same event.
SHINGLE_SIZE = 5

# 128 permutations. The estimate's standard error is roughly 1/sqrt(N), so 128 gives
# about 9% — comfortably tight enough to separate a reprint from a rewrite, and
# small enough that a signature is 512 bytes rather than several kilobytes.
PERMUTATIONS = 128

_MAX_HASH = (1 << 32) - 1
_TOKEN = re.compile(r"[a-z0-9ऀ-ॿ]+")


def normalise(text: str) -> list[str]:
    """Lowercase, strip punctuation, keep Devanagari.

    Deliberately does not stem or remove stopwords. Stopword removal would make two
    documents about the same subject look more alike, which is the opposite of what
    this measurement is for: the question is whether one document was copied from the
    other, not whether they are about the same thing.
    """
    return _TOKEN.findall(text.lower())


def shingles(text: str, size: int = SHINGLE_SIZE) -> set[str]:
    """Overlapping word windows."""
    tokens = normalise(text)
    if len(tokens) < size:
        # Too short to window: the whole thing is one shingle, so short items still
        # compare rather than silently matching everything.
        return {" ".join(tokens)} if tokens else set()

    return {" ".join(tokens[i : i + size]) for i in range(len(tokens) - size + 1)}


@dataclass(frozen=True, slots=True)
class Signature:
    """A MinHash signature, comparable and serialisable."""

    values: tuple[int, ...]

    def to_bytes(self) -> bytes:
        """Fixed-width big-endian, so the layout is stable across versions."""
        return struct.pack(f">{len(self.values)}I", *self.values)

    @classmethod
    def from_bytes(cls, data: bytes) -> Signature:
        count = len(data) // 4
        return cls(values=struct.unpack(f">{count}I", data))

    def similarity(self, other: Signature) -> float:
        """Estimated Jaccard similarity: the fraction of positions that agree."""
        if len(self.values) != len(other.values):
            raise ValueError(
                f"signature length mismatch: {len(self.values)} vs {len(other.values)}"
            )
        if not self.values:
            return 0.0

        agreements = sum(1 for a, b in zip(self.values, other.values, strict=True) if a == b)
        return agreements / len(self.values)


def _seeded_hash(value: str, seed: int) -> int:
    """A hash family indexed by seed.

    Uses blake2b with the seed as a personalisation string rather than the usual
    `(a*h + b) mod p` trick: it is a genuinely independent function per seed, and
    unlike Python's built-in `hash` it is stable across processes — which matters
    because these signatures are stored and compared days later.
    """
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=4, salt=seed.to_bytes(8, "big")[:8])
    return int.from_bytes(digest.digest(), "big")


def sign(text: str, *, permutations: int = PERMUTATIONS, size: int = SHINGLE_SIZE) -> Signature:
    """Compute a signature for a document."""
    document = shingles(text, size)

    if not document:
        return Signature(values=tuple([_MAX_HASH] * permutations))

    values = []
    for seed in range(permutations):
        values.append(min(_seeded_hash(shingle, seed) for shingle in document))

    return Signature(values=tuple(values))


def jaccard(left: str, right: str) -> float:
    """Exact Jaccard over shingles. Used to check the estimator, not in production."""
    a, b = shingles(left), shingles(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
