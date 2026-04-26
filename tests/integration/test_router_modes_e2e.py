"""
End-to-end integration tests for router mode switching.

These tests exercise create_model_router with real providers and verify
that the routing config (agent → tier) survives the full construction
path. No actual LLM HTTP calls are made — we verify provider identity
and model configuration, not LLM responses.

The "live API" tests (marked skip-if-no-ANTHROPIC_API_KEY) are skipped
in CI unless the key is available; they verify the full provider round-trip.

@decision DEC-LLM-005
@title Three-mode LLM selector: claude / offline / dual
@status accepted
@rationale See ada/llm/router.py for full rationale. E2E tests verify
    the router construction path and provider wiring across all three modes.

@decision DEC-LLM-006
@title Per-tier agent routing
@status accepted
@rationale Tier assignments are verified against the canonical tier sets
    defined in router.py (_OPUS_AGENTS, _SONNET_AGENTS, _HAIKU_AGENTS).

# @mock-exempt: only patch.dict(os.environ) is used — environment variables
#   are an external OS boundary, not an internal ada module. All providers
#   (ClaudeProvider, OpenAICompatProvider) are real instances. No LLM HTTP
#   calls are made (no complete() or stream() calls in these tests). The
#   live smoke test at the bottom makes a real API call when the key is set.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from ada.core.config import (
    AdaConfig,
    LLMConfig,
    ModelProfile,
    ModelRoutingConfig,
)
from ada.llm.claude import ClaudeProvider
from ada.llm.openai_compat import OpenAICompatProvider
from ada.llm.router import (
    ModelRouter,
    create_model_router,
    _OPUS_AGENTS,
    _SONNET_AGENTS,
    _HAIKU_AGENTS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _full_config(mode: str = "dual") -> AdaConfig:
    """Build a complete three-tier AdaConfig matching production layout."""
    profiles = {
        "opus_tier": ModelProfile(
            provider="claude", model="claude-opus-4-7",
            max_tokens=2048, temperature=0.3,
            api_key_env="ANTHROPIC_API_KEY", prompt_cache_system=True,
        ),
        "sonnet_tier": ModelProfile(
            provider="claude", model="claude-sonnet-4-6",
            max_tokens=1024, temperature=0.7, api_key_env="ANTHROPIC_API_KEY",
        ),
        "haiku_tier": ModelProfile(
            provider="claude", model="claude-haiku-4-5-20251001",
            max_tokens=512, temperature=0.4, api_key_env="ANTHROPIC_API_KEY",
        ),
        "offline_tier": ModelProfile(
            provider="openai_compat", model="local-model",
            base_url="http://localhost:8080/v1", max_tokens=2048, temperature=0.7,
        ),
    }
    # Full agent_mapping mirroring config/default.toml
    agent_mapping = {
        "cognitive_assessor": "opus_tier",
        "crisis_monitor": "opus_tier",
        "fusion": "opus_tier",
        "session_summarizer": "opus_tier",
        "wellness_companion": "sonnet_tier",
        "knowledge_agent": "sonnet_tier",
        "daily_summary": "sonnet_tier",
        "board_suggestion": "sonnet_tier",
        "progress_report": "sonnet_tier",
        "medication_manager": "sonnet_tier",
        "treatment_progress": "sonnet_tier",
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
        profiles=profiles, agent_mapping=agent_mapping, default_profile="sonnet_tier",
    )
    return AdaConfig(
        model_routing=routing,
        llm=LLMConfig(mode=mode),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Router construction — all modes
# ---------------------------------------------------------------------------

class TestRouterConstructionDual:
    """Dual mode: providers are built from TOML profiles as-is."""

    def test_router_is_model_router_instance(self):
        cfg = _full_config("dual")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            router = create_model_router(cfg)
        assert isinstance(router, ModelRouter)

    def test_dual_has_four_provider_profiles(self):
        """Dual mode creates all four profiles (opus, sonnet, haiku, offline)."""
        cfg = _full_config("dual")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            router = create_model_router(cfg)
        assert set(router._providers.keys()) == {"opus_tier", "sonnet_tier", "haiku_tier", "offline_tier"}

    def test_all_opus_agents_map_to_opus_model(self):
        cfg = _full_config("dual")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            router = create_model_router(cfg)
        for agent in _OPUS_AGENTS:
            provider = router.get_provider(agent)
            assert isinstance(provider, ClaudeProvider), f"{agent} should be ClaudeProvider"
            assert provider._model == "claude-opus-4-7", f"{agent} should use opus model"

    def test_all_sonnet_agents_map_to_sonnet_model(self):
        cfg = _full_config("dual")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            router = create_model_router(cfg)
        for agent in _SONNET_AGENTS:
            provider = router.get_provider(agent)
            assert isinstance(provider, ClaudeProvider), f"{agent} should be ClaudeProvider"
            assert provider._model == "claude-sonnet-4-6", f"{agent} should use sonnet model"

    def test_all_haiku_agents_map_to_haiku_model(self):
        cfg = _full_config("dual")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            router = create_model_router(cfg)
        for agent in _HAIKU_AGENTS:
            provider = router.get_provider(agent)
            assert isinstance(provider, ClaudeProvider), f"{agent} should be ClaudeProvider"
            assert provider._model == "claude-haiku-4-5-20251001", f"{agent} should use haiku model"

    def test_daily_summary_key_exists_and_routes_to_sonnet(self):
        """Verify the daily_summary routing key (main.py split from session_summarizer)."""
        cfg = _full_config("dual")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            router = create_model_router(cfg)
        provider = router.get_provider("daily_summary")
        assert isinstance(provider, ClaudeProvider)
        assert provider._model == "claude-sonnet-4-6"

    def test_verdict_key_routes_to_haiku(self):
        """verdict is used by ada/api/routes/verdict.py via router.get_provider('verdict')."""
        cfg = _full_config("dual")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            router = create_model_router(cfg)
        provider = router.get_provider("verdict")
        assert isinstance(provider, ClaudeProvider)
        assert provider._model == "claude-haiku-4-5-20251001"

    def test_tts_key_is_tts_not_tts_agent(self):
        """tts_agent.name returns 'tts' — verify the key 'tts' resolves correctly."""
        cfg = _full_config("dual")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            router = create_model_router(cfg)
        provider = router.get_provider("tts")
        assert isinstance(provider, ClaudeProvider)
        assert provider._model == "claude-haiku-4-5-20251001"


class TestRouterConstructionClaude:
    """Claude mode: only Claude profiles are built; offline_tier is excluded."""

    def test_offline_tier_not_in_providers(self):
        cfg = _full_config("claude")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            router = create_model_router(cfg)
        assert "offline_tier" not in router._providers

    def test_every_agent_resolves_to_claude(self):
        cfg = _full_config("claude")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            router = create_model_router(cfg)
        all_agents = list(_OPUS_AGENTS) + list(_SONNET_AGENTS) + list(_HAIKU_AGENTS)
        for agent in all_agents:
            provider = router.get_provider(agent)
            assert isinstance(provider, ClaudeProvider), (
                f"In claude mode, {agent} should be ClaudeProvider not {type(provider).__name__}"
            )


class TestRouterConstructionOffline:
    """Offline mode: all agents collapse to a single openai_compat provider."""

    def test_all_agents_are_openai_compat(self):
        cfg = _full_config("offline")
        router = create_model_router(cfg)
        all_agents = list(_OPUS_AGENTS) + list(_SONNET_AGENTS) + list(_HAIKU_AGENTS)
        for agent in all_agents:
            provider = router.get_provider(agent)
            assert isinstance(provider, OpenAICompatProvider), (
                f"In offline mode, {agent} should be OpenAICompatProvider"
            )

    def test_offline_single_provider(self):
        cfg = _full_config("offline")
        router = create_model_router(cfg)
        assert list(router._providers.keys()) == ["offline_tier"]


# ---------------------------------------------------------------------------
# Hot-swap path: db_mode parameter overrides config.llm.mode
# ---------------------------------------------------------------------------

class TestHotSwapDbMode:

    def test_db_offline_makes_all_openai_compat(self):
        cfg = _full_config("dual")
        router = create_model_router(cfg, db_mode="offline")
        provider = router.get_provider("crisis_monitor")
        assert isinstance(provider, OpenAICompatProvider)

    def test_db_claude_makes_all_claude(self):
        cfg = _full_config("offline")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            router = create_model_router(cfg, db_mode="claude")
        provider = router.get_provider("crisis_monitor")
        assert isinstance(provider, ClaudeProvider)
        assert provider._model == "claude-opus-4-7"

    def test_db_dual_same_as_pass_through(self):
        cfg = _full_config("dual")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            router_no_db = create_model_router(cfg)
            router_db_dual = create_model_router(cfg, db_mode="dual")
        p1 = router_no_db.get_provider("crisis_monitor")
        p2 = router_db_dual.get_provider("crisis_monitor")
        # Both should be the same model
        assert p1._model == p2._model  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Live API smoke test (skipped in CI unless ANTHROPIC_API_KEY is set)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="Requires ANTHROPIC_API_KEY — skipped in CI",
)
class TestLiveClaudeSmoke:
    """Smoke tests that make a real API call to Anthropic."""

    @pytest.mark.asyncio
    async def test_claude_mode_crisis_monitor_can_complete(self):
        """In claude mode, crisis_monitor routes to Opus and can complete."""
        cfg = _full_config("claude")
        router = create_model_router(cfg)
        provider = router.get_provider("crisis_monitor")
        assert isinstance(provider, ClaudeProvider)
        response = await provider.complete(
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=10,
            system="You are a test. Reply with one word.",
        )
        assert response.content
        assert response.input_tokens > 0
