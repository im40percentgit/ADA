"""
Unit tests for TranscriptionAgent.

Uses real EventBus, real in-memory SQLite, and a patched transcribe_audio
function (the external faster-whisper boundary) to keep tests deterministic
and fast.

Pattern mirrors test_voice_emotion_agent.py: publish AudioChunkReceivedEvent,
await asyncio.sleep for the to_thread call to complete, then assert on
published events and DB rows.

@decision DEC-STT-003
@title TranscriptionAgent follows VoiceEmotionAgent pattern exactly
@status accepted
@rationale See ada/agents/transcription.py. Tests verify: event routing,
    DB persistence, silence/empty-transcript skip, and config forwarding.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
import pytest_asyncio

from ada.agents.transcription import TranscriptionAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import (
    AudioChunkReceivedEvent,
    EventTypes,
    TranscriptionCompletedEvent,
)
from ada.core.state import StateManager
from ada.ml.stt import TranscriptionResult
from tests.fixtures.audio_gen import generate_silence_wav, generate_sine_wav


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state():
    sm = StateManager(":memory:")
    await sm.initialize()
    await sm.create_patient({
        "id": "patient-001",
        "name": "Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    await sm.create_session({"id": "session-001", "patient_id": "patient-001"})
    yield sm
    await sm.close()


@pytest_asyncio.fixture
async def agent_setup(state):
    """Fully wired TranscriptionAgent (no LLM needed)."""
    bus = EventBus()
    await bus.start()
    config = AdaConfig()
    agent = TranscriptionAgent()
    # TranscriptionAgent has no LLM — pass None; BaseAgent.initialize accepts it
    agent.initialize(bus, config, state, None)
    await agent.start()
    yield agent, bus, state
    await agent.stop()
    await bus.stop()


@pytest.fixture
def sine_wav():
    return generate_sine_wav(frequency=440.0, duration_s=1.0, sample_rate=16000)


@pytest.fixture
def silence_wav():
    return generate_silence_wav(duration_s=1.0)


def _fake_transcribe_success(
    audio_bytes: bytes,
    *,
    model_size: str = "base",
    language=None,
    compute_type: str = "int8",
) -> TranscriptionResult:
    """Deterministic stand-in for transcribe_audio."""
    return TranscriptionResult(
        text="I feel anxious today",
        language="en",
        confidence=0.92,
        duration_s=1.5,
    )


def _fake_transcribe_empty(audio_bytes, **kwargs) -> TranscriptionResult:
    """Simulates silence / decode failure (empty text)."""
    return TranscriptionResult()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTranscriptionAgent:

    @pytest.mark.asyncio
    async def test_publishes_transcription_completed_event(self, agent_setup, sine_wav):
        """Happy path: audio chunk -> TranscriptionCompletedEvent published."""
        agent, bus, state = agent_setup

        received: list[TranscriptionCompletedEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.TRANSCRIPTION_COMPLETED, collector, "test-collector")

        # @mock-exempt: faster_whisper.WhisperModel third-party ML boundary.
        with patch("ada.agents.transcription.transcribe_audio", side_effect=_fake_transcribe_success):
            await bus.publish(AudioChunkReceivedEvent(
                source="test",
                session_id="session-001",
                patient_id="patient-001",
                audio_bytes=sine_wav,
                sample_rate=16000,
                chunk_id="chunk-001",
            ))
            await asyncio.sleep(0.3)

        assert len(received) == 1
        evt = received[0]
        assert isinstance(evt, TranscriptionCompletedEvent)
        assert evt.text == "I feel anxious today"
        assert evt.session_id == "session-001"
        assert evt.patient_id == "patient-001"
        assert evt.audio_chunk_id == "chunk-001"
        assert evt.language == "en"
        assert evt.confidence == pytest.approx(0.92)
        assert evt.duration_s == pytest.approx(1.5)

    @pytest.mark.asyncio
    async def test_persists_transcription_to_db(self, agent_setup, sine_wav):
        """Transcription record written to transcriptions table."""
        agent, bus, state = agent_setup

        # @mock-exempt: faster_whisper.WhisperModel third-party ML boundary.
        with patch("ada.agents.transcription.transcribe_audio", side_effect=_fake_transcribe_success):
            await bus.publish(AudioChunkReceivedEvent(
                source="test",
                session_id="session-001",
                patient_id="patient-001",
                audio_bytes=sine_wav,
                sample_rate=16000,
                chunk_id="chunk-002",
            ))
            await asyncio.sleep(0.3)

        rows = await state.get_transcriptions("session-001")
        assert len(rows) == 1
        row = rows[0]
        assert row["text"] == "I feel anxious today"
        assert row["audio_chunk_id"] == "chunk-002"
        assert row["language"] == "en"
        assert row["confidence"] == pytest.approx(0.92)
        assert row["duration_s"] == pytest.approx(1.5)

    @pytest.mark.asyncio
    async def test_empty_transcript_not_published_or_persisted(self, agent_setup, silence_wav):
        """When transcribe_audio returns empty text, no event or DB row."""
        agent, bus, state = agent_setup

        received: list = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.TRANSCRIPTION_COMPLETED, collector, "test-collector")

        # @mock-exempt: faster_whisper.WhisperModel third-party ML boundary.
        with patch("ada.agents.transcription.transcribe_audio", side_effect=_fake_transcribe_empty):
            await bus.publish(AudioChunkReceivedEvent(
                source="test",
                session_id="session-001",
                patient_id="patient-001",
                audio_bytes=silence_wav,
                sample_rate=16000,
                chunk_id="chunk-003",
            ))
            await asyncio.sleep(0.3)

        assert received == []
        rows = await state.get_transcriptions("session-001")
        assert rows == []

    @pytest.mark.asyncio
    async def test_empty_audio_bytes_skipped(self, agent_setup):
        """Event with empty audio_bytes is silently ignored."""
        agent, bus, state = agent_setup

        received: list = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.TRANSCRIPTION_COMPLETED, collector, "test-collector")

        # @mock-exempt: faster_whisper.WhisperModel third-party ML boundary.
        with patch("ada.agents.transcription.transcribe_audio", side_effect=_fake_transcribe_success) as mock_fn:
            await bus.publish(AudioChunkReceivedEvent(
                source="test",
                session_id="session-001",
                patient_id="patient-001",
                audio_bytes=b"",
                sample_rate=16000,
                chunk_id="chunk-004",
            ))
            await asyncio.sleep(0.1)

        assert received == []
        mock_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_chunks_independent(self, agent_setup, sine_wav):
        """Two chunks produce two independent transcription records."""
        agent, bus, state = agent_setup

        call_count = 0

        def _fake_sequential(audio_bytes, **kwargs):
            nonlocal call_count
            call_count += 1
            return TranscriptionResult(
                text=f"utterance {call_count}",
                language="en",
                confidence=0.9,
                duration_s=1.0,
            )

        received: list[TranscriptionCompletedEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.TRANSCRIPTION_COMPLETED, collector, "test-collector")

        # @mock-exempt: faster_whisper.WhisperModel third-party ML boundary.
        with patch("ada.agents.transcription.transcribe_audio", side_effect=_fake_sequential):
            await bus.publish(AudioChunkReceivedEvent(
                source="test", session_id="session-001", patient_id="patient-001",
                audio_bytes=sine_wav, sample_rate=16000, chunk_id="chunk-005",
            ))
            await bus.publish(AudioChunkReceivedEvent(
                source="test", session_id="session-001", patient_id="patient-001",
                audio_bytes=sine_wav, sample_rate=16000, chunk_id="chunk-006",
            ))
            await asyncio.sleep(0.5)

        assert len(received) == 2
        assert received[0].text == "utterance 1"
        assert received[1].text == "utterance 2"

        rows = await state.get_transcriptions("session-001")
        assert len(rows) == 2
