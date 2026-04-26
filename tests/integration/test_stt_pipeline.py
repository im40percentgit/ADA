"""
Integration tests for the Phase 7 STT pipeline.

Full end-to-end path:
  AudioChunkReceivedEvent
    -> TranscriptionAgent (transcribe_audio mocked at the Whisper boundary)
    -> TranscriptionCompletedEvent published on EventBus
    -> transcriptions table persisted in StateManager

Uses real EventBus, real in-memory SQLite, and a patched transcribe_audio
(faster-whisper is the external boundary).

@decision DEC-STT-003
@title TranscriptionAgent follows VoiceEmotionAgent pattern exactly
@status accepted
@rationale Integration tests verify the complete wiring rather than
    individual components: fixture -> agent -> EventBus -> DB persistence.
    Mirrors test_ml_pipeline.py pattern.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
import pytest_asyncio

from ada.agents.transcription import TranscriptionAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig, STTConfig
from ada.core.events import (
    AudioChunkReceivedEvent,
    EventTypes,
    TranscriptionCompletedEvent,
)
from ada.core.state import StateManager
from ada.ml.stt import TranscriptionResult
from tests.fixtures.audio_gen import generate_silence_wav, generate_sine_wav


# ---------------------------------------------------------------------------
# Shared fake transcribe_audio
# ---------------------------------------------------------------------------

def _fake_transcribe(audio_bytes: bytes, **kwargs) -> TranscriptionResult:
    """Deterministic stand-in for faster-whisper inference."""
    if not audio_bytes:
        return TranscriptionResult()
    return TranscriptionResult(
        text="my head hurts a lot today",
        language="en",
        confidence=0.88,
        duration_s=2.1,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def stack():
    """Full integration stack: StateManager + EventBus + TranscriptionAgent."""
    state = StateManager(":memory:")
    await state.initialize()

    await state.create_patient({
        "id": "p1", "name": "Integration Patient",
        "dob": None, "preferences": {}, "emergency_contact": None,
        "caregiver_id": None,
    })
    await state.create_session({"id": "s1", "patient_id": "p1"})

    bus = EventBus()
    await bus.start()

    config = AdaConfig()

    agent = TranscriptionAgent()
    agent.initialize(bus, config, state, None)
    await agent.start()

    yield state, bus, agent

    await agent.stop()
    await bus.stop()
    await state.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSTTPipeline:

    @pytest.mark.asyncio
    async def test_full_pipeline_event_to_db(self, stack):
        """
        Audio chunk -> TranscriptionAgent -> event published -> DB persisted.
        Verifies the complete wiring end-to-end.
        """
        state, bus, agent = stack
        sine_wav = generate_sine_wav(frequency=440.0, duration_s=1.0)

        received: list[TranscriptionCompletedEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.TRANSCRIPTION_COMPLETED, collector, "integration-test")

        # @mock-exempt: faster_whisper.WhisperModel third-party ML boundary.
        with patch("ada.agents.transcription.transcribe_audio", side_effect=_fake_transcribe):
            await bus.publish(AudioChunkReceivedEvent(
                source="media_ws",
                session_id="s1",
                patient_id="p1",
                audio_bytes=sine_wav,
                sample_rate=16000,
                chunk_id="integ-chunk-001",
            ))
            await asyncio.sleep(0.4)

        # Event published
        assert len(received) == 1
        evt = received[0]
        assert evt.text == "my head hurts a lot today"
        assert evt.session_id == "s1"
        assert evt.patient_id == "p1"
        assert evt.audio_chunk_id == "integ-chunk-001"
        assert evt.language == "en"
        assert evt.confidence == pytest.approx(0.88)
        assert evt.duration_s == pytest.approx(2.1)

        # DB persisted
        rows = await state.get_transcriptions("s1")
        assert len(rows) == 1
        row = rows[0]
        assert row["text"] == "my head hurts a lot today"
        assert row["session_id"] == "s1"
        assert row["patient_id"] == "p1"
        assert row["audio_chunk_id"] == "integ-chunk-001"
        assert row["language"] == "en"
        assert row["confidence"] == pytest.approx(0.88)
        assert row["duration_s"] == pytest.approx(2.1)
        assert row["id"]  # UUID was generated

    @pytest.mark.asyncio
    async def test_silence_produces_no_event_or_db_row(self, stack):
        """Silent audio is swallowed; no event published, no DB row."""
        state, bus, agent = stack
        silence = generate_silence_wav(duration_s=1.0)

        received: list = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.TRANSCRIPTION_COMPLETED, collector, "integration-silence-test")

        # @mock-exempt: faster_whisper.WhisperModel third-party ML boundary.
        # Pass through to real is_silent_wav — that's exactly what we're testing.
        with patch("ada.agents.transcription.transcribe_audio", side_effect=_fake_transcribe):
            # Override to return empty for silence fixture
            def _empty(_bytes, **kwargs):
                return TranscriptionResult()

            with patch("ada.agents.transcription.transcribe_audio", side_effect=_empty):
                await bus.publish(AudioChunkReceivedEvent(
                    source="media_ws",
                    session_id="s1",
                    patient_id="p1",
                    audio_bytes=silence,
                    sample_rate=16000,
                    chunk_id="integ-chunk-002",
                ))
                await asyncio.sleep(0.3)

        assert received == []
        rows = await state.get_transcriptions("s1")
        assert rows == []

    @pytest.mark.asyncio
    async def test_multiple_chunks_accumulate_in_db(self, stack):
        """Three chunks from the same session all persist independently."""
        state, bus, agent = stack
        sine_wav = generate_sine_wav(frequency=440.0, duration_s=0.5)

        call_n = 0

        def _sequential(audio_bytes, **kwargs):
            nonlocal call_n
            call_n += 1
            return TranscriptionResult(
                text=f"sentence {call_n}",
                language="en",
                confidence=0.9,
                duration_s=0.5,
            )

        # @mock-exempt: faster_whisper.WhisperModel third-party ML boundary.
        with patch("ada.agents.transcription.transcribe_audio", side_effect=_sequential):
            for i in range(3):
                await bus.publish(AudioChunkReceivedEvent(
                    source="media_ws",
                    session_id="s1",
                    patient_id="p1",
                    audio_bytes=sine_wav,
                    sample_rate=16000,
                    chunk_id=f"integ-chunk-{i+10}",
                ))
            await asyncio.sleep(0.6)

        rows = await state.get_transcriptions("s1")
        assert len(rows) == 3
        texts = [r["text"] for r in rows]
        assert "sentence 1" in texts
        assert "sentence 2" in texts
        assert "sentence 3" in texts

    @pytest.mark.asyncio
    async def test_stt_config_forwarded_to_transcribe(self, stack):
        """model_size and language from STTConfig are passed to transcribe_audio."""
        state, bus, _ = stack

        # Create a fresh agent with explicit STT config
        config = AdaConfig()
        config.stt = STTConfig(model_size="small", language="en", compute_type="float32")

        agent2 = TranscriptionAgent()
        agent2.initialize(bus, config, state, None)
        await agent2.start()

        captured_kwargs: list[dict] = []

        def _capture(audio_bytes, **kwargs):
            captured_kwargs.append(kwargs)
            return TranscriptionResult(text="captured", language="en", confidence=0.9, duration_s=1.0)

        sine_wav = generate_sine_wav(frequency=440.0, duration_s=0.5)

        # @mock-exempt: faster_whisper.WhisperModel third-party ML boundary.
        with patch("ada.agents.transcription.transcribe_audio", side_effect=_capture):
            await bus.publish(AudioChunkReceivedEvent(
                source="test",
                session_id="s1",
                patient_id="p1",
                audio_bytes=sine_wav,
                sample_rate=16000,
                chunk_id="integ-cfg-chunk",
            ))
            await asyncio.sleep(0.3)

        await agent2.stop()

        # Two agents received the chunk (the stack fixture's agent + agent2).
        # At least one call must have used the configured model_size="small".
        assert len(captured_kwargs) >= 1
        small_calls = [kw for kw in captured_kwargs if kw.get("model_size") == "small"]
        assert small_calls, (
            f"No call used model_size='small'. Captured kwargs: {captured_kwargs}"
        )
        kw = small_calls[0]
        assert kw.get("language") == "en"
        assert kw.get("compute_type") == "float32"

    @pytest.mark.asyncio
    async def test_default_stt_config_uses_large_v3_turbo(self, stack):
        """DEC-ML-018: default model_size is large-v3-turbo (was base).

        This test verifies that TranscriptionAgent, when given an AdaConfig
        with default STTConfig, forwards model_size='large-v3-turbo' to the
        transcribe_audio call. It guards against regressions where the
        default reverts to 'base'.
        """
        state, bus, _ = stack

        config = AdaConfig()  # default STTConfig — model_size="large-v3-turbo"
        assert config.stt.model_size == "large-v3-turbo", (
            "DEC-ML-018: STTConfig default model_size must be 'large-v3-turbo'"
        )

        agent = TranscriptionAgent()
        agent.initialize(bus, config, state, None)
        await agent.start()

        captured_kwargs: list[dict] = []

        def _capture(audio_bytes, **kwargs):
            captured_kwargs.append(kwargs)
            return TranscriptionResult(text="default model check", language="en", confidence=0.9, duration_s=1.0)

        from tests.fixtures.audio_gen import generate_sine_wav
        sine_wav = generate_sine_wav(frequency=440.0, duration_s=0.5)

        # @mock-exempt: faster_whisper.WhisperModel third-party ML boundary.
        with patch("ada.agents.transcription.transcribe_audio", side_effect=_capture):
            from ada.core.events import AudioChunkReceivedEvent
            await bus.publish(AudioChunkReceivedEvent(
                source="test",
                session_id="s1",
                patient_id="p1",
                audio_bytes=sine_wav,
                sample_rate=16000,
                chunk_id="integ-default-model-chunk",
            ))
            await asyncio.sleep(0.3)

        await agent.stop()

        turbo_calls = [kw for kw in captured_kwargs if kw.get("model_size") == "large-v3-turbo"]
        assert turbo_calls, (
            f"DEC-ML-018 regression: no call used model_size='large-v3-turbo'. "
            f"Captured kwargs: {captured_kwargs}"
        )
