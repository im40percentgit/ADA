"""
LLM provider factory — selects and instantiates a provider from config.

@decision DEC-LLM-001
@title Abstract LLMProvider with Claude + OpenAI-compat implementations
@status accepted
@rationale See ada/llm/base.py for full rationale.
"""

from __future__ import annotations

import logging

from ada.core.config import AdaConfig, ModelProfile
from ada.llm.base import LLMProvider
from ada.llm.claude import ClaudeProvider
from ada.llm.openai_compat import OpenAICompatProvider

logger = logging.getLogger(__name__)


def create_llm_provider(config: AdaConfig) -> LLMProvider:
    """
    Instantiate the configured LLM provider.

    Reads provider type from config.llm.provider. API keys are resolved
    from environment variables — never from the config object directly.

    Args:
        config: Ada configuration instance.

    Returns:
        A ready-to-use LLMProvider implementation.

    Raises:
        ValueError: If an unknown provider is specified.
    """
    llm_cfg = config.llm
    provider_name = llm_cfg.provider

    if provider_name == "claude":
        api_key = llm_cfg.claude.api_key
        if not api_key:
            logger.warning(
                "ClaudeProvider: %s is not set — API calls will fail",
                llm_cfg.claude.api_key_env,
            )
        logger.info("LLM factory: creating ClaudeProvider (model=%s)", llm_cfg.model)
        return ClaudeProvider(
            api_key=api_key,
            model=llm_cfg.model,
            default_max_tokens=llm_cfg.max_tokens,
            default_temperature=llm_cfg.temperature,
        )

    if provider_name == "openai_compat":
        oc_cfg = llm_cfg.openai_compat
        api_key = oc_cfg.api_key
        logger.info(
            "LLM factory: creating OpenAICompatProvider (base_url=%s model=%s)",
            oc_cfg.base_url,
            oc_cfg.model,
        )
        return OpenAICompatProvider(
            base_url=oc_cfg.base_url,
            api_key=api_key,
            model=oc_cfg.model,
            default_max_tokens=llm_cfg.max_tokens,
            default_temperature=llm_cfg.temperature,
        )

    raise ValueError(
        f"Unknown LLM provider: {provider_name!r}. "
        "Valid options are 'claude' and 'openai_compat'."
    )


def create_llm_provider_from_profile(profile: ModelProfile) -> LLMProvider:
    """
    Create a provider from a ModelProfile config.

    Args:
        profile: A ModelProfile specifying provider type, model, and parameters.

    Returns:
        A ready-to-use LLMProvider implementation.

    Raises:
        ValueError: If an unknown provider is specified in the profile.
    """
    import os

    if profile.provider == "claude":
        api_key_env = profile.api_key_env or "ANTHROPIC_API_KEY"
        api_key = os.environ.get(api_key_env, "")
        if not api_key:
            logger.warning("create_llm_provider_from_profile: %s is not set", api_key_env)
        return ClaudeProvider(
            api_key=api_key,
            model=profile.model,
            default_max_tokens=profile.max_tokens,
            default_temperature=profile.temperature,
        )

    if profile.provider == "openai_compat":
        api_key_env = profile.api_key_env or "OPENAI_API_KEY"
        api_key = os.environ.get(api_key_env, "none")
        base_url = profile.base_url or "http://localhost:8080/v1"
        return OpenAICompatProvider(
            base_url=base_url,
            api_key=api_key,
            model=profile.model,
            default_max_tokens=profile.max_tokens,
            default_temperature=profile.temperature,
        )

    raise ValueError(
        f"Unknown provider in profile: {profile.provider!r}. "
        "Valid options are 'claude' and 'openai_compat'."
    )
