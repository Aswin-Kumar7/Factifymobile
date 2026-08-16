"""M04 — context propagation, mandatory redaction, and provider accounting."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.observability import REQUEST_ID_HEADER, metrics
from app.observability.context import bind_case, current_request_id, request_context
from app.observability.logging import ContextFormatter, configure, event

pytestmark = pytest.mark.unit


@pytest.fixture
def captured(caplog: pytest.LogCaptureFixture) -> Any:
    """Render records through the real formatter, so redaction is exercised."""
    formatter = ContextFormatter("%(asctime)s %(level)s %(name)s %(message)s")

    def rendered() -> list[dict[str, Any]]:
        return [json.loads(formatter.format(record)) for record in caplog.records]

    caplog.set_level(logging.INFO)
    return rendered


class TestRequestContext:
    def test_identifier_is_available_inside_the_block(self) -> None:
        with request_context("req-123"):
            assert current_request_id() == "req-123"

    def test_identifier_does_not_leak_outside_the_block(self) -> None:
        with request_context("req-123"):
            pass

        assert current_request_id() is None

    def test_case_binds_to_the_active_context(self) -> None:
        """The request id is known before the case; both appear once it exists."""
        with request_context("req-123"):
            bind_case("case-abc")
            from app.observability.context import current

            ctx = current()
            assert ctx is not None
            assert ctx.case_id == "case-abc"

    def test_nested_contexts_restore_the_outer_one(self) -> None:
        with request_context("outer"):
            with request_context("inner"):
                assert current_request_id() == "inner"
            assert current_request_id() == "outer"


class TestFixedFieldSet:
    def test_event_carries_the_skeleton(self, captured: Any) -> None:
        logger = logging.getLogger("facify.test")

        # Rendered inside the block: the formatter reads the context at format time,
        # which is when the real handler emits.
        with request_context("req-1"):
            bind_case("case-1")
            event(
                logger,
                "provider called",
                module="factcheck",
                outcome="ok",
                provider="factcheck",
                model_id="model-x",
                latency_ms=42.0,
            )
            record = captured()[0]
        assert record["request_id"] == "req-1"
        assert record["case_id"] == "case-1"
        assert record["module"] == "factcheck"
        assert record["outcome"] == "ok"
        assert record["provider"] == "factcheck"
        assert record["model_id"] == "model-x"
        assert record["latency_ms"] == 42.0

    def test_skip_reason_is_recorded(self, captured: Any) -> None:
        """A skipped provider must say so and say why — the response quotes this."""
        logger = logging.getLogger("facify.test")

        with request_context("req-1"):
            event(
                logger,
                "provider skipped",
                module="vision",
                outcome="skipped",
                provider="vision",
                failure_reason="capacity limited",
            )

        record = captured()[0]
        assert record["outcome"] == "skipped"
        assert record["failure_reason"] == "capacity limited"


class TestRedaction:
    """Redaction is applied at the formatter: it cannot be forgotten at a call site."""

    def test_credentials_never_reach_a_log(self, captured: Any) -> None:
        logger = logging.getLogger("facify.test")

        event(
            logger,
            "configured",
            module="config",
            outcome="ok",
            api_key="super-secret-value",
            token="another-secret",
        )

        rendered = json.dumps(captured()[0])
        assert "super-secret-value" not in rendered
        assert "another-secret" not in rendered

    def test_exif_location_never_reaches_a_log(self, captured: Any) -> None:
        logger = logging.getLogger("facify.test")

        event(logger, "exif read", module="intake", outcome="ok", latitude=28.61, longitude=77.20)

        rendered = json.dumps(captured()[0])
        assert "28.61" not in rendered
        assert "77.2" not in rendered

    def test_article_bodies_are_reported_by_size_not_content(self, captured: Any) -> None:
        logger = logging.getLogger("facify.test")

        event(
            logger,
            "extracted",
            module="extraction",
            outcome="ok",
            article_body="a genuinely long article body " * 50,
        )

        detail = captured()[0]["detail"]
        assert "genuinely long article" not in json.dumps(detail)
        assert "content omitted" in detail["article_body"]

    def test_unexpectedly_large_values_are_truncated(self, captured: Any) -> None:
        logger = logging.getLogger("facify.test")

        event(logger, "big", module="test", outcome="ok", note="x" * 5000)

        assert len(json.dumps(captured()[0]["detail"]["note"])) < 300


class TestProviderMetrics:
    def setup_method(self) -> None:
        metrics.reset()

    def test_successes_and_failures_are_counted_separately(self) -> None:
        metrics.record_success("vision", latency_ms=120.0)
        metrics.record_success("vision", latency_ms=80.0)
        metrics.record_failure("vision", latency_ms=200.0)

        snapshot = metrics.snapshot()["vision"]
        assert snapshot["calls"] == 3
        assert snapshot["successes"] == 2
        assert snapshot["failures"] == 1
        assert snapshot["failure_rate"] == pytest.approx(1 / 3, abs=1e-4)

    def test_skips_are_not_failures(self) -> None:
        """A provider skipped for budget did not fail; conflating them hides the
        honest degradation path behind what looks like an outage."""
        metrics.record_skip("vision", "capacity limited")
        metrics.record_skip("vision", "capacity limited")

        snapshot = metrics.snapshot()["vision"]
        assert snapshot["skips"] == 2
        assert snapshot["calls"] == 0
        assert snapshot["failure_rate"] == 0.0
        assert snapshot["skip_reasons"] == {"capacity limited": 2}

    def test_latency_percentiles_are_reported(self) -> None:
        for value in range(1, 101):
            metrics.record_success("llm", latency_ms=float(value))

        snapshot = metrics.snapshot()["llm"]
        assert snapshot["median_ms"] == pytest.approx(51.0, abs=1.0)
        assert snapshot["p95_ms"] == pytest.approx(96.0, abs=1.0)

    def test_percentiles_are_none_before_any_call(self) -> None:
        metrics.record_skip("archive", "disabled")

        assert metrics.snapshot()["archive"]["median_ms"] is None


class TestMiddleware:
    def test_response_carries_a_request_identifier(self) -> None:
        configure("INFO")
        with TestClient(create_app(Settings(_env_file=None))) as client:
            response = client.get("/healthz")

        assert response.headers[REQUEST_ID_HEADER]

    def test_caller_supplied_identifier_is_honoured(self) -> None:
        with TestClient(create_app(Settings(_env_file=None))) as client:
            response = client.get("/healthz", headers={REQUEST_ID_HEADER: "caller-abc123"})

        assert response.headers[REQUEST_ID_HEADER] == "caller-abc123"

    def test_hostile_caller_identifier_is_replaced(self) -> None:
        """The inbound id lands in every log line for the request; it is untrusted."""
        with TestClient(create_app(Settings(_env_file=None))) as client:
            response = client.get(
                "/healthz", headers={REQUEST_ID_HEADER: "a\nb injected=1 " + "x" * 500}
            )

        returned = response.headers[REQUEST_ID_HEADER]
        assert "\n" in returned or " " in returned or len(returned) <= 64
        assert "injected" not in returned
