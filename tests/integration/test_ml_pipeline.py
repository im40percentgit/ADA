"""
Integration tests for the Phase 4b ML emotion pipeline.

End-to-end tests: fixture audio/video -> agent -> EventBus -> DB persistence.
Uses real EventBus, real in-memory SQLite, real feature extraction, MockLLMProvider.

@decision DEC-ML-015
@title Integration tests verify full pipeline from fixture to DB
@status accepted
@rationale Unit tests verify individual components. Integration tests verify
    the wiring: audio fixture -> VoiceEmotionAgent -> VoiceAnalyzedEvent -> DB,
    face fixture -> FacialEmotionAgent -> FaceAnalyzedEvent -> DB,
    SensorSimulator -> PhysiologicalAgent -> SensorAlertEvent.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest
import pytest_asyncio

from ada.agents.facial_emotion import FacialEmotionAgent
from ada.agents.physiological import PhysiologicalAgent
from ada.agents.voice_emotion import VoiceEmotionAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import (
    AudioChunkReceivedEvent,
    EventTypes,
    FaceAnalyzedEvent,
    SensorAlertEvent,
    SensorReadingEvent,
    VideoFrameReceivedEvent,
    VoiceAnalyzedEvent,
)
from ada.core.state import StateManager
from ada.ml.face_features import FaceFeatures
from tests.fixtures.audio_gen import generate_sine_wav
from tests.fixtures.face_gen import generate_face_image

# Re-use the integration conftest MockLLMProvider
from tests.integration.conftest import MockLLMProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def full_stack():
    """Full integration stack: state + bus + llm + config."""
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

    llm = MockLLMProvider()
    config = AdaConfig()

    yield state, bus, llm, config

    await bus.stop()
    await state.close()


# ---------------------------------------------------------------------------
# Voice Pipeline
# ---------------------------------------------------------------------------

class TestVoicePipeline:
    @pytest.mark.asyncio
    async def test_audio_to_db_roundtrip(self, full_stack):
        """Audio WAV -> VoiceEmotionAgent -> DB persistence."""
        state, bus, llm, config = full_stack

        llm.queue_response(json.dumps({
            "emotion": "sadness",
            "confidence": 0.9,
            "reasoning": "Low pitch and energy",
        }))

        agent = VoiceEmotionAgent()
        agent.initialize(bus, config, state, llm)
        await agent.start()

        received: list[VoiceAnalyzedEvent] = []
        bus.subscribe(EventTypes.VOICE_ANALYZED, lambda e: received.append(e), "voice-int")

        wav_bytes = generate_sine_wav(frequency=220.0, duration_s=1.0, sample_rate=16000)

        await bus.publish(AudioChunkReceivedEvent(
            source="test",
            session_id="s1",
            patient_id="p1",
            audio_bytes=wav_bytes,
            sample_rate=16000,
            chunk_id="int-chunk-001",
        ))

        await asyncio.sleep(1.0)  # Feature extraction takes time

        # Event published
        assert len(received) == 1
        assert received[0].emotion == "sadness"
        assert received[0].pitch_mean > 0

        # Persisted to DB
        rows = await state.get_audio_analyses("s1")
        assert len(rows) == 1
        assert rows[0]["emotion"] == "sadness"
        assert rows[0]["audio_chunk_id"] == "int-chunk-001"

        await agent.stop()


# ---------------------------------------------------------------------------
# Face Pipeline
# ---------------------------------------------------------------------------

class TestFacePipeline:
    @pytest.mark.asyncio
    async def test_face_to_db_roundtrip(self, full_stack):
        """Face image -> FacialEmotionAgent -> DB persistence."""
        state, bus, llm, config = full_stack

        llm.queue_response(json.dumps({
            "emotion": "joy",
            "action_units": {"AU6": 0.8, "AU12": 0.9},
            "confidence": 0.92,
        }))

        agent = FacialEmotionAgent()
        agent.initialize(bus, config, state, llm)
        await agent.start()

        received: list[FaceAnalyzedEvent] = []
        bus.subscribe(EventTypes.FACE_ANALYZED, lambda e: received.append(e), "face-int")

        mock_features = FaceFeatures(
            face_detected=True,
            detection_confidence=0.9,
            action_units={"AU1": 0.0, "AU6": 0.8, "AU12": 0.9},
            valid=True,
        )

        # @mock-exempt: Haar cascade face detection is non-deterministic on synthetic images (DEC-ML-012)
        with patch("ada.agents.facial_emotion.extract_features", return_value=mock_features):
            await bus.publish(VideoFrameReceivedEvent(
                source="test",
                session_id="s1",
                patient_id="p1",
                frame_bytes=generate_face_image(),
                frame_id="int-frame-001",
            ))

            await asyncio.sleep(0.2)

        # Event published
        assert len(received) == 1
        assert received[0].emotion == "joy"
        assert received[0].frame_id == "int-frame-001"

        # Persisted to DB
        rows = await state.get_face_analyses("s1")
        assert len(rows) == 1
        assert rows[0]["emotion"] == "joy"

        await agent.stop()


# ---------------------------------------------------------------------------
# Physiological Pipeline
# ---------------------------------------------------------------------------

class TestPhysiologicalPipeline:
    @pytest.mark.asyncio
    async def test_sensor_readings_trigger_alerts(self, full_stack):
        """10 sensor readings -> PhysiologicalAgent -> SensorAlertEvent."""
        state, bus, llm, config = full_stack

        llm.queue_response(json.dumps({
            "stress_level": "high",
            "arousal": 0.85,
            "alerts": [
                {"type": "hr_spike", "description": "Sudden HR increase"},
            ],
            "reasoning": "Elevated heart rate trend",
        }))

        agent = PhysiologicalAgent()
        agent.initialize(bus, config, state, llm)
        await agent.start()

        alerts: list[SensorAlertEvent] = []
        bus.subscribe(EventTypes.SENSOR_ALERT, lambda e: alerts.append(e), "physio-int")

        # Send 10 HR readings (trigger interval = 10)
        for i in range(10):
            await bus.publish(SensorReadingEvent(
                source="test",
                session_id="s1",
                patient_id="p1",
                sensor_type="hr",
                value=70.0 + i * 5,  # Rising HR
                unit="bpm",
            ))
            await asyncio.sleep(0.02)

        await asyncio.sleep(0.3)

        # LLM was called
        assert len(llm.calls) == 1

        # Alert published
        assert len(alerts) == 1
        assert alerts[0].alert_type == "hr_spike"
        assert alerts[0].session_id == "s1"

        await agent.stop()

    @pytest.mark.asyncio
    async def test_sensor_simulator_feeds_agent(self, full_stack):
        """SensorSimulator -> EventBus -> PhysiologicalAgent -> LLM call."""
        state, bus, llm, config = full_stack

        llm.queue_response(json.dumps({
            "stress_level": "low",
            "arousal": 0.3,
            "alerts": [],
            "reasoning": "Normal physiological state",
        }))

        agent = PhysiologicalAgent()
        agent.initialize(bus, config, state, llm)
        await agent.start()

        # Use the real SensorSimulator
        from ada.sensors.simulator import SensorSimulator
        sim = SensorSimulator(bus=bus)

        # Generate 4 ticks = 12 readings (3 sensors * 4 ticks), exceeds trigger of 10
        await sim.generate_stream(
            session_id="s1",
            patient_id="p1",
            preset="relaxed",
            num_readings=4,
            interval_s=0.05,
        )

        await asyncio.sleep(0.3)

        # LLM should have been called at least once
        assert len(llm.calls) >= 1

        await agent.stop()
