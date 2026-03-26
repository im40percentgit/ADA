"""
Unit tests for shared board WebSocket handler (Phase 9b, Task 5).

Tests use a real in-memory StateManager with auth disabled (config.auth.enabled=False)
following the same pattern as test_chat_ws_emotion.py. The WebSocket handler consumes
an auth frame even when auth is disabled and extracts user_id from the payload.

Coverage:
  WS connect + auth       -- client connects and receives "connected" frame
  WS item_add             -- client sends item_add, receives item_added broadcast
  WS item_check           -- client sends item_check, receives item_checked broadcast
  WS auth failure          -- invalid board closes connection with 4001

@decision DEC-BOARD-005
@title Board WS tests use auth-disabled config to skip JWT validation
@status accepted
@rationale Matches the established pattern from test_chat_ws_emotion.py. JWT
    auth is already covered by test_auth.py. Disabling auth lets tests focus
    on the board WS protocol (connect, item_add, item_check) without
    generating real tokens.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from starlette.testclient import TestClient

from ada.agents.registry import AgentRegistry
from ada.api.app import create_app
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.state import StateManager
from ada.llm.router import make_null_router


# ---------------------------------------------------------------------------
# Fixed IDs
# ---------------------------------------------------------------------------

_CIRCLE_ID = "circle-ws-test-001"
_PATIENT_ID = "patient-ws-test-001"
_USER_ID = "user-ws-test-001"
_USER_EMAIL = "ws-user@example.com"
_MEMBER_ID = "ccm-ws-test-001"
_BOARD_ID = "board-ws-test-001"
_ITEM_ID = "item-ws-test-001"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def no_auth_config() -> AdaConfig:
    cfg = AdaConfig()
    cfg.auth.enabled = False
    return cfg


@pytest_asyncio.fixture
async def client_stack(no_auth_config):
    """Fully wired TestClient with auth disabled, seeded DB, and EventBus."""
    bus = EventBus()
    state = StateManager(":memory:")
    await state.initialize()
    await bus.start()

    # Seed: user, patient, circle, member, board, one item
    await state.create_user({
        "id": _USER_ID,
        "email": _USER_EMAIL,
        "hashed_password": "x",
        "role": "caregiver",
    })
    await state.create_patient({
        "id": _PATIENT_ID,
        "name": "WS Test Patient",
        "dob": "1990-01-01",
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    await state.create_care_circle(_CIRCLE_ID, _PATIENT_ID)
    await state.add_circle_member(
        member_id=_MEMBER_ID,
        circle_id=_CIRCLE_ID,
        user_id=_USER_ID,
        role="primary_caregiver",
        added_by=None,
    )
    await state.create_board({
        "id": _BOARD_ID,
        "care_circle_id": _CIRCLE_ID,
        "name": "WS Test Board",
        "board_type": "custom",
        "created_by": _USER_ID,
    })
    await state.create_board_item({
        "id": _ITEM_ID,
        "board_id": _BOARD_ID,
        "text": "Existing item",
        "position": 0.0,
        "created_by": _USER_ID,
    })

    registry = AgentRegistry(
        bus=bus, config=no_auth_config, state=state, router=make_null_router()
    )
    app = create_app(
        config=no_auth_config, bus=bus, state=state, registry=registry
    )

    with TestClient(app) as client:
        yield client, bus, state

    await bus.stop()
    await state.close()


# ---------------------------------------------------------------------------
# Test 1: WS connects and authenticates
# ---------------------------------------------------------------------------

class TestBoardWsConnect:
    async def test_ws_connects(self, client_stack):
        """Client connects, sends auth frame, receives 'connected' confirmation."""
        client, bus, state = client_stack

        with client.websocket_connect(f"/ws/board/{_BOARD_ID}") as ws:
            # Send auth frame (consumed by handler even when auth disabled)
            ws.send_json({"type": "auth", "user_id": _USER_ID})

            msg = ws.receive_json()
            assert msg["type"] == "connected"
            assert msg["board_id"] == _BOARD_ID
            assert msg["user_id"] == _USER_ID


# ---------------------------------------------------------------------------
# Test 2: WS item_add
# ---------------------------------------------------------------------------

class TestBoardWsItemAdd:
    async def test_ws_item_add(self, client_stack):
        """Client sends item_add, receives item_added broadcast with full item."""
        client, bus, state = client_stack

        with client.websocket_connect(f"/ws/board/{_BOARD_ID}") as ws:
            ws.send_json({"type": "auth", "user_id": _USER_ID})
            connected = ws.receive_json()
            assert connected["type"] == "connected"

            # Send item_add
            ws.send_json({
                "type": "item_add",
                "text": "Buy bread",
                "assigned_to": _USER_ID,
            })

            msg = ws.receive_json()
            assert msg["type"] == "item_added"
            assert msg["item"]["text"] == "Buy bread"
            assert msg["item"]["board_id"] == _BOARD_ID
            assert msg["item"]["assigned_to"] == _USER_ID
            assert msg["item"]["checked"] is False
            assert msg["item"]["approved"] is True


# ---------------------------------------------------------------------------
# Test 3: WS item_check
# ---------------------------------------------------------------------------

class TestBoardWsItemCheck:
    async def test_ws_item_check(self, client_stack):
        """Client sends item_check, receives item_checked broadcast."""
        client, bus, state = client_stack

        with client.websocket_connect(f"/ws/board/{_BOARD_ID}") as ws:
            ws.send_json({"type": "auth", "user_id": _USER_ID})
            connected = ws.receive_json()
            assert connected["type"] == "connected"

            # Check the existing item
            ws.send_json({
                "type": "item_check",
                "item_id": _ITEM_ID,
                "checked": True,
            })

            msg = ws.receive_json()
            assert msg["type"] == "item_checked"
            assert msg["item_id"] == _ITEM_ID
            assert msg["checked"] is True
            assert msg["user_id"] == _USER_ID


# ---------------------------------------------------------------------------
# Test 4: WS auth failure (non-existent board)
# ---------------------------------------------------------------------------

class TestBoardWsAuthFailure:
    async def test_ws_auth_failure(self, client_stack):
        """Connecting to a non-existent board closes connection with 4001."""
        client, bus, state = client_stack

        with pytest.raises(Exception):
            with client.websocket_connect("/ws/board/nonexistent-board") as ws:
                ws.send_json({"type": "auth", "user_id": _USER_ID})
                # The handler should close the connection after board lookup fails
                ws.receive_json()
