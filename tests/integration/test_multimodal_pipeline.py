"""Integration tests for the multimodal pipeline.

@decision DEC-MULTIMODAL-003
@title Integration tests use in-memory SQLite and real EventBus
@status accepted
@rationale Real infrastructure (no mocks) validates the full
    SensorSimulator → EventBus → StateManager path. In-memory SQLite
    keeps tests fast and isolated while exercising actual SQL schema.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from ada.core.bus import EventBus
from ada.core.events import EventTypes, SensorReadingEvent
from ada.core.state import StateManager
from ada.sensors.simulator import SensorSimulator


@pytest.fixture
async def infra():
    state = StateManager(":memory:")
    await state.initialize()
    bus = EventBus()
    await bus.start()
    yield bus, state
    await bus.stop()
    await state.close()


class TestSensorSimulatorToStorage:
    async def test_simulator_events_persist_to_db(self, infra):
        """SensorSimulator → EventBus → persist to sensor_readings table."""
        bus, state = infra
        sim = SensorSimulator(bus=bus)

        async def persist_reading(event: SensorReadingEvent):
            await state.create_sensor_reading(
                id=str(uuid.uuid4()),
                session_id=event.session_id,
                patient_id=event.patient_id,
                sensor_type=event.sensor_type,
                value=event.value,
                unit=event.unit,
            )

        bus.subscribe(EventTypes.SENSOR_READING, persist_reading, "persist")

        await sim.generate_stream(
            session_id="s1", patient_id="p1",
            preset="relaxed", num_readings=3, interval_s=0.01,
        )
        await asyncio.sleep(0.2)

        rows = await state.get_sensor_readings("s1")
        assert len(rows) == 9  # 3 readings × 3 sensor types

        types = {r["sensor_type"] for r in rows}
        assert types == {"hr", "gsr", "spo2"}

    async def test_audio_analysis_round_trip(self, infra):
        """Create audio analysis → retrieve from DB."""
        bus, state = infra
        entry_id = str(uuid.uuid4())
        await state.create_audio_analysis(
            id=entry_id, session_id="s1", patient_id="p1",
            audio_chunk_id="chunk-1", emotion="sadness",
            pitch_mean=180.5, energy_mean=0.42,
            speech_rate=2.1, confidence=0.85,
        )
        rows = await state.get_audio_analyses("s1")
        assert len(rows) == 1
        assert rows[0]["id"] == entry_id

    async def test_face_analysis_round_trip(self, infra):
        """Create face analysis with action units → retrieve with deserialized JSON."""
        bus, state = infra
        entry_id = str(uuid.uuid4())
        await state.create_face_analysis(
            id=entry_id, session_id="s1", patient_id="p1",
            frame_id="frame-1", emotion="surprise",
            action_units={"AU1": 0.7, "AU2": 0.5, "AU5": 0.9},
            confidence=0.92,
        )
        rows = await state.get_face_analyses("s1")
        assert len(rows) == 1
        assert isinstance(rows[0]["action_units"], dict)
        assert rows[0]["action_units"]["AU5"] == 0.9

    async def test_fused_emotion_round_trip(self, infra):
        """Create fused emotion → retrieve with deserialized modalities list."""
        bus, state = infra
        entry_id = str(uuid.uuid4())
        await state.create_fused_emotion(
            id=entry_id, session_id="s1", patient_id="p1",
            text_emotion="sadness", voice_emotion="fear",
            face_emotion="sadness",
            fused_emotion="sadness", fused_valence=-0.6,
            fused_arousal=0.5, confidence=0.88,
            modalities_available=["text", "voice", "face"],
        )
        rows = await state.get_fused_emotions("s1")
        assert len(rows) == 1
        assert rows[0]["modalities_available"] == ["text", "voice", "face"]

    async def test_sensor_type_filter(self, infra):
        """Filter sensor readings by type."""
        bus, state = infra
        sim = SensorSimulator(bus=bus)

        async def persist(event: SensorReadingEvent):
            await state.create_sensor_reading(
                id=str(uuid.uuid4()),
                session_id=event.session_id,
                patient_id=event.patient_id,
                sensor_type=event.sensor_type,
                value=event.value,
                unit=event.unit,
            )

        bus.subscribe(EventTypes.SENSOR_READING, persist, "persist")

        await sim.generate_stream(
            session_id="s1", patient_id="p1",
            preset="anxious", num_readings=5, interval_s=0.01,
        )
        await asyncio.sleep(0.2)

        hr_rows = await state.get_sensor_readings("s1", sensor_type="hr")
        assert len(hr_rows) == 5
        for row in hr_rows:
            assert row["sensor_type"] == "hr"
