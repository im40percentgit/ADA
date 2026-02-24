"""
Unit tests for appointment REST endpoints.

Tests use real in-memory SQLite, real FastAPI TestClient (used as context
manager to trigger lifespan), and dependency_overrides to bypass JWT auth
(auth is tested separately in test_auth.py).

Coverage:
- POST /api/patients/{patient_id}/appointments — create, 201, 404 on missing patient
- GET /api/patients/{patient_id}/appointments — list, status filter
- GET /api/patients/{patient_id}/appointments/{appointment_id} — get, 404
- PATCH /api/patients/{patient_id}/appointments/{appointment_id} — update
- DELETE /api/patients/{patient_id}/appointments/{appointment_id} — hard delete, 204
- Auth required (no override → 401/403)
- 404 for wrong patient_id on appointment access

@decision DEC-APPT-001
@title Route tests follow established dependency_overrides pattern
@status accepted
@rationale Consistent with test_medication_routes.py and test_knowledge.py.
    Auth is already tested in test_auth.py; route tests focus on CRUD logic.
    TestClient is used as a context manager to trigger the FastAPI lifespan.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
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
from ada.models.user import User


# ---------------------------------------------------------------------------
# Minimal LLM stub (required by AgentRegistry constructor)
# ---------------------------------------------------------------------------

class _NullLLM(LLMProvider):
    async def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(content="", model="null", input_tokens=0, output_tokens=0)

    async def stream(self, messages, **kwargs):
        return
        yield


_FAKE_USER = User(
    id="user-appt-001",
    email="clinician@example.com",
    role="clinician",
    patient_id=None,
    created_at=datetime.utcnow(),
    is_active=True,
)

_FUTURE_DT = (datetime.utcnow() + timedelta(days=7)).replace(microsecond=0)
_FUTURE_ISO = _FUTURE_DT.isoformat()


# ---------------------------------------------------------------------------
# Client factories
# ---------------------------------------------------------------------------

@contextmanager
def _make_client(state: StateManager) -> Generator[TestClient, None, None]:
    """Authenticated test client with real in-memory state."""
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, _NullLLM())
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


@contextmanager
def _make_unauthenticated_client(state: StateManager) -> Generator[TestClient, None, None]:
    """Client with NO auth override — verifies routes are protected."""
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, _NullLLM())
    app = create_app(config, bus, state, registry)
    # No dependency_overrides
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    await sm.create_patient({
        "id": "pat-appt-001",
        "name": "Appointment Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    yield sm
    await sm.close()


# ---------------------------------------------------------------------------
# POST /api/patients/{patient_id}/appointments
# ---------------------------------------------------------------------------

class TestCreateAppointment:

    def test_create_returns_201(self, state):
        with _make_client(state) as client:
            resp = client.post("/api/patients/pat-appt-001/appointments", json={
                "title": "Initial Assessment",
                "scheduled_at": _FUTURE_ISO,
            })
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Initial Assessment"
        assert data["patient_id"] == "pat-appt-001"
        assert "id" in data

    def test_create_default_fields(self, state):
        """Verify default values are applied correctly."""
        with _make_client(state) as client:
            resp = client.post("/api/patients/pat-appt-001/appointments", json={
                "title": "Therapy Session",
                "scheduled_at": _FUTURE_ISO,
            })
        assert resp.status_code == 201
        data = resp.json()
        assert data["duration_minutes"] == 60
        assert data["appointment_type"] == "therapy"
        assert data["status"] == "scheduled"
        assert data["description"] is None
        assert data["provider_name"] is None

    def test_create_with_all_fields(self, state):
        with _make_client(state) as client:
            resp = client.post("/api/patients/pat-appt-001/appointments", json={
                "title": "Follow-up",
                "scheduled_at": _FUTURE_ISO,
                "description": "Six-week check-in",
                "duration_minutes": 30,
                "appointment_type": "check-in",
                "status": "confirmed",
                "provider_name": "Dr. Smith",
                "notes": "Patient requested morning slot",
            })
        assert resp.status_code == 201
        data = resp.json()
        assert data["description"] == "Six-week check-in"
        assert data["duration_minutes"] == 30
        assert data["appointment_type"] == "check-in"
        assert data["status"] == "confirmed"
        assert data["provider_name"] == "Dr. Smith"
        assert data["notes"] == "Patient requested morning slot"

    def test_create_404_for_missing_patient(self, state):
        with _make_client(state) as client:
            resp = client.post("/api/patients/nonexistent-patient/appointments", json={
                "title": "Ghost Appointment",
                "scheduled_at": _FUTURE_ISO,
            })
        assert resp.status_code == 404

    def test_create_requires_auth(self, state):
        with _make_unauthenticated_client(state) as client:
            resp = client.post("/api/patients/pat-appt-001/appointments", json={
                "title": "Unauthorized",
                "scheduled_at": _FUTURE_ISO,
            })
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /api/patients/{patient_id}/appointments
# ---------------------------------------------------------------------------

class TestListAppointments:

    def test_empty_list(self, state):
        with _make_client(state) as client:
            resp = client.get("/api/patients/pat-appt-001/appointments")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_created_appointments(self, state):
        with _make_client(state) as client:
            client.post("/api/patients/pat-appt-001/appointments", json={
                "title": "Session A",
                "scheduled_at": _FUTURE_ISO,
            })
            client.post("/api/patients/pat-appt-001/appointments", json={
                "title": "Session B",
                "scheduled_at": _FUTURE_ISO,
            })
            resp = client.get("/api/patients/pat-appt-001/appointments")
        assert resp.status_code == 200
        titles = [a["title"] for a in resp.json()]
        assert "Session A" in titles
        assert "Session B" in titles

    def test_list_status_filter(self, state):
        """status query param should filter by appointment status."""
        with _make_client(state) as client:
            r1 = client.post("/api/patients/pat-appt-001/appointments", json={
                "title": "Scheduled Appt",
                "scheduled_at": _FUTURE_ISO,
                "status": "scheduled",
            })
            appt_id = r1.json()["id"]
            # Update one to cancelled
            client.patch(
                f"/api/patients/pat-appt-001/appointments/{appt_id}",
                json={"status": "cancelled"},
            )
            client.post("/api/patients/pat-appt-001/appointments", json={
                "title": "Still Scheduled",
                "scheduled_at": _FUTURE_ISO,
                "status": "scheduled",
            })

            # Filter to scheduled only
            resp = client.get(
                "/api/patients/pat-appt-001/appointments",
                params={"status": "scheduled"},
            )
        assert resp.status_code == 200
        titles = [a["title"] for a in resp.json()]
        assert "Still Scheduled" in titles
        assert "Scheduled Appt" not in titles

    def test_list_404_for_missing_patient(self, state):
        with _make_client(state) as client:
            resp = client.get("/api/patients/nonexistent/appointments")
        assert resp.status_code == 404

    def test_list_requires_auth(self, state):
        with _make_unauthenticated_client(state) as client:
            resp = client.get("/api/patients/pat-appt-001/appointments")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /api/patients/{patient_id}/appointments/{appointment_id}
# ---------------------------------------------------------------------------

class TestGetAppointment:

    def test_get_existing_appointment(self, state):
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-appt-001/appointments",
                json={"title": "Lithium Check", "scheduled_at": _FUTURE_ISO},
            )
            appt_id = create_resp.json()["id"]
            resp = client.get(f"/api/patients/pat-appt-001/appointments/{appt_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Lithium Check"
        assert resp.json()["id"] == appt_id

    def test_get_404_for_missing_appointment(self, state):
        with _make_client(state) as client:
            resp = client.get("/api/patients/pat-appt-001/appointments/nonexistent-id")
        assert resp.status_code == 404

    def test_get_404_for_wrong_patient(self, state):
        """Appointment belonging to a different patient returns 404."""
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-appt-001/appointments",
                json={"title": "My Appointment", "scheduled_at": _FUTURE_ISO},
            )
            appt_id = create_resp.json()["id"]
            resp = client.get(f"/api/patients/other-patient/appointments/{appt_id}")
        assert resp.status_code == 404

    def test_get_requires_auth(self, state):
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-appt-001/appointments",
                json={"title": "Secure Appointment", "scheduled_at": _FUTURE_ISO},
            )
        appt_id = create_resp.json()["id"]
        with _make_unauthenticated_client(state) as client:
            resp = client.get(f"/api/patients/pat-appt-001/appointments/{appt_id}")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# PATCH /api/patients/{patient_id}/appointments/{appointment_id}
# ---------------------------------------------------------------------------

class TestUpdateAppointment:

    def test_update_title(self, state):
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-appt-001/appointments",
                json={"title": "Old Title", "scheduled_at": _FUTURE_ISO},
            )
            appt_id = create_resp.json()["id"]
            resp = client.patch(
                f"/api/patients/pat-appt-001/appointments/{appt_id}",
                json={"title": "New Title"},
            )
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Title"

    def test_update_status_to_cancelled(self, state):
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-appt-001/appointments",
                json={"title": "To Cancel", "scheduled_at": _FUTURE_ISO},
            )
            appt_id = create_resp.json()["id"]
            resp = client.patch(
                f"/api/patients/pat-appt-001/appointments/{appt_id}",
                json={"status": "cancelled"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"
        # Unchanged fields preserved
        assert resp.json()["title"] == "To Cancel"

    def test_update_duration(self, state):
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-appt-001/appointments",
                json={"title": "Long Session", "scheduled_at": _FUTURE_ISO},
            )
            appt_id = create_resp.json()["id"]
            resp = client.patch(
                f"/api/patients/pat-appt-001/appointments/{appt_id}",
                json={"duration_minutes": 90},
            )
        assert resp.status_code == 200
        assert resp.json()["duration_minutes"] == 90

    def test_update_404_for_missing_appointment(self, state):
        with _make_client(state) as client:
            resp = client.patch(
                "/api/patients/pat-appt-001/appointments/bad-id",
                json={"title": "Phantom"},
            )
        assert resp.status_code == 404

    def test_update_404_for_wrong_patient(self, state):
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-appt-001/appointments",
                json={"title": "Correct Patient", "scheduled_at": _FUTURE_ISO},
            )
            appt_id = create_resp.json()["id"]
            resp = client.patch(
                f"/api/patients/wrong-patient/appointments/{appt_id}",
                json={"title": "Hijack"},
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/patients/{patient_id}/appointments/{appointment_id}
# ---------------------------------------------------------------------------

class TestDeleteAppointment:

    def test_delete_returns_204(self, state):
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-appt-001/appointments",
                json={"title": "To Delete", "scheduled_at": _FUTURE_ISO},
            )
            appt_id = create_resp.json()["id"]
            resp = client.delete(f"/api/patients/pat-appt-001/appointments/{appt_id}")
        assert resp.status_code == 204

    def test_deleted_appointment_is_gone(self, state):
        """Hard-delete: appointment is no longer retrievable."""
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-appt-001/appointments",
                json={"title": "Erasable", "scheduled_at": _FUTURE_ISO},
            )
            appt_id = create_resp.json()["id"]
            client.delete(f"/api/patients/pat-appt-001/appointments/{appt_id}")
            get_resp = client.get(f"/api/patients/pat-appt-001/appointments/{appt_id}")
        assert get_resp.status_code == 404

    def test_deleted_appointment_absent_from_list(self, state):
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-appt-001/appointments",
                json={"title": "Will Be Deleted", "scheduled_at": _FUTURE_ISO},
            )
            appt_id = create_resp.json()["id"]
            client.delete(f"/api/patients/pat-appt-001/appointments/{appt_id}")
            list_resp = client.get("/api/patients/pat-appt-001/appointments")
        assert list_resp.status_code == 200
        ids = [a["id"] for a in list_resp.json()]
        assert appt_id not in ids

    def test_delete_404_for_missing_appointment(self, state):
        with _make_client(state) as client:
            resp = client.delete("/api/patients/pat-appt-001/appointments/ghost-id")
        assert resp.status_code == 404

    def test_delete_404_for_wrong_patient(self, state):
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-appt-001/appointments",
                json={"title": "Someone Else's", "scheduled_at": _FUTURE_ISO},
            )
            appt_id = create_resp.json()["id"]
            resp = client.delete(f"/api/patients/wrong-patient/appointments/{appt_id}")
        assert resp.status_code == 404

    def test_delete_requires_auth(self, state):
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-appt-001/appointments",
                json={"title": "Auth Test", "scheduled_at": _FUTURE_ISO},
            )
        appt_id = create_resp.json()["id"]
        with _make_unauthenticated_client(state) as client:
            resp = client.delete(f"/api/patients/pat-appt-001/appointments/{appt_id}")
        assert resp.status_code in (401, 403)
