"""
Audio feature extraction using librosa.

Extracts pitch, energy, speech rate, and MFCCs from raw audio bytes.
These features are sent to the LLM for emotion classification rather
than using a dedicated ML model (see DEC-ML-001).

@decision DEC-ML-005
@title librosa for audio feature extraction
@status accepted
@rationale librosa provides well-tested, CPU-friendly implementations of
    pitch tracking (pyin), RMS energy, onset detection, and MFCCs. No GPU
    needed. The extracted features are human-interpretable, making them
    suitable for LLM-based classification prompts.
"""

from __future__ import annotations

import io
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import librosa
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class AudioFeatures:
    """Extracted audio features for emotion classification."""

    pitch_mean: float = 0.0       # Mean fundamental frequency (Hz)
    pitch_std: float = 0.0        # Pitch variability
    energy_mean: float = 0.0      # RMS energy (amplitude)
    energy_std: float = 0.0       # Energy variability
    speech_rate: float = 0.0      # Estimated syllables/sec via onset detection
    mfcc_means: list[float] = field(default_factory=list)  # 13 MFCC coefficients
    duration_s: float = 0.0       # Audio duration in seconds
    valid: bool = True            # Whether extraction succeeded
    error: str = ""               # Error message if extraction failed


_HAS_FFMPEG = shutil.which("ffmpeg") is not None


def _ffmpeg_decode(audio_bytes: bytes, sr: int) -> tuple[np.ndarray | None, int]:
    """Convert audio bytes (webm/opus/etc.) to PCM via ffmpeg."""
    if not _HAS_FFMPEG:
        logger.warning("ffmpeg not found — cannot decode webm/opus audio")
        return None, sr
    try:
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_in:
            tmp_in.write(audio_bytes)
            tmp_in_path = tmp_in.name
        tmp_out_path = tmp_in_path.replace(".webm", ".wav")
        subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_in_path, "-ar", str(sr), "-ac", "1", tmp_out_path],
            capture_output=True, timeout=10,
        )
        y, actual_sr = librosa.load(tmp_out_path, sr=sr, mono=True)
        return y, actual_sr
    except Exception as exc:
        logger.warning("ffmpeg decode failed: %s", exc)
        return None, sr
    finally:
        Path(tmp_in_path).unlink(missing_ok=True)
        Path(tmp_out_path).unlink(missing_ok=True)


def extract_features(
    audio_bytes: bytes,
    *,
    sr: int = 16000,
    n_mfcc: int = 13,
) -> AudioFeatures:
    """
    Extract audio features from raw audio bytes.

    Args:
        audio_bytes: Raw audio data (WAV, OGG, etc. -- anything librosa can decode).
        sr: Target sample rate for resampling.
        n_mfcc: Number of MFCC coefficients to extract.

    Returns:
        AudioFeatures dataclass with extracted values. On failure,
        returns AudioFeatures(valid=False, error="...").
    """
    if not audio_bytes:
        return AudioFeatures(valid=False, error="Empty audio data")

    try:
        # Try direct decode first; if it fails (e.g. webm/opus), convert via ffmpeg
        audio_buf = io.BytesIO(audio_bytes)
        try:
            y, actual_sr = librosa.load(audio_buf, sr=sr, mono=True)
        except Exception:
            y, actual_sr = _ffmpeg_decode(audio_bytes, sr)
            if y is None:
                return AudioFeatures(valid=False, error="ffmpeg decode failed")

        if len(y) == 0:
            return AudioFeatures(valid=False, error="Decoded waveform is empty")

        duration = len(y) / actual_sr

        # Pitch via pyin
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"), sr=actual_sr,
        )
        f0_valid = f0[~np.isnan(f0)] if f0 is not None else np.array([])
        pitch_mean = float(np.mean(f0_valid)) if len(f0_valid) > 0 else 0.0
        pitch_std = float(np.std(f0_valid)) if len(f0_valid) > 0 else 0.0

        # RMS energy
        rms = librosa.feature.rms(y=y)[0]
        energy_mean = float(np.mean(rms))
        energy_std = float(np.std(rms))

        # Speech rate via onset detection
        onsets = librosa.onset.onset_detect(y=y, sr=actual_sr, units="time")
        speech_rate = len(onsets) / duration if duration > 0 else 0.0

        # MFCCs
        mfccs = librosa.feature.mfcc(y=y, sr=actual_sr, n_mfcc=n_mfcc)
        mfcc_means = [float(np.mean(mfccs[i])) for i in range(n_mfcc)]

        return AudioFeatures(
            pitch_mean=round(pitch_mean, 2),
            pitch_std=round(pitch_std, 2),
            energy_mean=round(energy_mean, 6),
            energy_std=round(energy_std, 6),
            speech_rate=round(speech_rate, 2),
            mfcc_means=[round(m, 4) for m in mfcc_means],
            duration_s=round(duration, 3),
            valid=True,
        )
    except Exception as exc:
        logger.warning("Audio feature extraction failed: %s", exc)
        return AudioFeatures(valid=False, error=str(exc))


def features_to_prompt_summary(features: AudioFeatures) -> str:
    """Format AudioFeatures for inclusion in an LLM classification prompt."""
    if not features.valid:
        return f"Audio feature extraction failed: {features.error}"
    mfcc_str = ", ".join(f"{m:.2f}" for m in features.mfcc_means[:5])
    return (
        f"Pitch: {features.pitch_mean}Hz (std={features.pitch_std}), "
        f"Energy: {features.energy_mean} (std={features.energy_std}), "
        f"Speech rate: {features.speech_rate} syl/sec, "
        f"MFCCs (first 5): [{mfcc_str}], "
        f"Duration: {features.duration_s}s"
    )
