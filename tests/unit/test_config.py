"""M02 — configuration is typed, credential-free by default, and fails fast."""

import pytest
from pydantic import ValidationError

from app.config import Environment, ProviderSettings, Settings

# A real endpoint, because an enabled provider without one now refuses to boot.
VISION_ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"

pytestmark = pytest.mark.unit


def _settings(**overrides: object) -> Settings:
    """Build settings from explicit values, ignoring any ambient environment."""
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


class TestDefaults:
    def test_no_provider_is_enabled_by_default(self) -> None:
        """An accidental deploy must reach for nothing and cost nothing."""
        settings = _settings()

        assert all(not provider.enabled for provider in settings.providers.values())
        assert all(not provider.usable for provider in settings.providers.values())

    def test_no_provider_has_a_nonzero_cap_by_default(self) -> None:
        settings = _settings()

        assert all(provider.daily_cap == 0 for provider in settings.providers.values())

    def test_defaults_to_local_environment(self) -> None:
        assert _settings().environment is Environment.LOCAL


class TestValidation:
    def test_enabled_provider_without_credential_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="no api_key"):
            ProviderSettings(enabled=True)

    def test_enabled_llm_without_a_model_id_is_rejected(self) -> None:
        """Model identifiers are configuration; an enabled model with no id is a bug."""
        with pytest.raises(ValidationError, match=r"models\.extraction is unset"):
            _settings(llm={"enabled": True, "api_key": "k", "daily_cap": 10})

    def test_non_local_environment_requires_a_database(self) -> None:
        with pytest.raises(ValidationError, match="database_url is required"):
            _settings(environment="prod")

    def test_unknown_settings_are_rejected(self) -> None:
        """A typo in a deployment variable should fail the boot, not be ignored."""
        with pytest.raises(ValidationError):
            _settings(totally_unknown_key="x")

    def test_negative_cap_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ProviderSettings(daily_cap=-1)


class TestUsability:
    def test_a_daily_cap_no_longer_decides_whether_a_provider_is_used(self) -> None:
        """The daily cap is a spend alarm now, not a permission (2026-09-26)."""
        assert ProviderSettings(enabled=True, api_key="k", daily_cap=0).usable

    def test_a_disabled_provider_is_not_usable(self) -> None:
        assert not ProviderSettings(enabled=False, api_key="k", daily_cap=10).usable

    def test_fully_configured_provider_is_usable(self) -> None:
        provider = ProviderSettings(enabled=True, api_key="k", daily_cap=33)

        assert provider.usable


class TestEnvironmentLoading:
    def test_provider_credential_is_read_from_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FACTIFY_VISION__ENABLED", "true")
        monkeypatch.setenv("FACTIFY_VISION__API_KEY", "from-env")
        monkeypatch.setenv("FACTIFY_VISION__DAILY_CAP", "33")
        monkeypatch.setenv("FACTIFY_VISION__ENDPOINT", VISION_ENDPOINT)

        settings = Settings(_env_file=None)

        assert settings.vision.usable
        assert settings.vision.api_key is not None
        assert settings.vision.api_key.get_secret_value() == "from-env"

    def test_a_credential_with_no_endpoint_refuses_to_boot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A provider with nowhere to send the request passes the governor, spends a
        unit, and fails — which downstream reads as "the source had nothing"."""
        monkeypatch.setenv("FACTIFY_VISION__ENABLED", "true")
        monkeypatch.setenv("FACTIFY_VISION__API_KEY", "from-env")
        monkeypatch.setenv("FACTIFY_VISION__DAILY_CAP", "33")

        with pytest.raises(ValidationError, match="no endpoint"):
            Settings(_env_file=None)

    def test_vertex_ai_is_refused_by_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """It authenticates with an OAuth bearer token, not the x-goog-api-key header
        every provider here sends, so it would 401 on every call."""
        monkeypatch.setenv("FACTIFY_LLM__ENABLED", "true")
        monkeypatch.setenv("FACTIFY_LLM__API_KEY", "k")
        monkeypatch.setenv("FACTIFY_LLM__DAILY_CAP", "50")
        monkeypatch.setenv(
            "FACTIFY_LLM__ENDPOINT",
            "https://us-central1-aiplatform.googleapis.com/v1/projects/p/locations/"
            "us-central1/publishers/google/models/{model}:generateContent",
        )

        with pytest.raises(ValidationError, match="Vertex AI"):
            Settings(_env_file=None)

    def test_a_disabled_provider_needs_no_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The default configuration must boot with nothing set at all."""
        monkeypatch.setenv("FACTIFY_VISION__ENABLED", "false")

        settings = Settings(_env_file=None)

        assert not settings.vision.usable

    def test_every_provider_can_be_disabled_by_configuration_alone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The Day 13 fallback drill: turn each provider off without touching code."""
        for name in ("LLM", "FACTCHECK", "VISION", "ARCHIVE"):
            monkeypatch.setenv(f"FACTIFY_{name}__ENABLED", "false")

        settings = Settings(_env_file=None)

        assert all(not provider.usable for provider in settings.providers.values())


def test_the_migration_runner_and_the_pool_name_the_same_schema() -> None:
    """They moved apart once, silently, and nothing noticed.

    A product rename's search-and-replace set the runner's schema to "factify" while
    the database — and the pool's search path, after a hurried fix — still said
    "facify". The service kept working, because it never runs migrations at boot,
    and the next migration would have created an empty second schema and applied
    everything into it.
    """
    from app.db.migrate import SCHEMA
    from app.db.pool import SEARCH_PATH

    assert SEARCH_PATH.split(",")[0] == SCHEMA


def test_no_numbered_migration_renames_the_schema() -> None:
    """A schema rename must never be picked up by the forward-only runner.

    It has to land together with code changes, so it lives in `migrations/manual/`.
    A numbered copy would rename the live schema on the next run and break every
    query that still used the old name.
    """
    from app.db.migrate import discover

    for migration in discover():
        assert "RENAME TO" not in migration.sql.upper() or "SCHEMA" not in migration.sql.upper()
