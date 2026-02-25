"""
Unit tests for FacialEmotionAgent.

Follows the EmotionAnalyzerAgent test pattern. Since Haar cascade detection
of synthetic faces is not guaranteed, tests use a mock feature extraction
approach: we test the agent's event handling + LLM pipeline by directly
invoking handle_event with a VideoFrameReceivedEvent, and the agent
internally calls the real face feature extractor.

For the face-detected path, we patch the extract_features result to ensure
deterministic behavior. For the no-face path, we use a blank image.

@decision DEC-ML-012
@title FacialEmotionAgent tests mock feature extraction for face-detected path
@status accepted
@rationale Haar cascade detection of synthetic faces is non-deterministic.
    To test the LLM classification pipeline reliably, we mock the feature
    extraction return value for the face-detected path while using real
    extraction for the no-face path.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator
from unittest.mock import patch

import pytest
import pytest_asyncio

from ada.agents.facial_emotion import FacialEmotionAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import (
    EventTypes,
    FaceAnalyzedEvent,
    VideoFrameReceivedEvent,
)
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from ada.ml.face_features import FaceFeatures
from tests.fixtures.face_gen import generate_blank_image, generate_face_image


# ---------------------------------------------------------------------------
# MockLLMProvider
# ---------------------------------------------------------------------------

class MockLLMProvider(LLMProvider):
    def __init__(self, default_response: str = "{}") -> None:
        self.default_response = default_response
        self.response_queue: list[str] = []
        self.calls: list[dict] = []

    def queue_response(self, response: str) -> None:
        self.response_queue.append(response)

    async def complete(
        self, messages: list[dict], *, max_tokens: int = 1024,
        temperature: float = 0.7, system: str | None = None,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "system": system})
        content = self.response_queue.pop(0) if self.response_queue else self.default_response
        return LLMResponse(content=content, model="mock", input_tokens=1, output_tokens=1)

    async def stream(
        self, messages: list[dict], *, max_tokens: int = 1024,
        temperature: float = 0.7, system: str | None = None,
    ) -> AsyncIterator[str]:
        content = self.response_queue.pop(0) if self.response_queue else self.default_response
        for word in content.split():
            yield word + " "


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _canned_face_json(
    emotion: str = "joy",
    confidence: float = 0.88,
) -> str:
    return json.dumps({
        "emotion": emotion,
        "action_units": {
            "AU1": 0.1, "AU2": 0.1, "AU4": 0.0,
            "AU5": 0.2, "AU6": 0.7, "AU12": 0.8, "AU15": 0.0,
        },
        "confidence": confidence,
    })


_MOCK_FACE_FEATURES = FaceFeatures(
    face_detected=True,
    detection_confidence=0.9,
    action_units={
        "AU1": 0.1, "AU2": 0.1, "AU4": 0.0,
        "AU5": 0.2, "AU6": 0.7, "AU12": 0.8, "AU15": 0.0,
    },
    face_bbox=(0.2, 0.1, 0.6, 0.8),
    valid=True,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state():
    sm = StateManager(":memory:")
    await sm.initialize()
    await sm.create_patient({
        "id": "patient-001", "name": "Test Patient",
        "dob": None, "preferences": {}, "emergency_contact": None,
        "caregiver_id": None,
    })
    await sm.create_session({"id": "session-001", "patient_id": "patient-001"})
    yield sm
    await sm.close()


@pytest_asyncio.fixture
async def agent_setup(state):
    bus = EventBus()
    await bus.start()
    llm = MockLLMProvider()
    config = AdaConfig()
    agent = FacialEmotionAgent()
    agent.initialize(bus, config, state, llm)
    await agent.start()
    yield agent, bus, llm, state
    await agent.stop()
    await bus.stop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFacialEmotionAgent:
    @pytest.mark.asyncio
    async def test_publishes_face_analyzed_event(self, agent_setup):
        agent, bus, llm, state = agent_setup
        llm.queue_response(_canned_face_json())

        received: list[FaceAnalyzedEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.FACE_ANALYZED, collector, "test-collector")

        # @mock-exempt: Haar cascade face detection is non-deterministic on synthetic images (DEC-ML-012)
        with patch("ada.agents.facial_emotion.extract_features", return_value=_MOCK_FACE_FEATURES):
            await bus.publish(VideoFrameReceivedEvent(
                source="test",
                session_id="session-001",
                patient_id="patient-001",
                frame_bytes=generate_face_image(),
                frame_id="frame-001",
            ))
            await asyncio.sleep(0.1)

        assert len(received) == 1
        evt = received[0]
        assert isinstance(evt, FaceAnalyzedEvent)
        assert evt.emotion == "joy"
        assert evt.frame_id == "frame-001"
        assert evt.confidence == pytest.approx(0.88)
        assert "AU12" in evt.action_units

    @pytest.mark.asyncio
    async def test_persists_to_db(self, agent_setup):
        agent, bus, llm, state = agent_setup
        llm.queue_response(_canned_face_json(emotion="sadness", confidence=0.75))

        # @mock-exempt: Haar cascade face detection is non-deterministic on synthetic images (DEC-ML-012)
        with patch("ada.agents.facial_emotion.extract_features", return_value=_MOCK_FACE_FEATURES):
            await bus.publish(VideoFrameReceivedEvent(
                source="test",
                session_id="session-001",
                patient_id="patient-001",
                frame_bytes=generate_face_image(),
                frame_id="frame-002",
            ))
            await asyncio.sleep(0.1)

        rows = await state.get_face_analyses("session-001")
        assert len(rows) == 1
        assert rows[0]["emotion"] == "sadness"
        assert rows[0]["frame_id"] == "frame-002"

    @pytest.mark.asyncio
    async def test_no_face_skips(self, agent_setup):
        """Blank image (no face) should not trigger LLM or produce events."""
        agent, bus, llm, state = agent_setup

        received: list = []
        bus.subscribe(EventTypes.FACE_ANALYZED, lambda e: received.append(e), "no-face")

        await bus.publish(VideoFrameReceivedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            frame_bytes=generate_blank_image(),
            frame_id="frame-003",
        ))

        await asyncio.sleep(0.1)

        assert len(received) == 0
        assert llm.calls == []

    @pytest.mark.asyncio
    async def test_empty_frame_skipped(self, agent_setup):
        agent, bus, llm, state = agent_setup

        received: list = []
        bus.subscribe(EventTypes.FACE_ANALYZED, lambda e: received.append(e), "empty-test")

        await bus.publish(VideoFrameReceivedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            frame_bytes=b"",
            frame_id="frame-004",
        ))

        await asyncio.sleep(0.1)

        assert len(received) == 0
        assert llm.calls == []

    @pytest.mark.asyncio
    async def test_invalid_json_skips(self, agent_setup):
        agent, bus, llm, state = agent_setup
        llm.queue_response("not json")

        received: list = []
        bus.subscribe(EventTypes.FACE_ANALYZED, lambda e: received.append(e), "bad-json")

        # @mock-exempt: Haar cascade face detection is non-deterministic on synthetic images (DEC-ML-012)
        with patch("ada.agents.facial_emotion.extract_features", return_value=_MOCK_FACE_FEATURES):
            await bus.publish(VideoFrameReceivedEvent(
                source="test",
                session_id="session-001",
                patient_id="patient-001",
                frame_bytes=generate_face_image(),
                frame_id="frame-005",
            ))
            await asyncio.sleep(0.1)

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_agent_properties(self):
        agent = FacialEmotionAgent()
        assert agent.name == "facial_emotion"
        assert "facial" in agent.description.lower()
        assert EventTypes.VIDEO_FRAME_RECEIVED in agent.supported_events
