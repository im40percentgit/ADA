"""
Ada configuration via Pydantic Settings + TOML.

API keys are never stored in config — only the env var name is stored
(api_key_env pattern). The actual key is resolved at runtime via os.environ.

@decision DEC-CORE-002
@title SQLite via aiosqlite for state
@status accepted
@rationale Lightweight, zero-dependency, async-compatible. Suitable for
    single-process deployment in Phase 1. Can be swapped for PostgreSQL
    later by replacing StateManager without touching agent code.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# LLM mode type
# ---------------------------------------------------------------------------

LLMMode = Literal["claude", "offline", "dual"]
"""
Three-mode LLM selector.

claude  — all agents route to Claude tiers defined in model_routing.profiles.
offline — all agents route to the single offline_tier (local llama.cpp).
dual    — honor profiles + agent_mapping as written in TOML/system_settings.
"""


# ---------------------------------------------------------------------------
# Sub-config models
# ---------------------------------------------------------------------------

class ClaudeConfig(BaseModel):
    api_key_env: str = "ANTHROPIC_API_KEY"

    @property
    def api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "")
        return key


class OpenAICompatConfig(BaseModel):
    base_url: str = "http://localhost:8080/v1"
    api_key_env: str = "OPENAI_API_KEY"
    model: str = "local-model"

    @property
    def api_key(self) -> str:
        return os.environ.get(self.api_key_env, "none")


class LLMConfig(BaseModel):
    provider: str = "claude"
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 1024
    temperature: float = 0.7
    timeout: float = 60.0  # seconds — asyncio.wait_for() wraps all llm.complete() calls
    mode: LLMMode = "dual"
    claude: ClaudeConfig = ClaudeConfig()
    openai_compat: OpenAICompatConfig = OpenAICompatConfig()

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"claude", "openai_compat"}
        if v not in allowed:
            raise ValueError(f"provider must be one of {allowed}, got {v!r}")
        return v


class AgentConfig(BaseModel):
    enabled: bool = True
    timeout_seconds: float = 30.0  # Per-agent LLM call timeout (Phase 11a)


class DailySummaryConfig(BaseModel):
    """Configuration for the DailySummaryGenerator infrastructure subscriber."""

    enabled: bool = True
    debounce_seconds: float = 1800.0  # 30 minutes — wait for last session of day
    timeout_seconds: float = 60.0


class BoardSuggestionConfig(BaseModel):
    """Configuration for the board suggestion agent (Phase 9b)."""

    enabled: bool = False
    debounce_seconds: float = 5.0
    timeout_seconds: float = 30.0


class VerdictConfig(BaseModel):
    """Configuration for the nightly verdict cron (Phase 15+ M3).

    nightly_cron_enabled: Set False to disable the background cron entirely.
    cron_hour:            Hour (0-23, local to cron_timezone) when the cron fires.
    cron_minute:          Minute (0-59) when the cron fires.
    cron_timezone:        IANA timezone name for the firing schedule.

    @decision DEC-VERDICT-009: verdict-generation schedule lives in TOML
    (config.verdict.*), not the system_settings DB table. Rationale: cron
    schedule is deploy-config (when does the LLM run); user-runtime config
    (when does the caregiver get pinged) is a SEPARATE schedule that arrives
    in M4 with the push, and that one will use system_settings for runtime
    hot-swap.
    """

    nightly_cron_enabled: bool = True
    cron_hour: int = 22
    cron_minute: int = 30
    cron_timezone: str = "UTC"


class ProgressReportConfig(BaseModel):
    """Configuration for the progress report endpoint (Phase 12a)."""

    cache_ttl_seconds: int = 3600


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker thresholds (Phase 11a resilience)."""

    failure_threshold: int = 5
    failure_window_seconds: float = 60.0
    recovery_timeout_seconds: float = 120.0


class ResilienceConfig(BaseModel):
    """Resilience settings for all agents (Phase 11a)."""

    circuit_breaker: CircuitBreakerConfig = CircuitBreakerConfig()


class NotificationThrottleConfig(BaseModel):
    """Per-user, per-event-type throttle and deduplication settings (Phase 11b).

    throttle_window_seconds: minimum seconds between two notifications of the
        same event_type to the same user. Crisis events bypass this.
    dedup_window_seconds: if the exact same dedup_key was sent within this
        window, suppress the duplicate regardless of event type.

    @decision DEC-NOTIF-009
    @title Throttle via persistent notification_throttle_log in SQLite
    @status accepted
    @rationale In-memory throttle would reset on restart, silently allowing
        a flood after every redeploy. Persistent log gives accurate suppression
        across restarts and doubles as an audit trail. The table is pruned of
        records older than max(throttle, dedup) window on every write to cap
        growth without requiring a scheduled job.
    """

    throttle_window_seconds: float = 300.0   # 5 minutes per event type
    dedup_window_seconds: float = 30.0        # 30 seconds per exact duplicate


class NotificationConfig(BaseModel):
    """Push notification settings (Phase 10 + 11b).

    VAPID keys are read from environment variables at runtime — never stored
    in config files.  Set ADA_VAPID_PRIVATE_KEY and ADA_VAPID_PUBLIC_KEY
    in production.  When vapid_private_key is empty, the dispatcher skips
    real pushes (safe for testing and local dev).
    """

    enabled: bool = True
    vapid_private_key_env: str = "ADA_VAPID_PRIVATE_KEY"
    vapid_public_key_env: str = "ADA_VAPID_PUBLIC_KEY"
    vapid_email: str = "mailto:admin@ada.local"
    throttle: NotificationThrottleConfig = NotificationThrottleConfig()


class AgentsConfig(BaseModel):
    wellness_companion: AgentConfig = AgentConfig()
    crisis_monitor: AgentConfig = AgentConfig()
    medication_manager: AgentConfig = AgentConfig()
    cognitive_assessor: AgentConfig = AgentConfig()
    emotion_analyzer: AgentConfig = AgentConfig()
    knowledge_agent: AgentConfig = AgentConfig()
    daily_summary: DailySummaryConfig = DailySummaryConfig()
    board_suggestion: BoardSuggestionConfig = BoardSuggestionConfig()


class AuthConfig(BaseModel):
    """JWT authentication settings.

    The signing secret is read from an env var at runtime — never stored in config files.
    """

    secret_key_env: str = "ADA_JWT_SECRET"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    enabled: bool = True  # Set False in tests via dependency override

    @property
    def secret_key(self) -> str:
        import os
        key = os.environ.get(self.secret_key_env, "")
        if not key:
            # In development fall back to an insecure default so the server
            # starts without configuration; warn loudly.
            import logging
            logging.getLogger(__name__).warning(
                "ADA_JWT_SECRET not set — using insecure dev default. "
                "Set this env var in production."
            )
            return "dev-insecure-secret-change-in-production"
        return key


class STTConfig(BaseModel):
    """Phase 7 speech-to-text configuration (faster-whisper).

    model_size: faster-whisper model variant — smaller is faster but less
        accurate. Defaults to "large-v3-turbo" (DEC-ML-018).
    language: ISO 639-1 language code, or None for auto-detect.
    compute_type: CTranslate2 quantisation for CPU inference.
    min_confidence: drop transcriptions below this confidence (0.0-1.0).
    vad_filter: enable Silero VAD to strip non-speech before Whisper.
    vad_threshold: Silero VAD speech probability threshold (0.0-1.0).

    @decision DEC-ML-018
    @title faster-whisper default model_size bumped from base to large-v3-turbo
    @status accepted
    @rationale large-v3-turbo delivers significantly higher transcription
        accuracy than base (~WER improvement) at 2-3x the memory cost, which
        is acceptable on the target N=1 deployment hardware. The override
        ADA_STT__MODEL_SIZE=base is available for low-RAM hosts. CI tests
        that need fast inference should set model_size explicitly (e.g.
        STTConfig(model_size="small")) rather than relying on the default.
    """

    model_size: str = "large-v3-turbo"
    language: str | None = None
    compute_type: str = "int8"
    min_confidence: float = 0.4
    vad_filter: bool = False
    vad_threshold: float = 0.5


class MultimodalConfig(BaseModel):
    """Phase 4 multimodal pipeline configuration."""

    enabled: bool = False  # Off by default until Phase 4b ML agents are ready
    sensor_simulator_preset: str = "relaxed"
    sensor_simulator_interval: float = 1.0  # seconds between readings
    # Phase 4b: per-agent toggles
    voice_analysis_enabled: bool = True
    face_analysis_enabled: bool = True
    physiological_analysis_enabled: bool = True
    physiological_window_size: int = 30
    physiological_trigger_interval: int = 10
    # Phase 4c: Fusion
    fusion_enabled: bool = True
    fusion_staleness_half_life: float = 10.0
    fusion_min_weight: float = 0.01
    # Phase 7: STT
    stt_enabled: bool = False


class TTSConfig(BaseModel):
    """Phase 7 text-to-speech configuration."""

    enabled: bool = False  # Off by default
    provider: str = "kokoro"
    voice_model: str = ""  # Empty = use provider default
    fallback_provider: str = "piper"
    fallback_voice_model: str = "data/voices/piper/en_US-lessac-medium.onnx"
    sample_rate: int = 24000  # Kokoro native rate; Piper was 22050
    sentence_streaming: bool = True

    @field_validator("provider", "fallback_provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"", "piper", "kokoro"}
        if v not in allowed:
            raise ValueError(f"TTS provider must be one of {allowed}, got {v!r}")
        return v


class RateLimitConfig(BaseModel):
    """
    In-process sliding window rate limiting configuration.

    @decision DEC-SEC-001
    @title In-memory sliding window rate limiter (no Redis)
    @status accepted
    @rationale Single-process deployment (SQLite write-contention). Revisit for
        multi-instance deployments. Each IP gets its own deque of timestamps;
        entries older than 60 s are pruned on each request.
    """

    enabled: bool = True
    auth_requests_per_minute: int = 10
    api_requests_per_minute: int = 120
    ws_connections_per_ip: int = 5


class SecurityConfig(BaseModel):
    """
    Security policy: body size limits and strict CORS headers.

    @decision DEC-SEC-002
    @title Security headers + body size at middleware level
    @status accepted
    @rationale Defense-in-depth. Path-differentiated body limits allow media
        routes to receive larger payloads (10 MB) while keeping the general
        API surface small (1 MB). Headers are injected once at the middleware
        layer so every route benefits without per-handler boilerplate.
    """

    max_body_size_bytes: int = 1_048_576         # 1 MB
    max_media_body_size_bytes: int = 10_485_760  # 10 MB
    cors_allow_methods: list[str] = [
        "GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"
    ]
    cors_allow_headers: list[str] = [
        "Authorization",
        "Content-Type",
        "X-Request-ID",
        "X-Session-ID",
        "Accept",
        "Origin",
    ]


class NetworkConfig(BaseModel):
    """LAN and network binding configuration (Phase 11b PWA).

    Separates network-layer concerns (bind address, CORS allowlist) from
    general API config so the LAN dev script can override bind_host and
    cors_origins without touching the API host/port used by uvicorn.

    @decision DEC-PWA-003
    @title Separate NetworkConfig for LAN bind/CORS override
    @status accepted
    @rationale The existing APIConfig.host controls the uvicorn bind address.
        Adding a dedicated NetworkConfig lets the LAN dev script set
        ADA_NETWORK__BIND_HOST=0.0.0.0 and inject LAN origins into CORS
        without ambiguity. app.py reads network.cors_origins and merges them
        with api.cors_origins so localhost and LAN origins coexist.
    """

    bind_host: str = "127.0.0.1"
    cors_origins: list[str] = ["http://localhost:5173"]


class APIConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173"]


class DatabaseConfig(BaseModel):
    path: str = "data/ada.db"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "console"  # "console" | "json"
    request_id_header: str = "X-Request-ID"
    access_log: bool = True
    slow_request_threshold_ms: int = 2000


# ---------------------------------------------------------------------------
# Model routing config
# ---------------------------------------------------------------------------

class CompanionConfig(BaseModel):
    """Companion persona defaults (Phase 13a).

    These are used when a user has no saved preferences in the database.
    default_voice must be one of the values accepted by the companion_preferences
    table CHECK constraint: male, female, neutral.
    """

    default_name: str = "Ada"
    default_voice: str = "female"


class ModelProfile(BaseModel):
    """Configuration for a single model profile."""
    provider: str  # "claude" | "openai_compat"
    model: str
    max_tokens: int = 1024
    temperature: float = 0.7
    base_url: str | None = None  # for openai_compat
    api_key_env: str | None = None
    # DEC-LLM-007: send system prompt as structured cache_control block.
    prompt_cache_system: bool = False

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"claude", "openai_compat"}
        if v not in allowed:
            raise ValueError(f"provider must be one of {allowed}, got {v!r}")
        return v


class ModelRoutingConfig(BaseModel):
    """Per-agent model routing configuration."""
    profiles: dict[str, ModelProfile] = {}
    agent_mapping: dict[str, str] = {}
    default_profile: str = "conversational"


class RetentionConfig(BaseModel):
    """Data retention policy configuration (Phase 14c).

    Controls how long different categories of data are retained before they
    become eligible for cleanup via the admin retention endpoint.

    session_data_days: retain session records, messages, and related
        analytics (assessments, medications) for this many days.
    audit_log_days: retain audit log entries for this many days. Typically
        longer than session data to satisfy compliance requirements.
    export_temp_days: retain temporary export artefacts for this many days.
        Defined here for future use by a scheduled cleanup job; not yet
        consumed by the retention cleanup endpoint.
    """

    session_data_days: int = 365
    audit_log_days: int = 730
    export_temp_days: int = 7


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------

class AdaConfig(BaseSettings):
    """
    Root Ada configuration.

    Can be loaded from TOML files and overridden by environment variables.
    Env vars use double-underscore nesting: ADA_LLM__PROVIDER=openai_compat
    """

    model_config = SettingsConfigDict(
        env_prefix="ADA_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # @decision DEC-CORE-003
    # @title Env vars override init kwargs (TOML values)
    # @status accepted
    # @rationale pydantic-settings defaults init-kwargs > env-vars. from_toml
    #   passes merged TOML as init kwargs, which silently defeated env-var
    #   overrides despite the class docstring promising the opposite
    #   ("overridden by environment variables"). Swapping env_settings before
    #   init_settings here makes env vars win, restoring documented behavior
    #   and unblocking LAN-dev-mode overrides like ADA_API__HOST=0.0.0.0.
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (env_settings, init_settings, dotenv_settings, file_secret_settings)

    llm: LLMConfig = LLMConfig()
    agents: AgentsConfig = AgentsConfig()
    api: APIConfig = APIConfig()
    network: NetworkConfig = NetworkConfig()
    auth: AuthConfig = AuthConfig()
    database: DatabaseConfig = DatabaseConfig()
    logging: LoggingConfig = LoggingConfig()
    multimodal: MultimodalConfig = MultimodalConfig()
    notifications: NotificationConfig = NotificationConfig()
    stt: STTConfig = STTConfig()
    tts: TTSConfig = TTSConfig()
    rate_limit: RateLimitConfig = RateLimitConfig()
    security: SecurityConfig = SecurityConfig()
    resilience: ResilienceConfig = ResilienceConfig()
    progress_report: ProgressReportConfig = ProgressReportConfig()
    companion: CompanionConfig = CompanionConfig()
    model_routing: ModelRoutingConfig | None = None
    retention: RetentionConfig = RetentionConfig()
    verdict: VerdictConfig = VerdictConfig()

    @classmethod
    def from_toml(cls, *paths: str | Path) -> AdaConfig:
        """
        Load config by merging one or more TOML files left to right.

        Later files override earlier ones. Environment variables always
        take precedence over file values.

        Args:
            *paths: TOML file paths. Non-existent files are silently skipped.

        Returns:
            AdaConfig instance with merged values.
        """
        merged: dict[str, Any] = {}
        for path in paths:
            p = Path(path)
            if not p.exists():
                continue
            with open(p, "rb") as f:
                data = tomllib.load(f)
            _deep_merge(merged, data)

        return cls(**_flatten_config(merged))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> None:
    """Merge override into base in place, recursing into nested dicts."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _flatten_config(data: dict[str, Any]) -> dict[str, Any]:
    """
    Convert raw TOML dict into kwargs suitable for AdaConfig(**kwargs).

    TOML keys with hyphens are converted to underscores.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        normalized_key = key.replace("-", "_")
        if isinstance(value, dict):
            result[normalized_key] = value
        else:
            result[normalized_key] = value
    return result
