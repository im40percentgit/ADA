"""
Integration tests for TTS pipeline.

Tests MessageSentEvent -> TTSAgent -> AudioResponseEvent with sentence splitting.
Uses a mock TTSProvider to avoid requiring piper-tts at test time.

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
    """Mock TTS provider that returns predictable audio."""

    async def synthesize(self, text: str) -> TTSAudioChunk:
        # Return fake PCM bytes proportional to text length
        pcm = bytes(len(text) * 100)
        return TTSAudioChunk(audio_bytes=pcm, sample_rate=22050)

    async def is_available(self) -> bool:
        return True


@pytest.fixture
async def pipeline():
    """Set up TTSAgent with mock provider, real EventBus, real StateManager."""
    bus = EventBus()
    await bus.start()

    state = StateManager(":memory:")
    await state.initialize()

    config = AdaConfig()
    llm = MockLLMProvider()

    provider = MockTTSProvider()
    agent = TTSAgent(tts_provider=provider)

    agent.initialize(bus, config, state, llm)
    await agent.start()

    yield bus, agent

    await agent.stop()
    await bus.stop()
    await state.close()


class TestTTSPipeline:
    """Integration: MessageSentEvent -> TTSAgent -> AudioResponseEvent."""

    async def test_single_sentence_produces_one_audio_response(self, pipeline):
        bus, agent = pipeline
        agent.enable_voice("sess-1")

        received: list[AudioResponseEvent] = []

        async def capture(event: AudioResponseEvent) -> None:
            received.append(event)

        bus.subscribe(EventTypes.AUDIO_RESPONSE, capture, "test-capture")

        await bus.publish(MessageSentEvent(
            source="wellness_companion",
            session_id="sess-1",
            patient_id="pat-1",
            content="Hello, how are you feeling today?",
            message_id="msg-1",
            agent_name="wellness_companion",
        ))

        # Give the event loop time to process through two hops:
        # publish -> TTSAgent handler -> synthesize -> publish AudioResponse -> capture
        await asyncio.sleep(0.5)

        assert len(received) == 1
        assert received[0].session_id == "sess-1"
        assert received[0].message_id == "msg-1"
        assert received[0].is_final is True
        assert received[0].format == "wav"
        assert len(received[0].audio_bytes) > 44  # WAV header + data

    async def test_multi_sentence_produces_multiple_audio_responses(self, pipeline):
        bus, agent = pipeline
        agent.enable_voice("sess-1")

        received: list[AudioResponseEvent] = []

        async def capture(event: AudioResponseEvent) -> None:
            received.append(event)

        bus.subscribe(EventTypes.AUDIO_RESPONSE, capture, "test-capture")

        await bus.publish(MessageSentEvent(
            source="wellness_companion",
            session_id="sess-1",
            patient_id="pat-1",
            content="I understand that must be difficult. Let me help you think through this. What happened first?",
            message_id="msg-2",
            agent_name="wellness_companion",
        ))

        await asyncio.sleep(0.8)

        assert len(received) >= 2  # At least 2 sentences
        # Check sentence ordering
        for i, event in enumerate(received):
            assert event.sentence_index == i
            assert event.total_sentences == len(received)
        # Last one should be final
        assert received[-1].is_final is True
        # First is only final if there's exactly one sentence
        assert received[0].is_final is (len(received) == 1)

    async def test_no_audio_when_voice_disabled(self, pipeline):
        bus, agent = pipeline
        # Voice NOT enabled for sess-1

        received: list[AudioResponseEvent] = []

        async def capture(event: AudioResponseEvent) -> None:
            received.append(event)

        bus.subscribe(EventTypes.AUDIO_RESPONSE, capture, "test-capture")

        await bus.publish(MessageSentEvent(
            source="wellness_companion",
            session_id="sess-1",
            patient_id="pat-1",
            content="Hello there.",
            message_id="msg-3",
            agent_name="wellness_companion",
        ))

        await asyncio.sleep(0.3)
        assert len(received) == 0

    async def test_voice_enable_disable_toggle(self, pipeline):
        bus, agent = pipeline

        received: list[AudioResponseEvent] = []

        async def capture(event: AudioResponseEvent) -> None:
            received.append(event)

        bus.subscribe(EventTypes.AUDIO_RESPONSE, capture, "test-capture")

        # Enable voice
        agent.enable_voice("sess-1")
        await bus.publish(MessageSentEvent(
            source="wellness_companion",
            session_id="sess-1",
            patient_id="pat-1",
            content="First message.",
            message_id="msg-4",
            agent_name="wellness_companion",
        ))
        await asyncio.sleep(0.3)
        assert len(received) == 1

        # Disable voice
        agent.disable_voice("sess-1")
        await bus.publish(MessageSentEvent(
            source="wellness_companion",
            session_id="sess-1",
            patient_id="pat-1",
            content="Second message.",
            message_id="msg-5",
            agent_name="wellness_companion",
        ))
        await asyncio.sleep(0.3)
        assert len(received) == 1  # No new event

    async def test_audio_response_contains_valid_wav(self, pipeline):
        bus, agent = pipeline
        agent.enable_voice("sess-1")

        received: list[AudioResponseEvent] = []

        async def capture(event: AudioResponseEvent) -> None:
            received.append(event)

        bus.subscribe(EventTypes.AUDIO_RESPONSE, capture, "test-capture")

        await bus.publish(MessageSentEvent(
            source="wellness_companion",
            session_id="sess-1",
            patient_id="pat-1",
            content="Testing WAV output.",
            message_id="msg-6",
            agent_name="wellness_companion",
        ))

        await asyncio.sleep(0.3)

        assert len(received) == 1
        wav = received[0].audio_bytes
        # Check WAV header
        assert wav[:4] == b"RIFF"
        assert wav[8:12] == b"WAVE"
        assert wav[12:16] == b"fmt "

    async def test_empty_content_produces_no_audio(self, pipeline):
        bus, agent = pipeline
        agent.enable_voice("sess-1")

        received: list[AudioResponseEvent] = []

        async def capture(event: AudioResponseEvent) -> None:
            received.append(event)

        bus.subscribe(EventTypes.AUDIO_RESPONSE, capture, "test-capture")

        await bus.publish(MessageSentEvent(
            source="wellness_companion",
            session_id="sess-1",
            patient_id="pat-1",
            content="",
            message_id="msg-7",
            agent_name="wellness_companion",
        ))

        await asyncio.sleep(0.3)
        assert len(received) == 0

    async def test_whitespace_only_content_produces_no_audio(self, pipeline):
        bus, agent = pipeline
        agent.enable_voice("sess-1")

        received: list[AudioResponseEvent] = []

        async def capture(event: AudioResponseEvent) -> None:
            received.append(event)

        bus.subscribe(EventTypes.AUDIO_RESPONSE, capture, "test-capture")

        await bus.publish(MessageSentEvent(
            source="wellness_companion",
            session_id="sess-1",
            patient_id="pat-1",
            content="   \n  ",
            message_id="msg-8",
            agent_name="wellness_companion",
        ))

        await asyncio.sleep(0.3)
        assert len(received) == 0
