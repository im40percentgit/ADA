"""
Unit tests for clinician notes CRUD in StateManager.

Uses a real in-memory SQLite database — no mocks of internal modules.
Tests verify schema constraints (entity_type CHECK, UNIQUE index) and
query correctness for the clinician_notes table added in Phase 12a.

@decision DEC-CLIN-NOTES-001
@title Clinician notes state tests use real in-memory SQLite
@status accepted
@rationale Consistent with DEC-TEST-001 and Sacred Practice #5. Real SQL
    constraints (CHECK on entity_type, UNIQUE on user+entity) are tested
    without any mocks. Fast, zero-dependency, exercises actual schema.
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
    """StateManager pre-populated with users for FK references."""
    await state.create_user({
        "id": "clinician-1",
        "email": "dr.smith@example.com",
        "hashed_password": "hashed",
        "role": "clinician",
        "patient_id": None,
    })
    await state.create_user({
        "id": "clinician-2",
        "email": "dr.jones@example.com",
        "hashed_password": "hashed",
        "role": "clinician",
        "patient_id": None,
    })
    await state.create_user({
        "id": "caregiver-1",
        "email": "alice@example.com",
        "hashed_password": "hashed",
        "role": "caregiver",
        "patient_id": None,
    })
    return state


# ---------------------------------------------------------------------------
# Tests — StateManager CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_note(populated: StateManager):
    """Create a clinician note and retrieve it."""
    note_id = str(uuid.uuid4())
    await populated.upsert_clinician_note({
        "id": note_id,
        "user_id": "clinician-1",
        "entity_type": "session_summary",
        "entity_id": "session-abc",
        "content": "Patient showed improvement today.",
    })

    rows = await populated.get_clinician_notes("session_summary", "session-abc")
    assert len(rows) == 1
    assert rows[0]["id"] == note_id
    assert rows[0]["user_id"] == "clinician-1"
    assert rows[0]["content"] == "Patient showed improvement today."
    assert rows[0]["entity_type"] == "session_summary"
    assert rows[0]["entity_id"] == "session-abc"
    assert rows[0]["created_at"] is not None
    assert rows[0]["updated_at"] is not None


@pytest.mark.asyncio
async def test_read_notes(populated: StateManager):
    """Read all notes for a given entity."""
    await populated.upsert_clinician_note({
        "id": str(uuid.uuid4()),
        "user_id": "clinician-1",
        "entity_type": "daily_summary",
        "entity_id": "daily-001",
        "content": "First note.",
    })
    await populated.upsert_clinician_note({
        "id": str(uuid.uuid4()),
        "user_id": "clinician-2",
        "entity_type": "daily_summary",
        "entity_id": "daily-001",
        "content": "Second note.",
    })

    rows = await populated.get_clinician_notes("daily_summary", "daily-001")
    assert len(rows) == 2
    contents = {r["content"] for r in rows}
    assert "First note." in contents
    assert "Second note." in contents


@pytest.mark.asyncio
async def test_upsert_existing(populated: StateManager):
    """Upserting same (user_id, entity_type, entity_id) updates content."""
    note_id = str(uuid.uuid4())
    await populated.upsert_clinician_note({
        "id": note_id,
        "user_id": "clinician-1",
        "entity_type": "session_summary",
        "entity_id": "session-xyz",
        "content": "Original observation.",
    })

    # Upsert with same user + entity, different id (should update, not insert)
    await populated.upsert_clinician_note({
        "id": str(uuid.uuid4()),
        "user_id": "clinician-1",
        "entity_type": "session_summary",
        "entity_id": "session-xyz",
        "content": "Updated observation.",
    })

    rows = await populated.get_clinician_notes("session_summary", "session-xyz")
    assert len(rows) == 1
    assert rows[0]["content"] == "Updated observation."


@pytest.mark.asyncio
async def test_filter_by_user_id(populated: StateManager):
    """Filter notes by user_id."""
    await populated.upsert_clinician_note({
        "id": str(uuid.uuid4()),
        "user_id": "clinician-1",
        "entity_type": "session_summary",
        "entity_id": "session-001",
        "content": "Dr. Smith's note.",
    })
    await populated.upsert_clinician_note({
        "id": str(uuid.uuid4()),
        "user_id": "clinician-2",
        "entity_type": "session_summary",
        "entity_id": "session-001",
        "content": "Dr. Jones's note.",
    })

    # Filter to clinician-1 only
    rows = await populated.get_clinician_notes(
        "session_summary", "session-001", user_id="clinician-1"
    )
    assert len(rows) == 1
    assert rows[0]["user_id"] == "clinician-1"
    assert rows[0]["content"] == "Dr. Smith's note."


@pytest.mark.asyncio
async def test_multiple_users_same_entity(populated: StateManager):
    """Multiple users can annotate the same entity independently."""
    await populated.upsert_clinician_note({
        "id": str(uuid.uuid4()),
        "user_id": "clinician-1",
        "entity_type": "daily_summary",
        "entity_id": "daily-002",
        "content": "Clinician 1 note.",
    })
    await populated.upsert_clinician_note({
        "id": str(uuid.uuid4()),
        "user_id": "clinician-2",
        "entity_type": "daily_summary",
        "entity_id": "daily-002",
        "content": "Clinician 2 note.",
    })
    await populated.upsert_clinician_note({
        "id": str(uuid.uuid4()),
        "user_id": "caregiver-1",
        "entity_type": "daily_summary",
        "entity_id": "daily-002",
        "content": "Caregiver note.",
    })

    rows = await populated.get_clinician_notes("daily_summary", "daily-002")
    assert len(rows) == 3
    user_ids = {r["user_id"] for r in rows}
    assert user_ids == {"clinician-1", "clinician-2", "caregiver-1"}


@pytest.mark.asyncio
async def test_entity_type_constraint(populated: StateManager):
    """Only 'session_summary' and 'daily_summary' are valid entity types."""
    import aiosqlite

    with pytest.raises(aiosqlite.IntegrityError):
        await populated.upsert_clinician_note({
            "id": str(uuid.uuid4()),
            "user_id": "clinician-1",
            "entity_type": "invalid_type",
            "entity_id": "entity-1",
            "content": "Should fail.",
        })
