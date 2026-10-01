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
from urllib.parse import urlsplit

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
    # The account a key belongs to, for providers that take the two separately
    # (Sightengine's api_user beside its api_secret). An identifier, not a secret.
    account: str | None = None
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


class AuthSettings(BaseModel):
    """Sign-in (Supabase Auth) and the per-person credit book.

    `anon_key` is Supabase's public client key: made to ship in apps, so the app is
    handed it by `/v1/auth/config`. Kept in `.env` all the same, beside the rest of
    the project's configuration rather than in git. `supabase_url` defaults to the
    project the database belongs to.
    """

    model_config = {"frozen": True}

    supabase_url: str | None = None
    anon_key: SecretStr | None = None
    # Whether a check needs a signed-in person. It does: an account is compulsory.
    # Off only for a deliberately open server, and for tests that are not about
    # accounts (tests/conftest.py).
    required: bool = True
    # Credits a new account starts with on top of its Free plan; 0 since plans (0008).
    signup_credits: int = Field(default=0, ge=0)
    check_cost: int = Field(default=1, ge=0)
    # Off until plans exist: usage is recorded, nothing is refused.
    enforce_credits: bool = False
    # This server's own sign-in (app/accounts/local_auth.py).
    session_days: int = Field(default=30, gt=0)
    min_password_length: int = Field(default=8, ge=6)
    # Google sign-in: a Google Cloud OAuth client (web application). Off until both
    # are set; `public_url` is this server as the phone's browser reaches it, and
    # `<public_url>/v1/auth/google/callback` must be an authorised redirect URI.
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    public_url: str | None = None
    # A video check (speech read, frames checked) costs more than one of text.
    video_check_cost: int = Field(default=3, ge=0)
    # The website, where a Google sign-in started on the web returns. Defaults to
    # public_url (the same address, with Caddy sending /v1 to the API).
    web_url: str | None = None
    # Factify's own admins, besides accounts marked is_staff in the database.
    staff_emails: tuple[str, ...] = ()


class BillingSettings(BaseModel):
    """Razorpay, for organisations buying credits. Test keys move no real money."""

    model_config = {"frozen": True}

    razorpay_key_id: str | None = None
    razorpay_key_secret: SecretStr | None = None
    razorpay_webhook_secret: SecretStr | None = None
    # How often the server bills last month's extra usage (0008); 0 is never (then
    # POST /v1/admin/billing/close-month does it by hand). Each month is billed once.
    extra_usage_billing_hours: float = Field(default=6.0, ge=0)


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


class LocalModelSettings(BaseModel):
    """The models we run on our own server instead of another company's API.

    Each one is used only when its files are in `directory` and its libraries are
    installed (`uv sync --extra models`); otherwise that check says "not checked",
    never a made-up answer. Set FACTIFY_LOCAL__<NAME>=false to switch one off.
    """

    model_config = {"frozen": True}

    # Relative to the working directory; `.cache/` is never committed.
    directory: str = ".cache/models"
    # CPU threads each model may use per call.
    threads: int = Field(default=4, ge=1, le=32)
    # AI-made pictures: Community Forensics, retrained August 2026.
    pictures: bool = True
    # DDA (NeurIPS 2025) as a second opinion that must agree. Off: after a WhatsApp-style
    # send it caught 0 of 36 GPT-Image-2 pictures, so requiring agreement turned 23 of
    # the main model's 36 catches into "unclear" (scripts/eval_models.py, 2026-09-28).
    second_opinion: bool = False
    # Face swaps: YuNet finds faces, GenD judges them. Off: measured on real photos it
    # scored 4 of 9 real faces 90% or more "swapped" (Celeb-DF samples and our own test
    # pictures, 2026-09-28). A face check that tells people a real face is fake does
    # more harm than none; it stays off until it is calibrated on real Indian faces.
    faces: bool = False
    # Face swaps in a video, which is where they matter. On 25 real and 25 face-swapped
    # videos (Google's DeepFakeDetection set, 2026-09-30) GenD separated them at AUROC
    # 0.90, and past 0.8 it flagged no real video and caught 13 of the 25 swaps. That
    # set is close to what GenD was trained on, so real forwards will do worse. Loaded
    # on the first video, not at startup (1.26 GB).
    video_faces: bool = True
    # Cloned voices in a video's sound: Spectra-AASIST. Experimental.
    voice: bool = True
    # What is said in a video: Whisper through faster-whisper, its files in
    # `directory`/faster-whisper-<speech_model>. "small" (486 MB, about 0.5 GB of
    # memory) read Tamil nearly exactly and Hindi with spelling slips the claim reader
    # sees past; a larger one reads better and needs three times the memory.
    speech: bool = True
    speech_model: str = "small"
    # Load the video models (faces, voice, speech: about 3 GB together) at startup
    # rather than on the first video, which then took three minutes (2026-09-30). Off
    # by default for a small server; on where memory allows, as for a demo.
    warm_video: bool = False
    # Text in pictures: PaddleOCR's models through RapidOCR.
    ocr: bool = True
    # Which pages speak to a claim, and how: a reranker and two NLI models.
    stance: bool = True


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

    # Where a check's progress events travel between instances (the v5 Checking
    # screen). Unset keeps them in this process, which is right for one instance;
    # with several, a stream can land on another than the check, and a Redis URL
    # (`redis://...`, with the optional `redis` package installed) carries them.
    progress_redis_url: SecretStr | None = None

    models: ModelSettings = ModelSettings()
    limits: LimitSettings = LimitSettings()
    auth: AuthSettings = AuthSettings()
    billing: BillingSettings = BillingSettings()
    local: LocalModelSettings = LocalModelSettings()

    # Optional providers. Every default is off, and no default enables anything
    # metered — an accidental deploy must cost nothing and reach for nothing.
    llm: ProviderSettings = ProviderSettings()
    factcheck: ProviderSettings = ProviderSettings()
    vision: ProviderSettings = ProviderSettings()
    archive: ProviderSettings = ProviderSettings()
    # Live web search — the open-web evidence path. Off by default like the rest.
    websearch: ProviderSettings = ProviderSettings()
    # The AI-generated and face-swap detector (Sightengine). Its readings are
    # advisories: shown beside a picture, never an input to a verdict.
    synthetic: ProviderSettings = ProviderSettings()

    # Which search provider `websearch` speaks to: "tavily" (search + clean extract in
    # one call) or "exa" (neural search with page text). Determines the request shape
    # and auth header, exactly as api_format does for the LLM.
    websearch_provider: str = Field(default="tavily", pattern="^(tavily|exa)$")

    # Translation of claims made in the ten newer Indian languages into English, to
    # find and read English sources (app/extraction/translate.py). "google_free" is
    # Google's undocumented widget endpoint - no key, not covered by Google's terms,
    # can be refused without notice; "google_cloud" is the official API and needs
    # FACTIFY_TRANSLATION_KEY; "off" searches claims in their own words only.
    translation: str = Field(default="google_free", pattern="^(google_free|google_cloud|off)$")
    translation_key: SecretStr | None = None

    # Whether the ingested local corpus is searched for evidence - our own stored
    # articles, searched before the paid web search, which then runs only when they
    # do not settle the claim.
    #
    # Off while the corpus stood still (it stopped at 2026-08-18, when nothing ran
    # ingestion). On again now that ingestion runs on a schedule (below).
    corpus_retrieval: bool = True

    # Whether stored answers are served: a repeat of a checked text, picture or link
    # answered from the verdict cache, and a document's claims from the extraction
    # cache. Off for a test run that must check everything afresh; the fresh
    # answers are still stored.
    cache_reads: bool = True

    # How often, in seconds, the news is collected while the service runs: a small
    # batch of due feeds from data/feeds.json each time. 0 turns the schedule off;
    # `/internal/ingest-tick` still runs a batch when an outside scheduler calls it.
    ingestion_interval_seconds: float = 900

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
            "synthetic": self.synthetic,
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


def supabase_url_for(settings: Settings) -> str | None:
    """The Supabase project URL: configured, or read off the database's own address.

    A Supabase pooler connection's user is `postgres.<project-ref>`, and the project
    answers at `https://<project-ref>.supabase.co`.
    """
    if settings.auth.supabase_url:
        return settings.auth.supabase_url.rstrip("/")
    if settings.database_url is None:
        return None
    parts = urlsplit(str(settings.database_url))
    user, host = parts.username or "", parts.hostname or ""
    if host.endswith(".supabase.com") and user.startswith("postgres."):
        return f"https://{user.split('.', 1)[1]}.supabase.co"
    return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache settings.

    Called once during application construction so an invalid configuration fails at
    boot rather than at first use.
    """
    return Settings()
