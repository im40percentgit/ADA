"""
Tests for multimodal Pydantic models.

@decision DEC-MULTIMODAL-001
@title Separate /ws/media/ from /ws/chat/
@status accepted
@rationale Media backpressure must not block text chat. Separate WebSocket
    connections allow independent failure and flow control.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ada.models.multimodal import (
    FaceEmotionResult,
    FusedEmotionResult,
    SensorReading,
    VoiceEmotionResult,
)
from ada.models.emotion import PLUTCHIK_EMOTIONS, EmotionDimensions


class TestVoiceEmotionResult:
    def test_valid_voice_result(self):
        result = VoiceEmotionResult(
            emotion="sadness",
            pitch_mean=180.5,
            energy_mean=0.42,
            speech_rate=2.1,
            confidence=0.85,
        )
        assert result.emotion == "sadness"
        assert result.pitch_mean == 180.5
        assert result.energy_mean == 0.42
        assert result.speech_rate == 2.1
        assert result.confidence == 0.85

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            VoiceEmotionResult(
                emotion="joy", pitch_mean=200.0, energy_mean=0.5,
                speech_rate=3.0, confidence=1.5,
            )

    def test_energy_bounds(self):
        with pytest.raises(ValidationError):
            VoiceEmotionResult(
                emotion="joy", pitch_mean=200.0, energy_mean=-0.1,
                speech_rate=3.0, confidence=0.8,
            )


class TestFaceEmotionResult:
    def test_valid_face_result(self):
        result = FaceEmotionResult(
            emotion="surprise",
            action_units={"AU1": 0.7, "AU2": 0.5, "AU5": 0.9},
            confidence=0.92,
        )
        assert result.emotion == "surprise"
        assert result.action_units["AU1"] == 0.7
        assert result.confidence == 0.92

    def test_empty_action_units_default(self):
        result = FaceEmotionResult(emotion="joy", confidence=0.8)
        assert result.action_units == {}

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            FaceEmotionResult(emotion="joy", confidence=-0.1)


class TestSensorReading:
    def test_valid_heart_rate(self):
        reading = SensorReading(
            sensor_type="hr", value=72.0, unit="bpm",
        )
        assert reading.sensor_type == "hr"
        assert reading.value == 72.0
        assert reading.unit == "bpm"

    def test_valid_gsr(self):
        reading = SensorReading(
            sensor_type="gsr", value=3.5, unit="μS",
        )
        assert reading.sensor_type == "gsr"

    def test_valid_spo2(self):
        reading = SensorReading(
            sensor_type="spo2", value=98.0, unit="%",
        )
        assert reading.sensor_type == "spo2"

    def test_invalid_sensor_type(self):
        with pytest.raises(ValidationError):
            SensorReading(sensor_type="invalid", value=1.0, unit="x")

    def test_timestamp_auto_set(self):
        reading = SensorReading(sensor_type="hr", value=72.0, unit="bpm")
        assert reading.timestamp is not None


class TestFusedEmotionResult:
    def test_valid_fused_result(self):
        result = FusedEmotionResult(
            primary_emotion="sadness",
            intensity=0.7,
            dimensions=EmotionDimensions(valence=-0.6, arousal=0.3),
            confidence=0.88,
            text_emotion="sadness",
            voice_emotion="fear",
            face_emotion="sadness",
            physiological_state="elevated_arousal",
            modalities_available=["text", "voice", "face", "physiological"],
        )
        assert result.primary_emotion == "sadness"
        assert result.text_emotion == "sadness"
        assert result.voice_emotion == "fear"
        assert len(result.modalities_available) == 4

    def test_partial_modalities(self):
        """Fused result works with only some modalities present."""
        result = FusedEmotionResult(
            primary_emotion="joy",
            intensity=0.5,
            dimensions=EmotionDimensions(valence=0.7, arousal=0.4),
            confidence=0.6,
            modalities_available=["text"],
            text_emotion="joy",
        )
        assert result.voice_emotion is None
        assert result.face_emotion is None
        assert result.physiological_state is None
        assert result.modalities_available == ["text"]

    def test_is_subclass_of_emotion_result_fields(self):
        """FusedEmotionResult has all EmotionResult fields."""
        result = FusedEmotionResult(
            primary_emotion="anger",
            intensity=0.9,
            dimensions=EmotionDimensions(valence=-0.8, arousal=0.9),
            confidence=0.95,
            modalities_available=["text"],
        )
        assert result.primary_emotion == "anger"
        assert result.intensity == 0.9
        assert result.dimensions.valence == -0.8
        assert result.confidence == 0.95
