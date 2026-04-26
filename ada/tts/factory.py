"""TTS provider factory — selects provider based on config.

DEC-TTS-003: Kokoro is the new default; Piper is retained as a low-resource
fallback. Factory stays intentionally dumb — voice mapping logic lives in
TTSAgent, not here.
"""

from __future__ import annotations

from ada.tts.base import TTSProvider
from ada.tts.piper import PiperProvider


def create_tts_provider(
    provider: str = "kokoro",
    model_path: str | None = None,
    voice_id: str | None = None,
) -> TTSProvider:
    """Create a TTS provider instance.

    Args:
        provider: Provider name — "kokoro" (default) or "piper".
        model_path: Optional path to voice model file. For Kokoro this is
            accepted for API parity but ignored (kokoro-onnx manages its
            own model files). For Piper it is the .onnx model path.
        voice_id: Voice identifier passed to KokoroProvider. Ignored by
            PiperProvider (Piper selects voice via model_path).

    Returns:
        Configured TTSProvider instance.

    Raises:
        ValueError: If provider name is not recognized.
    """
    if provider == "kokoro":
        from ada.tts.kokoro import KokoroProvider
        return KokoroProvider(model_path=model_path, voice_id=voice_id)

    if provider == "piper":
        return PiperProvider(model_path=model_path)

    raise ValueError(f"Unknown TTS provider: {provider!r}. Available: kokoro, piper")
