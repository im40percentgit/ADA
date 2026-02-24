"""
Integration tests for the full emotion analysis flow.

Exercises: MESSAGE_RECEIVED → EmotionAnalyzerAgent → EmotionAnalyzedEvent + DB persistence.

Uses real EventBus, real in-memory SQLite, and MockLLMProvider (per DEC-TEST-005).

@decision DEC-EMOTION-005
@title Integration test covers full event flow and DB persistence end-to-end
@status accepted
@rationale The integration test verifies that EmotionAnalyzerAgent correctly
    wires into the EventBus, produces EmotionAnalyzedEvent with accurate field
    values, and persists the record to emotion_analyses via StateManager. This
    exercises paths that unit tests cannot — specifically the bus dispatch loop,
    the agent initialize/start/stop lifecycle, and FK-constrained DB writes.
"""

from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio

from ada.agents.emotion_analyzer import EmotionAnalyzerAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import EmotionAnalyzedEvent, EventTypes, MessageReceivedEvent
from ada.core.state import StateManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
# Note: state, bus, llm, config, patient_id, session_id fixtures are provided
# by tests/integration/conftest.py and injected automatically by pytest.

@pytest_asyncio.fixture
async def emotion_patient_id(state: StateManager) -> str:
    pid = "patient-integ-emotion-001"
    await state.create_patient({
        "id": pid,
        "name": "Emotion Integration Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    return pid


@pytest_asyncio.fixture
async def emotion_session_id(state: StateManager, emotion_patient_id: str) -> str:
    sid = "session-integ-emotion-001"
    await state.create_session({"id": sid, "patient_id": emotion_patient_id})
    return sid


@pytest_asyncio.fixture
async def wired(state: StateManager, llm, config, emotion_patient_id: str, emotion_session_id: str):
    """Fully wired EmotionAnalyzerAgent stack."""
    bus = EventBus()
    await bus.start()
    agent = EmotionAnalyzerAgent()
    agent.initialize(bus, config, state, llm)
    await agent.start()
    yield agent, bus, llm, state, emotion_patient_id, emotion_session_id
    await agent.stop()
    await bus.stop()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _emotion_json(
    primary: str = "sadness",
    secondary: str | None = None,
    intensity: float = 0.7,
    valence: float = -0.6,
    arousal: float = 0.4,
    confidence: float = 0.85,
) -> str:
    return json.dumps({
        "primary_emotion": primary,
        "secondary_emotion": secondary,
        "intensity": intensity,
        "valence": valence,
        "arousal": arousal,
        "confidence": confidence,
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEmotionFlow:
    @pytest.mark.asyncio
    async def test_full_flow_event_published(self, wired):
        """MESSAGE_RECEIVED triggers EMOTION_ANALYZED with correct fields."""
        agent, bus, llm, state, patient_id, session_id = wired
        llm.queue_response(_emotion_json(primary="sadness", valence=-0.6))

        received: list[EmotionAnalyzedEvent] = []
        bus.subscribe(EventTypes.EMOTION_ANALYZED, lambda e: received.append(e), "integ-collector")

        await bus.publish(MessageReceivedEvent(
            source="test",
            session_id=session_id,
            patient_id=patient_id,
            message_id="msg-integ-001",
            content="I've been feeling really down this week.",
        ))

        await asyncio.sleep(0.1)

        assert len(received) == 1
        evt = received[0]
        assert isinstance(evt, EmotionAnalyzedEvent)
        assert evt.event_type == EventTypes.EMOTION_ANALYZED
        assert evt.session_id == session_id
        assert evt.patient_id == patient_id
        assert evt.message_id == "msg-integ-001"
        assert evt.primary_emotion == "sadness"
        assert evt.valence == pytest.approx(-0.6)

    @pytest.mark.asyncio
    async def test_full_flow_db_persistence(self, wired):
        """Emotion analysis is persisted to emotion_analyses table."""
        agent, bus, llm, state, patient_id, session_id = wired
        llm.queue_response(_emotion_json(primary="anger", intensity=0.9, arousal=0.8))

        await bus.publish(MessageReceivedEvent(
            source="test",
            session_id=session_id,
            patient_id=patient_id,
            message_id="msg-integ-002",
            content="I'm furious about what they did to me.",
        ))

        await asyncio.sleep(0.1)

        rows = await state.get_emotion_analyses(session_id)
        assert len(rows) == 1
        row = rows[0]
        assert row["primary_emotion"] == "anger"
        assert row["intensity"] == pytest.approx(0.9)
        assert row["arousal"] == pytest.approx(0.8)
        assert row["session_id"] == session_id
        assert row["patient_id"] == patient_id
        assert row["message_id"] == "msg-integ-002"

    @pytest.mark.asyncio
    async def test_multiple_messages_accumulate(self, wired):
        """Multiple messages each produce a separate emotion analysis."""
        agent, bus, llm, state, patient_id, session_id = wired

        messages = [
            ("msg-integ-003", "I feel happy today.", _emotion_json(primary="joy", valence=0.8)),
            ("msg-integ-004", "But also a bit scared.", _emotion_json(primary="fear", valence=-0.3)),
            ("msg-integ-005", "And surprised by everything.", _emotion_json(primary="surprise", valence=0.2)),
        ]

        for msg_id, content, response in messages:
            llm.queue_response(response)
            await bus.publish(MessageReceivedEvent(
                source="test",
                session_id=session_id,
                patient_id=patient_id,
                message_id=msg_id,
                content=content,
            ))

        await asyncio.sleep(0.2)

        rows = await state.get_emotion_analyses(session_id)
        assert len(rows) == 3
        emotions = [r["primary_emotion"] for r in rows]
        assert "joy" in emotions
        assert "fear" in emotions
        assert "surprise" in emotions

    @pytest.mark.asyncio
    async def test_secondary_emotion_persisted(self, wired):
        """Secondary emotion is correctly stored and retrieved."""
        agent, bus, llm, state, patient_id, session_id = wired
        llm.queue_response(_emotion_json(primary="trust", secondary="anticipation"))

        await bus.publish(MessageReceivedEvent(
            source="test",
            session_id=session_id,
            patient_id=patient_id,
            message_id="msg-integ-006",
            content="I'm looking forward to working with my therapist.",
        ))

        await asyncio.sleep(0.1)

        rows = await state.get_emotion_analyses(session_id)
        assert len(rows) == 1
        assert rows[0]["primary_emotion"] == "trust"
        assert rows[0]["secondary_emotion"] == "anticipation"

    @pytest.mark.asyncio
    async def test_bad_llm_response_no_persistence(self, wired):
        """Malformed LLM response produces no event and no DB row."""
        agent, bus, llm, state, patient_id, session_id = wired
        llm.queue_response("I cannot analyse that right now.")

        received: list = []
        bus.subscribe(EventTypes.EMOTION_ANALYZED, lambda e: received.append(e), "bad-integ")

        await bus.publish(MessageReceivedEvent(
            source="test",
            session_id=session_id,
            patient_id=patient_id,
            message_id="msg-integ-007",
            content="Something happened.",
        ))

        await asyncio.sleep(0.1)

        assert received == []
        rows = await state.get_emotion_analyses(session_id)
        assert rows == []

    @pytest.mark.asyncio
    async def test_event_source_is_agent_name(self, wired):
        """Published event source field is 'emotion_analyzer'."""
        agent, bus, llm, state, patient_id, session_id = wired
        llm.queue_response(_emotion_json())

        received: list[EmotionAnalyzedEvent] = []
        bus.subscribe(EventTypes.EMOTION_ANALYZED, lambda e: received.append(e), "source-test")

        await bus.publish(MessageReceivedEvent(
            source="test",
            session_id=session_id,
            patient_id=patient_id,
            message_id="msg-integ-008",
            content="Testing source field.",
        ))

        await asyncio.sleep(0.1)

        assert len(received) == 1
        assert received[0].source == "emotion_analyzer"
