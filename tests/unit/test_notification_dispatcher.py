"""
Unit tests for NotificationDispatcher.

Uses a real in-memory StateManager and EventBus. pywebpush.webpush is
patched to avoid real HTTP calls — it is the only external boundary mocked,
consistent with Sacred Practice #5 (mock only external boundaries).

@decision DEC-NOTIF-002
@title NotificationDispatcher tests mock only pywebpush external boundary
@status accepted
@rationale StateManager, EventBus, and all Ada internals are tested with real
    implementations. Only pywebpush.webpush (outbound HTTP to push service)
    is mocked. Consistent with DEC-TEST-005 and Sacred Practice #5.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from ada.core.bus import EventBus
from ada.core.config import NotificationConfig
from ada.core.events import (
    BoardItemSuggestedEvent,
    CircleMemberAddedEvent,
    CrisisDetectedEvent,
    EventTypes,
)
from ada.core.state import StateManager
from ada.notifications.dispatcher import NotificationDispatcher


# ---------------------------------------------------------------------------
# Fixed IDs
# ---------------------------------------------------------------------------

_PATIENT_ID = "patient-disp-001"
_CIRCLE_ID = "circle-disp-001"

_PC_ID = "user-pc-001"        # primary_caregiver
_FAM_ID = "user-fam-001"      # family
_CLIN_ID = "user-clin-001"    # clinician

_ENDPOINT_PC = "https://push.example.com/pc"
_ENDPOINT_FAM = "https://push.example.com/fam"
_ENDPOINT_CLIN = "https://push.example.com/clin"


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
    """Pre-populate: patient + care circle + 3 members (pc/family/clinician) + 1 sub each."""
    # Patient
    await state.create_patient({
        "id": _PATIENT_ID,
        "name": "Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })

    # Users
    for uid, email, role in [
        (_PC_ID, "pc@example.com", "caregiver"),
        (_FAM_ID, "fam@example.com", "caregiver"),
        (_CLIN_ID, "clin@example.com", "clinician"),
    ]:
        await state.create_user({
            "id": uid,
            "email": email,
            "hashed_password": "hashed",
            "role": role,
            "patient_id": None,
        })

    # Care circle
    await state.create_care_circle(_CIRCLE_ID, _PATIENT_ID)
    await state.add_circle_member(
        f"ccm-pc-{_CIRCLE_ID}", _CIRCLE_ID, _PC_ID, "primary_caregiver"
    )
    await state.add_circle_member(
        f"ccm-fam-{_CIRCLE_ID}", _CIRCLE_ID, _FAM_ID, "family"
    )
    await state.add_circle_member(
        f"ccm-clin-{_CIRCLE_ID}", _CIRCLE_ID, _CLIN_ID, "clinician"
    )

    # Push subscriptions
    for uid, endpoint in [
        (_PC_ID, _ENDPOINT_PC),
        (_FAM_ID, _ENDPOINT_FAM),
        (_CLIN_ID, _ENDPOINT_CLIN),
    ]:
        await state.create_push_subscription({
            "id": str(uuid.uuid4()),
            "user_id": uid,
            "endpoint": endpoint,
            "p256dh_key": "key==",
            "auth_key": "auth==",
        })

    return state


@pytest_asyncio.fixture
async def bus() -> EventBus:
    b = EventBus()
    await b.start()
    yield b
    await b.stop()


def _make_dispatcher(bus: EventBus, state: StateManager, vapid_key: str = "") -> NotificationDispatcher:
    config = NotificationConfig(
        enabled=True,
        vapid_private_key_env="TEST_VAPID_PRIV",
        vapid_public_key_env="TEST_VAPID_PUB",
        vapid_email="mailto:test@ada.local",
    )
    import os
    if vapid_key:
        os.environ["TEST_VAPID_PRIV"] = vapid_key
    else:
        os.environ.pop("TEST_VAPID_PRIV", None)
    return NotificationDispatcher(bus, state, config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crisis_notifies_all_roles(populated: StateManager, bus: EventBus):
    """CRISIS_DETECTED → all 3 roles (pc, family, clinician) receive push."""
    dispatcher = _make_dispatcher(bus, populated, vapid_key="fake-vapid-key")

    sent_to: list[str] = []

    def _mock_webpush(subscription_info, **kwargs):
        sent_to.append(subscription_info["endpoint"])

    with patch("ada.notifications.dispatcher.webpush", _mock_webpush):
        event = CrisisDetectedEvent(
            patient_id=_PATIENT_ID,
            session_id="sess-1",
            severity="HIGH",
            trigger_text="I want to hurt myself",
            detection_method="llm",
        )
        await bus.publish(event)
        # Allow async handlers to complete
        import asyncio
        await asyncio.sleep(0.05)

    assert _ENDPOINT_PC in sent_to
    assert _ENDPOINT_FAM in sent_to
    assert _ENDPOINT_CLIN in sent_to
    assert len(sent_to) == 3


@pytest.mark.asyncio
async def test_board_event_skips_clinician(populated: StateManager, bus: EventBus):
    """BOARD_ITEM_SUGGESTED → primary_caregiver + family only; clinician skipped."""
    dispatcher = _make_dispatcher(bus, populated, vapid_key="fake-vapid-key")

    sent_to: list[str] = []

    def _mock_webpush(subscription_info, **kwargs):
        sent_to.append(subscription_info["endpoint"])

    with patch("ada.notifications.dispatcher.webpush", _mock_webpush):
        event = BoardItemSuggestedEvent(
            patient_id=_PATIENT_ID,
            board_id="board-1",
            item_id="item-1",
            text="Buy groceries",
        )
        await bus.publish(event)
        import asyncio
        await asyncio.sleep(0.05)

    assert _ENDPOINT_PC in sent_to
    assert _ENDPOINT_FAM in sent_to
    assert _ENDPOINT_CLIN not in sent_to
    assert len(sent_to) == 2


@pytest.mark.asyncio
async def test_circle_member_added_primary_only(populated: StateManager, bus: EventBus):
    """CIRCLE_MEMBER_ADDED → only primary_caregiver receives push."""
    dispatcher = _make_dispatcher(bus, populated, vapid_key="fake-vapid-key")

    sent_to: list[str] = []

    def _mock_webpush(subscription_info, **kwargs):
        sent_to.append(subscription_info["endpoint"])

    with patch("ada.notifications.dispatcher.webpush", _mock_webpush):
        event = CircleMemberAddedEvent(
            circle_id=_CIRCLE_ID,
            patient_id=_PATIENT_ID,
            user_id="new-user",
            role="family",
        )
        await bus.publish(event)
        import asyncio
        await asyncio.sleep(0.05)

    assert _ENDPOINT_PC in sent_to
    assert _ENDPOINT_FAM not in sent_to
    assert _ENDPOINT_CLIN not in sent_to
    assert len(sent_to) == 1


@pytest.mark.asyncio
async def test_no_vapid_key_skips_push(populated: StateManager, bus: EventBus):
    """Empty VAPID key → push HTTP call skipped, no error, log still written."""
    # No vapid key set
    dispatcher = _make_dispatcher(bus, populated, vapid_key="")

    push_called = False

    def _mock_webpush(*args, **kwargs):
        nonlocal push_called
        push_called = True

    with patch("ada.notifications.dispatcher.webpush", _mock_webpush):
        event = CrisisDetectedEvent(
            patient_id=_PATIENT_ID,
            session_id="sess-1",
            severity="LOW",
            trigger_text="feeling sad",
            detection_method="keyword",
        )
        await bus.publish(event)
        import asyncio
        await asyncio.sleep(0.05)

    # Push HTTP call must NOT have been made
    assert not push_called

    # But notification log entries should still be written (audit trail)
    log_rows = await populated._fetchall(
        "SELECT * FROM notification_log WHERE user_id IN (?, ?, ?)",
        (_PC_ID, _FAM_ID, _CLIN_ID),
    )
    assert len(log_rows) > 0
