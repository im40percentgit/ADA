"""
Unit tests for onboarding status: StateManager CRUD + REST endpoints.

Uses a real in-memory SQLite database — no mocks of internal code.
HTTP tests use FastAPI TestClient wired through create_app with a real
AdaConfig, EventBus, and a null LLM stub, matching the pattern from
test_companion_preferences.py.

@decision DEC-ONBOARDING-001
@title Onboarding status stored as a TEXT column on the users table
@status accepted
@rationale See ada/api/routes/onboarding.py for full rationale. Tests exercise
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

_USER_ID = "user-onboarding-001"
_USER_EMAIL = "onboarding-user@example.com"


def _make_user() -> User:
    return User(
        id=_USER_ID,
        email=_USER_EMAIL,
        role="user",
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
        "role": "user",
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
async def test_default_status_for_new_user_is_not_started(state: StateManager):
    """A freshly-created user has onboarding_status 'not_started'."""
    status = await state.get_onboarding_status(_USER_ID)
    assert status == "not_started"


@pytest.mark.asyncio
async def test_get_onboarding_status_returns_not_started_for_unknown_user(state: StateManager):
    """get_onboarding_status returns 'not_started' when the user does not exist."""
    status = await state.get_onboarding_status("nonexistent-user-id")
    assert status == "not_started"


@pytest.mark.asyncio
async def test_set_to_in_progress_then_get(state: StateManager):
    """Set to 'in_progress', then get returns 'in_progress'."""
    await state.set_onboarding_status(_USER_ID, "in_progress")
    status = await state.get_onboarding_status(_USER_ID)
    assert status == "in_progress"


@pytest.mark.asyncio
async def test_set_to_completed(state: StateManager):
    """Set to 'completed', then get returns 'completed'."""
    await state.set_onboarding_status(_USER_ID, "in_progress")
    await state.set_onboarding_status(_USER_ID, "completed")
    status = await state.get_onboarding_status(_USER_ID)
    assert status == "completed"


@pytest.mark.asyncio
async def test_set_status_round_trip_all_valid_values(state: StateManager):
    """All three valid status values can be stored and retrieved."""
    for value in ("not_started", "in_progress", "completed"):
        await state.set_onboarding_status(_USER_ID, value)
        result = await state.get_onboarding_status(_USER_ID)
        assert result == value


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_http_get_returns_not_started_for_new_user(state: StateManager):
    """GET /api/onboarding/status returns 'not_started' for a new user."""
    with _client(state, _make_user()) as client:
        resp = client.get("/api/onboarding/status")

    assert resp.status_code == 200
    assert resp.json() == {"status": "not_started"}


@pytest.mark.asyncio
async def test_http_put_in_progress_and_get(state: StateManager):
    """PUT 'in_progress' then GET returns 'in_progress'."""
    with _client(state, _make_user()) as client:
        put_resp = client.put("/api/onboarding/status", json={"status": "in_progress"})
        assert put_resp.status_code == 200
        assert put_resp.json() == {"status": "in_progress"}

        get_resp = client.get("/api/onboarding/status")

    assert get_resp.status_code == 200
    assert get_resp.json() == {"status": "in_progress"}


@pytest.mark.asyncio
async def test_http_put_completed(state: StateManager):
    """PUT 'completed' returns 'completed' and persists."""
    with _client(state, _make_user()) as client:
        client.put("/api/onboarding/status", json={"status": "in_progress"})
        put_resp = client.put("/api/onboarding/status", json={"status": "completed"})
        assert put_resp.status_code == 200
        assert put_resp.json() == {"status": "completed"}

        get_resp = client.get("/api/onboarding/status")

    assert get_resp.status_code == 200
    assert get_resp.json() == {"status": "completed"}


@pytest.mark.asyncio
async def test_http_put_not_started_rejected_422(state: StateManager):
    """PUT 'not_started' is rejected with HTTP 422 (cannot revert to initial state)."""
    with _client(state, _make_user()) as client:
        resp = client.put("/api/onboarding/status", json={"status": "not_started"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_http_put_invalid_status_rejected_422(state: StateManager):
    """PUT with an unrecognised status value returns HTTP 422."""
    with _client(state, _make_user()) as client:
        resp = client.put("/api/onboarding/status", json={"status": "banana"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_http_get_requires_auth(state: StateManager):
    """GET /api/onboarding/status without auth returns 401."""
    with _client(state, user=None) as client:
        resp = client.get("/api/onboarding/status")

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_http_put_requires_auth(state: StateManager):
    """PUT /api/onboarding/status without auth returns 401."""
    with _client(state, user=None) as client:
        resp = client.put("/api/onboarding/status", json={"status": "in_progress"})

    assert resp.status_code == 401
