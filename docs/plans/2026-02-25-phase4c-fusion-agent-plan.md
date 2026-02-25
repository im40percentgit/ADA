# Phase 4c — MultimodalFusionAgent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** MultimodalFusionAgent — deterministic weighted-average fusion of text, voice, face, and physiological emotion signals with exponential staleness decay.

**Architecture:**
```
EMOTION_ANALYZED (text) ──┐
VOICE_ANALYZED ───────────┤
FACE_ANALYZED ────────────┼──→ FusionAgent → weighted average → EMOTION_FUSED → fused_emotions DB
SENSOR_ALERT ─────────────┘
```

**Tech Stack:** Python 3.12+, no new dependencies. Pure math fusion.

**Decisions from design doc:**
- DEC-FUSION-001: Deterministic weighted average over LLM fusion
- DEC-FUSION-002: Trigger-on-any with staleness decay (no blocking on missing modalities)
- DEC-FUSION-003: Exponential staleness decay with half-life=10s
- DEC-FUSION-004: Backend fusion only, no frontend

---

## Existing Infrastructure (already built in Phase 4a)

These exist and must NOT be recreated:

| Artifact | Location | Notes |
|----------|----------|-------|
| `EventTypes.EMOTION_FUSED` | `ada/core/events.py:92` | String constant |
| `FusedEmotionEvent` | `ada/core/events.py:419-433` | Dataclass with text/voice/face/physio + fused fields |
| `FusedEmotionResult` | `ada/models/multimodal.py:64-93` | Pydantic model |
| `fused_emotions` table | `ada/core/state.py` | SQLite table with create/get methods |
| `state.create_fused_emotion()` | `ada/core/state.py:1238-1257` | Persistence method |
| `MultimodalConfig` | `ada/core/config.py:107-118` | Needs extending with fusion fields |

## Existing Patterns to Follow

- **BaseAgent ABC** (`ada/agents/base.py`): `__init__`, `name`, `description`, `supported_events`, `handle_event()`, lifecycle via `initialize(bus, config, state, llm)` then `start()`/`stop()`
- **PhysiologicalAgent** (`ada/agents/physiological.py`): Per-session buffer dict, event dispatch in `handle_event`, cleanup in `stop()`
- **Test pattern** (`tests/unit/test_physiological_agent.py`): `pytest_asyncio` fixtures, in-memory StateManager, real EventBus, `asyncio.sleep` for event propagation

---

## Task 1: Fusion Core — Pure Math Module

**File:** `ada/agents/fusion.py`
**Test file:** `tests/unit/test_fusion_agent.py`

Write the pure math functions first, with no agent logic. This keeps the fusion algorithm independently testable.

### Implementation

```python
# ada/agents/fusion.py — top section (before the agent class)

from __future__ import annotations

import logging
import math
import time
import uuid
from dataclasses import dataclass

from ada.agents.base import BaseAgent
from ada.core.events import (
    AdaEvent,
    EmotionAnalyzedEvent,
    EventTypes,
    FaceAnalyzedEvent,
    FusedEmotionEvent,
    SensorAlertEvent,
    VoiceAnalyzedEvent,
)

logger = logging.getLogger(__name__)
```

**ModalitySignal dataclass:**
```python
@dataclass
class ModalitySignal:
    """A single emotion signal from one modality."""
    emotion: str           # Plutchik emotion name
    valence: float         # -1.0 to 1.0
    arousal: float         # 0.0 to 1.0
    confidence: float      # 0.0 to 1.0
    timestamp: float       # time.monotonic()
    modality: str          # "text" | "voice" | "face" | "physiological"
```

**PLUTCHIK_MAP** — list of `(emotion, valence, arousal)` tuples. Used bidirectionally:
```python
PLUTCHIK_MAP: list[tuple[str, float, float]] = [
    ("joy",          0.8,  0.6),
    ("trust",        0.5,  0.3),
    ("fear",        -0.6,  0.8),
    ("surprise",     0.1,  0.9),
    ("sadness",     -0.7,  0.2),
    ("disgust",     -0.5,  0.5),
    ("anger",       -0.6,  0.7),
    ("anticipation", 0.4,  0.7),
]
```

**STRESS_TO_AROUSAL** mapping for physiological signals:
```python
STRESS_TO_AROUSAL: dict[str, float] = {
    "low": 0.2, "moderate": 0.5, "high": 0.7, "critical": 0.9,
}
```

**Pure functions to implement:**

1. `recency_weight(signal_age_seconds: float, half_life: float = 10.0) -> float`
   - Formula: `2 ** (-signal_age_seconds / half_life)`
   - Clamp to [0.0, 1.0] (age can be 0 or slightly negative due to clock)

2. `emotion_to_va(emotion: str) -> tuple[float, float]`
   - Look up emotion in PLUTCHIK_MAP (case-insensitive)
   - Return `(valence, arousal)`
   - If not found, return `(0.0, 0.5)` (neutral default)

3. `va_to_emotion(valence: float, arousal: float) -> str`
   - Find nearest Plutchik emotion by Euclidean distance in V-A space
   - Return the emotion name string

4. `fuse_signals(signals: list[ModalitySignal], now: float, half_life: float = 10.0, min_weight: float = 0.01) -> dict | None`
   - For each signal: `effective_weight = confidence * recency_weight(now - signal.timestamp, half_life)`
   - Filter out signals where `effective_weight < min_weight`
   - If no valid signals remain, return `None`
   - Compute weighted mean of valence and arousal
   - Map fused V/A to nearest emotion via `va_to_emotion()`
   - Compute overall confidence as: mean of effective weights
   - Return dict with keys: `fused_emotion`, `fused_valence`, `fused_arousal`, `confidence`, `modalities` (list of modality names that contributed)

### Tests for Task 1

**File:** `tests/unit/test_fusion_agent.py` — first section

Tests to write (all synchronous — pure math, no async needed):

1. **test_recency_weight_at_zero** — `recency_weight(0.0)` == 1.0
2. **test_recency_weight_at_half_life** — `recency_weight(10.0, half_life=10.0)` == 0.5
3. **test_recency_weight_at_double_half_life** — `recency_weight(20.0, half_life=10.0)` == 0.25
4. **test_recency_weight_negative_age_clamped** — `recency_weight(-1.0)` == 1.0 (clamped)
5. **test_emotion_to_va_known** — `emotion_to_va("joy")` == (0.8, 0.6)
6. **test_emotion_to_va_case_insensitive** — `emotion_to_va("JOY")` == (0.8, 0.6)
7. **test_emotion_to_va_unknown** — `emotion_to_va("boredom")` == (0.0, 0.5)
8. **test_va_to_emotion_exact** — `va_to_emotion(0.8, 0.6)` == "joy"
9. **test_va_to_emotion_nearest** — `va_to_emotion(0.7, 0.5)` should return "joy" (nearest)
10. **test_fuse_single_signal** — One text signal, fresh → returns that emotion
11. **test_fuse_multi_signal** — Two signals (joy + sadness) with equal weight → check V/A is average
12. **test_fuse_stale_signal_filtered** — Signal with age >> half_life and low confidence → filtered out, returns None
13. **test_fuse_staleness_reduces_weight** — Fresh signal dominates over stale one

### Verification
```bash
uv run python3 -m pytest tests/unit/test_fusion_agent.py -v -k "not Agent"
```

---

## Task 2: MultimodalFusionAgent — BaseAgent Subclass

**File:** `ada/agents/fusion.py` (append to same file after pure functions)

### Implementation

```python
class MultimodalFusionAgent(BaseAgent):
    """
    Fuses text, voice, face, and physiological emotion signals into
    a unified emotion assessment using deterministic weighted averaging
    with exponential staleness decay.

    @decision DEC-FUSION-001
    @title Deterministic weighted average over LLM fusion
    @status accepted
    @rationale Each upstream agent already used Claude for classification.
        Fusion combines outputs — a math problem, not reasoning. Deterministic
        fusion is fast (~0ms), predictable, and testable without mocks.

    @decision DEC-FUSION-002
    @title Trigger-on-any with staleness decay
    @status accepted
    @rationale Fusion fires on every incoming signal. Missing modalities get
        zero weight instead of blocking. Handles therapy sessions where
        modalities come and go (user mutes mic, covers camera).

    @decision DEC-FUSION-003
    @title Exponential staleness decay (half-life model)
    @status accepted
    @rationale weight = 2^(-age/half_life). Default half_life=10s. Avoids
        hard cutoffs — signals gradually lose influence.
    """
```

**Properties:**
- `name` = `"fusion"`
- `description` = `"Multimodal fusion — weighted-average emotion signal combiner"`
- `supported_events` = `[EMOTION_ANALYZED, VOICE_ANALYZED, FACE_ANALYZED, SENSOR_ALERT]`

**State:**
- `self._buffers: dict[str, dict[str, ModalitySignal]]` — `session_id → modality → signal`

**Config accessors (properties):**
- `_half_life` — from `config.multimodal.fusion_staleness_half_life` (default 10.0)
- `_min_weight` — from `config.multimodal.fusion_min_weight` (default 0.01)
- `_fusion_enabled` — from `config.multimodal.fusion_enabled` (default True)

**handle_event dispatch logic:**
```python
async def handle_event(self, event: AdaEvent) -> None:
    try:
        if event.event_type == EventTypes.EMOTION_ANALYZED:
            assert isinstance(event, EmotionAnalyzedEvent)
            await self._handle_text(event)
        elif event.event_type == EventTypes.VOICE_ANALYZED:
            assert isinstance(event, VoiceAnalyzedEvent)
            await self._handle_voice(event)
        elif event.event_type == EventTypes.FACE_ANALYZED:
            assert isinstance(event, FaceAnalyzedEvent)
            await self._handle_face(event)
        elif event.event_type == EventTypes.SENSOR_ALERT:
            assert isinstance(event, SensorAlertEvent)
            await self._handle_sensor(event)
    except Exception:
        logger.exception("FusionAgent: error handling %s", event.event_type)
```

**Signal extraction per event type:**

- `_handle_text(event: EmotionAnalyzedEvent)`:
  - Create ModalitySignal with `emotion=event.primary_emotion`, `valence=event.valence`, `arousal=event.arousal`, `confidence=event.confidence`, `timestamp=time.monotonic()`, `modality="text"`
  - Call `_update_and_fuse(event.session_id, event.patient_id, signal)`

- `_handle_voice(event: VoiceAnalyzedEvent)`:
  - Map `event.emotion` to V/A via `emotion_to_va()`
  - Create ModalitySignal with mapped V/A, `confidence=event.confidence`, `modality="voice"`
  - Call `_update_and_fuse(event.session_id, event.patient_id, signal)`

- `_handle_face(event: FaceAnalyzedEvent)`:
  - Map `event.emotion` to V/A via `emotion_to_va()`
  - Create ModalitySignal with mapped V/A, `confidence=event.confidence`, `modality="face"`
  - Call `_update_and_fuse(event.session_id, event.patient_id, signal)`

- `_handle_sensor(event: SensorAlertEvent)`:
  - Parse stress_level from `event.description` (format: `"stress=high, ..."`)
  - Look up arousal in `STRESS_TO_AROUSAL` (default to 0.5 for unknown)
  - Create ModalitySignal with `emotion="anticipation"` (physiological arousal maps closest), `valence=0.0` (neutral), arousal from lookup, `confidence=0.7` (fixed — sensor signals are reliable but indirect), `modality="physiological"`
  - Call `_update_and_fuse(event.session_id, event.patient_id, signal)`

**Core fusion method:**
```python
async def _update_and_fuse(self, session_id: str, patient_id: str, signal: ModalitySignal) -> None:
    if not session_id:
        return
    # Update buffer
    if session_id not in self._buffers:
        self._buffers[session_id] = {}
    self._buffers[session_id][signal.modality] = signal

    # Fuse
    signals = list(self._buffers[session_id].values())
    now = time.monotonic()
    result = fuse_signals(signals, now, self._half_life, self._min_weight)
    if result is None:
        return

    # Build per-modality emotion strings for the event
    buf = self._buffers[session_id]
    text_emotion = buf["text"].emotion if "text" in buf else ""
    voice_emotion = buf["voice"].emotion if "voice" in buf else ""
    face_emotion = buf["face"].emotion if "face" in buf else ""
    physio_state = buf["physiological"].emotion if "physiological" in buf else ""

    # Publish
    await self.bus.publish(FusedEmotionEvent(
        source=self.name,
        session_id=session_id,
        patient_id=patient_id,
        text_emotion=text_emotion,
        voice_emotion=voice_emotion,
        face_emotion=face_emotion,
        physiological_state=physio_state,
        fused_emotion=result["fused_emotion"],
        fused_valence=result["fused_valence"],
        fused_arousal=result["fused_arousal"],
        confidence=result["confidence"],
        modalities_available=result["modalities"],
    ))

    # Persist
    await self.state.create_fused_emotion(
        id=str(uuid.uuid4()),
        session_id=session_id,
        patient_id=patient_id,
        fused_emotion=result["fused_emotion"],
        fused_valence=result["fused_valence"],
        fused_arousal=result["fused_arousal"],
        confidence=result["confidence"],
        modalities_available=result["modalities"],
        text_emotion=text_emotion or None,
        voice_emotion=voice_emotion or None,
        face_emotion=face_emotion or None,
        physiological_state=physio_state or None,
    )
```

**Cleanup:**
```python
async def stop(self) -> None:
    self._buffers.clear()
    await super().stop()
```

### Tests for Task 2

Add to `tests/unit/test_fusion_agent.py`:

**Fixtures:**
- `state` — in-memory StateManager with patient + session (same pattern as physiological tests)
- `agent_setup` — EventBus + AdaConfig (with fusion config fields set) + MultimodalFusionAgent initialized and started. Use MockLLMProvider (agent doesn't call LLM but BaseAgent.initialize requires one).

**Tests (async):**
1. **test_agent_properties** — name, description, supported_events are correct
2. **test_text_signal_produces_fused_event** — Publish EmotionAnalyzedEvent → receive FusedEmotionEvent with text_emotion set, modalities=["text"]
3. **test_voice_signal_produces_fused_event** — Publish VoiceAnalyzedEvent → receive FusedEmotionEvent with voice_emotion set
4. **test_multi_signal_fusion** — Publish text + voice → FusedEmotionEvent has both modalities, fused values are a blend
5. **test_sensor_alert_produces_fused_event** — Publish SensorAlertEvent with "stress=high, ..." → FusedEmotionEvent with physiological modality
6. **test_empty_session_id_skipped** — Event with empty session_id → no FusedEmotionEvent published
7. **test_stop_clears_buffers** — After stop(), `_buffers` is empty
8. **test_fused_emotion_persisted_to_db** — After text event, check `state.get_fused_emotions(session_id)` returns 1 row
9. **test_fusion_disabled_via_config** — When `fusion_enabled=False`, agent still subscribes (it must, BaseAgent.start subscribes) but `_update_and_fuse` early-returns → no FusedEmotionEvent

**Note on MockLLMProvider:** Copy the same MockLLMProvider from `tests/unit/test_physiological_agent.py`. The fusion agent never calls it, but BaseAgent.initialize requires an LLMProvider.

### Verification
```bash
uv run python3 -m pytest tests/unit/test_fusion_agent.py -v
```

---

## Task 3: Config + Registration Wiring

### 3a. Extend MultimodalConfig

**File:** `ada/core/config.py`

Add three fields to `MultimodalConfig`:
```python
class MultimodalConfig(BaseModel):
    # ... existing fields ...
    # Phase 4c: Fusion
    fusion_enabled: bool = True
    fusion_staleness_half_life: float = 10.0
    fusion_min_weight: float = 0.01
```

### 3b. Update default.toml

**File:** `config/default.toml`

Append to `[multimodal]` section:
```toml
fusion_enabled = true
fusion_staleness_half_life = 10.0
fusion_min_weight = 0.01
```

### 3c. Register FusionAgent in main.py

**File:** `ada/main.py`

Add import:
```python
from ada.agents.fusion import MultimodalFusionAgent
```

Add registration after PhysiologicalAgent block (still inside `if config.multimodal.enabled:`):
```python
        if config.multimodal.fusion_enabled:
            registry.register(MultimodalFusionAgent())
            log.info("MultimodalFusionAgent registered")
```

**Important:** The fusion agent must be registered AFTER the source agents (voice, face, physiological) so it subscribes after them. The EventBus processes subscribers in registration order, so source agents publish first, then fusion picks up their events.

### Verification
```bash
uv run python3 -c "from ada.core.config import AdaConfig; c = AdaConfig(); print(c.multimodal.fusion_enabled, c.multimodal.fusion_staleness_half_life, c.multimodal.fusion_min_weight)"
uv run python3 -c "from ada.agents.fusion import MultimodalFusionAgent; a = MultimodalFusionAgent(); print(a.name, a.supported_events)"
```

---

## Task 4: Integration Tests

**File:** `tests/integration/test_fusion_pipeline.py`

Full pipeline tests that exercise EventBus event flow end-to-end.

### Setup
- In-memory StateManager with patient + session
- Real EventBus
- MultimodalFusionAgent initialized and started
- MockLLMProvider (required by initialize, never called)
- AdaConfig with `multimodal.fusion_enabled=True`
- Collector callback subscribed to `EMOTION_FUSED`

### Tests

1. **test_text_to_fused_pipeline**
   - Publish `EmotionAnalyzedEvent(primary_emotion="joy", valence=0.8, arousal=0.6, confidence=0.9)`
   - Wait for propagation
   - Assert: FusedEmotionEvent received with `fused_emotion="joy"`, `modalities_available=["text"]`
   - Assert: DB row exists in `fused_emotions`

2. **test_multi_signal_pipeline**
   - Publish EmotionAnalyzedEvent (joy, 0.8, 0.6, confidence=0.9)
   - Wait briefly
   - Publish VoiceAnalyzedEvent (emotion="sadness", confidence=0.9)
   - Wait briefly
   - Publish FaceAnalyzedEvent (emotion="fear", confidence=0.8)
   - Wait for propagation
   - Assert: Received 3 FusedEmotionEvents (one per incoming signal)
   - Assert: Last event has `modalities_available` containing all three
   - Assert: Last fused valence is between the individual modality valences (not dominated by any one)

3. **test_stale_signal_dominated_by_fresh**
   - Publish EmotionAnalyzedEvent with joy
   - Record the signal's monotonic timestamp
   - Manually age the text signal in the agent's buffer by setting `_buffers[sid]["text"].timestamp` to `time.monotonic() - 60` (1 minute old, effectively stale at half_life=10s)
   - Publish VoiceAnalyzedEvent with sadness (fresh)
   - Assert: Fused emotion is closer to sadness than joy (fresh voice dominates)

4. **test_sensor_alert_affects_arousal**
   - Publish SensorAlertEvent with description="stress=high, HR elevated"
   - Assert: FusedEmotionEvent received, arousal reflects high stress (0.7)
   - Publish EmotionAnalyzedEvent with joy (arousal=0.6)
   - Assert: Fused arousal is blend of 0.7 and 0.6

5. **test_single_modality_still_fuses**
   - Publish only one VoiceAnalyzedEvent
   - Assert: FusedEmotionEvent produced (single modality does not block)
   - Assert: `modalities_available == ["voice"]`

### Verification
```bash
uv run python3 -m pytest tests/integration/test_fusion_pipeline.py -v
```

---

## Task 5: Final Verification

Run the full test suite and verify nothing is broken:

```bash
# All fusion tests
uv run python3 -m pytest tests/unit/test_fusion_agent.py tests/integration/test_fusion_pipeline.py -v

# Full suite — expect 610+ existing + ~22 new, 0 failures
uv run python3 -m pytest tests/ --tb=short -q

# Frontend unaffected
cd web && npm run build
```

---

## Key Implementation Notes

1. **No LLM calls.** The fusion agent is pure math. Tests do not need MockLLMProvider responses — only the `initialize()` signature requires one.

2. **Use `time.monotonic()` for timestamps.** Not `datetime`. Monotonic clock cannot go backwards and is appropriate for measuring intervals. Tests can control time by directly setting `signal.timestamp` in the buffer.

3. **The FusedEmotionEvent and fused_emotions table already exist.** Do not create new event types or DB tables. They were built in Phase 4a infrastructure.

4. **Sensor alert stress parsing.** PhysiologicalAgent publishes SensorAlertEvent with `description="stress=high, ..."`. Parse the stress level from the description string using: `event.description.split(",")[0].split("=")[1]` with fallback to "moderate".

5. **Use `uv run` for ALL Python/pytest commands.** The project uses uv for dependency management.

6. **Config defaults match design doc.** `fusion_enabled=True`, `fusion_staleness_half_life=10.0`, `fusion_min_weight=0.01`.

7. **Event subscription order matters.** Register MultimodalFusionAgent AFTER source agents in main.py so it receives their published events.

8. **Write COMPLETE code for every task.** Full test files and implementation — no stubs, no "TODO" markers, no abbreviated code.
