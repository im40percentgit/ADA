"""
Integration tests for the DailySummaryGenerator pipeline.

Uses real in-memory SQLite, real EventBus, and MockLLMProvider.queue_response()
to exercise the full path from SESSION_ENDED event to persisted daily summary
and caregiver overview API response.

@decision DEC-DAILY-005
@title Integration tests use real in-memory SQLite + real EventBus
@status accepted
@rationale Consistent with DEC-TEST-005 (session_summarizer, chat_flow).
    Real SQLite exercises the UPSERT constraint, the row deserializer, and
    the caregiver route query in one shot. No mocks cross module boundaries —
    MockLLMProvider is a real LLMProvider subclass, not a Mock object.

Coverage:
14. Full pipeline: SESSION_ENDED → debounce → daily summary in DB
15. GET /api/caregiver/overview includes daily_summary field
"""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

import pytest
import pytest_asyncio

from fastapi.testclient import TestClient

from ada.agents.daily_summary_generator import DailySummaryGenerator
from ada.agents.registry import AgentRegistry
from ada.api.app import create_app
from ada.api.auth import get_current_user
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import EventTypes, SessionEndedEvent
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from ada.llm.router import make_null_router
from ada.models.user import User

# Re-use MockLLMProvider from conftest via import
from tests.integration.conftest import MockLLMProvider

# ---------------------------------------------------------------------------
# Short debounce for tests
# ---------------------------------------------------------------------------

SHORT_DEBOUNCE = 0.1  # seconds


# ---------------------------------------------------------------------------
# Minimal null LLM for route tests
# ---------------------------------------------------------------------------

class _NullLLM(LLMProvider):
    async def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(content="", model="null", input_tokens=0, output_tokens=0)

    async def stream(self, messages, **kwargs):
        return
        yield


# ---------------------------------------------------------------------------
# Test 14: Full pipeline — SESSION_ENDED → debounce → summary in DB
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_pipeline_session_ended_to_db(state: StateManager, bus: EventBus):
    """SESSION_ENDED → debounce timer → LLM call → daily_summary in DB."""
    # Seed a patient
    patient_id = "patient-pipeline-001"
    await state.create_patient({
        "id": patient_id,
        "name": "Pipeline Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })

    # Seed a session and SOAP note so there's context for the summary
    session_id = str(uuid.uuid4())
    await state.create_session({"id": session_id, "patient_id": patient_id})
    await state.create_session_summary({
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "patient_id": patient_id,
        "subjective": "Felt anxious about work",
        "objective": "Spoke quickly, fidgeted",
        "assessment": "Mild anxiety",
        "plan": "Continue daily check-ins",
        "key_topics": ["anxiety", "work"],
        "risk_flags": [],
    })

    llm = MockLLMProvider()
    llm.queue_response(json.dumps({
        "narrative": "Today the patient seemed mildly anxious about work.",
        "trend_alerts": [],
        "appointment_prep": ["Discuss work stress with therapist"],
        "key_topics": ["anxiety", "work"],
        "overall_mood": "anxious",
    }))

    await bus.start()
    generator = DailySummaryGenerator(bus, state, llm, debounce_seconds=SHORT_DEBOUNCE)

    # Fire SESSION_ENDED
    await bus.publish(SessionEndedEvent(
        source="test",
        session_id=session_id,
        patient_id=patient_id,
    ))

    # Wait for debounce + generation
    await asyncio.sleep(SHORT_DEBOUNCE + 0.3)

    # Verify summary in DB
    summary = await state.get_latest_daily_summary(patient_id)
    assert summary is not None
    assert summary["patient_id"] == patient_id
    assert summary["narrative"] == "Today the patient seemed mildly anxious about work."
    assert summary["overall_mood"] == "anxious"
    assert "Discuss work stress with therapist" in summary["appointment_prep"]
    assert "anxiety" in summary["key_topics"]

    await generator.shutdown()
    await bus.stop()


# ---------------------------------------------------------------------------
# Test 15: GET /api/caregiver/overview includes daily_summary
# ---------------------------------------------------------------------------

_CAREGIVER_USER = User(
    id="cg-daily-001",
    email="caregiver-daily@example.com",
    role="caregiver",
    patient_id=None,
    created_at=datetime.utcnow(),
    is_active=True,
)


@contextmanager
def _make_client(
    state: StateManager,
    user: User = _CAREGIVER_USER,
) -> Generator[TestClient, None, None]:
    """Authenticated TestClient with real in-memory state."""
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


@pytest.mark.asyncio
async def test_caregiver_overview_includes_daily_summary():
    """GET /api/caregiver/overview returns daily_summary field."""
    # Fresh state for this test
    state = StateManager(":memory:")
    await state.initialize()

    patient_id = "pat-daily-001"
    await state.create_patient({
        "id": patient_id,
        "name": "Daily Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": "cg-daily-001",
    })

    # Persist a daily summary directly
    summary_id = str(uuid.uuid4())
    await state.create_or_update_daily_summary({
        "id": summary_id,
        "patient_id": patient_id,
        "summary_date": "2026-03-22",
        "narrative": "Patient had a stable day with mild anxiety.",
        "trend_alerts": ["PHQ-9 rising over 3 days"],
        "appointment_prep": ["Discuss sleep quality"],
        "key_topics": ["sleep", "anxiety"],
        "overall_mood": "stable",
    })

    with _make_client(state) as client:
        resp = client.get("/api/caregiver/overview")

    assert resp.status_code == 200
    data = resp.json()
    assert "daily_summary" in data
    ds = data["daily_summary"]
    assert ds is not None
    assert ds["narrative"] == "Patient had a stable day with mild anxiety."
    assert ds["overall_mood"] == "stable"
    assert ds["summary_date"] == "2026-03-22"
    assert "PHQ-9 rising over 3 days" in ds["trend_alerts"]
    assert "Discuss sleep quality" in ds["appointment_prep"]

    await state.close()


@pytest.mark.asyncio
async def test_caregiver_overview_daily_summary_null_when_none():
    """GET /api/caregiver/overview returns daily_summary: null when no summary exists."""
    state = StateManager(":memory:")
    await state.initialize()

    patient_id = "pat-daily-002"
    await state.create_patient({
        "id": patient_id,
        "name": "No-Summary Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": "cg-daily-001",
    })

    with _make_client(state) as client:
        resp = client.get("/api/caregiver/overview")

    assert resp.status_code == 200
    data = resp.json()
    assert "daily_summary" in data
    assert data["daily_summary"] is None

    await state.close()
