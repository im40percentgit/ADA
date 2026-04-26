"""TTS provider factory — selects provider based on config.

DEC-TTS-003: Kokoro is the new default; Piper is retained as a low-resource
fallback. Factory stays intentionally dumb — voice mapping logic lives in
TTSAgent, not here.

@decision DEC-TTS-008
@title Provider chain pattern — FallbackTTSProvider(primary, fallback)
@status accepted
@rationale Kokoro can fail at runtime in two distinct ways: (1) the package
    or model assets are not installed (`is_available()` returns False), and
    (2) synthesis raises a transient runtime error (audio backend, ONNX
    runtime, missing voice). Both cases should fall back to Piper rather
    than 500 the chat WS — speech is a critical UX surface.

    FallbackTTSProvider wraps two providers selected at construction. The
    selection happens in create_tts_provider when both `provider` and
    `fallback_provider` are configured and differ. At synthesize time it
    short-circuits to the fallback if primary `is_available()` is False, and
    catches+logs+falls-back if primary `synthesize` raises. is_available
    returns True if EITHER provider is available, so an upstream agent that
    pre-checks availability sees "TTS works" if any link in the chain works.

    This is a chain pattern, not a strategy or a registry — there are
    exactly two providers and the second is always Piper (the local
    no-network option). DEC-TTS-007 (origin PR #75) handles Kokoro asset
    sourcing via cache-dir + auto-download; this DEC layers on top of that
    so Piper still rescues the request when Kokoro's auto-download or
    runtime fails for any reason.
"""

from __future__ import annotations

import logging

from ada.tts.base import TTSProvider
from ada.tts.piper import PiperProvider

logger = logging.getLogger(__name__)


class FallbackTTSProvider(TTSProvider):
    """Try a primary TTS provider, then a local fallback provider."""

    def __init__(self, primary: TTSProvider, fallback: TTSProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    async def synthesize(self, text: str):
        if await self.primary.is_available():
            try:
                return await self.primary.synthesize(text)
            except Exception as exc:
                logger.warning("Primary TTS failed; falling back to Piper: %s", exc)

        if not await self.fallback.is_available():
            raise RuntimeError("No TTS provider is available")
        return await self.fallback.synthesize(text)

    async def is_available(self) -> bool:
        return await self.primary.is_available() or await self.fallback.is_available()


def create_tts_provider(
    provider: str = "kokoro",
    model_path: str | None = None,
    voice_id: str | None = None,
    fallback_provider: str | None = None,
    fallback_model_path: str | None = None,
) -> TTSProvider:
    """Create a TTS provider instance.

    Args:
        provider: Provider name — "kokoro" (default) or "piper".
        model_path: Optional path to voice model file. For Kokoro this is
            the kokoro-v1.0.onnx path; voices-v1.0.bin is resolved next to it
            or from the repository root. For Piper it is the .onnx model path.
        voice_id: Voice identifier passed to KokoroProvider. Ignored by
            PiperProvider (Piper selects voice via model_path).
        fallback_provider: Optional provider to use when the primary is
            unavailable or raises during synthesis.
        fallback_model_path: Optional model path for the fallback provider.

    Returns:
        Configured TTSProvider instance.

    Raises:
        ValueError: If provider name is not recognized.
    """
    primary = _create_single_provider(provider, model_path=model_path, voice_id=voice_id)
    if fallback_provider and fallback_provider != provider:
        fallback = _create_single_provider(
            fallback_provider,
            model_path=fallback_model_path,
            voice_id=voice_id,
        )
        return FallbackTTSProvider(primary, fallback)
    return primary


def _create_single_provider(
    provider: str,
    *,
    model_path: str | None = None,
    voice_id: str | None = None,
) -> TTSProvider:
    """Create one concrete provider without wrapping fallback behavior."""
    if provider == "kokoro":
        from ada.tts.kokoro import KokoroProvider

        return KokoroProvider(model_path=model_path, voice_id=voice_id)

    if provider == "piper":
        return PiperProvider(model_path=model_path)

    raise ValueError(f"Unknown TTS provider: {provider!r}. Available: kokoro, piper")
