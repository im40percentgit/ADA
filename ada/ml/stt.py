"""
Speech-to-text transcription using faster-whisper.

Provides ``transcribe_audio()`` — a blocking function intended to be called
via ``asyncio.to_thread()`` from TranscriptionAgent.  The model is
lazy-loaded on first call and cached as a module-level singleton (protected
by a threading.Lock so concurrent ``to_thread`` calls are safe).

Silence guard (``is_silent_wav``) prevents Whisper hallucinations on
zero-filled PCM buffers — a common artefact when the browser's AudioContext
is suspended.  Only inspects WAV files; webm/opus passes through unchanged.

@decision DEC-ML-016
@title faster-whisper for server-side STT with amplitude-based silence guard
@status accepted
@rationale Web Speech API requires Google's servers (network errors when
    offline or blocked). faster-whisper runs fully locally, providing
    offline-capable, privacy-preserving transcription. CTranslate2 backend
    is 4x faster than OpenAI whisper with lower memory usage.
    Silence guard (is_silent_wav) prevents Whisper hallucinations on
    zero-filled buffers — checks max amplitude of first ~1000 WAV samples
    against a threshold of 100/32768 (~0.3% full scale).
    GPU is attempted first; CPU int8 is the fallback.

@decision DEC-ML-017
@title stt.py returns TranscriptionResult dataclass, not plain str
@status accepted
@rationale TranscriptionAgent needs language, confidence, and duration_s in
    addition to text for TranscriptionCompletedEvent. Structured result
    carries all fields. The silence guard from the prior transcribe.py
    prototype is preserved verbatim.
"""

from __future__ import annotations

import logging
import math
import struct
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Silence detection constants
# ---------------------------------------------------------------------------

# Amplitude threshold for silence detection (out of 32767 for 16-bit PCM).
# 100/32767 ~ 0.3% full scale -- safely below any real speech, above float noise.
_SILENCE_THRESHOLD = 100


# ---------------------------------------------------------------------------
# Model singleton (thread-safe lazy load)
# ---------------------------------------------------------------------------

_model = None
_model_lock = threading.Lock()


def _get_model(model_size: str, compute_type: str):
    """Lazy-load the Whisper model on first call (thread-safe singleton).

    Attempts GPU first; falls back to CPU with int8 quantisation.
    """
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:  # double-checked locking
            return _model
        from faster_whisper import WhisperModel
        logger.info("Loading Whisper model '%s' (compute_type=%s)...", model_size, compute_type)
        try:
            _model = WhisperModel(model_size, device="cuda", compute_type="float16")
            logger.info("Whisper model loaded on GPU (float16)")
        except Exception:
            _model = WhisperModel(model_size, device="cpu", compute_type=compute_type)
            logger.info("Whisper model loaded on CPU (%s)", compute_type)
    return _model


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class TranscriptionResult:
    """Output from a single transcription call.

    ``text`` is empty string when transcription produced nothing (silence,
    decode failure, or model error).  Callers should check ``bool(result.text)``
    before publishing events.
    """

    text: str = ""
    language: str = ""
    confidence: float = 0.0
    duration_s: float = 0.0


def is_silent_wav(audio_bytes: bytes) -> bool:
    """Return True if ``audio_bytes`` contains near-silent WAV audio.

    Only inspects files with a RIFF header.  Non-WAV formats (webm/opus)
    return False unconditionally -- they pass through to ffmpeg conversion.

    Reads the first ~1000 16-bit PCM samples and checks whether the maximum
    absolute amplitude is below ``_SILENCE_THRESHOLD`` (100/32767 ~ 0.3%).

    Args:
        audio_bytes: Raw audio file bytes.

    Returns:
        True if the audio is silent or empty, False otherwise.
    """
    if not audio_bytes:
        return True

    # Only inspect WAV files -- non-WAV formats pass through unchanged
    if audio_bytes[:4] != b"RIFF":
        return False

    # WAV PCM data starts at byte 44 (standard 44-byte header).
    # Read first 1000 samples (2 bytes each = 2000 bytes) for a fast check.
    PCM_OFFSET = 44
    SAMPLES_TO_CHECK = 1000
    pcm_data = audio_bytes[PCM_OFFSET : PCM_OFFSET + SAMPLES_TO_CHECK * 2]

    if not pcm_data:
        return True

    n_samples = len(pcm_data) // 2
    samples = struct.unpack_from(f"<{n_samples}h", pcm_data)
    max_amplitude = max(abs(s) for s in samples)

    if max_amplitude < _SILENCE_THRESHOLD:
        logger.debug(
            "Silence detected (max_amplitude=%d < threshold=%d) -- skipping Whisper",
            max_amplitude, _SILENCE_THRESHOLD,
        )
        return True

    return False


def transcribe_audio(
    audio_bytes: bytes,
    *,
    model_size: str = "base",
    language: str | None = None,
    compute_type: str = "int8",
) -> TranscriptionResult:
    """Transcribe raw audio bytes to text using faster-whisper.

    Accepts any format ffmpeg can decode (webm/opus, wav, mp3, etc.).
    WAV input is silence-checked before loading the GPU model to prevent
    Whisper hallucinations on zero-filled buffers.

    This is a **blocking** function -- call via ``asyncio.to_thread()`` from
    async code to avoid blocking the event loop.

    Args:
        audio_bytes: Raw audio data in any ffmpeg-decodable format.
        model_size: faster-whisper model size (tiny, base, small, medium,
            large-v3). Default "base" balances speed and accuracy on CPU.
        language: ISO 639-1 language code (e.g. "en") or None for auto-detect.
        compute_type: CTranslate2 compute type for CPU ("int8", "float32").

    Returns:
        ``TranscriptionResult`` with text, language, confidence, duration_s.
        ``text`` is empty string on silence, decode failure, or model error.
    """
    if not audio_bytes:
        return TranscriptionResult()

    # Guard: reject silent WAV before loading the model.
    if is_silent_wav(audio_bytes):
        logger.debug("Silent WAV input -- returning empty transcript")
        return TranscriptionResult()

    tmp_in: str | None = None
    tmp_wav: str | None = None
    try:
        is_wav = audio_bytes[:4] == b"RIFF"
        suffix = ".wav" if is_wav else ".webm"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_bytes)
            tmp_in = f.name

        if is_wav:
            tmp_wav = tmp_in
            logger.debug("Received WAV audio directly (%d bytes)", len(audio_bytes))
        else:
            tmp_wav = tmp_in.replace(suffix, ".wav")
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-probesize", "50M", "-analyzeduration", "50M",
                    "-i", tmp_in,
                    "-af", "aresample=async=1:first_pts=0",
                    "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                    tmp_wav,
                ],
                capture_output=True,
                timeout=15,
            )
            if result.returncode != 0 or not Path(tmp_wav).exists():
                stderr = result.stderr.decode(errors="replace")[-300:]
                logger.warning(
                    "ffmpeg conversion failed (rc=%d, %d bytes input): %s",
                    result.returncode, len(audio_bytes), stderr.strip(),
                )
                return TranscriptionResult()

            # Post-conversion silence check on the decoded WAV
            converted_bytes = Path(tmp_wav).read_bytes()
            if is_silent_wav(converted_bytes):
                logger.debug("Converted WAV is silent -- skipping Whisper")
                return TranscriptionResult()

        model = _get_model(model_size, compute_type)
        transcribe_kwargs: dict = {"beam_size": 5}
        if language:
            transcribe_kwargs["language"] = language

        segments, info = model.transcribe(tmp_wav, **transcribe_kwargs)
        segment_list = list(segments)  # consume generator before cleanup
        text = " ".join(seg.text.strip() for seg in segment_list)

        # Average log-probability -> linear confidence per segment
        if segment_list:
            avg_logprob = sum(s.avg_logprob for s in segment_list) / len(segment_list)
            # avg_logprob is typically -0.2 (good) to -1.5 (poor); clamp to [0, 1]
            confidence = float(min(1.0, max(0.0, math.exp(avg_logprob))))
        else:
            confidence = 0.0

        duration_s = float(info.duration) if info.duration else 0.0

        logger.info(
            "STT: transcribed %d chars, lang=%s (p=%.2f), confidence=%.2f, "
            "duration=%.1fs: %s",
            len(text), info.language, info.language_probability,
            confidence, duration_s, text[:80],
        )
        return TranscriptionResult(
            text=text.strip(),
            language=info.language or "",
            confidence=confidence,
            duration_s=duration_s,
        )

    except Exception as exc:
        logger.warning("Transcription failed: %s", exc)
        return TranscriptionResult()
    finally:
        if tmp_in:
            Path(tmp_in).unlink(missing_ok=True)
        if tmp_wav and tmp_wav != tmp_in:
            Path(tmp_wav).unlink(missing_ok=True)
