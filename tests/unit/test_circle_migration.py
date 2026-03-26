"""
Unit tests for the caregiver-to-care-circle migration in StateManager.

The migration runs automatically during initialize() via
_migrate_caregiver_to_circles(). Tests use a real in-memory SQLite database
seeded with legacy patient rows (those having a caregiver_id) to verify that
the migration correctly bootstraps care_circles and care_circle_members without
mocking any internals.

@decision DEC-CIRCLE-003
@title Caregiver-to-circle migration runs at every initialize() call
@status accepted
@rationale See state.py module docstring for full rationale.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from ada.core.state import StateManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def migrated_state() -> StateManager:
    """StateManager initialized with legacy patient data already seeded.

    Setup order:
      1. initialize() — creates schema, runs migration (finds nothing yet).
      2. Seed a caregiver user and two patients (one WITH caregiver_id,
         one WITHOUT).
      3. Call _migrate_caregiver_to_circles() manually to simulate a second
         startup after the legacy data was inserted.

    This mirrors the real-world scenario: an existing deployment has patients
    with caregiver_id set, then upgrades to Phase 9a and restarts the server.
    """
    sm = StateManager(":memory:")
    await sm.initialize()  # schema created, migration runs on empty DB

    # Seed caregiver user (must exist for FK on care_circle_members.user_id)
    await sm.create_user({
        "id": "user-caregiver-1",
        "email": "legacy_carer@example.com",
        "hashed_password": "hashed",
        "role": "caregiver",
        "patient_id": None,
    })

    # Patient WITH legacy caregiver_id
    await sm.create_patient({
        "id": "patient-legacy",
        "name": "Legacy Pat",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": "user-caregiver-1",
    })

    # Patient WITHOUT caregiver_id
    await sm.create_patient({
        "id": "patient-no-carer",
        "name": "Solo Pat",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })

    # Re-run migration to process the newly seeded legacy patient
    await sm._migrate_caregiver_to_circles()

    yield sm
    await sm.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migration_creates_circle(migrated_state: StateManager):
    """Patient with caregiver_id gets a care_circle after migration."""
    circle = await migrated_state.get_care_circle_by_patient("patient-legacy")
    assert circle is not None
    assert circle["id"] == "circle-patient-legacy"
    assert circle["patient_id"] == "patient-legacy"


@pytest.mark.asyncio
async def test_migration_adds_caregiver_as_primary(migrated_state: StateManager):
    """The linked caregiver user is added as primary_caregiver in the circle."""
    circle = await migrated_state.get_care_circle_by_patient("patient-legacy")
    assert circle is not None
    members = await migrated_state.get_circle_members(circle["id"])
    assert len(members) == 1
    assert members[0]["user_id"] == "user-caregiver-1"
    assert members[0]["role"] == "primary_caregiver"


@pytest.mark.asyncio
async def test_migration_skips_patients_without_caregiver(migrated_state: StateManager):
    """Patient without caregiver_id receives no care_circle from migration."""
    circle = await migrated_state.get_care_circle_by_patient("patient-no-carer")
    assert circle is None


@pytest.mark.asyncio
async def test_migration_is_idempotent(migrated_state: StateManager):
    """Running _migrate_caregiver_to_circles() twice creates no duplicate rows."""
    # Run migration a second time
    await migrated_state._migrate_caregiver_to_circles()

    # Still exactly one circle for the legacy patient
    circle = await migrated_state.get_care_circle_by_patient("patient-legacy")
    assert circle is not None

    # Still exactly one member in that circle
    members = await migrated_state.get_circle_members(circle["id"])
    assert len(members) == 1
    assert members[0]["user_id"] == "user-caregiver-1"
