"""
Integration test: full caregiver dashboard flow.

Uses a real StateManager (in-memory SQLite) with actual data inserted via
StateManager methods, a real FastAPI TestClient (sync), and dependency_overrides
to inject a caregiver user without a real JWT.

Test coverage:
- 200 response with all sections populated from seeded data
- Patient name matches what was inserted
- Session summary (SOAP) is present and has content
- crisis_alerts entries do NOT contain trigger_text (privacy strip)
- Assessments are grouped by instrument (phq9, gad7, who5)
- Medication and appointment data present
- 403 when authenticated user has role != "caregiver"

@decision DEC-CARE-002
@title Integration test exercises real StateManager + full HTTP round-trip
@status accepted
@rationale Unit tests (test_caregiver_overview.py) cover edge cases and auth
    corner cases with minimal fixtures. This integration test complements them
    by seeding all data types and verifying the aggregation in one cohesive
    scenario — confirming the full stack from HTTP request through SQL queries
    to JSON response.
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
# Minimal LLM stub
# ---------------------------------------------------------------------------

class _NullLLM(LLMProvider):
    async def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(content="", model="null", input_tokens=0, output_tokens=0)

    async def stream(self, messages, **kwargs):
        return
        yield


# ---------------------------------------------------------------------------
# Fake users
# ---------------------------------------------------------------------------

_CAREGIVER_ID = "cg-integration-001"
_PATIENT_ID = "pat-integration-001"
_SESSION_ID = "sess-integration-001"

_CAREGIVER_USER = User(
    id=_CAREGIVER_ID,
    email="caregiver-int@example.com",
    role="caregiver",
    patient_id=None,
    created_at=datetime.utcnow(),
    is_active=True,
)

_NON_CAREGIVER_USER = User(
    id="user-integration-002",
    email="patient-int@example.com",
    role="user",
    patient_id=_PATIENT_ID,
    created_at=datetime.utcnow(),
    is_active=True,
)


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

@contextmanager
def _make_client(
    state: StateManager,
    user: User = _CAREGIVER_USER,
) -> Generator[TestClient, None, None]:
    """Authenticated test client wired to a real in-memory StateManager."""
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


# ---------------------------------------------------------------------------
# Rich fixture: all data types seeded
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def rich_state() -> StateManager:
    """
    In-memory StateManager with one patient linked to the test caregiver,
    plus sessions, SOAP summary, crisis alert, assessments, medication,
    and appointment.
    """
    sm = StateManager(":memory:")
    await sm.initialize()

    # Patient
    await sm.create_patient({
        "id": _PATIENT_ID,
        "name": "Integration Patient",
        "dob": "1985-03-20",
        "preferences": {},
        "emergency_contact": "Spouse: 555-9999",
        "caregiver_id": _CAREGIVER_ID,
    })

    # Seed care circle for Phase 9a.
    # initialize() auto-migrates existing patients but patient is created AFTER
    # initialize() here, so we must manually create the circle in the fixture.
    await sm._exec(
        "INSERT INTO users (id, email, hashed_password, role, created_at, is_active)"
        " VALUES (?, ?, ?, ?, datetime('now'), 1)",
        (_CAREGIVER_ID, "caregiver-int@example.com", "hashed", "caregiver"),
    )
    await sm.create_care_circle(f"circle-{_PATIENT_ID}", _PATIENT_ID)
    await sm.add_circle_member(
        f"ccm-{_CAREGIVER_ID}", f"circle-{_PATIENT_ID}", _CAREGIVER_ID, "primary_caregiver"
    )

    # Session
    await sm.create_session({
        "id": _SESSION_ID,
        "patient_id": _PATIENT_ID,
        "started_at": "2026-02-25T14:00:00",
        "ended_at": "2026-02-25T15:00:00",
        "summary": "",
        "mood_start": None,
        "mood_end": None,
    })

    # SOAP session summary
    await sm.create_session_summary({
        "id": str(uuid.uuid4()),
        "session_id": _SESSION_ID,
        "patient_id": _PATIENT_ID,
        "subjective": "Patient reports feeling less anxious this week.",
        "objective": "Mood appeared stable throughout session.",
        "assessment": "Moderate improvement noted in anxiety symptoms.",
        "plan": "Continue CBT exercises; reassess PHQ-9 next session.",
        "key_topics": ["anxiety", "sleep"],
        "risk_flags": [],
    })

    # Crisis alert — trigger_text must be stripped in response
    await sm.save_crisis_alert({
        "id": str(uuid.uuid4()),
        "patient_id": _PATIENT_ID,
        "session_id": _SESSION_ID,
        "severity": "MODERATE",
        "trigger_text": "I sometimes wonder if it's worth going on",
        "detection_method": "keyword",
        "escalation_action": None,
    })

    # Assessments — one each for phq9, gad7, who5
    await sm.save_assessment({
        "id": str(uuid.uuid4()),
        "patient_id": _PATIENT_ID,
        "instrument": "phq9",
        "item_scores": [1, 2, 1, 0, 1, 0, 1, 0, 0],
        "total_score": 6,
        "severity": "mild",
        "timestamp": "2026-02-25T15:00:00",
    })
    await sm.save_assessment({
        "id": str(uuid.uuid4()),
        "patient_id": _PATIENT_ID,
        "instrument": "gad7",
        "item_scores": [1, 1, 2, 0, 1, 0, 0],
        "total_score": 5,
        "severity": "mild",
        "timestamp": "2026-02-25T15:05:00",
    })
    await sm.save_assessment({
        "id": str(uuid.uuid4()),
        "patient_id": _PATIENT_ID,
        "instrument": "who5",
        "item_scores": [3, 2, 3, 4, 3],
        "total_score": 60,
        "severity": "normal",
        "timestamp": "2026-02-25T15:10:00",
    })

    # Medication
    await sm.create_medication({
        "id": str(uuid.uuid4()),
        "patient_id": _PATIENT_ID,
        "name": "Escitalopram",
        "dosage": "10mg",
        "frequency": "daily",
        "active": True,
        "notes": None,
        "prescribed_by": None,
        "started_at": None,
    })

    # Appointment
    await sm.create_appointment({
        "id": str(uuid.uuid4()),
        "patient_id": _PATIENT_ID,
        "title": "Psychiatry check-in",
        "scheduled_at": "2026-03-10T10:00:00",
        "duration_minutes": 45,
        "appointment_type": "psychiatry",
        "status": "scheduled",
        "description": None,
        "provider_name": None,
        "notes": None,
    })

    yield sm
    await sm.close()


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestCaregiverFlow:
    """Full caregiver dashboard integration — all data sections verified."""

    def test_overview_200_all_sections_present(self, rich_state):
        """GET /api/caregiver/overview returns 200 with all top-level keys."""
        with _make_client(rich_state) as client:
            resp = client.get("/api/caregiver/overview")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "patient" in data
        assert "recent_sessions" in data
        assert "crisis_alerts" in data
        assert "assessments" in data
        assert "medications" in data
        assert "appointments" in data

    def test_patient_name_matches(self, rich_state):
        """Patient sub-object name matches what was inserted."""
        with _make_client(rich_state) as client:
            resp = client.get("/api/caregiver/overview")
        assert resp.status_code == 200
        patient = resp.json()["patient"]
        assert patient["name"] == "Integration Patient"
        assert patient["dob"] == "1985-03-20"
        assert patient["emergency_contact"] == "Spouse: 555-9999"

    def test_session_summary_present(self, rich_state):
        """Recent sessions include the SOAP summary that was inserted."""
        with _make_client(rich_state) as client:
            resp = client.get("/api/caregiver/overview")
        assert resp.status_code == 200
        sessions = resp.json()["recent_sessions"]
        assert len(sessions) == 1
        assert sessions[0]["id"] == _SESSION_ID
        summary = sessions[0]["summary"]
        assert summary is not None
        assert "improvement noted" in summary["assessment"]
        assert "CBT" in summary["plan"]
        assert "anxiety" in summary["key_topics"]

    def test_crisis_alert_trigger_text_stripped(self, rich_state):
        """crisis_alerts entries must NOT contain trigger_text."""
        with _make_client(rich_state) as client:
            resp = client.get("/api/caregiver/overview")
        assert resp.status_code == 200
        alerts = resp.json()["crisis_alerts"]
        assert len(alerts) == 1
        assert "trigger_text" not in alerts[0]
        # Verify other fields are present
        assert alerts[0]["severity"] == "MODERATE"

    def test_assessments_grouped_by_instrument(self, rich_state):
        """Assessments dict has phq9/gad7/who5 with one entry each."""
        with _make_client(rich_state) as client:
            resp = client.get("/api/caregiver/overview")
        assert resp.status_code == 200
        assessments = resp.json()["assessments"]
        assert "phq9" in assessments
        assert "gad7" in assessments
        assert "who5" in assessments
        assert len(assessments["phq9"]) == 1
        assert assessments["phq9"][0]["total_score"] == 6
        assert assessments["phq9"][0]["severity"] == "mild"
        assert len(assessments["gad7"]) == 1
        assert assessments["gad7"][0]["total_score"] == 5
        assert len(assessments["who5"]) == 1
        assert assessments["who5"][0]["total_score"] == 60
        assert assessments["who5"][0]["severity"] == "normal"

    def test_medication_in_response(self, rich_state):
        """Medications list contains the inserted medication."""
        with _make_client(rich_state) as client:
            resp = client.get("/api/caregiver/overview")
        assert resp.status_code == 200
        meds = resp.json()["medications"]
        assert len(meds) == 1
        assert meds[0]["name"] == "Escitalopram"
        assert meds[0]["dosage"] == "10mg"
        assert meds[0]["frequency"] == "daily"
        assert meds[0]["active"] is True

    def test_appointment_in_response(self, rich_state):
        """Appointments list contains the inserted appointment."""
        with _make_client(rich_state) as client:
            resp = client.get("/api/caregiver/overview")
        assert resp.status_code == 200
        appts = resp.json()["appointments"]
        assert len(appts) == 1
        assert appts[0]["title"] == "Psychiatry check-in"
        assert appts[0]["status"] == "scheduled"

    def test_non_caregiver_role_denied(self, rich_state):
        """User with role='user' receives 403 Forbidden."""
        with _make_client(rich_state, user=_NON_CAREGIVER_USER) as client:
            resp = client.get("/api/caregiver/overview")
        assert resp.status_code == 403
