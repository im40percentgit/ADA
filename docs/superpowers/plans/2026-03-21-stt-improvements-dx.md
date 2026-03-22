# STT Improvements + Developer Experience — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate Whisper hallucinations and improve transcription accuracy by adding Silero VAD, confidence filtering, and a larger model; improve local DX with Makefile + entry point + health check.

**Architecture:** Extend `STTConfig` with 3 new fields (min_confidence, vad_filter, vad_threshold). Pass them through `TranscriptionAgent` → `transcribe_audio()` → `model.transcribe()`. Remove redundant post-conversion silence check (Silero VAD subsumes it). Add `ada/__main__.py`, `Makefile`, and LLM health check.

**Tech Stack:** faster-whisper (Silero VAD built-in), Python 3.12, FastAPI, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-21-stt-improvements-dx-design.md`

---

### Task 1: Extend STTConfig with new fields

**Files:**
- Modify: `ada/core/config.py:107-118`

- [ ] **Step 1: Write the failing test**

```bash
uv run python -c "from ada.core.config import STTConfig; c = STTConfig(); assert hasattr(c, 'min_confidence'), 'missing min_confidence'; assert hasattr(c, 'vad_filter'), 'missing vad_filter'; assert hasattr(c, 'vad_threshold'), 'missing vad_threshold'; print('FAIL: should not exist yet')"
```

Expected: AssertionError (fields don't exist yet)

- [ ] **Step 2: Add the three new fields to STTConfig**

In `ada/core/config.py`, replace the `STTConfig` class:

```python
class STTConfig(BaseModel):
    """Phase 7 speech-to-text configuration (faster-whisper).

    model_size: faster-whisper model variant — smaller is faster but less
        accurate. "base" (~150 MB) is a good default for CPU inference.
    language: ISO 639-1 language code, or None for auto-detect.
    compute_type: CTranslate2 quantisation for CPU inference.
    min_confidence: drop transcriptions below this confidence (0.0-1.0).
    vad_filter: enable Silero VAD to strip non-speech before Whisper.
    vad_threshold: Silero VAD speech probability threshold (0.0-1.0).
    """

    model_size: str = "base"
    language: str | None = None
    compute_type: str = "int8"
    min_confidence: float = 0.4
    vad_filter: bool = False
    vad_threshold: float = 0.5
```

- [ ] **Step 3: Verify the fields exist**

```bash
uv run python -c "from ada.core.config import STTConfig; c = STTConfig(); print(c.min_confidence, c.vad_filter, c.vad_threshold)"
```

Expected: `0.4 False 0.5`

- [ ] **Step 4: Commit**

```bash
git add ada/core/config.py
git commit -m "feat(stt): extend STTConfig with min_confidence, vad_filter, vad_threshold"
```

---

### Task 2: Add confidence filter + VAD params to transcribe_audio()

**Files:**
- Modify: `ada/ml/stt.py:156-291`
- Test: `tests/unit/test_stt.py`

- [ ] **Step 1: Write failing tests for confidence filter and VAD params**

Append to `tests/unit/test_stt.py`:

```python
class TestConfidenceFilter:
    def test_low_confidence_returns_empty(self):
        """Transcription below min_confidence is dropped."""
        wav = generate_sine_wav(frequency=440.0, duration_s=1.0)

        mock_segment = MagicMock()
        mock_segment.text = "Thanks for watching"
        mock_segment.avg_logprob = -2.0  # exp(-2.0) ≈ 0.135 — well below 0.4

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.5
        mock_info.duration = 1.0

        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.return_value = ([mock_segment], mock_info)

        with patch("ada.ml.stt._get_model", return_value=mock_model_instance):
            result = transcribe_audio(wav, min_confidence=0.4)

        assert result.text == ""

    def test_high_confidence_passes(self):
        """Transcription above min_confidence is kept."""
        wav = generate_sine_wav(frequency=440.0, duration_s=1.0)

        mock_segment = MagicMock()
        mock_segment.text = "I feel anxious"
        mock_segment.avg_logprob = -0.2  # exp(-0.2) ≈ 0.82 — above 0.4

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.99
        mock_info.duration = 1.0

        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.return_value = ([mock_segment], mock_info)

        with patch("ada.ml.stt._get_model", return_value=mock_model_instance):
            result = transcribe_audio(wav, min_confidence=0.4)

        assert result.text == "I feel anxious"

    def test_zero_min_confidence_disables_filter(self):
        """min_confidence=0.0 disables the filter — all results pass."""
        wav = generate_sine_wav(frequency=440.0, duration_s=1.0)

        mock_segment = MagicMock()
        mock_segment.text = "anything"
        mock_segment.avg_logprob = -5.0  # very low confidence

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.1
        mock_info.duration = 1.0

        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.return_value = ([mock_segment], mock_info)

        with patch("ada.ml.stt._get_model", return_value=mock_model_instance):
            result = transcribe_audio(wav, min_confidence=0.0)

        assert result.text == "anything"


class TestVadParamsForwarding:
    def test_vad_filter_and_params_forwarded(self):
        """vad_filter and vad_parameters are passed to model.transcribe()."""
        wav = generate_sine_wav(frequency=440.0, duration_s=0.5)

        mock_segment = MagicMock()
        mock_segment.text = "hello"
        mock_segment.avg_logprob = -0.2

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.99
        mock_info.duration = 0.5

        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.return_value = ([mock_segment], mock_info)

        with patch("ada.ml.stt._get_model", return_value=mock_model_instance):
            transcribe_audio(wav, vad_filter=True, vad_threshold=0.6)

        call_kwargs = mock_model_instance.transcribe.call_args[1]
        assert call_kwargs["vad_filter"] is True
        assert call_kwargs["vad_parameters"] == {"threshold": 0.6}
        assert call_kwargs["no_speech_threshold"] == 0.6

    def test_vad_disabled_by_default(self):
        """When vad_filter=False, vad_filter/vad_parameters not in kwargs."""
        wav = generate_sine_wav(frequency=440.0, duration_s=0.5)

        mock_segment = MagicMock()
        mock_segment.text = "hello"
        mock_segment.avg_logprob = -0.2

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.99
        mock_info.duration = 0.5

        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.return_value = ([mock_segment], mock_info)

        with patch("ada.ml.stt._get_model", return_value=mock_model_instance):
            transcribe_audio(wav, vad_filter=False, vad_threshold=0.5)

        call_kwargs = mock_model_instance.transcribe.call_args[1]
        assert "vad_filter" not in call_kwargs
        assert "vad_parameters" not in call_kwargs
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run python -m pytest tests/unit/test_stt.py::TestConfidenceFilter -v
uv run python -m pytest tests/unit/test_stt.py::TestVadParamsForwarding -v
```

Expected: FAIL (transcribe_audio doesn't accept min_confidence/vad_filter/vad_threshold yet)

- [ ] **Step 3: Implement the changes in stt.py**

Replace `transcribe_audio()` signature (line 156):

```python
def transcribe_audio(
    audio_bytes: bytes,
    *,
    model_size: str = "base",
    language: str | None = None,
    compute_type: str = "int8",
    min_confidence: float = 0.0,
    vad_filter: bool = False,
    vad_threshold: float = 0.5,
) -> TranscriptionResult:
```

Update the transcribe kwargs block (replace lines 251-254):

```python
        model = _get_model(model_size, compute_type)
        transcribe_kwargs: dict = {"beam_size": 5, "no_speech_threshold": 0.6}
        if language:
            transcribe_kwargs["language"] = language
        if vad_filter:
            transcribe_kwargs["vad_filter"] = True
            transcribe_kwargs["vad_parameters"] = {"threshold": vad_threshold}
```

Add confidence filter after confidence calculation (after line 266):

```python
        if min_confidence > 0 and confidence < min_confidence:
            logger.info(
                "STT: confidence %.2f below threshold %.2f — dropping: %s",
                confidence, min_confidence, text[:60],
            )
            return TranscriptionResult()
```

Remove the post-conversion silence check block (lines 230-249 — the `converted_bytes` read, amplitude logging, and `is_silent_wav(converted_bytes)` check). Replace with just:

```python
            logger.info("STT: ffmpeg conversion succeeded — WAV %d bytes", Path(tmp_wav).stat().st_size)
```

- [ ] **Step 4: Run all stt tests**

```bash
uv run python -m pytest tests/unit/test_stt.py -v
```

Expected: ALL PASS (existing + new tests)

- [ ] **Step 5: Commit**

```bash
git add ada/ml/stt.py tests/unit/test_stt.py
git commit -m "feat(stt): add confidence filter, Silero VAD params, remove redundant silence check"
```

---

### Task 3: Update TranscriptionAgent to pass new config fields

**Files:**
- Modify: `ada/agents/transcription.py:87-106`
- Test: `tests/unit/test_transcription_agent.py`

- [ ] **Step 1: Update the _fake_transcribe_success stub signature**

In `tests/unit/test_transcription_agent.py`, replace `_fake_transcribe_success` (lines 86-99):

```python
def _fake_transcribe_success(
    audio_bytes: bytes,
    *,
    model_size: str = "base",
    language=None,
    compute_type: str = "int8",
    min_confidence: float = 0.0,
    vad_filter: bool = False,
    vad_threshold: float = 0.5,
) -> TranscriptionResult:
    """Deterministic stand-in for transcribe_audio."""
    return TranscriptionResult(
        text="I feel anxious today",
        language="en",
        confidence=0.92,
        duration_s=1.5,
    )
```

- [ ] **Step 2: Add a test for config passthrough**

Append to `TestTranscriptionAgent` class:

```python
    @pytest.mark.asyncio
    async def test_passes_stt_config_to_transcribe_audio(self, agent_setup, sine_wav):
        """STTConfig fields (min_confidence, vad_filter, vad_threshold) are forwarded."""
        agent, bus, state = agent_setup
        # Set config values
        agent.config.stt.min_confidence = 0.5
        agent.config.stt.vad_filter = True
        agent.config.stt.vad_threshold = 0.6

        with patch("ada.agents.transcription.transcribe_audio", side_effect=_fake_transcribe_success) as mock_fn:
            await bus.publish(AudioChunkReceivedEvent(
                source="test",
                session_id="session-001",
                patient_id="patient-001",
                audio_bytes=sine_wav,
                sample_rate=16000,
                chunk_id="chunk-cfg",
            ))
            await asyncio.sleep(0.3)

        mock_fn.assert_called_once()
        call_kwargs = mock_fn.call_args[1]
        assert call_kwargs["min_confidence"] == 0.5
        assert call_kwargs["vad_filter"] is True
        assert call_kwargs["vad_threshold"] == 0.6
```

- [ ] **Step 3: Run test — verify it fails**

```bash
uv run python -m pytest tests/unit/test_transcription_agent.py::TestTranscriptionAgent::test_passes_stt_config_to_transcribe_audio -v
```

Expected: FAIL (TranscriptionAgent doesn't pass the new kwargs yet)

- [ ] **Step 4: Update TranscriptionAgent to pass new fields**

In `ada/agents/transcription.py`, update `_handle_audio_chunk()` (lines 92-106). After the existing config reads (line 96), add:

```python
        min_confidence = getattr(stt_cfg, "min_confidence", 0.0) if stt_cfg else 0.0
        vad_filter = getattr(stt_cfg, "vad_filter", False) if stt_cfg else False
        vad_threshold = getattr(stt_cfg, "vad_threshold", 0.5) if stt_cfg else 0.5
```

Update the `transcribe_audio` call (lines 100-106):

```python
            result = await asyncio.to_thread(
                transcribe_audio,
                event.audio_bytes,
                model_size=model_size,
                language=language,
                compute_type=compute_type,
                min_confidence=min_confidence,
                vad_filter=vad_filter,
                vad_threshold=vad_threshold,
            )
```

- [ ] **Step 5: Run all transcription agent tests**

```bash
uv run python -m pytest tests/unit/test_transcription_agent.py -v
```

Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add ada/agents/transcription.py tests/unit/test_transcription_agent.py
git commit -m "feat(stt): forward min_confidence, vad_filter, vad_threshold through TranscriptionAgent"
```

---

### Task 4: Update development config + reduce buffer interval

**Files:**
- Modify: `config/development.toml:55-56`
- Modify: `ada/api/routes/media.py:91`

- [ ] **Step 1: Update development.toml**

Replace the `[stt]` section in `config/development.toml`:

```toml
[stt]
model_size = "large-v3"
language = "en"
compute_type = "float16"
min_confidence = 0.4
vad_filter = true
vad_threshold = 0.5
```

- [ ] **Step 2: Reduce audio buffer interval**

In `ada/api/routes/media.py`, change line 91:

```python
    AUDIO_BUFFER_INTERVAL = 2.0  # Flush every 2 seconds (was 3.0; VAD handles segmentation)
```

- [ ] **Step 3: Verify config loads correctly**

```bash
uv run python -c "
from ada.core.config import AdaConfig
c = AdaConfig()
print('model_size:', c.stt.model_size)
print('language:', c.stt.language)
print('compute_type:', c.stt.compute_type)
print('min_confidence:', c.stt.min_confidence)
print('vad_filter:', c.stt.vad_filter)
print('vad_threshold:', c.stt.vad_threshold)
"
```

Expected: `large-v3`, `en`, `float16`, `0.4`, `True`, `0.5`

- [ ] **Step 4: Commit**

```bash
git add config/development.toml ada/api/routes/media.py
git commit -m "feat(stt): update dev config for large-v3 + VAD, reduce buffer to 2s"
```

---

### Task 5: Developer experience — entry point, Makefile, health check

**Files:**
- Create: `ada/__main__.py`
- Create: `Makefile`
- Modify: `ada/main.py:104-120`

- [ ] **Step 1: Create ada/__main__.py**

```python
"""Allow ``python -m ada`` to start the server."""

from ada.main import main

main()
```

- [ ] **Step 2: Verify entry point works**

```bash
uv run python -c "import ada.__main__" 2>&1 | head -1 || true
```

(Just verifies the import path resolves — actual server start would block)

- [ ] **Step 3: Create Makefile**

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

- [ ] **Step 4: Add LLM health check in ada/main.py**

In `ada/main.py`, after the model router creation (after line 120), add:

```python
    # Health check: warn if local LLM server is unreachable
    if config.llm.provider == "openai_compat":
        import httpx
        base_url = config.llm.openai_compat.base_url
        try:
            resp = httpx.get(f"{base_url}/models", timeout=2.0)
            log.info("LLM server reachable", base_url=base_url, status=resp.status_code)
        except Exception:
            log.warning(
                "Local LLM server not reachable — start your model server or "
                "set ANTHROPIC_API_KEY to use Claude",
                base_url=base_url,
            )
```

- [ ] **Step 5: Run full test suite**

```bash
uv run python -m pytest tests/ -q
```

Expected: ALL 819+ tests pass

- [ ] **Step 6: Commit**

```bash
git add ada/__main__.py Makefile ada/main.py
git commit -m "feat(dx): add python -m ada entry point, Makefile, LLM health check"
```

---

### Task 6: Full verification

- [ ] **Step 1: Run full test suite one more time**

```bash
uv run python -m pytest tests/ -q
```

Expected: ALL PASS, no regressions

- [ ] **Step 2: Verify `make test` works**

```bash
make test
```

Expected: Same test results

- [ ] **Step 3: Verify `python -m ada` starts (if LLM server available)**

```bash
timeout 5 uv run python -m ada 2>&1 || true
```

Expected: Server starts, logs show agent registration and LLM health check result

- [ ] **Step 4: Final commit if any cleanup needed, then merge to main**
