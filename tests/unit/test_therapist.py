"""
Unit tests for ada.agents.therapist.TherapistAgent.

Tests agent lifecycle (initialize/start/stop), system prompt content,
and the pure _detect_mood helper. Integration-level message flow is
tested in tests/integration/test_chat_flow.py.

Uses a MockLLMProvider (real LLMProvider implementation, no mocks) and
an in-memory SQLite StateManager to avoid any external dependencies.

@decision DEC-TEST-004
@title Therapist unit tests use real MockLLMProvider and in-memory SQLite
@status accepted
@rationale Sacred Practice #5: test against real implementations. The
    MockLLMProvider is a genuine LLMProvider subclass that returns canned
    responses. The StateManager uses ":memory:" SQLite — real SQL, real
    schema, no mocks. This validates the agent wiring without hitting
    external APIs.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest

from ada.agents.therapist import TherapistAgent, _detect_mood
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import (
    EventTypes,
    MessageReceivedEvent,
    MessageSentEvent,
    SessionStartedEvent,
)
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse


# ---------------------------------------------------------------------------
# MockLLMProvider — real LLMProvider subclass, no mocks
# ---------------------------------------------------------------------------

class MockLLMProvider(LLMProvider):
    """
    Deterministic LLM provider for testing.

    Returns a fixed canned response for every complete() call.
    Records all calls for assertion in tests.
    """

    def __init__(self, canned_response: str = "I hear you. Tell me more.") -> None:
        self.canned_response = canned_response
        self.calls: list[dict] = []

    async def complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "system": system})
        return LLMResponse(
            content=self.canned_response,
            model="mock-model",
            input_tokens=len(str(messages)),
            output_tokens=len(self.canned_response),
        )

    async def stream(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        for word in self.canned_response.split():
            yield word + " "


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def state() -> StateManager:
    """In-memory SQLite state manager, initialized and torn down per test."""
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def llm() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.fixture
def config() -> AdaConfig:
    return AdaConfig()


@pytest.fixture
def agent(bus, config, state, llm) -> TherapistAgent:
    """Fully initialized (but not started) TherapistAgent."""
    a = TherapistAgent()
    a.initialize(bus, config, state, llm)
    return a


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------

class TestTherapistLifecycle:

    def test_agent_name(self, agent):
        assert agent.name == "therapist"

    def test_agent_description_is_non_empty(self, agent):
        assert len(agent.description) > 0

    def test_supported_events_includes_message_received(self, agent):
        assert EventTypes.MESSAGE_RECEIVED in agent.supported_events

    def test_supported_events_includes_session_started(self, agent):
        assert EventTypes.SESSION_STARTED in agent.supported_events

    def test_not_running_before_start(self, agent):
        assert not agent.is_running

    async def test_running_after_start(self, agent, bus):
        await bus.start()
        await agent.start()
        assert agent.is_running
        await agent.stop()
        await bus.stop()

    async def test_not_running_after_stop(self, agent, bus):
        await bus.start()
        await agent.start()
        await agent.stop()
        assert not agent.is_running
        await bus.stop()

    async def test_start_subscribes_to_bus(self, agent, bus):
        await bus.start()
        await agent.start()
        # Each supported event type gets one subscription
        for event_type in agent.supported_events:
            assert bus.subscriber_count(event_type) >= 1
        await agent.stop()
        await bus.stop()

    async def test_stop_unsubscribes_from_bus(self, agent, bus):
        await bus.start()
        await agent.start()
        await agent.stop()
        for event_type in agent.supported_events:
            assert bus.subscriber_count(event_type) == 0
        await bus.stop()

    def test_initialize_required_before_start(self, bus, config, state, llm):
        fresh_agent = TherapistAgent()
        # Not yet initialized — start() should raise
        with pytest.raises(RuntimeError, match="initialize"):
            asyncio.get_event_loop().run_until_complete(fresh_agent.start())

    async def test_session_started_event_handled_without_error(self, agent, bus):
        """SESSION_STARTED event should be processed gracefully."""
        await bus.start()
        await agent.start()

        event = SessionStartedEvent(session_id="sess-1", patient_id="pat-1")
        await agent.handle_event(event)
        # No assertion beyond no exception raised
        await agent.stop()
        await bus.stop()


# ---------------------------------------------------------------------------
# System prompt content
# ---------------------------------------------------------------------------

class TestSystemPromptContent:
    """The system prompt should reference key therapy techniques."""

    async def test_system_prompt_contains_cbt(self, agent, state):
        """LLM is called with a system prompt mentioning CBT."""
        # Seed a patient and session so save_message doesn't fail FK constraints
        await state.create_patient({
            "id": "pat-1", "name": "Test", "dob": None,
            "preferences": {}, "emergency_contact": None, "caregiver_id": None,
        })
        await state.create_session({
            "id": "sess-1", "patient_id": "pat-1",
        })

        event = MessageReceivedEvent(
            session_id="sess-1", patient_id="pat-1",
            content="I feel sad", message_id="msg-1",
        )
        await agent.handle_event(event)

        assert len(agent.llm.calls) == 1  # type: ignore[attr-defined]
        system_prompt = agent.llm.calls[0]["system"]  # type: ignore[attr-defined]
        assert system_prompt is not None
        assert "CBT" in system_prompt or "Cognitive Behavioural" in system_prompt

    async def test_system_prompt_contains_dbt(self, agent, state):
        await state.create_patient({
            "id": "pat-1", "name": "Test", "dob": None,
            "preferences": {}, "emergency_contact": None, "caregiver_id": None,
        })
        await state.create_session({"id": "sess-1", "patient_id": "pat-1"})

        event = MessageReceivedEvent(
            session_id="sess-1", patient_id="pat-1",
            content="hello", message_id="msg-1",
        )
        await agent.handle_event(event)

        system_prompt = agent.llm.calls[0]["system"]  # type: ignore[attr-defined]
        assert "DBT" in system_prompt or "Dialectical" in system_prompt

    async def test_system_prompt_contains_mi(self, agent, state):
        await state.create_patient({
            "id": "pat-1", "name": "Test", "dob": None,
            "preferences": {}, "emergency_contact": None, "caregiver_id": None,
        })
        await state.create_session({"id": "sess-1", "patient_id": "pat-1"})

        event = MessageReceivedEvent(
            session_id="sess-1", patient_id="pat-1",
            content="hello", message_id="msg-1",
        )
        await agent.handle_event(event)

        system_prompt = agent.llm.calls[0]["system"]  # type: ignore[attr-defined]
        assert "MI" in system_prompt or "Motivational" in system_prompt


# ---------------------------------------------------------------------------
# Message handling via event bus
# ---------------------------------------------------------------------------

class TestTherapistMessageHandling:

    async def test_handle_event_publishes_message_sent(self, agent, bus, state):
        """Processing a message should publish a MessageSentEvent."""
        await state.create_patient({
            "id": "pat-1", "name": "Test", "dob": None,
            "preferences": {}, "emergency_contact": None, "caregiver_id": None,
        })
        await state.create_session({"id": "sess-1", "patient_id": "pat-1"})

        sent_events: list[MessageSentEvent] = []

        async def capture(event):
            if isinstance(event, MessageSentEvent):
                sent_events.append(event)

        bus.subscribe(EventTypes.MESSAGE_SENT, capture, "test-capture")
        await bus.start()
        await agent.start()

        event = MessageReceivedEvent(
            session_id="sess-1", patient_id="pat-1",
            content="I feel sad today", message_id="msg-1",
        )
        # Call handle_event directly (not via bus) to keep test deterministic
        await agent.handle_event(event)
        await asyncio.sleep(0.15)

        await agent.stop()
        await bus.stop()

        assert len(sent_events) == 1
        assert sent_events[0].content == agent.llm.canned_response  # type: ignore[attr-defined]
        assert sent_events[0].session_id == "sess-1"

    async def test_message_persisted_to_state(self, agent, state):
        """User message and assistant response should both be saved to SQLite."""
        await state.create_patient({
            "id": "pat-1", "name": "Test", "dob": None,
            "preferences": {}, "emergency_contact": None, "caregiver_id": None,
        })
        await state.create_session({"id": "sess-1", "patient_id": "pat-1"})

        event = MessageReceivedEvent(
            session_id="sess-1", patient_id="pat-1",
            content="I feel sad today", message_id="msg-1",
        )
        await agent.handle_event(event)

        messages = await state.get_messages("sess-1")
        roles = [m["role"] for m in messages]
        assert "user" in roles
        assert "assistant" in roles


# ---------------------------------------------------------------------------
# _detect_mood helper (pure function)
# ---------------------------------------------------------------------------

class TestDetectMood:

    def test_negative_mood_from_sad(self):
        score, label = _detect_mood("I feel so sad today")
        assert label == "negative"
        assert score < 5.0

    def test_negative_mood_from_hopeless(self):
        score, label = _detect_mood("I feel hopeless and worthless")
        assert label == "negative"

    def test_positive_mood_from_happy(self):
        score, label = _detect_mood("I feel happy and grateful today")
        assert label == "positive"
        assert score > 5.0

    def test_mixed_mood(self):
        score, label = _detect_mood("I feel happy but also sad and anxious")
        assert label == "mixed"
        assert score == 5.0

    def test_neutral_message(self):
        score, label = _detect_mood("The weather is nice today")
        assert label == ""
        assert score == 5.0

    def test_empty_string(self):
        score, label = _detect_mood("")
        assert label == ""

    def test_returns_tuple(self):
        result = _detect_mood("I feel calm")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_score_is_float(self):
        score, _ = _detect_mood("I feel good")
        assert isinstance(score, float)
