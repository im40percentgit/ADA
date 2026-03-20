"""
TTS provider abstraction — ABC and audio chunk model.

@decision DEC-TTS-001
@title Abstract TTSProvider with Piper implementation
@status accepted
@rationale Mirrors LLMProvider ABC pattern. TTSProvider.synthesize() returns
    TTSAudioChunk (PCM bytes + metadata). PiperProvider is the first
    implementation; the factory allows swapping providers via config.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TTSAudioChunk:
    """Output from a TTS synthesis call."""

    audio_bytes: bytes  # Raw PCM or WAV bytes
    sample_rate: int = 22050
    channels: int = 1
    sample_width: int = 2  # 16-bit
    format: str = "pcm"  # "pcm" or "wav"


class TTSProvider(ABC):
    """Abstract base class for TTS providers."""

    @abstractmethod
    async def synthesize(self, text: str) -> TTSAudioChunk:
        """Synthesize text to audio.

        Args:
            text: Text to speak.

        Returns:
            TTSAudioChunk with PCM audio bytes.
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider is ready (model loaded, etc.)."""
        ...
