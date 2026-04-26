"""
Kokoro-82M ONNX TTS provider — lightweight neural speech synthesis.

@decision DEC-TTS-003
@title Kokoro-82M as default TTS, Piper retained for low-resource path
@status accepted
@rationale Kokoro-82M via kokoro-onnx (PyPI) gives significantly more
    natural speech than Piper en_US-lessac-medium with a comparable ONNX
    runtime footprint. The ONNX variant (not the torch package) keeps the
    dependency profile small and consistent with Piper's approach.
    Voice files are downloaded from HuggingFace on first use; subsequent
    calls hit the lazy singleton. Piper is kept in the factory as the
    fallback for low-RAM hosts or environments where kokoro-onnx fails
    to install (e.g. unsupported platform). Install via:
        pip install kokoro-onnx>=0.4.0 onnxruntime>=1.20.0

Voice mapping (companion preference -> Kokoro voice ID):
    female  -> af_bella   (warm, American female)
    male    -> am_adam    (American male)
    neutral -> af_nicole  (softer American female)
These are defaults for first dogfood; founder swaps on first use.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from ada.tts.base import TTSAudioChunk, TTSProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singleton — thread-safe, same pattern as piper.py
# ---------------------------------------------------------------------------

_kokoro_instance: Any = None  # kokoro_onnx.Kokoro instance
_kokoro_lock = threading.Lock()

# Default voice IDs for each companion preference value
VOICE_MAP: dict[str, str] = {
    "female": "af_bella",
    "male": "am_adam",
    "neutral": "af_nicole",
}
DEFAULT_VOICE = "af_bella"
DEFAULT_SAMPLE_RATE = 24000  # Kokoro native output rate


def _get_kokoro(lang: str = "en-us") -> Any:
    """Lazy-load Kokoro instance (thread-safe singleton).

    The Kokoro constructor downloads voice files from HuggingFace on first
    use. Subsequent calls return the cached instance without I/O.
    """
    global _kokoro_instance
    if _kokoro_instance is not None:
        return _kokoro_instance
    with _kokoro_lock:
        if _kokoro_instance is not None:
            return _kokoro_instance
        try:
            from kokoro_onnx import Kokoro  # type: ignore[import]

            _kokoro_instance = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")
            logger.info("Kokoro TTS loaded (lang=%s)", lang)
        except ImportError:
            logger.error(
                "kokoro-onnx not installed. Install with: pip install kokoro-onnx>=0.4.0 onnxruntime>=1.20.0"
            )
            raise
        except Exception as exc:
            logger.error("Kokoro TTS failed to load: %s", exc)
            raise
    return _kokoro_instance


def _synthesize_blocking(text: str, voice_id: str) -> TTSAudioChunk:
    """Blocking synthesis — call via asyncio.to_thread() from async context."""
    kokoro = _get_kokoro()
    # kokoro.create() returns (samples: np.ndarray[float32], sample_rate: int)
    samples, sample_rate = kokoro.create(text, voice=voice_id, speed=1.0, lang="en-us")

    # Convert float32 [-1, 1] to int16 PCM bytes
    import numpy as np  # type: ignore[import]

    pcm_int16 = (samples * 32767).clip(-32768, 32767).astype(np.int16)
    pcm_bytes = pcm_int16.tobytes()

    return TTSAudioChunk(
        audio_bytes=pcm_bytes,
        sample_rate=sample_rate,
        channels=1,
        sample_width=2,
        format="pcm",
    )


class KokoroProvider(TTSProvider):
    """Kokoro-82M ONNX TTS provider — neural speech synthesis.

    Voice selection is resolved at synthesis time (not construction) so
    mid-session voice changes propagate without rebuilding the provider.
    Pass voice_id=None to use the default (af_bella).
    """

    def __init__(self, model_path: str | None = None, voice_id: str | None = None) -> None:
        # model_path is accepted for API parity with PiperProvider but
        # kokoro-onnx downloads its own model files — it is not used.
        self._model_path = model_path
        self._voice_id = voice_id or DEFAULT_VOICE

    async def synthesize(self, text: str) -> TTSAudioChunk:
        """Synthesize text to PCM audio via Kokoro (non-blocking)."""
        if not text.strip():
            return TTSAudioChunk(audio_bytes=b"", sample_rate=DEFAULT_SAMPLE_RATE)
        return await asyncio.to_thread(_synthesize_blocking, text, self._voice_id)

    async def is_available(self) -> bool:
        """Check if kokoro-onnx is importable."""
        try:
            import kokoro_onnx  # noqa: F401  # type: ignore[import]

            return True
        except ImportError:
            return False
