"""
Piper TTS provider — local ONNX-based speech synthesis.

@decision DEC-TTS-002
@title Piper TTS for local voice synthesis
@status accepted
@rationale Piper runs fully offline via ONNX runtime. The en_US-lessac-medium
    voice (~60MB) provides natural speech. Lazy loading ensures no startup
    cost when TTS is disabled. Thread-safe singleton avoids reloading the
    model per request.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path

from ada.tts.base import TTSAudioChunk, TTSProvider

logger = logging.getLogger(__name__)

_piper_voice = None
_piper_lock = threading.Lock()


def _get_piper_voice(model_path: str | None = None):
    """Lazy-load Piper voice (thread-safe singleton)."""
    global _piper_voice
    if _piper_voice is not None:
        return _piper_voice
    with _piper_lock:
        if _piper_voice is not None:
            return _piper_voice
        try:
            from piper import PiperVoice

            if model_path:
                _piper_voice = PiperVoice.load(model_path)
            else:
                # Default: will be downloaded on first use
                _piper_voice = PiperVoice.load("en_US-lessac-medium")
            logger.info("Piper voice loaded: %s", model_path or "en_US-lessac-medium")
        except ImportError:
            logger.error("piper-tts not installed. Install with: pip install piper-tts")
            raise
    return _piper_voice


def _synthesize_blocking(text: str, model_path: str | None = None) -> TTSAudioChunk:
    """Blocking synthesis — call via asyncio.to_thread()."""
    import io
    import wave

    voice = _get_piper_voice(model_path)

    # Piper synthesize writes WAV to a file-like object
    audio_buffer = io.BytesIO()
    with wave.open(audio_buffer, "wb") as wav_file:
        voice.synthesize(text, wav_file)

    wav_bytes = audio_buffer.getvalue()
    # Extract PCM from WAV (skip 44-byte header)
    pcm_bytes = wav_bytes[44:] if len(wav_bytes) > 44 else wav_bytes

    return TTSAudioChunk(
        audio_bytes=pcm_bytes,
        sample_rate=voice.config.sample_rate,
        channels=1,
        sample_width=2,
        format="pcm",
    )


class PiperProvider(TTSProvider):
    """Piper TTS provider — local ONNX voice synthesis."""

    def __init__(self, model_path: str | None = None):
        self._model_path = model_path

    async def synthesize(self, text: str) -> TTSAudioChunk:
        """Synthesize text to PCM audio via Piper (non-blocking)."""
        if not text.strip():
            return TTSAudioChunk(audio_bytes=b"", sample_rate=22050)
        return await asyncio.to_thread(_synthesize_blocking, text, self._model_path)

    async def is_available(self) -> bool:
        """Check if piper-tts is importable."""
        try:
            import piper  # noqa: F401

            return True
        except ImportError:
            return False
