"""
Unit tests for organization (tenant) CRUD methods in StateManager.

Uses a real in-memory SQLite database — no mocks of internal modules.
Tests verify schema constraints and query correctness for the multi-tenancy
tables added in Phase 14a: organizations, organization_members, and
organization_id scoping on patients/users.

@decision DEC-TENANT-001
@title Organization tests use real in-memory SQLite, no mocks
@status accepted
@rationale Follows the established pattern in test_circle_state.py,
    test_knowledge.py, and test_auth.py. Testing against :memory: is fast,
    exercises real SQL constraints (UNIQUE, CHECK, REFERENCES), and requires
    no network or external services.
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
    """StateManager pre-populated with one org, one user, and one patient."""
    await state.create_organization({
        "id": "org-1",
        "name": "Sunrise Care",
        "slug": "sunrise-care",
        "plan": "free",
        "settings": {"feature_flags": ["dashboard"]},
    })
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
        "email": "admin@sunrise.com",
        "hashed_password": "hashed",
        "role": "admin",
        "patient_id": None,
    })
    return state


# ---------------------------------------------------------------------------
# Organization CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_get_organization(populated: StateManager):
    """Create an org and retrieve it by ID."""
    org = await populated.get_organization("org-1")
    assert org is not None
    assert org["name"] == "Sunrise Care"
    assert org["slug"] == "sunrise-care"
    assert org["plan"] == "free"
    assert org["settings"] == {"feature_flags": ["dashboard"]}


@pytest.mark.asyncio
async def test_get_organization_not_found(state: StateManager):
    """get_organization returns None for nonexistent ID."""
    result = await state.get_organization("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_update_organization(populated: StateManager):
    """Update name, plan, and settings on an org."""
    await populated.update_organization("org-1", {
        "name": "Sunrise Senior Care",
        "plan": "pro",
        "settings": {"theme": "dark"},
    })
    org = await populated.get_organization("org-1")
    assert org["name"] == "Sunrise Senior Care"
    assert org["plan"] == "pro"
    assert org["settings"] == {"theme": "dark"}
    assert org["updated_at"] is not None


@pytest.mark.asyncio
async def test_update_organization_ignores_unknown_fields(populated: StateManager):
    """Fields not in the allowed set are silently ignored."""
    await populated.update_organization("org-1", {"id": "hacked", "bogus": 42})
    org = await populated.get_organization("org-1")
    assert org["id"] == "org-1"  # unchanged


@pytest.mark.asyncio
async def test_slug_uniqueness(populated: StateManager):
    """UNIQUE constraint on slug prevents duplicate slugs."""
    with pytest.raises(Exception):
        await populated.create_organization({
            "id": "org-2",
            "name": "Another Org",
            "slug": "sunrise-care",  # duplicate
        })


@pytest.mark.asyncio
async def test_plan_check_constraint(state: StateManager):
    """CHECK constraint rejects invalid plan values."""
    with pytest.raises(Exception):
        await state.create_organization({
            "id": "org-bad",
            "name": "Bad Plan Org",
            "slug": "bad-plan",
            "plan": "platinum",  # not in ('free', 'pro', 'enterprise')
        })


# ---------------------------------------------------------------------------
# Organization members
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_and_list_members(populated: StateManager):
    """Add a member to an org and list all members."""
    await populated.add_organization_member("org-1", "user-1", "owner")
    members = await populated.list_organization_members("org-1")
    assert len(members) == 1
    assert members[0]["user_id"] == "user-1"
    assert members[0]["role"] == "owner"
    assert members[0]["email"] == "admin@sunrise.com"


@pytest.mark.asyncio
async def test_add_member_default_role(populated: StateManager):
    """Default role is 'member' when not specified."""
    await populated.add_organization_member("org-1", "user-1")
    members = await populated.list_organization_members("org-1")
    assert members[0]["role"] == "member"


@pytest.mark.asyncio
async def test_add_duplicate_member_fails(populated: StateManager):
    """UNIQUE(organization_id, user_id) prevents duplicate memberships."""
    await populated.add_organization_member("org-1", "user-1", "member")
    with pytest.raises(Exception):
        await populated.add_organization_member("org-1", "user-1", "admin")


@pytest.mark.asyncio
async def test_update_member_role(populated: StateManager):
    """Update role of an existing member."""
    await populated.add_organization_member("org-1", "user-1", "member")
    await populated.update_member_role("org-1", "user-1", "admin")
    members = await populated.list_organization_members("org-1")
    assert members[0]["role"] == "admin"


@pytest.mark.asyncio
async def test_remove_member(populated: StateManager):
    """Remove a member from an org."""
    await populated.add_organization_member("org-1", "user-1", "member")
    await populated.remove_organization_member("org-1", "user-1")
    members = await populated.list_organization_members("org-1")
    assert len(members) == 0


# ---------------------------------------------------------------------------
# User-to-organization lookup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_organization(populated: StateManager):
    """get_user_organization returns the org a user belongs to."""
    await populated.add_organization_member("org-1", "user-1", "owner")
    org = await populated.get_user_organization("user-1")
    assert org is not None
    assert org["id"] == "org-1"
    assert org["name"] == "Sunrise Care"


@pytest.mark.asyncio
async def test_get_user_organization_none(populated: StateManager):
    """get_user_organization returns None when user has no membership."""
    org = await populated.get_user_organization("user-1")
    assert org is None


# ---------------------------------------------------------------------------
# Patient org scoping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_patients_for_organization(state: StateManager):
    """get_patients_for_organization returns only patients with matching org_id."""
    await state.create_organization({
        "id": "org-a",
        "name": "Org A",
        "slug": "org-a",
    })
    # Patient scoped to org-a (set via direct SQL since create_patient
    # does not yet accept organization_id in its INSERT — we test the
    # query, not the insert path).
    await state.create_patient({
        "id": "p1",
        "name": "Scoped Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    # Use internal helper to set organization_id on the patient
    assert state._conn is not None
    await state._conn.execute(
        "UPDATE patients SET organization_id = ? WHERE id = ?",
        ("org-a", "p1"),
    )
    await state._conn.commit()

    # Unscoped patient
    await state.create_patient({
        "id": "p2",
        "name": "Unscoped Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })

    result = await state.get_patients_for_organization("org-a")
    assert len(result) == 1
    assert result[0]["id"] == "p1"
    assert result[0]["name"] == "Scoped Patient"


@pytest.mark.asyncio
async def test_get_patients_for_organization_empty(state: StateManager):
    """get_patients_for_organization returns empty list for org with no patients."""
    await state.create_organization({
        "id": "org-empty",
        "name": "Empty Org",
        "slug": "org-empty",
    })
    result = await state.get_patients_for_organization("org-empty")
    assert result == []


@pytest.mark.asyncio
async def test_multiple_members_in_org(populated: StateManager):
    """Multiple users can be members of the same organization."""
    await populated.create_user({
        "id": "user-2",
        "email": "nurse@sunrise.com",
        "hashed_password": "hashed",
        "role": "clinician",
        "patient_id": None,
    })
    await populated.add_organization_member("org-1", "user-1", "owner")
    await populated.add_organization_member("org-1", "user-2", "member")
    members = await populated.list_organization_members("org-1")
    assert len(members) == 2
    roles = {m["user_id"]: m["role"] for m in members}
    assert roles["user-1"] == "owner"
    assert roles["user-2"] == "member"
