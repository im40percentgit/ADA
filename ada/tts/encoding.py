"""
Audio encoding utilities for TTS output.

Wraps raw PCM bytes in a standard 44-byte WAV header for transport
over WebSocket.

@decision DEC-TTS-004
@title PCM-to-WAV encoding with standard 44-byte header
@status accepted
@rationale Browsers and audio players expect WAV framing. Building the header
    manually (struct.pack) avoids importing the wave module for a trivial
    44-byte prefix, keeping the function zero-dependency and allocation-light.
"""

from __future__ import annotations

import struct


def pcm_to_wav(
    pcm_bytes: bytes,
    *,
    sample_rate: int = 22050,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """Wrap raw PCM bytes in a WAV header.

    Args:
        pcm_bytes: Raw PCM audio data (int16 little-endian).
        sample_rate: Sample rate in Hz.
        channels: Number of audio channels.
        sample_width: Bytes per sample (2 for int16).

    Returns:
        Complete WAV file bytes (44-byte header + PCM data).
    """
    data_size = len(pcm_bytes)
    byte_rate = sample_rate * channels * sample_width
    block_align = channels * sample_width

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,  # file size - 8
        b"WAVE",
        b"fmt ",
        16,  # fmt chunk size
        1,  # PCM format
        channels,
        sample_rate,
        byte_rate,
        block_align,
        sample_width * 8,  # bits per sample
        b"data",
        data_size,
    )

    return header + pcm_bytes
