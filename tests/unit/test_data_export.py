"""
Unit tests for CSV data export endpoints (Phase 14c, Task 1).

Tests use a real in-memory SQLite StateManager and FastAPI TestClient with
dependency_overrides to inject authenticated users without real JWTs —
the same pattern as test_organization_routes.py and test_treatment_plans.py.

Coverage:
  GET /api/patients/{id}/export/assessments
  GET /api/patients/{id}/export/mood
  GET /api/patients/{id}/export/medications
  GET /api/patients/{id}/export/sessions

For each endpoint:
  - 200 with valid CSV body (parseable via csv.reader)
  - Correct headers (first row matches expected columns)
  - Content-Type = text/csv
  - Content-Disposition has attachment + correct filename pattern
  - Auth required (401 without token)
  - Tenant isolation (org-A user cannot export org-B patient — 404)

@decision DEC-EXPORT-TEST-001
@title Data export tests use real in-memory SQLite
@status accepted
@rationale Follows Sacred Practice #5 — no mocks of internal modules.
    Real in-memory SQLite exercises the full stack from HTTP request
    through SQL queries to CSV response. This matches the established
    pattern in test_organization_routes.py and test_treatment_plans.py.
"""

from __future__ import annotations

import csv
import io
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
# Fixed IDs
# ---------------------------------------------------------------------------

_USER_A_ID = "user-a-001"
_USER_A_EMAIL = "user-a@example.com"

_USER_B_ID = "user-b-001"
_USER_B_EMAIL = "user-b@example.com"

_ORG_A_ID = "org-a-001"
_ORG_B_ID = "org-b-001"

_PATIENT_A_ID = "patient-a-001"
_PATIENT_B_ID = "patient-b-001"

_SESSION_ID = "session-001"
_MEDICATION_ID = "medication-001"
_ASSESSMENT_ID = "assessment-001"


# ---------------------------------------------------------------------------
# User stubs
# ---------------------------------------------------------------------------

def _user(uid: str, email: str, role: str = "user") -> User:
    return User(
        id=uid,
        email=email,
        role=role,
        patient_id=None,
        created_at=datetime.utcnow(),
        is_active=True,
    )


_USER_A = _user(_USER_A_ID, _USER_A_EMAIL)
_USER_B = _user(_USER_B_ID, _USER_B_EMAIL)


# ---------------------------------------------------------------------------
# Fixture: seeded StateManager
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state() -> StateManager:
    """
    In-memory StateManager with:
      - 2 orgs (A, B)
      - 2 users (A in org A, B in org B)
      - patient A in org A with session, assessment, medication
      - patient B in org B with no data (for empty + isolation tests)
    """
    sm = StateManager(":memory:")
    await sm.initialize()

    now = datetime.utcnow().isoformat()

    # Organizations
    await sm._exec(
        "INSERT INTO organizations (id, name, slug, created_at, updated_at) VALUES (:id, :name, :slug, :ca, :ua)",
        {"id": _ORG_A_ID, "name": "Org A", "slug": "org-a", "ca": now, "ua": now},
    )
    await sm._exec(
        "INSERT INTO organizations (id, name, slug, created_at, updated_at) VALUES (:id, :name, :slug, :ca, :ua)",
        {"id": _ORG_B_ID, "name": "Org B", "slug": "org-b", "ca": now, "ua": now},
    )

    # Users
    for uid, email in [(_USER_A_ID, _USER_A_EMAIL), (_USER_B_ID, _USER_B_EMAIL)]:
        await sm.create_user({"id": uid, "email": email, "hashed_password": "x", "role": "user", "created_at": now})

    # Org memberships
    await sm._exec(
        "INSERT INTO organization_members (id, organization_id, user_id, role) VALUES (:id, :oid, :uid, :role)",
        {"id": "mem-a", "oid": _ORG_A_ID, "uid": _USER_A_ID, "role": "member"},
    )
    await sm._exec(
        "INSERT INTO organization_members (id, organization_id, user_id, role) VALUES (:id, :oid, :uid, :role)",
        {"id": "mem-b", "oid": _ORG_B_ID, "uid": _USER_B_ID, "role": "member"},
    )

    # Patient A (org A) with data
    await sm.create_patient({
        "id": _PATIENT_A_ID, "name": "Alice", "dob": None,
        "preferences": {}, "emergency_contact": None, "caregiver_id": None,
        "organization_id": _ORG_A_ID, "created_at": now,
    })

    # Patient B (org B) — no session/assessment/medication data
    await sm.create_patient({
        "id": _PATIENT_B_ID, "name": "Bob", "dob": None,
        "preferences": {}, "emergency_contact": None, "caregiver_id": None,
        "organization_id": _ORG_B_ID, "created_at": now,
    })

    # Session for patient A with mood data
    await sm.create_session({
        "id": _SESSION_ID, "patient_id": _PATIENT_A_ID,
        "started_at": "2025-01-15T10:00:00", "ended_at": "2025-01-15T10:50:00",
        "summary": "Good session with significant progress on coping skills.",
        "mood_start": 5.0, "mood_end": 7.5,
    })

    # Assessment for patient A
    await sm.save_assessment({
        "id": _ASSESSMENT_ID, "patient_id": _PATIENT_A_ID,
        "instrument": "phq9", "item_scores": [1, 0, 2, 1, 0, 1, 0, 0, 0],
        "total_score": 5, "severity": "mild", "timestamp": "2025-01-15T10:30:00",
    })

    # Medication for patient A
    await sm.create_medication({
        "id": _MEDICATION_ID, "patient_id": _PATIENT_A_ID,
        "name": "Sertraline 50mg", "active": 1,
        "created_at": "2025-01-10T09:00:00", "updated_at": "2025-01-10T09:00:00",
    })

    yield sm
    await sm.close()


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

@contextmanager
def _client(state: StateManager, user: User | None) -> Generator[TestClient, None, None]:
    """Authenticated or unauthenticated TestClient wired to the given state."""
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _parse_csv(text: str) -> list[list[str]]:
    """Parse CSV text into a list of rows."""
    return list(csv.reader(io.StringIO(text)))


def _assert_csv_response(resp, expected_headers: list[str], export_type: str, patient_id: str) -> list[list[str]]:
    """Assert 200, text/csv content-type, attachment disposition, and correct CSV headers."""
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    content_type = resp.headers.get("content-type", "")
    assert "text/csv" in content_type, f"Expected text/csv, got: {content_type}"
    disposition = resp.headers.get("content-disposition", "")
    assert "attachment" in disposition, f"Expected attachment, got: {disposition}"
    assert export_type in disposition, f"Expected '{export_type}' in filename, got: {disposition}"
    assert patient_id in disposition, f"Expected patient_id in filename, got: {disposition}"
    rows = _parse_csv(resp.text)
    assert len(rows) >= 1, "Expected at least a header row"
    assert rows[0] == expected_headers, f"Expected headers {expected_headers}, got {rows[0]}"
    return rows


# ===========================================================================
# Assessments export
# ===========================================================================

def test_export_assessments_200(state):
    """Returns 200 with valid CSV, correct headers, and one data row."""
    with _client(state, _USER_A) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/assessments")
    rows = _assert_csv_response(resp, ["date", "instrument", "scores", "total", "severity"], "assessments", _PATIENT_A_ID)
    assert len(rows) == 2, f"Expected header + 1 data row, got {len(rows)}: {rows}"
    assert rows[1][0] == "2025-01-15"
    assert rows[1][1] == "phq9"
    assert rows[1][3] == "5"
    assert rows[1][4] == "mild"


def test_export_assessments_no_auth(state):
    """Returns 401 when no auth token is provided."""
    with _client(state, None) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/assessments")
    assert resp.status_code == 401


def test_export_assessments_tenant_isolation(state):
    """User from org B cannot export org A patient — returns 404."""
    with _client(state, _USER_B) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/assessments")
    assert resp.status_code == 404


def test_export_assessments_patient_not_found(state):
    """Nonexistent patient returns 404."""
    with _client(state, _USER_A) as client:
        resp = client.get("/api/patients/no-such-patient/export/assessments")
    assert resp.status_code == 404


def test_export_assessments_empty(state):
    """Patient with no assessments returns header-only CSV."""
    with _client(state, _USER_B) as client:
        resp = client.get(f"/api/patients/{_PATIENT_B_ID}/export/assessments")
    rows = _assert_csv_response(resp, ["date", "instrument", "scores", "total", "severity"], "assessments", _PATIENT_B_ID)
    assert len(rows) == 1, f"Expected header-only CSV, got {len(rows)} rows"


# ===========================================================================
# Mood export
# ===========================================================================

def test_export_mood_200(state):
    """Returns 200 with valid CSV, correct headers, and one data row."""
    with _client(state, _USER_A) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/mood")
    rows = _assert_csv_response(resp, ["date", "score", "session_id"], "mood", _PATIENT_A_ID)
    assert len(rows) == 2, f"Expected header + 1 data row, got {len(rows)}"
    assert rows[1][0] == "2025-01-15"
    assert rows[1][1] == "7.5"        # mood_end preferred
    assert rows[1][2] == _SESSION_ID


def test_export_mood_no_auth(state):
    """Returns 401 when no auth token is provided."""
    with _client(state, None) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/mood")
    assert resp.status_code == 401


def test_export_mood_tenant_isolation(state):
    """User from org B cannot export org A patient mood — returns 404."""
    with _client(state, _USER_B) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/mood")
    assert resp.status_code == 404


def test_export_mood_empty(state):
    """Patient with no sessions (no mood data) returns header-only CSV."""
    with _client(state, _USER_B) as client:
        resp = client.get(f"/api/patients/{_PATIENT_B_ID}/export/mood")
    rows = _assert_csv_response(resp, ["date", "score", "session_id"], "mood", _PATIENT_B_ID)
    assert len(rows) == 1


# ===========================================================================
# Medications export
# ===========================================================================

def test_export_medications_200(state):
    """Returns 200 with valid CSV, correct headers, and one data row."""
    with _client(state, _USER_A) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/medications")
    rows = _assert_csv_response(resp, ["date", "medication", "status"], "medications", _PATIENT_A_ID)
    assert len(rows) == 2, f"Expected header + 1 data row, got {len(rows)}"
    assert rows[1][0] == "2025-01-10"
    assert rows[1][1] == "Sertraline 50mg"
    assert rows[1][2] == "active"


def test_export_medications_no_auth(state):
    """Returns 401 when no auth token is provided."""
    with _client(state, None) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/medications")
    assert resp.status_code == 401


def test_export_medications_tenant_isolation(state):
    """User from org B cannot export org A patient medications — returns 404."""
    with _client(state, _USER_B) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/medications")
    assert resp.status_code == 404


def test_export_medications_empty(state):
    """Patient with no medications returns header-only CSV."""
    with _client(state, _USER_B) as client:
        resp = client.get(f"/api/patients/{_PATIENT_B_ID}/export/medications")
    rows = _assert_csv_response(resp, ["date", "medication", "status"], "medications", _PATIENT_B_ID)
    assert len(rows) == 1


# ===========================================================================
# Sessions export
# ===========================================================================

def test_export_sessions_200(state):
    """Returns 200 with valid CSV, correct headers, and one data row."""
    with _client(state, _USER_A) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/sessions")
    rows = _assert_csv_response(resp, ["date", "duration", "mood_start", "mood_end", "summary_excerpt"], "sessions", _PATIENT_A_ID)
    assert len(rows) == 2, f"Expected header + 1 data row, got {len(rows)}"
    assert rows[1][0] == "2025-01-15"
    assert rows[1][1] == "50"           # 10:00-10:50 = 50 min
    assert rows[1][2] == "5.0"          # mood_start
    assert rows[1][3] == "7.5"          # mood_end
    assert "Good session" in rows[1][4] # summary excerpt


def test_export_sessions_no_auth(state):
    """Returns 401 when no auth token is provided."""
    with _client(state, None) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/sessions")
    assert resp.status_code == 401


def test_export_sessions_tenant_isolation(state):
    """User from org B cannot export org A patient sessions — returns 404."""
    with _client(state, _USER_B) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/sessions")
    assert resp.status_code == 404


def test_export_sessions_empty(state):
    """Patient with no sessions returns header-only CSV."""
    with _client(state, _USER_B) as client:
        resp = client.get(f"/api/patients/{_PATIENT_B_ID}/export/sessions")
    rows = _assert_csv_response(resp, ["date", "duration", "mood_start", "mood_end", "summary_excerpt"], "sessions", _PATIENT_B_ID)
    assert len(rows) == 1


def test_export_sessions_patient_not_found(state):
    """Nonexistent patient returns 404."""
    with _client(state, _USER_A) as client:
        resp = client.get("/api/patients/no-such-patient/export/sessions")
    assert resp.status_code == 404


# ===========================================================================
# Content-Disposition filename format
# ===========================================================================

def test_content_disposition_filename_assessments(state):
    """Filename follows pattern: assessments_{patient_id}_{date}.csv"""
    with _client(state, _USER_A) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/assessments")
    disposition = resp.headers.get("content-disposition", "")
    assert f"assessments_{_PATIENT_A_ID}_" in disposition
    assert ".csv" in disposition


def test_content_disposition_filename_sessions(state):
    """Filename follows pattern: sessions_{patient_id}_{date}.csv"""
    with _client(state, _USER_A) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/sessions")
    disposition = resp.headers.get("content-disposition", "")
    assert f"sessions_{_PATIENT_A_ID}_" in disposition
    assert ".csv" in disposition
