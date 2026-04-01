"""
Unit tests for medication REST endpoints.

Tests use real in-memory SQLite, real FastAPI TestClient (used as context manager
to trigger lifespan), and dependency_overrides to bypass JWT auth (auth is tested
separately in test_auth.py).

Coverage:
- POST /api/patients/{patient_id}/medications — create, 404 on missing patient
- GET /api/patients/{patient_id}/medications — list, active_only filter
- GET /api/patients/{patient_id}/medications/{medication_id} — get, 404
- PATCH /api/patients/{patient_id}/medications/{medication_id} — update
- DELETE /api/patients/{patient_id}/medications/{medication_id} — deactivate (204)
- Auth required (no override → 401/403)
- POST calls interaction check via agent registry when agent is registered

@decision DEC-AGENT-004
@title Route tests use dependency_overrides for auth isolation
@status accepted
@rationale Following the established pattern (test_knowledge.py). Auth is already
    tested in test_auth.py. Route tests focus on CRUD logic and agent integration.
    TestClient is used as a context manager to trigger the app lifespan (which sets
    app.state.*), consistent with how test_knowledge.py operates.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import AsyncIterator, Generator

import pytest
import pytest_asyncio

from fastapi.testclient import TestClient

from ada.agents.medication_manager import MedicationManagerAgent
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
# Helpers
# ---------------------------------------------------------------------------

class _NullLLM(LLMProvider):
    async def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(content="NO_INTERACTION", model="null", input_tokens=0, output_tokens=0)

    async def stream(self, messages, **kwargs) -> AsyncIterator[str]:
        return
        yield


class _InteractionLLM(LLMProvider):
    """Returns a canned LLM response, supports a response queue for sequencing."""

    def __init__(self, default_response: str = "NO_INTERACTION"):
        self.default_response = default_response
        self.response_queue: list[str] = []
        self.calls: list[dict] = []

    def queue(self, response: str) -> None:
        self.response_queue.append(response)

    async def complete(self, messages, **kwargs) -> LLMResponse:
        self.calls.append({"messages": messages})
        content = self.response_queue.pop(0) if self.response_queue else self.default_response
        return LLMResponse(content=content, model="mock", input_tokens=0, output_tokens=0)

    async def stream(self, messages, **kwargs) -> AsyncIterator[str]:
        yield self.default_response


_FAKE_USER = User(
    id="user-route-001",
    email="clinician@example.com",
    role="clinician",
    patient_id=None,
    created_at=datetime.utcnow(),
    is_active=True,
)


# ---------------------------------------------------------------------------
# Client factories
# ---------------------------------------------------------------------------

@contextmanager
def _make_client(
    state: StateManager,
    llm: LLMProvider | None = None,
    with_agent: bool = False,
) -> Generator[TestClient, None, None]:
    """
    Create an authenticated test client.

    Must be used as a context manager to trigger the FastAPI lifespan
    which initialises app.state (bus, state_manager, registry, config).

    Args:
        state: Pre-initialised StateManager (in-memory SQLite).
        llm: Optional LLM provider. Defaults to _NullLLM.
        with_agent: If True, register and activate MedicationManagerAgent.
    """
    config = AdaConfig()
    bus = EventBus()
    actual_llm = llm or _NullLLM()
    registry = AgentRegistry(bus, config, state, make_null_router(actual_llm))

    if with_agent:
        agent = MedicationManagerAgent()
        agent.initialize(bus, config, state, actual_llm)
        registry._agents.append(agent)
        registry._active.append(agent)

    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


@contextmanager
def _make_unauthenticated_client(
    state: StateManager,
) -> Generator[TestClient, None, None]:
    """Client with NO auth override — tests that routes are protected."""
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    # No dependency_overrides — real auth applies
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
        "id": "pat-route-001",
        "name": "Route Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    yield sm
    await sm.close()


# ---------------------------------------------------------------------------
# POST /api/patients/{patient_id}/medications
# ---------------------------------------------------------------------------

class TestCreateMedication:

    def test_create_returns_201(self, state):
        with _make_client(state) as client:
            resp = client.post("/api/patients/pat-route-001/medications", json={
                "name": "Sertraline",
                "dosage": "50mg",
                "frequency": "daily",
            })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Sertraline"
        assert data["patient_id"] == "pat-route-001"
        assert data["dosage"] == "50mg"
        assert "id" in data

    def test_create_404_for_missing_patient(self, state):
        with _make_client(state) as client:
            resp = client.post("/api/patients/nonexistent-patient/medications", json={
                "name": "Aspirin",
            })
        assert resp.status_code == 404

    def test_create_minimal_required_fields(self, state):
        with _make_client(state) as client:
            resp = client.post("/api/patients/pat-route-001/medications", json={
                "name": "Melatonin",
            })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Melatonin"
        assert data["dosage"] is None
        assert data["frequency"] is None

    def test_create_requires_auth(self, state):
        with _make_unauthenticated_client(state) as client:
            resp = client.post("/api/patients/pat-route-001/medications", json={
                "name": "Aspirin",
            })
        assert resp.status_code in (401, 403)

    def test_create_with_interaction_warning(self, state):
        """When agent detects an interaction, the warning is included in the response."""
        llm = _InteractionLLM()

        with _make_client(state, llm=llm, with_agent=True) as client:
            # First create Warfarin so the agent has something to check against
            client.post("/api/patients/pat-route-001/medications", json={"name": "Warfarin"})
            # Queue the interaction response for the second call
            llm.queue("INTERACTION: Warfarin and Aspirin increase bleeding risk")
            # Add Aspirin — should trigger interaction warning
            resp = client.post("/api/patients/pat-route-001/medications", json={"name": "Aspirin"})

        assert resp.status_code == 201
        data = resp.json()
        # Medication was still created despite the warning
        assert data["name"] == "Aspirin"
        assert "interaction_warning" in data
        assert len(data["interaction_warning"]) > 0

    def test_create_no_interaction_warning_when_clean(self, state):
        """When no interaction, response has no interaction_warning key."""
        llm = _InteractionLLM("NO_INTERACTION")

        with _make_client(state, llm=llm, with_agent=True) as client:
            client.post("/api/patients/pat-route-001/medications", json={"name": "Vitamin C"})
            resp = client.post("/api/patients/pat-route-001/medications", json={"name": "Vitamin D"})

        assert resp.status_code == 201
        data = resp.json()
        assert "interaction_warning" not in data


# ---------------------------------------------------------------------------
# GET /api/patients/{patient_id}/medications
# ---------------------------------------------------------------------------

class TestListMedications:

    def test_empty_list(self, state):
        with _make_client(state) as client:
            resp = client.get("/api/patients/pat-route-001/medications")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_created_medications(self, state):
        with _make_client(state) as client:
            client.post("/api/patients/pat-route-001/medications", json={"name": "Prozac"})
            client.post("/api/patients/pat-route-001/medications", json={"name": "Valium"})
            resp = client.get("/api/patients/pat-route-001/medications")
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()]
        assert "Prozac" in names
        assert "Valium" in names

    def test_list_404_for_missing_patient(self, state):
        with _make_client(state) as client:
            resp = client.get("/api/patients/nonexistent/medications")
        assert resp.status_code == 404

    def test_list_active_only_filter(self, state):
        """active_only=true should exclude deactivated medications."""
        with _make_client(state) as client:
            client.post("/api/patients/pat-route-001/medications", json={"name": "ActiveMed"})
            r2 = client.post("/api/patients/pat-route-001/medications", json={"name": "InactiveMed"})
            med_id = r2.json()["id"]
            client.delete(f"/api/patients/pat-route-001/medications/{med_id}")

            # Without filter: both present
            all_resp = client.get("/api/patients/pat-route-001/medications")
            all_names = [m["name"] for m in all_resp.json()]
            assert "InactiveMed" in all_names

            # With active_only=true: only active
            active_resp = client.get(
                "/api/patients/pat-route-001/medications",
                params={"active_only": True},
            )
            active_names = [m["name"] for m in active_resp.json()]
            assert "ActiveMed" in active_names
            assert "InactiveMed" not in active_names

    def test_list_requires_auth(self, state):
        with _make_unauthenticated_client(state) as client:
            resp = client.get("/api/patients/pat-route-001/medications")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /api/patients/{patient_id}/medications/{medication_id}
# ---------------------------------------------------------------------------

class TestGetMedication:

    def test_get_existing_medication(self, state):
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-route-001/medications",
                json={"name": "Lithium", "dosage": "300mg"},
            )
            med_id = create_resp.json()["id"]
            resp = client.get(f"/api/patients/pat-route-001/medications/{med_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Lithium"
        assert resp.json()["dosage"] == "300mg"

    def test_get_404_for_missing_medication(self, state):
        with _make_client(state) as client:
            resp = client.get("/api/patients/pat-route-001/medications/nonexistent-id")
        assert resp.status_code == 404

    def test_get_404_for_wrong_patient(self, state):
        """Medication belonging to a different patient returns 404."""
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-route-001/medications",
                json={"name": "Xanax"},
            )
            med_id = create_resp.json()["id"]
            resp = client.get(f"/api/patients/other-patient/medications/{med_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/patients/{patient_id}/medications/{medication_id}
# ---------------------------------------------------------------------------

class TestUpdateMedication:

    def test_update_dosage(self, state):
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-route-001/medications",
                json={"name": "Fluoxetine", "dosage": "20mg"},
            )
            med_id = create_resp.json()["id"]
            resp = client.patch(
                f"/api/patients/pat-route-001/medications/{med_id}",
                json={"dosage": "40mg"},
            )
        assert resp.status_code == 200
        assert resp.json()["dosage"] == "40mg"
        assert resp.json()["name"] == "Fluoxetine"  # unchanged

    def test_update_active_false_deactivates(self, state):
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-route-001/medications",
                json={"name": "Quetiapine"},
            )
            med_id = create_resp.json()["id"]
            resp = client.patch(
                f"/api/patients/pat-route-001/medications/{med_id}",
                json={"active": False},
            )
        assert resp.status_code == 200
        assert resp.json()["active"] is False

    def test_update_404_for_missing_medication(self, state):
        with _make_client(state) as client:
            resp = client.patch(
                "/api/patients/pat-route-001/medications/bad-id",
                json={"dosage": "100mg"},
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/patients/{patient_id}/medications/{medication_id}
# ---------------------------------------------------------------------------

class TestDeactivateMedication:

    def test_delete_returns_204(self, state):
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-route-001/medications",
                json={"name": "Risperidone"},
            )
            med_id = create_resp.json()["id"]
            resp = client.delete(f"/api/patients/pat-route-001/medications/{med_id}")
        assert resp.status_code == 204

    def test_deleted_medication_is_inactive(self, state):
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-route-001/medications",
                json={"name": "Olanzapine"},
            )
            med_id = create_resp.json()["id"]
            client.delete(f"/api/patients/pat-route-001/medications/{med_id}")
            # Fetch it — still exists but inactive
            get_resp = client.get(f"/api/patients/pat-route-001/medications/{med_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["active"] is False

    def test_delete_404_for_missing_medication(self, state):
        with _make_client(state) as client:
            resp = client.delete("/api/patients/pat-route-001/medications/ghost-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/patients/{patient_id}/medications/{medication_id}/log
# GET  /api/patients/{patient_id}/medications/{medication_id}/logs
# ---------------------------------------------------------------------------

class TestMedicationLogs:

    def test_log_medication_taken(self, state):
        """POST /log returns 201 with correct fields."""
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-route-001/medications",
                json={"name": "Metformin", "dosage": "500mg"},
            )
            med_id = create_resp.json()["id"]
            resp = client.post(
                f"/api/patients/pat-route-001/medications/{med_id}/log"
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["medication_id"] == med_id
        assert data["patient_id"] == "pat-route-001"
        assert data["status"] == "taken"
        assert "id" in data
        assert "taken_at" in data
        assert "created_at" in data

    def test_get_medication_logs(self, state):
        """POST a log then GET /logs returns a list containing the log."""
        with _make_client(state) as client:
            create_resp = client.post(
                "/api/patients/pat-route-001/medications",
                json={"name": "Lisinopril"},
            )
            med_id = create_resp.json()["id"]
            client.post(f"/api/patients/pat-route-001/medications/{med_id}/log")
            resp = client.get(f"/api/patients/pat-route-001/medications/{med_id}/logs")
        assert resp.status_code == 200
        logs = resp.json()
        assert isinstance(logs, list)
        assert len(logs) == 1
        assert logs[0]["medication_id"] == med_id

    def test_log_medication_not_found(self, state):
        """POST log for non-existent medication returns 404."""
        with _make_client(state) as client:
            resp = client.post(
                "/api/patients/pat-route-001/medications/nonexistent-med-id/log"
            )
        assert resp.status_code == 404
