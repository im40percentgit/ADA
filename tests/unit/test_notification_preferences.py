"""
Unit tests for notification preferences, per-user throttling, and deduplication.

Tests:
  - Default preferences are returned when none set
  - Preferences CRUD (get/set/update)
  - Throttle: suppress if same event_type sent within window
  - Throttle: crisis bypasses throttle window
  - Throttle: respects preferences — even crisis suppressed if user disabled it
  - Dedup: suppress exact duplicate within dedup window
  - Dedup: different event type is not suppressed
  - Dedup: same event after window passes is not suppressed
  - State: create/get notification_preferences rows

@decision DEC-NOTIF-008
@title Preferences + throttle + dedup tested with real in-memory StateManager
@status accepted
@rationale No mocks of internal modules. Real SQLite exercises constraints and
    JSON serialisation. Consistent with DEC-TEST-001 and Sacred Practice #5.
"""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest
import pytest_asyncio

from ada.core.config import NotificationThrottleConfig
from ada.core.state import StateManager
from ada.notifications.preferences import NotificationPreferenceManager


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
    """StateManager with one user."""
    await state.create_user({
        "id": "user-pref-001",
        "email": "pref@example.com",
        "hashed_password": "hashed",
        "role": "caregiver",
        "patient_id": None,
    })
    return state


def _pref_manager(state: StateManager, throttle_seconds: float = 30.0, dedup_seconds: float = 5.0) -> NotificationPreferenceManager:
    config = NotificationThrottleConfig(
        throttle_window_seconds=throttle_seconds,
        dedup_window_seconds=dedup_seconds,
    )
    return NotificationPreferenceManager(state, config)


# ---------------------------------------------------------------------------
# Preference CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_preferences_returned_when_none_set(populated: StateManager):
    """get_preferences returns default prefs when no row exists."""
    mgr = _pref_manager(populated)
    prefs = await mgr.get_preferences("user-pref-001")

    # All event types should default to enabled
    assert prefs["crisis_detected"] is True
    assert prefs["board_item_suggested"] is True
    assert prefs["board_item_added"] is True
    assert prefs["board_item_checked"] is True
    assert prefs["daily_summary_generated"] is True
    assert prefs["circle_member_added"] is True


@pytest.mark.asyncio
async def test_set_and_get_preferences(populated: StateManager):
    """set_preferences persists and get_preferences returns correct values."""
    mgr = _pref_manager(populated)

    await mgr.set_preferences("user-pref-001", {
        "crisis_detected": True,
        "board_item_suggested": False,
        "board_item_added": True,
        "board_item_checked": False,
        "daily_summary_generated": True,
        "circle_member_added": False,
    })

    prefs = await mgr.get_preferences("user-pref-001")
    assert prefs["crisis_detected"] is True
    assert prefs["board_item_suggested"] is False
    assert prefs["board_item_checked"] is False
    assert prefs["circle_member_added"] is False


@pytest.mark.asyncio
async def test_set_preferences_replaces_existing(populated: StateManager):
    """Calling set_preferences twice replaces the row (upsert)."""
    mgr = _pref_manager(populated)

    await mgr.set_preferences("user-pref-001", {
        "crisis_detected": True,
        "board_item_suggested": True,
        "board_item_added": True,
        "board_item_checked": True,
        "daily_summary_generated": True,
        "circle_member_added": True,
    })
    await mgr.set_preferences("user-pref-001", {
        "crisis_detected": False,
        "board_item_suggested": False,
        "board_item_added": False,
        "board_item_checked": False,
        "daily_summary_generated": False,
        "circle_member_added": False,
    })

    prefs = await mgr.get_preferences("user-pref-001")
    assert prefs["crisis_detected"] is False
    assert prefs["daily_summary_generated"] is False


# ---------------------------------------------------------------------------
# should_send: preference gating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_should_send_respects_disabled_preference(populated: StateManager):
    """If user disables board_item_suggested, should_send returns False."""
    mgr = _pref_manager(populated, throttle_seconds=3600.0)

    await mgr.set_preferences("user-pref-001", {
        "crisis_detected": True,
        "board_item_suggested": False,
        "board_item_added": True,
        "board_item_checked": True,
        "daily_summary_generated": True,
        "circle_member_added": True,
    })

    result = await mgr.should_send("user-pref-001", "board.item.suggested", "dedup-key-1")
    assert result is False


@pytest.mark.asyncio
async def test_should_send_true_when_preference_enabled(populated: StateManager):
    """should_send returns True for enabled event type (no prior sends)."""
    mgr = _pref_manager(populated, throttle_seconds=3600.0)
    result = await mgr.should_send("user-pref-001", "board.item.suggested", "dedup-key-2")
    assert result is True


@pytest.mark.asyncio
async def test_crisis_disabled_by_preference_is_suppressed(populated: StateManager):
    """
    Per spec: crisis bypasses throttle but NOT preferences.
    If user disables crisis_detected, even crisis notifications are suppressed.
    """
    mgr = _pref_manager(populated, throttle_seconds=3600.0)

    await mgr.set_preferences("user-pref-001", {
        "crisis_detected": False,
        "board_item_suggested": True,
        "board_item_added": True,
        "board_item_checked": True,
        "daily_summary_generated": True,
        "circle_member_added": True,
    })

    result = await mgr.should_send("user-pref-001", "crisis.detected", "dedup-key-crisis")
    assert result is False


# ---------------------------------------------------------------------------
# should_send: throttle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_throttle_suppresses_repeat_event_within_window(populated: StateManager):
    """Same event type for same user within throttle window → second call returns False."""
    mgr = _pref_manager(populated, throttle_seconds=3600.0)

    key1 = "dedup-throttle-1"
    key2 = "dedup-throttle-2"

    # First send — allowed
    r1 = await mgr.should_send("user-pref-001", "board.item.added", key1)
    assert r1 is True
    await mgr.record_sent("user-pref-001", "board.item.added", key1)

    # Second send of same event_type (different dedup key) — throttled
    r2 = await mgr.should_send("user-pref-001", "board.item.added", key2)
    assert r2 is False


@pytest.mark.asyncio
async def test_throttle_does_not_suppress_different_event_type(populated: StateManager):
    """Throttle is per event_type. Different types are independent."""
    mgr = _pref_manager(populated, throttle_seconds=3600.0)

    await mgr.should_send("user-pref-001", "board.item.added", "key-a")
    await mgr.record_sent("user-pref-001", "board.item.added", "key-a")

    # Different event type — not throttled
    r = await mgr.should_send("user-pref-001", "board.item.checked", "key-b")
    assert r is True


@pytest.mark.asyncio
async def test_crisis_bypasses_throttle(populated: StateManager):
    """
    Per spec: crisis bypasses throttle but NOT preferences.
    Two consecutive crisis events: second is still sent.
    """
    mgr = _pref_manager(populated, throttle_seconds=3600.0)

    r1 = await mgr.should_send("user-pref-001", "crisis.detected", "crisis-key-1")
    assert r1 is True
    await mgr.record_sent("user-pref-001", "crisis.detected", "crisis-key-1")

    r2 = await mgr.should_send("user-pref-001", "crisis.detected", "crisis-key-2")
    assert r2 is True


# ---------------------------------------------------------------------------
# should_send: deduplication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dedup_suppresses_identical_dedup_key_within_window(populated: StateManager):
    """Same dedup_key within dedup window → second call suppressed."""
    mgr = _pref_manager(populated, throttle_seconds=3600.0, dedup_seconds=60.0)

    dedup_key = "board-item-xyz"
    r1 = await mgr.should_send("user-pref-001", "board.item.added", dedup_key)
    assert r1 is True
    await mgr.record_sent("user-pref-001", "board.item.added", dedup_key)

    r2 = await mgr.should_send("user-pref-001", "board.item.added", dedup_key)
    assert r2 is False


@pytest.mark.asyncio
async def test_dedup_allows_different_dedup_key(populated: StateManager):
    """Different dedup key for same event type → not dedup-suppressed (throttle may apply)."""
    mgr = _pref_manager(populated, throttle_seconds=0.0, dedup_seconds=60.0)

    await mgr.should_send("user-pref-001", "board.item.added", "item-1")
    await mgr.record_sent("user-pref-001", "board.item.added", "item-1")

    r = await mgr.should_send("user-pref-001", "board.item.added", "item-2")
    assert r is True


# ---------------------------------------------------------------------------
# StateManager: notification_preferences table
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_state_set_and_get_notification_preferences(populated: StateManager):
    """StateManager.set/get notification_preferences round-trips JSON correctly."""
    prefs = {
        "crisis_detected": True,
        "board_item_suggested": False,
        "board_item_added": True,
        "board_item_checked": False,
        "daily_summary_generated": True,
        "circle_member_added": False,
    }
    await populated.set_notification_preferences("user-pref-001", prefs)
    result = await populated.get_notification_preferences("user-pref-001")
    assert result is not None
    assert result["board_item_suggested"] is False
    assert result["crisis_detected"] is True


@pytest.mark.asyncio
async def test_state_get_notification_preferences_none_when_missing(state: StateManager):
    """get_notification_preferences returns None when no row exists."""
    # No user, no prefs — still returns None
    result = await state.get_notification_preferences("nonexistent-user")
    assert result is None


@pytest.mark.asyncio
async def test_state_upsert_notification_preferences(populated: StateManager):
    """set_notification_preferences is idempotent — replaces on repeat."""
    await populated.set_notification_preferences("user-pref-001", {"crisis_detected": True, "board_item_suggested": True})
    await populated.set_notification_preferences("user-pref-001", {"crisis_detected": False, "board_item_suggested": False})

    result = await populated.get_notification_preferences("user-pref-001")
    assert result["crisis_detected"] is False
    assert result["board_item_suggested"] is False


# ---------------------------------------------------------------------------
# StateManager: notification_throttle_log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_state_record_and_get_last_sent(populated: StateManager):
    """record_notification_sent + get_last_notification_sent round-trips correctly."""
    ts = time.time()
    await populated.record_notification_sent("user-pref-001", "board.item.added", "dedup-key-111", ts)
    result = await populated.get_last_notification_sent("user-pref-001", "board.item.added")
    assert result is not None
    assert abs(result - ts) < 1.0


@pytest.mark.asyncio
async def test_state_dedup_key_lookup(populated: StateManager):
    """get_dedup_key_last_sent returns timestamp for a specific dedup key."""
    ts = time.time()
    await populated.record_notification_sent("user-pref-001", "crisis.detected", "crisis-dedup-001", ts)
    result = await populated.get_dedup_key_last_sent("user-pref-001", "crisis.detected", "crisis-dedup-001")
    assert result is not None
    assert abs(result - ts) < 1.0


@pytest.mark.asyncio
async def test_state_dedup_key_none_when_missing(populated: StateManager):
    """get_dedup_key_last_sent returns None when key not recorded."""
    result = await populated.get_dedup_key_last_sent("user-pref-001", "crisis.detected", "never-seen")
    assert result is None
