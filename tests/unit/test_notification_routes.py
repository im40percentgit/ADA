"""
Unit tests for push notification REST endpoints.

Uses a real in-memory StateManager and FastAPI TestClient with
dependency_overrides to inject authenticated users — the same pattern
as test_circle_routes.py (DEC-CIRCLE-004).

Coverage:
  POST   /api/notifications/subscribe    — 201 with sub id
  DELETE /api/notifications/subscribe    — 204
  GET    /api/notifications/vapid-key    — returns public key
  POST   /api/notifications/subscribe    — 401 without auth

@decision DEC-NOTIF-001
@title Notification route tests use real StateManager
@status accepted
@rationale Mocking StateManager would hide SQL constraint errors. A real
    in-memory SQLite DB exercises the full stack from HTTP request through
    SQL queries to JSON response, matching Sacred Practice #5 and the
    pattern established in test_circle_routes.py (DEC-CIRCLE-004).
"""

from __future__ import annotations

import os
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
# Minimal LLM stub
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

_USER_ID = "user-notif-route-001"
_USER_EMAIL = "notif-user@example.com"

_SUBSCRIPTION_BODY = {
    "endpoint": "https://push.example.com/endpoint/abc123",
    "keys": {
        "p256dh": "BNbp256dhKey==",
        "auth": "authKey==",
    },
}


# ---------------------------------------------------------------------------
# User stub
# ---------------------------------------------------------------------------

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
# Client factory
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
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_subscribe(state: StateManager):
    """POST /api/notifications/subscribe → 201 with subscription id."""
    with _client(state, _make_user()) as client:
        resp = client.post("/api/notifications/subscribe", json=_SUBSCRIPTION_BODY)

    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert len(data["id"]) > 0

    # Verify stored in DB
    subs = await state.get_push_subscriptions(_USER_ID)
    assert len(subs) == 1
    assert subs[0]["endpoint"] == _SUBSCRIPTION_BODY["endpoint"]
    assert subs[0]["p256dh_key"] == _SUBSCRIPTION_BODY["keys"]["p256dh"]


@pytest.mark.asyncio
async def test_unsubscribe(state: StateManager):
    """DELETE /api/notifications/subscribe → 204, subscription removed."""
    import uuid
    await state.create_push_subscription({
        "id": str(uuid.uuid4()),
        "user_id": _USER_ID,
        "endpoint": _SUBSCRIPTION_BODY["endpoint"],
        "p256dh_key": _SUBSCRIPTION_BODY["keys"]["p256dh"],
        "auth_key": _SUBSCRIPTION_BODY["keys"]["auth"],
    })

    with _client(state, _make_user()) as client:
        resp = client.request(
            "DELETE",
            "/api/notifications/subscribe",
            json={"endpoint": _SUBSCRIPTION_BODY["endpoint"]},
        )

    assert resp.status_code == 204

    subs = await state.get_push_subscriptions(_USER_ID)
    assert len(subs) == 0


@pytest.mark.asyncio
async def test_vapid_key(state: StateManager):
    """GET /api/notifications/vapid-key → returns public_key field."""
    os.environ["ADA_VAPID_PUBLIC_KEY"] = "test-public-vapid-key"
    try:
        with _client(state) as client:
            resp = client.get("/api/notifications/vapid-key")
    finally:
        os.environ.pop("ADA_VAPID_PUBLIC_KEY", None)

    assert resp.status_code == 200
    data = resp.json()
    assert "public_key" in data
    assert data["public_key"] == "test-public-vapid-key"


@pytest.mark.asyncio
async def test_subscribe_requires_auth(state: StateManager):
    """POST /api/notifications/subscribe without auth → 401."""
    with _client(state, user=None) as client:
        resp = client.post("/api/notifications/subscribe", json=_SUBSCRIPTION_BODY)

    assert resp.status_code == 401
