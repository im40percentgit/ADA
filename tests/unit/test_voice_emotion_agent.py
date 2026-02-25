"""
Unit tests for VoiceEmotionAgent.

Follows the EmotionAnalyzerAgent test pattern: real EventBus, real in-memory
SQLite, MockLLMProvider with canned JSON responses.

@decision DEC-ML-010
@title VoiceEmotionAgent tests use synthetic audio + canned LLM responses
@status accepted
@rationale Feature extraction is tested separately in test_audio_features.py.
    Agent tests focus on the event handling + LLM call + persistence pipeline.
    Using a real WAV fixture ensures the feature extraction runs end-to-end,
    while the canned LLM response makes classification deterministic.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import pytest
import pytest_asyncio

from ada.agents.voice_emotion import VoiceEmotionAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import (
    AudioChunkReceivedEvent,
    EventTypes,
    VoiceAnalyzedEvent,
)
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from tests.fixtures.audio_gen import generate_sine_wav


# ---------------------------------------------------------------------------
# MockLLMProvider
# ---------------------------------------------------------------------------

class MockLLMProvider(LLMProvider):
    """Deterministic LLM stub for voice emotion tests."""

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
# Helpers
# ---------------------------------------------------------------------------

def _canned_voice_json(
    emotion: str = "sadness",
    confidence: float = 0.85,
    reasoning: str = "Low pitch and energy suggest sadness",
) -> str:
    return json.dumps({
        "emotion": emotion,
        "confidence": confidence,
        "reasoning": reasoning,
    })


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state():
    sm = StateManager(":memory:")
    await sm.initialize()
    # Seed patient + session for FK constraints
    await sm.create_patient({
        "id": "patient-001",
        "name": "Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    await sm.create_session({"id": "session-001", "patient_id": "patient-001"})
    yield sm
    await sm.close()


@pytest_asyncio.fixture
async def agent_setup(state):
    """Fully wired VoiceEmotionAgent."""
    bus = EventBus()
    await bus.start()
    llm = MockLLMProvider()
    config = AdaConfig()
    agent = VoiceEmotionAgent()
    agent.initialize(bus, config, state, llm)
    await agent.start()
    yield agent, bus, llm, state
    await agent.stop()
    await bus.stop()


@pytest.fixture
def audio_wav() -> bytes:
    """1-second 440Hz sine wave WAV."""
    return generate_sine_wav(frequency=440.0, duration_s=1.0, sample_rate=16000)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestVoiceEmotionAgent:
    @pytest.mark.asyncio
    async def test_publishes_voice_analyzed_event(self, agent_setup, audio_wav):
        agent, bus, llm, state = agent_setup
        llm.queue_response(_canned_voice_json())

        received: list[VoiceAnalyzedEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.VOICE_ANALYZED, collector, "test-collector")

        await bus.publish(AudioChunkReceivedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            audio_bytes=audio_wav,
            sample_rate=16000,
            chunk_id="chunk-001",
        ))

        await asyncio.sleep(0.5)  # Feature extraction takes a moment

        assert len(received) == 1
        evt = received[0]
        assert isinstance(evt, VoiceAnalyzedEvent)
        assert evt.emotion == "sadness"
        assert evt.session_id == "session-001"
        assert evt.audio_chunk_id == "chunk-001"
        assert evt.confidence == pytest.approx(0.85)
        assert evt.pitch_mean > 0  # Should have extracted pitch

    @pytest.mark.asyncio
    async def test_persists_to_db(self, agent_setup, audio_wav):
        agent, bus, llm, state = agent_setup
        llm.queue_response(_canned_voice_json(emotion="anger", confidence=0.9))

        await bus.publish(AudioChunkReceivedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            audio_bytes=audio_wav,
            sample_rate=16000,
            chunk_id="chunk-002",
        ))

        await asyncio.sleep(0.5)

        rows = await state.get_audio_analyses("session-001")
        assert len(rows) == 1
        assert rows[0]["emotion"] == "anger"
        assert rows[0]["audio_chunk_id"] == "chunk-002"
        assert rows[0]["confidence"] == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_invalid_json_skips_gracefully(self, agent_setup, audio_wav):
        agent, bus, llm, state = agent_setup
        llm.queue_response("not valid json")

        received: list = []
        bus.subscribe(EventTypes.VOICE_ANALYZED, lambda e: received.append(e), "bad-json")

        await bus.publish(AudioChunkReceivedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            audio_bytes=audio_wav,
            sample_rate=16000,
            chunk_id="chunk-003",
        ))

        await asyncio.sleep(0.5)

        assert len(received) == 0
        rows = await state.get_audio_analyses("session-001")
        assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_empty_audio_skipped(self, agent_setup):
        agent, bus, llm, state = agent_setup

        received: list = []
        bus.subscribe(EventTypes.VOICE_ANALYZED, lambda e: received.append(e), "empty-test")

        await bus.publish(AudioChunkReceivedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            audio_bytes=b"",
            chunk_id="chunk-004",
        ))

        await asyncio.sleep(0.1)

        assert len(received) == 0
        assert llm.calls == []

    @pytest.mark.asyncio
    async def test_agent_properties(self):
        agent = VoiceEmotionAgent()
        assert agent.name == "voice_emotion"
        assert "voice" in agent.description.lower()
        assert EventTypes.AUDIO_CHUNK_RECEIVED in agent.supported_events

    @pytest.mark.asyncio
    async def test_markdown_fence_handling(self, agent_setup, audio_wav):
        agent, bus, llm, state = agent_setup
        fenced = f"```json\n{_canned_voice_json(emotion='joy')}\n```"
        llm.queue_response(fenced)

        received: list[VoiceAnalyzedEvent] = []
        bus.subscribe(EventTypes.VOICE_ANALYZED, lambda e: received.append(e), "fence-test")

        await bus.publish(AudioChunkReceivedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            audio_bytes=audio_wav,
            sample_rate=16000,
            chunk_id="chunk-005",
        ))

        await asyncio.sleep(0.5)

        assert len(received) == 1
        assert received[0].emotion == "joy"
