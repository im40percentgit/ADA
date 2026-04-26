"""
Model routing — resolves agent names to LLMProvider instances.

@decision DEC-LLM-002
@title Config-driven per-agent model routing with fallback
@status accepted
@rationale Mental health AI benefits from hybrid models: warm conversational
    models for therapy, reasoning models for clinical assessment. A router
    maps agent names to model profiles, each backed by a pre-instantiated
    provider. Unknown agents fall back to default_profile. When no
    model_routing config exists, falls back to legacy single-provider mode.

@decision DEC-LLM-005
@title Three-mode LLM selector: claude / offline / dual
@status accepted
@rationale The founder runs local llama.cpp for cost/privacy and wants a
    one-click toggle — not a config-file edit. Three modes cover all cases:
    - claude: all agents route to their Claude tier (Opus/Sonnet/Haiku)
    - offline: all agents route to a single openai_compat profile
    - dual (default): honor profiles + agent_mapping as written in TOML,
      giving Claude tiers for cloud agents and offline_tier for local ones.
    Mode resolution order: system_settings DB row > ADA_LLM__MODE env var >
    [llm].mode TOML > default "dual".
    Hot-swap behavior: in-flight LLM calls finish on the old provider; new
    calls take the new mode after the router is rebuilt and atomically
    swapped in AgentRegistry. No mid-stream provider switching occurs.
    verdict.py and progress_report.py re-resolve providers per request via
    router.get_provider(), so they automatically pick up the new router.

@decision DEC-LLM-006
@title Per-tier agent routing
@status accepted
@rationale Three tiers balance cost vs capability for a dementia-care N=1:
    - Opus 4.7 (claude-opus-4-7): cognitive_assessor, crisis_monitor,
      fusion, session_summarizer — deep clinical reasoning, low volume.
    - Sonnet 4.6 (claude-sonnet-4-6): wellness_companion, knowledge_agent,
      treatment_progress, daily_summary, board_suggestion, progress_report,
      medication_manager — warm conversation + summaries.
    - Haiku 4.5 (claude-haiku-4-5-20251001): tts, task_scoring,
      voice_emotion, facial_emotion, transcription, verdict_generator,
      emotion_analyzer, physiological — high-volume, low-stakes.
    In offline mode all agents collapse to a single openai_compat profile
    pointing at the local llama.cpp endpoint.
"""

from __future__ import annotations

import logging
import os

from ada.core.config import AdaConfig, ModelProfile, ModelRoutingConfig
from ada.llm.base import LLMProvider
from ada.llm.factory import create_llm_provider, create_llm_provider_from_profile

logger = logging.getLogger(__name__)

# Agents that belong to each Claude tier in dual/claude mode.
# This is the canonical tier definition — single source of truth.
_OPUS_AGENTS = frozenset({"cognitive_assessor", "crisis_monitor", "fusion", "session_summarizer"})
_SONNET_AGENTS = frozenset({
    "wellness_companion", "knowledge_agent", "treatment_progress",
    "daily_summary", "board_suggestion", "progress_report",
    "medication_manager",
})
_HAIKU_AGENTS = frozenset({
    "tts", "task_scoring", "voice_emotion", "facial_emotion",
    "transcription", "verdict", "emotion_analyzer", "physiological",
})


class ModelRouter:
    """Resolves agent names to LLMProvider instances."""

    def __init__(self, config: ModelRoutingConfig, providers: dict[str, LLMProvider]) -> None:
        self._providers = providers
        self._agent_mapping = config.agent_mapping
        self._default_profile = config.default_profile

    def get_provider(self, agent_name: str) -> LLMProvider:
        """Get the LLM provider assigned to an agent."""
        profile_name = self._agent_mapping.get(agent_name, self._default_profile)
        if profile_name not in self._providers:
            logger.warning(
                "ModelRouter: profile %r not found for agent %r, using default %r",
                profile_name, agent_name, self._default_profile,
            )
            profile_name = self._default_profile
        return self._providers[profile_name]

    def list_profiles(self) -> dict[str, str]:
        """Return agent -> profile mapping for diagnostics."""
        return dict(self._agent_mapping)

    @property
    def provider_names(self) -> list[str]:
        """Return list of available profile names."""
        return list(self._providers.keys())


def make_null_router(provider: LLMProvider | None = None) -> ModelRouter:
    """
    Create a minimal single-provider router for tests and fixtures.

    Wraps a single provider (or None) in a router so test code can pass a
    ModelRouter without setting up a full AdaConfig. All agent names resolve
    to the single provider.

    Args:
        provider: Any LLMProvider instance, or None for headless test fixtures
                  that never actually call the LLM.

    Returns:
        A ModelRouter with one "default" profile mapping to provider.
    """
    fallback_config = ModelRoutingConfig(
        profiles={},
        agent_mapping={},
        default_profile="default",
    )
    return ModelRouter(fallback_config, {"default": provider})  # type: ignore[dict-item]


def _resolve_mode(config: AdaConfig, db_mode: str | None = None) -> str:
    """Resolve LLM mode with priority: DB row > env var > TOML > default.

    Args:
        config: Ada configuration (carries TOML + env-overridden values).
        db_mode: Value from system_settings table, or None if not set.

    Returns:
        One of "claude", "offline", "dual".
    """
    # 1. system_settings DB row (set via PUT /api/admin/settings/llm-mode)
    if db_mode in ("claude", "offline", "dual"):
        return db_mode
    # 2. ADA_LLM__MODE env var (already baked into config.llm.mode by pydantic-settings)
    # 3. [llm].mode in TOML (also in config.llm.mode)
    # 4. Default "dual"
    return config.llm.mode  # pydantic default is "dual"


def create_model_router(config: AdaConfig, db_mode: str | None = None) -> ModelRouter:
    """
    Create a ModelRouter from config with mode-aware profile selection.

    Mode behavior (see DEC-LLM-005):
      claude  — every agent maps to its Claude tier profile.
      offline — every agent maps to offline_tier (single openai_compat provider).
      dual    — pass-through: honor profiles + agent_mapping as written in TOML.

    When no model_routing profiles are configured, falls back to legacy
    single-provider mode regardless of mode setting.

    Args:
        config: Ada configuration instance.
        db_mode: Optional mode override from system_settings table. When
            provided and valid, takes priority over config.llm.mode.

    Returns:
        A configured ModelRouter ready to dispatch LLM calls.
    """
    mode = _resolve_mode(config, db_mode)
    logger.info("ModelRouter: mode=%s", mode)

    if not (config.model_routing and config.model_routing.profiles):
        # Legacy fallback: wrap single provider in a router
        legacy_provider = create_llm_provider(config)
        fallback_config = ModelRoutingConfig(
            profiles={},
            agent_mapping={},
            default_profile="default",
        )
        logger.info("ModelRouter: legacy mode — all agents use single %s provider", config.llm.provider)
        return ModelRouter(fallback_config, {"default": legacy_provider})

    routing_config = config.model_routing

    if mode == "offline":
        return _build_offline_router(config, routing_config)

    if mode == "claude":
        return _build_claude_only_router(config, routing_config)

    # mode == "dual": pass-through
    return _build_dual_router(routing_config)


# ---------------------------------------------------------------------------
# Mode-specific builder helpers
# ---------------------------------------------------------------------------

def _build_dual_router(routing_config: ModelRoutingConfig) -> ModelRouter:
    """Build router that honors profiles + agent_mapping as written in TOML."""
    providers: dict[str, LLMProvider] = {}
    for name, profile in routing_config.profiles.items():
        providers[name] = create_llm_provider_from_profile(profile)
        logger.info("ModelRouter[dual]: created profile %r (provider=%s, model=%s)",
                    name, profile.provider, profile.model)
    return ModelRouter(routing_config, providers)


def _build_claude_only_router(config: AdaConfig, routing_config: ModelRoutingConfig) -> ModelRouter:
    """Build router that forces all agents to their Claude tier profile.

    Only Claude profiles (opus_tier, sonnet_tier, haiku_tier) are instantiated.
    Non-Claude profiles are skipped. The agent_mapping is rebuilt so every
    agent key maps to a Claude tier. Agents not in the tier tables fall back
    to the default_profile (which must be a Claude tier).
    """
    # Collect only Claude profiles
    providers: dict[str, LLMProvider] = {}
    for name, profile in routing_config.profiles.items():
        if profile.provider == "claude":
            providers[name] = create_llm_provider_from_profile(profile)
            logger.info("ModelRouter[claude]: created profile %r (model=%s)", name, profile.model)

    if not providers:
        # No Claude profiles defined — fall back to legacy single provider
        logger.warning("ModelRouter[claude]: no Claude profiles found, falling back to legacy")
        from ada.llm.factory import create_llm_provider
        legacy = create_llm_provider(config)
        fallback = ModelRoutingConfig(profiles={}, agent_mapping={}, default_profile="default")
        return ModelRouter(fallback, {"default": legacy})

    # Rebuild agent_mapping: each agent gets its tier profile if available,
    # otherwise the TOML default_profile (which should be a Claude tier).
    default_claude_profile = routing_config.default_profile
    if default_claude_profile not in providers:
        # Pick whichever Claude profile exists first as default
        default_claude_profile = next(iter(providers))

    new_mapping: dict[str, str] = {}
    for agent in _OPUS_AGENTS:
        new_mapping[agent] = "opus_tier" if "opus_tier" in providers else default_claude_profile
    for agent in _SONNET_AGENTS:
        new_mapping[agent] = "sonnet_tier" if "sonnet_tier" in providers else default_claude_profile
    for agent in _HAIKU_AGENTS:
        new_mapping[agent] = "haiku_tier" if "haiku_tier" in providers else default_claude_profile
    # Also include any extra agents from original mapping
    for agent, original_profile in routing_config.agent_mapping.items():
        if agent not in new_mapping:
            # Map to same Claude tier if the original profile is Claude, else default
            if original_profile in providers:
                new_mapping[agent] = original_profile
            else:
                new_mapping[agent] = default_claude_profile

    claude_routing = ModelRoutingConfig(
        profiles=routing_config.profiles,
        agent_mapping=new_mapping,
        default_profile=default_claude_profile,
    )
    return ModelRouter(claude_routing, providers)


def _build_offline_router(config: AdaConfig, routing_config: ModelRoutingConfig) -> ModelRouter:
    """Build router that collapses all agents to the offline_tier profile.

    If offline_tier is not defined in profiles, synthesizes one from
    config.llm.openai_compat settings.
    """
    if "offline_tier" in routing_config.profiles:
        offline_profile = routing_config.profiles["offline_tier"]
    else:
        # Synthesize from [llm.openai_compat]
        oc = config.llm.openai_compat
        offline_profile = ModelProfile(
            provider="openai_compat",
            model=oc.model,
            base_url=oc.base_url,
            max_tokens=config.llm.max_tokens,
            temperature=config.llm.temperature,
        )
        logger.info("ModelRouter[offline]: synthesized offline_tier from llm.openai_compat")

    offline_provider = create_llm_provider_from_profile(offline_profile)
    logger.info("ModelRouter[offline]: all agents -> offline_tier (model=%s)", offline_profile.model)

    # Build a mapping where every known agent -> "offline_tier"
    all_agents = _OPUS_AGENTS | _SONNET_AGENTS | _HAIKU_AGENTS | set(routing_config.agent_mapping.keys())
    offline_mapping = {agent: "offline_tier" for agent in all_agents}

    offline_routing = ModelRoutingConfig(
        profiles={"offline_tier": offline_profile},
        agent_mapping=offline_mapping,
        default_profile="offline_tier",
    )
    return ModelRouter(offline_routing, {"offline_tier": offline_provider})
