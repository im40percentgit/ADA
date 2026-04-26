"""
Unit tests for ada.tts — TTSProvider ABC, PiperProvider, and factory.

TTSProvider is tested for ABC enforcement (cannot instantiate directly).
PiperProvider is tested with mocked piper import to avoid requiring the
ONNX model. The factory is tested for provider selection and error handling.

@decision DEC-TTS-003
@title Kokoro-82M as default TTS, Piper retained for low-resource path
@status accepted
@rationale Factory default changed from piper to kokoro. Tests verify
    create_tts_provider() returns KokoroProvider by default and PiperProvider
    when explicitly requested. Both must be importable without downloading
    model files (lazy loading deferred until synthesize() is called).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from ada.tts.base import TTSAudioChunk, TTSProvider
from ada.tts.factory import create_tts_provider
from ada.tts.piper import PiperProvider


# ---------------------------------------------------------------------------
# TTSAudioChunk dataclass
# ---------------------------------------------------------------------------

class TestTTSAudioChunk:
    """Tests for the TTSAudioChunk dataclass."""

    def test_defaults(self):
        chunk = TTSAudioChunk(audio_bytes=b"hello")
        assert chunk.audio_bytes == b"hello"
        assert chunk.sample_rate == 22050
        assert chunk.channels == 1
        assert chunk.sample_width == 2
        assert chunk.format == "pcm"

    def test_custom_values(self):
        chunk = TTSAudioChunk(
            audio_bytes=b"\x00",
            sample_rate=44100,
            channels=2,
            sample_width=4,
            format="wav",
        )
        assert chunk.sample_rate == 44100
        assert chunk.channels == 2
        assert chunk.sample_width == 4
        assert chunk.format == "wav"


# ---------------------------------------------------------------------------
# TTSProvider ABC
# ---------------------------------------------------------------------------

class TestTTSProviderABC:
    """Tests for TTSProvider abstract base class."""

    def test_cannot_instantiate(self):
        """TTSProvider is abstract — direct instantiation must raise."""
        with pytest.raises(TypeError, match="synthesize|is_available"):
            TTSProvider()

    def test_concrete_subclass_works(self):
        """A fully implemented subclass can be instantiated."""

        class DummyProvider(TTSProvider):
            async def synthesize(self, text: str) -> TTSAudioChunk:
                return TTSAudioChunk(audio_bytes=b"dummy")

            async def is_available(self) -> bool:
                return True

        provider = DummyProvider()
        assert provider is not None

    @pytest.mark.asyncio
    async def test_concrete_subclass_synthesize(self):
        """Concrete subclass synthesize() returns TTSAudioChunk."""

        class DummyProvider(TTSProvider):
            async def synthesize(self, text: str) -> TTSAudioChunk:
                return TTSAudioChunk(audio_bytes=text.encode())

            async def is_available(self) -> bool:
                return True

        provider = DummyProvider()
        result = await provider.synthesize("test")
        assert result.audio_bytes == b"test"

    def test_partial_implementation_fails(self):
        """Subclass missing one abstract method cannot be instantiated."""

        class PartialProvider(TTSProvider):
            async def synthesize(self, text: str) -> TTSAudioChunk:
                return TTSAudioChunk(audio_bytes=b"")
            # Missing is_available

        with pytest.raises(TypeError):
            PartialProvider()


# ---------------------------------------------------------------------------
# PiperProvider (mocked)
# ---------------------------------------------------------------------------

class TestPiperProvider:
    """Tests for PiperProvider with mocked piper dependency."""

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty_chunk(self):
        """Empty text should return empty audio without calling piper."""
        provider = PiperProvider()
        result = await provider.synthesize("")
        assert result.audio_bytes == b""
        assert result.sample_rate == 22050

    @pytest.mark.asyncio
    async def test_whitespace_text_returns_empty_chunk(self):
        """Whitespace-only text should return empty audio."""
        provider = PiperProvider()
        result = await provider.synthesize("   ")
        assert result.audio_bytes == b""

    @pytest.mark.asyncio
    async def test_is_available_without_piper(self):
        """is_available() returns False when piper is not installed."""
        provider = PiperProvider()
        with patch.dict("sys.modules", {"piper": None}):
            result = await provider.is_available()
            assert result is False

    @pytest.mark.asyncio
    async def test_is_available_with_piper(self):
        """is_available() returns True when piper is importable."""
        provider = PiperProvider()
        mock_piper = MagicMock()
        with patch.dict("sys.modules", {"piper": mock_piper}):
            result = await provider.is_available()
            assert result is True

    @pytest.mark.asyncio
    async def test_synthesize_calls_piper(self):
        """synthesize() delegates to _synthesize_blocking via to_thread."""
        sample_rate = 22050
        pcm_data = b"\x00\x01" * 100  # 200 bytes of PCM

        # Mock the PiperVoice
        mock_voice = MagicMock()
        mock_config = MagicMock()
        mock_config.sample_rate = sample_rate
        mock_voice.config = mock_config

        def fake_synthesize(text, wav_file):
            """Mimic real Piper: write PCM frames to the Wave_write object."""
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)

        mock_voice.synthesize = fake_synthesize

        # Patch _get_piper_voice to return our mock
        with patch("ada.tts.piper._get_piper_voice", return_value=mock_voice):
            provider = PiperProvider()
            result = await provider.synthesize("Hello world")

        assert result.audio_bytes == pcm_data
        assert result.sample_rate == sample_rate
        assert result.channels == 1
        assert result.sample_width == 2
        assert result.format == "pcm"

    def test_stores_model_path(self):
        """PiperProvider stores the model path for later use."""
        provider = PiperProvider(model_path="/path/to/model.onnx")
        assert provider._model_path == "/path/to/model.onnx"

    def test_default_model_path_is_none(self):
        provider = PiperProvider()
        assert provider._model_path is None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestCreateTTSProvider:
    """Tests for create_tts_provider factory."""

    def test_piper_provider(self):
        provider = create_tts_provider("piper")
        assert isinstance(provider, PiperProvider)

    def test_piper_with_model_path(self):
        provider = create_tts_provider("piper", model_path="/tmp/voice.onnx")
        assert isinstance(provider, PiperProvider)
        assert provider._model_path == "/tmp/voice.onnx"

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown TTS provider.*nope"):
            create_tts_provider("nope")

    def test_default_is_kokoro(self):
        """DEC-TTS-003: factory default changed from piper to kokoro."""
        from ada.tts.kokoro import KokoroProvider
        provider = create_tts_provider()
        assert isinstance(provider, KokoroProvider)

    def test_kokoro_provider_returned_for_kokoro(self):
        from ada.tts.kokoro import KokoroProvider
        provider = create_tts_provider("kokoro")
        assert isinstance(provider, KokoroProvider)

    def test_kokoro_with_voice_id(self):
        from ada.tts.kokoro import KokoroProvider
        provider = create_tts_provider("kokoro", voice_id="am_adam")
        assert isinstance(provider, KokoroProvider)
        assert provider._voice_id == "am_adam"
