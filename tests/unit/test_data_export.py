"""
Unit tests for CSV data export endpoints (Phase 14c, Task 1 + T1b).

Tests use a real in-memory SQLite StateManager and FastAPI TestClient with
dependency_overrides to inject authenticated users without real JWTs —
the same pattern as test_organization_routes.py and test_treatment_plans.py.

Coverage:
  GET /api/patients/{id}/export/assessments
  GET /api/patients/{id}/export/mood
  GET /api/patients/{id}/export/medications  (adherence logs, not medication list)
  GET /api/patients/{id}/export/sessions
  GET /api/patients/{id}/export/wellbeing    (WHO-5 assessments only)

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
_WHO5_ASSESSMENT_ID = "assessment-who5-001"
_MED_LOG_ID_1 = "medlog-001"
_MED_LOG_ID_2 = "medlog-002"


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
      - patient A in org A with:
          - 1 session (with mood data)
          - 1 PHQ-9 assessment
          - 1 WHO-5 assessment
          - 1 medication with 2 adherence log entries
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

    # Users — set organization_id so require_patient_access org-match path works.
    # User A belongs to org A, user B to org B. Patient A is in org A, patient B
    # in org B — so the org-based check grants same-org access and denies cross-org.
    await sm.create_user({"id": _USER_A_ID, "email": _USER_A_EMAIL, "hashed_password": "x", "role": "user", "created_at": now})
    await sm.create_user({"id": _USER_B_ID, "email": _USER_B_EMAIL, "hashed_password": "x", "role": "user", "created_at": now})
    await sm._exec("UPDATE users SET organization_id = ? WHERE id = ?", (_ORG_A_ID, _USER_A_ID))
    await sm._exec("UPDATE users SET organization_id = ? WHERE id = ?", (_ORG_B_ID, _USER_B_ID))

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

    # WHO-5 assessment for patient A (separate from the PHQ-9 above)
    await sm.save_assessment({
        "id": _WHO5_ASSESSMENT_ID, "patient_id": _PATIENT_A_ID,
        "instrument": "who5", "item_scores": [3, 2, 3, 2, 3],
        "total_score": 52, "severity": "below_threshold", "timestamp": "2025-01-20T14:00:00",
    })

    # Medication for patient A
    await sm.create_medication({
        "id": _MEDICATION_ID, "patient_id": _PATIENT_A_ID,
        "name": "Sertraline 50mg", "active": 1,
        "created_at": "2025-01-10T09:00:00", "updated_at": "2025-01-10T09:00:00",
    })

    # Adherence logs for the medication (two entries: taken then skipped)
    await sm.create_medication_log({
        "id": _MED_LOG_ID_1, "medication_id": _MEDICATION_ID, "patient_id": _PATIENT_A_ID,
        "taken_at": "2025-01-15T08:00:00", "status": "taken",
        "created_at": "2025-01-15T08:00:00",
    })
    await sm.create_medication_log({
        "id": _MED_LOG_ID_2, "medication_id": _MEDICATION_ID, "patient_id": _PATIENT_A_ID,
        "taken_at": "2025-01-14T08:00:00", "status": "skipped",
        "created_at": "2025-01-14T08:00:00",
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
    """Returns 200 with valid CSV, correct headers, and one row per assessment.

    Fixture seeds 2 assessments for patient A: a WHO-5 (2025-01-20) and a
    PHQ-9 (2025-01-15). Both appear in the all-instruments export, newest first.
    """
    with _client(state, _USER_A) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/assessments")
    rows = _assert_csv_response(resp, ["date", "instrument", "scores", "total", "severity"], "assessments", _PATIENT_A_ID)
    assert len(rows) == 3, f"Expected header + 2 data rows, got {len(rows)}: {rows}"
    # Newest first: WHO-5 at row 1, PHQ-9 at row 2
    assert rows[1][0] == "2025-01-20"
    assert rows[1][1] == "who5"
    assert rows[2][0] == "2025-01-15"
    assert rows[2][1] == "phq9"
    assert rows[2][3] == "5"
    assert rows[2][4] == "mild"


def test_export_assessments_no_auth(state):
    """Returns 401 when no auth token is provided."""
    with _client(state, None) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/assessments")
    assert resp.status_code == 401


def test_export_assessments_tenant_isolation(state):
    """User from org B cannot export org A patient — returns 403.

    require_patient_access now runs before _resolve_patient, so cross-org
    access is denied with 403 (not 404) to avoid leaking patient existence.
    """
    with _client(state, _USER_B) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/assessments")
    assert resp.status_code == 403


def test_export_assessments_patient_not_found(state):
    """Accessing a nonexistent patient returns 403 (authz runs before existence check)."""
    with _client(state, _USER_A) as client:
        resp = client.get("/api/patients/no-such-patient/export/assessments")
    assert resp.status_code == 403


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
    """User from org B cannot export org A patient mood — returns 403."""
    with _client(state, _USER_B) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/mood")
    assert resp.status_code == 403


def test_export_mood_empty(state):
    """Patient with no sessions (no mood data) returns header-only CSV."""
    with _client(state, _USER_B) as client:
        resp = client.get(f"/api/patients/{_PATIENT_B_ID}/export/mood")
    rows = _assert_csv_response(resp, ["date", "score", "session_id"], "mood", _PATIENT_B_ID)
    assert len(rows) == 1


# ===========================================================================
# Medications export  (adherence logs — one row per log event)
# ===========================================================================

def test_export_medications_200(state):
    """Returns 200 with valid CSV, correct headers, and one row per adherence log.

    Fixture seeds 2 logs for Sertraline 50mg (taken 2025-01-15, skipped 2025-01-14).
    Rows should arrive newest-first: taken row before skipped row.
    """
    with _client(state, _USER_A) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/medications")
    rows = _assert_csv_response(resp, ["date", "medication", "status"], "medications", _PATIENT_A_ID)
    assert len(rows) == 3, f"Expected header + 2 log rows, got {len(rows)}: {rows}"
    # Newest first (2025-01-15 taken)
    assert rows[1][0] == "2025-01-15T08:00:00"
    assert rows[1][1] == "Sertraline 50mg"
    assert rows[1][2] == "taken"
    # Older entry (2025-01-14 skipped)
    assert rows[2][0] == "2025-01-14T08:00:00"
    assert rows[2][1] == "Sertraline 50mg"
    assert rows[2][2] == "skipped"


def test_export_medications_no_auth(state):
    """Returns 401 when no auth token is provided."""
    with _client(state, None) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/medications")
    assert resp.status_code == 401


def test_export_medications_tenant_isolation(state):
    """User from org B cannot export org A patient medications — returns 403."""
    with _client(state, _USER_B) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/medications")
    assert resp.status_code == 403


def test_export_medications_no_logs(state):
    """Patient with medications but no adherence logs returns header-only CSV.

    Patient B has no medications at all, so no logs either.
    """
    with _client(state, _USER_B) as client:
        resp = client.get(f"/api/patients/{_PATIENT_B_ID}/export/medications")
    rows = _assert_csv_response(resp, ["date", "medication", "status"], "medications", _PATIENT_B_ID)
    assert len(rows) == 1, f"Expected header-only CSV, got {len(rows)} rows"


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
    """User from org B cannot export org A patient sessions — returns 403."""
    with _client(state, _USER_B) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/sessions")
    assert resp.status_code == 403


def test_export_sessions_empty(state):
    """Patient with no sessions returns header-only CSV."""
    with _client(state, _USER_B) as client:
        resp = client.get(f"/api/patients/{_PATIENT_B_ID}/export/sessions")
    rows = _assert_csv_response(resp, ["date", "duration", "mood_start", "mood_end", "summary_excerpt"], "sessions", _PATIENT_B_ID)
    assert len(rows) == 1


def test_export_sessions_patient_not_found(state):
    """Accessing a nonexistent patient returns 403 (authz runs before existence check)."""
    with _client(state, _USER_A) as client:
        resp = client.get("/api/patients/no-such-patient/export/sessions")
    assert resp.status_code == 403


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


# ===========================================================================
# Wellbeing export  (WHO-5 assessments only)
# ===========================================================================

def test_export_wellbeing_200(state):
    """Returns 200 with valid CSV, correct headers, and one WHO-5 row."""
    with _client(state, _USER_A) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/wellbeing")
    rows = _assert_csv_response(resp, ["date", "score", "severity"], "wellbeing", _PATIENT_A_ID)
    assert len(rows) == 2, f"Expected header + 1 data row, got {len(rows)}: {rows}"
    assert rows[1][0] == "2025-01-20"
    assert rows[1][1] == "52"
    assert rows[1][2] == "below_threshold"


def test_export_wellbeing_no_auth(state):
    """Returns 401 when no auth token is provided."""
    with _client(state, None) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/wellbeing")
    assert resp.status_code == 401


def test_export_wellbeing_tenant_isolation(state):
    """User from org B cannot export org A patient wellbeing — returns 403."""
    with _client(state, _USER_B) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/wellbeing")
    assert resp.status_code == 403


def test_export_wellbeing_patient_not_found(state):
    """Accessing a nonexistent patient returns 403 (authz runs before existence check)."""
    with _client(state, _USER_A) as client:
        resp = client.get("/api/patients/no-such-patient/export/wellbeing")
    assert resp.status_code == 403


def test_export_wellbeing_empty(state):
    """Patient with no WHO-5 assessments returns header-only CSV."""
    with _client(state, _USER_B) as client:
        resp = client.get(f"/api/patients/{_PATIENT_B_ID}/export/wellbeing")
    rows = _assert_csv_response(resp, ["date", "score", "severity"], "wellbeing", _PATIENT_B_ID)
    assert len(rows) == 1, f"Expected header-only CSV, got {len(rows)} rows"


def test_export_wellbeing_filters_non_who5(state):
    """Only WHO-5 assessments appear — PHQ-9 row from same patient is excluded.

    Fixture seeds one PHQ-9 (assessment-001) and one WHO-5 (assessment-who5-001)
    for patient A. Wellbeing export must return only the WHO-5 row.
    """
    with _client(state, _USER_A) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/wellbeing")
    rows = _assert_csv_response(resp, ["date", "score", "severity"], "wellbeing", _PATIENT_A_ID)
    assert len(rows) == 2, f"Expected header + 1 WHO-5 row only, got {len(rows)}: {rows}"
    assert rows[1][0] == "2025-01-20"   # WHO-5 date, not PHQ-9 date (2025-01-15)


def test_export_wellbeing_filename_format(state):
    """Filename follows pattern: wellbeing_{patient_id}_{date}.csv"""
    with _client(state, _USER_A) as client:
        resp = client.get(f"/api/patients/{_PATIENT_A_ID}/export/wellbeing")
    disposition = resp.headers.get("content-disposition", "")
    assert f"wellbeing_{_PATIENT_A_ID}_" in disposition
    assert ".csv" in disposition
