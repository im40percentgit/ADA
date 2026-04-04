"""
Unit tests for cognitive screening interaction REST endpoints.

  POST /api/patients/{patient_id}/screenings/start
  POST /api/screenings/{screening_id}/respond

Uses real in-memory SQLite, real FastAPI TestClient, and a real EventBus with
a subscriber that captures published events — no mocks of internal code.

Auth is bypassed via dependency_overrides (consistent with
test_alert_routes.py and test_appointment_routes.py).

@decision DEC-SCREEN-INTERACT-002
@title Screening route tests use real EventBus subscriber for event capture
@status accepted
@rationale Sacred Practice #5 forbids internal mocks. A real EventBus
    subscriber that appends to a list is equivalent in correctness to a mock
    while staying within the no-mocks rule. State uses real in-memory SQLite.
"""

from __future__ import annotations

import asyncio
import uuid
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
from ada.core.events import (
    AssessmentTriggeredEvent,
    CognitiveTaskResponseEvent,
    EventTypes,
)
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from ada.llm.router import make_null_router
from ada.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _NullLLM(LLMProvider):
    async def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(content="", model="null", input_tokens=0, output_tokens=0)

    async def stream(self, messages, **kwargs):
        return
        yield


_FAKE_USER = User(
    id="user-screen-001",
    email="clinician@example.com",
    role="clinician",
    patient_id=None,
    created_at=datetime.utcnow(),
    is_active=True,
)

PATIENT_ID = "pat-screen-001"


def _make_capturing_bus() -> tuple[EventBus, list[Any]]:
    """
    Return a real EventBus pre-wired with a subscriber that appends every
    published event to a shared list.

    Implementation note: EventBus.publish() puts items into subscriber queues
    synchronously (queue.put_nowait). The handler coroutines only run when
    the bus worker loop is active (bus.start()). TestClient runs sync, so
    after each request we drain the queues via _drain_bus() rather than
    starting the full worker loop.
    """
    bus = EventBus()
    captured: list[Any] = []

    async def _capture(event: Any) -> None:
        captured.append(event)

    # Subscribe to both event types the routes publish
    bus.subscribe(EventTypes.ASSESSMENT_TRIGGERED, _capture, "test_capture_assessment")
    bus.subscribe(EventTypes.COGNITIVE_TASK_RESPONSE, _capture, "test_capture_cognitive")

    return bus, captured


def _drain_bus(bus: EventBus) -> None:
    """
    Drain all subscriber queues by running the event loop briefly.

    TestClient uses the sync interface, so published events sit in queues
    until we explicitly process them. We start the bus, yield control so
    all queued events are dispatched, then stop.
    """
    async def _run():
        await bus.start()
        await asyncio.sleep(0)   # yield to let _process_queue tasks fire
        await bus.stop()

    asyncio.get_event_loop().run_until_complete(_run())


@contextmanager
def _make_client(
    state: StateManager,
    bus: EventBus,
) -> Generator[TestClient, None, None]:
    config = AdaConfig()
    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    await sm.create_patient({
        "id": PATIENT_ID,
        "name": "Screen Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    yield sm
    await sm.close()


# ---------------------------------------------------------------------------
# POST /api/patients/{patient_id}/screenings/start
# ---------------------------------------------------------------------------


class TestStartScreening:

    def test_returns_screening_id(self, state):
        """Start endpoint returns a UUID screening_id."""
        bus, _ = _make_capturing_bus()
        with _make_client(state, bus) as client:
            resp = client.post(f"/api/patients/{PATIENT_ID}/screenings/start")

        assert resp.status_code == 201
        data = resp.json()
        assert "screening_id" in data
        # Must be a valid UUID
        uuid.UUID(data["screening_id"])

    def test_creates_state_record(self, state):
        """Start endpoint creates a cognitive_screenings row in the DB."""
        bus, _ = _make_capturing_bus()
        with _make_client(state, bus) as client:
            resp = client.post(f"/api/patients/{PATIENT_ID}/screenings/start")

        screening_id = resp.json()["screening_id"]
        record = asyncio.get_event_loop().run_until_complete(
            state.get_cognitive_screening(screening_id)
        )
        assert record is not None
        assert record["patient_id"] == PATIENT_ID
        assert record["status"] == "in_progress"

    def test_publishes_assessment_triggered_event(self, state):
        """Start endpoint publishes AssessmentTriggeredEvent(instrument='cognitive')."""
        bus, captured = _make_capturing_bus()
        with _make_client(state, bus) as client:
            resp = client.post(f"/api/patients/{PATIENT_ID}/screenings/start")

        assert resp.status_code == 201
        screening_id = resp.json()["screening_id"]

        # Drain subscriber queues so handlers run and populate `captured`
        _drain_bus(bus)

        assert len(captured) == 1
        event = captured[0]
        assert isinstance(event, AssessmentTriggeredEvent)
        assert event.instrument == "cognitive"
        assert event.patient_id == PATIENT_ID
        assert event.metadata.get("screening_id") == screening_id

    def test_unknown_patient_returns_404(self, state):
        """Start endpoint returns 404 for non-existent patient."""
        bus, _ = _make_capturing_bus()
        with _make_client(state, bus) as client:
            resp = client.post("/api/patients/nonexistent-patient/screenings/start")

        assert resp.status_code == 404
        assert "Patient not found" in resp.json()["detail"]

    def test_no_event_published_on_404(self, state):
        """No event is published when the patient does not exist."""
        bus, captured = _make_capturing_bus()
        with _make_client(state, bus) as client:
            client.post("/api/patients/nonexistent-patient/screenings/start")

        assert len(captured) == 0


# ---------------------------------------------------------------------------
# POST /api/screenings/{screening_id}/respond
# ---------------------------------------------------------------------------


class TestRespondToTask:

    def _create_screening(self, state: StateManager) -> str:
        """Helper: insert an in-progress screening and return its ID."""
        sid = str(uuid.uuid4())
        asyncio.get_event_loop().run_until_complete(
            state.create_cognitive_screening({
                "id": sid,
                "patient_id": PATIENT_ID,
            })
        )
        return sid

    def test_respond_returns_200(self, state):
        """Respond endpoint returns 200 with accepted status."""
        bus, _ = _make_capturing_bus()
        sid = self._create_screening(state)

        with _make_client(state, bus) as client:
            resp = client.post(
                f"/api/screenings/{sid}/respond",
                json={"task_index": 0, "response": "blue"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    def test_publishes_task_response_event(self, state):
        """Respond endpoint publishes CognitiveTaskResponseEvent with correct fields."""
        bus, captured = _make_capturing_bus()
        sid = self._create_screening(state)

        with _make_client(state, bus) as client:
            client.post(
                f"/api/screenings/{sid}/respond",
                json={"task_index": 2, "response": {"answer": "triangle", "count": 3}},
            )

        # Drain subscriber queues so handlers run and populate `captured`
        _drain_bus(bus)

        assert len(captured) == 1
        event = captured[0]
        assert isinstance(event, CognitiveTaskResponseEvent)
        assert event.screening_id == sid
        assert event.task_index == 2
        assert event.response == {"answer": "triangle", "count": 3}
        assert event.patient_id == PATIENT_ID

    def test_respond_string_response(self, state):
        """Respond endpoint accepts plain string responses."""
        bus, _ = _make_capturing_bus()
        sid = self._create_screening(state)

        with _make_client(state, bus) as client:
            resp = client.post(
                f"/api/screenings/{sid}/respond",
                json={"task_index": 1, "response": "apple banana cherry"},
            )

        assert resp.status_code == 200

    def test_respond_unknown_screening_returns_404(self, state):
        """Respond endpoint returns 404 for non-existent screening."""
        bus, _ = _make_capturing_bus()
        with _make_client(state, bus) as client:
            resp = client.post(
                "/api/screenings/nonexistent-screening-id/respond",
                json={"task_index": 0, "response": "anything"},
            )

        assert resp.status_code == 404
        assert "Cognitive screening not found" in resp.json()["detail"]

    def test_respond_missing_task_index_returns_422(self, state):
        """Respond endpoint returns 422 if task_index is absent."""
        bus, _ = _make_capturing_bus()
        sid = self._create_screening(state)

        with _make_client(state, bus) as client:
            resp = client.post(
                f"/api/screenings/{sid}/respond",
                json={"response": "some answer"},
            )

        assert resp.status_code == 422

    def test_respond_missing_response_returns_422(self, state):
        """Respond endpoint returns 422 if response field is absent."""
        bus, _ = _make_capturing_bus()
        sid = self._create_screening(state)

        with _make_client(state, bus) as client:
            resp = client.post(
                f"/api/screenings/{sid}/respond",
                json={"task_index": 0},
            )

        assert resp.status_code == 422
