"""
Unit tests for ada.ml.stt — silence guard and TranscriptionResult.

Tests is_silent_wav() thoroughly (the critical hallucination-prevention guard)
and transcribe_audio() with a fully mocked faster-whisper model so the test
suite does not require GPU or the actual Whisper weights.

@decision DEC-ML-016
@title faster-whisper with amplitude-based silence guard
@status accepted
@rationale See ada/ml/stt.py for full rationale. These tests verify the
    silence guard is correct and that transcribe_audio() routes through the
    guard before loading the model.

@decision DEC-ML-017
@title TranscriptionResult dataclass
@status accepted
@rationale Tests confirm all fields are populated correctly and that the
    empty-text sentinel is returned for silence / decode failures.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ada.ml.stt import TranscriptionResult, is_silent_wav, transcribe_audio
from tests.fixtures.audio_gen import generate_silence_wav, generate_sine_wav


# ---------------------------------------------------------------------------
# is_silent_wav
# ---------------------------------------------------------------------------

class TestIsSilentWav:
    def test_silence_wav_returns_true(self):
        """All-zero WAV is detected as silent."""
        wav = generate_silence_wav(duration_s=1.0)
        assert is_silent_wav(wav) is True

    def test_sine_wave_returns_false(self):
        """440Hz tone at default amplitude is not silent."""
        wav = generate_sine_wav(frequency=440.0, duration_s=1.0)
        assert is_silent_wav(wav) is False

    def test_very_low_amplitude_below_threshold(self):
        """0.1% amplitude (< threshold 100/32767) is treated as silent."""
        wav = generate_sine_wav(frequency=440.0, duration_s=1.0, amplitude=0.001)
        assert is_silent_wav(wav) is True

    def test_five_percent_amplitude_passes(self):
        """5% amplitude (>>100/32767) passes the silence check."""
        wav = generate_sine_wav(frequency=440.0, duration_s=1.0, amplitude=0.05)
        assert is_silent_wav(wav) is False

    def test_empty_bytes_returns_true(self):
        """Empty input treated as silent."""
        assert is_silent_wav(b"") is True

    def test_non_wav_returns_false(self):
        """webm/opus EBML header is not a WAV — always passes through."""
        webm_header = b"\x1aEBML" + b"\x00" * 100
        assert is_silent_wav(webm_header) is False

    def test_short_silence_returns_true(self):
        """Even a 100ms silent clip is caught."""
        wav = generate_silence_wav(duration_s=0.1)
        assert is_silent_wav(wav) is True

    def test_riff_header_but_no_pcm_data(self):
        """Truncated WAV with RIFF header but no PCM data beyond offset 44."""
        # Minimal 44-byte RIFF header with no audio data
        stub = b"RIFF" + b"\x00" * 40
        # No samples -> treated as silent (empty pcm_data branch)
        assert is_silent_wav(stub) is True


# ---------------------------------------------------------------------------
# TranscriptionResult
# ---------------------------------------------------------------------------

class TestTranscriptionResult:
    def test_defaults(self):
        r = TranscriptionResult()
        assert r.text == ""
        assert r.language == ""
        assert r.confidence == 0.0
        assert r.duration_s == 0.0

    def test_bool_empty_text(self):
        """Empty text is falsy — callers check bool(result.text)."""
        assert not bool(TranscriptionResult().text)

    def test_bool_nonempty_text(self):
        r = TranscriptionResult(text="hello", language="en", confidence=0.9, duration_s=1.5)
        assert bool(r.text)
        assert r.language == "en"
        assert r.confidence == pytest.approx(0.9)
        assert r.duration_s == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# transcribe_audio — guarded paths (no real Whisper needed)
# ---------------------------------------------------------------------------

class TestTranscribeAudio:
    def test_empty_bytes_returns_empty_result(self):
        """Empty input short-circuits before any ffmpeg/model call."""
        result = transcribe_audio(b"")
        assert result.text == ""

    def test_silent_wav_returns_empty_result(self):
        """Silent WAV is caught by silence guard — model never loaded."""
        wav = generate_silence_wav(duration_s=1.0)
        # @mock-exempt: faster_whisper.WhisperModel is a third-party ML model
        # requiring ~150MB weights download and GPU/CPU inference. Mocking
        # _get_model verifies the silence guard fires before model load.
        with patch("ada.ml.stt._get_model") as mock_model:
            result = transcribe_audio(wav)
        assert result.text == ""
        mock_model.assert_not_called()

    def test_sine_wav_calls_model(self):
        """Non-silent WAV reaches the model and returns transcribed text."""
        wav = generate_sine_wav(frequency=440.0, duration_s=1.0)

        # @mock-exempt: faster_whisper.WhisperModel is a third-party ML model
        # requiring ~150MB weights and GPU inference. MagicMock simulates the
        # segment/info objects the real model returns.
        mock_segment = MagicMock()
        mock_segment.text = "hello world"
        mock_segment.avg_logprob = -0.3

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.99
        mock_info.duration = 1.0

        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.return_value = ([mock_segment], mock_info)

        with patch("ada.ml.stt._get_model", return_value=mock_model_instance):
            result = transcribe_audio(wav)

        assert result.text == "hello world"
        assert result.language == "en"
        assert result.confidence > 0.0
        assert result.duration_s == pytest.approx(1.0)

    def test_model_exception_returns_empty_result(self):
        """If the model raises, transcribe_audio returns empty (no crash)."""
        wav = generate_sine_wav(frequency=440.0, duration_s=1.0)

        # @mock-exempt: faster_whisper.WhisperModel third-party boundary.
        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.side_effect = RuntimeError("GPU OOM")

        with patch("ada.ml.stt._get_model", return_value=mock_model_instance):
            result = transcribe_audio(wav)

        assert result.text == ""

    def test_no_segments_returns_empty_text(self):
        """Model returns zero segments — empty text, zero confidence."""
        wav = generate_sine_wav(frequency=440.0, duration_s=1.0)

        # @mock-exempt: faster_whisper.WhisperModel third-party boundary.
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.5
        mock_info.duration = 1.0

        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.return_value = ([], mock_info)

        with patch("ada.ml.stt._get_model", return_value=mock_model_instance):
            result = transcribe_audio(wav)

        assert result.text == ""
        assert result.confidence == 0.0

    def test_language_kwarg_forwarded(self):
        """Explicit language is passed through to model.transcribe()."""
        wav = generate_sine_wav(frequency=440.0, duration_s=0.5)

        # @mock-exempt: faster_whisper.WhisperModel third-party boundary.
        mock_segment = MagicMock()
        mock_segment.text = "hola"
        mock_segment.avg_logprob = -0.2

        mock_info = MagicMock()
        mock_info.language = "es"
        mock_info.language_probability = 0.95
        mock_info.duration = 0.5

        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.return_value = ([mock_segment], mock_info)

        with patch("ada.ml.stt._get_model", return_value=mock_model_instance):
            result = transcribe_audio(wav, language="es")

        call_kwargs = mock_model_instance.transcribe.call_args[1]
        assert call_kwargs.get("language") == "es"
        assert result.language == "es"


# ---------------------------------------------------------------------------
# Confidence filter
# ---------------------------------------------------------------------------

class TestConfidenceFilter:
    def test_low_confidence_returns_empty(self):
        """Transcription below min_confidence is dropped."""
        wav = generate_sine_wav(frequency=440.0, duration_s=1.0)

        mock_segment = MagicMock()
        mock_segment.text = "Thanks for watching"
        mock_segment.avg_logprob = -2.0  # exp(-2.0) ≈ 0.135 — well below 0.4

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.5
        mock_info.duration = 1.0

        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.return_value = ([mock_segment], mock_info)

        with patch("ada.ml.stt._get_model", return_value=mock_model_instance):
            result = transcribe_audio(wav, min_confidence=0.4)

        assert result.text == ""

    def test_high_confidence_passes(self):
        """Transcription above min_confidence is kept."""
        wav = generate_sine_wav(frequency=440.0, duration_s=1.0)

        mock_segment = MagicMock()
        mock_segment.text = "I feel anxious"
        mock_segment.avg_logprob = -0.2  # exp(-0.2) ≈ 0.82 — above 0.4

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.99
        mock_info.duration = 1.0

        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.return_value = ([mock_segment], mock_info)

        with patch("ada.ml.stt._get_model", return_value=mock_model_instance):
            result = transcribe_audio(wav, min_confidence=0.4)

        assert result.text == "I feel anxious"

    def test_zero_min_confidence_disables_filter(self):
        """min_confidence=0.0 disables the filter — all results pass."""
        wav = generate_sine_wav(frequency=440.0, duration_s=1.0)

        mock_segment = MagicMock()
        mock_segment.text = "anything"
        mock_segment.avg_logprob = -5.0

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.1
        mock_info.duration = 1.0

        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.return_value = ([mock_segment], mock_info)

        with patch("ada.ml.stt._get_model", return_value=mock_model_instance):
            result = transcribe_audio(wav, min_confidence=0.0)

        assert result.text == "anything"


# ---------------------------------------------------------------------------
# VAD parameter forwarding
# ---------------------------------------------------------------------------

class TestVadParamsForwarding:
    def test_vad_filter_and_params_forwarded(self):
        """vad_filter, vad_parameters, and no_speech_threshold are passed to model.transcribe()."""
        wav = generate_sine_wav(frequency=440.0, duration_s=0.5)

        mock_segment = MagicMock()
        mock_segment.text = "hello"
        mock_segment.avg_logprob = -0.2

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.99
        mock_info.duration = 0.5

        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.return_value = ([mock_segment], mock_info)

        with patch("ada.ml.stt._get_model", return_value=mock_model_instance):
            transcribe_audio(wav, vad_filter=True, vad_threshold=0.6)

        call_kwargs = mock_model_instance.transcribe.call_args[1]
        assert call_kwargs["vad_filter"] is True
        assert call_kwargs["vad_parameters"] == {"threshold": 0.6}
        assert call_kwargs["no_speech_threshold"] == 0.6

    def test_vad_disabled_by_default(self):
        """When vad_filter=False, vad_filter/vad_parameters not in kwargs."""
        wav = generate_sine_wav(frequency=440.0, duration_s=0.5)

        mock_segment = MagicMock()
        mock_segment.text = "hello"
        mock_segment.avg_logprob = -0.2

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.99
        mock_info.duration = 0.5

        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.return_value = ([mock_segment], mock_info)

        with patch("ada.ml.stt._get_model", return_value=mock_model_instance):
            transcribe_audio(wav, vad_filter=False, vad_threshold=0.5)

        call_kwargs = mock_model_instance.transcribe.call_args[1]
        assert "vad_filter" not in call_kwargs
        assert "vad_parameters" not in call_kwargs
        assert call_kwargs["no_speech_threshold"] == 0.6  # always set, independent of VAD
