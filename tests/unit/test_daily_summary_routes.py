"""
Unit tests for GET /api/patients/{patient_id}/daily-summaries/{date}.

Uses a real in-memory SQLite database, FastAPI TestClient, and
dependency_overrides for auth bypass — no mocks of internal modules.

Coverage:
- 200 response when a matching summary exists
- 404 response when no summary exists for that patient+date
- Response includes all expected fields (narrative, trend_alerts,
  appointment_prep, key_topics, overall_mood, id, patient_id,
  summary_date, created_at)

@decision DEC-DAILY-SUMM-002
@title Daily summary route tests use real in-memory SQLite
@status accepted
@rationale Consistent with DEC-TEST-001 and all other route tests in this
    project. Real SQL is exercised without mocking StateManager internals,
    ensuring the UNIQUE(patient_id, summary_date) lookup path is verified.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

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
from ada.models.user import User


# ---------------------------------------------------------------------------
# Fake authenticated user
# ---------------------------------------------------------------------------

_TEST_USER = User(
    id="user-ds-001",
    email="clinician@example.com",
    role="clinician",
    patient_id=None,
    created_at=datetime.utcnow(),
    is_active=True,
)


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

from contextlib import contextmanager

@contextmanager
def _make_client(state: StateManager, user: User = _TEST_USER):
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router())
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PATIENT_ID = "pat-ds-001"
_SUMMARY_DATE = "2026-04-03"
_SUMMARY_ID = str(uuid.uuid4())

_SAMPLE_SUMMARY: dict[str, Any] = {
    "id": _SUMMARY_ID,
    "patient_id": _PATIENT_ID,
    "summary_date": _SUMMARY_DATE,
    "narrative": "Patient reported improved sleep and reduced anxiety.",
    "trend_alerts": ["phq9_score_increase"],
    "appointment_prep": ["Review medication schedule"],
    "key_topics": ["sleep", "anxiety"],
    "overall_mood": "improving",
}


@pytest_asyncio.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    await sm.create_patient({
        "id": _PATIENT_ID,
        "name": "Test Patient",
        "dob": "1990-01-01",
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    yield sm
    await sm.close()


@pytest_asyncio.fixture
async def state_with_summary(state: StateManager) -> StateManager:
    """StateManager pre-populated with one daily summary."""
    await state.create_or_update_daily_summary(_SAMPLE_SUMMARY)
    return state


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_daily_summary_found(state_with_summary: StateManager):
    """GET /api/patients/{id}/daily-summaries/{date} returns 200 when found."""
    with _make_client(state_with_summary) as client:
        resp = client.get(f"/api/patients/{_PATIENT_ID}/daily-summaries/{_SUMMARY_DATE}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == _SUMMARY_ID
        assert data["patient_id"] == _PATIENT_ID
        assert data["summary_date"] == _SUMMARY_DATE


@pytest.mark.asyncio
async def test_get_daily_summary_not_found(state: StateManager):
    """GET /api/patients/{id}/daily-summaries/{date} returns 404 when missing."""
    with _make_client(state) as client:
        resp = client.get(f"/api/patients/{_PATIENT_ID}/daily-summaries/1999-01-01")
        assert resp.status_code == 404
        assert "1999-01-01" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_daily_summary_all_fields(state_with_summary: StateManager):
    """Response includes all expected fields with correct types."""
    with _make_client(state_with_summary) as client:
        resp = client.get(f"/api/patients/{_PATIENT_ID}/daily-summaries/{_SUMMARY_DATE}")
        assert resp.status_code == 200
        data = resp.json()

        # Scalar fields
        assert data["narrative"] == _SAMPLE_SUMMARY["narrative"]
        assert data["overall_mood"] == _SAMPLE_SUMMARY["overall_mood"]
        assert data["created_at"] is not None

        # JSON-decoded list fields
        assert isinstance(data["trend_alerts"], list)
        assert data["trend_alerts"] == _SAMPLE_SUMMARY["trend_alerts"]

        assert isinstance(data["appointment_prep"], list)
        assert data["appointment_prep"] == _SAMPLE_SUMMARY["appointment_prep"]

        assert isinstance(data["key_topics"], list)
        assert data["key_topics"] == _SAMPLE_SUMMARY["key_topics"]
