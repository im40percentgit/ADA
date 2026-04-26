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
from ada.llm.router import make_null_router, create_model_router
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


def _build_app_with_real_router(state: StateManager, mode: str = "dual"):
    """Build a FastAPI app using a real mode-aware ModelRouter (DEC-LLM-008).

    Used by tests that assert the GET endpoint returns the *effective*
    agent_mapping rather than the static TOML mapping, which differs per mode.
    The router is built via create_model_router() so the builder helpers
    (_build_claude_only_router etc.) populate _agent_mapping correctly.
    """
    config = _make_three_tier_config(mode=mode)
    bus = EventBus()
    real_router = create_model_router(config)
    registry = AgentRegistry(bus, config, state, real_router)

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
        # Must use real router so the live router's provider_names reflect the
        # three Claude tiers (DEC-LLM-008: GET now reads from live router, not TOML).
        with TestClient(_build_app_with_real_router(state, mode="dual"), raise_server_exceptions=True) as client:
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


# ---------------------------------------------------------------------------
# Tests: effective agent_mapping differs across modes (DEC-LLM-008)
# ---------------------------------------------------------------------------

class TestEffectiveAgentMapping:
    """Assert that GET /llm-mode returns the live router mapping, not static TOML.

    In claude mode every agent must map to a claude tier (opus/sonnet/haiku).
    In offline mode every agent must map to offline_tier.
    In dual mode the TOML mapping is honoured (mixed tiers).

    These tests use _build_app_with_real_router() so the registry holds a
    real mode-aware ModelRouter whose _agent_mapping has been rebuilt by
    the mode-specific builder helper.
    """

    @pytest.mark.asyncio
    async def test_claude_mode_all_agents_map_to_claude_tiers(self, state):
        with TestClient(
            _build_app_with_real_router(state, mode="claude"),
            raise_server_exceptions=True,
        ) as client:
            resp = client.get("/api/admin/settings/llm-mode")
        assert resp.status_code == 200
        mapping = resp.json()["agent_mapping"]
        claude_tiers = {"opus_tier", "sonnet_tier", "haiku_tier"}
        for agent, profile in mapping.items():
            assert profile in claude_tiers, (
                f"Agent {agent!r} mapped to {profile!r} in claude mode — expected claude tier"
            )

    @pytest.mark.asyncio
    async def test_offline_mode_all_agents_map_to_offline_tier(self, state):
        with TestClient(
            _build_app_with_real_router(state, mode="offline"),
            raise_server_exceptions=True,
        ) as client:
            resp = client.get("/api/admin/settings/llm-mode")
        assert resp.status_code == 200
        mapping = resp.json()["agent_mapping"]
        assert len(mapping) > 0, "offline mode must produce a non-empty agent_mapping"
        for agent, profile in mapping.items():
            assert profile == "offline_tier", (
                f"Agent {agent!r} mapped to {profile!r} in offline mode — expected offline_tier"
            )

    @pytest.mark.asyncio
    async def test_claude_and_offline_mappings_differ(self, state):
        """The effective mapping for claude mode must differ from offline mode."""
        with TestClient(
            _build_app_with_real_router(state, mode="claude"),
            raise_server_exceptions=True,
        ) as client:
            claude_resp = client.get("/api/admin/settings/llm-mode")
        with TestClient(
            _build_app_with_real_router(state, mode="offline"),
            raise_server_exceptions=True,
        ) as client:
            offline_resp = client.get("/api/admin/settings/llm-mode")

        claude_mapping = claude_resp.json()["agent_mapping"]
        offline_mapping = offline_resp.json()["agent_mapping"]
        # At least one agent must differ between the two modes
        assert claude_mapping != offline_mapping, (
            "claude and offline modes returned identical agent_mapping — "
            "endpoint is returning static TOML instead of effective router mapping"
        )

    @pytest.mark.asyncio
    async def test_dual_mode_honors_toml_tiers(self, state):
        """Dual mode preserves the per-agent TOML mapping (mixed tiers)."""
        with TestClient(
            _build_app_with_real_router(state, mode="dual"),
            raise_server_exceptions=True,
        ) as client:
            resp = client.get("/api/admin/settings/llm-mode")
        assert resp.status_code == 200
        mapping = resp.json()["agent_mapping"]
        # The test config assigns these explicitly — check they survive dual mode
        assert mapping.get("crisis_monitor") == "opus_tier"
        assert mapping.get("wellness_companion") == "sonnet_tier"
        assert mapping.get("tts") == "haiku_tier"

    @pytest.mark.asyncio
    async def test_get_reflects_agent_mapping_after_put_hot_swap(self, state):
        """PUT then GET on the SAME app instance must show the new agent_mapping.

        Regression guard for the hot-swap bug: the tester observed that after
        PUT mode=offline, subsequent GET returned mode="offline" correctly but
        agent_mapping still showed the dual/claude tiers. This test exercises
        the exact PUT→GET path on one TestClient (same app.state.registry),
        catching any stale-reference or caching bug in the hot-swap path.
        """
        # Start in dual mode so mappings are mixed-tier
        app = _build_app_with_real_router(state, mode="dual")
        with TestClient(app, raise_server_exceptions=True) as client:
            # Baseline: dual mode has mixed tiers
            get1 = client.get("/api/admin/settings/llm-mode")
            assert get1.status_code == 200
            dual_mapping = get1.json()["agent_mapping"]
            # crisis_monitor should be opus_tier in dual mode (from TOML)
            assert dual_mapping.get("crisis_monitor") == "opus_tier", (
                f"Baseline failed: crisis_monitor={dual_mapping.get('crisis_monitor')!r}"
            )

            # Switch to offline — should collapse all agents to offline_tier
            put_resp = client.put("/api/admin/settings/llm-mode", json={"mode": "offline"})
            assert put_resp.status_code == 200

            # GET on same client instance must now reflect offline mapping
            get2 = client.get("/api/admin/settings/llm-mode")
            assert get2.status_code == 200
            data2 = get2.json()
            assert data2["mode"] == "offline", f"mode not updated: {data2['mode']!r}"
            offline_mapping = data2["agent_mapping"]
            for agent, profile in offline_mapping.items():
                assert profile == "offline_tier", (
                    f"After PUT offline: agent {agent!r} still maps to {profile!r} "
                    f"(expected offline_tier) — hot-swap did not propagate to GET"
                )

            # Switch to claude — should collapse all agents to claude tiers
            put_resp2 = client.put("/api/admin/settings/llm-mode", json={"mode": "claude"})
            assert put_resp2.status_code == 200

            get3 = client.get("/api/admin/settings/llm-mode")
            assert get3.status_code == 200
            data3 = get3.json()
            assert data3["mode"] == "claude", f"mode not updated: {data3['mode']!r}"
            claude_mapping = data3["agent_mapping"]
            claude_tiers = {"opus_tier", "sonnet_tier", "haiku_tier"}
            for agent, profile in claude_mapping.items():
                assert profile in claude_tiers, (
                    f"After PUT claude: agent {agent!r} maps to {profile!r} "
                    f"(expected claude tier) — hot-swap did not propagate to GET"
                )
