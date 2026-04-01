"""Integration tests: Phase 10b patient dashboard flows end-to-end.

Exercises the three new patient-facing capabilities added in Phase 10b:
  1. Patient sees their care circle and boards after caregiver creates the circle.
  2. Patient logs a medication as taken and retrieves the log.
  3. Patient requests a change to an appointment.

Uses the same pattern as test_caregiver_setup_flow.py: real in-memory SQLite
StateManager, real JWT auth (no dependency_overrides), FastAPI TestClient
entered as a context manager so the ASGI lifespan fires.

@decision DEC-PAT-DASH-001
@title Patient dashboard integration tests use real auth, same pattern as caregiver setup tests
@status accepted
@rationale These tests must exercise the full auth vertical slice — register,
    login, bearer token — to verify that patient role tokens can reach the
    new Phase 10b endpoints. No mocking ensures that auth guards, circle
    membership checks, and state persistence all work together.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from ada.agents.registry import AgentRegistry
from ada.api.app import create_app
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from ada.llm.router import make_null_router


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
# App / client factory
# ---------------------------------------------------------------------------


def _make_client(state: StateManager) -> TestClient:
    """Return a TestClient that MUST be used as a context manager to fire lifespan."""
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    # No dependency_overrides — auth runs for real
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def state():
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def register_and_login(client: TestClient, email: str, password: str, role: str = "user") -> str:
    """Register a user and return a JWT access token."""
    client.post("/api/auth/register", json={"email": email, "password": password, "role": role})
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed ({resp.status_code}): {resp.text}"
    return resp.json()["access_token"]


def setup_circle(client: TestClient) -> tuple[str, str, str, str]:
    """Register patient + caregiver, create circle, return (patient_token, cg_token, patient_id, circle_id)."""
    patient_token = register_and_login(client, "patient@test.com", "TestPass1234", "user")
    cg_token = register_and_login(client, "cg@test.com", "CgPass1234", "caregiver")
    resp = client.post(
        "/api/circles/create-with-patient",
        json={"patient_name": "Test Patient", "patient_email": "patient@test.com"},
        headers={"Authorization": f"Bearer {cg_token}"},
    )
    assert resp.status_code == 201, f"Circle creation failed ({resp.status_code}): {resp.text}"
    data = resp.json()
    return patient_token, cg_token, data["patient_id"], data["circle_id"]


# ---------------------------------------------------------------------------
# Test 1: Patient can access their care circle and boards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patient_sees_circle_after_caregiver_setup(state: StateManager):
    """Patient can access their care circle after caregiver creates one."""
    with _make_client(state) as client:
        patient_token, _cg_token, _patient_id, circle_id = setup_circle(client)
        pat_headers = {"Authorization": f"Bearer {patient_token}"}

        # Patient sees their circle via GET /api/circles/my
        resp = client.get("/api/circles/my", headers=pat_headers)
        assert resp.status_code == 200, resp.text
        circles = resp.json()
        assert len(circles) == 1, f"Expected 1 circle, got {len(circles)}: {circles}"
        # get_circles_by_user returns rows with key 'id' (the care_circles.id column)
        assert circles[0]["id"] == circle_id, (
            f"Expected circle id={circle_id} in response: {circles[0]}"
        )

        # Patient can access the circle's boards list
        resp = client.get(f"/api/circles/{circle_id}/boards", headers=pat_headers)
        assert resp.status_code == 200, f"Boards list failed ({resp.status_code}): {resp.text}"
        assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Test 2: Patient can log medication as taken
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patient_logs_medication_taken(state: StateManager):
    """Patient can log that they took a medication."""
    with _make_client(state) as client:
        patient_token, cg_token, patient_id, _circle_id = setup_circle(client)
        cg_headers = {"Authorization": f"Bearer {cg_token}"}
        pat_headers = {"Authorization": f"Bearer {patient_token}"}

        # Caregiver adds a medication
        resp = client.post(
            f"/api/patients/{patient_id}/medications",
            json={"name": "Fluoxetine", "dosage": "20mg", "frequency": "daily"},
            headers=cg_headers,
        )
        assert resp.status_code == 201, f"Medication creation failed ({resp.status_code}): {resp.text}"
        med_id = resp.json()["id"]

        # Patient logs the medication as taken
        resp = client.post(
            f"/api/patients/{patient_id}/medications/{med_id}/log",
            headers=pat_headers,
        )
        assert resp.status_code == 201, f"Medication log failed ({resp.status_code}): {resp.text}"
        log = resp.json()
        assert log["medication_id"] == med_id
        assert log["status"] == "taken"

        # Patient retrieves the log — should see 1 entry
        resp = client.get(
            f"/api/patients/{patient_id}/medications/{med_id}/logs",
            headers=pat_headers,
        )
        assert resp.status_code == 200, f"Medication logs list failed ({resp.status_code}): {resp.text}"
        logs = resp.json()
        assert len(logs) == 1, f"Expected 1 log entry, got {len(logs)}: {logs}"
        assert logs[0]["medication_id"] == med_id
        assert logs[0]["status"] == "taken"


# ---------------------------------------------------------------------------
# Test 3: Patient can request appointment change
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patient_requests_appointment_change(state: StateManager):
    """Patient can request a change to an appointment."""
    with _make_client(state) as client:
        patient_token, cg_token, patient_id, _circle_id = setup_circle(client)
        cg_headers = {"Authorization": f"Bearer {cg_token}"}
        pat_headers = {"Authorization": f"Bearer {patient_token}"}

        # Caregiver schedules an appointment
        resp = client.post(
            f"/api/patients/{patient_id}/appointments",
            json={
                "title": "Therapy session",
                "scheduled_at": "2026-04-15T10:00:00Z",
                "duration_minutes": 60,
                "appointment_type": "therapy",
            },
            headers=cg_headers,
        )
        assert resp.status_code == 201, f"Appointment creation failed ({resp.status_code}): {resp.text}"
        appt_id = resp.json()["id"]

        # Patient requests a change
        resp = client.patch(
            f"/api/patients/{patient_id}/appointments/{appt_id}",
            json={"change_requested": True, "change_note": "Can we move to Tuesday instead?"},
            headers=pat_headers,
        )
        assert resp.status_code == 200, f"Appointment update failed ({resp.status_code}): {resp.text}"

        # Verify change_requested and change_note are persisted
        resp = client.get(
            f"/api/patients/{patient_id}/appointments/{appt_id}",
            headers=pat_headers,
        )
        assert resp.status_code == 200, f"Appointment GET failed ({resp.status_code}): {resp.text}"
        appt = resp.json()
        assert appt["change_requested"] is True, f"Expected change_requested=True, got: {appt}"
        assert appt["change_note"] == "Can we move to Tuesday instead?", f"Unexpected change_note: {appt}"
