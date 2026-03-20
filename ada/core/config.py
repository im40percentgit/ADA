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
from typing import Any

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    model: str = "claude-sonnet-4-5-20250514"
    max_tokens: int = 1024
    temperature: float = 0.7
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


class AgentsConfig(BaseModel):
    therapist: AgentConfig = AgentConfig()
    crisis_monitor: AgentConfig = AgentConfig()
    medication_manager: AgentConfig = AgentConfig()
    cognitive_assessor: AgentConfig = AgentConfig()
    emotion_analyzer: AgentConfig = AgentConfig()
    knowledge_agent: AgentConfig = AgentConfig()


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


class TTSConfig(BaseModel):
    """Phase 7 text-to-speech configuration."""

    enabled: bool = False  # Off by default
    provider: str = "piper"
    voice_model: str = ""  # Empty = use provider default
    sample_rate: int = 22050
    sentence_streaming: bool = True

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"piper"}
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

class ModelProfile(BaseModel):
    """Configuration for a single model profile."""
    provider: str  # "claude" | "openai_compat"
    model: str
    max_tokens: int = 1024
    temperature: float = 0.7
    base_url: str | None = None  # for openai_compat
    api_key_env: str | None = None

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

    llm: LLMConfig = LLMConfig()
    agents: AgentsConfig = AgentsConfig()
    api: APIConfig = APIConfig()
    auth: AuthConfig = AuthConfig()
    database: DatabaseConfig = DatabaseConfig()
    logging: LoggingConfig = LoggingConfig()
    multimodal: MultimodalConfig = MultimodalConfig()
    tts: TTSConfig = TTSConfig()
    rate_limit: RateLimitConfig = RateLimitConfig()
    security: SecurityConfig = SecurityConfig()
    model_routing: ModelRoutingConfig | None = None

    @classmethod
    def from_toml(cls, *paths: str | Path) -> "AdaConfig":
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
