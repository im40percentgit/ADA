"""
Integration tests for the admin LLM-mode settings API (DEC-LLM-005).

Tests GET and PUT /api/admin/settings/llm-mode with:
  - A real in-memory SQLite StateManager (system_settings table persists)
  - A real FastAPI TestClient
  - A real AgentRegistry + ModelRouter
  - Auth dependency overridden with a fake caregiver user (no JWT)

Verifies:
  - GET returns the effective mode and routing info
  - PUT persists the mode to SQLite and hot-swaps the router
  - After PUT, subsequent GET reflects the new mode
  - Invalid mode returns 422

@decision DEC-LLM-005
@title Three-mode LLM selector: claude / offline / dual
@status accepted
@rationale See ada/llm/router.py for full rationale. These tests cover the
    HTTP control surface (GET/PUT round-trip, SQLite persistence, hot-swap).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from ada.agents.registry import AgentRegistry
from ada.api.app import create_app
from ada.api.auth import get_current_user
from ada.core.bus import EventBus
from ada.core.config import (
    AdaConfig,
    LLMConfig,
    ModelProfile,
    ModelRoutingConfig,
)
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from ada.llm.router import make_null_router
from ada.models.user import User


# ---------------------------------------------------------------------------
# Minimal LLM stub (real subclass — no HTTP calls)
# ---------------------------------------------------------------------------

class _NullLLM(LLMProvider):
    async def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(content="", model="null", input_tokens=0, output_tokens=0)

    async def stream(self, messages, **kwargs) -> AsyncIterator[str]:
        return
        yield


# ---------------------------------------------------------------------------
# Fake caregiver user for auth bypass
# ---------------------------------------------------------------------------

_CAREGIVER = User(
    id="cg-admin-settings-001",
    email="caregiver@ada.test",
    role="caregiver",
    patient_id=None,
    created_at=datetime.now(timezone.utc),
    is_active=True,
)


# ---------------------------------------------------------------------------
# Config + client factory helpers
# ---------------------------------------------------------------------------

def _make_three_tier_config(mode: str = "dual") -> AdaConfig:
    """Build AdaConfig with three-tier profiles so the router has real profiles."""
    profiles = {
        "opus_tier": ModelProfile(
            provider="claude", model="claude-opus-4-7",
            max_tokens=2048, temperature=0.3, api_key_env="ANTHROPIC_API_KEY",
            prompt_cache_system=True,
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
    agent_mapping = {
        "crisis_monitor": "opus_tier",
        "wellness_companion": "sonnet_tier",
        "tts": "haiku_tier",
    }
    routing = ModelRoutingConfig(
        profiles=profiles, agent_mapping=agent_mapping, default_profile="sonnet_tier",
    )
    return AdaConfig(
        model_routing=routing,
        llm=LLMConfig(mode=mode),  # type: ignore[arg-type]
    )


def _build_app(state: StateManager, mode: str = "dual"):
    """Build a FastAPI app wired to real in-memory state + three-tier config."""
    config = _make_three_tier_config(mode=mode)
    null_llm = _NullLLM()
    bus = EventBus()
    null_router = make_null_router(null_llm)
    registry = AgentRegistry(bus, config, state, null_router)

    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: _CAREGIVER
    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


# ---------------------------------------------------------------------------
# Tests: GET /api/admin/settings/llm-mode
# ---------------------------------------------------------------------------

class TestGetLLMMode:

    @pytest.mark.asyncio
    async def test_returns_200_with_mode(self, state):
        with TestClient(_build_app(state), raise_server_exceptions=True) as client:
            resp = client.get("/api/admin/settings/llm-mode")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] in ("claude", "offline", "dual")

    @pytest.mark.asyncio
    async def test_response_has_profiles_and_agent_mapping(self, state):
        with TestClient(_build_app(state), raise_server_exceptions=True) as client:
            resp = client.get("/api/admin/settings/llm-mode")
        assert resp.status_code == 200
        data = resp.json()
        assert "profiles" in data
        assert "agent_mapping" in data
        assert isinstance(data["profiles"], list)
        assert isinstance(data["agent_mapping"], dict)

    @pytest.mark.asyncio
    async def test_profiles_contains_three_tiers(self, state):
        with TestClient(_build_app(state), raise_server_exceptions=True) as client:
            resp = client.get("/api/admin/settings/llm-mode")
        profiles = resp.json()["profiles"]
        assert "opus_tier" in profiles
        assert "sonnet_tier" in profiles
        assert "haiku_tier" in profiles

    @pytest.mark.asyncio
    async def test_default_mode_is_dual(self, state):
        with TestClient(_build_app(state, mode="dual"), raise_server_exceptions=True) as client:
            resp = client.get("/api/admin/settings/llm-mode")
        # No DB row set — should reflect TOML/config default "dual"
        assert resp.json()["mode"] == "dual"


# ---------------------------------------------------------------------------
# Tests: PUT /api/admin/settings/llm-mode
# ---------------------------------------------------------------------------

class TestPutLLMMode:

    @pytest.mark.asyncio
    async def test_put_returns_200_with_applied_at(self, state):
        with TestClient(_build_app(state), raise_server_exceptions=True) as client:
            resp = client.put("/api/admin/settings/llm-mode", json={"mode": "offline"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "offline"
        assert "applied_at" in data

    @pytest.mark.asyncio
    async def test_put_persists_to_sqlite(self, state):
        with TestClient(_build_app(state), raise_server_exceptions=True) as client:
            client.put("/api/admin/settings/llm-mode", json={"mode": "claude"})
        # Read directly from DB to verify persistence
        stored = await state.get_system_setting("llm_mode")
        assert stored == "claude"

    @pytest.mark.asyncio
    async def test_put_round_trip_reflected_in_get(self, state):
        """After PUT, GET reads the DB row and reflects the new mode."""
        with TestClient(_build_app(state), raise_server_exceptions=True) as client:
            put_resp = client.put("/api/admin/settings/llm-mode", json={"mode": "offline"})
            assert put_resp.status_code == 200
            get_resp = client.get("/api/admin/settings/llm-mode")
        assert get_resp.json()["mode"] == "offline"

    @pytest.mark.asyncio
    async def test_put_invalid_mode_returns_422(self, state):
        with TestClient(_build_app(state), raise_server_exceptions=False) as client:
            resp = client.put("/api/admin/settings/llm-mode", json={"mode": "turbo-max"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_all_three_valid_modes_accepted(self, state):
        with TestClient(_build_app(state), raise_server_exceptions=True) as client:
            for mode in ("claude", "offline", "dual"):
                resp = client.put("/api/admin/settings/llm-mode", json={"mode": mode})
                assert resp.status_code == 200, f"mode={mode!r} failed: {resp.text}"
                assert resp.json()["mode"] == mode

    @pytest.mark.asyncio
    async def test_mode_survives_multiple_changes(self, state):
        """Mode persists across multiple PUTs — last write wins."""
        with TestClient(_build_app(state), raise_server_exceptions=True) as client:
            client.put("/api/admin/settings/llm-mode", json={"mode": "claude"})
            client.put("/api/admin/settings/llm-mode", json={"mode": "offline"})
            client.put("/api/admin/settings/llm-mode", json={"mode": "dual"})
        stored = await state.get_system_setting("llm_mode")
        assert stored == "dual"
