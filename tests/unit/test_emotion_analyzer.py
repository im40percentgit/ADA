"""
Unit tests for EmotionAnalyzerAgent, EmotionResult, EmotionDimensions,
and the emotion_analyses StateManager CRUD.

Tests follow Sacred Practice #5 — real in-memory SQLite, real EventBus,
MockLLMProvider with canned JSON responses. No internal mocks.

@decision DEC-EMOTION-004
@title Unit tests use real in-memory SQLite and real EventBus (no internal mocks)
@status accepted
@rationale Consistent with Sacred Practice #5 and DEC-TEST-005: mocks are
    acceptable only for external boundaries (HTTP APIs, third-party services).
    MockLLMProvider is a real LLMProvider subclass — it satisfies the interface
    contract and lets us control LLM output deterministically without mocking
    internal modules. The real EventBus and real SQLite exercise the full
    wiring path that production code uses.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import pytest
import pytest_asyncio

from ada.agents.emotion_analyzer import EmotionAnalyzerAgent, _strip_fences
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import EmotionAnalyzedEvent, EventTypes, MessageReceivedEvent
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from ada.models.emotion import EmotionDimensions, EmotionResult, PLUTCHIK_EMOTIONS


# ---------------------------------------------------------------------------
# MockLLMProvider (local stub — real LLMProvider subclass per Sacred Practice #5)
# ---------------------------------------------------------------------------

class MockLLMProvider(LLMProvider):
    """Deterministic LLM stub with a per-test response queue."""

    def __init__(self, default_response: str = "{}") -> None:
        self.default_response = default_response
        self.response_queue: list[str] = []
        self.calls: list[dict] = []

    def queue_response(self, response: str) -> None:
        self.response_queue.append(response)

    async def complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "system": system})
        content = self.response_queue.pop(0) if self.response_queue else self.default_response
        return LLMResponse(content=content, model="mock", input_tokens=1, output_tokens=1)

    async def stream(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        content = self.response_queue.pop(0) if self.response_queue else self.default_response
        for word in content.split():
            yield word + " "


# ---------------------------------------------------------------------------
# EmotionDimensions model tests
# ---------------------------------------------------------------------------

class TestEmotionDimensions:
    def test_valid_dimensions(self):
        dims = EmotionDimensions(valence=0.5, arousal=0.8)
        assert dims.valence == 0.5
        assert dims.arousal == 0.8

    def test_valence_lower_bound(self):
        dims = EmotionDimensions(valence=-1.0, arousal=0.0)
        assert dims.valence == -1.0

    def test_valence_upper_bound(self):
        dims = EmotionDimensions(valence=1.0, arousal=1.0)
        assert dims.valence == 1.0

    def test_arousal_lower_bound(self):
        dims = EmotionDimensions(valence=0.0, arousal=0.0)
        assert dims.arousal == 0.0

    def test_arousal_upper_bound(self):
        dims = EmotionDimensions(valence=0.0, arousal=1.0)
        assert dims.arousal == 1.0

    def test_valence_below_minimum_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            EmotionDimensions(valence=-1.1, arousal=0.5)

    def test_valence_above_maximum_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            EmotionDimensions(valence=1.1, arousal=0.5)

    def test_arousal_below_minimum_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            EmotionDimensions(valence=0.0, arousal=-0.1)

    def test_arousal_above_maximum_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            EmotionDimensions(valence=0.0, arousal=1.1)


# ---------------------------------------------------------------------------
# EmotionResult model tests
# ---------------------------------------------------------------------------

class TestEmotionResult:
    def _make_result(self, **overrides) -> EmotionResult:
        defaults = dict(
            primary_emotion="sadness",
            secondary_emotion=None,
            intensity=0.7,
            dimensions=EmotionDimensions(valence=-0.6, arousal=0.4),
            confidence=0.85,
        )
        defaults.update(overrides)
        return EmotionResult(**defaults)

    def test_basic_construction(self):
        result = self._make_result()
        assert result.primary_emotion == "sadness"
        assert result.secondary_emotion is None
        assert result.intensity == 0.7
        assert result.dimensions.valence == -0.6
        assert result.dimensions.arousal == 0.4
        assert result.confidence == 0.85

    def test_with_secondary_emotion(self):
        result = self._make_result(secondary_emotion="anger")
        assert result.secondary_emotion == "anger"

    def test_intensity_zero(self):
        result = self._make_result(intensity=0.0)
        assert result.intensity == 0.0

    def test_intensity_one(self):
        result = self._make_result(intensity=1.0)
        assert result.intensity == 1.0

    def test_intensity_below_minimum_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self._make_result(intensity=-0.1)

    def test_intensity_above_maximum_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self._make_result(intensity=1.1)

    def test_confidence_zero(self):
        result = self._make_result(confidence=0.0)
        assert result.confidence == 0.0

    def test_confidence_one(self):
        result = self._make_result(confidence=1.0)
        assert result.confidence == 1.0

    def test_confidence_below_minimum_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self._make_result(confidence=-0.01)

    def test_confidence_above_maximum_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self._make_result(confidence=1.01)

    def test_all_plutchik_emotions_valid(self):
        for emotion in PLUTCHIK_EMOTIONS:
            result = self._make_result(primary_emotion=emotion)
            assert result.primary_emotion == emotion

    def test_plutchik_emotions_set_completeness(self):
        assert PLUTCHIK_EMOTIONS == {
            "joy", "trust", "fear", "surprise",
            "sadness", "disgust", "anger", "anticipation",
        }


# ---------------------------------------------------------------------------
# _strip_fences utility tests
# ---------------------------------------------------------------------------

class TestStripFences:
    def test_no_fences(self):
        raw = '{"key": "value"}'
        assert _strip_fences(raw) == '{"key": "value"}'

    def test_json_fence(self):
        raw = '```json\n{"key": "value"}\n```'
        assert _strip_fences(raw) == '{"key": "value"}'

    def test_plain_fence(self):
        raw = '```\n{"key": "value"}\n```'
        assert _strip_fences(raw) == '{"key": "value"}'

    def test_fence_with_whitespace(self):
        raw = '  ```json  \n{"key": "value"}\n```  '
        assert _strip_fences(raw) == '{"key": "value"}'


# ---------------------------------------------------------------------------
# emotion_analyses StateManager CRUD tests
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state():
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


@pytest_asyncio.fixture
async def seeded_state(state):
    """State with a patient and session pre-created (FK constraints)."""
    await state.create_patient({
        "id": "patient-001",
        "name": "Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    await state.create_session({
        "id": "session-001",
        "patient_id": "patient-001",
    })
    return state


class TestEmotionAnalysesCRUD:
    @pytest.mark.asyncio
    async def test_create_and_retrieve(self, seeded_state):
        await seeded_state.create_emotion_analysis({
            "id": "ea-001",
            "session_id": "session-001",
            "patient_id": "patient-001",
            "message_id": "msg-001",
            "primary_emotion": "sadness",
            "secondary_emotion": "anger",
            "intensity": 0.7,
            "valence": -0.6,
            "arousal": 0.4,
            "confidence": 0.85,
        })
        results = await seeded_state.get_emotion_analyses("session-001")
        assert len(results) == 1
        r = results[0]
        assert r["id"] == "ea-001"
        assert r["primary_emotion"] == "sadness"
        assert r["secondary_emotion"] == "anger"
        assert r["intensity"] == pytest.approx(0.7)
        assert r["valence"] == pytest.approx(-0.6)
        assert r["arousal"] == pytest.approx(0.4)
        assert r["confidence"] == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_secondary_emotion_nullable(self, seeded_state):
        await seeded_state.create_emotion_analysis({
            "id": "ea-002",
            "session_id": "session-001",
            "patient_id": "patient-001",
            "message_id": "msg-002",
            "primary_emotion": "joy",
            "intensity": 0.9,
            "valence": 0.8,
            "arousal": 0.7,
            "confidence": 0.95,
        })
        results = await seeded_state.get_emotion_analyses("session-001")
        assert results[0]["secondary_emotion"] is None

    @pytest.mark.asyncio
    async def test_get_empty_session(self, seeded_state):
        results = await seeded_state.get_emotion_analyses("session-nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_multiple_analyses_ordered_by_created_at(self, seeded_state):
        for i in range(3):
            await seeded_state.create_emotion_analysis({
                "id": f"ea-{i:03d}",
                "session_id": "session-001",
                "patient_id": "patient-001",
                "message_id": f"msg-{i:03d}",
                "primary_emotion": "fear",
                "intensity": 0.5,
                "valence": -0.3,
                "arousal": 0.6,
                "confidence": 0.7,
            })
        results = await seeded_state.get_emotion_analyses("session-001")
        assert len(results) == 3
        # Ordered ascending by created_at
        ids = [r["id"] for r in results]
        assert ids == ["ea-000", "ea-001", "ea-002"]


# ---------------------------------------------------------------------------
# EmotionAnalyzerAgent unit tests
# ---------------------------------------------------------------------------

def _canned_json(
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


@pytest_asyncio.fixture
async def agent_setup(seeded_state):
    """Fully wired EmotionAnalyzerAgent with real EventBus and MockLLMProvider."""
    bus = EventBus()
    await bus.start()
    llm = MockLLMProvider()
    config = AdaConfig()
    agent = EmotionAnalyzerAgent()
    agent.initialize(bus, config, seeded_state, llm)
    await agent.start()
    yield agent, bus, llm, seeded_state
    await agent.stop()
    await bus.stop()


class TestEmotionAnalyzerAgent:
    @pytest.mark.asyncio
    async def test_publishes_emotion_analyzed_event(self, agent_setup):
        agent, bus, llm, state = agent_setup
        llm.queue_response(_canned_json())

        received: list[EmotionAnalyzedEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.EMOTION_ANALYZED, collector, "test-collector")

        await bus.publish(MessageReceivedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            message_id="msg-unit-001",
            content="I feel so lost and hopeless today.",
        ))

        # Give the bus time to process
        await asyncio.sleep(0.05)

        assert len(received) == 1
        evt = received[0]
        assert isinstance(evt, EmotionAnalyzedEvent)
        assert evt.primary_emotion == "sadness"
        assert evt.session_id == "session-001"
        assert evt.patient_id == "patient-001"
        assert evt.message_id == "msg-unit-001"
        assert evt.intensity == pytest.approx(0.7)
        assert evt.valence == pytest.approx(-0.6)
        assert evt.arousal == pytest.approx(0.4)
        assert evt.confidence == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_persists_to_db(self, agent_setup):
        agent, bus, llm, state = agent_setup
        llm.queue_response(_canned_json(primary="anger", intensity=0.8))

        await bus.publish(MessageReceivedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            message_id="msg-unit-002",
            content="I'm so angry about what happened.",
        ))

        await asyncio.sleep(0.05)

        rows = await state.get_emotion_analyses("session-001")
        assert len(rows) == 1
        assert rows[0]["primary_emotion"] == "anger"
        assert rows[0]["intensity"] == pytest.approx(0.8)
        assert rows[0]["message_id"] == "msg-unit-002"

    @pytest.mark.asyncio
    async def test_handles_markdown_fence_in_response(self, agent_setup):
        agent, bus, llm, state = agent_setup
        fenced = f"```json\n{_canned_json(primary='joy', valence=0.9)}\n```"
        llm.queue_response(fenced)

        received: list[EmotionAnalyzedEvent] = []
        bus.subscribe(EventTypes.EMOTION_ANALYZED, lambda e: received.append(e), "fence-test")

        await bus.publish(MessageReceivedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            message_id="msg-unit-003",
            content="Everything is wonderful!",
        ))

        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].primary_emotion == "joy"
        assert received[0].valence == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_invalid_json_skips_gracefully(self, agent_setup):
        agent, bus, llm, state = agent_setup
        llm.queue_response("not valid json at all")

        received: list = []
        bus.subscribe(EventTypes.EMOTION_ANALYZED, lambda e: received.append(e), "bad-json-test")

        await bus.publish(MessageReceivedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            message_id="msg-unit-004",
            content="Some content.",
        ))

        await asyncio.sleep(0.05)

        # Should not publish an event
        assert len(received) == 0
        # Should not persist anything
        rows = await state.get_emotion_analyses("session-001")
        assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_empty_message_skipped(self, agent_setup):
        agent, bus, llm, state = agent_setup

        received: list = []
        bus.subscribe(EventTypes.EMOTION_ANALYZED, lambda e: received.append(e), "empty-test")

        await bus.publish(MessageReceivedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            message_id="msg-unit-005",
            content="   ",
        ))

        await asyncio.sleep(0.05)

        assert len(received) == 0
        assert llm.calls == []

    @pytest.mark.asyncio
    async def test_agent_properties(self):
        agent = EmotionAnalyzerAgent()
        assert agent.name == "emotion_analyzer"
        assert "emotion" in agent.description.lower()
        assert EventTypes.MESSAGE_RECEIVED in agent.supported_events

    @pytest.mark.asyncio
    async def test_secondary_emotion_preserved(self, agent_setup):
        agent, bus, llm, state = agent_setup
        llm.queue_response(_canned_json(primary="fear", secondary="surprise"))

        received: list[EmotionAnalyzedEvent] = []
        bus.subscribe(EventTypes.EMOTION_ANALYZED, lambda e: received.append(e), "secondary-test")

        await bus.publish(MessageReceivedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            message_id="msg-unit-006",
            content="I don't know what to expect — it's scary.",
        ))

        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].primary_emotion == "fear"
        assert received[0].secondary_emotion == "surprise"
