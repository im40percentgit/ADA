"""
Unit tests for create_model_router mode-aware behavior (DEC-LLM-005, DEC-LLM-006).

Tests each mode (claude / offline / dual) and verifies that agents resolve
to the correct provider tier. Providers are never actually called — only
the model string on the resolved provider is checked.

@decision DEC-LLM-005
@title Three-mode LLM selector: claude / offline / dual
@status accepted
@rationale See ada/llm/router.py for full rationale.

# @mock-exempt: patch.dict("os.environ") only — environment variables are
#   an external OS boundary, not internal module mocking. No internal ada
#   functions are mocked. Providers are real instances; LLM HTTP calls are
#   never triggered (no complete() or stream() calls are made in these tests).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ada.core.config import (
    AdaConfig,
    LLMConfig,
    ModelProfile,
    ModelRoutingConfig,
)
from ada.llm.claude import ClaudeProvider
from ada.llm.openai_compat import OpenAICompatProvider
from ada.llm.router import ModelRouter, create_model_router, _resolve_mode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(mode: str = "dual") -> AdaConfig:
    """Build a minimal AdaConfig with the three-tier profiles and mode set."""
    profiles = {
        "opus_tier": ModelProfile(
            provider="claude",
            model="claude-opus-4-7",
            max_tokens=2048,
            temperature=0.3,
            api_key_env="ANTHROPIC_API_KEY",
            prompt_cache_system=True,
        ),
        "sonnet_tier": ModelProfile(
            provider="claude",
            model="claude-sonnet-4-6",
            max_tokens=1024,
            temperature=0.7,
            api_key_env="ANTHROPIC_API_KEY",
        ),
        "haiku_tier": ModelProfile(
            provider="claude",
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            temperature=0.4,
            api_key_env="ANTHROPIC_API_KEY",
        ),
        "offline_tier": ModelProfile(
            provider="openai_compat",
            model="local-model",
            base_url="http://localhost:8080/v1",
            max_tokens=2048,
            temperature=0.7,
        ),
    }
    agent_mapping = {
        # Opus
        "cognitive_assessor": "opus_tier",
        "crisis_monitor": "opus_tier",
        "fusion": "opus_tier",
        "session_summarizer": "opus_tier",
        # Sonnet
        "wellness_companion": "sonnet_tier",
        "knowledge_agent": "sonnet_tier",
        "daily_summary": "sonnet_tier",
        "board_suggestion": "sonnet_tier",
        "progress_report": "sonnet_tier",
        "medication_manager": "sonnet_tier",
        # Haiku
        "tts": "haiku_tier",
        "task_scoring": "haiku_tier",
        "voice_emotion": "haiku_tier",
        "facial_emotion": "haiku_tier",
        "transcription": "haiku_tier",
        "verdict": "haiku_tier",
        "emotion_analyzer": "haiku_tier",
        "physiological": "haiku_tier",
    }
    routing = ModelRoutingConfig(
        profiles=profiles,
        agent_mapping=agent_mapping,
        default_profile="sonnet_tier",
    )
    cfg = AdaConfig(
        model_routing=routing,
        llm=LLMConfig(mode=mode),  # type: ignore[arg-type]
    )
    return cfg


# ---------------------------------------------------------------------------
# _resolve_mode
# ---------------------------------------------------------------------------

class TestResolveMode:

    def test_db_row_wins_over_env_and_toml(self):
        cfg = _make_config(mode="claude")
        assert _resolve_mode(cfg, db_mode="offline") == "offline"

    def test_invalid_db_row_falls_back_to_config(self):
        cfg = _make_config(mode="claude")
        assert _resolve_mode(cfg, db_mode="bad-value") == "claude"

    def test_no_db_row_uses_config(self):
        cfg = _make_config(mode="offline")
        assert _resolve_mode(cfg, db_mode=None) == "offline"

    def test_default_mode_is_dual(self):
        cfg = _make_config(mode="dual")
        assert _resolve_mode(cfg) == "dual"


# ---------------------------------------------------------------------------
# Dual mode — pass-through
# ---------------------------------------------------------------------------

class TestDualMode:

    def _make_router(self) -> ModelRouter:
        cfg = _make_config(mode="dual")
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            return create_model_router(cfg)

    def test_crisis_monitor_gets_opus(self):
        router = self._make_router()
        provider = router.get_provider("crisis_monitor")
        assert isinstance(provider, ClaudeProvider)
        assert provider._model == "claude-opus-4-7"

    def test_wellness_companion_gets_sonnet(self):
        router = self._make_router()
        provider = router.get_provider("wellness_companion")
        assert isinstance(provider, ClaudeProvider)
        assert provider._model == "claude-sonnet-4-6"

    def test_tts_gets_haiku(self):
        router = self._make_router()
        provider = router.get_provider("tts")
        assert isinstance(provider, ClaudeProvider)
        assert provider._model == "claude-haiku-4-5-20251001"

    def test_unknown_agent_uses_default_profile(self):
        router = self._make_router()
        provider = router.get_provider("nonexistent_agent_xyz")
        # Default is sonnet_tier
        assert isinstance(provider, ClaudeProvider)
        assert provider._model == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Claude mode — forces all agents to Claude tiers
# ---------------------------------------------------------------------------

class TestClaudeMode:

    def _make_router(self) -> ModelRouter:
        cfg = _make_config(mode="claude")
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            return create_model_router(cfg)

    def test_crisis_monitor_routes_to_claude_opus(self):
        router = self._make_router()
        provider = router.get_provider("crisis_monitor")
        assert isinstance(provider, ClaudeProvider)
        assert provider._model == "claude-opus-4-7"

    def test_cognitive_assessor_routes_to_claude_opus(self):
        router = self._make_router()
        provider = router.get_provider("cognitive_assessor")
        assert isinstance(provider, ClaudeProvider)
        assert provider._model == "claude-opus-4-7"

    def test_wellness_companion_routes_to_claude_sonnet(self):
        router = self._make_router()
        provider = router.get_provider("wellness_companion")
        assert isinstance(provider, ClaudeProvider)
        assert provider._model == "claude-sonnet-4-6"

    def test_tts_routes_to_claude_haiku(self):
        router = self._make_router()
        provider = router.get_provider("tts")
        assert isinstance(provider, ClaudeProvider)
        assert provider._model == "claude-haiku-4-5-20251001"

    def test_verdict_routes_to_claude_haiku(self):
        router = self._make_router()
        provider = router.get_provider("verdict")
        assert isinstance(provider, ClaudeProvider)
        assert provider._model == "claude-haiku-4-5-20251001"

    def test_no_offline_provider_created(self):
        router = self._make_router()
        # offline_tier should not be in providers
        assert "offline_tier" not in router._providers

    def test_all_providers_are_claude(self):
        router = self._make_router()
        for name, provider in router._providers.items():
            assert isinstance(provider, ClaudeProvider), (
                f"Profile {name!r} is not a ClaudeProvider in claude mode"
            )


# ---------------------------------------------------------------------------
# Offline mode — collapses to single openai_compat provider
# ---------------------------------------------------------------------------

class TestOfflineMode:

    def _make_router(self) -> ModelRouter:
        cfg = _make_config(mode="offline")
        return create_model_router(cfg)

    def test_crisis_monitor_routes_to_offline(self):
        router = self._make_router()
        provider = router.get_provider("crisis_monitor")
        assert isinstance(provider, OpenAICompatProvider)

    def test_wellness_companion_routes_to_offline(self):
        router = self._make_router()
        provider = router.get_provider("wellness_companion")
        assert isinstance(provider, OpenAICompatProvider)

    def test_tts_routes_to_offline(self):
        router = self._make_router()
        provider = router.get_provider("tts")
        assert isinstance(provider, OpenAICompatProvider)

    def test_all_agents_same_provider_instance(self):
        """In offline mode every agent resolves to the same offline_tier provider."""
        router = self._make_router()
        p1 = router.get_provider("crisis_monitor")
        p2 = router.get_provider("wellness_companion")
        p3 = router.get_provider("tts")
        # All should be the same instance (single offline provider)
        assert p1 is p2
        assert p2 is p3

    def test_only_offline_tier_profile(self):
        router = self._make_router()
        assert list(router._providers.keys()) == ["offline_tier"]

    def test_offline_tier_model(self):
        router = self._make_router()
        provider = router.get_provider("wellness_companion")
        assert isinstance(provider, OpenAICompatProvider)
        assert provider._model == "local-model"


# ---------------------------------------------------------------------------
# DB mode override (hot-swap path)
# ---------------------------------------------------------------------------

class TestDbModeOverride:

    def test_db_offline_overrides_toml_claude(self):
        cfg = _make_config(mode="claude")
        router = create_model_router(cfg, db_mode="offline")
        provider = router.get_provider("crisis_monitor")
        assert isinstance(provider, OpenAICompatProvider)

    def test_db_claude_overrides_toml_offline(self):
        cfg = _make_config(mode="offline")
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            router = create_model_router(cfg, db_mode="claude")
        provider = router.get_provider("crisis_monitor")
        assert isinstance(provider, ClaudeProvider)
        assert provider._model == "claude-opus-4-7"


# ---------------------------------------------------------------------------
# Prompt-cache flag (DEC-LLM-007)
# ---------------------------------------------------------------------------

class TestPromptCacheFlag:

    def test_opus_tier_has_cache_enabled_in_dual_mode(self):
        cfg = _make_config(mode="dual")
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            router = create_model_router(cfg)
        opus_provider = router.get_provider("crisis_monitor")
        assert isinstance(opus_provider, ClaudeProvider)
        assert opus_provider._prompt_cache_system is True

    def test_sonnet_tier_has_cache_disabled(self):
        cfg = _make_config(mode="dual")
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            router = create_model_router(cfg)
        sonnet_provider = router.get_provider("wellness_companion")
        assert isinstance(sonnet_provider, ClaudeProvider)
        assert sonnet_provider._prompt_cache_system is False


# ---------------------------------------------------------------------------
# Legacy fallback (no model_routing config)
# ---------------------------------------------------------------------------

class TestLegacyFallback:

    def test_no_routing_config_uses_single_provider(self):
        cfg = AdaConfig(llm=LLMConfig(provider="claude", mode="dual"))  # type: ignore[arg-type]
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            router = create_model_router(cfg)
        # Should still work — all agents resolve to the single default provider
        provider = router.get_provider("any_agent")
        assert isinstance(provider, ClaudeProvider)
