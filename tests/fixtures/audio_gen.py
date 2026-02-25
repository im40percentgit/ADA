"""
Generate synthetic audio fixtures for testing.

@decision DEC-ML-006
@title Synthetic audio fixtures for deterministic testing
@status accepted
@rationale Programmatically generated sine waves provide deterministic,
    repeatable test inputs. A 440Hz tone has a known pitch, predictable
    energy, and extractable MFCCs. This avoids depending on external
    audio files and makes tests fully self-contained.
"""

from __future__ import annotations

import io
import wave

import numpy as np


def generate_sine_wav(
    *,
    frequency: float = 440.0,
    duration_s: float = 1.0,
    sample_rate: int = 16000,
    amplitude: float = 0.5,
) -> bytes:
    """
    Generate a WAV file with a single sine wave tone.

    Args:
        frequency: Tone frequency in Hz.
        duration_s: Duration in seconds.
        sample_rate: Sample rate.
        amplitude: Peak amplitude (0.0-1.0).

    Returns:
        WAV file content as bytes.
    """
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    samples = (amplitude * np.sin(2 * np.pi * frequency * t) * 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())

    return buf.getvalue()


def generate_silence_wav(
    *,
    duration_s: float = 0.5,
    sample_rate: int = 16000,
) -> bytes:
    """Generate a silent WAV file."""
    return generate_sine_wav(
        frequency=0.0, duration_s=duration_s,
        sample_rate=sample_rate, amplitude=0.0,
    )
