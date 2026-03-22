# STT Improvements + Developer Experience

**Date:** 2026-03-21
**Status:** Approved
**Scope:** Improve speech-to-text accuracy/hallucination resistance + local dev ergonomics

---

## Problem

Ada's STT pipeline produces hallucinations ("Thanks for watching!", "Bye-bye") and has poor accuracy. Root causes:

1. **Whisper `base` model** (74M params) is too small for reliable transcription
2. **No Voice Activity Detection** — silence, breathing, background noise all reach Whisper
3. **No language pinning** — auto-detect on short utterances causes confusion
4. **No confidence filtering** — low-confidence hallucinations are published as real transcriptions
5. **3-second buffer** adds unnecessary latency

Additionally, local developer experience has friction:
- No `python -m ada` entry point
- No Makefile for common commands
- No health check when LLM server is unreachable

## Design

### STT Config Fixes

**Config changes** (`config/development.toml`):
- `model_size = "large-v3"` — 1.5B params, 20x larger than base, GPU handles in ~150ms
- `language = "en"` — eliminates auto-detect errors on short utterances
- `compute_type = "float16"` — native GPU precision, fastest inference

**Confidence filter** (`ada/ml/stt.py`):
- New `min_confidence` parameter (default 0.4)
- After transcription, if computed confidence < min_confidence, return empty result
- Drops hallucinations which typically have very low avg_logprob

**No-speech threshold**:
- Pass `no_speech_threshold=0.6` to faster-whisper's `transcribe()` call
- Segments where Whisper detects high no-speech probability are dropped before text extraction

### Silero VAD Integration

**Built into faster-whisper** — no new dependency required:
- Pass `vad_filter=True` to `model.transcribe()`
- Pass `vad_parameters={"threshold": 0.5}` (configurable via `STTConfig.vad_threshold`) — note: faster-whisper's API uses `vad_parameters` dict, not a `vad_threshold` kwarg
- Silero VAD strips non-speech segments before Whisper processes them
- This is the single biggest improvement for hallucination resistance

**Silence guard simplification**:
- Keep `is_silent_wav()` as a fast pre-check to avoid loading the model on empty buffers
- Remove the post-conversion `is_silent_wav(converted_bytes)` check and the associated `converted_bytes` read + amplitude debug logging block (lines 231-247) — Silero VAD subsumes this, and the debug logging was a diagnostic aid for the now-resolved silence bug

**Buffer interval reduction**:
- `AUDIO_BUFFER_INTERVAL` in `ada/api/routes/media.py`: 3.0 -> 2.0 seconds
- VAD handles segmentation, so shorter buffers reduce perceived latency

### Config Model Extension

`ada/core/config.py` — `STTConfig`:
Proposed `STTConfig` (currently has only model_size, language, compute_type):
```python
class STTConfig(BaseModel):
    model_size: str = "base"
    language: str | None = None
    compute_type: str = "int8"
    min_confidence: float = 0.4      # NEW
    vad_filter: bool = False          # NEW
    vad_threshold: float = 0.5        # NEW — maps to vad_parameters={"threshold": ...}
```

`config/development.toml`:
```toml
[stt]
model_size = "large-v3"
language = "en"
compute_type = "float16"
min_confidence = 0.4
vad_filter = true
vad_threshold = 0.5
```

### TranscriptionAgent Config Passthrough

`ada/agents/transcription.py` — pass new config fields to `transcribe_audio()`:
- `min_confidence` from `stt_cfg.min_confidence`
- `vad_filter` from `stt_cfg.vad_filter`
- `vad_threshold` from `stt_cfg.vad_threshold`

**Note:** `transcribe_audio()` maps `vad_threshold` to `vad_parameters={"threshold": value}` at the call site — the config field name differs from the faster-whisper API parameter name.

**Model singleton constraint:** The Whisper model loads once per process via `_get_model()` singleton. Changing `model_size` in config requires a server restart. Tests that patch `_get_model` are not affected.

### Developer Experience

**`ada/__main__.py`** (new):
```python
from ada.main import main
main()
```

**`Makefile`** (new):
```makefile
.PHONY: dev install test backend frontend

install:
	uv pip install -e ".[stt,tts,dev]"
	cd web && npm install

dev:
	@trap 'kill 0' INT; $(MAKE) backend & $(MAKE) frontend & wait

backend:
	uv run python -m ada

frontend:
	cd web && npm run dev

test:
	uv run python -m pytest tests/ -q
```

**LLM server health check** (`ada/main.py`):
- After config loads, if provider is `openai_compat`, attempt `httpx.get(base_url + "/models", timeout=2.0)`
- On failure: `logger.warning("Local LLM server not reachable at %s. Start your model server or set ANTHROPIC_API_KEY.", base_url)`
- Non-blocking — Ada still starts

## Files Modified

| File | Change |
|------|--------|
| `ada/ml/stt.py` | Confidence filter, VAD params, remove redundant post-convert silence check |
| `ada/core/config.py` | Extend STTConfig (min_confidence, vad_filter, vad_threshold) |
| `config/development.toml` | large-v3, en, float16, vad_filter=true |
| `ada/agents/transcription.py` | Pass new config fields through to transcribe_audio() |
| `ada/api/routes/media.py` | AUDIO_BUFFER_INTERVAL 3.0 -> 2.0 |
| `ada/__main__.py` | New entry point |
| `Makefile` | New dev commands |
| `ada/main.py` | LLM health check on startup |
| `tests/unit/test_stt.py` | Test confidence filter, verify `vad_filter`+`vad_parameters` in transcribe call_args |
| `tests/unit/test_transcription_agent.py` | Update `_fake_transcribe_success` stub for new kwargs, test config passthrough |

## Verification

1. `uv run python -m pytest tests/ -q` — all tests pass
2. `uv run python -m ada` — server starts, health check reports LLM status
3. `make dev` — both backend and frontend start
4. Enable mic in browser, speak into Ada — transcriptions appear without hallucinations
5. Stay silent for 10s — no phantom transcriptions published
