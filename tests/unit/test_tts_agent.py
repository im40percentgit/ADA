"""
Unit tests for TTSAgent.

Follows the VoiceEmotionAgent test pattern: real EventBus, MockLLMProvider,
MockTTSProvider with predictable audio output. Tests cover event routing,
voice session management, sentence splitting, and error resilience.

@decision DEC-TTS-006
@title TTSAgent tests use MockTTSProvider + real EventBus (no internal mocks)
@status accepted
@rationale Consistent with Sacred Practice #5 and DEC-TEST-005. MockTTSProvider
    is a real TTSProvider subclass returning deterministic PCM bytes. The real
    EventBus exercises the full publish/subscribe path. Sentence splitting and
    WAV encoding are tested in their own unit test files.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest
import pytest_asyncio

from ada.agents.tts_agent import TTSAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import (
    AudioResponseEvent,
    EventTypes,
    MessageSentEvent,
)
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from ada.tts.base import TTSAudioChunk, TTSProvider


# ---------------------------------------------------------------------------
# MockLLMProvider (required by BaseAgent.initialize)
# ---------------------------------------------------------------------------

class MockLLMProvider(LLMProvider):
    """Minimal LLM stub — TTSAgent doesn't use LLM, but BaseAgent requires one."""

    async def complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> LLMResponse:
        return LLMResponse(content="", model="mock", input_tokens=0, output_tokens=0)

    async def stream(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        yield ""


# ---------------------------------------------------------------------------
# MockTTSProvider
# ---------------------------------------------------------------------------

class MockTTSProvider(TTSProvider):
    """Deterministic TTS stub returning predictable PCM bytes."""

    def __init__(
        self,
        sample_rate: int = 22050,
        channels: int = 1,
        sample_width: int = 2,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width
        self.calls: list[str] = []
        self._fail_on: set[str] = set()
        self._return_empty: set[str] = set()

    def fail_on(self, text: str) -> None:
        """Make synthesize() raise for a specific input text."""
        self._fail_on.add(text)

    def return_empty_on(self, text: str) -> None:
        """Make synthesize() return empty audio for a specific input text."""
        self._return_empty.add(text)

    async def synthesize(self, text: str) -> TTSAudioChunk:
        self.calls.append(text)
        if text in self._fail_on:
            raise RuntimeError(f"MockTTSProvider: deliberate failure for {text!r}")
        if text in self._return_empty:
            return TTSAudioChunk(
                audio_bytes=b"",
                sample_rate=self.sample_rate,
                channels=self.channels,
                sample_width=self.sample_width,
            )
        # Return deterministic PCM: 100 bytes of 0x42
        pcm = b"\x42" * 100
        return TTSAudioChunk(
            audio_bytes=pcm,
            sample_rate=self.sample_rate,
            channels=self.channels,
            sample_width=self.sample_width,
        )

    async def is_available(self) -> bool:
        return True


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
    """Fully wired TTSAgent with real EventBus and MockTTSProvider."""
    bus = EventBus()
    await bus.start()
    llm = MockLLMProvider()
    config = AdaConfig()
    tts_provider = MockTTSProvider()
    agent = TTSAgent(tts_provider=tts_provider)
    agent.initialize(bus, config, state, llm)
    await agent.start()
    yield agent, bus, tts_provider, state
    await agent.stop()
    await bus.stop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTTSAgentProperties:
    def test_name(self):
        agent = TTSAgent()
        assert agent.name == "tts"

    def test_description(self):
        agent = TTSAgent()
        assert "tts" in agent.description.lower()
        assert "speech" in agent.description.lower()

    def test_supported_events(self):
        agent = TTSAgent()
        assert EventTypes.MESSAGE_SENT in agent.supported_events

    def test_tts_provider_assertion_when_none(self):
        agent = TTSAgent()
        with pytest.raises(AssertionError, match="no TTS provider"):
            _ = agent.tts_provider

    def test_set_tts_provider(self):
        agent = TTSAgent()
        provider = MockTTSProvider()
        agent.set_tts_provider(provider)
        assert agent.tts_provider is provider


class TestVoiceSessionManagement:
    def test_enable_voice(self):
        agent = TTSAgent()
        agent.enable_voice("session-001")
        assert agent.is_voice_enabled("session-001")

    def test_disable_voice(self):
        agent = TTSAgent()
        agent.enable_voice("session-001")
        agent.disable_voice("session-001")
        assert not agent.is_voice_enabled("session-001")

    def test_is_voice_enabled_default_false(self):
        agent = TTSAgent()
        assert not agent.is_voice_enabled("session-001")

    def test_disable_nonexistent_session_no_error(self):
        agent = TTSAgent()
        # discard on a set that doesn't contain the item should not raise
        agent.disable_voice("session-nonexistent")
        assert not agent.is_voice_enabled("session-nonexistent")

    def test_multiple_sessions(self):
        agent = TTSAgent()
        agent.enable_voice("session-001")
        agent.enable_voice("session-002")
        assert agent.is_voice_enabled("session-001")
        assert agent.is_voice_enabled("session-002")
        agent.disable_voice("session-001")
        assert not agent.is_voice_enabled("session-001")
        assert agent.is_voice_enabled("session-002")


class TestTTSAgentEventHandling:
    @pytest.mark.asyncio
    async def test_skips_non_voice_sessions(self, agent_setup):
        agent, bus, tts_provider, state = agent_setup
        # Voice NOT enabled for session-001

        received: list[AudioResponseEvent] = []
        bus.subscribe(EventTypes.AUDIO_RESPONSE, lambda e: received.append(e), "test-skip")

        await bus.publish(MessageSentEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            message_id="msg-001",
            content="Hello, how are you?",
        ))

        await asyncio.sleep(0.1)

        assert len(received) == 0
        assert tts_provider.calls == []

    @pytest.mark.asyncio
    async def test_synthesizes_single_sentence(self, agent_setup):
        agent, bus, tts_provider, state = agent_setup
        agent.enable_voice("session-001")

        received: list[AudioResponseEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.AUDIO_RESPONSE, collector, "test-single")

        await bus.publish(MessageSentEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            message_id="msg-001",
            content="Hello there.",
        ))

        await asyncio.sleep(0.2)

        assert len(received) == 1
        evt = received[0]
        assert isinstance(evt, AudioResponseEvent)
        assert evt.session_id == "session-001"
        assert evt.patient_id == "patient-001"
        assert evt.message_id == "msg-001"
        assert evt.sentence_index == 0
        assert evt.total_sentences == 1
        assert evt.is_final is True
        assert evt.format == "wav"
        assert evt.sample_rate == 22050
        assert len(evt.audio_bytes) > 0
        # WAV header starts with RIFF
        assert evt.audio_bytes[:4] == b"RIFF"

    @pytest.mark.asyncio
    async def test_synthesizes_multiple_sentences(self, agent_setup):
        agent, bus, tts_provider, state = agent_setup
        agent.enable_voice("session-001")

        received: list[AudioResponseEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.AUDIO_RESPONSE, collector, "test-multi")

        await bus.publish(MessageSentEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            message_id="msg-002",
            content="I understand how you feel. That sounds really difficult. How can I help?",
        ))

        await asyncio.sleep(0.3)

        assert len(received) == 3
        # Check sentence indices
        for i, evt in enumerate(received):
            assert evt.sentence_index == i
            assert evt.total_sentences == 3
        # Only the last sentence should have is_final=True
        assert received[0].is_final is False
        assert received[1].is_final is False
        assert received[2].is_final is True

    @pytest.mark.asyncio
    async def test_empty_content_produces_no_events(self, agent_setup):
        agent, bus, tts_provider, state = agent_setup
        agent.enable_voice("session-001")

        received: list[AudioResponseEvent] = []
        bus.subscribe(EventTypes.AUDIO_RESPONSE, lambda e: received.append(e), "test-empty")

        await bus.publish(MessageSentEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            message_id="msg-003",
            content="",
        ))

        await asyncio.sleep(0.1)

        assert len(received) == 0
        assert tts_provider.calls == []

    @pytest.mark.asyncio
    async def test_whitespace_content_produces_no_events(self, agent_setup):
        agent, bus, tts_provider, state = agent_setup
        agent.enable_voice("session-001")

        received: list[AudioResponseEvent] = []
        bus.subscribe(EventTypes.AUDIO_RESPONSE, lambda e: received.append(e), "test-ws")

        await bus.publish(MessageSentEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            message_id="msg-004",
            content="   \n\t  ",
        ))

        await asyncio.sleep(0.1)

        assert len(received) == 0
        assert tts_provider.calls == []

    @pytest.mark.asyncio
    async def test_synthesis_failure_doesnt_block_others(self, agent_setup):
        agent, bus, tts_provider, state = agent_setup
        agent.enable_voice("session-001")

        # The sentence splitter will split this into 3 sentences.
        # Make the second one fail.
        content = "First sentence is fine. Second sentence will fail. Third sentence should work."

        received: list[AudioResponseEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.AUDIO_RESPONSE, collector, "test-fail")

        # We need to know what the second sentence text will be after splitting
        from ada.tts.sentence_splitter import split_sentences
        sentences = split_sentences(content)
        assert len(sentences) == 3
        tts_provider.fail_on(sentences[1])

        await bus.publish(MessageSentEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            message_id="msg-005",
            content=content,
        ))

        await asyncio.sleep(0.3)

        # Should have 2 events (first and third), second failed
        assert len(received) == 2
        assert received[0].sentence_index == 0
        assert received[1].sentence_index == 2

    @pytest.mark.asyncio
    async def test_empty_audio_from_provider_skipped(self, agent_setup):
        agent, bus, tts_provider, state = agent_setup
        agent.enable_voice("session-001")

        content = "First is normal. Second returns empty audio. Third is normal too."

        from ada.tts.sentence_splitter import split_sentences
        sentences = split_sentences(content)
        assert len(sentences) == 3
        tts_provider.return_empty_on(sentences[1])

        received: list[AudioResponseEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.AUDIO_RESPONSE, collector, "test-empty-audio")

        await bus.publish(MessageSentEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            message_id="msg-006",
            content=content,
        ))

        await asyncio.sleep(0.3)

        # Should have 2 events (sentence indices 0 and 2), second had empty audio
        assert len(received) == 2
        assert received[0].sentence_index == 0
        assert received[1].sentence_index == 2

    @pytest.mark.asyncio
    async def test_source_is_agent_name(self, agent_setup):
        agent, bus, tts_provider, state = agent_setup
        agent.enable_voice("session-001")

        received: list[AudioResponseEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.AUDIO_RESPONSE, collector, "test-source")

        await bus.publish(MessageSentEvent(
            source="therapist",
            session_id="session-001",
            patient_id="patient-001",
            message_id="msg-007",
            content="Hello.",
        ))

        await asyncio.sleep(0.2)

        assert len(received) == 1
        assert received[0].source == "tts"

    @pytest.mark.asyncio
    async def test_voice_disabled_mid_stream(self, agent_setup):
        """Verify that disabling voice prevents future events from being synthesized."""
        agent, bus, tts_provider, state = agent_setup
        agent.enable_voice("session-001")

        received: list[AudioResponseEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.AUDIO_RESPONSE, collector, "test-disable")

        # First message should produce audio
        await bus.publish(MessageSentEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            message_id="msg-008",
            content="First message.",
        ))

        await asyncio.sleep(0.2)
        assert len(received) == 1

        # Disable voice
        agent.disable_voice("session-001")

        # Second message should NOT produce audio
        await bus.publish(MessageSentEvent(
            source="test",
            session_id="session-001",
            patient_id="patient-001",
            message_id="msg-009",
            content="Second message.",
        ))

        await asyncio.sleep(0.2)
        assert len(received) == 1  # Still 1, no new events
