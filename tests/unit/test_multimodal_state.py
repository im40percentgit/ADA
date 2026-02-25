"""
Tests for multimodal storage tables CRUD.

@decision DEC-MULTIMODAL-003
@title Four dedicated tables for multimodal data (audio, face, sensor, fused)
@status accepted
@rationale Each modality produces a distinct schema. Merging them into a
    single table would require nullable columns and type discrimination logic.
    Separate tables keep each schema clean and independently queryable, consistent
    with the existing pattern (emotion_analyses vs session_summaries vs
    cognitive_screenings in state.py).
"""

from __future__ import annotations

import uuid

import pytest

from ada.core.state import StateManager


@pytest.fixture
async def state():
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


class TestAudioAnalyses:
    async def test_create_and_get(self, state: StateManager):
        entry_id = str(uuid.uuid4())
        await state.create_audio_analysis(
            id=entry_id, session_id="s1", patient_id="p1",
            audio_chunk_id="chunk-1", emotion="sadness",
            pitch_mean=180.5, energy_mean=0.42,
            speech_rate=2.1, confidence=0.85,
        )
        rows = await state.get_audio_analyses("s1")
        assert len(rows) == 1
        assert rows[0]["emotion"] == "sadness"
        assert rows[0]["pitch_mean"] == 180.5

    async def test_get_empty_session(self, state: StateManager):
        rows = await state.get_audio_analyses("nonexistent")
        assert rows == []

    async def test_multiple_entries(self, state: StateManager):
        for i in range(3):
            await state.create_audio_analysis(
                id=str(uuid.uuid4()), session_id="s1", patient_id="p1",
                audio_chunk_id=f"chunk-{i}", emotion="joy",
                pitch_mean=200.0, energy_mean=0.5,
                speech_rate=3.0, confidence=0.9,
            )
        rows = await state.get_audio_analyses("s1")
        assert len(rows) == 3


class TestFaceAnalyses:
    async def test_create_and_get(self, state: StateManager):
        entry_id = str(uuid.uuid4())
        await state.create_face_analysis(
            id=entry_id, session_id="s1", patient_id="p1",
            frame_id="frame-1", emotion="surprise",
            action_units={"AU1": 0.7, "AU2": 0.5},
            confidence=0.92,
        )
        rows = await state.get_face_analyses("s1")
        assert len(rows) == 1
        assert rows[0]["emotion"] == "surprise"
        assert rows[0]["action_units"]["AU1"] == 0.7

    async def test_get_empty(self, state: StateManager):
        rows = await state.get_face_analyses("nonexistent")
        assert rows == []


class TestSensorReadings:
    async def test_create_and_get(self, state: StateManager):
        entry_id = str(uuid.uuid4())
        await state.create_sensor_reading(
            id=entry_id, session_id="s1", patient_id="p1",
            sensor_type="hr", value=72.0, unit="bpm",
        )
        rows = await state.get_sensor_readings("s1")
        assert len(rows) == 1
        assert rows[0]["sensor_type"] == "hr"
        assert rows[0]["value"] == 72.0

    async def test_filter_by_sensor_type(self, state: StateManager):
        for sensor_type, value, unit in [
            ("hr", 72.0, "bpm"), ("gsr", 3.5, "μS"), ("hr", 75.0, "bpm"),
        ]:
            await state.create_sensor_reading(
                id=str(uuid.uuid4()), session_id="s1", patient_id="p1",
                sensor_type=sensor_type, value=value, unit=unit,
            )
        rows = await state.get_sensor_readings("s1", sensor_type="hr")
        assert len(rows) == 2

    async def test_get_empty(self, state: StateManager):
        rows = await state.get_sensor_readings("nonexistent")
        assert rows == []


class TestFusedEmotions:
    async def test_create_and_get(self, state: StateManager):
        entry_id = str(uuid.uuid4())
        await state.create_fused_emotion(
            id=entry_id, session_id="s1", patient_id="p1",
            text_emotion="sadness", voice_emotion="fear",
            face_emotion="sadness", physiological_state="elevated_arousal",
            fused_emotion="sadness", fused_valence=-0.6,
            fused_arousal=0.5, confidence=0.88,
            modalities_available=["text", "voice", "face", "physiological"],
        )
        rows = await state.get_fused_emotions("s1")
        assert len(rows) == 1
        assert rows[0]["fused_emotion"] == "sadness"
        assert rows[0]["modalities_available"] == ["text", "voice", "face", "physiological"]

    async def test_partial_modalities(self, state: StateManager):
        entry_id = str(uuid.uuid4())
        await state.create_fused_emotion(
            id=entry_id, session_id="s1", patient_id="p1",
            text_emotion="joy", fused_emotion="joy",
            fused_valence=0.7, fused_arousal=0.4, confidence=0.6,
            modalities_available=["text"],
        )
        rows = await state.get_fused_emotions("s1")
        assert len(rows) == 1
        assert rows[0]["voice_emotion"] is None

    async def test_get_empty(self, state: StateManager):
        rows = await state.get_fused_emotions("nonexistent")
        assert rows == []
