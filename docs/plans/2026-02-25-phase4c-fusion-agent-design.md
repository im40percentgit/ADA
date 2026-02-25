# Phase 4c — MultimodalFusionAgent Design

**Goal:** A single BaseAgent subclass that fuses text, voice, face, and physiological emotion signals into a unified emotion assessment using deterministic weighted averaging with staleness decay.

**Depends on:** Phase 4a (event types, storage tables, FusedEmotionResult model) and Phase 4b (VoiceEmotionAgent, FacialEmotionAgent, PhysiologicalAgent).

**Tech Stack:** Python 3.12+, no new dependencies. Pure math — no LLM calls.

---

## Architecture

```
EMOTION_ANALYZED (text) ──┐
VOICE_ANALYZED ───────────┤
FACE_ANALYZED ────────────┼──→ FusionAgent → weighted average → EMOTION_FUSED → fused_emotions DB
SENSOR_ALERT ─────────────┘
```

The agent subscribes to all four upstream signal events. On every incoming signal, it updates the session buffer, computes a weighted-average fusion, and publishes an EMOTION_FUSED event.

---

## Key Decisions

### DEC-FUSION-001: Deterministic weighted average over LLM fusion
Each upstream agent already used Claude for emotion classification. The fusion layer combines their outputs — a math problem, not a reasoning problem. Deterministic fusion is fast (~0ms), predictable, and testable without mocks. LLM fusion would add latency + API cost for marginal benefit.

### DEC-FUSION-002: Trigger-on-any with staleness decay
Fusion fires on every incoming signal, weighting each modality by recency via exponential decay. Missing modalities get zero weight instead of blocking fusion. This handles therapy sessions where modalities come and go (user mutes mic, covers camera).

### DEC-FUSION-003: Exponential staleness decay (half-life model)
`weight = 2^(-age_seconds / half_life)`. Default half_life=10s. A signal from 10s ago has 50% weight; 20s ago has 25%; 60s ago has ~1.5% (discarded below min_weight threshold). Avoids hard cutoffs — signals gradually lose influence.

### DEC-FUSION-004: Backend fusion only, no frontend
Phase 4c focuses on the server-side fusion agent. Frontend media capture components (MediaCapture.tsx, VoiceIndicator.tsx, FaceOverlay.tsx) are deferred to Phase 4d.

---

## Signal Buffer

```python
@dataclass
class ModalitySignal:
    emotion: str           # Plutchik emotion name
    valence: float         # -1.0 to 1.0
    arousal: float         # 0.0 to 1.0
    confidence: float      # 0.0 to 1.0
    timestamp: float       # time.monotonic()
    modality: str          # "text" | "voice" | "face" | "physiological"
```

Per-session buffer: `dict[str, dict[str, ModalitySignal]]` — `session_id → modality → latest signal`. Only the most recent signal per modality is kept.

---

## Staleness Decay

```python
def recency_weight(signal_age_seconds: float, half_life: float = 10.0) -> float:
    return 2 ** (-signal_age_seconds / half_life)
```

| Age (s) | Weight |
|---------|--------|
| 0       | 1.000  |
| 5       | 0.707  |
| 10      | 0.500  |
| 20      | 0.250  |
| 30      | 0.125  |
| 60      | 0.016  |

---

## Plutchik Valence-Arousal Mapping

```python
PLUTCHIK_MAP = [
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

Used bidirectionally:
- **Emotion → valence/arousal**: For upstream events (voice, face) that only provide emotion name + confidence
- **Valence/arousal → emotion**: For the final fused result (nearest-neighbor by Euclidean distance)

---

## Fusion Algorithm

On every incoming signal:

1. **Update buffer**: Store/replace the latest signal for this session + modality
2. **Collect signals**: Get all signals for this session
3. **Compute weights**: For each signal: `effective_weight = confidence × recency_weight(age)`
4. **Filter stale**: Discard signals with `effective_weight < min_weight` (default 0.01)
5. **Check minimum**: If no valid signals remain, skip (no fusion)
6. **Weighted average**: Compute weighted mean of valence and arousal
7. **Map to emotion**: Find nearest Plutchik emotion by Euclidean distance in V-A space
8. **Compute confidence**: Average of effective weights (normalized)
9. **Publish**: `FusedEmotionEvent` with per-modality breakdown
10. **Persist**: `state.create_fused_emotion()` to `fused_emotions` table

---

## Event Subscriptions

| Subscribes To | Source | Extracts |
|--------------|--------|----------|
| `EMOTION_ANALYZED` | EmotionAnalyzerAgent | emotion, valence, arousal, confidence |
| `VOICE_ANALYZED` | VoiceEmotionAgent | emotion, confidence → map to V/A |
| `FACE_ANALYZED` | FacialEmotionAgent | emotion, confidence → map to V/A |
| `SENSOR_ALERT` | PhysiologicalAgent | stress_level → arousal mapping |

### Sensor Alert Mapping
```python
STRESS_TO_AROUSAL = {"low": 0.2, "moderate": 0.5, "high": 0.7, "critical": 0.9}
# Stress doesn't directly map to valence — use neutral (0.0)
```

---

## Config Additions

```toml
[multimodal]
fusion_enabled = true
fusion_staleness_half_life = 10.0
fusion_min_weight = 0.01
```

---

## Files

### New
| File | Purpose |
|------|---------|
| `ada/agents/fusion.py` | MultimodalFusionAgent (BaseAgent subclass) |
| `tests/unit/test_fusion_agent.py` | Unit tests (~12 tests) |
| `tests/integration/test_fusion_pipeline.py` | End-to-end pipeline tests (~5 tests) |

### Modified
| File | Change |
|------|--------|
| `ada/core/config.py` | Add fusion fields to MultimodalConfig |
| `config/default.toml` | Add fusion config keys |
| `ada/main.py` | Register FusionAgent when enabled |

---

## Testing Strategy

**Unit tests** (no LLM needed — pure math):
- Recency weight calculation at various ages
- Plutchik V/A mapping (emotion → V/A and V/A → emotion)
- Single modality fusion (only text available)
- Multi-modality fusion (text + voice + face)
- Staleness decay (old signal gets low weight)
- Missing modality handling (graceful, no crash)
- Buffer cleanup on session end
- Config field defaults

**Integration tests**:
- EmotionAnalyzedEvent → FusionAgent → FusedEmotionEvent → DB
- Multi-signal: text + voice + face arrive sequentially → fused result reflects all three
- Stale signal test: old voice + fresh text → text dominates
- PhysiologicalAgent sensor alert → affects fusion arousal

---

## Verification Checklist

1. `uv run python3 -m pytest tests/unit/test_fusion_agent.py -v` — all pass
2. `uv run python3 -m pytest tests/integration/test_fusion_pipeline.py -v` — all pass
3. `uv run python3 -m pytest tests/ --tb=short -q` — 610+ existing + ~17 new, 0 failures
4. `cd web && npm run build` — unaffected
