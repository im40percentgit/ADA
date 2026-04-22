"""
Integration test: patient-access authorization (IDOR fix).

Verifies that require_patient_access correctly gates every patient-scoped
endpoint — an authenticated user without circle membership cannot read or
modify another user's patient records.

Test cases:
  - 403 for cross-user access on every patient-scoped endpoint (parametrized)
  - 200/2xx for self-access (user A -> patient A)
  - 200/2xx for caregiver in shared circle (cross-circle positive case)

@decision DEC-AUTHZ-001
@title Integration test validates require_patient_access on all patient routes
@status accepted
@rationale Parametrized across every patient-scoped endpoint so future routes
    that forget the dependency are caught immediately. Real in-memory SQLite +
    FastAPI TestClient (no mocks) -- consistent with DEC-TEST-005.
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
        return LLMResponse(content="ok", model="null", input_tokens=0, output_tokens=0)

    async def stream(self, messages, **kwargs):
        return
        yield


# ---------------------------------------------------------------------------
# Fixed IDs
# ---------------------------------------------------------------------------

_USER_A_ID = "authz-user-a"
_USER_B_ID = "authz-user-b"
_PATIENT_A_ID = "authz-patient-a"
_PATIENT_B_ID = "authz-patient-b"
_CIRCLE_A_ID = "authz-circle-a"
_CIRCLE_B_ID = "authz-circle-b"

_USER_A = User(
    id=_USER_A_ID,
    email="user-a@authz-test.com",
    role="caregiver",
    patient_id=None,
    created_at=datetime.utcnow(),
    is_active=True,
)

_USER_B = User(
    id=_USER_B_ID,
    email="user-b@authz-test.com",
    role="caregiver",
    patient_id=None,
    created_at=datetime.utcnow(),
    is_active=True,
)

# User whose patient_id field directly matches _PATIENT_A_ID (self-access path)
_SELF_USER = User(
    id="authz-self-user",
    email="self@authz-test.com",
    role="user",
    patient_id=_PATIENT_A_ID,
    created_at=datetime.utcnow(),
    is_active=True,
)


# ---------------------------------------------------------------------------
# Shared state fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def authz_state() -> StateManager:
    """
    In-memory StateManager with two patients in separate care circles.

    User A is a member of circle A (patient A only).
    User B is a member of circle B (patient B only).
    No overlap -- so A->patientB must always 403.
    """
    sm = StateManager(":memory:")
    await sm.initialize()

    # Insert users into DB (required for org-mode query)
    for uid, email, role in [
        (_USER_A_ID, "user-a@authz-test.com", "caregiver"),
        (_USER_B_ID, "user-b@authz-test.com", "caregiver"),
        ("authz-self-user", "self@authz-test.com", "user"),
    ]:
        await sm._exec(
            "INSERT INTO users (id, email, hashed_password, role, created_at, is_active)"
            " VALUES (?, ?, ?, ?, datetime('now'), 1)",
            (uid, email, "hashed", role),
        )

    # Patient A
    await sm.create_patient({
        "id": _PATIENT_A_ID,
        "name": "Patient Alpha",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
        "organization_id": None,
    })

    # Patient B
    await sm.create_patient({
        "id": _PATIENT_B_ID,
        "name": "Patient Beta",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
        "organization_id": None,
    })

    # Circle A: user A + self-user -> patient A
    await sm.create_care_circle(_CIRCLE_A_ID, _PATIENT_A_ID)
    await sm.add_circle_member(
        "ccm-a-usera", _CIRCLE_A_ID, _USER_A_ID, "primary_caregiver"
    )
    await sm.add_circle_member(
        "ccm-a-self", _CIRCLE_A_ID, "authz-self-user", "primary_caregiver"
    )

    # Circle B: user B -> patient B
    await sm.create_care_circle(_CIRCLE_B_ID, _PATIENT_B_ID)
    await sm.add_circle_member(
        "ccm-b-userb", _CIRCLE_B_ID, _USER_B_ID, "primary_caregiver"
    )

    # Seed minimal records for patient A so endpoints don't 404 before auth check
    med_id = "authz-med-a"
    await sm.create_medication({
        "id": med_id,
        "patient_id": _PATIENT_A_ID,
        "name": "Sertraline",
        "dosage": "50mg",
        "frequency": "daily",
        "start_date": None,
        "end_date": None,
        "notes": None,
        "prescribed_by": None,
        "active": 1,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    })

    await sm._exec(
        """INSERT INTO cognitive_screenings
           (id, patient_id, status, overall_score, started_at, created_at)
           VALUES (?, ?, 'completed', 0.85, datetime('now'), datetime('now'))""",
        ("authz-screening-a", _PATIENT_A_ID),
    )

    await sm.create_appointment({
        "id": "authz-appt-a",
        "patient_id": _PATIENT_A_ID,
        "title": "Check-in",
        "description": None,
        "scheduled_at": "2026-05-01T10:00:00",
        "duration_minutes": 30,
        "appointment_type": "therapy",
        "status": "scheduled",
        "provider_name": None,
        "notes": None,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    })

    await sm.create_treatment_plan({
        "id": "authz-plan-a",
        "patient_id": _PATIENT_A_ID,
        "clinician_id": _USER_A_ID,
        "organization_id": None,
        "title": "CBT Plan",
    })

    yield sm
    await sm.close()


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

@contextmanager
def _make_client(state: StateManager, user: User) -> Generator[TestClient, None, None]:
    """Return an authenticated TestClient wired to a real in-memory state."""
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


# ---------------------------------------------------------------------------
# Parametrized endpoint list
# ---------------------------------------------------------------------------

_PATIENT_ENDPOINTS = [
    # patients.py
    ("GET",    "/api/patients/{patient_id}",                              None),
    ("PATCH",  "/api/patients/{patient_id}",                              {"name": "X"}),
    # assessments.py
    ("GET",    "/api/patients/{patient_id}/assessments",                  None),
    ("GET",    "/api/patients/{patient_id}/mood-history",                 None),
    ("GET",    "/api/patients/{patient_id}/crisis-alerts",                None),
    # medications.py
    ("GET",    "/api/patients/{patient_id}/medications",                  None),
    ("POST",   "/api/patients/{patient_id}/medications",
     {"name": "X", "dosage": "1mg", "frequency": "daily"}),
    ("GET",    "/api/patients/{patient_id}/medications/authz-med-a",      None),
    ("PATCH",  "/api/patients/{patient_id}/medications/authz-med-a",      {"dosage": "2mg"}),
    ("DELETE", "/api/patients/{patient_id}/medications/authz-med-a",      None),
    ("POST",   "/api/patients/{patient_id}/medications/authz-med-a/log",  None),
    ("GET",    "/api/patients/{patient_id}/medications/authz-med-a/logs", None),
    # cognitive.py
    ("GET",    "/api/patients/{patient_id}/cognitive-screenings",         None),
    ("GET",    "/api/patients/{patient_id}/cognitive-screenings/authz-screening-a", None),
    # screening_interact.py
    ("POST",   "/api/patients/{patient_id}/screenings/start",             {}),
    # appointments.py
    ("GET",    "/api/patients/{patient_id}/appointments",                 None),
    ("POST",   "/api/patients/{patient_id}/appointments",
     {"title": "X", "scheduled_at": "2026-06-01T10:00:00",
      "duration_minutes": 30, "appointment_type": "therapy"}),
    ("GET",    "/api/patients/{patient_id}/appointments/authz-appt-a",   None),
    ("PATCH",  "/api/patients/{patient_id}/appointments/authz-appt-a",   {"title": "Y"}),
    ("DELETE", "/api/patients/{patient_id}/appointments/authz-appt-a",   None),
    # daily_summaries.py
    ("GET",    "/api/patients/{patient_id}/daily-summaries/2026-04-21",   None),
    # knowledge.py
    ("GET",    "/api/patients/{patient_id}/knowledge/graph",              None),
    ("GET",    "/api/patients/{patient_id}/knowledge/insights",           None),
    ("GET",    "/api/patients/{patient_id}/knowledge/trends",             None),
    # progress_report.py
    ("GET",    "/api/patients/{patient_id}/progress-report",              None),
    # sessions.py
    ("GET",    "/api/patients/{patient_id}/sessions",                     None),
    # treatment_plans.py
    ("GET",    "/api/patients/{patient_id}/treatment-plans",              None),
    # prescribing_notes.py
    ("GET",    "/api/patients/{patient_id}/prescribing-notes",            None),
    # data_export.py
    ("GET",    "/api/patients/{patient_id}/export/assessments",           None),
    ("GET",    "/api/patients/{patient_id}/export/mood",                  None),
    ("GET",    "/api/patients/{patient_id}/export/medications",           None),
    ("GET",    "/api/patients/{patient_id}/export/sessions",              None),
    ("GET",    "/api/patients/{patient_id}/export/wellbeing",             None),
]


def _endpoint_id(val):
    if isinstance(val, tuple):
        return f"{val[0]} {val[1]}"
    return str(val)


# ---------------------------------------------------------------------------
# Test 1: Cross-user 403
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,path_tmpl,body", _PATIENT_ENDPOINTS, ids=_endpoint_id)
def test_cross_user_access_returns_403(
    authz_state: StateManager,
    method: str,
    path_tmpl: str,
    body,
) -> None:
    """User A authenticated but accessing patient B's data must always get 403."""
    path = path_tmpl.replace("{patient_id}", _PATIENT_B_ID)
    with _make_client(authz_state, _USER_A) as client:
        kwargs = {"json": body} if body is not None else {}
        resp = getattr(client, method.lower())(path, **kwargs)
    assert resp.status_code == 403, (
        f"{method} {path} returned {resp.status_code}, expected 403. "
        f"Body: {resp.text[:200]}"
    )


# ---------------------------------------------------------------------------
# Test 2: Self-access returns not-403
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,path_tmpl,body", _PATIENT_ENDPOINTS, ids=_endpoint_id)
def test_own_patient_access_not_403(
    authz_state: StateManager,
    method: str,
    path_tmpl: str,
    body,
) -> None:
    """User A accessing patient A must NOT return 403.

    204, 404, 422, 400, 500 are all acceptable -- auth passed, some other
    layer produced the response.
    """
    path = path_tmpl.replace("{patient_id}", _PATIENT_A_ID)
    with _make_client(authz_state, _USER_A) as client:
        kwargs = {"json": body} if body is not None else {}
        resp = getattr(client, method.lower())(path, **kwargs)
    assert resp.status_code != 403, (
        f"{method} {path} returned 403 -- authz incorrectly denied user A "
        f"access to their own patient A. Body: {resp.text[:200]}"
    )


# ---------------------------------------------------------------------------
# Test 3: Self-access via user.patient_id fast-path
# ---------------------------------------------------------------------------

def test_self_patient_id_field_grants_access(authz_state: StateManager) -> None:
    """role=user whose patient_id == path patient_id bypasses DB check."""
    path = f"/api/patients/{_PATIENT_A_ID}"
    with _make_client(authz_state, _SELF_USER) as client:
        resp = client.get(path)
    assert resp.status_code == 200, (
        f"Self-access via patient_id field was incorrectly denied: {resp.text[:200]}"
    )


# ---------------------------------------------------------------------------
# Test 4: Caregiver added to shared circle gets access
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_caregiver_in_shared_circle_can_access(authz_state: StateManager) -> None:
    """Add user B into circle A -- then user B can read patient A."""
    await authz_state.add_circle_member(
        "ccm-a-userb", _CIRCLE_A_ID, _USER_B_ID, "family"
    )
    path = f"/api/patients/{_PATIENT_A_ID}"
    with _make_client(authz_state, _USER_B) as client:
        resp = client.get(path)
    assert resp.status_code == 200, (
        f"Caregiver in shared circle was denied: {resp.text[:200]}"
    )


# ---------------------------------------------------------------------------
# Test 5: Direct state method test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_can_access_patient_state_method(authz_state: StateManager) -> None:
    """StateManager.user_can_access_patient returns correct booleans."""
    assert await authz_state.user_can_access_patient(_USER_A_ID, _PATIENT_A_ID) is True
    assert await authz_state.user_can_access_patient(_USER_A_ID, _PATIENT_B_ID) is False
    assert await authz_state.user_can_access_patient(_USER_B_ID, _PATIENT_B_ID) is True
    assert await authz_state.user_can_access_patient(_USER_B_ID, _PATIENT_A_ID) is False
