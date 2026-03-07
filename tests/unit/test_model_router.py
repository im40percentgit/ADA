"""
Unit tests for ModelRouter and config-driven model routing.

@decision DEC-LLM-002
@title Config-driven per-agent model routing with fallback
@status accepted
@rationale See ada/llm/router.py for full rationale.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ada.core.config import (
    AdaConfig,
    LLMConfig,
    ModelProfile,
    ModelRoutingConfig,
)
from ada.llm.base import LLMProvider
from ada.llm.router import ModelRouter, create_model_router
from ada.llm.factory import create_llm_provider_from_profile


# ---------------------------------------------------------------------------
# ModelProfile config validation
# ---------------------------------------------------------------------------

class TestModelProfile:

    def test_valid_claude_profile(self):
        p = ModelProfile(provider="claude", model="claude-sonnet-4-5-20250514")
        assert p.provider == "claude"
        assert p.max_tokens == 1024
        assert p.temperature == 0.7

    def test_valid_openai_compat_profile(self):
        p = ModelProfile(
            provider="openai_compat",
            model="local-model",
            base_url="http://localhost:8080/v1",
            max_tokens=512,
            temperature=0.3,
        )
        assert p.provider == "openai_compat"
        assert p.base_url == "http://localhost:8080/v1"

    def test_invalid_provider_rejected(self):
        with pytest.raises(ValueError, match="provider must be one of"):
            ModelProfile(provider="gpt4all", model="some-model")

    def test_defaults(self):
        p = ModelProfile(provider="claude", model="test")
        assert p.max_tokens == 1024
        assert p.temperature == 0.7
        assert p.base_url is None
        assert p.api_key_env is None


# ---------------------------------------------------------------------------
# ModelRoutingConfig
# ---------------------------------------------------------------------------

class TestModelRoutingConfig:

    def test_empty_config(self):
        c = ModelRoutingConfig()
        assert c.profiles == {}
        assert c.agent_mapping == {}
        assert c.default_profile == "conversational"

    def test_config_with_profiles(self):
        c = ModelRoutingConfig(
            profiles={
                "warm": ModelProfile(provider="claude", model="claude-sonnet-4-5-20250514"),
                "fast": ModelProfile(provider="openai_compat", model="local", base_url="http://localhost:8080/v1"),
            },
            agent_mapping={"therapist": "warm", "crisis_monitor": "fast"},
            default_profile="warm",
        )
        assert len(c.profiles) == 2
        assert c.agent_mapping["therapist"] == "warm"


# ---------------------------------------------------------------------------
# ModelRouter
# ---------------------------------------------------------------------------

class TestModelRouter:
    # @mock-exempt: ModelRouter tests use mock LLMProvider sentinels to verify
    # dispatch identity (is/is not checks). LLMProvider is an ABC — instantiating
    # real providers requires API keys and HTTP clients. The router's sole
    # responsibility is dispatching; mocks are the minimal correct boundary here.

    def _make_router(self) -> tuple[ModelRouter, MagicMock, MagicMock]:
        """Create a router with two mock providers."""
        mock_warm = MagicMock(spec=LLMProvider)
        mock_fast = MagicMock(spec=LLMProvider)
        config = ModelRoutingConfig(
            profiles={},  # profiles not used by router directly
            agent_mapping={"therapist": "warm", "crisis_monitor": "fast"},
            default_profile="warm",
        )
        providers = {"warm": mock_warm, "fast": mock_fast}
        router = ModelRouter(config, providers)
        return router, mock_warm, mock_fast

    def test_mapped_agent_gets_correct_provider(self):
        router, mock_warm, mock_fast = self._make_router()
        assert router.get_provider("therapist") is mock_warm
        assert router.get_provider("crisis_monitor") is mock_fast

    def test_unknown_agent_gets_default(self):
        router, mock_warm, _ = self._make_router()
        assert router.get_provider("unknown_agent") is mock_warm

    def test_list_profiles(self):
        router, _, _ = self._make_router()
        mapping = router.list_profiles()
        assert mapping == {"therapist": "warm", "crisis_monitor": "fast"}

    def test_provider_names(self):
        router, _, _ = self._make_router()
        assert sorted(router.provider_names) == ["fast", "warm"]

    def test_missing_profile_falls_back_to_default(self):
        """If agent_mapping points to a non-existent profile, fall back to default."""
        mock_default = MagicMock(spec=LLMProvider)  # @mock-exempt: sentinel for identity check
        config = ModelRoutingConfig(
            agent_mapping={"broken_agent": "nonexistent_profile"},
            default_profile="default",
        )
        router = ModelRouter(config, {"default": mock_default})
        assert router.get_provider("broken_agent") is mock_default


# ---------------------------------------------------------------------------
# create_llm_provider_from_profile
# ---------------------------------------------------------------------------

class TestCreateProviderFromProfile:

    def test_creates_claude_provider(self):
        from ada.llm.claude import ClaudeProvider
        profile = ModelProfile(provider="claude", model="claude-sonnet-4-5-20250514")
        provider = create_llm_provider_from_profile(profile)
        assert isinstance(provider, ClaudeProvider)

    def test_creates_openai_compat_provider(self):
        from ada.llm.openai_compat import OpenAICompatProvider
        profile = ModelProfile(
            provider="openai_compat",
            model="local-model",
            base_url="http://localhost:8080/v1",
        )
        provider = create_llm_provider_from_profile(profile)
        assert isinstance(provider, OpenAICompatProvider)

    def test_unknown_provider_raises(self):
        # Bypass validation to test factory error path
        profile = ModelProfile(provider="claude", model="test")
        profile.provider = "unknown"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="Unknown provider in profile"):
            create_llm_provider_from_profile(profile)

    def test_profile_max_tokens_and_temperature_forwarded(self):
        from ada.llm.openai_compat import OpenAICompatProvider
        profile = ModelProfile(
            provider="openai_compat",
            model="test",
            base_url="http://localhost:8080/v1",
            max_tokens=2048,
            temperature=0.3,
        )
        provider = create_llm_provider_from_profile(profile)
        assert isinstance(provider, OpenAICompatProvider)
        assert provider._default_max_tokens == 2048
        assert provider._default_temperature == 0.3


# ---------------------------------------------------------------------------
# create_model_router (integration)
# ---------------------------------------------------------------------------

class TestCreateModelRouter:

    def test_legacy_mode_when_no_model_routing(self):
        """When model_routing is None, should create single-provider router."""
        config = AdaConfig(llm=LLMConfig(provider="claude"))
        router = create_model_router(config)
        assert "default" in router.provider_names
        # All agents should get the same provider
        p1 = router.get_provider("therapist")
        p2 = router.get_provider("crisis_monitor")
        assert p1 is p2

    def test_legacy_mode_when_empty_profiles(self):
        """Empty profiles dict should also trigger legacy mode."""
        config = AdaConfig(
            llm=LLMConfig(provider="claude"),
            model_routing=ModelRoutingConfig(profiles={}),
        )
        router = create_model_router(config)
        assert "default" in router.provider_names

    def test_multi_profile_mode(self):
        """With profiles defined, should create separate providers."""
        config = AdaConfig(
            model_routing=ModelRoutingConfig(
                profiles={
                    "warm": ModelProfile(provider="claude", model="claude-sonnet-4-5-20250514"),
                    "fast": ModelProfile(
                        provider="openai_compat",
                        model="local",
                        base_url="http://localhost:8080/v1",
                    ),
                },
                agent_mapping={"therapist": "warm", "crisis_monitor": "fast"},
                default_profile="warm",
            ),
        )
        router = create_model_router(config)
        assert sorted(router.provider_names) == ["fast", "warm"]
        # Different agents should get different providers
        p1 = router.get_provider("therapist")
        p2 = router.get_provider("crisis_monitor")
        assert p1 is not p2


# ---------------------------------------------------------------------------
# AdaConfig integration — model_routing field
# ---------------------------------------------------------------------------

class TestAdaConfigModelRouting:

    def test_model_routing_is_optional(self):
        config = AdaConfig()
        assert config.model_routing is None

    def test_model_routing_accepts_config(self):
        config = AdaConfig(
            model_routing=ModelRoutingConfig(
                default_profile="local",
                profiles={"local": ModelProfile(provider="claude", model="test")},
            ),
        )
        assert config.model_routing is not None
        assert "local" in config.model_routing.profiles
