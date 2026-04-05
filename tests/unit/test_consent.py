"""
Unit tests for consent management: StateManager CRUD + REST endpoints.

Uses a real in-memory SQLite database for all tests -- no mocks of internal
code. HTTP tests use FastAPI TestClient wired through create_app with a real
AdaConfig, EventBus, and a null LLM stub, matching the pattern established
in test_companion_preferences.py.

@decision DEC-CONSENT-001
@title Consent stored per-user with upsert semantics and default-deny
@status accepted
@rationale See ada/api/routes/consent.py for full rationale. Tests exercise
    the full HTTP -> StateManager -> SQLite stack without mocking internals.
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

_USER_ID = "user-consent-001"
_USER_EMAIL = "consent-user@example.com"


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
async def test_get_user_consents_returns_empty_when_none(state: StateManager):
    """get_user_consents returns empty list for a user with no consent records."""
    result = await state.get_user_consents(_USER_ID)
    assert result == []


@pytest.mark.asyncio
async def test_grant_consent(state: StateManager):
    """Granting consent creates a record with granted=True."""
    await state.set_consent(_USER_ID, "data_collection", True)
    records = await state.get_user_consents(_USER_ID)

    assert len(records) == 1
    assert records[0]["consent_type"] == "data_collection"
    assert records[0]["granted"] is True
    assert records[0]["version"] == "1.0"
    assert records[0]["revoked_at"] is None


@pytest.mark.asyncio
async def test_revoke_consent(state: StateManager):
    """Granting then revoking sets granted=False and populates revoked_at."""
    await state.set_consent(_USER_ID, "data_collection", True)
    await state.set_consent(_USER_ID, "data_collection", False)
    records = await state.get_user_consents(_USER_ID)

    assert len(records) == 1
    assert records[0]["granted"] is False
    assert records[0]["revoked_at"] is not None


@pytest.mark.asyncio
async def test_re_grant_consent(state: StateManager):
    """Re-granting after revoke sets granted=True and clears revoked_at."""
    await state.set_consent(_USER_ID, "data_collection", True)
    await state.set_consent(_USER_ID, "data_collection", False)
    await state.set_consent(_USER_ID, "data_collection", True)
    records = await state.get_user_consents(_USER_ID)

    assert len(records) == 1
    assert records[0]["granted"] is True
    assert records[0]["revoked_at"] is None


@pytest.mark.asyncio
async def test_multiple_consent_types(state: StateManager):
    """Multiple consent types are stored as separate records."""
    await state.set_consent(_USER_ID, "data_collection", True)
    await state.set_consent(_USER_ID, "ai_analysis", False)
    await state.set_consent(_USER_ID, "research", True, version="2.0")
    records = await state.get_user_consents(_USER_ID)

    assert len(records) == 3
    by_type = {r["consent_type"]: r for r in records}
    assert by_type["data_collection"]["granted"] is True
    assert by_type["ai_analysis"]["granted"] is False
    assert by_type["research"]["granted"] is True
    assert by_type["research"]["version"] == "2.0"


@pytest.mark.asyncio
async def test_revoke_without_prior_grant(state: StateManager):
    """Revoking a consent type that was never granted creates a not-granted row."""
    await state.set_consent(_USER_ID, "data_sharing", False)
    records = await state.get_user_consents(_USER_ID)

    assert len(records) == 1
    assert records[0]["granted"] is False
    assert records[0]["revoked_at"] is not None


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_http_get_defaults_when_no_consents(state: StateManager):
    """GET /api/consent returns default not-granted entries for all consent types."""
    with _client(state, _make_user()) as client:
        resp = client.get("/api/consent")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 4  # all four consent types
    by_type = {r["consent_type"]: r for r in data}
    for ct in ("data_collection", "ai_analysis", "data_sharing", "research"):
        assert ct in by_type
        assert by_type[ct]["granted"] is False


@pytest.mark.asyncio
async def test_http_put_grant_and_get(state: StateManager):
    """PUT to grant consent, then GET returns it granted."""
    with _client(state, _make_user()) as client:
        put_resp = client.put("/api/consent", json={
            "consent_type": "data_collection",
            "granted": True,
        })
        assert put_resp.status_code == 200
        assert put_resp.json() == {"status": "ok"}

        get_resp = client.get("/api/consent")

    data = get_resp.json()
    by_type = {r["consent_type"]: r for r in data}
    assert by_type["data_collection"]["granted"] is True
    # Other types remain not-granted
    assert by_type["ai_analysis"]["granted"] is False
    assert by_type["data_sharing"]["granted"] is False
    assert by_type["research"]["granted"] is False


@pytest.mark.asyncio
async def test_http_put_revoke(state: StateManager):
    """PUT to grant then revoke returns granted=False."""
    with _client(state, _make_user()) as client:
        client.put("/api/consent", json={
            "consent_type": "ai_analysis",
            "granted": True,
        })
        client.put("/api/consent", json={
            "consent_type": "ai_analysis",
            "granted": False,
        })
        get_resp = client.get("/api/consent")

    by_type = {r["consent_type"]: r for r in get_resp.json()}
    assert by_type["ai_analysis"]["granted"] is False
    assert by_type["ai_analysis"]["revoked_at"] is not None


@pytest.mark.asyncio
async def test_http_put_invalid_consent_type(state: StateManager):
    """PUT with an invalid consent_type returns HTTP 422."""
    with _client(state, _make_user()) as client:
        resp = client.put("/api/consent", json={
            "consent_type": "invalid_type",
            "granted": True,
        })

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_http_put_missing_granted(state: StateManager):
    """PUT without granted field returns HTTP 422."""
    with _client(state, _make_user()) as client:
        resp = client.put("/api/consent", json={
            "consent_type": "data_collection",
        })

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_http_put_non_boolean_granted(state: StateManager):
    """PUT with non-boolean granted returns HTTP 422."""
    with _client(state, _make_user()) as client:
        resp = client.put("/api/consent", json={
            "consent_type": "data_collection",
            "granted": "yes",
        })

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_http_requires_auth(state: StateManager):
    """GET /api/consent without auth returns 401."""
    with _client(state, user=None) as client:
        resp = client.get("/api/consent")

    assert resp.status_code == 401
