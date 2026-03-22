"""
Integration tests for the full chat message flow.

Verifies that a user message published to the EventBus travels through
the WellnessCompanionAgent and produces a MessageSentEvent with the correct
content — using a real EventBus, real in-memory SQLite StateManager,
and a MockLLMProvider.

@decision DEC-TEST-005
@title Integration tests exercise real agent wiring end-to-end
@status accepted
@rationale See tests/integration/conftest.py for full rationale. These
    tests prove that the publish -> subscribe -> handle_event -> publish
    chain works correctly with no component mocked out except the
    external LLM API.
"""

from __future__ import annotations

import asyncio

import pytest

from ada.agents.wellness_companion import WellnessCompanionAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import (
    AssessmentTriggeredEvent,
    EventTypes,
    MessageReceivedEvent,
    MessageSentEvent,
    MoodDetectedEvent,
    SessionStartedEvent,
)
from ada.core.state import StateManager

from .conftest import MockLLMProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def therapist(bus, config, state, llm, patient_id, session_id):
    """Fully wired, started WellnessCompanionAgent."""
    agent = WellnessCompanionAgent()
    agent.initialize(bus, config, state, llm)
    await bus.start()
    await agent.start()
    yield agent
    await agent.stop()
    await bus.stop()


# ---------------------------------------------------------------------------
# End-to-end message flow
# ---------------------------------------------------------------------------

class TestChatFlow:

    async def test_user_message_produces_message_sent_event(
        self, therapist, bus, session_id, patient_id
    ):
        """
        Publishing a MessageReceivedEvent to the bus should result in
        a MessageSentEvent being published by the WellnessCompanionAgent.
        """
        sent_events: list[MessageSentEvent] = []

        async def capture_sent(event):
            sent_events.append(event)

        bus.subscribe(EventTypes.MESSAGE_SENT, capture_sent, "test-capture-sent")

        event = MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content="I have been feeling really anxious lately.",
            message_id="msg-001",
        )
        await bus.publish(event)

        # Allow bus to drain and agent to process
        await asyncio.sleep(0.4)

        assert len(sent_events) == 1
        assert sent_events[0].session_id == session_id
        assert sent_events[0].patient_id == patient_id
        assert sent_events[0].agent_name == "wellness_companion"

    async def test_response_content_matches_mock_llm(
        self, therapist, bus, llm, session_id, patient_id
    ):
        """The MessageSentEvent content should equal the MockLLMProvider response."""
        llm.queue_response("That sounds really difficult. Can you tell me more?")

        sent_events: list[MessageSentEvent] = []

        async def capture(event):
            sent_events.append(event)

        bus.subscribe(EventTypes.MESSAGE_SENT, capture, "content-capture")

        await bus.publish(MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content="I feel hopeless sometimes.",
            message_id="msg-002",
        ))
        await asyncio.sleep(0.4)

        assert len(sent_events) == 1
        assert sent_events[0].content == "That sounds really difficult. Can you tell me more?"

    async def test_messages_persisted_to_state(
        self, therapist, bus, state, session_id, patient_id
    ):
        """Both user and assistant messages should be saved to SQLite."""
        await bus.publish(MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content="Hello, I need support.",
            message_id="msg-003",
        ))
        await asyncio.sleep(0.4)

        messages = await state.get_messages(session_id)
        roles = [m["role"] for m in messages]
        assert "user" in roles
        assert "assistant" in roles

    async def test_user_message_content_persisted_correctly(
        self, therapist, bus, state, session_id, patient_id
    ):
        """The exact user message text should appear in the saved messages."""
        user_text = "I've been struggling with sleep lately."
        await bus.publish(MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content=user_text,
            message_id="msg-004",
        ))
        await asyncio.sleep(0.4)

        messages = await state.get_messages(session_id)
        user_messages = [m for m in messages if m["role"] == "user"]
        assert any(m["content"] == user_text for m in user_messages)

    async def test_multiple_messages_accumulate_history(
        self, therapist, bus, state, llm, session_id, patient_id
    ):
        """
        Multiple exchanges should accumulate in the message history and
        be passed to the LLM for context on subsequent calls.
        """
        for i in range(3):
            await bus.publish(MessageReceivedEvent(
                session_id=session_id,
                patient_id=patient_id,
                content=f"Message number {i}",
                message_id=f"msg-multi-{i}",
            ))
            await asyncio.sleep(0.4)

        messages = await state.get_messages(session_id)
        # 3 user + 3 assistant = 6 messages
        assert len(messages) == 6

        # The third LLM call should have received more context
        assert len(llm.calls) == 3
        # Each successive call should have more messages in history
        assert len(llm.calls[2]["messages"]) > len(llm.calls[0]["messages"])

    async def test_session_started_event_handled(
        self, therapist, bus, session_id, patient_id
    ):
        """SESSION_STARTED event should be handled without error."""
        event = SessionStartedEvent(session_id=session_id, patient_id=patient_id)
        await bus.publish(event)
        await asyncio.sleep(0.2)
        # No crash = success

    async def test_mood_detected_event_published_for_sad_message(
        self, therapist, bus, session_id, patient_id
    ):
        """A message with negative keywords should trigger a MoodDetectedEvent."""
        mood_events: list[MoodDetectedEvent] = []

        async def capture_mood(event):
            mood_events.append(event)

        bus.subscribe(EventTypes.MOOD_DETECTED, capture_mood, "mood-capture")

        await bus.publish(MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content="I feel so sad and hopeless today.",
            message_id="msg-mood-001",
        ))
        await asyncio.sleep(0.4)

        assert len(mood_events) == 1
        assert mood_events[0].mood_label == "negative"
        assert mood_events[0].mood_score < 5.0

    async def test_no_mood_event_for_neutral_message(
        self, therapist, bus, session_id, patient_id
    ):
        """A neutral message should not trigger a MoodDetectedEvent."""
        mood_events: list[MoodDetectedEvent] = []

        async def capture_mood(event):
            mood_events.append(event)

        bus.subscribe(EventTypes.MOOD_DETECTED, capture_mood, "mood-capture-neutral")

        await bus.publish(MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content="The weather is nice today.",
            message_id="msg-neutral-001",
        ))
        await asyncio.sleep(0.4)

        assert len(mood_events) == 0

    async def test_assessment_triggered_for_phq_mention(
        self, therapist, bus, session_id, patient_id
    ):
        """A message mentioning PHQ-9 should trigger an AssessmentTriggeredEvent."""
        assessment_events: list[AssessmentTriggeredEvent] = []

        async def capture_assessment(event):
            assessment_events.append(event)

        bus.subscribe(
            EventTypes.ASSESSMENT_TRIGGERED,
            capture_assessment,
            "assessment-capture",
        )

        await bus.publish(MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content="Can I fill out a PHQ-9 assessment?",
            message_id="msg-phq-001",
        ))
        await asyncio.sleep(0.4)

        assert len(assessment_events) == 1
        assert assessment_events[0].instrument == "phq9"

    async def test_llm_failure_produces_fallback_response(
        self, bus, config, state, patient_id, session_id
    ):
        """
        When the LLM raises an exception, the WellnessCompanionAgent should publish
        a fallback response rather than silently failing.
        """
        class FailingLLMProvider(MockLLMProvider):
            async def complete(self, messages, **kwargs):
                raise RuntimeError("LLM service unavailable")

        failing_llm = FailingLLMProvider()
        agent = WellnessCompanionAgent()
        agent.initialize(bus, config, state, failing_llm)
        await bus.start()
        await agent.start()

        sent_events: list[MessageSentEvent] = []

        async def capture(event):
            sent_events.append(event)

        bus.subscribe(EventTypes.MESSAGE_SENT, capture, "fallback-capture")

        await bus.publish(MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content="Hello",
            message_id="msg-fail-001",
        ))
        await asyncio.sleep(0.4)

        await agent.stop()
        await bus.stop()

        assert len(sent_events) == 1
        # The fallback message should mention crisis resources
        assert "crisis" in sent_events[0].content.lower() or "trouble" in sent_events[0].content.lower()
