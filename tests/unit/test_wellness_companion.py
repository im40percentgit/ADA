"""
Unit tests for ada.agents.wellness_companion.WellnessCompanionAgent.

Tests agent lifecycle (initialize/start/stop), system prompt content
(wellness check-in contract — no CBT/DBT/MI terms), prompt contract
assertions, and the pure _detect_mood helper. Integration-level message
flow is tested in tests/integration/test_chat_flow.py.

Uses a MockLLMProvider (real LLMProvider implementation, no mocks) and
an in-memory SQLite StateManager to avoid any external dependencies.

@decision DEC-TEST-004
@title WellnessCompanionAgent unit tests use real MockLLMProvider and in-memory SQLite
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

from ada.agents.wellness_companion import WellnessCompanionAgent, _detect_mood
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
def agent(bus, config, state, llm) -> WellnessCompanionAgent:
    """Fully initialized (but not started) WellnessCompanionAgent."""
    a = WellnessCompanionAgent()
    a.initialize(bus, config, state, llm)
    return a


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------

class TestWellnessCompanionLifecycle:

    def test_agent_name(self, agent):
        assert agent.name == "wellness_companion"

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
        fresh_agent = WellnessCompanionAgent()
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
# System prompt contract tests (wellness check-in)
# ---------------------------------------------------------------------------

class TestSystemPromptContract:
    """The system prompt must satisfy the wellness companion contract:
    - Contains "wellness" and "check-in" language
    - Does NOT contain CBT/DBT/MI therapeutic terminology
    """

    def _get_system_prompt(self, agent) -> str:
        """Return the module-level _SYSTEM_PROMPT from the agent's module."""
        import ada.agents.wellness_companion as wc_module
        return wc_module._SYSTEM_PROMPT

    def test_agent_name_is_wellness_companion(self, agent):
        assert agent.name == "wellness_companion"

    def test_system_prompt_contains_wellness(self, agent):
        prompt = self._get_system_prompt(agent)
        assert "wellness" in prompt.lower()

    def test_system_prompt_contains_checkin_language(self, agent):
        prompt = self._get_system_prompt(agent)
        # Prompt should describe a check-in role
        assert "check" in prompt.lower() or "check-in" in prompt.lower()

    def test_system_prompt_does_not_contain_cbt(self, agent):
        prompt = self._get_system_prompt(agent)
        assert "CBT" not in prompt
        assert "Cognitive Behavioural Therapy" not in prompt
        assert "Cognitive Behavioral Therapy" not in prompt

    def test_system_prompt_does_not_contain_dbt(self, agent):
        prompt = self._get_system_prompt(agent)
        assert "DBT" not in prompt
        assert "Dialectical Behaviour Therapy" not in prompt
        assert "Dialectical Behavior Therapy" not in prompt

    def test_system_prompt_does_not_contain_thought_record(self, agent):
        prompt = self._get_system_prompt(agent)
        assert "thought record" not in prompt.lower()

    def test_system_prompt_does_not_contain_behavioral_activation(self, agent):
        prompt = self._get_system_prompt(agent)
        assert "behavioral activation" not in prompt.lower()
        assert "behavioural activation" not in prompt.lower()

    async def test_llm_called_with_wellness_system_prompt(self, agent, state):
        """LLM is called with the wellness companion system prompt."""
        await state.create_patient({
            "id": "pat-1", "name": "Test", "dob": None,
            "preferences": {}, "emergency_contact": None, "caregiver_id": None,
        })
        await state.create_session({
            "id": "sess-1", "patient_id": "pat-1",
        })

        event = MessageReceivedEvent(
            session_id="sess-1", patient_id="pat-1",
            content="I feel tired today", message_id="msg-1",
        )
        await agent.handle_event(event)

        assert len(agent.llm.calls) == 1  # type: ignore[attr-defined]
        system_prompt = agent.llm.calls[0]["system"]  # type: ignore[attr-defined]
        assert system_prompt is not None
        assert "wellness" in system_prompt.lower()
        assert "CBT" not in system_prompt
        assert "DBT" not in system_prompt


# ---------------------------------------------------------------------------
# Message handling via event bus
# ---------------------------------------------------------------------------

class TestWellnessCompanionMessageHandling:

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


# ---------------------------------------------------------------------------
# LLM timeout tests (RC2 — asyncio.wait_for wraps llm.complete())
# ---------------------------------------------------------------------------

class HangingLLMProvider(LLMProvider):
    """
    LLM provider that never resolves — simulates a hung API call.

    Used to verify that asyncio.wait_for() causes the agent to fall back
    to the crisis-safe error message rather than hanging indefinitely.
    """

    async def complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> LLMResponse:
        # Sleep forever — test harness will time this out via the agent's
        # internal wait_for() (config.llm.timeout set to 0.1 s in fixture)
        await asyncio.sleep(3600)
        raise AssertionError("HangingLLMProvider should never reach this line")

    async def stream(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        await asyncio.sleep(3600)
        return
        yield  # make this an async generator


class TestLLMTimeout:
    """
    Verify that RC2 is fixed: a hung LLM call is bounded by config.llm.timeout
    and the agent produces the fallback response rather than hanging.

    The config fixture sets timeout=0.1 s so tests run fast.
    """

    @pytest.fixture
    def short_timeout_config(self) -> AdaConfig:
        """AdaConfig with a very short LLM timeout to make tests fast."""
        cfg = AdaConfig()
        # Pydantic model — create a new LLMConfig with short timeout
        from ada.core.config import LLMConfig
        cfg.llm = LLMConfig(timeout=0.1)
        return cfg

    @pytest.fixture
    def hanging_llm(self) -> HangingLLMProvider:
        return HangingLLMProvider()

    @pytest.fixture
    async def agent_with_hanging_llm(
        self, bus, short_timeout_config, state, hanging_llm
    ) -> WellnessCompanionAgent:
        a = WellnessCompanionAgent()
        a.initialize(bus, short_timeout_config, state, hanging_llm)
        return a

    async def test_timeout_produces_fallback_response(
        self, agent_with_hanging_llm, bus, state
    ):
        """
        When the LLM call times out the agent must publish the crisis-safe
        fallback message rather than hanging indefinitely.
        """
        await state.create_patient({
            "id": "pat-timeout", "name": "Test", "dob": None,
            "preferences": {}, "emergency_contact": None, "caregiver_id": None,
        })
        await state.create_session({"id": "sess-timeout", "patient_id": "pat-timeout"})

        sent_events: list[MessageSentEvent] = []

        async def capture(event):
            sent_events.append(event)

        bus.subscribe(EventTypes.MESSAGE_SENT, capture, "test-timeout-capture")
        await bus.start()
        await agent_with_hanging_llm.start()

        event = MessageReceivedEvent(
            session_id="sess-timeout",
            patient_id="pat-timeout",
            content="Hello",
            message_id="msg-timeout-1",
        )

        # Should complete quickly (timeout=0.1 s) not in 3600 s
        await asyncio.wait_for(
            agent_with_hanging_llm.handle_event(event),
            timeout=5.0,
        )
        await asyncio.sleep(0.1)

        await agent_with_hanging_llm.stop()
        await bus.stop()

        # The fallback message must be published
        assert len(sent_events) == 1
        assert "having trouble" in sent_events[0].content.lower()

    async def test_timeout_does_not_hang(
        self, agent_with_hanging_llm, bus, state
    ):
        """
        handle_event() must return within a reasonable time even when
        the LLM provider never resolves.  Failure = test hangs > 5 s.
        """
        await state.create_patient({
            "id": "pat-hang", "name": "Test", "dob": None,
            "preferences": {}, "emergency_contact": None, "caregiver_id": None,
        })
        await state.create_session({"id": "sess-hang", "patient_id": "pat-hang"})

        await bus.start()
        await agent_with_hanging_llm.start()

        event = MessageReceivedEvent(
            session_id="sess-hang",
            patient_id="pat-hang",
            content="Tell me something",
            message_id="msg-hang-1",
        )

        # If RC2 is not fixed this will raise asyncio.TimeoutError after 5 s,
        # failing the test.  With the fix it should complete in ~0.1 s.
        import time
        start = time.monotonic()
        await asyncio.wait_for(
            agent_with_hanging_llm.handle_event(event),
            timeout=5.0,
        )
        elapsed = time.monotonic() - start

        await agent_with_hanging_llm.stop()
        await bus.stop()

        # Should finish well under 1 s (timeout is 0.1 s + overhead)
        assert elapsed < 2.0, f"handle_event took {elapsed:.2f} s — LLM timeout not firing"
