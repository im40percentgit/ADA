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
"""

from __future__ import annotations

import logging

from ada.core.config import AdaConfig, ModelRoutingConfig
from ada.llm.base import LLMProvider
from ada.llm.factory import create_llm_provider, create_llm_provider_from_profile

logger = logging.getLogger(__name__)


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


def create_model_router(config: AdaConfig) -> ModelRouter:
    """
    Create a ModelRouter from config.

    If config.model_routing is set with profiles, creates per-profile providers.
    Otherwise, falls back to legacy single-provider from [llm] section,
    wrapping it in a router with a single "default" profile.
    """
    if config.model_routing and config.model_routing.profiles:
        routing_config = config.model_routing
        providers: dict[str, LLMProvider] = {}
        for name, profile in routing_config.profiles.items():
            providers[name] = create_llm_provider_from_profile(profile)
            logger.info("ModelRouter: created profile %r (provider=%s, model=%s)",
                        name, profile.provider, profile.model)
        return ModelRouter(routing_config, providers)

    # Legacy fallback: wrap single provider in a router
    legacy_provider = create_llm_provider(config)
    fallback_config = ModelRoutingConfig(
        profiles={},
        agent_mapping={},
        default_profile="default",
    )
    logger.info("ModelRouter: legacy mode — all agents use single %s provider", config.llm.provider)
    return ModelRouter(fallback_config, {"default": legacy_provider})
