"""
Unit tests for care circle CRUD methods in StateManager.

Uses a real in-memory SQLite database — no mocks of internal modules.
All 9 tests verify schema constraints and query correctness directly
against the StateManager methods added in Phase 9a.

@decision DEC-CIRCLE-002
@title Care circle tests use real in-memory SQLite, no mocks
@status accepted
@rationale StateManager is a thin async wrapper around aiosqlite. Testing
    against :memory: is fast, exercises real SQL constraints (UNIQUE,
    REFERENCES, CHECK), and requires no network. This follows the established
    pattern in test_knowledge.py, test_assessments.py, and test_auth.py.
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
    """StateManager pre-populated with one patient and one user."""
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
    return state


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_care_circle(populated: StateManager):
    """Create a circle and retrieve it via get_care_circle_by_patient."""
    await populated.create_care_circle("circle-1", "patient-1")
    row = await populated.get_care_circle_by_patient("patient-1")
    assert row is not None
    assert row["id"] == "circle-1"
    assert row["patient_id"] == "patient-1"


@pytest.mark.asyncio
async def test_create_care_circle_duplicate_patient_fails(populated: StateManager):
    """UNIQUE(patient_id) — second circle for same patient raises."""
    await populated.create_care_circle("circle-1", "patient-1")
    with pytest.raises(Exception):
        await populated.create_care_circle("circle-2", "patient-1")


@pytest.mark.asyncio
async def test_add_circle_member(populated: StateManager):
    """Add a member and verify via get_circle_members."""
    await populated.create_care_circle("circle-1", "patient-1")
    await populated.add_circle_member(
        member_id="member-1",
        circle_id="circle-1",
        user_id="user-1",
        role="primary_caregiver",
    )
    members = await populated.get_circle_members("circle-1")
    assert len(members) == 1
    assert members[0]["user_id"] == "user-1"
    assert members[0]["role"] == "primary_caregiver"
    assert members[0]["email"] == "caregiver@example.com"


@pytest.mark.asyncio
async def test_add_duplicate_member_fails(populated: StateManager):
    """UNIQUE(circle_id, user_id) — adding same user twice raises."""
    await populated.create_care_circle("circle-1", "patient-1")
    await populated.add_circle_member(
        member_id="member-1",
        circle_id="circle-1",
        user_id="user-1",
        role="family",
    )
    with pytest.raises(Exception):
        await populated.add_circle_member(
            member_id="member-2",
            circle_id="circle-1",
            user_id="user-1",
            role="clinician",
        )


@pytest.mark.asyncio
async def test_remove_circle_member(populated: StateManager):
    """Add then remove a member — circle should be empty afterwards."""
    await populated.create_care_circle("circle-1", "patient-1")
    await populated.add_circle_member(
        member_id="member-1",
        circle_id="circle-1",
        user_id="user-1",
        role="family",
    )
    await populated.remove_circle_member("circle-1", "user-1")
    members = await populated.get_circle_members("circle-1")
    assert members == []


@pytest.mark.asyncio
async def test_get_circles_by_user(state: StateManager):
    """User in 2 circles — get_circles_by_user returns both with patient_name."""
    # Two patients
    await state.create_patient({"id": "p-a", "name": "Alice", "dob": None, "preferences": {}, "emergency_contact": None, "caregiver_id": None})
    await state.create_patient({"id": "p-b", "name": "Bob", "dob": None, "preferences": {}, "emergency_contact": None, "caregiver_id": None})
    # One shared caregiver user
    await state.create_user({"id": "u-1", "email": "shared@example.com", "hashed_password": "h", "role": "caregiver", "patient_id": None})
    # Two circles
    await state.create_care_circle("c-a", "p-a")
    await state.create_care_circle("c-b", "p-b")
    # User is member of both
    await state.add_circle_member("m-1", "c-a", "u-1", "primary_caregiver")
    await state.add_circle_member("m-2", "c-b", "u-1", "family")

    circles = await state.get_circles_by_user("u-1")
    assert len(circles) == 2
    names = {c["patient_name"] for c in circles}
    assert names == {"Alice", "Bob"}
    roles = {c["my_role"] for c in circles}
    assert roles == {"primary_caregiver", "family"}


@pytest.mark.asyncio
async def test_get_member_role(populated: StateManager):
    """get_circle_member returns the correct role for the member."""
    await populated.create_care_circle("circle-1", "patient-1")
    await populated.add_circle_member(
        member_id="member-1",
        circle_id="circle-1",
        user_id="user-1",
        role="clinician",
    )
    row = await populated.get_circle_member("circle-1", "user-1")
    assert row is not None
    assert row["role"] == "clinician"


@pytest.mark.asyncio
async def test_get_circle_member_not_found(populated: StateManager):
    """get_circle_member returns None when user is not in the circle."""
    await populated.create_care_circle("circle-1", "patient-1")
    row = await populated.get_circle_member("circle-1", "user-nonexistent")
    assert row is None


@pytest.mark.asyncio
async def test_get_patients_by_circle_member(state: StateManager):
    """User in 2 circles — get_patients_by_circle_member returns both patients."""
    await state.create_patient({"id": "p-a", "name": "Alice", "dob": None, "preferences": {}, "emergency_contact": None, "caregiver_id": None})
    await state.create_patient({"id": "p-b", "name": "Bob", "dob": None, "preferences": {}, "emergency_contact": None, "caregiver_id": None})
    await state.create_user({"id": "u-1", "email": "carer@example.com", "hashed_password": "h", "role": "caregiver", "patient_id": None})
    await state.create_care_circle("c-a", "p-a")
    await state.create_care_circle("c-b", "p-b")
    await state.add_circle_member("m-1", "c-a", "u-1", "primary_caregiver")
    await state.add_circle_member("m-2", "c-b", "u-1", "primary_caregiver")

    patients = await state.get_patients_by_circle_member("u-1")
    assert len(patients) == 2
    names = {p["name"] for p in patients}
    assert names == {"Alice", "Bob"}
