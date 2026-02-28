# Phase 4a — Multimodal Pipeline Infrastructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the data pipeline infrastructure (event types, storage tables, binary ingest API, sensor simulator, PWA shell) that Phase 4b ML agents and Phase 4c fusion agent will plug into.

**Architecture:** New event types and Pydantic models for voice, face, sensor, and fused emotion signals. Media WebSocket endpoint (`/ws/media/{session_id}`) for streaming binary data (audio chunks, video frames, sensor readings) separate from the existing chat WebSocket. REST fallback endpoints for non-streaming clients. SensorSimulator generates realistic physiological data for testing without hardware. PWA manifest + service worker make the existing React app installable on mobile.

**Tech Stack:** Python 3.12+, FastAPI, SQLite/aiosqlite, Pydantic v2, pytest-asyncio, vite-plugin-pwa, React 18

---

## Task 1: Multimodal Pydantic Models

### Context
Phase 3 established `EmotionResult` and `EmotionDimensions` in `ada/models/emotion.py`. Phase 4a needs parallel models for voice, face, sensor, and fused emotion results. These live in a new file `ada/models/multimodal.py` to avoid bloating the emotion module.

### Files
- Create: `ada/models/multimodal.py`
- Create: `tests/unit/test_multimodal_models.py`

### Steps

**Step 1: Write failing tests for VoiceEmotionResult**

Create `tests/unit/test_multimodal_models.py`:

```python
"""Tests for multimodal Pydantic models."""

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
        # These fields come from EmotionResult's structure
        assert result.primary_emotion == "anger"
        assert result.intensity == 0.9
        assert result.dimensions.valence == -0.8
        assert result.confidence == 0.95
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_multimodal_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ada.models.multimodal'`

**Step 3: Implement the models**

Create `ada/models/multimodal.py`:

```python
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
    connections allow independent failure and flow control.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

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

    @classmethod
    def model_validator_sensor_type(cls, v: str) -> str:
        if v not in VALID_SENSOR_TYPES:
            raise ValueError(f"sensor_type must be one of {VALID_SENSOR_TYPES}, got {v!r}")
        return v

    from pydantic import field_validator

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
    dimensions: "EmotionDimensions" = Field(description="Fused valence/arousal")
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


# Deferred import to avoid circular dependency
from ada.models.emotion import EmotionDimensions  # noqa: E402

FusedEmotionResult.model_rebuild()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_multimodal_models.py -v`
Expected: PASS (14 tests)

**Step 5: Commit**

```
feat(models): multimodal Pydantic models — voice, face, sensor, fused emotion
```

---

## Task 2: Multimodal Event Types

### Context
Events follow the pattern in `ada/core/events.py`: string constants in `EventTypes` class + `@dataclass` subclasses of `AdaEvent`. Add 5 new event types for the multimodal pipeline.

### Files
- Modify: `ada/core/events.py`
- Create: `tests/unit/test_multimodal_events.py`

### Steps

**Step 1: Write failing tests for new event types**

Create `tests/unit/test_multimodal_events.py`:

```python
"""Tests for multimodal event types."""

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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_multimodal_events.py -v`
Expected: FAIL — `ImportError: cannot import name 'VoiceAnalyzedEvent'`

**Step 3: Add event types and dataclasses to events.py**

Add to `EventTypes` class (after `SESSION_SUMMARIZED`):

```python
    # Multimodal (Phase 4)
    VOICE_ANALYZED = "voice.analyzed"
    FACE_ANALYZED = "face.analyzed"
    SENSOR_READING = "sensor.reading"
    SENSOR_ALERT = "sensor.alert"
    EMOTION_FUSED = "emotion.fused"
```

Add dataclasses at the end of the file:

```python
@dataclass
class VoiceAnalyzedEvent(AdaEvent):
    """Published by VoiceEmotionAgent after analysing an audio chunk."""

    event_type: str = EventTypes.VOICE_ANALYZED
    session_id: str = ""
    patient_id: str = ""
    audio_chunk_id: str = ""
    emotion: str = ""
    pitch_mean: float = 0.0
    energy_mean: float = 0.0
    speech_rate: float = 0.0
    confidence: float = 0.0


@dataclass
class FaceAnalyzedEvent(AdaEvent):
    """Published by FacialEmotionAgent after analysing a video frame."""

    event_type: str = EventTypes.FACE_ANALYZED
    session_id: str = ""
    patient_id: str = ""
    frame_id: str = ""
    emotion: str = ""
    action_units: dict = field(default_factory=dict)
    confidence: float = 0.0


@dataclass
class SensorReadingEvent(AdaEvent):
    """Published by SensorSimulator or IoT gateway for each sensor reading."""

    event_type: str = EventTypes.SENSOR_READING
    session_id: str = ""
    patient_id: str = ""
    sensor_type: str = ""    # hr, gsr, spo2
    value: float = 0.0
    unit: str = ""           # bpm, μS, %


@dataclass
class SensorAlertEvent(AdaEvent):
    """Published by PhysiologicalAgent when a sensor reading is anomalous."""

    event_type: str = EventTypes.SENSOR_ALERT
    session_id: str = ""
    patient_id: str = ""
    sensor_type: str = ""
    alert_type: str = ""     # spike, drop, threshold
    value: float = 0.0
    threshold: float = 0.0
    description: str = ""


@dataclass
class FusedEmotionEvent(AdaEvent):
    """Published by MultimodalFusionAgent after combining all modality signals."""

    event_type: str = EventTypes.EMOTION_FUSED
    session_id: str = ""
    patient_id: str = ""
    text_emotion: str = ""
    voice_emotion: str = ""
    face_emotion: str = ""
    physiological_state: str = ""
    fused_emotion: str = ""
    fused_valence: float = 0.0
    fused_arousal: float = 0.0
    confidence: float = 0.0
    modalities_available: list = field(default_factory=list)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_multimodal_events.py -v`
Expected: PASS (15 tests)

**Step 5: Run full test suite to check for regressions**

Run: `pytest tests/ -v --tb=short`
Expected: 494+ tests pass, 0 failures

**Step 6: Commit**

```
feat(events): multimodal event types — voice, face, sensor, fused emotion
```

---

## Task 3: Multimodal Storage Tables

### Context
Follow the existing pattern in `ada/core/state.py`: add tables to `_SCHEMA`, add CRUD methods. Four new tables: `audio_analyses`, `face_analyses`, `sensor_readings`, `fused_emotions`.

### Files
- Modify: `ada/core/state.py`
- Create: `tests/unit/test_multimodal_state.py`

### Steps

**Step 1: Write failing tests for audio_analyses CRUD**

Create `tests/unit/test_multimodal_state.py`:

```python
"""Tests for multimodal storage tables CRUD."""

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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_multimodal_state.py -v`
Expected: FAIL — `AttributeError: 'StateManager' object has no attribute 'create_audio_analysis'`

**Step 3: Add tables to _SCHEMA in state.py**

Add before the final index block (before `CREATE INDEX IF NOT EXISTS idx_sessions_patient`):

```sql
CREATE TABLE IF NOT EXISTS audio_analyses (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    patient_id TEXT NOT NULL,
    audio_chunk_id TEXT NOT NULL,
    emotion TEXT NOT NULL,
    pitch_mean REAL NOT NULL,
    energy_mean REAL NOT NULL,
    speech_rate REAL NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audio_session ON audio_analyses(session_id);
CREATE INDEX IF NOT EXISTS idx_audio_patient ON audio_analyses(patient_id);

CREATE TABLE IF NOT EXISTS face_analyses (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    patient_id TEXT NOT NULL,
    frame_id TEXT NOT NULL,
    emotion TEXT NOT NULL,
    action_units TEXT NOT NULL DEFAULT '{}',
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_face_session ON face_analyses(session_id);
CREATE INDEX IF NOT EXISTS idx_face_patient ON face_analyses(patient_id);

CREATE TABLE IF NOT EXISTS sensor_readings (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    patient_id TEXT NOT NULL,
    sensor_type TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sensor_session ON sensor_readings(session_id);
CREATE INDEX IF NOT EXISTS idx_sensor_patient ON sensor_readings(patient_id);
CREATE INDEX IF NOT EXISTS idx_sensor_type ON sensor_readings(sensor_type);

CREATE TABLE IF NOT EXISTS fused_emotions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    patient_id TEXT NOT NULL,
    text_emotion TEXT,
    voice_emotion TEXT,
    face_emotion TEXT,
    physiological_state TEXT,
    fused_emotion TEXT NOT NULL,
    fused_valence REAL NOT NULL,
    fused_arousal REAL NOT NULL,
    confidence REAL NOT NULL,
    modalities_available TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_fused_session ON fused_emotions(session_id);
CREATE INDEX IF NOT EXISTS idx_fused_patient ON fused_emotions(patient_id);
```

**Step 4: Add CRUD methods to StateManager**

Add these methods to the `StateManager` class:

```python
    # ------------------------------------------------------------------
    # Audio analyses
    # ------------------------------------------------------------------

    async def create_audio_analysis(
        self, *, id: str, session_id: str, patient_id: str,
        audio_chunk_id: str, emotion: str, pitch_mean: float,
        energy_mean: float, speech_rate: float, confidence: float,
    ) -> None:
        await self._db.execute(
            """INSERT INTO audio_analyses
               (id, session_id, patient_id, audio_chunk_id, emotion,
                pitch_mean, energy_mean, speech_rate, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (id, session_id, patient_id, audio_chunk_id, emotion,
             pitch_mean, energy_mean, speech_rate, confidence),
        )
        await self._db.commit()

    async def get_audio_analyses(self, session_id: str) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT * FROM audio_analyses WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Face analyses
    # ------------------------------------------------------------------

    async def create_face_analysis(
        self, *, id: str, session_id: str, patient_id: str,
        frame_id: str, emotion: str, action_units: dict,
        confidence: float,
    ) -> None:
        await self._db.execute(
            """INSERT INTO face_analyses
               (id, session_id, patient_id, frame_id, emotion,
                action_units, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (id, session_id, patient_id, frame_id, emotion,
             json.dumps(action_units), confidence),
        )
        await self._db.commit()

    async def get_face_analyses(self, session_id: str) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT * FROM face_analyses WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["action_units"] = json.loads(d["action_units"])
            result.append(d)
        return result

    # ------------------------------------------------------------------
    # Sensor readings
    # ------------------------------------------------------------------

    async def create_sensor_reading(
        self, *, id: str, session_id: str, patient_id: str,
        sensor_type: str, value: float, unit: str,
    ) -> None:
        await self._db.execute(
            """INSERT INTO sensor_readings
               (id, session_id, patient_id, sensor_type, value, unit)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (id, session_id, patient_id, sensor_type, value, unit),
        )
        await self._db.commit()

    async def get_sensor_readings(
        self, session_id: str, *, sensor_type: str | None = None,
    ) -> list[dict]:
        if sensor_type:
            cursor = await self._db.execute(
                """SELECT * FROM sensor_readings
                   WHERE session_id = ? AND sensor_type = ?
                   ORDER BY created_at""",
                (session_id, sensor_type),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM sensor_readings WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Fused emotions
    # ------------------------------------------------------------------

    async def create_fused_emotion(
        self, *, id: str, session_id: str, patient_id: str,
        fused_emotion: str, fused_valence: float, fused_arousal: float,
        confidence: float, modalities_available: list[str],
        text_emotion: str | None = None, voice_emotion: str | None = None,
        face_emotion: str | None = None, physiological_state: str | None = None,
    ) -> None:
        await self._db.execute(
            """INSERT INTO fused_emotions
               (id, session_id, patient_id, text_emotion, voice_emotion,
                face_emotion, physiological_state, fused_emotion,
                fused_valence, fused_arousal, confidence, modalities_available)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (id, session_id, patient_id, text_emotion, voice_emotion,
             face_emotion, physiological_state, fused_emotion,
             fused_valence, fused_arousal, confidence,
             json.dumps(modalities_available)),
        )
        await self._db.commit()

    async def get_fused_emotions(self, session_id: str) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT * FROM fused_emotions WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["modalities_available"] = json.loads(d["modalities_available"])
            result.append(d)
        return result
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_multimodal_state.py -v`
Expected: PASS (10 tests)

**Step 5: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All existing 494+ tests pass, 0 failures

**Step 6: Commit**

```
feat(state): multimodal storage tables — audio, face, sensor, fused emotion
```

---

## Task 4: Sensor Simulator

### Context
The SensorSimulator generates realistic physiological data (HR, GSR, SpO2) and publishes `SENSOR_READING` events to the EventBus. This replaces real hardware for testing and development. Configurable presets model different emotional states.

### Files
- Create: `ada/sensors/__init__.py`
- Create: `ada/sensors/simulator.py`
- Create: `tests/unit/test_sensor_simulator.py`

### Steps

**Step 1: Write failing tests**

Create `tests/unit/test_sensor_simulator.py`:

```python
"""Tests for SensorSimulator."""

from __future__ import annotations

import asyncio

import pytest

from ada.core.bus import EventBus
from ada.core.events import EventTypes, SensorReadingEvent
from ada.sensors.simulator import SensorSimulator


@pytest.fixture
async def bus():
    b = EventBus()
    await b.start()
    yield b
    await b.stop()


class TestSensorSimulator:
    def test_default_presets(self):
        sim = SensorSimulator()
        assert "relaxed" in sim.presets
        assert "anxious" in sim.presets
        assert "panic_attack" in sim.presets

    def test_preset_has_all_sensor_types(self):
        sim = SensorSimulator()
        for preset_name, preset in sim.presets.items():
            assert "hr" in preset, f"Missing hr in {preset_name}"
            assert "gsr" in preset, f"Missing gsr in {preset_name}"
            assert "spo2" in preset, f"Missing spo2 in {preset_name}"

    async def test_generate_single_reading(self, bus: EventBus):
        sim = SensorSimulator(bus=bus)
        collected: list[SensorReadingEvent] = []

        async def on_reading(event: SensorReadingEvent):
            collected.append(event)

        bus.subscribe(EventTypes.SENSOR_READING, on_reading, "test")

        await sim.emit_reading(
            session_id="s1", patient_id="p1",
            sensor_type="hr", value=72.0, unit="bpm",
        )
        await asyncio.sleep(0.05)

        assert len(collected) == 1
        assert collected[0].sensor_type == "hr"
        assert collected[0].value == 72.0

    async def test_generate_preset_stream(self, bus: EventBus):
        sim = SensorSimulator(bus=bus)
        collected: list[SensorReadingEvent] = []

        async def on_reading(event: SensorReadingEvent):
            collected.append(event)

        bus.subscribe(EventTypes.SENSOR_READING, on_reading, "test")

        # Generate 3 readings at 10Hz (0.3s)
        await sim.generate_stream(
            session_id="s1", patient_id="p1",
            preset="relaxed", num_readings=3, interval_s=0.05,
        )
        await asyncio.sleep(0.1)

        # 3 readings × 3 sensor types = 9 events
        assert len(collected) == 9
        sensor_types = {e.sensor_type for e in collected}
        assert sensor_types == {"hr", "gsr", "spo2"}

    async def test_relaxed_preset_ranges(self, bus: EventBus):
        sim = SensorSimulator(bus=bus)
        collected: list[SensorReadingEvent] = []

        async def on_reading(event: SensorReadingEvent):
            collected.append(event)

        bus.subscribe(EventTypes.SENSOR_READING, on_reading, "test")

        await sim.generate_stream(
            session_id="s1", patient_id="p1",
            preset="relaxed", num_readings=10, interval_s=0.01,
        )
        await asyncio.sleep(0.2)

        hr_values = [e.value for e in collected if e.sensor_type == "hr"]
        for v in hr_values:
            assert 55 <= v <= 85, f"Relaxed HR {v} out of range"

    async def test_panic_preset_elevated(self, bus: EventBus):
        sim = SensorSimulator(bus=bus)
        collected: list[SensorReadingEvent] = []

        async def on_reading(event: SensorReadingEvent):
            collected.append(event)

        bus.subscribe(EventTypes.SENSOR_READING, on_reading, "test")

        await sim.generate_stream(
            session_id="s1", patient_id="p1",
            preset="panic_attack", num_readings=10, interval_s=0.01,
        )
        await asyncio.sleep(0.2)

        hr_values = [e.value for e in collected if e.sensor_type == "hr"]
        for v in hr_values:
            assert v >= 100, f"Panic HR {v} too low"

    async def test_stop_stream(self, bus: EventBus):
        sim = SensorSimulator(bus=bus)
        collected: list[SensorReadingEvent] = []

        async def on_reading(event: SensorReadingEvent):
            collected.append(event)

        bus.subscribe(EventTypes.SENSOR_READING, on_reading, "test")

        task = asyncio.create_task(
            sim.generate_stream(
                session_id="s1", patient_id="p1",
                preset="relaxed", num_readings=1000, interval_s=0.01,
            )
        )
        await asyncio.sleep(0.05)
        sim.stop()
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should have stopped early — far fewer than 3000 events
        assert len(collected) < 100
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_sensor_simulator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ada.sensors'`

**Step 3: Create the module**

Create `ada/sensors/__init__.py`:

```python
```

Create `ada/sensors/simulator.py`:

```python
"""
Sensor simulator for generating realistic physiological data streams.

Produces SENSOR_READING events via EventBus with configurable presets
modelling different emotional/physiological states. Swappable for real
IoT gateway without changing any consumer code.

@decision DEC-MULTIMODAL-004
@title Simulated sensors first, real IoT gateway later
@status accepted
@rationale Proves the full data pipeline architecture without requiring
    physical hardware. Presets generate clinically-plausible ranges so
    downstream agents (PhysiologicalAgent, FusionAgent) can be tested
    under realistic conditions.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Any

from ada.core.bus import EventBus
from ada.core.events import EventTypes, SensorReadingEvent


@dataclass
class SensorPreset:
    """Value ranges for a single sensor type within a preset."""

    mean: float
    std: float
    min_val: float
    max_val: float
    unit: str


# Clinically-plausible ranges based on published stress response data
_PRESETS: dict[str, dict[str, SensorPreset]] = {
    "relaxed": {
        "hr": SensorPreset(mean=68.0, std=4.0, min_val=55.0, max_val=85.0, unit="bpm"),
        "gsr": SensorPreset(mean=2.0, std=0.3, min_val=1.0, max_val=4.0, unit="μS"),
        "spo2": SensorPreset(mean=98.0, std=0.5, min_val=96.0, max_val=100.0, unit="%"),
    },
    "anxious": {
        "hr": SensorPreset(mean=88.0, std=6.0, min_val=75.0, max_val=110.0, unit="bpm"),
        "gsr": SensorPreset(mean=5.0, std=1.0, min_val=3.0, max_val=10.0, unit="μS"),
        "spo2": SensorPreset(mean=97.0, std=0.8, min_val=94.0, max_val=99.0, unit="%"),
    },
    "panic_attack": {
        "hr": SensorPreset(mean=125.0, std=10.0, min_val=100.0, max_val=160.0, unit="bpm"),
        "gsr": SensorPreset(mean=10.0, std=2.0, min_val=6.0, max_val=18.0, unit="μS"),
        "spo2": SensorPreset(mean=95.0, std=1.5, min_val=90.0, max_val=98.0, unit="%"),
    },
}


class SensorSimulator:
    """Generates realistic physiological sensor data streams.

    Usage:
        sim = SensorSimulator(bus=event_bus)
        await sim.generate_stream(session_id, patient_id, preset="relaxed", num_readings=100)
    """

    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus = bus
        self._running = False

    @property
    def presets(self) -> dict[str, dict[str, SensorPreset]]:
        return _PRESETS

    async def emit_reading(
        self, *, session_id: str, patient_id: str,
        sensor_type: str, value: float, unit: str,
    ) -> None:
        """Publish a single sensor reading event."""
        if self._bus is None:
            raise RuntimeError("SensorSimulator requires an EventBus")
        await self._bus.publish(
            SensorReadingEvent(
                source="sensor_simulator",
                session_id=session_id,
                patient_id=patient_id,
                sensor_type=sensor_type,
                value=round(value, 1),
                unit=unit,
            )
        )

    async def generate_stream(
        self, *, session_id: str, patient_id: str,
        preset: str = "relaxed", num_readings: int = 100,
        interval_s: float = 1.0,
    ) -> None:
        """Generate a stream of sensor readings from a preset."""
        if preset not in _PRESETS:
            raise ValueError(f"Unknown preset: {preset}. Choose from {list(_PRESETS.keys())}")

        self._running = True
        preset_config = _PRESETS[preset]

        for _ in range(num_readings):
            if not self._running:
                break

            for sensor_type, sp in preset_config.items():
                value = random.gauss(sp.mean, sp.std)
                value = max(sp.min_val, min(sp.max_val, value))
                await self.emit_reading(
                    session_id=session_id,
                    patient_id=patient_id,
                    sensor_type=sensor_type,
                    value=value,
                    unit=sp.unit,
                )

            await asyncio.sleep(interval_s)

    def stop(self) -> None:
        """Stop the current stream generation."""
        self._running = False
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_sensor_simulator.py -v`
Expected: PASS (7 tests)

**Step 5: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All pass

**Step 6: Commit**

```
feat(sensors): SensorSimulator — realistic physiological data streams
```

---

## Task 5: Media WebSocket Endpoint

### Context
A new WebSocket endpoint at `/ws/media/{session_id}` handles multiplexed binary data (audio chunks, video frames, sensor readings). Uses the same JWT auth handshake pattern as `/ws/chat/`. Publishes events to EventBus for downstream agents.

### Files
- Create: `ada/api/routes/media.py`
- Modify: `ada/api/app.py` — include media router
- Create: `tests/unit/test_media_ws.py`

### Steps

**Step 1: Write failing tests**

Create `tests/unit/test_media_ws.py`:

```python
"""Tests for media WebSocket endpoint."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from ada.api.app import create_app
from ada.agents.registry import AgentRegistry
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import EventTypes, SensorReadingEvent, VoiceAnalyzedEvent
from ada.core.state import StateManager


@pytest.fixture
async def setup():
    config = AdaConfig()
    config.auth.enabled = False
    state = StateManager(":memory:")
    await state.initialize()
    bus = EventBus()
    await bus.start()
    registry = AgentRegistry(bus, config, state, None)
    app = create_app(config, bus, state, registry)
    yield app, bus, state, config
    await bus.stop()
    await state.close()


class TestMediaWebSocket:
    def test_media_route_exists(self, setup):
        app, bus, state, config = setup
        # Route should be registered
        routes = [r.path for r in app.routes]
        assert "/ws/media/{session_id}" in routes

    async def test_sensor_data_publishes_event(self, setup):
        app, bus, state, config = setup
        collected: list[SensorReadingEvent] = []

        async def on_reading(event):
            collected.append(event)

        bus.subscribe(EventTypes.SENSOR_READING, on_reading, "test")

        with TestClient(app) as client:
            with client.websocket_connect("/ws/media/test-session") as ws:
                # Auth handshake (disabled in test config)
                ws.send_json({"type": "auth", "token": "test"})

                # Send sensor data
                ws.send_json({
                    "type": "sensor_data",
                    "sensor_type": "hr",
                    "value": 72.0,
                    "unit": "bpm",
                    "patient_id": "p1",
                })

        await asyncio.sleep(0.1)
        assert len(collected) >= 1
        assert collected[0].sensor_type == "hr"

    async def test_audio_chunk_accepted(self, setup):
        app, bus, state, config = setup

        with TestClient(app) as client:
            with client.websocket_connect("/ws/media/test-session") as ws:
                ws.send_json({"type": "auth", "token": "test"})

                # Send audio metadata + binary
                ws.send_json({
                    "type": "audio_chunk",
                    "patient_id": "p1",
                    "metadata": {
                        "codec": "webm/opus",
                        "sample_rate": 48000,
                    },
                })
                ws.send_bytes(b"\x00" * 1024)  # Simulated audio data

                # Should get acknowledgement
                response = ws.receive_json()
                assert response["type"] == "ack"

    async def test_video_frame_accepted(self, setup):
        app, bus, state, config = setup

        with TestClient(app) as client:
            with client.websocket_connect("/ws/media/test-session") as ws:
                ws.send_json({"type": "auth", "token": "test"})

                ws.send_json({
                    "type": "video_frame",
                    "patient_id": "p1",
                    "metadata": {
                        "resolution": "640x480",
                        "format": "jpeg",
                    },
                })
                ws.send_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # JPEG header

                response = ws.receive_json()
                assert response["type"] == "ack"

    async def test_unknown_type_returns_error(self, setup):
        app, bus, state, config = setup

        with TestClient(app) as client:
            with client.websocket_connect("/ws/media/test-session") as ws:
                ws.send_json({"type": "auth", "token": "test"})
                ws.send_json({"type": "unknown_data", "patient_id": "p1"})

                response = ws.receive_json()
                assert response["type"] == "error"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_media_ws.py -v`
Expected: FAIL — `ImportError` (media module doesn't exist)

**Step 3: Implement the media WebSocket endpoint**

Create `ada/api/routes/media.py`:

```python
"""
WebSocket media endpoint — /ws/media/{session_id}.

Handles multiplexed binary data: audio chunks, video frames, and sensor
readings. Separate from /ws/chat/ to prevent media backpressure from
blocking text chat.

@decision DEC-MULTIMODAL-001
@title Separate /ws/media/ from /ws/chat/
@status accepted
@rationale Media streams (audio at ~100ms chunks, video at ~1fps) generate
    high-frequency data that could block the chat WebSocket's response
    queue. Separate connections allow independent failure and flow control.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from ada.core.events import (
    EventTypes,
    SensorReadingEvent,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["media"])


@router.websocket("/ws/media/{session_id}")
async def media_websocket(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket endpoint for streaming media data.

    Protocol:
        1. Client sends auth: {"type": "auth", "token": "<JWT>"}
        2. Client sends JSON header: {"type": "audio_chunk"|"video_frame"|"sensor_data", ...}
        3. For audio/video: client follows with binary frame
        4. Server responds: {"type": "ack", "id": "<chunk_id>"} or {"type": "error", ...}

    Sensor data is JSON-only (no binary payload needed).
    """
    await websocket.accept()
    logger.info("Media WS: session %s connected", session_id)

    # --- Auth handshake ---
    config = websocket.app.state.config
    if config.auth.enabled:
        from ada.api.auth import decode_token
        try:
            raw_auth = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            auth_msg = json.loads(raw_auth)
            if auth_msg.get("type") != "auth" or not auth_msg.get("token"):
                raise ValueError("Missing auth type or token")
            token = auth_msg["token"]
            decode_token(token, config.auth.secret_key, config.auth.algorithm)
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("Media WS: auth failed for session %s — %s", session_id, exc)
            await websocket.close(code=4001)
            return
    else:
        # Consume auth message even when disabled (test compatibility)
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
        except (asyncio.TimeoutError, Exception):
            pass

    bus = websocket.app.state.bus
    pending_binary: dict | None = None  # Holds metadata while awaiting binary frame

    try:
        while True:
            try:
                message = await websocket.receive()
            except WebSocketDisconnect:
                break

            if "text" in message:
                data = json.loads(message["text"])
                msg_type = data.get("type", "")

                if msg_type == "sensor_data":
                    await _handle_sensor(bus, session_id, data)
                    await _send_ack(websocket, str(uuid.uuid4()))

                elif msg_type in ("audio_chunk", "video_frame"):
                    # Store metadata, wait for binary payload
                    pending_binary = data
                    pending_binary["_session_id"] = session_id

                else:
                    await _send_error(websocket, f"Unknown type: {msg_type}")

            elif "bytes" in message and pending_binary is not None:
                chunk_id = str(uuid.uuid4())
                msg_type = pending_binary.get("type", "")

                if msg_type == "audio_chunk":
                    await _handle_audio(bus, session_id, pending_binary, message["bytes"], chunk_id)
                elif msg_type == "video_frame":
                    await _handle_video(bus, session_id, pending_binary, message["bytes"], chunk_id)

                pending_binary = None
                await _send_ack(websocket, chunk_id)

    except Exception:
        logger.exception("Media WS: unhandled error in session %s", session_id)
    finally:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()
        logger.info("Media WS: session %s disconnected", session_id)


async def _handle_sensor(bus, session_id: str, data: dict) -> None:
    """Publish sensor reading event."""
    await bus.publish(
        SensorReadingEvent(
            source="media_ws",
            session_id=session_id,
            patient_id=data.get("patient_id", ""),
            sensor_type=data.get("sensor_type", ""),
            value=float(data.get("value", 0)),
            unit=data.get("unit", ""),
        )
    )


async def _handle_audio(bus, session_id: str, metadata: dict, audio_bytes: bytes, chunk_id: str) -> None:
    """Store audio chunk metadata. Actual ML processing happens in Phase 4b."""
    logger.debug(
        "Media WS: audio chunk %s (%d bytes, %s)",
        chunk_id, len(audio_bytes),
        metadata.get("metadata", {}).get("codec", "unknown"),
    )
    # Phase 4b: VoiceEmotionAgent will process audio_bytes
    # For now, just log receipt. The binary data is available for agents
    # that subscribe to a future AUDIO_CHUNK_RECEIVED event.


async def _handle_video(bus, session_id: str, metadata: dict, frame_bytes: bytes, chunk_id: str) -> None:
    """Store video frame metadata. Actual ML processing happens in Phase 4b."""
    logger.debug(
        "Media WS: video frame %s (%d bytes, %s)",
        chunk_id, len(frame_bytes),
        metadata.get("metadata", {}).get("format", "unknown"),
    )
    # Phase 4b: FacialEmotionAgent will process frame_bytes


async def _send_ack(websocket: WebSocket, chunk_id: str) -> None:
    try:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json({"type": "ack", "id": chunk_id})
    except Exception:
        pass


async def _send_error(websocket: WebSocket, detail: str) -> None:
    try:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json({"type": "error", "detail": detail})
    except Exception:
        pass
```

**Step 4: Register the router in app.py**

In `ada/api/app.py`, add the import:

```python
from ada.api.routes import appointments, assessments, auth, chat, cognitive, knowledge, medications, media, patients, sessions
```

And add the router inclusion after the chat router:

```python
    app.include_router(media.router)
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_media_ws.py -v`
Expected: PASS (5 tests)

**Step 6: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All pass

**Step 7: Commit**

```
feat(api): media WebSocket endpoint — binary audio/video/sensor ingest
```

---

## Task 6: REST Fallback Endpoints

### Context
REST endpoints for non-WebSocket clients to upload audio, video frames, and sensor data. These complement the media WebSocket for batch uploads and simpler integrations.

### Files
- Modify: `ada/api/routes/media.py` — add REST endpoints
- Create: `tests/unit/test_media_rest.py`

### Steps

**Step 1: Write failing tests**

Create `tests/unit/test_media_rest.py`:

```python
"""Tests for media REST fallback endpoints."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from ada.api.app import create_app
from ada.agents.registry import AgentRegistry
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import EventTypes, SensorReadingEvent
from ada.core.state import StateManager


@pytest.fixture
async def client_setup():
    config = AdaConfig()
    config.auth.enabled = False
    state = StateManager(":memory:")
    await state.initialize()
    bus = EventBus()
    await bus.start()
    registry = AgentRegistry(bus, config, state, None)
    app = create_app(config, bus, state, registry)
    client = TestClient(app)
    yield client, bus, state
    await bus.stop()
    await state.close()


class TestSensorEndpoint:
    def test_post_sensor_reading(self, client_setup):
        client, bus, state = client_setup
        response = client.post(
            "/api/sessions/s1/sensor",
            json={
                "sensor_type": "hr",
                "value": 72.0,
                "unit": "bpm",
                "patient_id": "p1",
            },
        )
        assert response.status_code == 201
        assert response.json()["sensor_type"] == "hr"

    def test_post_sensor_invalid_type(self, client_setup):
        client, bus, state = client_setup
        response = client.post(
            "/api/sessions/s1/sensor",
            json={
                "sensor_type": "invalid",
                "value": 1.0,
                "unit": "x",
                "patient_id": "p1",
            },
        )
        assert response.status_code == 422


class TestAudioEndpoint:
    def test_post_audio_chunk(self, client_setup):
        client, bus, state = client_setup
        response = client.post(
            "/api/sessions/s1/audio",
            files={"file": ("chunk.webm", b"\x00" * 1024, "audio/webm")},
            data={"patient_id": "p1"},
        )
        assert response.status_code == 201
        assert "chunk_id" in response.json()


class TestVideoFrameEndpoint:
    def test_post_video_frame(self, client_setup):
        client, bus, state = client_setup
        response = client.post(
            "/api/sessions/s1/video-frame",
            files={"file": ("frame.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 100, "image/jpeg")},
            data={"patient_id": "p1"},
        )
        assert response.status_code == 201
        assert "frame_id" in response.json()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_media_rest.py -v`
Expected: FAIL — 404 (routes don't exist yet)

**Step 3: Add REST endpoints to media.py**

Add to `ada/api/routes/media.py` (using a separate REST router):

```python
from fastapi import APIRouter, File, Form, Request, UploadFile

rest_router = APIRouter(tags=["media"], prefix="/api")


@rest_router.post("/sessions/{session_id}/sensor", status_code=201)
async def post_sensor_reading(
    session_id: str,
    request: Request,
    sensor_type: str = "",
    value: float = 0.0,
    unit: str = "",
    patient_id: str = "",
) -> dict:
    """Post a single sensor reading via REST."""
    body = await request.json()
    sensor_type = body.get("sensor_type", sensor_type)
    value = body.get("value", value)
    unit = body.get("unit", unit)
    patient_id = body.get("patient_id", patient_id)

    valid_types = {"hr", "gsr", "spo2"}
    if sensor_type not in valid_types:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"sensor_type must be one of {valid_types}")

    bus = request.app.state.bus
    reading_id = str(uuid.uuid4())

    await bus.publish(
        SensorReadingEvent(
            source="rest_api",
            session_id=session_id,
            patient_id=patient_id,
            sensor_type=sensor_type,
            value=value,
            unit=unit,
        )
    )

    return {"id": reading_id, "sensor_type": sensor_type, "value": value, "unit": unit}


@rest_router.post("/sessions/{session_id}/audio", status_code=201)
async def post_audio_chunk(
    session_id: str,
    request: Request,
    file: UploadFile = File(...),
    patient_id: str = Form(""),
) -> dict:
    """Upload an audio chunk via REST (multipart/form-data)."""
    audio_bytes = await file.read()
    chunk_id = str(uuid.uuid4())

    logger.debug("REST: audio chunk %s (%d bytes)", chunk_id, len(audio_bytes))
    # Phase 4b: VoiceEmotionAgent will process audio_bytes

    return {"chunk_id": chunk_id, "size_bytes": len(audio_bytes), "session_id": session_id}


@rest_router.post("/sessions/{session_id}/video-frame", status_code=201)
async def post_video_frame(
    session_id: str,
    request: Request,
    file: UploadFile = File(...),
    patient_id: str = Form(""),
) -> dict:
    """Upload a video frame via REST (multipart/form-data)."""
    frame_bytes = await file.read()
    frame_id = str(uuid.uuid4())

    logger.debug("REST: video frame %s (%d bytes)", frame_id, len(frame_bytes))
    # Phase 4b: FacialEmotionAgent will process frame_bytes

    return {"frame_id": frame_id, "size_bytes": len(frame_bytes), "session_id": session_id}
```

Update `ada/api/app.py` to include the REST router:

```python
    app.include_router(media.rest_router)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_media_rest.py -v`
Expected: PASS (4 tests)

**Step 5: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All pass

**Step 6: Commit**

```
feat(api): REST fallback endpoints for audio, video, and sensor upload
```

---

## Task 7: PWA Shell

### Context
Add PWA manifest, service worker, and responsive layout to make Ada installable on mobile. Uses `vite-plugin-pwa` for service worker generation.

### Files
- Create: `web/public/manifest.json`
- Modify: `web/vite.config.ts` — add vite-plugin-pwa
- Modify: `web/public/index.html` (if exists) or `web/index.html` — add manifest link
- Modify: `web/package.json` — add vite-plugin-pwa dependency

### Steps

**Step 1: Install vite-plugin-pwa**

Run: `cd web && npm install vite-plugin-pwa -D`

**Step 2: Create PWA manifest**

Create `web/public/manifest.json`:

```json
{
  "name": "Ada — Mental Health AI",
  "short_name": "Ada",
  "description": "Multi-agent AI system for conversational therapy and mental health support",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#1a1a2e",
  "theme_color": "#16213e",
  "orientation": "portrait-primary",
  "icons": [
    {
      "src": "/ada-192.png",
      "sizes": "192x192",
      "type": "image/png"
    },
    {
      "src": "/ada-512.png",
      "sizes": "512x512",
      "type": "image/png"
    }
  ]
}
```

**Step 3: Create placeholder icons**

Run: `cd web/public && python3 -c "
# Generate minimal valid PNGs as placeholders
import struct, zlib
def make_png(size, color=(22, 33, 62)):
    width = height = size
    raw = b''
    for y in range(height):
        raw += b'\x00'  # filter byte
        for x in range(width):
            raw += bytes(color) + b'\xff'
    compressed = zlib.compress(raw)
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' +
            chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', compressed) +
            chunk(b'IEND', b''))
open('ada-192.png', 'wb').write(make_png(192))
open('ada-512.png', 'wb').write(make_png(512))
print('Created placeholder icons')
"`

**Step 4: Update vite.config.ts**

Replace `web/vite.config.ts`:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: false, // Using static manifest.json
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg}'],
        runtimeCaching: [
          {
            urlPattern: /^https?:\/\/.*\/api\/.*/i,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: { maxEntries: 50, maxAgeSeconds: 300 },
            },
          },
        ],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
```

**Step 5: Add manifest link to index.html**

Check if `web/index.html` exists and add the manifest link in the `<head>`:

```html
<link rel="manifest" href="/manifest.json" />
<meta name="theme-color" content="#16213e" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
```

**Step 6: Verify frontend builds**

Run: `cd web && npm run build`
Expected: Build succeeds with service worker generated

**Step 7: Commit**

```
feat(web): PWA shell — manifest, service worker, installable on mobile
```

---

## Task 8: Config + Main Integration

### Context
Add multimodal-related configuration and wire SensorSimulator into `main.py` for optional startup.

### Files
- Modify: `ada/core/config.py` — add multimodal config section
- Modify: `ada/main.py` — optional SensorSimulator setup
- Create: `tests/unit/test_multimodal_config.py`

### Steps

**Step 1: Write failing test for config**

Create `tests/unit/test_multimodal_config.py`:

```python
"""Tests for multimodal configuration."""

from __future__ import annotations

from ada.core.config import AdaConfig, MultimodalConfig


class TestMultimodalConfig:
    def test_default_disabled(self):
        config = AdaConfig()
        assert config.multimodal.enabled is False

    def test_sensor_simulator_defaults(self):
        config = AdaConfig()
        assert config.multimodal.sensor_simulator_preset == "relaxed"
        assert config.multimodal.sensor_simulator_interval == 1.0

    def test_media_ws_enabled_when_multimodal_enabled(self):
        config = AdaConfig(multimodal=MultimodalConfig(enabled=True))
        assert config.multimodal.enabled is True
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_multimodal_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'MultimodalConfig'`

**Step 3: Add MultimodalConfig to config.py**

Add after `AgentsConfig`:

```python
class MultimodalConfig(BaseModel):
    """Phase 4 multimodal pipeline configuration."""

    enabled: bool = False  # Off by default until Phase 4b ML agents are ready
    sensor_simulator_preset: str = "relaxed"
    sensor_simulator_interval: float = 1.0  # seconds between readings
```

Add to `AdaConfig`:

```python
    multimodal: MultimodalConfig = MultimodalConfig()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_multimodal_config.py -v`
Expected: PASS (3 tests)

**Step 5: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All pass

**Step 6: Commit**

```
feat(config): multimodal configuration section for Phase 4
```

---

## Task 9: Integration Tests

### Context
End-to-end tests verifying the full multimodal pipeline: sensor simulator → EventBus → storage, media WS → EventBus, REST → EventBus.

### Files
- Create: `tests/integration/test_multimodal_pipeline.py`

### Steps

**Step 1: Write integration tests**

Create `tests/integration/test_multimodal_pipeline.py`:

```python
"""Integration tests for the multimodal pipeline."""

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

        # Subscribe to persist readings
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

        # Generate 3 readings
        await sim.generate_stream(
            session_id="s1", patient_id="p1",
            preset="relaxed", num_readings=3, interval_s=0.01,
        )
        await asyncio.sleep(0.2)

        # 3 readings × 3 sensor types = 9 rows
        rows = await state.get_sensor_readings("s1")
        assert len(rows) == 9

        # Check each type is present
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
```

**Step 2: Run integration tests**

Run: `pytest tests/integration/test_multimodal_pipeline.py -v`
Expected: PASS (5 tests)

**Step 3: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All 494+ existing tests pass + ~50 new tests

**Step 4: Commit**

```
test(integration): multimodal pipeline end-to-end tests
```

---

## Task 10: Final Verification & Commit

### Steps

**Step 1: Run the full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: ~540+ tests pass, 0 failures

**Step 2: Verify no regressions in existing functionality**

Run: `pytest tests/unit/test_therapist.py tests/unit/test_emotion_analyzer.py tests/integration/test_knowledge_flow.py -v`
Expected: All pass (Phase 3 agents unaffected)

**Step 3: Verify frontend builds**

Run: `cd web && npm run build`
Expected: Build succeeds, dist/ contains service worker

**Step 4: Final commit if any fixes needed**

```
fix: integration fixes for Phase 4a multimodal infrastructure
```

---

## Verification Checklist

1. **Unit tests:** `pytest tests/unit/test_multimodal_*.py tests/unit/test_sensor_simulator.py tests/unit/test_media_*.py -v`
2. **Integration tests:** `pytest tests/integration/test_multimodal_pipeline.py -v`
3. **Regression:** `pytest tests/ -v --tb=short` — all 494+ existing tests still pass
4. **Frontend:** `cd web && npm run build` — PWA build succeeds
5. **Models:** Pydantic validation works for all 4 multimodal models
6. **Events:** 5 new event types registered, dataclasses instantiate correctly
7. **Storage:** 4 new tables with CRUD methods work (in-memory SQLite)
8. **Sensor simulator:** Generates realistic data for 3 presets
9. **Media WS:** Accepts auth, sensor data, audio chunks, video frames
10. **REST:** Audio upload, video frame upload, sensor POST all return 201
