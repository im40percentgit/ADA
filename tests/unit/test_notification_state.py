"""
Unit tests for push subscription and notification log CRUD in StateManager.

Uses a real in-memory SQLite database — no mocks of internal modules.
All 5 tests verify schema constraints and query correctness directly
against the StateManager methods added in Phase 10.

@decision DEC-NOTIF-001
@title Notification state tests use real in-memory SQLite
@status accepted
@rationale Consistent with DEC-TEST-001 and Sacred Practice #5. Real SQL
    constraints (UNIQUE on endpoint, FK to users) are tested without any
    mocks. Fast, zero-dependency, exercises actual schema.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from ada.core.state import StateManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


@pytest_asyncio.fixture
async def populated(state: StateManager) -> StateManager:
    """StateManager pre-populated with two users for FK references."""
    await state.create_user({
        "id": "user-1",
        "email": "alice@example.com",
        "hashed_password": "hashed",
        "role": "caregiver",
        "patient_id": None,
    })
    await state.create_user({
        "id": "user-2",
        "email": "bob@example.com",
        "hashed_password": "hashed",
        "role": "caregiver",
        "patient_id": None,
    })
    return state


def _sub(user_id: str = "user-1", endpoint: str = "https://push.example.com/sub/abc") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "endpoint": endpoint,
        "p256dh_key": "BNbxxx==",
        "auth_key": "authyyy==",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_push_subscription(populated: StateManager):
    """Create a subscription and retrieve it."""
    sub = _sub()
    await populated.create_push_subscription(sub)

    rows = await populated.get_push_subscriptions("user-1")
    assert len(rows) == 1
    assert rows[0]["endpoint"] == sub["endpoint"]
    assert rows[0]["p256dh_key"] == sub["p256dh_key"]
    assert rows[0]["auth_key"] == sub["auth_key"]
    assert rows[0]["user_id"] == "user-1"


@pytest.mark.asyncio
async def test_push_subscription_replace_on_duplicate_endpoint(populated: StateManager):
    """INSERT OR REPLACE: re-subscribing same endpoint updates keys, no error."""
    sub1 = _sub()
    await populated.create_push_subscription(sub1)

    # Same endpoint, new id and keys (simulates browser re-subscription)
    sub2 = {
        "id": str(uuid.uuid4()),
        "user_id": "user-1",
        "endpoint": sub1["endpoint"],   # same endpoint
        "p256dh_key": "BNbnew==",
        "auth_key": "authnew==",
    }
    await populated.create_push_subscription(sub2)

    rows = await populated.get_push_subscriptions("user-1")
    assert len(rows) == 1               # still one row
    assert rows[0]["p256dh_key"] == "BNbnew=="   # updated
    assert rows[0]["auth_key"] == "authnew=="


@pytest.mark.asyncio
async def test_get_subscriptions_by_user(populated: StateManager):
    """Multiple devices for one user; another user's sub not returned."""
    await populated.create_push_subscription(_sub("user-1", "https://push.example.com/sub/1"))
    await populated.create_push_subscription(_sub("user-1", "https://push.example.com/sub/2"))
    await populated.create_push_subscription(_sub("user-2", "https://push.example.com/sub/3"))

    user1_rows = await populated.get_push_subscriptions("user-1")
    user2_rows = await populated.get_push_subscriptions("user-2")

    assert len(user1_rows) == 2
    assert len(user2_rows) == 1
    endpoints = {r["endpoint"] for r in user1_rows}
    assert "https://push.example.com/sub/1" in endpoints
    assert "https://push.example.com/sub/2" in endpoints


@pytest.mark.asyncio
async def test_delete_push_subscription(populated: StateManager):
    """Delete by endpoint; other subscriptions unaffected."""
    await populated.create_push_subscription(_sub("user-1", "https://push.example.com/sub/a"))
    await populated.create_push_subscription(_sub("user-1", "https://push.example.com/sub/b"))

    await populated.delete_push_subscription("https://push.example.com/sub/a")

    rows = await populated.get_push_subscriptions("user-1")
    assert len(rows) == 1
    assert rows[0]["endpoint"] == "https://push.example.com/sub/b"


@pytest.mark.asyncio
async def test_create_notification_log(populated: StateManager):
    """Notification log entry is persisted."""
    entry = {
        "id": str(uuid.uuid4()),
        "user_id": "user-1",
        "event_type": "crisis.detected",
        "title": "Crisis Alert",
        "body": "Severity: HIGH",
    }
    await populated.create_notification_log(entry)

    # Verify via direct SQL (no public getter needed for these tests)
    rows = await populated._fetchall(
        "SELECT * FROM notification_log WHERE user_id = ?", ("user-1",)
    )
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["title"] == "Crisis Alert"
    assert row["event_type"] == "crisis.detected"
