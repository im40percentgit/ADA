"""
Unit tests for companion preferences: StateManager CRUD + REST endpoints.

Uses a real in-memory SQLite database for all tests — no mocks of internal
code. HTTP tests use FastAPI TestClient wired through create_app with a real
AdaConfig, EventBus, and a null LLM stub, matching the pattern established
in test_notification_routes.py (DEC-NOTIF-001) and test_circle_routes.py.

@decision DEC-COMPANION-001
@title Companion preferences stored per-user in SQLite companion_preferences table
@status accepted
@rationale See ada/api/routes/companion.py for full rationale. Tests exercise
    the full HTTP → StateManager → SQLite stack without mocking internals.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from ada.agents.registry import AgentRegistry
from ada.api.app import create_app
from ada.api.auth import get_current_user
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from ada.llm.router import make_null_router
from ada.models.user import User


# ---------------------------------------------------------------------------
# Minimal null LLM (no external calls)
# ---------------------------------------------------------------------------

class _NullLLM(LLMProvider):
    async def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(content="", model="null", input_tokens=0, output_tokens=0)

    async def stream(self, messages, **kwargs):
        return
        yield


# ---------------------------------------------------------------------------
# Fixed IDs
# ---------------------------------------------------------------------------

_USER_ID = "user-companion-001"
_USER_EMAIL = "companion-user@example.com"


def _make_user() -> User:
    return User(
        id=_USER_ID,
        email=_USER_EMAIL,
        role="caregiver",
        patient_id=None,
        created_at=datetime.utcnow(),
        is_active=True,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    await sm.create_user({
        "id": _USER_ID,
        "email": _USER_EMAIL,
        "hashed_password": "hashed",
        "role": "caregiver",
        "patient_id": None,
    })
    yield sm
    await sm.close()


# ---------------------------------------------------------------------------
# HTTP client factory
# ---------------------------------------------------------------------------

@contextmanager
def _client(state: StateManager, user: User | None = None) -> Generator[TestClient, None, None]:
    """TestClient wired to the given StateManager. Optionally inject auth user."""
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


# ---------------------------------------------------------------------------
# StateManager CRUD tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_companion_preferences_returns_none_when_no_row(state: StateManager):
    """get_companion_preferences returns None for a user with no saved prefs."""
    result = await state.get_companion_preferences(_USER_ID)
    assert result is None


@pytest.mark.asyncio
async def test_set_and_get_companion_preferences(state: StateManager):
    """Round-trip: set preferences and retrieve them intact."""
    prefs = {
        "name": "Luna",
        "voice": "neutral",
        "personality": {"warmth": "professional", "verbosity": "terse", "formality": "formal"},
    }
    await state.set_companion_preferences(_USER_ID, prefs)
    result = await state.get_companion_preferences(_USER_ID)

    assert result is not None
    assert result["name"] == "Luna"
    assert result["voice"] == "neutral"
    assert result["personality"] == {"warmth": "professional", "verbosity": "terse", "formality": "formal"}


@pytest.mark.asyncio
async def test_set_companion_preferences_upserts(state: StateManager):
    """Calling set twice updates the row (INSERT OR REPLACE semantics)."""
    await state.set_companion_preferences(_USER_ID, {
        "name": "Ada",
        "voice": "female",
        "personality": {"warmth": "warm"},
    })
    await state.set_companion_preferences(_USER_ID, {
        "name": "Max",
        "voice": "male",
        "personality": {"warmth": "neutral"},
    })
    result = await state.get_companion_preferences(_USER_ID)
    assert result["name"] == "Max"
    assert result["voice"] == "male"


@pytest.mark.asyncio
async def test_personality_json_round_trip(state: StateManager):
    """Personality dict with multiple keys survives JSON encode/decode."""
    personality = {
        "warmth": "warm",
        "verbosity": "balanced",
        "formality": "casual",
        "custom_key": "custom_value",
    }
    await state.set_companion_preferences(_USER_ID, {
        "name": "Ada",
        "voice": "female",
        "personality": personality,
    })
    result = await state.get_companion_preferences(_USER_ID)
    assert result["personality"] == personality


@pytest.mark.asyncio
async def test_empty_personality_dict_stored_correctly(state: StateManager):
    """Empty personality dict is stored and returned as empty dict (not null)."""
    await state.set_companion_preferences(_USER_ID, {
        "name": "Ada",
        "voice": "female",
        "personality": {},
    })
    result = await state.get_companion_preferences(_USER_ID)
    assert result["personality"] == {}


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_http_get_defaults_when_no_prefs(state: StateManager):
    """GET /api/companion/preferences returns config defaults when no DB row."""
    with _client(state, _make_user()) as client:
        resp = client.get("/api/companion/preferences")

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Ada"
    assert data["voice"] == "female"
    assert "personality" in data
    assert data["personality"]["warmth"] == "warm"


@pytest.mark.asyncio
async def test_http_put_and_get_full_prefs(state: StateManager):
    """PUT then GET returns the saved preferences."""
    with _client(state, _make_user()) as client:
        put_resp = client.put("/api/companion/preferences", json={
            "name": "Sage",
            "voice": "neutral",
            "personality": {"warmth": "professional", "verbosity": "terse", "formality": "formal"},
        })
        assert put_resp.status_code == 200

        get_resp = client.get("/api/companion/preferences")

    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["name"] == "Sage"
    assert data["voice"] == "neutral"
    assert data["personality"]["warmth"] == "professional"


@pytest.mark.asyncio
async def test_http_partial_update_name_only(state: StateManager):
    """PUT with only name preserves existing voice and personality."""
    with _client(state, _make_user()) as client:
        # First: save full prefs
        client.put("/api/companion/preferences", json={
            "name": "Ada",
            "voice": "neutral",
            "personality": {"warmth": "warm", "verbosity": "expansive", "formality": "casual"},
        })
        # Partial update — only name
        put_resp = client.put("/api/companion/preferences", json={"name": "Aria"})

    assert put_resp.status_code == 200
    data = put_resp.json()
    assert data["name"] == "Aria"
    assert data["voice"] == "neutral"                          # preserved
    assert data["personality"]["verbosity"] == "expansive"    # preserved


@pytest.mark.asyncio
async def test_http_invalid_voice_returns_422(state: StateManager):
    """PUT with an invalid voice value returns HTTP 422."""
    with _client(state, _make_user()) as client:
        resp = client.put("/api/companion/preferences", json={
            "name": "Ada",
            "voice": "robot",  # invalid — not in (male, female, neutral)
        })

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_http_personality_partial_merge(state: StateManager):
    """PUT with partial personality dict merges into existing personality."""
    with _client(state, _make_user()) as client:
        client.put("/api/companion/preferences", json={
            "name": "Ada",
            "voice": "female",
            "personality": {"warmth": "warm", "verbosity": "balanced", "formality": "casual"},
        })
        put_resp = client.put("/api/companion/preferences", json={
            "personality": {"verbosity": "terse"},
        })

    assert put_resp.status_code == 200
    data = put_resp.json()
    assert data["personality"]["verbosity"] == "terse"      # updated
    assert data["personality"]["warmth"] == "warm"          # preserved
    assert data["personality"]["formality"] == "casual"     # preserved


@pytest.mark.asyncio
async def test_http_requires_auth(state: StateManager):
    """GET /api/companion/preferences without auth → 401."""
    with _client(state, user=None) as client:
        resp = client.get("/api/companion/preferences")

    assert resp.status_code == 401
