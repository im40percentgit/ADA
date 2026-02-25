"""
Tests for multimodal event types.

@decision DEC-MULTIMODAL-002
@title Multimodal events as plain dataclasses on the existing EventBus
@status accepted
@rationale Reusing the EventBus and AdaEvent base keeps multimodal signals
    consistent with all other domain events. No new pub/sub infrastructure
    is needed — agents subscribe to VOICE_ANALYZED, FACE_ANALYZED, etc.
    exactly as they do for EMOTION_ANALYZED today.
"""

from __future__ import annotations

from ada.core.events import (
    EventTypes,
    FaceAnalyzedEvent,
    FusedEmotionEvent,
    SensorAlertEvent,
    SensorReadingEvent,
    VoiceAnalyzedEvent,
)


class TestMultimodalEventTypes:
    def test_voice_analyzed_constant(self):
        assert EventTypes.VOICE_ANALYZED == "voice.analyzed"

    def test_face_analyzed_constant(self):
        assert EventTypes.FACE_ANALYZED == "face.analyzed"

    def test_sensor_reading_constant(self):
        assert EventTypes.SENSOR_READING == "sensor.reading"

    def test_sensor_alert_constant(self):
        assert EventTypes.SENSOR_ALERT == "sensor.alert"

    def test_emotion_fused_constant(self):
        assert EventTypes.EMOTION_FUSED == "emotion.fused"


class TestVoiceAnalyzedEvent:
    def test_default_fields(self):
        event = VoiceAnalyzedEvent()
        assert event.event_type == "voice.analyzed"
        assert event.session_id == ""
        assert event.emotion == ""
        assert event.pitch_mean == 0.0
        assert event.energy_mean == 0.0
        assert event.speech_rate == 0.0
        assert event.confidence == 0.0

    def test_populated_fields(self):
        event = VoiceAnalyzedEvent(
            session_id="s1", patient_id="p1",
            audio_chunk_id="chunk-1", emotion="sadness",
            pitch_mean=180.0, energy_mean=0.4,
            speech_rate=2.5, confidence=0.85,
        )
        assert event.audio_chunk_id == "chunk-1"
        assert event.emotion == "sadness"


class TestFaceAnalyzedEvent:
    def test_default_fields(self):
        event = FaceAnalyzedEvent()
        assert event.event_type == "face.analyzed"
        assert event.frame_id == ""
        assert event.emotion == ""
        assert event.action_units == {}
        assert event.confidence == 0.0

    def test_populated_fields(self):
        event = FaceAnalyzedEvent(
            session_id="s1", patient_id="p1",
            frame_id="frame-42", emotion="surprise",
            action_units={"AU1": 0.7}, confidence=0.9,
        )
        assert event.frame_id == "frame-42"
        assert event.action_units["AU1"] == 0.7


class TestSensorReadingEvent:
    def test_default_fields(self):
        event = SensorReadingEvent()
        assert event.event_type == "sensor.reading"
        assert event.sensor_type == ""
        assert event.value == 0.0
        assert event.unit == ""

    def test_heart_rate(self):
        event = SensorReadingEvent(
            session_id="s1", patient_id="p1",
            sensor_type="hr", value=72.0, unit="bpm",
        )
        assert event.sensor_type == "hr"
        assert event.value == 72.0


class TestSensorAlertEvent:
    def test_default_fields(self):
        event = SensorAlertEvent()
        assert event.event_type == "sensor.alert"
        assert event.alert_type == ""
        assert event.threshold == 0.0

    def test_hr_spike(self):
        event = SensorAlertEvent(
            session_id="s1", patient_id="p1",
            sensor_type="hr", alert_type="spike",
            value=145.0, threshold=100.0,
            description="Heart rate spike detected",
        )
        assert event.alert_type == "spike"
        assert event.value == 145.0


class TestFusedEmotionEvent:
    def test_default_fields(self):
        event = FusedEmotionEvent()
        assert event.event_type == "emotion.fused"
        assert event.fused_emotion == ""
        assert event.modalities_available == []

    def test_full_fusion(self):
        event = FusedEmotionEvent(
            session_id="s1", patient_id="p1",
            text_emotion="sadness", voice_emotion="fear",
            face_emotion="sadness", physiological_state="elevated_arousal",
            fused_emotion="sadness", fused_valence=-0.6,
            fused_arousal=0.5, confidence=0.88,
            modalities_available=["text", "voice", "face", "physiological"],
        )
        assert event.fused_emotion == "sadness"
        assert len(event.modalities_available) == 4
