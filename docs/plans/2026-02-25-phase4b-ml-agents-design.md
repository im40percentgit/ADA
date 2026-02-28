# Phase 4b — ML Emotion Agents Design

**Goal:** Three new BaseAgent subclasses that extract features from audio, video, and physiological sensor data, then classify emotional/stress states via LLM. Backend only — frontend media capture deferred to Phase 4c.

**Depends on:** Phase 4a infrastructure (event types, storage tables, media WebSocket, SensorSimulator).

**Tech Stack:** Python 3.12+, librosa (audio features), opencv-python-headless (face detection), numpy (sliding windows), Claude LLM (classification).

---

## Architecture

```
Audio bytes  → librosa feature extraction  → LLM classification → VoiceAnalyzedEvent  → audio_analyses DB
Video frame  → OpenCV face detection       → LLM classification → FaceAnalyzedEvent   → face_analyses DB
Sensor data  → sliding window aggregation  → LLM classification → SensorAlertEvent    → sensor alerts
```

All three agents follow the same pattern:
1. Subscribe to incoming data events via EventBus
2. Extract features using signal processing libraries
3. Send structured feature summary to Claude for emotion/state classification
4. Publish result events to EventBus
5. Persist results to existing Phase 4a storage tables

---

## Key Decisions

### DEC-ML-001: LLM classification over dedicated ML models
Feature extraction uses real signal processing (librosa, OpenCV) but the final classification step sends extracted features to Claude instead of wav2vec2/FER. This avoids ~2GB of model downloads, works on any CPU, and leverages Claude's clinical emotion understanding. The feature extraction layer is model-agnostic — dedicated ML models can be swapped in later as a performance optimization.

### DEC-ML-002: Backend agents only, no frontend
Phase 4b focuses on server-side processing. Frontend media capture (MediaCapture.tsx, VoiceIndicator.tsx, FaceOverlay.tsx) is deferred to Phase 4c. Agents are tested against fixture files and synthetic feature generators.

### DEC-ML-003: Three independent agents, fusion deferred
VoiceEmotionAgent, FacialEmotionAgent, and PhysiologicalAgent each produce signals independently. The MultimodalFusionAgent (which combines all signals into EMOTION_FUSED) is deferred to Phase 4c — it's architecturally different (consumes other agents' outputs) and deserves focused design.

---

## New Events

Phase 4a defined output events (VOICE_ANALYZED, FACE_ANALYZED). Phase 4b adds input trigger events:

| Event | Dataclass | Published By | Consumed By |
|-------|-----------|-------------|-------------|
| `AUDIO_CHUNK_RECEIVED` | `AudioChunkReceivedEvent` | Media WS `_handle_audio` | VoiceEmotionAgent |
| `VIDEO_FRAME_RECEIVED` | `VideoFrameReceivedEvent` | Media WS `_handle_video` | FacialEmotionAgent |
| `SENSOR_READING` | `SensorReadingEvent` | SensorSimulator / REST | PhysiologicalAgent |

### AudioChunkReceivedEvent
```python
@dataclass
class AudioChunkReceivedEvent(AdaEvent):
    event_type: str = EventTypes.AUDIO_CHUNK_RECEIVED
    session_id: str = ""
    patient_id: str = ""
    audio_bytes: bytes = b""
    codec: str = "webm/opus"
    sample_rate: int = 48000
    chunk_id: str = ""
```

### VideoFrameReceivedEvent
```python
@dataclass
class VideoFrameReceivedEvent(AdaEvent):
    event_type: str = EventTypes.VIDEO_FRAME_RECEIVED
    session_id: str = ""
    patient_id: str = ""
    frame_bytes: bytes = b""
    format: str = "jpeg"
    resolution: str = ""
    frame_id: str = ""
```

---

## Agents

### VoiceEmotionAgent

**Subscribes to:** `AUDIO_CHUNK_RECEIVED`
**Publishes:** `VOICE_ANALYZED`
**Persists to:** `audio_analyses` table

**Feature extraction** (`ada/ml/audio_features.py`):
- librosa.load() decodes audio bytes to waveform
- Pitch: librosa.pyin() → mean fundamental frequency (Hz)
- Energy: RMS energy → mean amplitude
- Speech rate: onset detection → syllables/sec estimate
- MFCCs: 13 coefficients for timbre characterization

**LLM classification prompt:**
```
Analyze these audio features from a therapy session:
- Pitch: {pitch_mean}Hz, Energy: {energy_mean}, Speech rate: {speech_rate} syl/sec
- MFCC summary: {mfcc_summary}
Classify emotional state using Plutchik's 8 emotions (joy, trust, fear, surprise,
sadness, disgust, anger, anticipation). Return JSON:
{"emotion": "...", "confidence": 0.0-1.0, "reasoning": "..."}
```

### FacialEmotionAgent

**Subscribes to:** `VIDEO_FRAME_RECEIVED`
**Publishes:** `FACE_ANALYZED`
**Persists to:** `face_analyses` table

**Feature extraction** (`ada/ml/face_features.py`):
- OpenCV DNN face detector (pre-trained Caffe model, ships with OpenCV)
- Facial landmark detection for action unit estimation
- Action units: AU1 (inner brow raise), AU2 (outer brow raise), AU4 (brow lowerer), AU5 (upper lid raise), AU6 (cheek raise), AU12 (lip corner pull), AU15 (lip corner depress)
- Values 0.0-1.0 estimated from landmark geometry ratios

**LLM classification prompt:**
```
Analyze these facial action units from a therapy session video frame:
- AU1 (inner brow raise): {au1}, AU2 (outer brow raise): {au2},
  AU4 (brow lowerer): {au4}, AU5 (upper lid raise): {au5},
  AU6 (cheek raise): {au6}, AU12 (lip corner pull): {au12},
  AU15 (lip corner depress): {au15}
- Face detected: {face_detected}, confidence: {detection_confidence}
Classify emotional state using Plutchik's 8 emotions. Return JSON:
{"emotion": "...", "action_units": {...}, "confidence": 0.0-1.0}
```

### PhysiologicalAgent

**Subscribes to:** `SENSOR_READING`
**Publishes:** `SENSOR_ALERT`
**Persists to:** reads from `sensor_readings`, publishes alerts

**Sliding window analysis:**
```python
# Per-session buffer: last N readings per sensor type
self._windows: dict[str, dict[str, deque[float]]]  # session_id → sensor_type → values
# Default window_size=30, trigger every 10 new readings
```

**LLM classification prompt:**
```
Analyze this physiological data window from a therapy session:
- HR trend: {hr_values} bpm (mean={hr_mean}, delta={hr_delta})
- GSR trend: {gsr_values} uS (mean={gsr_mean}, delta={gsr_delta})
- SpO2 trend: {spo2_values}% (mean={spo2_mean}, min={spo2_min})
Classify: stress_level (low/moderate/high/critical), arousal (0.0-1.0).
Flag alerts: hr_spike, gsr_spike, spo2_drop, rapid_change. Return JSON:
{"stress_level": "...", "arousal": 0.0, "alerts": [...], "reasoning": "..."}
```

---

## Config Additions

```toml
[multimodal]
enabled = false
sensor_simulator_preset = "relaxed"
sensor_simulator_interval = 1.0
# Phase 4b additions:
voice_analysis_enabled = true
face_analysis_enabled = true
physiological_analysis_enabled = true
physiological_window_size = 30
physiological_trigger_interval = 10
```

---

## Registration in main.py

```python
if config.multimodal.enabled:
    if config.multimodal.voice_analysis_enabled:
        registry.register(VoiceEmotionAgent())
    if config.multimodal.face_analysis_enabled:
        registry.register(FacialEmotionAgent())
    if config.multimodal.physiological_analysis_enabled:
        registry.register(PhysiologicalAgent())
```

---

## Modified Files

| File | Change |
|------|--------|
| `ada/core/events.py` | Add AUDIO_CHUNK_RECEIVED, VIDEO_FRAME_RECEIVED event types + dataclasses |
| `ada/api/routes/media.py` | Publish events from `_handle_audio` and `_handle_video` |
| `ada/core/config.py` | Extend MultimodalConfig with new fields |
| `config/default.toml` | Add new multimodal config keys |
| `ada/main.py` | Register ML agents when multimodal enabled |
| `ada/agents/__init__.py` | Export new agents |

## New Files

| File | Purpose |
|------|---------|
| `ada/ml/__init__.py` | ML module init |
| `ada/ml/audio_features.py` | librosa wrapper — pitch, energy, speech rate, MFCCs |
| `ada/ml/face_features.py` | OpenCV face detection + action unit estimation |
| `ada/agents/voice_emotion.py` | VoiceEmotionAgent (BaseAgent subclass) |
| `ada/agents/facial_emotion.py` | FacialEmotionAgent (BaseAgent subclass) |
| `ada/agents/physiological.py` | PhysiologicalAgent (BaseAgent subclass) |
| `tests/fixtures/test_audio.wav` | Short WAV for integration tests (~1s, 16kHz mono) |
| `tests/fixtures/test_face.jpg` | Face image for integration tests (small, synthetic) |
| `tests/unit/test_audio_features.py` | Audio feature extraction tests |
| `tests/unit/test_face_features.py` | Face feature extraction tests |
| `tests/unit/test_voice_emotion_agent.py` | VoiceEmotionAgent unit tests |
| `tests/unit/test_facial_emotion_agent.py` | FacialEmotionAgent unit tests |
| `tests/unit/test_physiological_agent.py` | PhysiologicalAgent unit tests |
| `tests/integration/test_ml_pipeline.py` | End-to-end ML pipeline tests |

## Dependencies

Add to `pyproject.toml` or `requirements.txt`:
- `librosa>=0.10` — audio feature extraction
- `opencv-python-headless>=4.8` — face detection without GUI deps
- `numpy>=1.24` — sliding windows, array ops (likely already a transitive dep)

---

## Testing Strategy

**Unit tests** — synthetic feature generators produce realistic feature dicts:
- `AudioFeatureGenerator` → pitch, energy, speech_rate, mfccs matching clinical ranges
- `FaceFeatureGenerator` → action unit values for known emotion expressions
- LLM stub returns canned classification responses

**Integration tests** — small fixture files (WAV, JPEG):
- Audio: 1s 16kHz mono WAV tone (provably extractable features)
- Face: synthetic face image (OpenCV-detectable)
- Full pipeline: fixture → feature extraction → LLM stub → event published → DB persisted

**Regression** — full `pytest` suite continues to pass (558+ existing tests unaffected)

---

## Verification Checklist

1. `pytest tests/unit/test_audio_features.py -v` — librosa extraction works
2. `pytest tests/unit/test_face_features.py -v` — OpenCV detection works
3. `pytest tests/unit/test_voice_emotion_agent.py -v` — agent publishes VoiceAnalyzedEvent
4. `pytest tests/unit/test_facial_emotion_agent.py -v` — agent publishes FaceAnalyzedEvent
5. `pytest tests/unit/test_physiological_agent.py -v` — sliding window + alerts work
6. `pytest tests/integration/test_ml_pipeline.py -v` — fixture → DB round-trip
7. `pytest tests/ --tb=short -q` — full suite passes (558 existing + ~40 new)
8. `cd web && npm run build` — frontend unaffected
