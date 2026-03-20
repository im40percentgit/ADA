"""TTS provider factory — selects provider based on config."""

from __future__ import annotations

from ada.tts.base import TTSProvider
from ada.tts.piper import PiperProvider


def create_tts_provider(
    provider: str = "piper",
    model_path: str | None = None,
) -> TTSProvider:
    """Create a TTS provider instance.

    Args:
        provider: Provider name ("piper").
        model_path: Optional path to voice model file.

    Returns:
        Configured TTSProvider instance.

    Raises:
        ValueError: If provider name is not recognized.
    """
    if provider == "piper":
        return PiperProvider(model_path=model_path)
    raise ValueError(f"Unknown TTS provider: {provider!r}. Available: piper")
