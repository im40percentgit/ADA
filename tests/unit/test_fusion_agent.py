"""
Unit tests for MultimodalFusionAgent and pure math fusion functions.

Tests are split into two sections:
  1. Pure math functions (synchronous) -- recency_weight, emotion_to_va,
     va_to_emotion, fuse_signals. No EventBus, no DB, no async.
  2. MultimodalFusionAgent (async) -- event routing, DB persistence,
     config-gated fusion. Uses real EventBus and in-memory SQLite.

@decision DEC-FUSION-005
@title Unit tests cover pure math independently from agent wiring
@status accepted
@rationale Pure math tests are synchronous and fast. They give precise
    coverage of the fusion algorithm without any async overhead. Agent
    tests verify event routing and persistence wiring on top.
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

import pytest
import pytest_asyncio

from ada.agents.fusion import (
    PLUTCHIK_MAP,
    ModalitySignal,
    MultimodalFusionAgent,
    emotion_to_va,
    fuse_signals,
    recency_weight,
    va_to_emotion,
)
from ada.core.bus import EventBus
from ada.core.config import AdaConfig, MultimodalConfig
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
# MockLLMProvider (fusion agent never calls LLM, but BaseAgent.initialize
# requires one via its interface contract)
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
# Helpers
# ---------------------------------------------------------------------------

def _make_signal(
    emotion: str = "joy",
    valence: float = 0.8,
    arousal: float = 0.6,
    confidence: float = 1.0,
    age_seconds: float = 0.0,
    modality: str = "text",
) -> ModalitySignal:
    return ModalitySignal(
        emotion=emotion,
        valence=valence,
        arousal=arousal,
        confidence=confidence,
        timestamp=time.monotonic() - age_seconds,
        modality=modality,
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
    agent = MultimodalFusionAgent()
    agent.initialize(bus, config, state, llm)
    await agent.start()
    yield agent, bus, state
    await agent.stop()
    await bus.stop()


@pytest_asyncio.fixture
async def agent_setup_disabled(state):
    """Agent setup with fusion_enabled=False."""
    bus = EventBus()
    await bus.start()
    llm = MockLLMProvider()
    config = AdaConfig(multimodal=MultimodalConfig(fusion_enabled=False))
    agent = MultimodalFusionAgent()
    agent.initialize(bus, config, state, llm)
    await agent.start()
    yield agent, bus, state
    await agent.stop()
    await bus.stop()


# ===========================================================================
# Section 1: Pure math functions (synchronous)
# ===========================================================================

class TestRecencyWeight:
    def test_recency_weight_at_zero(self):
        assert recency_weight(0.0) == 1.0

    def test_recency_weight_at_half_life(self):
        result = recency_weight(10.0, half_life=10.0)
        assert abs(result - 0.5) < 1e-10

    def test_recency_weight_at_double_half_life(self):
        result = recency_weight(20.0, half_life=10.0)
        assert abs(result - 0.25) < 1e-10

    def test_recency_weight_negative_age_clamped(self):
        result = recency_weight(-1.0)
        assert result == 1.0

    def test_recency_weight_custom_half_life(self):
        result = recency_weight(5.0, half_life=5.0)
        assert abs(result - 0.5) < 1e-10


class TestEmotionToVA:
    def test_emotion_to_va_known(self):
        valence, arousal = emotion_to_va("joy")
        assert valence == 0.8
        assert arousal == 0.6

    def test_emotion_to_va_case_insensitive(self):
        assert emotion_to_va("JOY") == emotion_to_va("joy")

    def test_emotion_to_va_mixed_case(self):
        assert emotion_to_va("Joy") == emotion_to_va("joy")

    def test_emotion_to_va_unknown(self):
        valence, arousal = emotion_to_va("boredom")
        assert valence == 0.0
        assert arousal == 0.5

    def test_emotion_to_va_all_plutchik(self):
        for name, expected_v, expected_a in PLUTCHIK_MAP:
            v, a = emotion_to_va(name)
            assert v == expected_v, f"valence mismatch for {name}"
            assert a == expected_a, f"arousal mismatch for {name}"

    def test_emotion_to_va_fear(self):
        v, a = emotion_to_va("fear")
        assert v == -0.6
        assert a == 0.8


class TestVAToEmotion:
    def test_va_to_emotion_exact_joy(self):
        assert va_to_emotion(0.8, 0.6) == "joy"

    def test_va_to_emotion_exact_sadness(self):
        assert va_to_emotion(-0.7, 0.2) == "sadness"

    def test_va_to_emotion_nearest_to_joy(self):
        # (0.7, 0.5) is closest to joy (0.8, 0.6) by Euclidean distance
        result = va_to_emotion(0.7, 0.5)
        assert result == "joy"

    def test_va_to_emotion_nearest_to_fear(self):
        # High arousal, negative valence => fear
        result = va_to_emotion(-0.6, 0.85)
        assert result == "fear"

    def test_va_to_emotion_returns_string(self):
        result = va_to_emotion(0.0, 0.5)
        assert isinstance(result, str)
        assert result in [name for name, _, _ in PLUTCHIK_MAP]


class TestFuseSignals:
    def test_fuse_single_signal(self):
        sig = _make_signal(emotion="joy", valence=0.8, arousal=0.6, confidence=1.0)
        now = time.monotonic()
        result = fuse_signals([sig], now)
        assert result is not None
        assert result["fused_emotion"] == "joy"
        assert abs(result["fused_valence"] - 0.8) < 1e-6
        assert abs(result["fused_arousal"] - 0.6) < 1e-6
        assert result["modalities"] == ["text"]

    def test_fuse_multi_signal_average(self):
        # joy (v=0.8, a=0.6) and sadness (v=-0.7, a=0.2), equal confidence=1.0, both fresh
        joy = _make_signal(emotion="joy", valence=0.8, arousal=0.6, confidence=1.0, modality="text")
        sadness = _make_signal(emotion="sadness", valence=-0.7, arousal=0.2, confidence=1.0, modality="voice")
        now = time.monotonic()
        result = fuse_signals([joy, sadness], now)
        assert result is not None
        # Equal weights => average
        assert abs(result["fused_valence"] - (0.8 + -0.7) / 2) < 1e-6
        assert abs(result["fused_arousal"] - (0.6 + 0.2) / 2) < 1e-6
        assert set(result["modalities"]) == {"text", "voice"}

    def test_fuse_stale_signal_filtered(self):
        # Very old signal (60s >> half_life=10s) with low confidence => filtered
        stale = _make_signal(emotion="joy", confidence=0.1, age_seconds=60.0)
        now = time.monotonic()
        # effective weight = 0.1 * 2^(-60/10) = 0.1 * 0.015625 = 0.0015625 < min_weight=0.01
        result = fuse_signals([stale], now, half_life=10.0, min_weight=0.01)
        assert result is None

    def test_fuse_staleness_reduces_weight(self):
        # Stale joy vs fresh sadness — sadness should dominate
        stale_joy = _make_signal(emotion="joy", valence=0.8, arousal=0.6,
                                  confidence=1.0, age_seconds=30.0, modality="text")
        fresh_sadness = _make_signal(emotion="sadness", valence=-0.7, arousal=0.2,
                                      confidence=1.0, age_seconds=0.0, modality="voice")
        now = time.monotonic()
        result = fuse_signals([stale_joy, fresh_sadness], now, half_life=10.0)
        assert result is not None
        # Fresh sadness has weight=1.0, stale joy has weight=2^(-3)=0.125
        # Fused valence should be closer to sadness (negative)
        assert result["fused_valence"] < 0.0, "Fresh sadness should dominate"

    def test_fuse_empty_list(self):
        result = fuse_signals([], time.monotonic())
        assert result is None

    def test_fuse_returns_all_required_keys(self):
        sig = _make_signal()
        result = fuse_signals([sig], time.monotonic())
        assert result is not None
        assert "fused_emotion" in result
        assert "fused_valence" in result
        assert "fused_arousal" in result
        assert "confidence" in result
        assert "modalities" in result

    def test_fuse_confidence_is_mean_of_weights(self):
        sig = _make_signal(confidence=0.8)
        now = time.monotonic()
        result = fuse_signals([sig], now, half_life=10.0)
        assert result is not None
        # For a fresh signal (age~0): effective_weight ~= confidence = 0.8
        # mean_confidence = total_weight / len(valid) = 0.8 / 1 = 0.8
        assert abs(result["confidence"] - 0.8) < 0.01


# ===========================================================================
# Section 2: MultimodalFusionAgent (async)
# ===========================================================================

class TestFusionAgentProperties:
    def test_agent_properties(self):
        agent = MultimodalFusionAgent()
        assert agent.name == "fusion"
        assert "fusion" in agent.description.lower()
        assert EventTypes.EMOTION_ANALYZED in agent.supported_events
        assert EventTypes.VOICE_ANALYZED in agent.supported_events
        assert EventTypes.FACE_ANALYZED in agent.supported_events
        assert EventTypes.SENSOR_ALERT in agent.supported_events


class TestFusionAgentEvents:
    @pytest.mark.asyncio
    async def test_text_signal_produces_fused_event(self, agent_setup):
        agent, bus, state = agent_setup
        received: list[FusedEmotionEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.EMOTION_FUSED, collector, "test-collector")

        await bus.publish(EmotionAnalyzedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            primary_emotion="joy",
            valence=0.8,
            arousal=0.6,
            confidence=0.9,
        ))
        await asyncio.sleep(0.1)

        assert len(received) == 1
        evt = received[0]
        assert evt.text_emotion == "joy"
        assert evt.modalities_available == ["text"]
        assert evt.fused_emotion == "joy"

    @pytest.mark.asyncio
    async def test_voice_signal_produces_fused_event(self, agent_setup):
        agent, bus, state = agent_setup
        received: list[FusedEmotionEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.EMOTION_FUSED, collector, "test-voice-collector")

        await bus.publish(VoiceAnalyzedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            emotion="sadness",
            confidence=0.85,
        ))
        await asyncio.sleep(0.1)

        assert len(received) == 1
        evt = received[0]
        assert evt.voice_emotion == "sadness"
        assert evt.modalities_available == ["voice"]

    @pytest.mark.asyncio
    async def test_face_signal_produces_fused_event(self, agent_setup):
        agent, bus, state = agent_setup
        received: list[FusedEmotionEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.EMOTION_FUSED, collector, "test-face-collector")

        await bus.publish(FaceAnalyzedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            emotion="fear",
            confidence=0.75,
        ))
        await asyncio.sleep(0.1)

        assert len(received) == 1
        evt = received[0]
        assert evt.face_emotion == "fear"
        assert evt.modalities_available == ["face"]

    @pytest.mark.asyncio
    async def test_multi_signal_fusion(self, agent_setup):
        agent, bus, state = agent_setup
        received: list[FusedEmotionEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.EMOTION_FUSED, collector, "test-multi-collector")

        await bus.publish(EmotionAnalyzedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            primary_emotion="joy",
            valence=0.8,
            arousal=0.6,
            confidence=0.9,
        ))
        await asyncio.sleep(0.05)

        await bus.publish(VoiceAnalyzedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            emotion="sadness",
            confidence=0.9,
        ))
        await asyncio.sleep(0.1)

        assert len(received) == 2
        last = received[-1]
        assert set(last.modalities_available) == {"text", "voice"}
        # Fused valence should be a blend (not pure joy or pure sadness)
        joy_v = 0.8
        sadness_v = -0.7
        assert sadness_v < last.fused_valence < joy_v

    @pytest.mark.asyncio
    async def test_sensor_alert_produces_fused_event(self, agent_setup):
        agent, bus, state = agent_setup
        received: list[FusedEmotionEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.EMOTION_FUSED, collector, "test-sensor-collector")

        await bus.publish(SensorAlertEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            sensor_type="hr",
            alert_type="hr_spike",
            value=0.7,
            threshold=0.0,
            description="stress=high, HR elevated",
        ))
        await asyncio.sleep(0.1)

        assert len(received) == 1
        evt = received[0]
        assert "physiological" in evt.modalities_available
        assert evt.physiological_state == "anticipation"
        # Arousal should reflect high stress (0.7)
        assert abs(evt.fused_arousal - 0.7) < 0.1

    @pytest.mark.asyncio
    async def test_empty_session_id_skipped(self, agent_setup):
        agent, bus, state = agent_setup
        received: list = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.EMOTION_FUSED, collector, "test-empty-collector")

        await bus.publish(EmotionAnalyzedEvent(
            source="test",
            session_id="",
            patient_id="patient-001",
            primary_emotion="joy",
            valence=0.8,
            arousal=0.6,
            confidence=0.9,
        ))
        await asyncio.sleep(0.1)

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_stop_clears_buffers(self, agent_setup):
        agent, bus, state = agent_setup

        await bus.publish(EmotionAnalyzedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            primary_emotion="joy",
            valence=0.8,
            arousal=0.6,
            confidence=0.9,
        ))
        await asyncio.sleep(0.1)

        assert len(agent._buffers) > 0

        await agent.stop()
        assert len(agent._buffers) == 0

    @pytest.mark.asyncio
    async def test_fused_emotion_persisted_to_db(self, agent_setup):
        agent, bus, state = agent_setup

        await bus.publish(EmotionAnalyzedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            primary_emotion="joy",
            valence=0.8,
            arousal=0.6,
            confidence=0.9,
        ))
        await asyncio.sleep(0.15)

        rows = await state.get_fused_emotions("session-001")
        assert len(rows) == 1
        assert rows[0]["fused_emotion"] == "joy"
        assert rows[0]["text_emotion"] == "joy"
        assert abs(rows[0]["fused_valence"] - 0.8) < 1e-4

    @pytest.mark.asyncio
    async def test_fusion_disabled_via_config(self, agent_setup_disabled):
        agent, bus, state = agent_setup_disabled
        received: list = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.EMOTION_FUSED, collector, "test-disabled-collector")

        await bus.publish(EmotionAnalyzedEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            primary_emotion="joy",
            valence=0.8,
            arousal=0.6,
            confidence=0.9,
        ))
        await asyncio.sleep(0.1)

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_sensor_alert_stress_parsing_critical(self, agent_setup):
        """Critical stress level maps to arousal=0.9."""
        agent, bus, state = agent_setup
        received: list[FusedEmotionEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.EMOTION_FUSED, collector, "test-critical-collector")

        await bus.publish(SensorAlertEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            sensor_type="gsr",
            alert_type="gsr_spike",
            value=0.9,
            threshold=0.0,
            description="stress=critical, GSR doubled",
        ))
        await asyncio.sleep(0.1)

        assert len(received) == 1
        assert abs(received[0].fused_arousal - 0.9) < 0.05

    @pytest.mark.asyncio
    async def test_sensor_alert_unknown_stress_defaults_to_moderate(self, agent_setup):
        """Unknown stress level defaults to moderate (arousal=0.5)."""
        agent, bus, state = agent_setup
        received: list[FusedEmotionEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.EMOTION_FUSED, collector, "test-unknown-collector")

        await bus.publish(SensorAlertEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            sensor_type="hr",
            alert_type="rapid_change",
            value=0.5,
            threshold=0.0,
            description="stress=unknown_level, some detail",
        ))
        await asyncio.sleep(0.1)

        assert len(received) == 1
        assert abs(received[0].fused_arousal - 0.5) < 0.05
