# Phase 4 Design: Multimodal & Mobile

**Issue:** TBD (create during implementation)
**Approach:** Infrastructure-first, hybrid edge+server ML, PWA for mobile
**Date:** 2026-02-24

## Sub-Phases

- **Phase 4a:** Multimodal Pipeline Infrastructure + PWA Shell
- **Phase 4b:** ML Agents (Voice + Face) + Frontend Components
- **Phase 4c:** Fusion Agent + Edge Inference + Physiological Agent

## Architecture

```
Phase 4a — Infrastructure
  ├─ Binary ingest API (media WebSocket + REST fallback)
  ├─ New event types + Pydantic models (multimodal signals)
  ├─ SensorSimulator (generates GSR/HR/SpO2 streams for testing)
  ├─ Multimodal storage tables (audio_analyses, face_analyses, sensor_readings, fused_emotions)
  └─ PWA shell (manifest, service worker, responsive layout)

Phase 4b — ML Agents
  ├─ VoiceEmotionAgent (BaseAgent)
  │   ├─ Server: librosa feature extraction + wav2vec2 SER model
  │   └─ Client: Web Audio API (pitch, energy, speech rate)
  ├─ FacialEmotionAgent (BaseAgent)
  │   ├─ Server: OpenCV + FER model (lightweight CNN)
  │   └─ Client: face-api.js (TF.js face detection + expression)
  └─ Camera/Microphone React components

Phase 4c — Fusion + Edge
  ├─ MultimodalFusionAgent (BaseAgent)
  │   └─ Subscribes to EMOTION_ANALYZED + VOICE_ANALYZED + FACE_ANALYZED + SENSOR_READING
  │      → Time-windowed buffer (5s) → weighted ensemble → EMOTION_FUSED
  ├─ PhysiologicalAgent (sensor anomaly detection → SENSOR_ALERT)
  ├─ Edge runtime (ONNX.js/TF.js models in browser)
  └─ IoT gateway protocol stub (for future real hardware)
```

Each modality produces its own event. The fusion agent listens to all of them and
produces a unified EMOTION_FUSED event that downstream agents (TherapistAgent,
CrisisMonitor) can consume.

## Data Model

### New Event Types

| Event | Payload Fields | Producer |
|-------|---------------|----------|
| `voice.analyzed` | session_id, audio_chunk_id, emotion, pitch_mean, energy, speech_rate, confidence | VoiceEmotionAgent |
| `face.analyzed` | session_id, frame_id, emotion, action_units, confidence | FacialEmotionAgent |
| `sensor.reading` | session_id, sensor_type (gsr/hr/spo2), value, timestamp | SensorSimulator / IoT gateway |
| `sensor.alert` | session_id, sensor_type, alert_type (spike/drop/threshold), value | PhysiologicalAgent |
| `emotion.fused` | session_id, text_emotion, voice_emotion, face_emotion, physiological_state, fused_emotion, fused_valence, fused_arousal, confidence, modalities_available | MultimodalFusionAgent |

### New Tables

| Table | Purpose |
|-------|---------|
| `audio_analyses` | Per-chunk voice emotion results (emotion, pitch, energy, speech_rate, confidence) |
| `face_analyses` | Per-frame facial emotion results (emotion, action_units JSON, confidence) |
| `sensor_readings` | Time-series sensor data (sensor_type, value, timestamp) |
| `fused_emotions` | Unified multimodal emotion snapshots (all modalities + fused result) |

### Pydantic Models

- `VoiceEmotionResult` — emotion, pitch_mean, energy_mean, speech_rate, confidence
- `FaceEmotionResult` — emotion, action_units (dict of AU intensities), confidence
- `SensorReading` — sensor_type, value, unit, timestamp
- `FusedEmotionResult` — extends EmotionResult with per-modality breakdown + modalities_available list

FusedEmotionResult is backward-compatible with EmotionResult — it adds fields but
any consumer expecting the base Plutchik's 8 + valence/arousal structure still works.

## Binary Ingest API

### Media WebSocket

```
WS /ws/media/{session_id}  →  Multiplexed binary + JSON frames

Frame format (JSON header + binary payload):
{
  "type": "audio_chunk" | "video_frame" | "sensor_data",
  "timestamp": "ISO8601",
  "metadata": { ...codec, sample_rate, resolution, sensor_type... }
}
followed by binary payload (audio bytes, JPEG frame, sensor packet)
```

Separate from `/ws/chat/` to prevent media backpressure from blocking chat
responsiveness. Either can fail independently.

### REST Fallback Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/sessions/{id}/audio` | POST | Upload audio chunk (multipart/form-data) |
| `/sessions/{id}/video-frame` | POST | Upload video frame (multipart/form-data) |
| `/sessions/{id}/sensor` | POST | Push sensor reading (JSON) |

## ML Pipeline

### Voice Emotion Recognition

Server-side:
```
Audio chunk (WAV/WebM) → librosa feature extraction
  → MFCCs, pitch (f0), energy, speech rate, spectral centroid
    → Pre-trained wav2vec2 SER model (HuggingFace)
      → VoiceEmotionResult → VOICE_ANALYZED event
```

- Model: wav2vec2-based SER from HuggingFace (CPU-friendly, no GPU required)
- Audio format: Browser captures WebM/Opus via MediaRecorder; server converts to WAV
- Client-side: Web Audio API extracts pitch, energy, speech rate as metadata

### Facial Emotion Recognition

Server-side:
```
Video frame (JPEG) → OpenCV face detection (Haar/DNN)
  → Crop face region → FER model (lightweight Keras CNN)
    → FaceEmotionResult → FACE_ANALYZED event
```

- Model: `fer` library (lightweight CNN) or MediaPipe Face Mesh
- Client-side: face-api.js (TF.js) at ~5-10fps for real-time UI overlay
- Server receives ~1fps JPEG frames for full model analysis

### Python Dependencies (new)

```
librosa                    # Audio feature extraction
soundfile                  # Audio I/O
transformers               # HuggingFace models (wav2vec2)
torch                      # PyTorch runtime (CPU)
opencv-python-headless     # Face detection (no GUI)
fer                        # Facial expression recognition
```

### Client Dependencies (new)

```
face-api.js                # Browser face detection + expression
vite-plugin-pwa            # PWA service worker generation
```

## Fusion Agent

### MultimodalFusionAgent

Subscribes to all modality events. Uses a 5-second time window to collect signals
around a message event. Not all modalities need to be present — missing modalities
are excluded, remaining weights renormalized.

Default weights: text=0.3, voice=0.3, face=0.25, physiological=0.15

Output: FusedEmotionResult with per-modality breakdown. Downstream agents subscribe
to EMOTION_FUSED instead of individual modality events.

### Sensor Simulator

Generates realistic physiological data streams for testing:
- GSR (galvanic skin response), HR (heart rate), SpO2 (blood oxygen)
- Configurable presets: "relaxed", "anxious", "panic_attack"
- Publishes SENSOR_READING events to EventBus — indistinguishable from real sensors
- Swappable for real gateway later without changing consumer code

### PhysiologicalAgent

- Rolling window analysis (mean, variance, rate of change)
- Anomaly detection: HR spike >30% above baseline, GSR rapid increase, SpO2 drop
- Publishes SENSOR_ALERT for crisis-relevant readings
- Maps physiological state to arousal dimension (feeds into fusion agent)

## PWA + Frontend

### PWA Infrastructure

- `web/public/manifest.json` — app name "Ada", icons, theme color, display: standalone
- `web/src/sw.ts` — service worker (app shell + API cache strategy)
- `vite-plugin-pwa` — generates service worker from Vite build
- Responsive layout updates to existing components
- Install prompt component ("Add Ada to Home Screen")

### New React Components

| Component | Purpose |
|-----------|---------|
| `MediaCapture.tsx` | Camera/mic permissions, MediaRecorder, WebSocket media connection |
| `VoiceIndicator.tsx` | Real-time audio visualization (waveform/energy bar) via Web Audio API |
| `FaceOverlay.tsx` | Camera preview with face-api.js detection overlay + expression label |
| `MultimodalDashboard.tsx` | All active modalities + fused emotion state in real-time |
| `SensorDisplay.tsx` | Real-time sensor readings (HR, GSR, SpO2) with sparkline charts |

### useMediaStream Hook

```typescript
useMediaStream(sessionId) → {
  startAudio(),     // Begin mic capture + audio chunk streaming
  startVideo(),     // Begin camera capture + frame streaming
  stopAll(),
  audioFeatures,    // Real-time client-side audio features
  faceDetection,    // Real-time client-side face detection result
  isConnected,
  permissions: { mic, camera }
}
```

### Client-Side Inference

- `web/src/ml/voice-features.ts` — Web Audio API pitch/energy extraction
- `web/src/ml/face-detect.ts` — face-api.js wrapper
- Models loaded lazily from `/static/models/` on first use (not bundled)

### Privacy

Camera and microphone are opt-in per session. Clear visual indicators when active.
No recording persisted client-side — frames/chunks streamed to server and discarded
after analysis.

## Decisions

- DEC-MULTIMODAL-001: Separate /ws/media/ from /ws/chat/ (prevents media backpressure from blocking chat)
- DEC-MULTIMODAL-002: Hybrid edge+server ML (lightweight client models for real-time feedback, full server models for accuracy)
- DEC-MULTIMODAL-003: MultimodalFusionAgent as weighted ensemble with time-windowed buffering (gracefully handles missing modalities)
- DEC-MULTIMODAL-004: Simulated sensors first, real IoT gateway later (proves architecture without hardware)
- DEC-MULTIMODAL-005: PWA first, React Native deferred to Phase 5 (fastest path to mobile access)
- DEC-MULTIMODAL-006: face-api.js for client-side face detection (TF.js-based, well-maintained, works in browser)
- DEC-MULTIMODAL-007: wav2vec2 SER from HuggingFace for voice emotion (CPU-friendly, pre-trained, no GPU required)
- DEC-MULTIMODAL-008: FER library for server-side facial expression recognition (lightweight Keras CNN, CPU-friendly)
- DEC-MULTIMODAL-009: Default fusion weights text=0.3, voice=0.3, face=0.25, physio=0.15 (text and voice carry most clinical signal in therapy)

## Files (Projected)

### Phase 4a — Infrastructure
| File | Action |
|------|--------|
| `ada/core/events.py` | Modify — add VOICE_ANALYZED, FACE_ANALYZED, SENSOR_READING, SENSOR_ALERT, EMOTION_FUSED |
| `ada/models/multimodal.py` | Create — VoiceEmotionResult, FaceEmotionResult, SensorReading, FusedEmotionResult |
| `ada/core/state.py` | Modify — add audio_analyses, face_analyses, sensor_readings, fused_emotions tables |
| `ada/api/routes/media.py` | Create — media WebSocket + REST fallback endpoints |
| `ada/sensors/simulator.py` | Create — SensorSimulator |
| `ada/sensors/__init__.py` | Create |
| `ada/core/config.py` | Modify — add multimodal config section |
| `web/public/manifest.json` | Create — PWA manifest |
| `web/src/sw.ts` | Create — service worker |
| `web/vite.config.ts` | Modify — add vite-plugin-pwa |

### Phase 4b — ML Agents
| File | Action |
|------|--------|
| `ada/agents/voice_emotion.py` | Create — VoiceEmotionAgent |
| `ada/agents/facial_emotion.py` | Create — FacialEmotionAgent |
| `ada/ml/__init__.py` | Create |
| `ada/ml/audio_features.py` | Create — librosa feature extraction |
| `ada/ml/face_features.py` | Create — OpenCV + FER pipeline |
| `ada/main.py` | Modify — register new agents |
| `web/src/components/MediaCapture.tsx` | Create |
| `web/src/components/VoiceIndicator.tsx` | Create |
| `web/src/components/FaceOverlay.tsx` | Create |
| `web/src/hooks/useMediaStream.ts` | Create |
| `web/src/ml/voice-features.ts` | Create |
| `web/src/ml/face-detect.ts` | Create |

### Phase 4c — Fusion + Edge
| File | Action |
|------|--------|
| `ada/agents/multimodal_fusion.py` | Create — MultimodalFusionAgent |
| `ada/agents/physiological.py` | Create — PhysiologicalAgent |
| `web/src/components/MultimodalDashboard.tsx` | Create |
| `web/src/components/SensorDisplay.tsx` | Create |
