"""
Pydantic models for multimodal emotion analysis results.

Covers voice (audio), face (video), physiological sensors, and fused
multimodal emotion signals. FusedEmotionResult extends EmotionResult
fields so downstream consumers expecting Plutchik's 8 + valence/arousal
still work.

@decision DEC-MULTIMODAL-001
@title Separate /ws/media/ from /ws/chat/
@status accepted
@rationale Media backpressure must not block text chat. Separate WebSocket
    connections allow independent failure and flow control. Text chat must
    remain responsive even if audio/video processing is slow or unavailable.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from ada.models.emotion import EmotionDimensions

VALID_SENSOR_TYPES = frozenset({"hr", "gsr", "spo2"})


class VoiceEmotionResult(BaseModel):
    """Result of voice emotion analysis on an audio chunk."""

    emotion: str = Field(description="Detected emotion from speech")
    pitch_mean: float = Field(description="Mean fundamental frequency (Hz)")
    energy_mean: float = Field(ge=0.0, le=1.0, description="Mean energy (normalized)")
    speech_rate: float = Field(ge=0.0, description="Syllables per second")
    confidence: float = Field(ge=0.0, le=1.0, description="Analysis confidence")


class FaceEmotionResult(BaseModel):
    """Result of facial emotion analysis on a video frame."""

    emotion: str = Field(description="Detected facial expression emotion")
    action_units: dict[str, float] = Field(
        default_factory=dict, description="FACS action unit intensities"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Analysis confidence")


class SensorReading(BaseModel):
    """A single physiological sensor reading."""

    sensor_type: str = Field(description="Sensor type: hr, gsr, or spo2")
    value: float = Field(description="Sensor value")
    unit: str = Field(description="Measurement unit (bpm, μS, %)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("sensor_type")
    @classmethod
    def validate_sensor_type(cls, v: str) -> str:
        if v not in VALID_SENSOR_TYPES:
            raise ValueError(f"sensor_type must be one of {VALID_SENSOR_TYPES}, got {v!r}")
        return v


class FusedEmotionResult(BaseModel):
    """
    Unified multimodal emotion result combining text, voice, face, and
    physiological signals.

    Maintains the same core fields as EmotionResult (primary_emotion, intensity,
    dimensions, confidence) so downstream consumers work unchanged. Adds
    per-modality breakdown and modalities_available list.
    """

    # Core fields (compatible with EmotionResult)
    primary_emotion: str = Field(description="Fused primary emotion (Plutchik's 8)")
    secondary_emotion: str | None = Field(default=None)
    intensity: float = Field(ge=0.0, le=1.0, description="Fused intensity")
    dimensions: EmotionDimensions = Field(description="Fused valence/arousal")
    confidence: float = Field(ge=0.0, le=1.0, description="Fused confidence")

    # Per-modality breakdown
    text_emotion: str | None = Field(default=None, description="Text-based emotion")
    voice_emotion: str | None = Field(default=None, description="Voice-based emotion")
    face_emotion: str | None = Field(default=None, description="Face-based emotion")
    physiological_state: str | None = Field(
        default=None, description="Physiological state label"
    )

    # Which modalities contributed to this fusion
    modalities_available: list[str] = Field(
        default_factory=list, description="List of modalities present"
    )
