"""Progress events for the Checking screen (contract 1.3).

Held here:

  - events arrive in order, numbered, and every stream ends with `done` or `error`;
  - a reader who starts late is given everything so far, and one who reconnects
    resumes where it left off;
  - a site read for several claims is one source on screen, done when its last read
    ends; a page the source check later throws out is taken back, so the count the
    screen ends on is the count of sources the answer cites;
  - nothing that was checked travels in an event: no claim, no text, no page path;
  - the pipeline emits them from a real check, and a refused check ends its stream.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.verify import _watched
from app.domain.enums import EvidenceKind, Method, Relation, Tier
from app.intake.normalizer import normalise_text
from app.orchestration.pipeline import Orchestrator
from app.orchestration.progress import (
    CheckProgress,
    LocalProgressBus,
    RedisProgressBus,
    current_progress,
    initials,
    valid_key,
)
from tests.unit import factories

pytestmark = pytest.mark.unit

KEY = "5f0c6a52-8a3e-4c52-9d6e-0b1f2a3c4d5e"


async def _drain(bus: Any, key: str = KEY) -> list[dict[str, Any]]:
    return [event async for event in bus.subscribe(key)]


# ----------------------------------------------------------------------------- bus


class TestTheBus:
    async def test_events_arrive_in_order_and_end_with_done(self) -> None:
        bus = LocalProgressBus()
        for step in ("read", "search", "compare"):
            await bus.publish(KEY, {"type": "step", "step": step})
        await bus.publish(KEY, {"type": "done", "case_id": "c1"})

        events = await _drain(bus)

        assert [e["seq"] for e in events] == [1, 2, 3, 4]
        assert [e.get("step") for e in events[:3]] == ["read", "search", "compare"]
        assert events[-1] == {"type": "done", "case_id": "c1", "seq": 4}

    async def test_a_reader_who_starts_first_hears_each_event_as_it_happens(self) -> None:
        bus = LocalProgressBus()
        heard = asyncio.create_task(_drain(bus))
        await asyncio.sleep(0)
        await bus.publish(KEY, {"type": "step", "step": "read"})
        await asyncio.sleep(0)
        await bus.publish(KEY, {"type": "error", "code": "no_credit"})

        events = await asyncio.wait_for(heard, 1)

        assert [e["type"] for e in events] == ["step", "error"]

    async def test_nothing_is_added_after_the_end(self) -> None:
        bus = LocalProgressBus()
        await bus.publish(KEY, {"type": "done", "case_id": "c1"})
        await bus.publish(KEY, {"type": "step", "step": "search"})

        events, finished = await bus.since(KEY, 0)

        assert finished
        assert [e["type"] for e in events] == ["done"]

    async def test_polling_asks_for_what_came_after(self) -> None:
        bus = LocalProgressBus()
        for step in ("read", "search"):
            await bus.publish(KEY, {"type": "step", "step": step})

        events, finished = await bus.since(KEY, 1)

        assert [e["step"] for e in events] == ["search"]
        assert not finished
        assert await bus.since("unknown", 0) == ([], False)

    async def test_a_finished_check_is_forgotten_after_a_while(self) -> None:
        now = [0.0]
        bus = LocalProgressBus(clock=lambda: now[0])
        await bus.publish(KEY, {"type": "done", "case_id": "c1"})
        now[0] = 601.0
        await bus.publish("other", {"type": "step", "step": "read"})

        assert await bus.since(KEY, 0) == ([], False)

    def test_only_uuids_are_listened_on(self) -> None:
        assert valid_key(KEY)
        assert valid_key(uuid4().hex)
        assert not valid_key("../../etc/passwd")
        assert not valid_key("short")


# -------------------------------------------------------------------- one check


class TestOneCheck:
    async def test_steps_only_move_forward(self) -> None:
        bus = LocalProgressBus()
        progress = CheckProgress(bus, KEY)
        await progress.step("read")
        await progress.step("compare")
        await progress.step("search")  # a slower claim, still searching

        events, _ = await bus.since(KEY, 0)
        assert [e["step"] for e in events] == ["read", "compare"]

    async def test_a_site_read_for_two_claims_is_one_source(self) -> None:
        bus = LocalProgressBus()
        progress = CheckProgress(bus, KEY, names={"altnews.in": "Alt News"}.get)
        await progress.source_started("https://www.altnews.in/a")
        await progress.source_started("https://altnews.in/b")
        await progress.source_done("https://altnews.in/a", claim_id="cl_1", found=False)
        # still being read for the second claim: not done yet
        events, _ = await bus.since(KEY, 0)
        assert [e["type"] for e in events] == ["source_started"]
        assert events[0] == {
            "type": "source_started",
            "publisher": "Alt News",
            "domain": "altnews.in",
            "initials": "AN",
            "seq": 1,
        }

        await progress.source_done("https://altnews.in/b", claim_id="cl_2", found=True)
        events, _ = await bus.since(KEY, 1)
        assert [(e["type"], e.get("outcome"), e.get("n")) for e in events] == [
            ("source_done", "evidence", None),
            ("evidence_count", None, 1),
        ]

    async def test_a_source_the_check_throws_out_is_taken_back(self) -> None:
        bus = LocalProgressBus()
        progress = CheckProgress(bus, KEY)
        for site in ("pib.gov.in", "ndtv.com"):
            await progress.source_started(f"https://{site}/story")
            await progress.source_done(f"https://{site}/story", claim_id="cl_1", found=True)

        # The source check keeps PIB and decides NDTV was about something else.
        await progress.verified("cl_1", ["https://pib.gov.in/story"])

        events, _ = await bus.since(KEY, 0)
        tail = [(e["type"], e.get("domain"), e.get("outcome"), e.get("n")) for e in events[-2:]]
        assert tail == [
            ("source_done", "ndtv.com", "not_relevant", None),
            ("evidence_count", None, None, 1),
        ]

    async def test_nothing_that_was_checked_is_in_an_event(self) -> None:
        bus = LocalProgressBus()
        progress = CheckProgress(bus, KEY)
        secret = "/2026/09/rbi-bans-rs-500-notes-from-october"
        await progress.step("read")
        await progress.source_started(f"https://www.thehindu.com{secret}", "The Hindu")
        await progress.source_done(f"https://www.thehindu.com{secret}", claim_id="cl_1", found=True)
        await progress.verified("cl_1", [f"https://www.thehindu.com{secret}"])
        await progress.done("case-1")

        wire = json.dumps((await bus.since(KEY, 0))[0])
        assert "rbi" not in wire and "notes" not in wire and "2026" not in wire
        assert "thehindu.com" in wire and "The Hindu" in wire

    async def test_a_bus_that_fails_never_fails_the_check(self) -> None:
        class Broken:
            async def publish(self, key: str, event: dict[str, Any]) -> None:
                raise ConnectionError("redis down")

        progress = CheckProgress(Broken(), KEY)  # type: ignore[arg-type]
        await progress.step("read")
        await progress.done("case-1")

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Press Trust of India", "PTI"),
            ("Alt News", "AN"),
            ("BOOM", "BO"),
            ("pib.gov.in", "PI"),
            ("The Hindu", "TH"),
        ],
    )
    def test_initials(self, name: str, expected: str) -> None:
        assert initials(name) == expected


# ---------------------------------------------------------------- the pipeline


class _Source:
    """One page per claim on `site`, saying `relation` about it."""

    version = "v"
    allowed_domains: frozenset[str] = frozenset()
    fallback = False
    tier = Tier.C
    kind = EvidenceKind.FACT_CHECK
    method = Method.CLAIM_REVIEW

    def __init__(self, site: str, relation: Relation) -> None:
        self.name = site
        self._site = site
        self._relation = relation

    async def candidates(self, claim: Any) -> list[Any]:
        from app.sources.base import SourceCandidate

        return [SourceCandidate(url=f"https://{self._site}/{claim.id}")]

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


class _NoCache:
    async def get_verdict(self, parts: Any) -> None:
        return None


class _NoGovernor:
    async def try_acquire(self, provider: str) -> Any:
        from app.governor.governor import Skip, SkipReason

        return Skip(provider=provider, reason=SkipReason.NOT_CONFIGURED)


class TestThePipelineReports:
    async def test_a_check_reports_its_steps_and_each_source(self) -> None:
        bus = LocalProgressBus()
        orchestrator = Orchestrator(
            cache=_NoCache(),  # type: ignore[arg-type]
            governor=_NoGovernor(),  # type: ignore[arg-type]
            resolvers=[
                _Source("factly.in", Relation.CONTRADICTS),
                _Source("example.org", Relation.NOT_RELEVANT),
            ],
            extractor_version="test",
        )
        token = current_progress.set(CheckProgress(bus, KEY))
        try:
            await orchestrator.verify(
                normalise_text("A claim."), case_id=uuid4(), claims=[factories.claim()]
            )
        finally:
            current_progress.reset(token)

        events, _ = await bus.since(KEY, 0)
        kinds = [e["type"] for e in events]
        assert kinds[0] == "step" and events[0]["step"] == "search"
        done = {e["domain"]: e["outcome"] for e in events if e["type"] == "source_done"}
        assert done == {"factly.in": "evidence", "example.org": "not_relevant"}
        started = [e["domain"] for e in events if e["type"] == "source_started"]
        assert sorted(started) == ["example.org", "factly.in"]
        # Each source is started before it is done.
        for domain in started:
            at = {e["type"]: i for i, e in enumerate(events) if e.get("domain") == domain}
            assert at["source_started"] < at["source_done"]
        assert {"type": "evidence_count", "n": 1} in [
            {k: v for k, v in e.items() if k != "seq"} for e in events
        ]

    async def test_a_check_nobody_follows_reports_nothing(self) -> None:
        assert current_progress.get() is None
        orchestrator = Orchestrator(
            cache=_NoCache(),  # type: ignore[arg-type]
            governor=_NoGovernor(),  # type: ignore[arg-type]
            resolvers=[_Source("factly.in", Relation.CONTRADICTS)],
            extractor_version="test",
        )
        result = await orchestrator.verify(
            normalise_text("A claim."), case_id=uuid4(), claims=[factories.claim()]
        )
        assert result.claims


# -------------------------------------------------------------------- endpoints


def _request(bus: Any, header: str | None = None) -> Any:
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(progress_bus=bus)),
        headers={"X-Request-ID": header} if header else {},
    )


class TestTheStreamEnds:
    async def test_a_refused_check_ends_with_its_reason(self) -> None:
        bus = LocalProgressBus()
        with pytest.raises(HTTPException):
            async with _watched(_request(bus), KEY):
                raise HTTPException(status_code=402, detail="no credits left")

        events = await _drain(bus)
        assert [(e["type"], e.get("step") or e.get("code")) for e in events] == [
            ("step", "read"),
            ("error", "no_credit"),
        ]
        assert current_progress.get() is None

    async def test_a_failure_ends_it_too(self) -> None:
        bus = LocalProgressBus()
        with pytest.raises(RuntimeError):
            async with _watched(_request(bus), KEY):
                raise RuntimeError("boom")
        assert (await _drain(bus))[-1]["code"] == "failed"

    async def test_nobody_following_means_no_events(self) -> None:
        bus = LocalProgressBus()
        async with _watched(_request(bus), None) as watching:
            assert watching is None
            assert current_progress.get() is None


class TestTheHttpStream:
    @staticmethod
    def _client() -> Any:
        from fastapi.testclient import TestClient

        from app.main import create_app

        return TestClient(create_app())

    def test_the_stream_replays_the_check_and_ends(self) -> None:
        client = self._client()
        bus = client.app.state.progress_bus

        async def publish() -> None:
            await bus.publish(KEY, {"type": "step", "step": "read"})
            await bus.publish(KEY, {"type": "evidence_count", "n": 2})
            await bus.publish(KEY, {"type": "done", "case_id": "c1"})

        asyncio.run(publish())

        with client.stream("GET", f"/v1/cases/{KEY}/events") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = "".join(response.iter_text())

        assert "event: step" in body
        assert "id: 3\nevent: done\n" in body
        assert body.index("event: step") < body.index("event: done")

        with client.stream(
            "GET", f"/v1/cases/{KEY}/events", headers={"Last-Event-ID": "2"}
        ) as response:
            resumed = "".join(response.iter_text())
        assert "event: step" not in resumed and "event: done" in resumed

    def test_polling_and_a_made_up_key(self) -> None:
        client = self._client()
        bus = client.app.state.progress_bus
        asyncio.run(bus.publish(KEY, {"type": "step", "step": "read"}))

        polled = client.get(f"/v1/cases/{KEY}/progress", params={"after": 0}).json()
        assert polled["finished"] is False
        assert polled["events"][0]["step"] == "read"
        assert client.get("/v1/cases/not-a-uuid/events").status_code == 404


# ------------------------------------------------------------------------ Redis


class _FakeRedis:
    """The few Redis calls the bus makes, in memory."""

    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.listeners: dict[str, list[asyncio.Queue[str]]] = {}

    async def rpush(self, key: str, value: str) -> int:
        self.lists.setdefault(key, []).append(value)
        return len(self.lists[key])

    async def rpop(self, key: str) -> str:
        return self.lists[key].pop()

    async def lset(self, key: str, index: int, value: str) -> None:
        self.lists[key][index] = value

    async def expire(self, key: str, seconds: int) -> None:
        return None

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        items = self.lists.get(key, [])
        return items[start:] if end == -1 else items[start : end + 1]

    async def publish(self, topic: str, data: str) -> None:
        for queue in self.listeners.get(topic, []):
            queue.put_nowait(data)

    def pubsub(self) -> Any:
        outer = self

        class _PubSub:
            queue: asyncio.Queue[str] = asyncio.Queue()

            async def subscribe(self, topic: str) -> None:
                outer.listeners.setdefault(topic, []).append(self.queue)

            async def get_message(self, **_: Any) -> dict[str, str] | None:
                try:
                    return {"data": await asyncio.wait_for(self.queue.get(), 1)}
                except TimeoutError:
                    return None

            async def unsubscribe(self, topic: str) -> None:
                outer.listeners[topic].remove(self.queue)

            async def aclose(self) -> None:
                return None

        return _PubSub()


class TestTheRedisBus:
    async def test_events_are_replayed_then_heard_live(self) -> None:
        bus = RedisProgressBus(_FakeRedis())
        await bus.publish(KEY, {"type": "step", "step": "read"})

        heard = asyncio.create_task(_drain(bus))
        await asyncio.sleep(0.01)
        await bus.publish(KEY, {"type": "step", "step": "search"})
        await bus.publish(KEY, {"type": "done", "case_id": "c1"})

        events = await asyncio.wait_for(heard, 2)
        assert [(e["seq"], e["type"]) for e in events] == [(1, "step"), (2, "step"), (3, "done")]

        polled, finished = await bus.since(KEY, 1)
        assert finished and [e["seq"] for e in polled] == [2, 3]
