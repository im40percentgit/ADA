"""Integration test: full caregiver setup flow end-to-end.

Exercises the complete caregiver onboarding path using real HTTP round-trips,
real in-memory SQLite StateManager, and genuine JWT auth (register → login →
token). No dependency_overrides — auth is exercised for real.

Uses FastAPI TestClient (sync) entered as a context manager so the ASGI
lifespan fires and app.state.state_manager is populated. Real passwords and
JWTs are issued through the auth routes, not mocked.

Test coverage:
- Register caregiver → no circles yet → create circle with new patient
  → circle exists → fetch caregiver overview for that patient (test 1)
- Register patient first → register caregiver → lookup patient by email
  → create circle linked to existing patient → patient_id matches (test 2)
- Register caregiver → create circle → add medication → list medications
  → verify medication present (test 3)

@decision DEC-SETUP-001
@title Caregiver setup integration tests use real JWT auth
@status accepted
@rationale Unlike earlier integration tests (test_circle_flow.py,
    test_caregiver_flow.py) which override get_current_user, these tests
    exercise the full authentication path. Using TestClient with real
    register/login/JWT-bearer calls validates the complete vertical slice:
    auth routes, circle lookup+create, and medication management — confirming
    Task 1 (lookup) and Task 2 (create-with-patient) work end-to-end.
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
# Helper
# ---------------------------------------------------------------------------

def register_and_login(client: TestClient, email: str, password: str, role: str = "user") -> str:
    """Register a user and return a JWT access token."""
    client.post("/api/auth/register", json={"email": email, "password": password, "role": role})
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed ({resp.status_code}): {resp.text}"
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Test 1: register caregiver → create circle with new patient → verify
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_caregiver_setup_create_new_patient(state: StateManager):
    """Register caregiver → no circles yet → create circle with new patient
    → circle exists → fetch caregiver overview for that patient."""
    with _make_client(state) as client:
        # Register + login as caregiver (real JWT)
        token = register_and_login(client, "cg@example.com", "secret123", role="caregiver")
        headers = {"Authorization": f"Bearer {token}"}

        # No circles yet
        resp = client.get("/api/circles/my", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []

        # Create circle with a brand-new patient (name only, no email)
        resp = client.post(
            "/api/circles/create-with-patient",
            json={"patient_name": "Alice Newpatient"},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["patient_name"] == "Alice Newpatient"
        patient_id = body["patient_id"]
        assert patient_id

        # Circle now exists
        resp = client.get("/api/circles/my", headers=headers)
        assert resp.status_code == 200
        circles = resp.json()
        assert len(circles) == 1
        assert circles[0]["patient_name"] == "Alice Newpatient"

        # Fetch caregiver overview for this specific patient
        resp = client.get(
            f"/api/caregiver/overview?patient_id={patient_id}",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Overview patient dict contains name/dob/emergency_contact (no id field)
        assert data["patient"]["name"] == "Alice Newpatient"
        assert "recent_sessions" in data
        assert "medications" in data


# ---------------------------------------------------------------------------
# Test 2: register patient → caregiver looks up by email → links in circle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_caregiver_setup_link_existing_patient(state: StateManager):
    """Register patient first → register caregiver → lookup patient by email
    → create circle linked to existing patient → patient_id matches."""
    with _make_client(state) as client:
        # Register the patient first (role=user auto-creates a patient record)
        pat_token = register_and_login(client, "patient@example.com", "patpass123", role="user")

        # Fetch the patient's own user info to capture their patient_id
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {pat_token}"})
        assert resp.status_code == 200
        pat_user = resp.json()
        expected_patient_id = pat_user["patient_id"]
        assert expected_patient_id, "User registration should auto-create a patient record"

        # Register caregiver
        cg_token = register_and_login(client, "caregiver2@example.com", "cgpass123", role="caregiver")
        cg_headers = {"Authorization": f"Bearer {cg_token}"}

        # Caregiver looks up patient by email
        resp = client.get(
            "/api/circles/lookup?email=patient@example.com",
            headers=cg_headers,
        )
        assert resp.status_code == 200, resp.text
        lookup = resp.json()
        assert lookup["email"] == "patient@example.com"
        assert lookup["patient_id"] == expected_patient_id
        assert lookup["role"] == "user"

        # Create circle linked to the existing patient via email
        resp = client.post(
            "/api/circles/create-with-patient",
            json={"patient_name": "Existing Patient", "patient_email": "patient@example.com"},
            headers=cg_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()

        # patient_id must match the one registered by the patient
        assert body["patient_id"] == expected_patient_id


# ---------------------------------------------------------------------------
# Test 3: caregiver → create circle → add + list medications
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_caregiver_can_manage_medications_after_setup(state: StateManager):
    """Register caregiver → create circle → add medication → list medications
    → verify medication is present."""
    with _make_client(state) as client:
        # Register + login caregiver
        token = register_and_login(client, "cg3@example.com", "pass3secure", role="caregiver")
        headers = {"Authorization": f"Bearer {token}"}

        # Create circle with new patient
        resp = client.post(
            "/api/circles/create-with-patient",
            json={"patient_name": "Med Patient"},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        patient_id = resp.json()["patient_id"]

        # Add a medication
        resp = client.post(
            f"/api/patients/{patient_id}/medications",
            json={
                "name": "Sertraline",
                "dosage": "50mg",
                "frequency": "daily",
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        med = resp.json()
        assert med["name"] == "Sertraline"
        assert med["dosage"] == "50mg"
        assert med["frequency"] == "daily"

        # List medications
        resp = client.get(
            f"/api/patients/{patient_id}/medications",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        meds = resp.json()
        assert len(meds) == 1
        assert meds[0]["name"] == "Sertraline"
        assert meds[0]["dosage"] == "50mg"
        assert meds[0]["active"] is True
