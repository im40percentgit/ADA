"""
Kokoro-82M ONNX TTS provider — lightweight neural speech synthesis.

@decision DEC-TTS-003
@title Kokoro-82M as default TTS, Piper retained for low-resource path
@status accepted
@rationale Kokoro-82M via kokoro-onnx (PyPI) gives significantly more
    natural speech than Piper en_US-lessac-medium with a comparable ONNX
    runtime footprint. The ONNX variant (not the torch package) keeps the
    dependency profile small and consistent with Piper's approach.
    Piper is kept in the factory as the fallback for low-RAM hosts or
    environments where kokoro-onnx fails to install (e.g. unsupported
    platform). Install via:
        pip install kokoro-onnx>=0.4.0 onnxruntime>=1.20.0

@decision DEC-TTS-007
@title Kokoro voice files auto-downloaded to ~/.cache/ada/kokoro/ on first use
@status accepted
@rationale The kokoro-onnx Python package does NOT auto-download voice model
    files — it expects them to exist on disk. Prior code passed bare filenames
    ("kokoro-v1.0.onnx", "voices-v1.0.bin"), which only worked when the
    process CWD happened to be the project root. Founder dogfood 2026-04-26
    hit this wall when the FastAPI process CWD differed from expectation.
    Fix:
      1. Resolve both files against an XDG-style cache directory
         (~/.cache/ada/kokoro/ by default, overridable via
         ADA_TTS__KOKORO_CACHE_DIR env var).
      2. Auto-download missing files from the canonical GitHub releases URL
         (https://github.com/thewh1teagle/kokoro-onnx/releases/download/
         model-files-v1.0/) using urllib.request.urlretrieve so init is
         CWD-independent on any deployment.
      3. At startup, also check the project root as a legacy fallback so
         existing installations with the files there keep working without
         a re-download.

Voice mapping (companion preference -> Kokoro voice ID):
    female  -> af_bella   (warm, American female)
    male    -> am_adam    (American male)
    neutral -> af_nicole  (softer American female)
These are defaults for first dogfood; founder swaps on first use.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import urllib.request
from pathlib import Path
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

# Model file names (must match the GitHub release asset names)
_MODEL_FILENAME = "kokoro-v1.0.onnx"
_VOICES_FILENAME = "voices-v1.0.bin"
_RELEASE_BASE_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
)


def _get_cache_dir() -> Path:
    """Return the directory used for Kokoro model files.

    Defaults to ~/.cache/ada/kokoro/. Override with ADA_TTS__KOKORO_CACHE_DIR
    environment variable for custom deployments.
    """
    env_override = os.environ.get("ADA_TTS__KOKORO_CACHE_DIR")
    if env_override:
        return Path(env_override).expanduser().resolve()
    return Path.home() / ".cache" / "ada" / "kokoro"


def _resolve_model_file(filename: str) -> Path:
    """Return absolute path for a Kokoro model file.

    Search order (first match wins):
    1. Cache directory (~/.cache/ada/kokoro/ or ADA_TTS__KOKORO_CACHE_DIR).
    2. Project-root legacy location — same directory as this module's package
       root, allowing existing manual placements to keep working.
    3. If not found in either place, download from GitHub releases into the
       cache directory and return that path.

    Args:
        filename: Bare file name, e.g. "kokoro-v1.0.onnx".

    Returns:
        Absolute Path to the file (guaranteed to exist after this call).

    Raises:
        FileNotFoundError: If the file cannot be found or downloaded.
    """
    # 1. Cache dir
    cache_dir = _get_cache_dir()
    cache_path = cache_dir / filename
    if cache_path.exists():
        logger.debug("Kokoro: found %s in cache (%s)", filename, cache_path)
        return cache_path

    # 2. Legacy project-root placement (CWD-independent: walk up from this file)
    # This file lives at ada/tts/kokoro.py — the project root is two levels up.
    project_root = Path(__file__).parent.parent.parent.resolve()
    legacy_path = project_root / filename
    if legacy_path.exists():
        logger.info(
            "Kokoro: found %s at legacy project-root path %s — "
            "consider moving to %s for CWD-independence",
            filename, legacy_path, cache_dir,
        )
        return legacy_path

    # 3. Download into cache
    logger.info("Kokoro: %s not found locally, downloading to %s ...", filename, cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    url = f"{_RELEASE_BASE_URL}/{filename}"
    try:
        tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
        urllib.request.urlretrieve(url, str(tmp_path))
        tmp_path.rename(cache_path)
        logger.info("Kokoro: downloaded %s (%d bytes)", filename, cache_path.stat().st_size)
        return cache_path
    except Exception as exc:
        # Clean up incomplete download
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise FileNotFoundError(
            f"Kokoro: could not find or download {filename!r}.\n"
            f"  Cache location: {cache_path}\n"
            f"  Legacy location: {legacy_path}\n"
            f"  Download URL: {url}\n"
            f"  Download error: {exc}\n"
            "  Manual fix: wget the file to the cache directory, or set "
            "ADA_TTS__KOKORO_CACHE_DIR to a directory containing the files."
        ) from exc


def _get_kokoro() -> Any:
    """Lazy-load Kokoro instance (thread-safe singleton).

    Resolves model file paths to absolute locations, auto-downloading from
    GitHub releases if needed (DEC-TTS-007). Subsequent calls return the
    cached instance without any I/O.
    """
    global _kokoro_instance
    if _kokoro_instance is not None:
        return _kokoro_instance
    with _kokoro_lock:
        if _kokoro_instance is not None:
            return _kokoro_instance
        try:
            from kokoro_onnx import Kokoro  # type: ignore[import]
        except ImportError:
            logger.error(
                "kokoro-onnx not installed. Install with: "
                "pip install kokoro-onnx>=0.4.0 onnxruntime>=1.20.0"
            )
            raise

        model_path = _resolve_model_file(_MODEL_FILENAME)
        voices_path = _resolve_model_file(_VOICES_FILENAME)
        logger.info(
            "Kokoro TTS loading: model=%s voices=%s",
            model_path, voices_path,
        )
        try:
            _kokoro_instance = Kokoro(str(model_path), str(voices_path))
            logger.info("Kokoro TTS loaded successfully")
        except Exception as exc:
            logger.error("Kokoro TTS failed to load: %s", exc)
            raise

    return _kokoro_instance


def reset_kokoro_singleton() -> None:
    """Reset the lazy singleton (test helper only — not for production use)."""
    global _kokoro_instance
    with _kokoro_lock:
        _kokoro_instance = None


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

    Model files are resolved via _resolve_model_file() which checks
    ~/.cache/ada/kokoro/, then the project root, then auto-downloads from
    GitHub releases. CWD-independent by design (DEC-TTS-007).
    """

    def __init__(self, model_path: str | None = None, voice_id: str | None = None) -> None:
        # model_path is accepted for API parity with PiperProvider. When
        # provided it is passed to the legacy-path resolution; when None the
        # standard cache/auto-download path is used.
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
