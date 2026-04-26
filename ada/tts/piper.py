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

DEFAULT_PIPER_MODEL = "data/voices/piper/en_US-lessac-medium.onnx"

_piper_voices: dict[tuple[str, str | None], object] = {}
_piper_lock = threading.Lock()


def _repo_root() -> Path:
    """Return the repository root for local Piper voice lookup."""
    return Path(__file__).resolve().parents[2]


def _resolve_model_path(model_path: str | None = None) -> Path:
    """Resolve Piper voice model path independent of cwd."""
    raw = Path(model_path or DEFAULT_PIPER_MODEL).expanduser()
    candidates = [raw]
    if not raw.is_absolute():
        candidates.insert(0, _repo_root() / raw)

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()


def _resolve_config_path(model_path: Path) -> Path | None:
    """Return the companion Piper JSON config path when it exists."""
    candidates = [
        Path(str(model_path) + ".json"),
        model_path.with_suffix(".onnx.json"),
        model_path.with_suffix(".json"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def _get_piper_voice(model_path: str | None = None):
    """Lazy-load Piper voice (thread-safe singleton)."""
    resolved_model = _resolve_model_path(model_path)
    resolved_config = _resolve_config_path(resolved_model)
    cache_key = (str(resolved_model), str(resolved_config) if resolved_config else None)
    if cache_key in _piper_voices:
        return _piper_voices[cache_key]

    with _piper_lock:
        if cache_key in _piper_voices:
            return _piper_voices[cache_key]
        try:
            from piper import PiperVoice

            if not resolved_model.exists():
                raise FileNotFoundError(f"Piper model not found: {resolved_model}")
            if resolved_config is None:
                raise FileNotFoundError(
                    "Piper voice config not found. Expected "
                    f"{resolved_model}.json next to the model."
                )

            voice = PiperVoice.load(resolved_model, config_path=resolved_config)
            _piper_voices[cache_key] = voice
            logger.info("Piper voice loaded: %s", resolved_model)
        except ImportError:
            logger.error("piper-tts not installed. Install with: pip install piper-tts")
            raise
    return _piper_voices[cache_key]


def _synthesize_blocking(text: str, model_path: str | None = None) -> TTSAudioChunk:
    """Blocking synthesis — call via asyncio.to_thread()."""
    voice = _get_piper_voice(model_path)

    chunks = list(voice.synthesize(text))
    if not chunks:
        return TTSAudioChunk(audio_bytes=b"")

    pcm_bytes = b"".join(chunk.audio_int16_bytes for chunk in chunks)
    first = chunks[0]
    return TTSAudioChunk(
        audio_bytes=pcm_bytes,
        sample_rate=first.sample_rate,
        channels=first.sample_channels,
        sample_width=first.sample_width,
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
        """Check if piper-tts and the configured local voice files are available."""
        try:
            import piper  # noqa: F401

            model_path = _resolve_model_path(self._model_path)
            return model_path.exists() and _resolve_config_path(model_path) is not None
        except ImportError:
            return False
