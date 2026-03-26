"""Integration tests: shared board REST lifecycle (Phase 9b).

Exercises the full board flow using a real in-memory SQLite StateManager and
FastAPI TestClient. No mocks except the LLM provider (external boundary).

Test coverage:
- Full CRUD lifecycle: create board, add item, check item, delete item
- Ada suggestion approval: seed suggested item, verify approval endpoint

@decision DEC-BOARD-004
@title Board integration test uses real HTTP round-trips against in-memory state
@status accepted
@rationale Mirrors the pattern established in test_circle_flow.py. A real
    StateManager (SQLite :memory:) and TestClient validate the entire vertical
    slice -- route, auth dependency override, state persistence -- without
    mocking internal modules. Only the LLM provider is stubbed because it is
    an external boundary.
"""

from __future__ import annotations

import uuid
from datetime import datetime

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


@pytest_asyncio.fixture
async def state():
    """In-memory StateManager seeded with a user, patient, circle, and membership."""
    sm = StateManager(":memory:")
    await sm.initialize()

    # Insert user into users table
    await sm._exec(
        "INSERT INTO users (id, email, hashed_password, role, created_at, is_active)"
        " VALUES (?, ?, ?, ?, datetime('now'), 1)",
        ("user-cg", "caregiver@test.com", "hashed", "caregiver"),
    )

    # Create patient
    await sm.create_patient({
        "id": "pat-1",
        "name": "Alice",
        "dob": "1990-01-01",
        "emergency_contact": None,
        "caregiver_id": None,
    })

    # Create care circle and add caregiver as member
    circle_id = "circle-1"
    await sm.create_care_circle(circle_id, "pat-1")
    await sm.add_circle_member(
        member_id=str(uuid.uuid4()),
        circle_id=circle_id,
        user_id="user-cg",
        role="primary_caregiver",
    )

    yield sm
    await sm.close()


# ---------------------------------------------------------------------------
# Test 1: Full board CRUD lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_board_crud_lifecycle(state: StateManager):
    """Create board -> add item -> check item -> delete item via REST."""
    cg = _user("user-cg", "caregiver@test.com")
    circle_id = "circle-1"

    with _make_client(state, cg) as client:
        # 1. Create board
        resp = client.post(
            f"/api/circles/{circle_id}/boards",
            json={"name": "Shopping List", "board_type": "shopping"},
        )
        assert resp.status_code == 201, resp.text
        board = resp.json()
        assert board["name"] == "Shopping List"
        assert board["board_type"] == "shopping"
        board_id = board["id"]

        # 2. List boards -- should have exactly 1
        resp = client.get(f"/api/circles/{circle_id}/boards")
        assert resp.status_code == 200, resp.text
        boards = resp.json()
        assert len(boards) == 1
        assert boards[0]["id"] == board_id

        # 3. Add item
        resp = client.post(
            f"/api/boards/{board_id}/items",
            json={"text": "Milk"},
        )
        assert resp.status_code == 201, resp.text
        item = resp.json()
        assert item["text"] == "Milk"
        assert item["checked"] is False
        item_id = item["id"]

        # 4. Get board -- should have 1 item
        resp = client.get(f"/api/boards/{board_id}")
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert len(payload["items"]) == 1
        assert payload["items"][0]["id"] == item_id

        # 5. Check the item
        resp = client.patch(
            f"/api/boards/{board_id}/items/{item_id}",
            json={"checked": True},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["checked"] is True

        # 6. Get board again -- item is checked
        resp = client.get(f"/api/boards/{board_id}")
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["checked"] is True

        # 7. Delete item
        resp = client.delete(f"/api/boards/{board_id}/items/{item_id}")
        assert resp.status_code == 204, resp.text

        # 8. Get board again -- 0 items
        resp = client.get(f"/api/boards/{board_id}")
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["items"]) == 0


# ---------------------------------------------------------------------------
# Test 2: Ada suggestion approval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ada_suggestion_approval(state: StateManager):
    """Seed an Ada-suggested item, verify it shows as unapproved, then approve it."""
    cg = _user("user-cg", "caregiver@test.com")
    circle_id = "circle-1"

    # Pre-seed a board directly via state manager (matches what BoardSuggestionAgent does).
    # created_by must reference an existing users row; use the caregiver seeded in the fixture.
    board_id = str(uuid.uuid4())
    await state.create_board({
        "id": board_id,
        "care_circle_id": circle_id,
        "name": "Ada Suggestions",
        "board_type": "custom",
        "created_by": "user-cg",
    })

    # Seed a suggested item: suggested_by_ada=True, approved=False.
    # created_by must also reference a real users row.
    item_id = str(uuid.uuid4())
    await state.create_board_item({
        "id": item_id,
        "board_id": board_id,
        "text": "Schedule physio appointment",
        "created_by": "user-cg",
        "suggested_by_ada": True,
        "approved": False,
        "position": 0.0,
    })

    with _make_client(state, cg) as client:
        # 1. GET board -- item should show suggested_by_ada=true, approved=false
        resp = client.get(f"/api/boards/{board_id}")
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert len(payload["items"]) == 1
        item = payload["items"][0]
        assert item["suggested_by_ada"] is True
        assert item["approved"] is False

        # 2. Approve the Ada suggestion
        resp = client.post(f"/api/boards/{board_id}/items/{item_id}/approve")
        assert resp.status_code == 200, resp.text
        approved_item = resp.json()
        assert approved_item["approved"] is True

        # 3. GET board again -- item shows approved=true
        resp = client.get(f"/api/boards/{board_id}")
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["approved"] is True
