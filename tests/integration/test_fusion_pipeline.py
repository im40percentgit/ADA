"""
Integration tests for the Phase 4c MultimodalFusionAgent pipeline.

End-to-end tests: incoming event -> FusionAgent -> FusedEmotionEvent + DB persistence.
Uses real EventBus, real in-memory SQLite, real MultimodalFusionAgent.
MockLLMProvider is provided only because BaseAgent.initialize() requires one --
the fusion agent never calls the LLM.

@decision DEC-FUSION-006
@title Integration tests verify full fusion pipeline end-to-end
@status accepted
@rationale Unit tests verify math and event routing in isolation. Integration
    tests verify the complete wiring: EventBus dispatch -> FusionAgent ->
    FusedEmotionEvent -> DB persistence. Staleness decay is also tested by
    directly aging signals in the buffer, which requires integration-level
    access to agent internals.
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

import pytest
import pytest_asyncio

from ada.agents.fusion import MultimodalFusionAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import (
    EmotionAnalyzedEvent,
    EventTypes,
    FaceAnalyzedEvent,
    FusedEmotionEvent,
    SensorAlertEvent,
    VoiceAnalyzedEvent,
)
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse


# ---------------------------------------------------------------------------
# MockLLMProvider (never called by fusion agent -- required by initialize())
# ---------------------------------------------------------------------------

class MockLLMProvider(LLMProvider):
    async def complete(
        self, messages: list[dict], *, max_tokens: int = 1024,
        temperature: float = 0.7, system: str | None = None,
    ) -> LLMResponse:
        return LLMResponse(content="{}", model="mock", input_tokens=0, output_tokens=0)

    async def stream(
        self, messages: list[dict], *, max_tokens: int = 1024,
        temperature: float = 0.7, system: str | None = None,
    ) -> AsyncIterator[str]:
        yield ""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def fusion_stack():
    """Full integration stack for fusion pipeline tests."""
    state = StateManager(":memory:")
    await state.initialize()
    await state.create_patient({
        "id": "p1", "name": "Integration Patient",
        "dob": None, "preferences": {}, "emergency_contact": None,
        "caregiver_id": None,
    })
    await state.create_session({"id": "s1", "patient_id": "p1"})

    bus = EventBus()
    await bus.start()

    config = AdaConfig()
    llm = MockLLMProvider()

    agent = MultimodalFusionAgent()
    agent.initialize(bus, config, state, llm)
    await agent.start()

    received: list[FusedEmotionEvent] = []

    async def collector(event: FusedEmotionEvent) -> None:
        received.append(event)

    bus.subscribe(EventTypes.EMOTION_FUSED, collector, "integration-collector")

    yield agent, bus, state, received

    await agent.stop()
    await bus.stop()
    await state.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFusionPipeline:

    @pytest.mark.asyncio
    async def test_text_to_fused_pipeline(self, fusion_stack):
        """Single text signal flows end-to-end: event -> fused event + DB row."""
        agent, bus, state, received = fusion_stack

        await bus.publish(EmotionAnalyzedEvent(
            source="emotion_analyzer",
            session_id="s1",
            patient_id="p1",
            primary_emotion="joy",
            valence=0.8,
            arousal=0.6,
            confidence=0.9,
        ))
        await asyncio.sleep(0.15)

        assert len(received) == 1, f"Expected 1 event, got {len(received)}"
        evt = received[0]
        assert evt.fused_emotion == "joy"
        assert evt.modalities_available == ["text"]
        assert evt.session_id == "s1"
        assert evt.patient_id == "p1"

        rows = await state.get_fused_emotions("s1")
        assert len(rows) == 1
        assert rows[0]["fused_emotion"] == "joy"
        assert abs(rows[0]["fused_valence"] - 0.8) < 0.01

    @pytest.mark.asyncio
    async def test_multi_signal_pipeline(self, fusion_stack):
        """Three sequential signals produce three fused events; last has all modalities."""
        agent, bus, state, received = fusion_stack

        await bus.publish(EmotionAnalyzedEvent(
            source="emotion_analyzer",
            session_id="s1",
            patient_id="p1",
            primary_emotion="joy",
            valence=0.8,
            arousal=0.6,
            confidence=0.9,
        ))
        await asyncio.sleep(0.05)

        await bus.publish(VoiceAnalyzedEvent(
            source="voice_emotion",
            session_id="s1",
            patient_id="p1",
            emotion="sadness",
            confidence=0.9,
        ))
        await asyncio.sleep(0.05)

        await bus.publish(FaceAnalyzedEvent(
            source="facial_emotion",
            session_id="s1",
            patient_id="p1",
            emotion="fear",
            confidence=0.8,
        ))
        await asyncio.sleep(0.15)

        assert len(received) == 3, f"Expected 3 events (one per signal), got {len(received)}"

        last = received[-1]
        assert set(last.modalities_available) == {"text", "voice", "face"}

        # Fused valence must be a blend: joy(0.8), sadness(-0.7), fear(-0.6)
        # Weighted blend should be in roughly (-0.7, 0.8) range, not extreme
        joy_v = 0.8
        sadness_v = -0.7
        assert sadness_v < last.fused_valence < joy_v

        rows = await state.get_fused_emotions("s1")
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_stale_signal_dominated_by_fresh(self, fusion_stack):
        """A 60-second-old text signal loses to a fresh voice signal."""
        agent, bus, state, received = fusion_stack

        # Publish text (joy) — gets buffered
        await bus.publish(EmotionAnalyzedEvent(
            source="emotion_analyzer",
            session_id="s1",
            patient_id="p1",
            primary_emotion="joy",
            valence=0.8,
            arousal=0.6,
            confidence=1.0,
        ))
        await asyncio.sleep(0.1)

        # Age the text signal by 60 seconds (6 half-lives — weight ~= 0.016)
        agent._buffers["s1"]["text"].timestamp = time.monotonic() - 60.0

        # Publish fresh voice (sadness, v=-0.7)
        await bus.publish(VoiceAnalyzedEvent(
            source="voice_emotion",
            session_id="s1",
            patient_id="p1",
            emotion="sadness",
            confidence=1.0,
        ))
        await asyncio.sleep(0.15)

        # Last fused event should be sadness-dominated (negative valence)
        assert len(received) >= 2
        last = received[-1]
        assert last.fused_valence < 0.0, (
            f"Stale joy should not dominate fresh sadness; got fused_valence={last.fused_valence}"
        )
        assert "voice" in last.modalities_available

    @pytest.mark.asyncio
    async def test_sensor_alert_affects_arousal(self, fusion_stack):
        """Physiological stress=high signal produces arousal=0.7, blends with text."""
        agent, bus, state, received = fusion_stack

        # Sensor alert: stress=high -> arousal=0.7
        await bus.publish(SensorAlertEvent(
            source="physiological",
            session_id="s1",
            patient_id="p1",
            sensor_type="hr",
            alert_type="hr_spike",
            value=0.7,
            threshold=0.0,
            description="stress=high, HR elevated",
        ))
        await asyncio.sleep(0.1)

        assert len(received) == 1
        first = received[0]
        assert abs(first.fused_arousal - 0.7) < 0.05, (
            f"Expected arousal ~0.7 for stress=high, got {first.fused_arousal}"
        )
        assert "physiological" in first.modalities_available

        # Now add text emotion: joy (arousal=0.6)
        await bus.publish(EmotionAnalyzedEvent(
            source="emotion_analyzer",
            session_id="s1",
            patient_id="p1",
            primary_emotion="joy",
            valence=0.8,
            arousal=0.6,
            confidence=1.0,
        ))
        await asyncio.sleep(0.1)

        assert len(received) == 2
        second = received[1]
        # Fused arousal should be a blend of 0.7 (physio) and 0.6 (text)
        assert 0.5 < second.fused_arousal < 0.8, (
            f"Expected blended arousal in (0.5, 0.8), got {second.fused_arousal}"
        )
        assert set(second.modalities_available) == {"physiological", "text"}

    @pytest.mark.asyncio
    async def test_single_modality_still_fuses(self, fusion_stack):
        """A single voice event is sufficient to produce a FusedEmotionEvent."""
        agent, bus, state, received = fusion_stack

        await bus.publish(VoiceAnalyzedEvent(
            source="voice_emotion",
            session_id="s1",
            patient_id="p1",
            emotion="trust",
            confidence=0.85,
        ))
        await asyncio.sleep(0.15)

        assert len(received) == 1
        evt = received[0]
        assert evt.modalities_available == ["voice"]
        assert evt.fused_emotion != ""

        rows = await state.get_fused_emotions("s1")
        assert len(rows) == 1
        assert rows[0]["voice_emotion"] == "trust"
