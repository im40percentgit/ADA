"""
Unit tests for prescribing notes — StateManager CRUD and REST endpoints.

Uses a real in-memory SQLite database. HTTP tests use FastAPI TestClient with
dependency_overrides for auth isolation (following test_medication_routes.py).

Coverage:
- StateManager: create_prescribing_note, get_prescribing_notes (ordering)
- POST /api/patients/{id}/prescribing-notes — create, 404, note_type validation
- GET  /api/patients/{id}/prescribing-notes — list, 404 on missing patient
- Role guard: clinician and admin may POST; caregiver and user may not (403)

@decision DEC-PRESC-NOTES-002
@title Prescribing notes tests use real SQLite + TestClient, no mocks
@status accepted
@rationale Consistent with DEC-TEST-001 and the established pattern in
    test_medication_routes.py. Real SQL constraints (CHECK on note_type,
    REFERENCES FKs) are exercised without mocks. Fast, zero-dependency.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator

import pytest
import pytest_asyncio

from fastapi.testclient import TestClient

from ada.agents.registry import AgentRegistry
from ada.api.app import create_app
from ada.api.auth import get_current_user
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.state import StateManager
from ada.llm.router import make_null_router
from ada.llm.base import LLMProvider, LLMResponse
from ada.models.user import User


# ---------------------------------------------------------------------------
# Minimal null LLM (required to build AgentRegistry)
# ---------------------------------------------------------------------------

class _NullLLM(LLMProvider):
    async def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(content="", model="null", input_tokens=0, output_tokens=0)

    async def stream(self, messages, **kwargs):
        return
        yield


# ---------------------------------------------------------------------------
# User stubs for role testing
# ---------------------------------------------------------------------------

def _make_user(role: str, user_id: str = "user-test-001") -> User:
    return User(
        id=user_id,
        email=f"{role}@example.com",
        role=role,
        patient_id=None,
        created_at=datetime.utcnow(),
        is_active=True,
    )


_CLINICIAN = _make_user("clinician", "clinician-001")
_ADMIN = _make_user("admin", "admin-001")
_CAREGIVER = _make_user("caregiver", "caregiver-001")
_PATIENT_USER = _make_user("user", "patient-user-001")


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

@contextmanager
def _make_client(
    state: StateManager,
    acting_as: User,
) -> Generator[TestClient, None, None]:
    """Authenticated TestClient with the given user injected via dependency_overrides."""
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: acting_as
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


@contextmanager
def _make_unauthed_client(state: StateManager) -> Generator[TestClient, None, None]:
    """Client with no auth override — exercises the 401 path."""
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state() -> StateManager:
    """In-memory StateManager pre-populated with a patient and a clinician user."""
    sm = StateManager(":memory:")
    await sm.initialize()
    await sm.create_patient({
        "id": "pat-001",
        "name": "Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    # Clinician and admin must exist as users for FK on clinician_id
    await sm.create_user({
        "id": "clinician-001",
        "email": "clinician@example.com",
        "hashed_password": "hashed",
        "role": "clinician",
        "patient_id": None,
    })
    await sm.create_user({
        "id": "admin-001",
        "email": "admin@example.com",
        "hashed_password": "hashed",
        "role": "admin",
        "patient_id": None,
    })
    await sm.create_user({
        "id": "caregiver-001",
        "email": "caregiver@example.com",
        "hashed_password": "hashed",
        "role": "caregiver",
        "patient_id": None,
    })
    await sm.create_user({
        "id": "patient-user-001",
        "email": "patient@example.com",
        "hashed_password": "hashed",
        "role": "user",
        "patient_id": "pat-001",
    })
    # Add all test users to a care circle for pat-001 so require_patient_access
    # authorizes them. The patient-user also has patient_id="pat-001" on their
    # User model, so they pass via the fast-path; the circle covers the rest.
    # Role must be one of ('primary_caregiver', 'family', 'clinician') per CHECK
    # constraint — "member" is not a valid circle role. The 403 for caregiver/
    # patient-user roles comes from the app-level role guard, not circle membership,
    # so giving them "clinician" circle membership does not break those tests.
    await sm.create_care_circle("circle-pn-001", "pat-001")
    for uid in ("clinician-001", "admin-001", "caregiver-001", "patient-user-001"):
        await sm.add_circle_member(
            f"ccm-pn-{uid}", "circle-pn-001", uid, "clinician"
        )
    yield sm
    await sm.close()


# ---------------------------------------------------------------------------
# StateManager unit tests
# ---------------------------------------------------------------------------

class TestStateManagerCRUD:

    @pytest.mark.asyncio
    async def test_create_and_retrieve(self, state: StateManager):
        """create_prescribing_note stores a note retrievable via get_prescribing_notes."""
        await state.create_prescribing_note({
            "id": "note-001",
            "patient_id": "pat-001",
            "clinician_id": "clinician-001",
            "note_type": "prescribe",
            "content": "Start Sertraline 50mg daily.",
        })
        notes = await state.get_prescribing_notes("pat-001")
        assert len(notes) == 1
        n = notes[0]
        assert n["id"] == "note-001"
        assert n["patient_id"] == "pat-001"
        assert n["clinician_id"] == "clinician-001"
        assert n["note_type"] == "prescribe"
        assert n["content"] == "Start Sertraline 50mg daily."
        assert n["medication_id"] is None
        assert n["created_at"] is not None

    @pytest.mark.asyncio
    async def test_notes_ordered_newest_first(self, state: StateManager):
        """get_prescribing_notes returns notes newest-first by created_at."""
        import asyncio
        await state.create_prescribing_note({
            "id": "note-older",
            "patient_id": "pat-001",
            "clinician_id": "clinician-001",
            "note_type": "review",
            "content": "First note.",
            "created_at": "2026-01-01T10:00:00",
        })
        await state.create_prescribing_note({
            "id": "note-newer",
            "patient_id": "pat-001",
            "clinician_id": "clinician-001",
            "note_type": "adjust",
            "content": "Second note.",
            "created_at": "2026-01-02T10:00:00",
        })
        notes = await state.get_prescribing_notes("pat-001")
        assert notes[0]["id"] == "note-newer"
        assert notes[1]["id"] == "note-older"

    @pytest.mark.asyncio
    async def test_empty_list_for_unknown_patient(self, state: StateManager):
        """No notes for a patient that has none returns empty list."""
        notes = await state.get_prescribing_notes("nonexistent-patient")
        assert notes == []

    @pytest.mark.asyncio
    async def test_note_type_constraint(self, state: StateManager):
        """INSERT with invalid note_type raises a DB integrity error."""
        import aiosqlite
        with pytest.raises(aiosqlite.IntegrityError):
            await state.create_prescribing_note({
                "id": "bad-note",
                "patient_id": "pat-001",
                "clinician_id": "clinician-001",
                "note_type": "invalid_type",
                "content": "Should fail.",
            })


# ---------------------------------------------------------------------------
# POST /api/patients/{patient_id}/prescribing-notes
# ---------------------------------------------------------------------------

class TestCreatePrescribingNote:

    def test_clinician_can_create(self, state):
        with _make_client(state, _CLINICIAN) as client:
            resp = client.post("/api/patients/pat-001/prescribing-notes", json={
                "note_type": "prescribe",
                "content": "Start Sertraline 50mg.",
            })
        assert resp.status_code == 201
        data = resp.json()
        assert data["note_type"] == "prescribe"
        assert data["content"] == "Start Sertraline 50mg."
        assert data["clinician_id"] == "clinician-001"
        assert data["patient_id"] == "pat-001"
        assert "id" in data
        assert "created_at" in data

    def test_admin_can_create(self, state):
        with _make_client(state, _ADMIN) as client:
            resp = client.post("/api/patients/pat-001/prescribing-notes", json={
                "note_type": "review",
                "content": "Quarterly medication review complete.",
            })
        assert resp.status_code == 201
        assert resp.json()["clinician_id"] == "admin-001"

    def test_caregiver_is_forbidden(self, state):
        with _make_client(state, _CAREGIVER) as client:
            resp = client.post("/api/patients/pat-001/prescribing-notes", json={
                "note_type": "prescribe",
                "content": "Should be blocked.",
            })
        assert resp.status_code == 403

    def test_patient_user_is_forbidden(self, state):
        with _make_client(state, _PATIENT_USER) as client:
            resp = client.post("/api/patients/pat-001/prescribing-notes", json={
                "note_type": "prescribe",
                "content": "Should be blocked.",
            })
        assert resp.status_code == 403

    def test_unauthenticated_is_rejected(self, state):
        with _make_unauthed_client(state) as client:
            resp = client.post("/api/patients/pat-001/prescribing-notes", json={
                "note_type": "prescribe",
                "content": "No auth.",
            })
        assert resp.status_code in (401, 403)

    def test_missing_patient_returns_404(self, state):
        # require_patient_access raises 403 for any patient the caller has no circle
        # membership for — including nonexistent patients (avoids leaking existence).
        with _make_client(state, _CLINICIAN) as client:
            resp = client.post("/api/patients/nonexistent/prescribing-notes", json={
                "note_type": "prescribe",
                "content": "Ghost patient.",
            })
        assert resp.status_code in (403, 404)

    def test_invalid_note_type_returns_422(self, state):
        with _make_client(state, _CLINICIAN) as client:
            resp = client.post("/api/patients/pat-001/prescribing-notes", json={
                "note_type": "invalid",
                "content": "Bad type.",
            })
        assert resp.status_code == 422

    def test_empty_content_returns_422(self, state):
        with _make_client(state, _CLINICIAN) as client:
            resp = client.post("/api/patients/pat-001/prescribing-notes", json={
                "note_type": "review",
                "content": "   ",
            })
        assert resp.status_code == 422

    def test_optional_medication_id_omitted(self, state):
        """medication_id is optional — omitting it stores NULL."""
        with _make_client(state, _CLINICIAN) as client:
            resp = client.post("/api/patients/pat-001/prescribing-notes", json={
                "note_type": "discontinue",
                "content": "Stop aspirin due to allergy.",
            })
        assert resp.status_code == 201
        assert resp.json()["medication_id"] is None

    def test_optional_medication_id_explicit_null(self, state):
        """Passing medication_id=null is accepted and stored as NULL."""
        with _make_client(state, _CLINICIAN) as client:
            resp = client.post("/api/patients/pat-001/prescribing-notes", json={
                "note_type": "review",
                "content": "General review, no specific medication.",
                "medication_id": None,
            })
        assert resp.status_code == 201
        assert resp.json()["medication_id"] is None

    def test_all_valid_note_types(self, state):
        """All four note_type values are accepted."""
        for note_type in ("prescribe", "adjust", "discontinue", "review"):
            with _make_client(state, _CLINICIAN) as client:
                resp = client.post("/api/patients/pat-001/prescribing-notes", json={
                    "note_type": note_type,
                    "content": f"Note of type {note_type}.",
                })
            assert resp.status_code == 201, f"Expected 201 for note_type={note_type}"


# ---------------------------------------------------------------------------
# GET /api/patients/{patient_id}/prescribing-notes
# ---------------------------------------------------------------------------

class TestListPrescribingNotes:

    def test_empty_list(self, state):
        with _make_client(state, _CLINICIAN) as client:
            resp = client.get("/api/patients/pat-001/prescribing-notes")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_created_notes(self, state):
        with _make_client(state, _CLINICIAN) as client:
            client.post("/api/patients/pat-001/prescribing-notes", json={
                "note_type": "prescribe",
                "content": "Note A.",
            })
            client.post("/api/patients/pat-001/prescribing-notes", json={
                "note_type": "adjust",
                "content": "Note B.",
            })
            resp = client.get("/api/patients/pat-001/prescribing-notes")
        assert resp.status_code == 200
        notes = resp.json()
        assert len(notes) == 2
        contents = {n["content"] for n in notes}
        assert "Note A." in contents
        assert "Note B." in contents

    def test_list_newest_first(self, state):
        """Notes are returned newest first."""
        with _make_client(state, _CLINICIAN) as client:
            r1 = client.post("/api/patients/pat-001/prescribing-notes", json={
                "note_type": "prescribe",
                "content": "First created.",
            })
            r2 = client.post("/api/patients/pat-001/prescribing-notes", json={
                "note_type": "review",
                "content": "Second created.",
            })
            resp = client.get("/api/patients/pat-001/prescribing-notes")
        notes = resp.json()
        # Second created should appear first (newest first ordering)
        assert notes[0]["content"] == "Second created."
        assert notes[1]["content"] == "First created."

    def test_list_missing_patient_returns_404(self, state):
        # require_patient_access raises 403 for any patient the caller has no circle
        # membership for — including nonexistent patients (avoids leaking existence).
        with _make_client(state, _CLINICIAN) as client:
            resp = client.get("/api/patients/nonexistent/prescribing-notes")
        assert resp.status_code in (403, 404)

    def test_caregiver_can_list(self, state):
        """Any authenticated user — including caregiver — can read notes."""
        with _make_client(state, _CLINICIAN) as client:
            client.post("/api/patients/pat-001/prescribing-notes", json={
                "note_type": "review",
                "content": "Visible to caregiver.",
            })
        with _make_client(state, _CAREGIVER) as client:
            resp = client.get("/api/patients/pat-001/prescribing-notes")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_patient_user_can_list(self, state):
        """Patient (role=user) can also read prescribing notes."""
        with _make_client(state, _CLINICIAN) as client:
            client.post("/api/patients/pat-001/prescribing-notes", json={
                "note_type": "prescribe",
                "content": "Patient-visible note.",
            })
        with _make_client(state, _PATIENT_USER) as client:
            resp = client.get("/api/patients/pat-001/prescribing-notes")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_unauthenticated_is_rejected(self, state):
        with _make_unauthed_client(state) as client:
            resp = client.get("/api/patients/pat-001/prescribing-notes")
        assert resp.status_code in (401, 403)
