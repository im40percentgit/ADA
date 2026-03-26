"""
Unit tests for board CRUD methods in StateManager (Phase 9b).

Uses a real in-memory SQLite database — no mocks of internal modules.
All 10 tests verify schema constraints and query correctness directly
against the StateManager methods added in Phase 9b.

@decision DEC-BOARD-002
@title Board state tests use real in-memory SQLite, no mocks
@status accepted
@rationale Consistent with DEC-CIRCLE-002 and Sacred Practice #5. Testing
    against :memory: is fast, exercises real SQL constraints (CHECK, REFERENCES,
    DEFAULT), and catches bool-coercion bugs (INTEGER 0/1 -> Python bool) that
    mocks would hide entirely.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from ada.core.state import StateManager


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


@pytest_asyncio.fixture
async def populated(state: StateManager):
    """StateManager pre-populated with one patient, one user, and one care circle."""
    await state.create_patient({
        "id": "patient-1",
        "name": "Alice",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    await state.create_user({
        "id": "user-1",
        "email": "caregiver@example.com",
        "hashed_password": "hashed",
        "role": "caregiver",
        "patient_id": None,
    })
    await state.create_care_circle("circle-1", "patient-1")
    return state


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_board(populated: StateManager):
    """Create a board and retrieve it via get_board."""
    await populated.create_board({
        "id": "board-1",
        "care_circle_id": "circle-1",
        "name": "Shopping List",
        "board_type": "shopping",
        "created_by": "user-1",
    })
    row = await populated.get_board("board-1")
    assert row is not None
    assert row["id"] == "board-1"
    assert row["name"] == "Shopping List"
    assert row["board_type"] == "shopping"
    assert row["care_circle_id"] == "circle-1"


@pytest.mark.asyncio
async def test_list_boards_by_circle(populated: StateManager):
    """Create two boards and verify list_boards_by_circle returns both."""
    await populated.create_board({
        "id": "board-1",
        "care_circle_id": "circle-1",
        "name": "Shopping",
        "board_type": "shopping",
        "created_by": "user-1",
    })
    await populated.create_board({
        "id": "board-2",
        "care_circle_id": "circle-1",
        "name": "Chores",
        "board_type": "chores",
        "created_by": "user-1",
    })
    boards = await populated.list_boards_by_circle("circle-1")
    assert len(boards) == 2
    names = {b["name"] for b in boards}
    assert names == {"Shopping", "Chores"}


@pytest.mark.asyncio
async def test_create_board_item(populated: StateManager):
    """Create a board item and verify it appears in get_board_items."""
    await populated.create_board({
        "id": "board-1",
        "care_circle_id": "circle-1",
        "name": "Shopping",
        "board_type": "shopping",
        "created_by": "user-1",
    })
    await populated.create_board_item({
        "id": "item-1",
        "board_id": "board-1",
        "text": "Milk",
        "created_by": "user-1",
    })
    items = await populated.get_board_items("board-1")
    assert len(items) == 1
    assert items[0]["text"] == "Milk"
    assert items[0]["checked"] is False
    assert items[0]["suggested_by_ada"] is False
    assert items[0]["approved"] is True


@pytest.mark.asyncio
async def test_create_board_item_position(populated: StateManager):
    """get_next_board_position increments correctly as items are added."""
    await populated.create_board({
        "id": "board-1",
        "care_circle_id": "circle-1",
        "name": "Shopping",
        "board_type": "shopping",
        "created_by": "user-1",
    })
    # Empty board should return 0.0
    pos0 = await populated.get_next_board_position("board-1")
    assert pos0 == 0.0

    await populated.create_board_item({
        "id": "item-1",
        "board_id": "board-1",
        "text": "Milk",
        "position": pos0,
        "created_by": "user-1",
    })
    pos1 = await populated.get_next_board_position("board-1")
    assert pos1 == 1.0

    await populated.create_board_item({
        "id": "item-2",
        "board_id": "board-1",
        "text": "Bread",
        "position": pos1,
        "created_by": "user-1",
    })
    pos2 = await populated.get_next_board_position("board-1")
    assert pos2 == 2.0


@pytest.mark.asyncio
async def test_check_board_item(populated: StateManager):
    """update_board_item with checked=1 returns bool True from get_board_item."""
    await populated.create_board({
        "id": "board-1",
        "care_circle_id": "circle-1",
        "name": "Shopping",
        "board_type": "shopping",
        "created_by": "user-1",
    })
    await populated.create_board_item({
        "id": "item-1",
        "board_id": "board-1",
        "text": "Eggs",
        "created_by": "user-1",
    })
    await populated.update_board_item("item-1", {"checked": 1})
    item = await populated.get_board_item("item-1")
    assert item is not None
    assert item["checked"] is True


@pytest.mark.asyncio
async def test_update_board_item_text(populated: StateManager):
    """update_board_item can change the text of an existing item."""
    await populated.create_board({
        "id": "board-1",
        "care_circle_id": "circle-1",
        "name": "Shopping",
        "board_type": "shopping",
        "created_by": "user-1",
    })
    await populated.create_board_item({
        "id": "item-1",
        "board_id": "board-1",
        "text": "Mlik",  # typo
        "created_by": "user-1",
    })
    await populated.update_board_item("item-1", {"text": "Milk"})
    item = await populated.get_board_item("item-1")
    assert item is not None
    assert item["text"] == "Milk"


@pytest.mark.asyncio
async def test_delete_board_item(populated: StateManager):
    """delete_board_item removes the item; get_board_items returns empty list."""
    await populated.create_board({
        "id": "board-1",
        "care_circle_id": "circle-1",
        "name": "Shopping",
        "board_type": "shopping",
        "created_by": "user-1",
    })
    await populated.create_board_item({
        "id": "item-1",
        "board_id": "board-1",
        "text": "Milk",
        "created_by": "user-1",
    })
    await populated.delete_board_item("item-1")
    items = await populated.get_board_items("board-1")
    assert items == []


@pytest.mark.asyncio
async def test_reorder_board_item(populated: StateManager):
    """update_board_item can change position; get_board_items respects ordering."""
    await populated.create_board({
        "id": "board-1",
        "care_circle_id": "circle-1",
        "name": "Shopping",
        "board_type": "shopping",
        "created_by": "user-1",
    })
    await populated.create_board_item({
        "id": "item-1",
        "board_id": "board-1",
        "text": "Milk",
        "position": 0.0,
        "created_by": "user-1",
    })
    await populated.create_board_item({
        "id": "item-2",
        "board_id": "board-1",
        "text": "Bread",
        "position": 1.0,
        "created_by": "user-1",
    })
    # Move "Bread" before "Milk" by giving it position -1.0
    await populated.update_board_item("item-2", {"position": -1.0})
    items = await populated.get_board_items("board-1")
    assert items[0]["id"] == "item-2"
    assert items[1]["id"] == "item-1"


@pytest.mark.asyncio
async def test_board_item_ada_suggestion(populated: StateManager):
    """Create an Ada-suggested item with approved=0; verify bool deserialization."""
    await populated.create_board({
        "id": "board-1",
        "care_circle_id": "circle-1",
        "name": "Shopping",
        "board_type": "shopping",
        "created_by": "user-1",
    })
    await populated.create_board_item({
        "id": "item-1",
        "board_id": "board-1",
        "text": "Low-sodium crackers",
        "created_by": "user-1",
        "suggested_by_ada": 1,
        "approved": 0,
    })
    item = await populated.get_board_item("item-1")
    assert item is not None
    assert item["suggested_by_ada"] is True
    assert item["approved"] is False


@pytest.mark.asyncio
async def test_approve_board_item(populated: StateManager):
    """Caregiver approves an Ada-suggested item; approved becomes True."""
    await populated.create_board({
        "id": "board-1",
        "care_circle_id": "circle-1",
        "name": "Shopping",
        "board_type": "shopping",
        "created_by": "user-1",
    })
    await populated.create_board_item({
        "id": "item-1",
        "board_id": "board-1",
        "text": "Omega-3 supplements",
        "created_by": "user-1",
        "suggested_by_ada": 1,
        "approved": 0,
    })
    # Caregiver approves
    await populated.update_board_item("item-1", {"approved": 1})
    item = await populated.get_board_item("item-1")
    assert item is not None
    assert item["approved"] is True
    assert item["suggested_by_ada"] is True  # unchanged
