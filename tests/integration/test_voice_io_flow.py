"""
Integration test for voice I/O flow.

Tests the full conceptual round-trip:
  Audio in -> STT -> therapist -> TTS -> audio out

Since TranscriptionAgent requires faster-whisper and the therapist
requires an LLM, this test verifies the event wiring between agents
using mocks for the ML components.

@decision DEC-TTS-007
@title TTS integration tests use real EventBus + StateManager with MockTTSProvider
@status accepted
@rationale Full pipeline verification: MessageSentEvent -> TTSAgent ->
    AudioResponseEvent. Only the TTS synthesis is mocked (MockTTSProvider returns
    deterministic PCM bytes); event routing, sentence splitting, and WAV encoding
    are exercised for real. Consistent with DEC-TEST-005 and Sacred Practice #5.
"""

from __future__ import annotations

import asyncio

import pytest

from ada.agents.tts_agent import TTSAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import (
    AudioResponseEvent,
    EventTypes,
    MessageSentEvent,
)
from ada.core.state import StateManager
from ada.tts.base import TTSAudioChunk, TTSProvider

from .conftest import MockLLMProvider


class MockTTSProvider(TTSProvider):
    async def synthesize(self, text: str) -> TTSAudioChunk:
        return TTSAudioChunk(audio_bytes=bytes(100), sample_rate=22050)

    async def is_available(self) -> bool:
        return True


@pytest.fixture
async def voice_flow():
    """Set up event bus with TTSAgent for voice flow testing."""
    bus = EventBus()
    await bus.start()
    state = StateManager(":memory:")
    await state.initialize()
    config = AdaConfig()
    llm = MockLLMProvider()

    tts_agent = TTSAgent(tts_provider=MockTTSProvider())
    tts_agent.initialize(bus, config, state, llm)
    await tts_agent.start()

    yield bus, tts_agent, state

    await tts_agent.stop()
    await bus.stop()
    await state.close()


class TestVoiceIOFlow:
    """Integration: simulated voice I/O round-trip."""

    async def test_message_sent_triggers_tts_for_voice_session(self, voice_flow):
        """Simulate: transcription -> message_received -> therapist response -> TTS."""
        bus, tts_agent, state = voice_flow
        tts_agent.enable_voice("sess-1")

        audio_events: list[AudioResponseEvent] = []

        async def capture_audio(event: AudioResponseEvent) -> None:
            audio_events.append(event)

        bus.subscribe(EventTypes.AUDIO_RESPONSE, capture_audio, "test-audio")

        # Simulate what happens after therapist processes a transcription:
        # TherapistAgent publishes MESSAGE_SENT
        await bus.publish(MessageSentEvent(
            source="therapist",
            session_id="sess-1",
            patient_id="pat-1",
            content="I hear you. That sounds challenging.",
            message_id="msg-voice-1",
            agent_name="therapist",
        ))

        await asyncio.sleep(0.5)

        assert len(audio_events) >= 1
        assert audio_events[0].session_id == "sess-1"
        assert audio_events[0].format == "wav"

    async def test_text_only_session_no_tts(self, voice_flow):
        """Sessions without voice mode should not produce audio events."""
        bus, tts_agent, state = voice_flow
        # Voice NOT enabled

        audio_events: list[AudioResponseEvent] = []

        async def capture_audio(event: AudioResponseEvent) -> None:
            audio_events.append(event)

        bus.subscribe(EventTypes.AUDIO_RESPONSE, capture_audio, "test-audio")

        await bus.publish(MessageSentEvent(
            source="therapist",
            session_id="sess-text",
            patient_id="pat-1",
            content="Regular text response.",
            message_id="msg-text-1",
            agent_name="therapist",
        ))

        await asyncio.sleep(0.3)
        assert len(audio_events) == 0

    async def test_multiple_sessions_independent(self, voice_flow):
        """Voice mode is per-session -- one session's voice doesn't affect another."""
        bus, tts_agent, state = voice_flow
        tts_agent.enable_voice("sess-voice")
        # sess-text has no voice

        audio_events: list[AudioResponseEvent] = []

        async def capture_audio(event: AudioResponseEvent) -> None:
            audio_events.append(event)

        bus.subscribe(EventTypes.AUDIO_RESPONSE, capture_audio, "test-audio")

        # Send messages for both sessions
        await bus.publish(MessageSentEvent(
            source="therapist", session_id="sess-voice",
            patient_id="pat-1", content="Voice response.",
            message_id="msg-v1", agent_name="therapist",
        ))
        await bus.publish(MessageSentEvent(
            source="therapist", session_id="sess-text",
            patient_id="pat-2", content="Text response.",
            message_id="msg-t1", agent_name="therapist",
        ))

        await asyncio.sleep(0.5)

        # Only voice session should have audio
        assert all(e.session_id == "sess-voice" for e in audio_events)
        assert len(audio_events) >= 1
