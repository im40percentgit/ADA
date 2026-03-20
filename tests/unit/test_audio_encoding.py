"""
Unit tests for ada.tts.encoding — PCM-to-WAV conversion.

Validates: RIFF magic bytes, chunk sizes, sample rate, channels, bits per
sample, data segment matches input PCM, and parameterized variations.
"""

from __future__ import annotations

import struct

import pytest

from ada.tts.encoding import pcm_to_wav


class TestPcmToWav:
    """Tests for pcm_to_wav()."""

    def _parse_wav_header(self, wav_bytes: bytes) -> dict:
        """Parse the 44-byte WAV header into a dict."""
        assert len(wav_bytes) >= 44, "WAV must be at least 44 bytes"
        fields = struct.unpack("<4sI4s4sIHHIIHH4sI", wav_bytes[:44])
        return {
            "riff_magic": fields[0],
            "file_size": fields[1],
            "wave_magic": fields[2],
            "fmt_id": fields[3],
            "fmt_size": fields[4],
            "audio_format": fields[5],
            "channels": fields[6],
            "sample_rate": fields[7],
            "byte_rate": fields[8],
            "block_align": fields[9],
            "bits_per_sample": fields[10],
            "data_id": fields[11],
            "data_size": fields[12],
        }

    def test_riff_magic(self):
        wav = pcm_to_wav(b"\x00" * 100)
        header = self._parse_wav_header(wav)
        assert header["riff_magic"] == b"RIFF"
        assert header["wave_magic"] == b"WAVE"

    def test_fmt_chunk(self):
        wav = pcm_to_wav(b"\x00" * 100)
        header = self._parse_wav_header(wav)
        assert header["fmt_id"] == b"fmt "
        assert header["fmt_size"] == 16
        assert header["audio_format"] == 1  # PCM

    def test_data_chunk(self):
        pcm = b"\x01\x02" * 50  # 100 bytes
        wav = pcm_to_wav(pcm)
        header = self._parse_wav_header(wav)
        assert header["data_id"] == b"data"
        assert header["data_size"] == 100

    def test_file_size_field(self):
        pcm = b"\x00" * 200
        wav = pcm_to_wav(pcm)
        header = self._parse_wav_header(wav)
        # file_size = 36 + data_size
        assert header["file_size"] == 36 + 200

    def test_default_parameters(self):
        wav = pcm_to_wav(b"\x00" * 100)
        header = self._parse_wav_header(wav)
        assert header["sample_rate"] == 22050
        assert header["channels"] == 1
        assert header["bits_per_sample"] == 16
        assert header["byte_rate"] == 22050 * 1 * 2
        assert header["block_align"] == 1 * 2

    def test_custom_sample_rate(self):
        wav = pcm_to_wav(b"\x00" * 100, sample_rate=44100)
        header = self._parse_wav_header(wav)
        assert header["sample_rate"] == 44100
        assert header["byte_rate"] == 44100 * 1 * 2

    def test_stereo(self):
        wav = pcm_to_wav(b"\x00" * 100, channels=2)
        header = self._parse_wav_header(wav)
        assert header["channels"] == 2
        assert header["byte_rate"] == 22050 * 2 * 2
        assert header["block_align"] == 2 * 2

    def test_data_bytes_preserved(self):
        pcm = bytes(range(256)) * 4  # 1024 bytes of varied data
        wav = pcm_to_wav(pcm)
        assert wav[44:] == pcm

    def test_total_length(self):
        pcm = b"\x00" * 500
        wav = pcm_to_wav(pcm)
        assert len(wav) == 44 + 500

    def test_empty_pcm(self):
        wav = pcm_to_wav(b"")
        header = self._parse_wav_header(wav)
        assert header["data_size"] == 0
        assert header["file_size"] == 36
        assert len(wav) == 44

    def test_wav_is_valid_for_wave_module(self):
        """Verify the output can be read by Python's wave module."""
        import io
        import wave

        pcm = b"\x00\x01" * 1000  # 2000 bytes of PCM
        wav_bytes = pcm_to_wav(pcm, sample_rate=16000)

        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            assert wf.getnframes() == 1000
            frames = wf.readframes(1000)
            assert frames == pcm
