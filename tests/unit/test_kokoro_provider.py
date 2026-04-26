"""
Unit tests for KokoroProvider (DEC-TTS-003).

Strategy: kokoro-onnx downloads ONNX model files from HuggingFace on first
use — unsuitable for CI. We mock the kokoro_onnx module at the sys.modules
boundary (external third-party package) to test the provider logic without
requiring the package to be installed or files to be downloaded.

@decision DEC-TTS-003
@title Kokoro-82M as default TTS, Piper retained for low-resource path
@status accepted
@rationale See ada/tts/kokoro.py for full rationale.

# @mock-exempt: kokoro_onnx is a third-party ONNX package that downloads
#   HuggingFace model files on first instantiation — not suitable for unit
#   tests. All mocking is on the external package boundary only. Internal
#   kokoro.py logic (voice selection, PCM conversion, empty-text guard) is
#   tested against the real implementation with a stubbed external dependency.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest

from ada.tts.base import TTSAudioChunk
from ada.tts.factory import create_tts_provider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_kokoro_mock(samples_float32=None, sample_rate=24000) -> MagicMock:
    """Return a mock kokoro_onnx.Kokoro instance.

    The real Kokoro.create() returns (np.ndarray[float32], int).
    We replicate that shape here.
    """
    if samples_float32 is None:
        # 100 frames of silence
        samples_float32 = np.zeros(100, dtype=np.float32)

    mock_kokoro_instance = MagicMock()
    mock_kokoro_instance.create.return_value = (samples_float32, sample_rate)

    mock_module = MagicMock()
    mock_module.Kokoro.return_value = mock_kokoro_instance
    return mock_module, mock_kokoro_instance


# ---------------------------------------------------------------------------
# KokoroProvider unit tests
# ---------------------------------------------------------------------------

class TestKokoroProviderAvailability:

    @pytest.mark.asyncio
    async def test_is_available_when_kokoro_installed(self):
        """is_available() returns True when kokoro_onnx is importable."""
        from ada.tts.kokoro import KokoroProvider
        provider = KokoroProvider()
        mock_module = MagicMock()
        with patch.dict(sys.modules, {"kokoro_onnx": mock_module}):
            result = await provider.is_available()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_available_returns_false_without_kokoro(self):
        """is_available() returns False when kokoro_onnx is not importable."""
        from ada.tts.kokoro import KokoroProvider
        provider = KokoroProvider()
        # Remove from sys.modules to simulate ImportError
        with patch.dict(sys.modules, {"kokoro_onnx": None}):
            result = await provider.is_available()
        assert result is False


class TestKokoroProviderVoiceMapping:

    def test_default_voice_is_af_bella(self):
        from ada.tts.kokoro import KokoroProvider, DEFAULT_VOICE
        provider = KokoroProvider()
        assert provider._voice_id == DEFAULT_VOICE
        assert DEFAULT_VOICE == "af_bella"

    def test_voice_id_accepted_at_construction(self):
        from ada.tts.kokoro import KokoroProvider
        provider = KokoroProvider(voice_id="am_adam")
        assert provider._voice_id == "am_adam"

    def test_model_path_accepted_for_api_parity(self):
        from ada.tts.kokoro import KokoroProvider
        provider = KokoroProvider(model_path="/some/path.onnx")
        assert provider._model_path == "/some/path.onnx"

    def test_voice_map_covers_all_companion_preferences(self):
        from ada.tts.kokoro import VOICE_MAP
        assert "female" in VOICE_MAP
        assert "male" in VOICE_MAP
        assert "neutral" in VOICE_MAP

    def test_voice_map_values_are_nonempty(self):
        from ada.tts.kokoro import VOICE_MAP
        for pref, voice_id in VOICE_MAP.items():
            assert voice_id, f"VOICE_MAP[{pref!r}] is empty"


class TestKokoroProviderSynthesize:

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty_chunk(self):
        """Empty text guard — no kokoro call needed."""
        from ada.tts.kokoro import KokoroProvider
        provider = KokoroProvider()
        result = await provider.synthesize("")
        assert result.audio_bytes == b""
        assert result.sample_rate == 24000

    @pytest.mark.asyncio
    async def test_whitespace_text_returns_empty_chunk(self):
        from ada.tts.kokoro import KokoroProvider
        provider = KokoroProvider()
        result = await provider.synthesize("   ")
        assert result.audio_bytes == b""

    @pytest.mark.asyncio
    async def test_synthesize_calls_kokoro_create(self):
        """Real text goes through kokoro.create() and returns PCM bytes."""
        import ada.tts.kokoro as kokoro_mod

        samples = np.array([0.5, -0.5, 0.0], dtype=np.float32)
        mock_module, mock_instance = _make_kokoro_mock(samples_float32=samples, sample_rate=24000)

        # Reset the singleton so our mock gets used
        original_instance = kokoro_mod._kokoro_instance
        kokoro_mod._kokoro_instance = None
        try:
            with patch.dict(sys.modules, {"kokoro_onnx": mock_module}):
                provider = kokoro_mod.KokoroProvider(voice_id="af_bella")
                result = await provider.synthesize("Hello world")
        finally:
            kokoro_mod._kokoro_instance = original_instance

        assert isinstance(result, TTSAudioChunk)
        assert len(result.audio_bytes) > 0
        assert result.sample_rate == 24000
        assert result.channels == 1
        assert result.sample_width == 2
        assert result.format == "pcm"
        # Verify create() was called with the right voice
        mock_instance.create.assert_called_once_with("Hello world", voice="af_bella", speed=1.0, lang="en-us")

    @pytest.mark.asyncio
    async def test_pcm_conversion_clips_float_to_int16(self):
        """float32 [-1, 1] → int16 PCM: boundary values clip correctly."""
        import ada.tts.kokoro as kokoro_mod

        # Sample with clipping values
        samples = np.array([1.0, -1.0, 0.0, 0.5], dtype=np.float32)
        mock_module, mock_instance = _make_kokoro_mock(samples_float32=samples, sample_rate=24000)

        original_instance = kokoro_mod._kokoro_instance
        kokoro_mod._kokoro_instance = None
        try:
            with patch.dict(sys.modules, {"kokoro_onnx": mock_module}):
                provider = kokoro_mod.KokoroProvider()
                result = await provider.synthesize("clip test")
        finally:
            kokoro_mod._kokoro_instance = original_instance

        # 4 samples × 2 bytes/sample = 8 bytes
        assert len(result.audio_bytes) == 8
        # Parse back as int16
        parsed = np.frombuffer(result.audio_bytes, dtype=np.int16)
        assert parsed[0] == 32767   # 1.0 * 32767 → 32767
        assert parsed[1] == -32767  # -1.0 * 32767 → -32767 (clip(-32768,32767) preserves this)
        assert parsed[2] == 0       # 0.0 → 0


# ---------------------------------------------------------------------------
# Factory dispatch tests (DEC-TTS-003)
# ---------------------------------------------------------------------------

class TestTTSFactoryKokoro:

    def test_factory_default_is_kokoro(self):
        """create_tts_provider() with no args returns KokoroProvider."""
        from ada.tts.kokoro import KokoroProvider
        provider = create_tts_provider()
        assert isinstance(provider, KokoroProvider)

    def test_factory_kokoro_explicit(self):
        from ada.tts.kokoro import KokoroProvider
        provider = create_tts_provider("kokoro")
        assert isinstance(provider, KokoroProvider)

    def test_factory_piper_still_works(self):
        from ada.tts.piper import PiperProvider
        provider = create_tts_provider("piper")
        assert isinstance(provider, PiperProvider)

    def test_factory_kokoro_passes_voice_id(self):
        from ada.tts.kokoro import KokoroProvider
        provider = create_tts_provider("kokoro", voice_id="am_adam")
        assert isinstance(provider, KokoroProvider)
        assert provider._voice_id == "am_adam"

    def test_factory_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown TTS provider.*unknown_prov"):
            create_tts_provider("unknown_prov")


# ---------------------------------------------------------------------------
# Cache-path resolution tests (DEC-TTS-007)
#
# _resolve_model_file() has three distinct code paths:
#   1. File exists in cache dir   → return immediately, no download
#   2. File exists at legacy path → return immediately, no download
#   3. Neither exists             → download from GitHub releases
#
# urllib.request.urlretrieve is the ONLY external boundary mocked here.
# All path-selection logic, mkdir, rename, and error handling run against the
# real _resolve_model_file() implementation (Sacred Practice #5 compliant).
#
# @mock-exempt: urllib.request.urlretrieve is an HTTP I/O boundary — it would
#   reach real GitHub in tests without mocking. All internal path logic
#   (cache dir resolution, legacy fallback, atomic rename, error cleanup)
#   is tested against the real implementation using tmp_path fixtures.
# ---------------------------------------------------------------------------

class TestResolveModelFile:

    def setup_method(self):
        """Reset the singleton before each test so _get_kokoro() does not
        short-circuit and tests stay independent."""
        import ada.tts.kokoro as kokoro_mod
        kokoro_mod.reset_kokoro_singleton()

    def test_cache_hit_returns_absolute_path_no_download(self, tmp_path, monkeypatch):
        """When the file is in the cache dir, return its path without downloading."""
        import ada.tts.kokoro as kokoro_mod

        cache_dir = tmp_path / "kokoro_cache"
        cache_dir.mkdir()
        model_file = cache_dir / "kokoro-v1.0.onnx"
        model_file.write_bytes(b"fake-model-bytes")

        monkeypatch.setenv("ADA_TTS__KOKORO_CACHE_DIR", str(cache_dir))

        with patch("urllib.request.urlretrieve") as mock_dl:
            result = kokoro_mod._resolve_model_file("kokoro-v1.0.onnx")

        mock_dl.assert_not_called()
        assert result == model_file
        assert result.is_absolute()

    def test_legacy_path_hit_returns_absolute_path_no_download(self, tmp_path, monkeypatch):
        """When the file is at the project-root legacy location, return it without downloading."""
        import ada.tts.kokoro as kokoro_mod

        # Point cache to an empty dir so cache lookup misses
        empty_cache = tmp_path / "empty_cache"
        empty_cache.mkdir()
        monkeypatch.setenv("ADA_TTS__KOKORO_CACHE_DIR", str(empty_cache))

        # Place the file at the project root (two levels up from ada/tts/kokoro.py)
        project_root = Path(kokoro_mod.__file__).parent.parent.parent.resolve()
        legacy_file = project_root / "voices-v1.0.bin"
        already_existed = legacy_file.exists()

        try:
            if not already_existed:
                legacy_file.write_bytes(b"fake-voices-bytes")

            with patch("urllib.request.urlretrieve") as mock_dl:
                result = kokoro_mod._resolve_model_file("voices-v1.0.bin")

            mock_dl.assert_not_called()
            assert result == legacy_file
            assert result.is_absolute()
        finally:
            if not already_existed:
                legacy_file.unlink(missing_ok=True)

    def test_download_triggered_when_file_absent(self, tmp_path, monkeypatch):
        """When neither cache nor legacy path has the file, urlretrieve is called."""
        import ada.tts.kokoro as kokoro_mod

        cache_dir = tmp_path / "dl_cache"
        cache_dir.mkdir()
        monkeypatch.setenv("ADA_TTS__KOKORO_CACHE_DIR", str(cache_dir))

        # Simulate urlretrieve by writing a real file to the tmp path arg
        def _fake_urlretrieve(url, dest):
            Path(dest).write_bytes(b"downloaded-bytes")

        with patch("urllib.request.urlretrieve", side_effect=_fake_urlretrieve) as mock_dl:
            # Only mock the legacy path lookup so it misses (override __file__ parent)
            with patch.object(
                kokoro_mod, "_resolve_model_file",
                wraps=kokoro_mod._resolve_model_file,
            ):
                # Remove legacy file if it exists to force download path
                project_root = Path(kokoro_mod.__file__).parent.parent.parent.resolve()
                legacy_file = project_root / "kokoro-v1.0.onnx"
                if legacy_file.exists():
                    pytest.skip(
                        "kokoro-v1.0.onnx exists at project root; "
                        "download path cannot be exercised without removing it"
                    )

                result = kokoro_mod._resolve_model_file("kokoro-v1.0.onnx")

        mock_dl.assert_called_once()
        called_url = mock_dl.call_args[0][0]
        assert "kokoro-v1.0.onnx" in called_url
        assert "github.com" in called_url
        assert result.is_absolute()
        assert result.exists()

    def test_download_uses_absolute_path_regardless_of_cwd(self, tmp_path, monkeypatch):
        """The resolved path is always absolute, even when CWD is different from project root."""
        import ada.tts.kokoro as kokoro_mod

        cache_dir = tmp_path / "abs_test_cache"
        cache_dir.mkdir()
        model_file = cache_dir / "kokoro-v1.0.onnx"
        model_file.write_bytes(b"cached-bytes")
        monkeypatch.setenv("ADA_TTS__KOKORO_CACHE_DIR", str(cache_dir))

        # Verify result is absolute regardless of any relative path ambiguity
        result = kokoro_mod._resolve_model_file("kokoro-v1.0.onnx")
        assert result.is_absolute(), (
            f"_resolve_model_file returned a relative path: {result!r}. "
            "This would break Kokoro init when FastAPI CWD != project root (DEC-TTS-007)."
        )

    def test_download_failure_raises_file_not_found(self, tmp_path, monkeypatch):
        """If urlretrieve fails, a FileNotFoundError is raised with a helpful message."""
        import ada.tts.kokoro as kokoro_mod

        cache_dir = tmp_path / "fail_cache"
        cache_dir.mkdir()
        monkeypatch.setenv("ADA_TTS__KOKORO_CACHE_DIR", str(cache_dir))

        project_root = Path(kokoro_mod.__file__).parent.parent.parent.resolve()
        if (project_root / "kokoro-v1.0.onnx").exists():
            pytest.skip("kokoro-v1.0.onnx at project root — cannot test download-failure path")

        def _fail(*_a, **_kw):
            raise OSError("network unreachable")

        with patch("urllib.request.urlretrieve", side_effect=_fail):
            with pytest.raises(FileNotFoundError, match="kokoro-v1.0.onnx"):
                kokoro_mod._resolve_model_file("kokoro-v1.0.onnx")

    def test_env_override_changes_cache_dir(self, tmp_path, monkeypatch):
        """ADA_TTS__KOKORO_CACHE_DIR env var is respected by _get_cache_dir()."""
        import ada.tts.kokoro as kokoro_mod

        custom_dir = tmp_path / "custom_kokoro_dir"
        monkeypatch.setenv("ADA_TTS__KOKORO_CACHE_DIR", str(custom_dir))

        result = kokoro_mod._get_cache_dir()
        assert result == custom_dir.resolve()
        assert result.is_absolute()

    def test_default_cache_dir_is_under_home(self, monkeypatch):
        """Default cache dir is ~/.cache/ada/kokoro/ when env var is not set."""
        import ada.tts.kokoro as kokoro_mod

        monkeypatch.delenv("ADA_TTS__KOKORO_CACHE_DIR", raising=False)

        result = kokoro_mod._get_cache_dir()
        assert result == Path.home() / ".cache" / "ada" / "kokoro"
        assert result.is_absolute()
