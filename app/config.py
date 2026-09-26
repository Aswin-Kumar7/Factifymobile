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

    None of these limits a person's checks; that is the per-user credit book's job
    (`app/accounts`). What is left here protects the account, not the product:

    - `daily_cap` is a spend **alarm**. Crossing it logs a warning once that day and
      calls continue. Zero means no alarm. It used to refuse, which made it a product
      limit shared by everyone — about 27 checks a day for the whole service.
    - `daily_hard_cap` is the emergency stop against a runaway bug: past it, calls
      are refused. Zero, the default, means never.
    - `per_minute_cap` paces rather than refuses: a call beyond it waits for room in
      the window, because the ceiling it mirrors (a provider's own rate limit) clears
      in seconds.
    """

    model_config = {"frozen": True}

    enabled: bool = False
    api_key: SecretStr | None = None
    daily_cap: int = Field(default=0, ge=0)
    daily_hard_cap: int = Field(default=0, ge=0)
    per_minute_cap: int = Field(default=0, ge=0)
    timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    max_retries: int = Field(default=1, ge=0, le=5)

    # Where the provider lives. Configurable rather than hard-coded because the same
    # credential can front different surfaces — a Gemini key works against the
    # Generative Language API, while Vertex AI is a different host *and* a different
    # auth scheme. Keeping the URL in configuration means switching surface is an
    # environment change, and a wrong one fails at boot rather than at first call.
    #
    # `{model}` is substituted from `models.extraction` / `models.escalation`.
    endpoint: str = ""

    # Which wire dialect the endpoint speaks: "gemini" (the Generative Language API's
    # generateContent, x-goog-api-key) or "openai" (chat/completions, bearer token —
    # Groq, OpenRouter, Azure). The model is a swappable dependency by design, so the
    # provider is an environment change, not a code change. See app/extraction/
    # model_wire.py. Vision (FACTIFY_VISION__*) has its own block and stays whatever it
    # is set to, because the OpenAI-compatible free tiers expose no vision model.
    api_format: str = Field(default="gemini", pattern="^(gemini|openai)$")

    @model_validator(mode="after")
    def _enabled_providers_need_a_credential(self) -> Self:
        if self.enabled and self.api_key is None:
            raise ValueError(
                "provider is enabled but no api_key was supplied; "
                "set the credential in the server environment or disable the provider"
            )
        return self

    @model_validator(mode="after")
    def _bearer_endpoints_are_rejected(self) -> Self:
        """Vertex AI cannot be driven with an API key, so refuse it explicitly.

        The Gemini format authenticates with an `x-goog-api-key` header. Vertex AI
        wants an OAuth bearer token from a service account, so pointing this
        configuration at `aiplatform.googleapis.com` would produce 401s on every
        call. Naming the reason at boot is worth more than a stack of auth failures
        that look like an outage. Only relevant to the Gemini format: an
        openai-format endpoint carries its own bearer token and is not Vertex.
        """
        is_vertex = self.endpoint and "aiplatform.googleapis.com" in self.endpoint
        if self.api_format == "gemini" and is_vertex:
            raise ValueError(
                "this endpoint is Vertex AI, which authenticates with an OAuth bearer "
                "token rather than an API key. Use the Generative Language API "
                "(generativelanguage.googleapis.com) with a Gemini API key, or add "
                "service-account auth before pointing at Vertex"
            )
        return self

    @property
    def usable(self) -> bool:
        """Enabled and credentialled.

        The governor's question, deliberately not including the endpoint: quota
        accounting and transport are separate concerns, and a component that only
        meters calls should not need a URL to do it. A daily cap no longer decides it:
        the cap is an alarm, not a permission.
        """
        return self.enabled and self.api_key is not None

    @property
    def is_callable(self) -> bool:
        """Usable *and* has somewhere to send the request.

        The caller's question. Checked at boot by `Settings` rather than enforced
        here, because an enabled provider with no endpoint would otherwise pass the
        governor and fail every call — and downstream that reads as "the source had
        nothing" rather than "we were misconfigured".
        """
        return self.usable and bool(self.endpoint)


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

    Environment variables use the ``FACTIFY_`` prefix and ``__`` for nesting, so a
    provider credential is supplied as ``FACTIFY_VISION__API_KEY``. Credentials are
    read from the server environment only.
    """

    model_config = SettingsConfigDict(
        env_prefix="FACTIFY_",
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

    # Signs result receipts (M42). Also not a provider credential: it signs our own
    # attestations rather than authenticating us to anyone.
    #
    # Absent means receipts are not issued. `ReceiptSigner` refuses an empty key
    # rather than signing with a default, because a receipt signed with a value
    # anyone could guess verifies for anyone and is worse than no receipt at all —
    # it looks like tamper-evidence without being any.
    receipt_signing_key: SecretStr | None = None

    models: ModelSettings = ModelSettings()
    limits: LimitSettings = LimitSettings()

    # Optional providers. Every default is off, and no default enables anything
    # metered — an accidental deploy must cost nothing and reach for nothing.
    llm: ProviderSettings = ProviderSettings()
    factcheck: ProviderSettings = ProviderSettings()
    vision: ProviderSettings = ProviderSettings()
    archive: ProviderSettings = ProviderSettings()
    # Live web search — the open-web evidence path. Off by default like the rest.
    websearch: ProviderSettings = ProviderSettings()

    # Which search provider `websearch` speaks to: "tavily" (search + clean extract in
    # one call) or "exa" (neural search with page text). Determines the request shape
    # and auth header, exactly as api_format does for the LLM.
    websearch_provider: str = Field(default="tavily", pattern="^(tavily|exa)$")

    # Whether the ingested local corpus is searched for evidence. Off by default.
    #
    # The corpus stopped updating on 2026-08-18, so for anything recent it can only
    # offer old articles on a nearby topic. It ran first on every claim, cost up to
    # six model reads per claim, and supplied 11% of all stored evidence. It stays
    # built — origin counting still reads its stored signatures — and comes back with
    # FACTIFY_CORPUS_RETRIEVAL=true once ingestion runs again.
    corpus_retrieval: bool = False

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

        # An enabled provider with no endpoint is a credential with nowhere to send
        # it: it passes the governor, spends a unit, fails, and the failure reads
        # downstream as "the source had nothing to say". Refusing to boot turns a
        # silent wrong answer into a loud configuration error.
        stranded = [
            name
            for name, provider in self.providers.items()
            if provider.usable and not provider.endpoint
        ]
        if stranded:
            raise ValueError(
                f"enabled with a credential but no endpoint: {', '.join(sorted(stranded))}. "
                "Set FACTIFY_<PROVIDER>__ENDPOINT or disable the provider"
            )

        return self

    @property
    def providers(self) -> dict[str, ProviderSettings]:
        """Every external provider by name, for the governor and the ops report."""
        return {
            "llm": self.llm,
            "factcheck": self.factcheck,
            "vision": self.vision,
            "archive": self.archive,
            "web_search": self.websearch,
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
