"""Snapshot record and replay (M47).

Deterministic CI over live-sourced data. Tests run against stored bytes — real
responses fetched from real URLs at a recorded time — rather than re-fetching.

The rule that matters: **CI never touches the network.** A publisher editing a page
mid-run is a flake, not a finding, and a suite that fails for that reason gets
ignored within a week. Live retrieval is exercised by the ingestion worker and the
audit run, which are supposed to notice when the web changes.

    FACIFY_RECORD_SNAPSHOTS=1 uv run pytest -m replay    # capture
    uv run pytest -m replay                              # replay, the default
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SNAPSHOT_DIR = Path(__file__).resolve().parent / "snapshots"


def recording() -> bool:
    """Whether to capture rather than replay. Never true in CI."""
    return os.environ.get("FACIFY_RECORD_SNAPSHOTS") == "1"


def key_for(url: str) -> str:
    """A stable filename for a URL, safe on every filesystem."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


class SnapshotMissing(Exception):
    """No stored snapshot, and recording is off.

    Deliberately loud. The alternative — falling back to a live fetch — would make
    CI silently network-dependent again, which is the exact property this module
    exists to remove.
    """

    def __init__(self, url: str) -> None:
        super().__init__(
            f"no snapshot for {url}. Re-record with FACIFY_RECORD_SNAPSHOTS=1, or fix "
            "the test to use one that exists. CI must not fetch."
        )


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Bytes as they were, and when they were taken."""

    url: str
    status_code: int
    body: bytes
    content_type: str
    fetched_at: str

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    @property
    def content_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.body).hexdigest()


def save(url: str, *, status_code: int, body: bytes, content_type: str = "text/html") -> Path:
    """Store a snapshot. Only ever called in recording mode."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    key = key_for(url)

    # Metadata and body are separate files: the body stays byte-exact and
    # inspectable, rather than base64 inside JSON where nobody will ever read it.
    (SNAPSHOT_DIR / f"{key}.body").write_bytes(body)
    meta = {
        "url": url,
        "status_code": status_code,
        "content_type": content_type,
        "fetched_at": datetime.now(UTC).isoformat(),
        "content_hash": "sha256:" + hashlib.sha256(body).hexdigest(),
        "byte_count": len(body),
    }
    path = SNAPSHOT_DIR / f"{key}.json"
    path.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return path


def load(url: str) -> Snapshot:
    """Read a stored snapshot, or raise. Never falls back to the network."""
    key = key_for(url)
    meta_path = SNAPSHOT_DIR / f"{key}.json"
    body_path = SNAPSHOT_DIR / f"{key}.body"

    if not meta_path.exists() or not body_path.exists():
        raise SnapshotMissing(url)

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return Snapshot(
        url=str(meta["url"]),
        status_code=int(meta["status_code"]),
        body=body_path.read_bytes(),
        content_type=str(meta.get("content_type", "text/html")),
        fetched_at=str(meta.get("fetched_at", "")),
    )


def available() -> list[str]:
    """Every URL with a stored snapshot."""
    if not SNAPSHOT_DIR.exists():
        return []
    urls: list[str] = []
    for meta in sorted(SNAPSHOT_DIR.glob("*.json")):
        urls.append(str(json.loads(meta.read_text(encoding="utf-8"))["url"]))
    return urls


class ReplayFetcher:
    """A `SecureFetcher` stand-in that serves snapshots and never opens a socket.

    Matches the real fetcher's return shape, so code under test cannot tell the
    difference — and cannot accidentally work only under replay.
    """

    def __init__(self) -> None:
        self.requested: list[str] = []

    async def fetch(self, url: str, *, provider: str = "test") -> object:
        from app.security.fetcher import FetchResult

        self.requested.append(url)
        snapshot = load(url)
        return FetchResult(
            url=url,
            final_url=url,
            status_code=snapshot.status_code,
            content_type=snapshot.content_type,
            body=snapshot.body,
            byte_count=len(snapshot.body),
            fetched_at=datetime.now(UTC),
            elapsed_ms=0.0,
        )

    async def post_json(
        self,
        url: str,
        payload: dict[str, object],
        *,
        provider: str,
        headers: dict[str, str] | None = None,
    ) -> object:
        """Provider POSTs replay too, keyed by URL.

        A test that reaches a model provider is a test whose result depends on a
        model, which is not something CI can assert against.
        """
        return await self.fetch(url, provider=provider)

    async def aclose(self) -> None:
        return None
