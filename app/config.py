"""Typed configuration (M02).

Two rules shape this module.

**Model identifiers are configuration, never code.** Models rotate; a model name
compiled into a call site is a migration waiting to happen. Every model the system
may invoke is named here and nowhere else.

**Every provider can be switched off without a code change.** The Day 13 gate
requires disabling each optional provider in turn and confirming deterministic
fallback, and the M14 gate requires setting every cap to zero and still producing a
complete, honest, abstaining run. Both are impossible unless enablement and caps are
pure configuration.

Invalid configuration is a boot failure, not a surprise at first use.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Any, Self

from pydantic import BaseModel, Field, PostgresDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    PROD = "prod"


class ProviderSettings(BaseModel):
    """One external provider's operating envelope.

    `daily_cap` is deliberately set *below* the provider's own limit so the system
    degrades on our terms before the provider degrades on its own (codexplan.md §11).
    A cap of zero is a valid, meaningful configuration: the provider is skipped and
    the reason is recorded.
    """

    model_config = {"frozen": True}

    enabled: bool = False
    api_key: SecretStr | None = None
    daily_cap: int = Field(default=0, ge=0)
    per_minute_cap: int = Field(default=0, ge=0)
    timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    max_retries: int = Field(default=1, ge=0, le=5)

    @model_validator(mode="after")
    def _enabled_providers_need_a_credential(self) -> Self:
        if self.enabled and self.api_key is None:
            raise ValueError(
                "provider is enabled but no api_key was supplied; "
                "set the credential in the server environment or disable the provider"
            )
        return self

    @property
    def usable(self) -> bool:
        """Enabled, credentialled, and permitted at least one call per day."""
        return self.enabled and self.api_key is not None and self.daily_cap > 0


class ModelSettings(BaseModel):
    """Model identifiers. No model name appears anywhere else in the codebase.

    `extraction` serves the single structured claim-extraction call per document.
    `escalation` is used only when schema validation fails or the input is unusable,
    and is capped separately (codexplan.md §11).
    """

    model_config = {"frozen": True, "protected_namespaces": ()}

    extraction: str = ""
    escalation: str = ""
    text_embedding: str = ""
    image_embedding: str = ""


class LimitSettings(BaseModel):
    """Resource ceilings enforced before any decode or parse (M10)."""

    model_config = {"frozen": True}

    max_upload_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    max_pdf_pages: int = Field(default=50, gt=0)
    max_video_seconds: int = Field(default=90, gt=0)
    max_video_keyframes: int = Field(default=12, gt=0, le=24)
    max_redirects: int = Field(default=5, ge=0, le=10)
    max_fetch_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    fetch_timeout_seconds: float = Field(default=15.0, gt=0, le=60)
    raw_media_retention_hours: int = Field(default=24, gt=0, le=72)


class Settings(BaseSettings):
    """Application settings, loaded once at startup.

    Environment variables use the ``FACIFY_`` prefix and ``__`` for nesting, so a
    provider credential is supplied as ``FACIFY_VISION__API_KEY``. Credentials are
    read from the server environment only.
    """

    model_config = SettingsConfigDict(
        env_prefix="FACIFY_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        frozen=True,
    )

    environment: Environment = Environment.LOCAL
    database_url: PostgresDsn | None = None
    log_level: str = "INFO"

    # Trigger authentication for the internal ingestion endpoint (M24). Not a
    # provider credential — it authenticates the scheduler to us.
    ingest_trigger_secret: SecretStr | None = None

    models: ModelSettings = ModelSettings()
    limits: LimitSettings = LimitSettings()

    # Optional providers. Every default is off, and no default enables anything
    # metered — an accidental deploy must cost nothing and reach for nothing.
    llm: ProviderSettings = ProviderSettings()
    factcheck: ProviderSettings = ProviderSettings()
    vision: ProviderSettings = ProviderSettings()
    archive: ProviderSettings = ProviderSettings()

    @model_validator(mode="after")
    def _model_ids_required_when_llm_enabled(self) -> Self:
        if self.llm.enabled and not self.models.extraction:
            raise ValueError(
                "llm provider is enabled but models.extraction is unset; "
                "model identifiers are configuration and must be named explicitly"
            )
        return self

    @model_validator(mode="after")
    def _production_requires_a_database(self) -> Self:
        if self.environment is not Environment.LOCAL and self.database_url is None:
            raise ValueError(f"database_url is required in the {self.environment} environment")
        return self

    @property
    def providers(self) -> dict[str, ProviderSettings]:
        """Every external provider by name, for the governor and the ops report."""
        return {
            "llm": self.llm,
            "factcheck": self.factcheck,
            "vision": self.vision,
            "archive": self.archive,
        }

    def redacted(self) -> dict[str, Any]:
        """Configuration safe to log: enablement and caps, never credentials."""
        return {
            "environment": str(self.environment),
            "database_configured": self.database_url is not None,
            "log_level": self.log_level,
            "models": self.models.model_dump(),
            "limits": self.limits.model_dump(),
            "providers": {
                name: {
                    "enabled": provider.enabled,
                    "credentialled": provider.api_key is not None,
                    "usable": provider.usable,
                    "daily_cap": provider.daily_cap,
                    "per_minute_cap": provider.per_minute_cap,
                }
                for name, provider in self.providers.items()
            },
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache settings.

    Called once during application construction so an invalid configuration fails at
    boot rather than at first use.
    """
    return Settings()
