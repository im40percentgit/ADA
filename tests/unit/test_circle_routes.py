"""
Unit tests for care circle REST endpoints.

Tests use a real in-memory StateManager and FastAPI TestClient with
dependency_overrides to inject authenticated users without real JWTs —
the same pattern as tests/integration/test_caregiver_flow.py.

Coverage:
  GET  /api/circles/my               — member sees their circle; outsider sees []
  GET  /api/circles/{id}/members     — member gets list; non-member gets 404
  POST /api/circles/{id}/members     — primary_caregiver adds family (201);
                                       family member denied (403)
  DELETE /api/circles/{id}/members   — primary_caregiver removes (204);
                                       family member denied (403)

@decision DEC-CIRCLE-004
@title Route tests use real StateManager instead of mocks
@status accepted
@rationale Mocking StateManager would hide SQL constraint errors (e.g. the
    UNIQUE constraint on duplicate members) that the routes rely on for 409
    responses. A real in-memory SQLite DB exercises the full stack from HTTP
    request through SQL queries to JSON response, matching Sacred Practice #5.
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
# Minimal LLM stub (same as caregiver integration test)
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

_CIRCLE_ID = "circle-route-test-001"
_PATIENT_ID = "patient-route-test-001"

_PC_USER_ID = "user-pc-route-001"
_PC_EMAIL = "pc-route@example.com"

_FAM_USER_ID = "user-fam-route-001"
_FAM_EMAIL = "fam-route@example.com"

_OUTSIDER_ID = "user-out-route-001"
_OUTSIDER_EMAIL = "outsider-route@example.com"

# A fourth user that can be added as a new member in add_member tests
_NEW_USER_ID = "user-new-route-001"
_NEW_USER_EMAIL = "newmember-route@example.com"

_PC_MEMBER_ID = "ccm-pc-route-001"
_FAM_MEMBER_ID = "ccm-fam-route-001"

# A patient user (role="user") for lookup tests
_PATIENT_USER_ID = "user-patient-lookup-001"
_PATIENT_USER_EMAIL = "patient-lookup@example.com"


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


_PC_USER = _user(_PC_USER_ID, _PC_EMAIL)
_FAM_USER = _user(_FAM_USER_ID, _FAM_EMAIL)
_OUTSIDER_USER = _user(_OUTSIDER_ID, _OUTSIDER_EMAIL)


# ---------------------------------------------------------------------------
# Fixture: seeded StateManager
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state() -> StateManager:
    """
    In-memory StateManager with:
      - 4 users (pc, family, outsider, new_member)
      - 1 patient
      - 1 care circle
      - 2 members (pc as primary_caregiver, fam as family)
    """
    sm = StateManager(":memory:")
    await sm.initialize()

    for uid, email in [
        (_PC_USER_ID, _PC_EMAIL),
        (_FAM_USER_ID, _FAM_EMAIL),
        (_OUTSIDER_ID, _OUTSIDER_EMAIL),
        (_NEW_USER_ID, _NEW_USER_EMAIL),
    ]:
        await sm.create_user({
            "id": uid,
            "email": email,
            "hashed_password": "x",
            "role": "caregiver",
        })

    # Patient-role user for lookup endpoint tests
    await sm.create_user({
        "id": _PATIENT_USER_ID,
        "email": _PATIENT_USER_EMAIL,
        "hashed_password": "x",
        "role": "user",
    })

    await sm.create_patient({
        "id": _PATIENT_ID,
        "name": "Route Test Patient",
        "dob": "1992-06-15",
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })

    await sm.create_care_circle(_CIRCLE_ID, _PATIENT_ID)

    await sm.add_circle_member(
        member_id=_PC_MEMBER_ID,
        circle_id=_CIRCLE_ID,
        user_id=_PC_USER_ID,
        role="primary_caregiver",
        added_by=None,
    )
    await sm.add_circle_member(
        member_id=_FAM_MEMBER_ID,
        circle_id=_CIRCLE_ID,
        user_id=_FAM_USER_ID,
        role="family",
        added_by=_PC_USER_ID,
    )

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
# Tests: GET /api/circles/my
# ---------------------------------------------------------------------------

def test_list_my_circles(state):
    """Primary caregiver sees their circle in GET /api/circles/my."""
    with _client(state, _PC_USER) as client:
        resp = client.get("/api/circles/my")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == _CIRCLE_ID


def test_list_my_circles_empty(state):
    """Outsider (not a member of any circle) gets an empty list."""
    with _client(state, _OUTSIDER_USER) as client:
        resp = client.get("/api/circles/my")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Tests: GET /api/circles/{id}/members
# ---------------------------------------------------------------------------

def test_list_circle_members(state):
    """Primary caregiver can list members of their circle."""
    with _client(state, _PC_USER) as client:
        resp = client.get(f"/api/circles/{_CIRCLE_ID}/members")
    assert resp.status_code == 200
    members = resp.json()
    user_ids = {m["user_id"] for m in members}
    assert _PC_USER_ID in user_ids
    assert _FAM_USER_ID in user_ids


def test_list_members_non_member_404(state):
    """Non-member gets 404 when trying to list members."""
    with _client(state, _OUTSIDER_USER) as client:
        resp = client.get(f"/api/circles/{_CIRCLE_ID}/members")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: POST /api/circles/{id}/members
# ---------------------------------------------------------------------------

def test_add_member(state):
    """Primary caregiver can add a new family member (201)."""
    with _client(state, _PC_USER) as client:
        resp = client.post(
            f"/api/circles/{_CIRCLE_ID}/members",
            json={"email": _NEW_USER_EMAIL, "role": "family"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == _NEW_USER_EMAIL
    assert body["role"] == "family"
    assert body["user_id"] == _NEW_USER_ID


def test_add_member_family_denied(state):
    """Family member cannot add others — gets 403."""
    with _client(state, _FAM_USER) as client:
        resp = client.post(
            f"/api/circles/{_CIRCLE_ID}/members",
            json={"email": _NEW_USER_EMAIL, "role": "family"},
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests: DELETE /api/circles/{id}/members/{user_id}
# ---------------------------------------------------------------------------

def test_remove_member(state):
    """Primary caregiver can remove a family member (204)."""
    with _client(state, _PC_USER) as client:
        resp = client.delete(f"/api/circles/{_CIRCLE_ID}/members/{_FAM_USER_ID}")
    assert resp.status_code == 204


def test_remove_member_non_primary_denied(state):
    """Family member cannot remove others — gets 403."""
    with _client(state, _FAM_USER) as client:
        resp = client.delete(f"/api/circles/{_CIRCLE_ID}/members/{_PC_USER_ID}")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests: GET /api/circles/lookup
# ---------------------------------------------------------------------------

def test_lookup_user_by_email_found(state):
    """Caregiver can look up a patient user by email — returns 200 with correct fields."""
    with _client(state, _PC_USER) as client:
        resp = client.get(f"/api/circles/lookup?email={_PATIENT_USER_EMAIL}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == _PATIENT_USER_ID
    assert body["email"] == _PATIENT_USER_EMAIL
    assert body["role"] == "user"


def test_lookup_user_by_email_not_found(state):
    """Lookup for a non-existent email returns 404."""
    with _client(state, _PC_USER) as client:
        resp = client.get("/api/circles/lookup?email=nobody@example.com")
    assert resp.status_code == 404


def test_lookup_user_by_email_forbidden_for_patient(state):
    """Non-caregiver users get 403 on lookup."""
    patient_user = User(
        id=_PATIENT_USER_ID,
        email=_PATIENT_USER_EMAIL,
        role="user",
        patient_id=None,
        created_at=datetime.utcnow(),
        is_active=True,
    )
    with _client(state, patient_user) as client:
        resp = client.get("/api/circles/lookup?email=someone@example.com")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests: POST /api/circles/create-with-patient
# ---------------------------------------------------------------------------

def test_create_patient_for_circle(state):
    """Caregiver creates a brand-new patient + circle — returns 201 with IDs."""
    with _client(state, _PC_USER) as client:
        resp = client.post(
            "/api/circles/create-with-patient",
            json={"patient_name": "New Patient"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert "circle_id" in body
    assert "patient_id" in body
    assert body["patient_name"] == "New Patient"
    # Verify the circle actually exists in state
    import asyncio
    circle = asyncio.get_event_loop().run_until_complete(
        state.get_care_circle_by_patient(body["patient_id"])
    )
    assert circle is not None
    assert circle["id"] == body["circle_id"]


def test_create_patient_for_circle_links_existing(state):
    """When patient_email matches an existing patient user, links to their patient_id."""
    # _PATIENT_USER_ID has role="user" but no patient_id yet — create a patient for them
    import asyncio
    from datetime import datetime, timezone

    existing_patient_id = "patient-existing-link-001"
    asyncio.get_event_loop().run_until_complete(
        state.create_patient({
            "id": existing_patient_id,
            "name": "Existing Patient",
            "dob": None,
            "preferences": "{}",
            "emergency_contact": None,
            "caregiver_id": None,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        })
    )
    # Update the patient user to point at that patient record
    asyncio.get_event_loop().run_until_complete(
        state._exec(
            "UPDATE users SET patient_id = ? WHERE id = ?",
            (existing_patient_id, _PATIENT_USER_ID),
        )
    )

    with _client(state, _PC_USER) as client:
        resp = client.post(
            "/api/circles/create-with-patient",
            json={"patient_name": "Existing Patient", "patient_email": _PATIENT_USER_EMAIL},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["patient_id"] == existing_patient_id


def test_create_patient_for_circle_duplicate_409(state):
    """Returns 409 when the target patient already has a care circle."""
    # _PATIENT_ID already has _CIRCLE_ID in the seeded state
    # We need a user whose patient_id points at _PATIENT_ID
    import asyncio
    from datetime import datetime, timezone

    asyncio.get_event_loop().run_until_complete(
        state._exec(
            "UPDATE users SET patient_id = ? WHERE id = ?",
            (_PATIENT_ID, _PATIENT_USER_ID),
        )
    )

    with _client(state, _PC_USER) as client:
        resp = client.post(
            "/api/circles/create-with-patient",
            json={"patient_name": "Route Test Patient", "patient_email": _PATIENT_USER_EMAIL},
        )
    assert resp.status_code == 409
