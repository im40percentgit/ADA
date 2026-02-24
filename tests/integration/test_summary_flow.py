"""
Integration tests for the Session Summarizer end-to-end flow.

Tests the full pipeline:
  SESSION_ENDED published → SessionSummarizer processes → SOAP note in DB
  → SESSION_SUMMARIZED event published → REST endpoint returns the note

Uses real EventBus, real in-memory SQLite, MockLLMProvider from conftest,
and FastAPI TestClient with dependency_overrides for auth bypass.

@decision DEC-SUMMARY-006
@title Integration tests exercise full event → DB → REST pipeline
@status accepted
@rationale Unit tests verify the summarizer logic in isolation. Integration
    tests verify the wiring: EventBus dispatch triggers the handler, the DB
    record is readable via the REST endpoint, and the SESSION_SUMMARIZED event
    carries the correct summary_id. This catches wiring bugs that unit tests
    with direct method calls would miss.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

import pytest
import pytest_asyncio

from fastapi.testclient import TestClient

from ada.agents.registry import AgentRegistry
from ada.agents.session_summarizer import SessionSummarizer
from ada.api.app import create_app
from ada.api.auth import get_current_user
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import EventTypes, SessionEndedEvent, SessionSummarizedEvent
from ada.core.state import StateManager
from ada.models.user import User

# Re-use MockLLMProvider from integration conftest
from tests.integration.conftest import MockLLMProvider


_FAKE_USER = User(
    id="user-summary-001",
    email="clinician@test.com",
    role="clinician",
    patient_id=None,
    created_at=datetime.utcnow(),
    is_active=True,
)

_SOAP_JSON = json.dumps({
    "subjective": "Patient reports persistent low mood for two weeks.",
    "objective": "Patient maintained eye contact; spoke in measured pace.",
    "assessment": "Mild depressive episode with good insight.",
    "plan": "Continue weekly CBT; introduce behavioural activation homework.",
    "key_topics": ["low mood", "sleep", "motivation"],
    "risk_flags": [],
})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    await sm.create_patient({
        "id": "pat-sum-001",
        "name": "Summary Integration Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    await sm.create_session({
        "id": "sess-sum-001",
        "patient_id": "pat-sum-001",
    })
    yield sm
    await sm.close()


@pytest_asyncio.fixture
async def bus() -> EventBus:
    b = EventBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
def llm() -> MockLLMProvider:
    return MockLLMProvider(canned_response=_SOAP_JSON)


@contextmanager
def _make_client(
    state: StateManager,
    bus: EventBus,
    llm: MockLLMProvider,
) -> Generator[TestClient, None, None]:
    """Authenticated TestClient wired with a real SessionSummarizer."""
    config = AdaConfig()
    registry = AgentRegistry(bus, config, state, llm)
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestSummaryFlow:

    @pytest.mark.asyncio
    async def test_session_ended_triggers_summarizer(self, state, bus, llm):
        """SESSION_ENDED published on bus → summarizer persists SOAP note."""
        # Seed a message so the summarizer has content to process
        await state.save_message({
            "id": "msg-int-001",
            "session_id": "sess-sum-001",
            "role": "user",
            "content": "I have been feeling low for two weeks.",
        })

        summarizer = SessionSummarizer(bus, state, llm)

        published_events: list[SessionSummarizedEvent] = []
        bus.subscribe(
            EventTypes.SESSION_SUMMARIZED,
            lambda e: published_events.append(e),
            "test_collector",
        )

        # Publish SESSION_ENDED
        await bus.publish(SessionEndedEvent(
            session_id="sess-sum-001",
            patient_id="pat-sum-001",
        ))

        # Allow event loop to process
        await asyncio.sleep(0.05)

        # SOAP note persisted
        summary = await state.get_session_summary("sess-sum-001")
        assert summary is not None
        assert summary["session_id"] == "sess-sum-001"
        assert summary["patient_id"] == "pat-sum-001"
        assert "low mood" in summary["key_topics"]
        assert summary["risk_flags"] == []

        # SESSION_SUMMARIZED published with matching IDs
        assert len(published_events) == 1
        evt = published_events[0]
        assert evt.session_id == "sess-sum-001"
        assert evt.patient_id == "pat-sum-001"
        assert evt.summary_id == summary["id"]

    @pytest.mark.asyncio
    async def test_rest_endpoint_returns_summary(self, state, bus, llm):
        """After summarizer runs, GET /sessions/{id}/summary returns the note."""
        await state.save_message({
            "id": "msg-int-002",
            "session_id": "sess-sum-001",
            "role": "user",
            "content": "Sleep has been poor.",
        })

        summarizer = SessionSummarizer(bus, state, llm)

        await bus.publish(SessionEndedEvent(
            session_id="sess-sum-001",
            patient_id="pat-sum-001",
        ))
        await asyncio.sleep(0.05)

        with _make_client(state, bus, llm) as client:
            resp = client.get("/api/sessions/sess-sum-001/summary")

        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "sess-sum-001"
        assert data["patient_id"] == "pat-sum-001"
        assert data["subjective"] == "Patient reports persistent low mood for two weeks."
        assert data["objective"] == "Patient maintained eye contact; spoke in measured pace."
        assert data["assessment"] == "Mild depressive episode with good insight."
        assert data["plan"] == "Continue weekly CBT; introduce behavioural activation homework."
        assert data["key_topics"] == ["low mood", "sleep", "motivation"]
        assert data["risk_flags"] == []

    @pytest.mark.asyncio
    async def test_rest_endpoint_404_before_summary(self, state, bus, llm):
        """GET /sessions/{id}/summary returns 404 before the summarizer has run."""
        with _make_client(state, bus, llm) as client:
            resp = client.get("/api/sessions/sess-sum-001/summary")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_rest_endpoint_404_unknown_session(self, state, bus, llm):
        """GET /sessions/{id}/summary returns 404 for a completely unknown session."""
        with _make_client(state, bus, llm) as client:
            resp = client.get("/api/sessions/nonexistent-session/summary")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_rest_endpoint_requires_auth(self, state, bus, llm):
        """GET /sessions/{id}/summary without auth returns 401/403."""
        config = AdaConfig()
        registry = AgentRegistry(bus, config, state, llm)
        app = create_app(config, bus, state, registry)
        # No dependency_overrides — real auth enforced
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/sessions/sess-sum-001/summary")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_no_messages_no_summary(self, state, bus, llm):
        """SESSION_ENDED with no messages → no summary, 404 from REST."""
        # Do not seed any messages
        summarizer = SessionSummarizer(bus, state, llm)

        await bus.publish(SessionEndedEvent(
            session_id="sess-sum-001",
            patient_id="pat-sum-001",
        ))
        await asyncio.sleep(0.05)

        # LLM never called
        assert len(llm.calls) == 0

        # No DB record
        assert await state.get_session_summary("sess-sum-001") is None

    @pytest.mark.asyncio
    async def test_summary_id_in_event_matches_db(self, state, bus, llm):
        """The summary_id in SESSION_SUMMARIZED must match the DB record's id."""
        await state.save_message({
            "id": "msg-int-003",
            "session_id": "sess-sum-001",
            "role": "assistant",
            "content": "How have you been sleeping?",
        })

        summarizer = SessionSummarizer(bus, state, llm)
        captured: list = []
        bus.subscribe(
            EventTypes.SESSION_SUMMARIZED,
            lambda e: captured.append(e),
            "id_checker",
        )

        await bus.publish(SessionEndedEvent(
            session_id="sess-sum-001",
            patient_id="pat-sum-001",
        ))
        await asyncio.sleep(0.05)

        db_record = await state.get_session_summary("sess-sum-001")
        assert db_record is not None
        assert len(captured) == 1
        assert captured[0].summary_id == db_record["id"]
