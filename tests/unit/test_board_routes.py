"""
Unit tests for shared board REST endpoints (Phase 9b, Task 4).

Tests use a real in-memory StateManager and FastAPI TestClient with
dependency_overrides to inject authenticated users without real JWTs --
the same pattern as test_circle_routes.py.

Coverage:
  GET    /api/circles/{id}/boards           -- member sees boards
  POST   /api/circles/{id}/boards           -- member creates board (201)
  GET    /api/boards/{id}                   -- member gets board + items
  POST   /api/boards/{id}/items             -- member adds item (201)
  PATCH  /api/boards/{id}/items/{item_id}   -- member updates item
  DELETE /api/boards/{id}/items/{item_id}   -- member deletes item (204)
  POST   /api/boards/{id}/items/{id}/approve-- member approves suggestion
  GET    /api/boards/{id}                   -- non-member gets 404

@decision DEC-BOARD-004
@title Board route tests use real StateManager instead of mocks
@status accepted
@rationale Matches Sacred Practice #5 and the pattern from test_circle_routes.
    A real in-memory SQLite DB exercises the full stack from HTTP request
    through SQL queries to JSON response, catching constraint errors and
    serialization bugs that mocks would hide.
"""

from __future__ import annotations

import uuid
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

_CIRCLE_ID = "circle-board-test-001"
_PATIENT_ID = "patient-board-test-001"

_USER_ID = "user-board-test-001"
_USER_EMAIL = "board-user@example.com"

_OUTSIDER_ID = "user-board-outsider-001"
_OUTSIDER_EMAIL = "board-outsider@example.com"

_MEMBER_ID = "ccm-board-test-001"

_BOARD_ID = "board-test-001"


# ---------------------------------------------------------------------------
# User stubs
# ---------------------------------------------------------------------------

def _user(uid: str, email: str) -> User:
    return User(
        id=uid,
        email=email,
        role="caregiver",
        patient_id=None,
        created_at=datetime.utcnow(),
        is_active=True,
    )


_MEMBER_USER = _user(_USER_ID, _USER_EMAIL)
_OUTSIDER_USER = _user(_OUTSIDER_ID, _OUTSIDER_EMAIL)


# ---------------------------------------------------------------------------
# Fixture: seeded StateManager with circle + board + one item
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state() -> StateManager:
    """
    In-memory StateManager with:
      - 2 users (member, outsider)
      - 1 patient
      - 1 care circle with 1 member (primary_caregiver)
      - 1 board in the circle
      - 1 item on the board (with an Ada-suggested unapproved item)
    """
    sm = StateManager(":memory:")
    await sm.initialize()

    for uid, email in [
        (_USER_ID, _USER_EMAIL),
        (_OUTSIDER_ID, _OUTSIDER_EMAIL),
    ]:
        await sm.create_user({
            "id": uid,
            "email": email,
            "hashed_password": "x",
            "role": "caregiver",
        })

    await sm.create_patient({
        "id": _PATIENT_ID,
        "name": "Board Test Patient",
        "dob": "1990-01-01",
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })

    await sm.create_care_circle(_CIRCLE_ID, _PATIENT_ID)

    await sm.add_circle_member(
        member_id=_MEMBER_ID,
        circle_id=_CIRCLE_ID,
        user_id=_USER_ID,
        role="primary_caregiver",
        added_by=None,
    )

    await sm.create_board({
        "id": _BOARD_ID,
        "care_circle_id": _CIRCLE_ID,
        "name": "Grocery List",
        "board_type": "shopping",
        "created_by": _USER_ID,
    })

    # A normal item
    await sm.create_board_item({
        "id": "item-normal-001",
        "board_id": _BOARD_ID,
        "text": "Buy milk",
        "position": 0.0,
        "created_by": _USER_ID,
    })

    # An Ada-suggested unapproved item (created_by must be a real user due to FK;
    # the suggested_by_ada flag is what marks it as an Ada suggestion)
    await sm.create_board_item({
        "id": "item-suggestion-001",
        "board_id": _BOARD_ID,
        "text": "Ada suggests: Buy vitamins",
        "position": 1.0,
        "created_by": _USER_ID,
        "suggested_by_ada": 1,
        "approved": 0,
    })

    yield sm
    await sm.close()


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

@contextmanager
def _client(state: StateManager, user: User) -> Generator[TestClient, None, None]:
    """Authenticated TestClient wired to the given StateManager and user."""
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


# ---------------------------------------------------------------------------
# Test 1: GET /api/circles/{circle_id}/boards
# ---------------------------------------------------------------------------

def test_list_boards(state):
    """Member sees boards in their circle."""
    with _client(state, _MEMBER_USER) as client:
        resp = client.get(f"/api/circles/{_CIRCLE_ID}/boards")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == _BOARD_ID
    assert data[0]["name"] == "Grocery List"


# ---------------------------------------------------------------------------
# Test 2: POST /api/circles/{circle_id}/boards
# ---------------------------------------------------------------------------

def test_create_board(state):
    """Member creates a new board (201)."""
    with _client(state, _MEMBER_USER) as client:
        resp = client.post(
            f"/api/circles/{_CIRCLE_ID}/boards",
            json={"name": "Chores", "board_type": "chores"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Chores"
    assert body["board_type"] == "chores"
    assert body["care_circle_id"] == _CIRCLE_ID
    assert body["created_by"] == _USER_ID
    assert "id" in body


# ---------------------------------------------------------------------------
# Test 3: GET /api/boards/{board_id}
# ---------------------------------------------------------------------------

def test_get_board_with_items(state):
    """Member gets board details with all items."""
    with _client(state, _MEMBER_USER) as client:
        resp = client.get(f"/api/boards/{_BOARD_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["board"]["id"] == _BOARD_ID
    assert body["board"]["name"] == "Grocery List"
    assert len(body["items"]) == 2
    texts = {item["text"] for item in body["items"]}
    assert "Buy milk" in texts
    assert "Ada suggests: Buy vitamins" in texts


# ---------------------------------------------------------------------------
# Test 4: POST /api/boards/{board_id}/items
# ---------------------------------------------------------------------------

def test_add_item(state):
    """Member adds an item to the board (201)."""
    with _client(state, _MEMBER_USER) as client:
        resp = client.post(
            f"/api/boards/{_BOARD_ID}/items",
            json={"text": "Buy eggs", "assigned_to": _USER_ID},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["text"] == "Buy eggs"
    assert body["assigned_to"] == _USER_ID
    assert body["board_id"] == _BOARD_ID
    assert body["created_by"] == _USER_ID
    assert body["checked"] is False
    assert body["approved"] is True


# ---------------------------------------------------------------------------
# Test 5: PATCH /api/boards/{board_id}/items/{item_id}
# ---------------------------------------------------------------------------

def test_update_item(state):
    """Member updates item fields (text, checked)."""
    with _client(state, _MEMBER_USER) as client:
        resp = client.patch(
            f"/api/boards/{_BOARD_ID}/items/item-normal-001",
            json={"text": "Buy whole milk", "checked": True},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "Buy whole milk"
    assert body["checked"] is True


# ---------------------------------------------------------------------------
# Test 6: DELETE /api/boards/{board_id}/items/{item_id}
# ---------------------------------------------------------------------------

def test_delete_item(state):
    """Member deletes an item (204)."""
    with _client(state, _MEMBER_USER) as client:
        resp = client.delete(f"/api/boards/{_BOARD_ID}/items/item-normal-001")
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Test 7: POST /api/boards/{board_id}/items/{item_id}/approve
# ---------------------------------------------------------------------------

def test_approve_suggestion(state):
    """Member approves an Ada-suggested item -- approved flips to True."""
    with _client(state, _MEMBER_USER) as client:
        # Verify it starts unapproved
        resp = client.get(f"/api/boards/{_BOARD_ID}")
        items = resp.json()["items"]
        suggestion = next(i for i in items if i["id"] == "item-suggestion-001")
        assert suggestion["approved"] is False

        # Approve it
        resp = client.post(
            f"/api/boards/{_BOARD_ID}/items/item-suggestion-001/approve"
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["approved"] is True
    assert body["id"] == "item-suggestion-001"


# ---------------------------------------------------------------------------
# Test 8: Non-member denied
# ---------------------------------------------------------------------------

def test_non_member_denied(state):
    """Outsider gets 404 when accessing a board (avoids leaking existence)."""
    with _client(state, _OUTSIDER_USER) as client:
        resp = client.get(f"/api/boards/{_BOARD_ID}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 9: DELETE /api/boards/{board_id}/items  (clear all)
# ---------------------------------------------------------------------------

def test_clear_board_items(state):
    """Member clears all items from a board (204); items are gone afterward."""
    with _client(state, _MEMBER_USER) as client:
        # Confirm items exist before clear
        pre = client.get(f"/api/boards/{_BOARD_ID}")
        assert pre.status_code == 200
        assert len(pre.json()["items"]) == 2

        resp = client.delete(f"/api/boards/{_BOARD_ID}/items")
        assert resp.status_code == 204

        # Items should be gone
        post = client.get(f"/api/boards/{_BOARD_ID}")
        assert post.status_code == 200
        assert post.json()["items"] == []


def test_clear_board_items_outsider_denied(state):
    """Outsider cannot clear items (404)."""
    with _client(state, _OUTSIDER_USER) as client:
        resp = client.delete(f"/api/boards/{_BOARD_ID}/items")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 10: DELETE /api/boards/{board_id}  (delete board)
# ---------------------------------------------------------------------------

def test_delete_board(state):
    """Member deletes a board (204); board and items are gone afterward."""
    with _client(state, _MEMBER_USER) as client:
        resp = client.delete(f"/api/boards/{_BOARD_ID}")
        assert resp.status_code == 204

        # Board should return 404
        gone = client.get(f"/api/boards/{_BOARD_ID}")
        assert gone.status_code == 404

        # Board list should be empty
        boards = client.get(f"/api/circles/{_CIRCLE_ID}/boards")
        assert boards.status_code == 200
        assert boards.json() == []


def test_delete_board_outsider_denied(state):
    """Outsider cannot delete a board (404)."""
    with _client(state, _OUTSIDER_USER) as client:
        resp = client.delete(f"/api/boards/{_BOARD_ID}")
    assert resp.status_code == 404
