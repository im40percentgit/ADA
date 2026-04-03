"""Integration tests: push notification REST lifecycle and dispatcher logging.

Exercises the notification flow from subscription management through
event-driven dispatcher logging using a real in-memory SQLite StateManager
and FastAPI TestClient.

Test coverage:
- Full subscription REST lifecycle: subscribe, vapid-key, unsubscribe
- Subscription persists to DB and is cleaned up on DELETE
- NotificationDispatcher logs notifications to notification_log when
  VAPID key is absent (log-only path, no real HTTP push required)

@decision DEC-NOTIF-007
@title Notification integration test uses log-only path for dispatcher
@status accepted
@rationale When VAPID private key is empty, _send_push() logs the record
    before returning, giving us a deterministic audit trail to assert
    against without needing a real push endpoint or mocking pywebpush.
    This tests the full dispatcher path (event -> circle lookup -> role
    filter -> subscription fetch -> log write) without external dependencies.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime

import pytest
import pytest_asyncio

from fastapi.testclient import TestClient

from ada.agents.registry import AgentRegistry
from ada.api.app import create_app
from ada.api.auth import get_current_user
from ada.core.bus import EventBus
from ada.core.config import AdaConfig, NotificationConfig
from ada.core.events import CrisisDetectedEvent
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from ada.llm.router import make_null_router
from ada.models.user import User
from ada.notifications.dispatcher import NotificationDispatcher


# ---------------------------------------------------------------------------
# Shared test helpers (mirrors test_circle_flow.py and test_board_flow.py)
# ---------------------------------------------------------------------------


class _NullLLM(LLMProvider):
    async def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(content="", model="null", input_tokens=0, output_tokens=0)

    async def stream(self, messages, **kwargs):
        return
        yield


def _make_client(state: StateManager, user: User) -> TestClient:
    """Return a TestClient that must be used as a context manager to trigger lifespan."""
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=True)


def _user(uid: str, email: str, role: str = "caregiver") -> User:
    return User(
        id=uid,
        email=email,
        role=role,
        patient_id=None,
        created_at=datetime.utcnow(),
        is_active=True,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def state():
    """In-memory StateManager seeded with a user."""
    sm = StateManager(":memory:")
    await sm.initialize()

    await sm._exec(
        "INSERT INTO users (id, email, hashed_password, role, created_at, is_active)"
        " VALUES (?, ?, ?, ?, datetime('now'), 1)",
        ("user-cg", "caregiver@test.com", "hashed", "caregiver"),
    )

    yield sm
    await sm.close()


@pytest_asyncio.fixture
async def state_with_circle():
    """In-memory StateManager seeded with user, patient, circle, and membership."""
    sm = StateManager(":memory:")
    await sm.initialize()

    await sm._exec(
        "INSERT INTO users (id, email, hashed_password, role, created_at, is_active)"
        " VALUES (?, ?, ?, ?, datetime('now'), 1)",
        ("user-cg", "caregiver@test.com", "hashed", "caregiver"),
    )

    await sm.create_patient({
        "id": "pat-1",
        "name": "Alice",
        "dob": "1990-01-01",
        "emergency_contact": None,
        "caregiver_id": None,
    })

    await sm.create_care_circle("circle-1", "pat-1")
    await sm.add_circle_member(
        member_id=str(uuid.uuid4()),
        circle_id="circle-1",
        user_id="user-cg",
        role="primary_caregiver",
    )

    yield sm
    await sm.close()


# ---------------------------------------------------------------------------
# Test 1: Full subscription REST lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscribe_and_list(state: StateManager):
    """Subscribe -> verify DB -> vapid-key -> unsubscribe -> verify removed."""
    user = _user("user-cg", "caregiver@test.com")
    endpoint = "https://push.example.com/abc"

    with _make_client(state, user) as client:
        # 1. POST subscribe
        resp = client.post(
            "/api/notifications/subscribe",
            json={
                "endpoint": endpoint,
                "keys": {
                    "p256dh": "test-p256dh-key",
                    "auth": "test-auth-key",
                },
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "id" in data

        # 2. Verify subscription persisted in DB
        subs = await state.get_push_subscriptions("user-cg")
        assert len(subs) == 1
        assert subs[0]["endpoint"] == endpoint
        assert subs[0]["p256dh_key"] == "test-p256dh-key"
        assert subs[0]["auth_key"] == "test-auth-key"
        assert subs[0]["user_id"] == "user-cg"

        # 3. GET vapid-key — may be empty string when env not set; that is OK
        resp = client.get("/api/notifications/vapid-key")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "public_key" in body
        assert isinstance(body["public_key"], str)

        # 4. DELETE unsubscribe — Starlette TestClient.delete() does not expose
        #    a body parameter, so use the generic request() method instead.
        resp = client.request(
            "DELETE",
            "/api/notifications/subscribe",
            content=json.dumps({"endpoint": endpoint}),
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 204, resp.text

        # 5. Verify subscription removed from DB
        subs = await state.get_push_subscriptions("user-cg")
        assert len(subs) == 0


# ---------------------------------------------------------------------------
# Test 2: NotificationDispatcher logs notifications via log-only path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatcher_logs_notification(state_with_circle: StateManager):
    """NotificationDispatcher writes a notification_log entry when VAPID key is absent.

    When _vapid_private_key is empty, _send_push() logs the notification
    and returns early -- no real HTTP push is made. This tests the full
    dispatcher pipeline: event publish -> circle lookup -> role filter ->
    subscription fetch -> notification_log write.
    """
    state = state_with_circle

    # Seed a push subscription for the caregiver
    await state.create_push_subscription({
        "id": str(uuid.uuid4()),
        "user_id": "user-cg",
        "endpoint": "https://push.example.com/test",
        "p256dh_key": "test-p256dh",
        "auth_key": "test-auth",
    })

    # Create EventBus and start it
    bus = EventBus()
    await bus.start()

    try:
        # Instantiate dispatcher with empty VAPID keys (log-only path).
        # NotificationConfig defaults: vapid_private_key_env = "ADA_VAPID_PRIVATE_KEY".
        # Since the env var is not set, _vapid_private_key will be "" -> log-only.
        config = NotificationConfig()
        dispatcher = NotificationDispatcher(bus, state, config)

        # Publish a CRISIS_DETECTED event for patient pat-1
        await bus.publish(
            CrisisDetectedEvent(
                patient_id="pat-1",
                session_id="sess-test",
                severity="HIGH",
                trigger_text="I want to hurt myself",
                detection_method="keyword",
                escalation_action="alert_caregiver",
            )
        )

        # Wait briefly for async handler to complete
        await asyncio.sleep(0.2)

    finally:
        await bus.stop()

    # Verify notification_log has an entry for user-cg
    logs = await state._fetchall(
        "SELECT * FROM notification_log WHERE user_id = ?",
        ("user-cg",),
    )
    assert len(logs) >= 1, f"Expected at least 1 log entry, got {len(logs)}"
    log = dict(logs[0])
    assert log["event_type"] == "crisis.detected"
    assert log["user_id"] == "user-cg"
    assert "Crisis" in log["title"]
