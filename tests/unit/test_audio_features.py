"""
Unit tests for audio feature extraction.

Uses synthetic WAV fixtures (programmatically generated sine waves)
to verify librosa feature extraction produces reasonable values.

@decision DEC-ML-006
@title Synthetic audio fixtures for deterministic testing
@status accepted
@rationale Programmatically generated sine waves provide deterministic,
    repeatable test inputs. A 440Hz tone has a known pitch, predictable
    energy, and extractable MFCCs. This avoids depending on external
    audio files and makes tests fully self-contained.
"""

from __future__ import annotations

import pytest

from ada.ml.audio_features import AudioFeatures, extract_features, features_to_prompt_summary
from tests.fixtures.audio_gen import generate_silence_wav, generate_sine_wav


class TestExtractFeatures:
    def test_sine_440hz_pitch(self):
        """A 440Hz sine wave should be detected near 440Hz."""
        wav_bytes = generate_sine_wav(frequency=440.0, duration_s=1.0)
        features = extract_features(wav_bytes, sr=16000)

        assert features.valid is True
        # librosa pyin should detect pitch within ~50Hz of 440
        assert 380.0 < features.pitch_mean < 500.0, f"pitch_mean={features.pitch_mean}"

    def test_sine_has_positive_energy(self):
        """A tone should have measurable RMS energy."""
        wav_bytes = generate_sine_wav(frequency=440.0, duration_s=1.0, amplitude=0.5)
        features = extract_features(wav_bytes, sr=16000)

        assert features.valid is True
        assert features.energy_mean > 0.0

    def test_silence_has_low_energy(self):
        """Silent audio should have near-zero energy."""
        wav_bytes = generate_silence_wav(duration_s=0.5)
        features = extract_features(wav_bytes, sr=16000)

        assert features.valid is True
        assert features.energy_mean < 0.01

    def test_mfcc_count(self):
        """Should extract the default 13 MFCCs."""
        wav_bytes = generate_sine_wav(frequency=440.0, duration_s=1.0)
        features = extract_features(wav_bytes, sr=16000)

        assert features.valid is True
        assert len(features.mfcc_means) == 13

    def test_custom_mfcc_count(self):
        """Should respect custom n_mfcc parameter."""
        wav_bytes = generate_sine_wav(frequency=440.0, duration_s=1.0)
        features = extract_features(wav_bytes, sr=16000, n_mfcc=20)

        assert features.valid is True
        assert len(features.mfcc_means) == 20

    def test_duration(self):
        """Duration should be approximately correct."""
        wav_bytes = generate_sine_wav(frequency=440.0, duration_s=1.0)
        features = extract_features(wav_bytes, sr=16000)

        assert features.valid is True
        assert 0.9 < features.duration_s < 1.1

    def test_speech_rate_nonnegative(self):
        """Speech rate should be non-negative."""
        wav_bytes = generate_sine_wav(frequency=440.0, duration_s=1.0)
        features = extract_features(wav_bytes, sr=16000)

        assert features.valid is True
        assert features.speech_rate >= 0.0

    def test_empty_bytes_returns_invalid(self):
        """Empty input should return valid=False."""
        features = extract_features(b"")
        assert features.valid is False
        assert "empty" in features.error.lower()

    def test_corrupt_bytes_returns_invalid(self):
        """Non-audio bytes should return valid=False."""
        features = extract_features(b"not audio data at all")
        assert features.valid is False
        assert features.error != ""

    def test_different_frequencies_different_pitch(self):
        """Higher frequency should produce higher pitch_mean."""
        low_wav = generate_sine_wav(frequency=200.0, duration_s=1.0)
        high_wav = generate_sine_wav(frequency=600.0, duration_s=1.0)
        low_features = extract_features(low_wav, sr=16000)
        high_features = extract_features(high_wav, sr=16000)

        assert low_features.valid and high_features.valid
        assert high_features.pitch_mean > low_features.pitch_mean


class TestFeaturesToPromptSummary:
    def test_valid_features(self):
        features = AudioFeatures(
            pitch_mean=220.0, pitch_std=15.0,
            energy_mean=0.05, energy_std=0.01,
            speech_rate=3.5, mfcc_means=[1.0, 2.0, 3.0, 4.0, 5.0] + [0.0] * 8,
            duration_s=2.0, valid=True,
        )
        summary = features_to_prompt_summary(features)

        assert "220.0Hz" in summary
        assert "3.5 syl/sec" in summary
        assert "2.0s" in summary

    def test_invalid_features(self):
        features = AudioFeatures(valid=False, error="Decode failed")
        summary = features_to_prompt_summary(features)

        assert "failed" in summary.lower()
        assert "Decode failed" in summary
