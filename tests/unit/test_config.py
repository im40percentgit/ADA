"""
Unit tests for Ada configuration models (DEC-LLM-005, DEC-TTS-003, DEC-ML-018).

Covers: LLMConfig.mode default and validation, LLMMode type, STTConfig.model_size
default, TTSConfig.provider default and validation, ModelProfile.prompt_cache_system.

@decision DEC-LLM-005
@title Three-mode LLM selector: claude / offline / dual
@status accepted
@rationale Config tests verify the contract that other modules depend on:
    defaults are "dual", "large-v3-turbo", and "kokoro". Validators reject
    bad values loudly rather than silently falling back.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ada.core.config import (
    AdaConfig,
    LLMConfig,
    ModelProfile,
    ModelRoutingConfig,
    STTConfig,
    TTSConfig,
)


# ---------------------------------------------------------------------------
# LLMConfig
# ---------------------------------------------------------------------------

class TestLLMConfig:

    def test_default_mode_is_dual(self):
        cfg = LLMConfig()
        assert cfg.mode == "dual"

    def test_mode_claude_accepted(self):
        cfg = LLMConfig(mode="claude")
        assert cfg.mode == "claude"

    def test_mode_offline_accepted(self):
        cfg = LLMConfig(mode="offline")
        assert cfg.mode == "offline"

    def test_default_model_is_sonnet_4_6(self):
        """LLMConfig.model should default to claude-sonnet-4-6 (DEC-LLM-006)."""
        cfg = LLMConfig()
        assert cfg.model == "claude-sonnet-4-6"

    def test_invalid_mode_rejected(self):
        """Bad mode value should raise a ValidationError."""
        with pytest.raises(ValidationError):
            LLMConfig(mode="turbo-max")  # type: ignore[arg-type]

    def test_default_provider_is_claude(self):
        cfg = LLMConfig()
        assert cfg.provider == "claude"

    def test_invalid_provider_rejected(self):
        with pytest.raises(ValidationError):
            LLMConfig(provider="gemini")


# ---------------------------------------------------------------------------
# STTConfig
# ---------------------------------------------------------------------------

class TestSTTConfig:

    def test_default_model_size_is_large_v3_turbo(self):
        """DEC-ML-018: STT default bumped from 'base' to 'large-v3-turbo'."""
        cfg = STTConfig()
        assert cfg.model_size == "large-v3-turbo"

    def test_model_size_can_be_overridden(self):
        cfg = STTConfig(model_size="base")
        assert cfg.model_size == "base"

    def test_default_compute_type_is_int8(self):
        cfg = STTConfig()
        assert cfg.compute_type == "int8"

    def test_default_min_confidence(self):
        cfg = STTConfig()
        assert cfg.min_confidence == 0.4

    def test_default_vad_filter_is_false(self):
        cfg = STTConfig()
        assert cfg.vad_filter is False


# ---------------------------------------------------------------------------
# TTSConfig
# ---------------------------------------------------------------------------

class TestTTSConfig:

    def test_default_provider_is_kokoro(self):
        """DEC-TTS-003: TTS default changed from 'piper' to 'kokoro'."""
        cfg = TTSConfig()
        assert cfg.provider == "kokoro"

    def test_piper_still_accepted(self):
        cfg = TTSConfig(provider="piper")
        assert cfg.provider == "piper"

    def test_invalid_provider_rejected(self):
        with pytest.raises(ValidationError):
            TTSConfig(provider="google-tts")

    def test_default_sample_rate_is_24000(self):
        """Kokoro native rate (was 22050 for Piper)."""
        cfg = TTSConfig()
        assert cfg.sample_rate == 24000

    def test_sentence_streaming_default_true(self):
        cfg = TTSConfig()
        assert cfg.sentence_streaming is True


# ---------------------------------------------------------------------------
# ModelProfile.prompt_cache_system
# ---------------------------------------------------------------------------

class TestModelProfileCacheFlag:

    def test_default_prompt_cache_system_is_false(self):
        """prompt_cache_system defaults False for backward compat (DEC-LLM-007)."""
        p = ModelProfile(provider="claude", model="claude-sonnet-4-6")
        assert p.prompt_cache_system is False

    def test_prompt_cache_system_can_be_enabled(self):
        p = ModelProfile(
            provider="claude",
            model="claude-opus-4-7",
            prompt_cache_system=True,
        )
        assert p.prompt_cache_system is True


# ---------------------------------------------------------------------------
# AdaConfig integration: defaults compose correctly
# ---------------------------------------------------------------------------

class TestAdaConfigDefaults:

    def test_llm_mode_default_in_root_config(self):
        cfg = AdaConfig()
        assert cfg.llm.mode == "dual"

    def test_stt_model_size_default_in_root_config(self):
        cfg = AdaConfig()
        assert cfg.stt.model_size == "large-v3-turbo"

    def test_tts_provider_default_in_root_config(self):
        cfg = AdaConfig()
        assert cfg.tts.provider == "kokoro"

    def test_model_routing_defaults_to_none(self):
        """Without TOML, model_routing is None — router uses legacy fallback."""
        cfg = AdaConfig()
        assert cfg.model_routing is None

    def test_model_routing_can_be_set(self):
        profiles = {
            "sonnet_tier": ModelProfile(
                provider="claude", model="claude-sonnet-4-6",
            ),
        }
        routing = ModelRoutingConfig(
            profiles=profiles,
            agent_mapping={"wellness_companion": "sonnet_tier"},
            default_profile="sonnet_tier",
        )
        cfg = AdaConfig(model_routing=routing)
        assert cfg.model_routing is not None
        assert "sonnet_tier" in cfg.model_routing.profiles
